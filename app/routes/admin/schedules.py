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


@bp.route("/schedules")
@login_required
def schedules_screen():
    """Every schedule, what it means in words, and what is waiting on it."""
    db = get_db()
    return render_template(
        "admin/schedules.html",
        schedule_templates=[
            {"row": t, "says": scheduling.describe_template(t),
             "dates": scheduling.upcoming(t, scheduling.utcnow(), 3)}
            for t in scheduling.templates(db)],
        #  What is actually on the clock right now, whatever kind of
        #  thing it is. A schedule with nothing waiting on it is a
        #  schedule you can delete without wondering.
        waiting=scheduling.recent(db, limit=50),
        weekdays=scheduling.WEEKDAYS,
        repeats=scheduling.REPEATS,
        month_days=scheduling.MONTH_DAYS,
    )


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
    else:
        db.commit()
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
    if scheduling.delete_template(db, name):
        db.commit()
        flash("Removed. Anything already waiting keeps the time it was given.",
              "success")
    else:
        flash("That schedule is already gone.", "warning")
    return redirect(_back())


def _back():
    """Where to return. Only same-site paths, so this cannot be used to
    bounce somebody somewhere else."""
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("admin.schedules_screen")
