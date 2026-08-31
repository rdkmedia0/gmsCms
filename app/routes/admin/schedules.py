"""The times this site does things, in one place.

A schedule is not a property of a newsletter, a post or a backup: it is a
time this site acts at, and "the first Monday at nine" means the same
thing whichever of them is using it. It was defined on the Newsletters
screen and again on the Blog screen -- one list, two homes -- and picked
on a third, Backups, which could offer only what the other two happened
to have made. Landing on Backups first, you could see the picker and had
no way to fill it.

So the list lives here and nowhere else. Every screen that USES a
schedule keeps its own picker, because that is where the decision is
made; what moved is the making and the removing.

The routes are named for what they are. They were
`newsletter_schedule_template_save` and lived beside the newsletter
routes, which was true when a schedule was something only a newsletter
had, and became a lie the day a backup ran on one.
"""
from flask import flash, redirect, render_template, request, url_for

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import scheduling


#  Two screens, because they are two questions. "What times do I have"
#  is a short list you change twice a year; "what is on the clock" only
#  ever grows -- every send, every publish and every backup leaves a row,
#  and a year of automatic backups is 365 of them in front of the one
#  thing you were looking for.
STATES = (
    ("waiting", "Waiting"),
    ("going", "Going out now"),
    ("failed", "Did not go"),
    ("done", "Done"),
    ("all", "Everything"),
)


def _tabs(active):
    return [("Schedules", url_for("admin.schedules_screen"), active == "schedules"),
            ("Scheduled items", url_for("admin.scheduled_items"), active == "items")]


@bp.route("/schedules")
@login_required
def schedules_screen():
    """The times themselves: named once, picked wherever they are used."""
    db = get_db()
    return render_template(
        "admin/schedules.html",
        tabs=_tabs("schedules"),
        schedule_templates=[
            {"row": t, "says": scheduling.describe_template(t),
             "dates": scheduling.upcoming(t, scheduling.utcnow(), 3),
             #  What is relying on it, so the confirm can say what
             #  deleting it would actually do -- and backups are the
             #  quiet one, because they store a schedule by NAME.
             "uses": scheduling.uses_of(db, t["name"])}
            for t in scheduling.templates(db)],
        counts=scheduling.counts(db),
        #  The one being edited, if any. Editing was the gap: you could
        #  add one and delete one, and changing an hour meant retyping
        #  every field under exactly the same name and hoping.
        editing=scheduling.template(db, request.args.get("edit", "")),
        weekdays=scheduling.WEEKDAYS,
        repeats=scheduling.REPEATS,
        month_days=scheduling.MONTH_DAYS,
    )


@bp.route("/schedules/items")
@login_required
def scheduled_items():
    """What is on the clock, and what has been.

    Filtered rather than paged: the question is almost always "what is
    waiting" or "what failed", and both of those are short. Everything is
    there for the time it is not.
    """
    db = get_db()
    state = request.args.get("state", "waiting")
    if state not in dict(STATES):
        state = "waiting"
    return render_template(
        "admin/scheduled_items.html",
        tabs=_tabs("items"),
        state=state,
        states=STATES,
        counts=scheduling.counts(db),
        items=scheduling.items(db, state),
    )


@bp.route("/schedules/items/<int:row_id>/cancel", methods=["POST"])
@login_required
def scheduled_item_cancel(row_id):
    """Take one item off the clock.

    By its own id: this list is looking at ROWS rather than at the things
    they point to, and two newsletters can be waiting on the same
    schedule.
    """
    db = get_db()
    removed, why = scheduling.cancel_one(db, row_id)
    if removed:
        db.commit()
        flash("Taken off the clock.", "success")
    else:
        flash(why, "warning")
    return redirect(_back(url_for("admin.scheduled_items",
                                  state=request.form.get("state") or "waiting")))


@bp.route("/schedules/items/clear", methods=["POST"])
@login_required
def scheduled_items_clear():
    """Tidy away what has already happened.

    Finished rows only. Nothing waiting and nothing in flight can be
    cleared here, because clearing those would be cancelling them under a
    word that does not mean cancel.

    `newsletter_sends` -- the record that forty people were emailed -- is
    untouched. This is the job queue, not the history.
    """
    db = get_db()
    failed_only = request.form.get("only") == "failed"
    gone = scheduling.clear_finished(db, failed_only=failed_only)
    db.commit()
    flash("Cleared %d finished item%s. What was actually sent is still recorded."
          % (gone, "" if gone == 1 else "s") if gone
          else "There was nothing finished to clear.",
          "success" if gone else "warning")
    return redirect(_back(url_for("admin.scheduled_items",
                                  state=request.form.get("state") or "done")))


@bp.route("/schedules/save", methods=["POST"])
@login_required
def schedule_save():
    """Name a time. Saving the same name again replaces it."""
    db = get_db()
    saved, error = scheduling.save_template(
        db, request.form.get("name"), request.form.get("repeat_kind"),
        request.form.get("hour"), request.form.get("minute"),
        request.form.get("weekday") or None,
        request.form.get("monthday") or None,
        when=request.form.get("when") or None,
        #  The clock the hour was typed on. Without it "9am" is 9am UTC.
        tz_offset=request.form.get("tz_offset") or 0,
        #  The zone, not just the offset: only a zone knows when the
        #  clocks change, and an offset captured in summer is wrong all
        #  winter.
        tz_name=request.form.get("tz_name"),
        month_day=request.form.get("month_day") or "first")
    if error:
        flash(error, "error")
        return redirect(_back())
    #  Editing, with the name changed. save_template replaces BY NAME, so
    #  a renamed one would arrive as a second schedule and leave the
    #  original sitting there -- which is what "edit" must not do.
    was = (request.form.get("was") or "").strip()
    now = (request.form.get("name") or "").strip()
    renamed = bool(was) and was != now
    if renamed:
        #  Anything booked on the old name keeps its time and still goes;
        #  it simply carries a label nothing answers to any more. Said,
        #  rather than left to be discovered.
        moved = scheduling.uses_of(db, was)
        scheduling.delete_template(db, was)
    db.commit()
    if renamed and moved["waiting"]:
        flash("Saved as “%s”. %d thing%s already waiting under the old "
              "name keep%s the time it was given and still go."
              % (now, moved["waiting"], "" if moved["waiting"] == 1 else "s",
                 "s" if moved["waiting"] == 1 else ""), "warning")
    elif renamed and moved["backups"]:
        flash("Saved as “%s”. Automatic backups were set to the old "
              "name — pick this one on the Backups screen." % now, "warning")
    else:
        flash("Saved. You can pick it when you schedule a newsletter, a post "
              "or a backup.", "success")
    return redirect(_back())


@bp.route("/schedules/delete", methods=["POST"])
@login_required
def schedule_delete():
    """Remove one. Anything already waiting on it keeps the time it was
    given -- a schedule says when the next thing goes, so taking it away
    cannot un-book what it has already booked."""
    db = get_db()
    name = (request.form.get("name") or "").strip()
    #  Read BEFORE it goes, and said afterwards: what was relying on it
    #  is exactly what somebody needs told, and it cannot be counted once
    #  the row is gone.
    uses = scheduling.uses_of(db, name)
    if not scheduling.delete_template(db, name):
        flash("That schedule is already gone.", "warning")
        return redirect(_back())
    db.commit()
    said = ["Removed."]
    if uses["waiting"]:
        said.append("%d thing%s already waiting on it keep%s the time %s "
                    "given, and still go."
                    % (uses["waiting"], "" if uses["waiting"] == 1 else "s",
                       "s" if uses["waiting"] == 1 else "",
                       "it was" if uses["waiting"] == 1 else "they were"))
    if uses["backups"]:
        said.append("Automatic backups were set to it, so after the one already "
                    "booked they will stop — pick another schedule on the "
                    "Backups screen.")
    flash(" ".join(said), "warning" if uses["backups"] else "success")
    return redirect(_back())


def _back(default=None):
    """Where to return. Only same-site paths, so this cannot be used to
    bounce somebody somewhere else."""
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default or url_for("admin.schedules_screen")
