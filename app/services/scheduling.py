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


def schedule(db, kind, target_id, subject, audience, when_utc):
    """Put one send on the clock. Replaces any pending one for the same
    thing, because "schedule it" said twice means the second time."""
    cancel(db, kind, target_id)
    db.execute(
        "INSERT INTO newsletter_schedule (kind, target_id, subject, audience, send_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (kind, target_id, subject or "", audience or "all", _stamp(when_utc)))


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
