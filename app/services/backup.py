"""
Backups: the only answer to deletion, and to a database somebody has been
able to write to.

Nothing else in this app addresses either. Encryption protects a COPY of
the database from being read; it does nothing for one that has been
emptied, or quietly edited. That is what this is for, and it is why the
archive is deliberately restorable somewhere else entirely.

Two things here are less obvious than they look.

The database is snapshotted through SQLite itself (`VACUUM INTO`), never
copied as a file. Copying a database that is being written to produces an
archive that restores into corruption — and you would find that out on the
one day it matters. The same in reverse on restore: the archive's contents
are pushed into the LIVE database through SQLite's own backup API rather
than swapping files underneath a running app, so open connections and
in-flight requests stay consistent and no restart is required.

And `.encryption_key` is left out by default. With it, the archive is a
complete, portable compromise — Stripe key, Cal.com key, SMTP password,
all usable by whoever finds it in a synced cloud folder. Without it, a
restore onto a fresh machine needs those few credentials re-entered, which
is a small price for a backup that cannot spend your money.
"""
import datetime
import json
import os
import shutil
import sqlite3
import zipfile

from flask import current_app

from ..db import DATA_DIR, DB_PATH

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
MANIFEST_NAME = "manifest.json"
DB_NAME = "cms.db"
KEY_NAME = ".encryption_key"

#  What a backup covers, beyond the database.
MEDIA_SOURCES = (
    ("uploads", lambda app: os.path.join(app.static_folder, "uploads")),
    ("themes", lambda app: os.path.join(app.static_folder, "themes")),
    ("private_downloads", lambda app: os.path.join(DATA_DIR, "private_downloads")),
)

#  Subscribers are counted here for a reason beyond tidiness: an email
#  list is the one thing in this database that cannot be rebuilt by
#  hand. Pages can be typed again, orders live in Stripe as well -- the
#  people who agreed to hear from you, and the record of them agreeing,
#  exist here and nowhere else. The manifest is how somebody checks a
#  backup without opening it, so it says how many.
COUNTED_TABLES = ("pages", "sections", "templates", "orders", "customers",
                  "entitlements", "bookings", "digital_files", "subscribers")

#  There is no schedule list here any more.
#
#  Backups had their own: "Every day" or "Every week", with no time of
#  day, no timezone, and a claim of their own -- a second, weaker copy of
#  something this app already does properly. A backup now runs on one of
#  the NAMED schedules (services/scheduling.py), the same ones a
#  newsletter is sent on and a post is published on: made once, named by
#  the owner, and carrying the hour, the weekday or month day, and the
#  clock they were typed on.
#
#  What differs, and it is the only thing that does: a send happens ONCE
#  at the moment chosen, deliberately -- a schedule says when the next
#  one goes, it does not keep sending. A backup is the opposite: it is
#  worth nothing unless it keeps happening. So a backup job books the
#  next occurrence when it finishes. See `_run_scheduled`.


def backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _counts(db):
    out = {}
    for table in COUNTED_TABLES:
        try:
            out[table] = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        except sqlite3.Error:
            out[table] = None
    return out


def _snapshot_database(destination):
    """A consistent copy of the live database, taken while it is in use.

    VACUUM INTO runs inside a read transaction, so the result is one
    coherent point in time — unlike copying the file, which can catch a
    half-written page and produce an archive that only fails on the day
    it is needed.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("VACUUM INTO ?", (destination,))
    finally:
        conn.close()


def create_backup(db, app=None, include_media=True, include_key=False, label="manual"):
    """Writes a new archive and returns its filename."""
    app = app or current_app
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"backup_{stamp}.zip"
    path = os.path.join(backup_dir(), name)
    #  Two backups in the same second are not a hypothetical — taking one
    #  by hand while a scheduled one runs, or the safety copy taken during
    #  a restore, land on the same timestamp. Names are made unique rather
    #  than one archive silently replacing another, which is the exact
    #  failure this whole feature exists to prevent.
    suffix = 2
    while os.path.exists(path):
        name = f"backup_{stamp}-{suffix}.zip"
        path = os.path.join(backup_dir(), name)
        suffix += 1
    staging = os.path.join(backup_dir(), f".{stamp}.db")

    _snapshot_database(staging)
    manifest = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "includes_media": bool(include_media),
        "includes_encryption_key": bool(include_key),
        "counts": _counts(db),
    }
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            archive.write(staging, DB_NAME)
            if include_key:
                key_path = os.path.join(DATA_DIR, KEY_NAME)
                if os.path.exists(key_path):
                    archive.write(key_path, KEY_NAME)
            if include_media:
                for folder, resolve in MEDIA_SOURCES:
                    root = resolve(app)
                    if not os.path.isdir(root):
                        continue
                    for base, _dirs, files in os.walk(root):
                        for filename in files:
                            full = os.path.join(base, filename)
                            rel = os.path.relpath(full, root)
                            archive.write(full, os.path.join(folder, rel))
    finally:
        if os.path.exists(staging):
            os.remove(staging)
    return name


def list_backups():
    """Newest first, with whatever the manifest says about each."""
    #  Ordered by when each was actually written, not by name: names with
    #  a collision suffix do not sort in the order they were made, and
    #  "newest first" has to mean newest for prune() to drop the right
    #  ones.
    out = []
    names = [n for n in os.listdir(backup_dir()) if n.endswith(".zip")]
    for name in sorted(names, key=lambda n: os.path.getmtime(os.path.join(backup_dir(), n)),
                       reverse=True):
        path = os.path.join(backup_dir(), name)
        entry = {
            "name": name,
            "size": os.path.getsize(path),
            "created_at": datetime.datetime.fromtimestamp(
                os.path.getmtime(path)).isoformat(timespec="seconds"),
            "manifest": None,
        }
        try:
            with zipfile.ZipFile(path) as archive:
                entry["manifest"] = json.loads(archive.read(MANIFEST_NAME).decode())
        except (zipfile.BadZipFile, KeyError, ValueError, OSError):
            entry["broken"] = True
        out.append(entry)
    return out


def path_for(name):
    """Resolved path, or None if the name tries to leave the backup folder."""
    if not name or "/" in name or "\\\\" in name or not name.endswith(".zip"):
        return None
    path = os.path.abspath(os.path.join(backup_dir(), name))
    if os.path.commonpath([path, os.path.abspath(backup_dir())]) != os.path.abspath(backup_dir()):
        return None
    return path if os.path.exists(path) else None


def delete_backup(name):
    path = path_for(name)
    if not path:
        return False
    os.remove(path)
    return True


def prune(keep):
    """Drops the oldest beyond `keep`. Returns how many went."""
    if not keep or keep < 1:
        return 0
    archives = [b["name"] for b in list_backups()]
    removed = 0
    for name in archives[keep:]:
        if delete_backup(name):
            removed += 1
    return removed


def inspect(fileobj):
    """What an uploaded archive says it contains, before anything is
    replaced. Returns (manifest, error)."""
    try:
        with zipfile.ZipFile(fileobj) as archive:
            names = archive.namelist()
            if DB_NAME not in names:
                return None, "That archive has no database in it, so it isn't a backup of this site."
            manifest = json.loads(archive.read(MANIFEST_NAME).decode()) if MANIFEST_NAME in names else {}
            manifest["has_media"] = any(n.startswith(("uploads/", "themes/", "private_downloads/"))
                                        for n in names)
            manifest["has_key"] = KEY_NAME in names
            return manifest, None
    except (zipfile.BadZipFile, ValueError, KeyError) as e:
        return None, f"That file couldn't be read as a backup ({type(e).__name__})."


def restore(fileobj, app=None, restore_media=True):
    """Puts an archive back. (ok, error).

    The database goes back through SQLite's own backup API rather than by
    replacing the file: swapping a file underneath a running app leaves
    open connections pointing at an inode that no longer exists, and
    whether that shows up as stale reads or an error depends on timing.
    Pushing pages through SQLite instead is transactional, survives
    concurrent readers, and needs no restart.
    """
    app = app or current_app
    staging = os.path.join(backup_dir(), ".restore.db")
    try:
        with zipfile.ZipFile(fileobj) as archive:
            names = archive.namelist()
            if DB_NAME not in names:
                return False, "That archive has no database in it."
            with archive.open(DB_NAME) as source, open(staging, "wb") as target:
                shutil.copyfileobj(source, target)

            #  Refuse a file that is not actually a database before
            #  anything live is touched.
            probe = sqlite3.connect(staging)
            try:
                probe.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            except sqlite3.DatabaseError:
                return False, "The database inside that archive is unreadable."
            live = sqlite3.connect(DB_PATH)
            try:
                probe.backup(live)
            finally:
                live.close()
                probe.close()

            if restore_media:
                for folder, resolve in MEDIA_SOURCES:
                    root = resolve(app)
                    os.makedirs(root, exist_ok=True)
                    prefix = folder + "/"
                    for entry in names:
                        if not entry.startswith(prefix) or entry.endswith("/"):
                            continue
                        relative = entry[len(prefix):]
                        #  Same containment rule every extraction in this
                        #  app follows: never write outside the target.
                        destination = os.path.abspath(os.path.join(root, relative))
                        if os.path.commonpath([destination, os.path.abspath(root)]) != os.path.abspath(root):
                            continue
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        with archive.open(entry) as source, open(destination, "wb") as target:
                            shutil.copyfileobj(source, target)
    except (zipfile.BadZipFile, OSError, sqlite3.Error) as e:
        return False, f"Restore failed ({type(e).__name__}: {e})."
    finally:
        if os.path.exists(staging):
            os.remove(staging)
    return True, None


# ---------------------------------------------------------------- schedule


def settings_for(db):
    rows = {
        r["key"]: r["value"]
        for r in db.execute(
            "SELECT key, value FROM settings WHERE key IN "
            "('backup_schedule', 'backup_keep', 'backup_last_run', "
            "'backup_include_media')"
        ).fetchall()
    }
    return {
        #  The NAME of a schedule in schedule_templates, or empty for
        #  "not scheduled". It was "daily"/"weekly"/"off"; an install
        #  carrying one of those is migrated in db.py, so the old words
        #  never reach this.
        "schedule": rows.get("backup_schedule") or "",
        "keep": int(rows.get("backup_keep") or 7),
        "last_run": rows.get("backup_last_run") or "",
        "include_media": (rows.get("backup_include_media") or "1") != "0",
    }


def save_settings(db, schedule, keep, include_media):
    """Which schedule backups run on, how many to keep, and what goes in.

    The schedule is checked against the named ones rather than a fixed
    list of its own: a name that no longer exists means not scheduled,
    which is what deleting a schedule should do.
    """
    from . import scheduling
    schedule = (schedule or "").strip()
    if schedule and not scheduling.template(db, schedule):
        schedule = ""
    keep = max(1, min(60, int(keep or 7)))
    for key, value in (
        ("backup_schedule", schedule),
        ("backup_keep", str(keep)),
        ("backup_include_media", "1" if include_media else "0"),
    ):
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    return schedule


#  One backup schedule for the site, so the job it books has no target of
#  its own to point at. Zero, named here rather than written as a bare 0
#  in four places.
BACKUP_TARGET = 0


def book_next(db, when=None):
    """Puts the next backup on the clock, or takes it off.

    Called when the settings are saved and again by each run, because a
    backup that happens once is not a backup. Returns the moment booked,
    or None when nothing is scheduled.
    """
    from . import scheduling
    scheduling.cancel(db, "backup", BACKUP_TARGET)
    name = settings_for(db)["schedule"]
    if not name:
        return None
    row = scheduling.template(db, name)
    if not row:
        return None
    dates = scheduling.upcoming(row, when or scheduling.utcnow(), 1)
    if not dates:
        return None
    scheduling.schedule(db, "backup", BACKUP_TARGET, "Backup", "all", dates[0],
                        template_name=name)
    return dates[0]


def run_now(db, app=None):
    """Takes a scheduled backup and tidies up after it. Returns its name.

    No claim of its own: the job was already claimed by whoever is
    running it, the same way a scheduled send is. This used to hold a
    second claim -- a conditional UPDATE on a settings row -- which was
    the same idea implemented twice.
    """
    config = settings_for(db)
    name = create_backup(db, app=app, include_media=config["include_media"],
                         label="scheduled")
    prune(config["keep"])
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('backup_last_run', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (datetime.datetime.now().isoformat(timespec="seconds"),))
    return name
