"""
The files a site sells.

These cannot live in `app/static/uploads/` like every other upload in this
app. That directory is served straight off disk by Flask to anyone who
knows a URL, which is exactly right for a photo on a page and exactly
wrong for something a person paid for: the first buyer to share the link
would give it away to everybody. Paid files therefore live under DATA_DIR,
outside every served directory, and reach a buyer only by being streamed
through a route that has already checked their entitlement and counted the
download.

DATA_DIR is the same volume the database sits on, so a file survives a
container rebuild the same way the record of who bought it does.
"""
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from ..db import DATA_DIR

STORE_DIR = os.path.join(DATA_DIR, "private_downloads")

#  An allowlist, not a blocklist, for the reason every upload path in this
#  app uses one: a blocklist is a list of the attacks somebody already
#  thought of. Generous enough to cover what people actually sell —
#  ebooks, audio, video, artwork, fonts, templates, spreadsheets.
ALLOWED_EXTENSIONS = {
    ".pdf", ".epub", ".mobi", ".txt", ".rtf", ".md",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mov", ".m4v", ".webm",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".psd", ".ai", ".indd",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".odt", ".ods",
    ".ttf", ".otf", ".woff", ".woff2",
}


def store_dir():
    os.makedirs(STORE_DIR, exist_ok=True)
    return STORE_DIR


def save_upload(db, file):
    """(file_id, error). The stored name is generated, never the client's.

    The original name is kept only as a label — it is what the buyer's
    browser will save the file as, and it never touches the filesystem.
    """
    if not file or not file.filename:
        return None, "Please choose a file."
    #  The name is kept as the buyer typed it — "Wedding Guide.pdf", not
    #  "Wedding_Guide.pdf" — because it is only ever a label and the name
    #  their browser saves. It never becomes a path: the file on disk is
    #  a generated uuid. Stripped of any directory part and anything
    #  unprintable, and length-capped, so nothing odd reaches the header
    #  Werkzeug builds from it.
    original = (file.filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    original = "".join(ch for ch in original if ch.isprintable()).strip()[:120] or "file"
    ext = os.path.splitext(secure_filename(original))[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None, f"{ext or 'That file type'} isn't one we can sell as a download."
    stored_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(store_dir(), stored_name)
    file.save(path)
    cur = db.execute(
        "INSERT INTO digital_files (stored_name, original_name, size) VALUES (?, ?, ?)",
        (stored_name, original, os.path.getsize(path)),
    )
    return cur.lastrowid, None


def list_files(db):
    return db.execute("SELECT * FROM digital_files ORDER BY id DESC").fetchall()


def get_file(db, file_id):
    return db.execute("SELECT * FROM digital_files WHERE id = ?", (file_id,)).fetchone()


def path_for(row):
    """The file's real path, or None if it would land outside the store.

    The stored name is generated here so it should always be safe; the
    check stays because "should always be" is how directory traversal gets
    in. Same containment pattern as the image library's delete route.
    """
    if not row:
        return None
    path = os.path.abspath(os.path.join(store_dir(), row["stored_name"]))
    if os.path.commonpath([path, os.path.abspath(store_dir())]) != os.path.abspath(store_dir()):
        return None
    return path if os.path.exists(path) else None


def in_use(db, file_id):
    """How many buyers still have a live claim on this file."""
    row = db.execute(
        "SELECT COUNT(*) AS n FROM entitlements WHERE kind = 'download' AND ref = ? "
        "AND revoked_at IS NULL", (str(file_id),)
    ).fetchone()
    return row["n"] if row else 0


def delete_file(db, file_id):
    """(ok, error). Refuses while anyone can still claim it.

    Deleting it anyway would take away something people paid for, and the
    only sign would be a broken download weeks later. The rule that points
    at it has to be changed first — a deliberate decision, made once,
    rather than a surprise.
    """
    row = get_file(db, file_id)
    if not row:
        return False, "That file is already gone."
    claims = in_use(db, file_id)
    if claims:
        return False, (f"{claims} buyer{'s' if claims != 1 else ''} can still download this. "
                       "Point those products at a different file first.")
    path = path_for(row)
    if path:
        try:
            os.remove(path)
        except OSError as e:  # noqa: BLE001 - the row goes either way
            current_app.logger.warning("Could not remove %s: %s", path, e)
    db.execute("DELETE FROM digital_files WHERE id = ?", (file_id,))
    return True, None


def claim(db, entitlement, customer_id):
    """Spends one download and returns (file_row, error).

    Counted before the file is sent, for the same reason a session credit
    is taken before the booking is made: the alternative leaves a window
    where two clicks each get a free one.
    """
    cur = db.execute(
        "UPDATE entitlements SET used = used + 1 "
        "WHERE id = ? AND customer_id = ? AND kind = 'download' AND revoked_at IS NULL "
        "AND used < granted AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
        (entitlement, customer_id),
    )
    if not cur.rowcount:
        return None, "There are no downloads left on this."
    row = db.execute(
        "SELECT f.* FROM entitlements e JOIN digital_files f ON f.id = CAST(e.ref AS INTEGER) "
        "WHERE e.id = ?", (entitlement,)
    ).fetchone()
    if not path_for(row):
        #  Give the download back: the buyer did nothing wrong, and the
        #  owner needs to see this rather than a silent 404.
        db.execute("UPDATE entitlements SET used = MAX(0, used - 1) WHERE id = ?", (entitlement,))
        return None, "That file is missing. Please get in touch and we'll send it."
    return row, None
