"""Does the Background control reach the page on every template?

It did not. Every shipped theme painted the body itself, reading a
--site-body-bg the app only sets for a zone override, so the theme's own
fallback colour always won and the control did nothing on sixteen
templates. A theme says what its ground is in its manifest now, and
site-base.css paints it: zone override, then the owner's choice, then
the template's own.

Two halves. The static half reads every installed theme and refuses a
body that paints, or a private --site-body-bg. The live half sets the
ground through the real route and checks what the page emits: any
colour is taken, the ink flips with it, nonsense is refused, the reset
works, and a zone override on the body still wins.

The browser half -- that the computed colour of the body really IS the
ground on all twenty -- is tools/ground_browser_check.py, run on the
host, because no server-side test can see the cascade.

Run inside the container:

    docker compose exec -T web python tools/ground_check.py
"""
import glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, "/app")
DATA_DIR = tempfile.mkdtemp(prefix="ground-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import bootstrap                                     # noqa: E402

app = create_app()
client = app.test_client()
passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    print("%-62s %s%s" % (what, "ok" if ok else "FAILED",
                          ("  " + str(detail)) if detail and not ok else ""))
    passed += bool(ok)
    failed += not ok


print("Every shipped theme")
print("-" * 70)
#  The shipped ones -- each has a zip behind it. static/themes also holds
#  whatever this install has saved or generated, and a checker's own
#  leftovers, none of which this is about.
shipped = {os.path.basename(z)[:-4] for z in glob.glob("/app/app/data/template-packages/*.zip")}
themes = sorted(p for p in glob.glob(os.path.join(app.static_folder, "themes", "*"))
                if os.path.basename(p) in shipped)
check("there are templates to look at", len(themes) >= 16, len(themes))
painting, private, no_ground = [], [], []
for folder in themes:
    slug = os.path.basename(folder)
    css_path = os.path.join(folder, "theme.css")
    if os.path.exists(css_path):
        css = re.sub(r"/\*.*?\*/", "", open(css_path, encoding="utf-8").read(), flags=re.S)
        body = re.search(r"^body[^{]*\{([^}]*)\}", css, flags=re.M)
        if body and re.search(r"(^|;)\s*(background(-color)?|color)\s*:", body.group(1)):
            painting.append(slug)
        if re.search(r"--site-body-bg\s*:", css):
            private.append(slug)
    manifest_path = os.path.join(folder, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            if not json.load(fh).get("ground_color"):
                no_ground.append(slug)
check("no theme paints the body itself", not painting, painting)
check("no theme defines a private --site-body-bg", not private, private)
check("every template says what its ground is", not no_ground, no_ground)

print()
print("The Background control, through the real route")
print("-" * 70)
with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    bootstrap.clear_generated_password_flag(db, uid)
    db.commit()
    active = db.execute("SELECT id FROM templates WHERE is_active = 1").fetchone()["id"]
with client.session_transaction() as s:
    s["user_id"] = uid
ORIGIN = {"Origin": "http://localhost"}


def page_vars():
    html = client.get("/").get_data(as_text=True)
    return dict(re.findall(r"(--site-[a-z-]+):\s*([^;]+);", html))


def luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


r = client.post(f"/admin/templates/{active}/ground", data={"ground": "#123456"}, headers=ORIGIN)
check("a dark colour is taken", r.status_code in (302, 303), r.status_code)
v = page_vars()
check("and the page is painted with it", v.get("--site-ground") == "#123456", v.get("--site-ground"))
check("with a pale ink worked out for it", v.get("--site-ink") and luminance(v["--site-ink"]) > 0.6, v.get("--site-ink"))
#  A heading in a brand colour has to read too: the brand colour itself
#  while it can, a paler step of it once the ground is dark.
for role in ("primary", "secondary"):
    text = v.get(f"--site-{role}-text")
    check(f"and a {role}-coloured heading is given a shade that reads",
          bool(text) and luminance(text) > 0.4, text)
client.post(f"/admin/templates/{active}/ground", data={"ground": "#fff4dd"}, headers=ORIGIN)
v = page_vars()
check("a pale colour flips the ink dark", v.get("--site-ground") == "#fff4dd"
      and v.get("--site-ink") and luminance(v["--site-ink"]) < 0.3, (v.get("--site-ground"), v.get("--site-ink")))
client.post(f"/admin/templates/{active}/ground", data={"ground": "#8a9a80"}, headers=ORIGIN)
v = page_vars()
check("a mid-tone still gets an ink that reads", v.get("--site-ground") == "#8a9a80"
      and v.get("--site-ink") and abs(luminance(v["--site-ink"]) - luminance("#8a9a80")) > 0.35,
      (v.get("--site-ground"), v.get("--site-ink")))
before = v.get("--site-ground")
client.post(f"/admin/templates/{active}/ground", data={"ground": "not a colour"}, headers=ORIGIN)
check("nonsense is refused and changes nothing", page_vars().get("--site-ground") == before)
client.post(f"/admin/templates/{active}/ground", data={"ground": "default"}, headers=ORIGIN)
with app.app_context():
    row = get_db().execute("SELECT ground_color, ink_color FROM templates WHERE id = ?", (active,)).fetchone()
check("reset puts the template's own back", row["ground_color"] is None and row["ink_color"] is None)
check("and the page still has a ground to paint", bool(page_vars().get("--site-ground")))

print()
print("A zone override on the body still wins")
print("-" * 70)
with app.app_context():
    db = get_db()
    db.execute("UPDATE templates SET zone_style_overrides = ? WHERE id = ?",
               (json.dumps({"body": {"bg": "#abcdef"}}), active))
    db.commit()
v = page_vars()
check("the override is emitted beside the ground", v.get("--site-body-bg") == "#abcdef", v.get("--site-body-bg"))
base = open(os.path.join(app.static_folder, "css", "site-base.css"), encoding="utf-8").read()
check("and site-base reads it before the ground",
      "var(--site-body-bg, var(--site-ground" in base)

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
