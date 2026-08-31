"""Sending a newsletter later.

The hard part of a scheduled send is not the clock, it is that this app
runs as TWO gunicorn workers against one SQLite file. Whatever wakes up
and looks for due sends is going to be running twice, so "find the due
rows and send them" would mail everybody twice. Every design decision
below follows from that.

**The claim is the lock.** Taking a job is one UPDATE with the state it
expects in its WHERE clause -- `claimed_at IS NULL` -- so exactly one
worker's UPDATE can match and `rowcount` says which one won. No lock
table, no advisory lock, nothing to leak if a process dies mid-send: a
row that was claimed and never finished is visible AS a claimed row and
can be reported rather than silently retried into a double send.

**A send that fails is not retried automatically.** It is written down
with its error and left for a person. An automatic retry of "send email
to forty people" cannot tell "the SMTP server was briefly down" from
"twenty of them already got it", and guessing wrong is the one failure
here that cannot be taken back.

**The clock is UTC in the database and local on the screen.** What the
owner types is their own time; what is stored is UTC, because a schedule
written in a zone that changes twice a year is a schedule that moves.

**The thread starts per worker, on the first request.** With `--preload`
the app is built in the master and forked, and threads do not survive a
fork -- so starting one at import time would leave a thread in the
master, where no requests are served, and none in the workers. It is
armed by the first request each worker handles instead. The consequence
worth knowing: a site nobody ever visits does not send. Scheduling one is
itself a request, so the thread is running from the moment there is
anything to do.
"""
import datetime
import threading
import time

#  How often to look. A minute is far finer than anybody schedules to,
#  and it costs one indexed query per worker per minute.
TICK_SECONDS = 60

_started = threading.Lock()
_running = False


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def to_utc(local_text, offset_minutes):
    """A `datetime-local` value plus the browser's offset, as UTC.

    The offset comes from the browser rather than a setting, because the
    person typing the time is the one looking at that clock. Returns None
    for anything unparseable -- a schedule this app cannot read is a
    schedule it must not accept.
    """
    if not local_text:
        return None
    try:
        naive = datetime.datetime.fromisoformat(local_text.strip())
    except (ValueError, TypeError):
        return None
    try:
        offset = int(offset_minutes)
    except (TypeError, ValueError):
        offset = 0
    #  getTimezoneOffset() is minutes to ADD to local to reach UTC.
    return (naive + datetime.timedelta(minutes=offset)).replace(
        tzinfo=datetime.timezone.utc, microsecond=0)


def _stamp(when):
    return when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def schedule(db, kind, target_id, subject, audience, when_utc, template_name=None):
    """Put one send on the clock. Replaces any pending one for the same
    thing, because "schedule it" said twice means the second time.

    `template_name` is the named schedule it came from, kept so the list
    can say "First Monday" rather than a timestamp somebody has to
    decode. Null for a moment somebody typed.
    """
    cancel(db, kind, target_id)
    db.execute(
        "INSERT INTO newsletter_schedule (kind, target_id, subject, audience, "
        "send_at, template_name) VALUES (?, ?, ?, ?, ?, ?)",
        (kind, target_id, subject or "", audience or "all", _stamp(when_utc),
         template_name))


def cancel(db, kind, target_id):
    """Take back anything not yet claimed. A claimed one is already going
    out and cannot be recalled -- saying otherwise would be a lie."""
    return db.execute(
        "DELETE FROM newsletter_schedule WHERE kind = ? AND target_id = ? "
        "AND claimed_at IS NULL", (kind, target_id)).rowcount


def pending_for(db, kind, target_id):
    """The one still waiting, if there is one."""
    return db.execute(
        "SELECT * FROM newsletter_schedule WHERE kind = ? AND target_id = ? "
        "AND claimed_at IS NULL ORDER BY send_at LIMIT 1",
        (kind, target_id)).fetchone()


def recent(db, limit=20):
    """What is waiting, and what has just gone -- so a schedule is
    something you can look at rather than something you have to trust."""
    return db.execute(
        "SELECT * FROM newsletter_schedule ORDER BY send_at DESC LIMIT ?",
        (limit,)).fetchall()


def due(db, now=None):
    return db.execute(
        "SELECT * FROM newsletter_schedule WHERE claimed_at IS NULL AND send_at <= ? "
        "ORDER BY send_at", (_stamp(now or utcnow()),)).fetchall()


def claim(db, row_id):
    """Take one job, or find that somebody else already has it.

    The whole lock is the WHERE clause: two workers issue this UPDATE and
    only the first one changes a row, because after it the row no longer
    matches `claimed_at IS NULL`. Commit immediately -- the claim has to
    be visible to the other worker BEFORE this one starts the slow part.
    """
    taken = db.execute(
        "UPDATE newsletter_schedule SET claimed_at = ? WHERE id = ? AND claimed_at IS NULL",
        (_stamp(utcnow()), row_id)).rowcount
    db.commit()
    return taken == 1


def finish(db, row_id, sent, failed, error=None):
    db.execute(
        "UPDATE newsletter_schedule SET done_at = ?, sent = ?, failed = ?, error = ? "
        "WHERE id = ?",
        (_stamp(utcnow()), sent, failed, error, row_id))
    db.commit()


def start(app, run_one):
    """Arm the poller for THIS process, once.

    `run_one(app, row)` is passed in rather than imported, because the
    sending lives in the routes layer and a service never reaches back up
    into it (CLAUDE.md: import direction is one-way).
    """
    global _running
    with _started:
        if _running:
            return False
        _running = True

    def loop():
        while True:
            time.sleep(TICK_SECONDS)
            try:
                with app.app_context():
                    from ..db import get_db
                    db = get_db()
                    for row in due(db):
                        if not claim(db, row["id"]):
                            continue        # another worker got there first
                        run_one(app, row)
            except Exception as e:          # noqa: BLE001
                #  A poller that dies on one bad job stops every later
                #  one, silently. Anything unexpected is logged and the
                #  next tick tries again.
                app.logger.exception("scheduled send tick failed: %s", e)

    thread = threading.Thread(target=loop, name="cms-scheduled-sends", daemon=True)
    thread.start()
    return True


#  ---- Named schedules ---------------------------------------------------
#
#  A time somebody sends at, defined once and assigned, rather than a
#  datetime retyped into a box every month. The list then says "First
#  Monday" where it used to say a timestamp.
#
#  The shape a mail scheduler offers, because that is the one people
#  already know: every day, every week on a chosen day, every month on a
#  chosen date, or a one-off time.
#
#  **Assigning one sets the NEXT occurrence. It does not re-send.** A
#  schedule that mailed identical words to the same list every month is a
#  thing nobody can take back, so a repeating schedule answers "when is
#  the next one" and the sending stays a decision somebody makes. What
#  `last_used_at` records is when this schedule last put something on the
#  clock, which is the question "when did this last go" actually asks.
REPEATS = (("daily", "Every day"),
           ("weekly", "Every week"),
           ("monthly", "Every month"),
           ("once", "Once, at a set time"))

WEEKDAYS = (("0", "Monday"), ("1", "Tuesday"), ("2", "Wednesday"),
            ("3", "Thursday"), ("4", "Friday"), ("5", "Saturday"),
            ("6", "Sunday"))


def templates(db):
    """Every named schedule, oldest first so the list does not shuffle."""
    try:
        return db.execute(
            "SELECT * FROM schedule_templates ORDER BY id").fetchall()
    except Exception:  # noqa: BLE001 - a missing table must not break a screen
        return []


def template(db, name):
    try:
        return db.execute("SELECT * FROM schedule_templates WHERE name = ?",
                          (name,)).fetchone()
    except Exception:  # noqa: BLE001
        return None


def save_template(db, name, repeat_kind, hour, minute, weekday=None,
                  monthday=None, when=None):
    """(saved, error). Saving the same name again replaces it."""
    name = (name or "").strip()
    if not name:
        return False, "Give it a name so you can pick it out later."
    if repeat_kind not in dict(REPEATS):
        return False, "Choose how often it repeats."

    def _int(value, low, high, default=None):
        try:
            n = int(value)
        except (TypeError, ValueError):
            return default
        return n if low <= n <= high else default

    #  A one-off carries its whole moment; the repeating ones carry the
    #  part of it that repeats.
    if repeat_kind == "once":
        moment = to_utc(when, 0)
        if moment is None:
            return False, "Give it a date and a time."
        hour, minute, weekday, monthday = moment.hour, moment.minute, None, None
        once_at = _stamp(moment)
    else:
        once_at = None
        hour = _int(hour, 0, 23, 9)
        minute = _int(minute, 0, 59, 0)
        weekday = _int(weekday, 0, 6, 0) if repeat_kind == "weekly" else None
        #  28, not 31: a schedule set to the 30th silently never happens
        #  in February, which is a gap nobody notices for a year.
        monthday = _int(monthday, 1, 28, 1) if repeat_kind == "monthly" else None

    db.execute(
        "INSERT INTO schedule_templates (name, repeat_kind, hour, minute, "
        "weekday, monthday, once_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET repeat_kind = excluded.repeat_kind, "
        "hour = excluded.hour, minute = excluded.minute, "
        "weekday = excluded.weekday, monthday = excluded.monthday, "
        "once_at = excluded.once_at",
        (name, repeat_kind, hour, minute, weekday, monthday, once_at))
    return True, None


def delete_template(db, name):
    return db.execute("DELETE FROM schedule_templates WHERE name = ?",
                      (name,)).rowcount > 0


def mark_used(db, name, when):
    """When this schedule last put something on the clock."""
    if not name:
        return
    db.execute("UPDATE schedule_templates SET last_used_at = ? WHERE name = ?",
               (_stamp(when) if hasattr(when, "strftime") else when, name))


def describe_template(row):
    """The schedule in words, which is what a list column should say."""
    at = "%02d:%02d" % (row["hour"], row["minute"])
    kind = row["repeat_kind"] if "repeat_kind" in row.keys() else "weekly"
    if kind == "daily":
        return "Every day at %s" % at
    if kind == "monthly":
        return "Day %d of every month at %s" % (row["monthday"] or 1, at)
    if kind == "once":
        return "Once, at %s" % ((row["once_at"] or "")[:16] or at)
    day = dict(WEEKDAYS).get(str(row["weekday"] if row["weekday"] is not None else 0), "")
    return "Every %s at %s" % (day, at)


def next_occurrence(row, now):
    """When this named schedule next comes round, from `now` (UTC-naive).

    Worked out rather than stored, because "the first Monday" is a rule
    and a stored date is an answer that goes stale the moment it passes.
    """
    kind = row["repeat_kind"] if "repeat_kind" in row.keys() else "weekly"
    if kind == "once":
        try:
            return datetime.datetime.strptime(row["once_at"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None
    when = now.replace(hour=row["hour"], minute=row["minute"],
                       second=0, microsecond=0)
    if kind == "daily":
        return when if when > now else when + datetime.timedelta(days=1)
    if kind == "monthly":
        day = row["monthday"] or 1
        if when.day > day or (when.day == day and when <= now):
            month = when.month + 1
            year = when.year + (1 if month > 12 else 0)
            month = 1 if month > 12 else month
            return when.replace(year=year, month=month, day=day)
        return when.replace(day=day)
    weekday = row["weekday"] if row["weekday"] is not None else 0
    ahead = (weekday - when.weekday()) % 7
    when = when + datetime.timedelta(days=ahead)
    return when if when > now else when + datetime.timedelta(days=7)
