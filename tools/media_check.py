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

#  ---- Pictures that are the same picture twice ----
#
#  By BYTES, never by name: a name says nothing about content, and the
#  earlier sweep that trusted names is how 77 orphans survived a cleanup.
#
#  The distinction that matters is WHERE the copies are. Two templates
#  holding identical bytes is CORRECT and must not be "fixed" -- a
#  template's pictures belong to the template (CLAUDE.md), and a shared
#  app-wide folder is exactly what made an exported package silently
#  incomplete. A fork carrying its own copy of what it forked is the
#  same thing and equally right. Two copies inside ONE template, or two
#  uploads of the same file, are waste.
import hashlib                                                     # noqa: E402
from collections import defaultdict                                # noqa: E402

by_hash = defaultdict(list)
static_root = app.static_folder
for base, dirs, files in os.walk(static_root):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "fonts")]
    for fname in files:
        if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        full = os.path.join(base, fname)
        try:
            with open(full, "rb") as fh:
                by_hash[hashlib.sha256(fh.read()).hexdigest()].append(full)
        except OSError:
            pass


def _owner(path):
    """Which template a picture belongs to, or None for an upload."""
    rel = os.path.relpath(path, static_root).replace(os.sep, "/")
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "themes" else None


wasted = 0
across = 0
for digest, paths in sorted(by_hash.items()):
    if len(paths) < 2:
        continue
    owners = [_owner(p) for p in paths]
    if len(set(owners)) == len(paths) and all(owners):
        #  One copy each, in different templates. Correct.
        across += 1
        continue
    size = os.path.getsize(paths[0])
    wasted += size * (len(paths) - 1)
    print("    DUPLICATE  %.0f KB, %d copies in the same place:" % (size / 1024, len(paths)))
    for path in paths:
        print("               %s" % os.path.relpath(path, static_root))

print()
print("  %d picture(s) shared between templates — correct, each owns its own copy" % across)
print("  %.2f MB of genuine duplication" % (wasted / 1048576))

print("  %d distinct media URLs fetched across every template and the live site" % checked)
print("  %d missing, %d served as the wrong type" % (missing, wrong_type))
print("  %d checks, %d failed" % (checked, missing + wrong_type))
sys.exit(1 if (missing or wrong_type) else 0)
