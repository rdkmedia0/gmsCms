"""
The Backups screen.

Thin, like every route file here: parse the request, call
services/backup.py, redirect. The interesting decisions — how the
database is snapshotted, why the encryption key is left out, how two
workers avoid both running the same scheduled backup — all live in the
service, where they can be read in one place.
"""
import os

from flask import request, flash, redirect, url_for, render_template, send_file, current_app

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import backup


@bp.route("/backups")
@login_required
def backups():
    db = get_db()
    return render_template(
        "admin/backups.html",
        backups=backup.list_backups(),
        settings=backup.settings_for(db),
        schedules=backup.SCHEDULES,
        backup_dir=backup.BACKUP_DIR,
    )


@bp.route("/backups/create", methods=["POST"])
@login_required
def backup_create():
    db = get_db()
    include_media = request.form.get("include_media") == "1"
    include_key = request.form.get("include_key") == "1"
    try:
        name = backup.create_backup(db, current_app, include_media, include_key)
    except OSError as e:  # noqa: BLE001 - disk full, permissions, unmounted volume
        flash(f"Couldn't write the backup — {e}", "error")
        return redirect(url_for("admin.backups"))
    backup.prune(backup.settings_for(db)["keep"])
    if include_key:
        flash(f"{name} created — it contains your encryption key, so treat the file itself as a "
              "credential: anyone who has it has your Stripe and Cal.com keys.", "warning")
    else:
        flash(f"{name} created. Download a copy somewhere off this machine — a backup that only "
              "exists on the volume it is backing up protects you from mistakes, not from losing "
              "the machine.", "success")
    return redirect(url_for("admin.backups"))


@bp.route("/backups/<name>/download")
@login_required
def backup_download(name):
    path = backup.path_for(name)
    if not path:
        flash("That backup doesn't exist.", "error")
        return redirect(url_for("admin.backups"))
    return send_file(path, as_attachment=True, download_name=name)


@bp.route("/backups/<name>/delete", methods=["POST"])
@login_required
def backup_delete(name):
    flash("Backup deleted." if backup.delete_backup(name) else "That backup doesn't exist.",
          "success" if backup.path_for(name) is None else "error")
    return redirect(url_for("admin.backups"))


@bp.route("/backups/restore", methods=["POST"])
@login_required
def backup_restore():
    """Restores, after taking a snapshot of what is about to be replaced.

    The snapshot is not politeness. A restore is the one action here that
    destroys current data on purpose, and the moment someone reaches for
    it is the moment they are least likely to be thinking clearly — the
    wrong file, or the right file from the wrong week, is otherwise
    unrecoverable.
    """
    db = get_db()
    name = (request.form.get("name") or "").strip()
    upload = request.files.get("archive")

    if name:
        path = backup.path_for(name)
        if not path:
            flash("That backup doesn't exist.", "error")
            return redirect(url_for("admin.backups"))
        source = open(path, "rb")
    elif upload and upload.filename:
        source = upload.stream
    else:
        flash("Choose a backup to restore, or upload one.", "error")
        return redirect(url_for("admin.backups"))

    try:
        manifest, error = backup.inspect(source)
        if error:
            flash(error, "error")
            return redirect(url_for("admin.backups"))
        source.seek(0)
        try:
            safety = backup.create_backup(db, current_app, include_media=False,
                                          label="before-restore")
        except OSError:
            safety = None
        ok, error = backup.restore(source, current_app,
                                   restore_media=request.form.get("restore_media") == "1")
    finally:
        if name:
            source.close()

    if not ok:
        flash(error, "error")
        return redirect(url_for("admin.backups"))
    taken = manifest.get("created_at", "an earlier date") if manifest else "an earlier date"
    note = f" Your previous state was saved as {safety} first." if safety else ""
    flash(f"Restored from {taken}.{note}", "success")
    return redirect(url_for("admin.backups"))


@bp.route("/backups/settings", methods=["POST"])
@login_required
def backup_settings():
    db = get_db()
    backup.save_settings(
        db,
        request.form.get("schedule"),
        request.form.get("keep", type=int),
        request.form.get("include_media") == "1",
    )
    db.commit()
    flash("Backup schedule saved.", "success")
    return redirect(url_for("admin.backups"))
