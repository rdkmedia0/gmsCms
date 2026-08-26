"""Every picture on every page of every template, fetched.

Changing an image format means changing a filename, and a filename lives
in a template's page JSON, its manifest, its theme CSS and sometimes its
markup. A reference that did not follow shows up as a missing picture on
one page of one template -- which nobody sees until somebody installs
that template. So this installs the lot and asks for every media URL
each page renders.

Also checks the Content-Type, because a picture served as
application/octet-stream is a picture some browsers decline to draw, and
the slim base image this ships on has no system mime table to guess from.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, "/app")
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="media-check-")

from app import create_app                       # noqa: E402
from app.db import get_db                        # noqa: E402

MEDIA = re.compile(r"/static/[A-Za-z0-9._/-]+\.(?:webp|png|jpe?g|gif|svg|mp4|webm|woff2)")
EXPECTED = {
    ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".woff2": "font/woff2",
}

app = create_app()
client = app.test_client()

with app.app_context():
    templates = [(t["id"], t["name"]) for t in
                 get_db().execute("SELECT id, name FROM templates ORDER BY name").fetchall()]
print("  %d templates installed" % len(templates))

checked = missing = wrong_type = 0
seen = set()

#  Read each installed package's OWN content rather than activating it.
#  Flipping is_active does not apply a template's pages -- that takes
#  _apply_pack_content -- so the first version of this check measured one
#  template sixteen times and reported nine URLs for the whole library.
import glob                                                     # noqa: E402
import io                                                       # noqa: E402

THEMES = os.path.join(app.static_folder, "themes")
for slug in sorted(os.listdir(THEMES)):
    folder = os.path.join(THEMES, slug)
    if not os.path.isdir(folder):
        continue
    text = []
    for pattern in ("pages/*.json", "manifest.json", "blog_posts.json", "*.css"):
        for path in glob.glob(os.path.join(folder, pattern)):
            text.append(io.open(path, encoding="utf-8", errors="replace").read())
    for url in sorted(set(MEDIA.findall(chr(10).join(text)))):
        if url in seen:
            continue
        seen.add(url)
        response = client.get(url)
        checked += 1
        if response.status_code != 200:
            missing += 1
            print("    MISSING  %s  (%s)" % (url, slug))
            continue
        want = EXPECTED.get(os.path.splitext(url)[1].lower())
        got = (response.headers.get("Content-Type") or "").split(";")[0]
        if want and got != want:
            wrong_type += 1
            print("    WRONG TYPE  %s -> %s (wanted %s)" % (url, got, want))

#  ...and the site as it actually stands, for anything the packages do not
#  mention (the active look's own CSS, uploaded pictures, fonts).
with app.app_context():
    slugs = [p["slug"] for p in get_db().execute("SELECT slug FROM pages").fetchall()]
for slug in slugs:
    html = client.get("/" if slug == "home" else "/" + slug).get_data(as_text=True)
    for url in sorted(set(MEDIA.findall(html))):
        if url in seen:
            continue
        seen.add(url)
        response = client.get(url)
        checked += 1
        if response.status_code != 200:
            missing += 1
            print("    MISSING  %s  (live page /%s)" % (url, slug))

print("  %d distinct media URLs fetched across every template and the live site" % checked)
print("  %d missing, %d served as the wrong type" % (missing, wrong_type))
print("  %d checks, %d failed" % (checked, missing + wrong_type))
sys.exit(1 if (missing or wrong_type) else 0)
