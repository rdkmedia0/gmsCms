"""Does the email list survive a backup, a restore, and a restart?

Asked because it is the one thing in this database that cannot be typed
again. A page can be rewritten; the people who agreed to hear from you,
and the record of them agreeing, exist here and nowhere else.

Run against a site of its own, so nothing here touches a real list:

    docker compose exec -T web python /tmp/pc.py            # phase one
    docker compose exec -T web python /tmp/pc.py --after    # after a restart

Phase one builds a site in a fixed directory, puts a subscriber on it,
takes a backup, deletes the subscriber, restores, and checks they came
back with every column intact. `--after` reopens the same directory
without seeding anything and checks the row is still there -- which is
what a restart actually tests, since the whole point is that the data is
on a mounted volume rather than inside the container.
"""
import os
import sys

sys.path.insert(0, "/app")

HOME = "/app/data/.persistence-check"
os.environ["DATA_DIR"] = HOME

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app.services import backup, subscribers                  # noqa: E402

AFTER = "--after" in sys.argv
failures = []


def check(name, ok, detail=""):
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


app = create_app()

if AFTER:
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM subscribers WHERE email = 'kept@example.com'").fetchone()
        check("the subscriber is still there after a restart", row is not None)
        if row:
            check("with their consent wording", row["consent_text"] == "Yes, email me occasional updates.")
            check("with when they confirmed, and from where",
                  bool(row["confirmed_at"]) and row["confirm_ip"] == "203.0.113.7")
            check("with when the invitation was sent", bool(row["confirm_sent_at"]))
        check("the backup file is still on disk",
              any(b["name"].endswith(".zip") for b in backup.list_backups()))
    print()
    print("%d checks, %d failed" % (4 + 1, len(failures)))
    sys.exit(1 if failures else 0)

with app.app_context():
    db = get_db()
    db.execute("DELETE FROM subscribers")
    status, token = subscribers.add(db, "kept@example.com",
                                    "Yes, email me occasional updates.",
                                    source="http://example.com/", ip="198.51.100.4")
    subscribers.mark_confirmation_sent(db, "kept@example.com")
    subscribers.confirm(db, token, ip="203.0.113.7")
    db.commit()
    before = dict(db.execute("SELECT * FROM subscribers WHERE email = 'kept@example.com'").fetchone())
    check("a confirmed subscriber exists to test with", bool(before["confirmed_at"]))

    #  ------------------------------------------------------ the backup
    name = backup.create_backup(db, label="persistence check")
    path = backup.path_for(name)
    check("a backup was written", bool(path) and os.path.exists(str(path)), str(path))

    #  What the manifest says about it, without opening the archive.
    import json
    import zipfile
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read(backup.MANIFEST_NAME))
        names = z.namelist()
    check("the manifest counts the email list", manifest["counts"].get("subscribers") == 1,
          repr(manifest["counts"].get("subscribers")))
    check("the archive carries the database", backup.DB_NAME in names)
    check("and deliberately not the encryption key", backup.KEY_NAME not in names)

    #  The archive's own copy of the table, read straight out of it.
    import shutil
    import sqlite3
    import tempfile
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(path) as z:
        z.extract(backup.DB_NAME, tmp)
    inside = sqlite3.connect(os.path.join(tmp, backup.DB_NAME))
    inside.row_factory = sqlite3.Row
    archived = inside.execute("SELECT * FROM subscribers WHERE email = 'kept@example.com'").fetchone()
    check("the person is inside the archive", archived is not None)
    if archived:
        for column in ("consent_text", "source", "ip", "created_at",
                       "confirm_sent_at", "confirmed_at", "confirm_ip", "token"):
            check("the archive keeps: %s" % column, archived[column] == before[column],
                  "%r vs %r" % (archived[column], before[column]))
    inside.close()
    shutil.rmtree(tmp, ignore_errors=True)

    #  ----------------------------------------------------- the restore
    db.execute("DELETE FROM subscribers")
    db.commit()
    check("the list is empty before restoring", db.execute(
        "SELECT COUNT(*) FROM subscribers").fetchone()[0] == 0)

with app.app_context():
    with open(path, "rb") as archive:
        ok, error = backup.restore(archive)
    check("the restore reported success", ok, str(error))

with app.app_context():
    db = get_db()
    back = db.execute("SELECT * FROM subscribers WHERE email = 'kept@example.com'").fetchone()
    check("restoring brings the person back", back is not None)
    if back:
        same = all(back[c] == before[c] for c in
                   ("consent_text", "source", "ip", "created_at", "confirm_sent_at",
                    "confirmed_at", "confirm_ip", "token"))
        check("with every part of the consent record", same)
        check("and their unsubscribe link still works", back["token"] == before["token"])

print()
print("%d checks, %d failed" % (21, len(failures)))
if failures:
    print("failed:", ", ".join(failures))
print()
print("Now restart the app and run this again with --after.")
sys.exit(1 if failures else 0)
