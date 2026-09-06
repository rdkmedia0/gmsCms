"""Does a file still land, in a section and in a cell?

The render check proves the markup did not move and the placement matrix
proves every tool still draws itself, but neither one posts a FILE. These
three routes were just merged, so this walks an actual upload through
both containers on a throwaway site.
"""
import io as _io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")
DATA_DIR = tempfile.mkdtemp(prefix="upload-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import bootstrap                                     # noqa: E402

#  A real, tiny PNG (1x1, transparent) so the extension check has
#  something honest to accept.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "0557bfabd40000000049454e44ae426082")

failures = []


def check(name, ok, detail=""):
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


app = create_app()
#  Its own uploads folder as well as its own database. Without this the
#  files it posts land in the real one -- which is shared, since
#  UPLOAD_FOLDER is a path in the image rather than something DATA_DIR
#  moves -- and every Image Library picker on the site then offers a
#  1x1 test PNG. That is exactly what happened the first time this ran,
#  and the render check noticed before anybody else did.
app.config["UPLOAD_FOLDER"] = os.path.join(DATA_DIR, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
client = app.test_client()

with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    bootstrap.clear_generated_password_flag(db, uid)
    page = db.execute("SELECT id FROM pages ORDER BY id LIMIT 1").fetchone()
    #  One Image section, and one Columns section with a cell to drop into.
    cur = db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                     "VALUES (?, 'image', '', '', 900)", (page["id"],))
    image_id = cur.lastrowid
    cur = db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                     "VALUES (?, 'columns', '', ?, 901)",
                     (page["id"], json.dumps({"columns": ["", ""]})))
    columns_id = cur.lastrowid
    cur = db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                     "VALUES (?, 'file', '', '', 902)", (page["id"],))
    file_id = cur.lastrowid
    cur = db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                     "VALUES (?, 'media', '', '', 903)", (page["id"],))
    media_id = cur.lastrowid
    db.commit()

with client.session_transaction() as s:
    s["user_id"] = uid

def post(url, field, name, data=PNG):
    return client.post(url, data={field: (_io.BytesIO(data), name)},
                       content_type="multipart/form-data",
                       #  X-Inline-Edit is what wants_json() actually looks
                       #  for -- the editor sets it on every save. Without it
                       #  these routes correctly flash and redirect, which is
                       #  the no-script path and not what is being tested.
                       headers={"Origin": "http://localhost", "X-Inline-Edit": "1"})

#  ------------------------------------------------------- as a section
r = post("/admin/sections/%d/image-upload" % image_id, "image", "hello.png")
body = r.get_json() or {}
check("a picture uploads to a section", r.status_code == 200 and body.get("ok"), str(body))
check("and the section now points at it", (body.get("url") or "").startswith("/static/uploads/"))
with app.app_context():
    row = get_db().execute("SELECT content FROM sections WHERE id = ?", (image_id,)).fetchone()
    check("saved on the row itself", row["content"] == body.get("url"))
    check("the file is really on disk", os.path.exists(os.path.join(
        app.config["UPLOAD_FOLDER"], os.path.basename(body.get("url", "x")))))

#  ---------------------------------------------------------- as a cell
r = post("/admin/sections/%d/columns/0/image-upload" % columns_id, "image", "hello.png")
body = r.get_json() or {}
check("the same picture uploads into a cell", r.status_code == 200 and body.get("ok"), str(body))
with app.app_context():
    row = get_db().execute("SELECT content FROM sections WHERE id = ?", (columns_id,)).fetchone()
    cell = json.loads(row["content"])["columns"][0]
    check("the cell holds it", isinstance(cell, dict) and cell.get("content") == body.get("url"))
    check("and knows it is an Image", cell.get("type") == "image" and cell.get("tool_name") == "Image")

#  -------------------------------------------------- what is refused
r = post("/admin/sections/%d/image-upload" % image_id, "image", "sneaky.exe", b"MZ")
check("an executable is refused as a section", r.status_code == 400, str(r.status_code))
r = post("/admin/sections/%d/columns/0/image-upload" % columns_id, "image", "sneaky.exe", b"MZ")
check("and refused in a cell too", r.status_code == 400, str(r.status_code))
r = client.post("/admin/sections/%d/image-upload" % image_id, data={},
                content_type="multipart/form-data",
                headers={"Origin": "http://localhost", "X-Inline-Edit": "1"})
check("no file at all is refused", r.status_code == 400)

#  ------------------------------------------------ a download, and media
r = post("/admin/sections/%d/file-upload" % file_id, "file", "notes.pdf", b"%PDF-1.4 tiny")
body = r.get_json() or {}
check("a file uploads to a section", r.status_code == 200 and body.get("ok"), str(body))
check("its size is measured", (body.get("size") or 0) > 0, str(body.get("size")))
with app.app_context():
    row = get_db().execute("SELECT title, file_size FROM sections WHERE id = ?", (file_id,)).fetchone()
    check("the name it arrived under becomes the label", row["title"] == "notes.pdf")
    check("and the size is on the row", row["file_size"] == body.get("size"))

r = post("/admin/sections/%d/columns/1/file-upload" % columns_id, "file", "notes.pdf", b"%PDF-1.4 tiny")
body = r.get_json() or {}
check("a file uploads into a cell", r.status_code == 200 and body.get("ok"), str(body))
with app.app_context():
    cell = json.loads(get_db().execute(
        "SELECT content FROM sections WHERE id = ?", (columns_id,)).fetchone()["content"])["columns"][1]
    check("the cell keeps the label and the size",
          cell.get("title") == "notes.pdf" and cell.get("file_size") == body.get("size"), str(cell))

r = post("/admin/sections/%d/media-upload" % media_id, "media", "clip.mp4", b"\x00\x00\x00\x18ftypmp42")
body = r.get_json() or {}
check("a video uploads to a section", r.status_code == 200 and body.get("ok"), str(body))
check("and is recognised as video", body.get("media_type") == "video", str(body.get("media_type")))
r = post("/admin/sections/%d/media-upload" % media_id, "media", "song.mp3", b"ID3")
check("an audio file is recognised as audio",
      (r.get_json() or {}).get("media_type") == "audio")

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (19, len(failures)))
if failures:
    print("failed:", ", ".join(failures))
sys.exit(1 if failures else 0)
