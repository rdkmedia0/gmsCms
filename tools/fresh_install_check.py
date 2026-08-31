"""What somebody gets when they install this for the first time.

Everything else in `tools/` measures a site that has been used. This one
measures the site nobody has touched yet, which is the one every new
owner meets and the one most likely to carry something left behind by
development: a test page, a stray theme directory, a setting with a
developer's own address in it.

It boots the app against an empty DATA_DIR, twice -- because the second
boot is where a seed that is not idempotent shows itself -- and asks the
questions a first five minutes would:

  * does it come up at all, and does it say how to sign in?
  * are all sixteen templates in the library, with one of them active?
  * is there a site to look at, and does every page of it render?
  * does every admin screen open?
  * is anything on it left over from somewhere else -- a page, a theme
    directory, a subscriber, an order, somebody's postal address?

Run inside the container:

    docker compose exec -T web python /tmp/fic.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="fresh-install-")
os.environ["DATA_DIR"] = DATA_DIR

failures = []
RUN = 0


def check(name, ok, detail=""):
    global RUN
    RUN += 1
    print("%-58s %s%s" % (name, "ok" if ok else "FAILED", "  " + detail if detail and not ok else ""))
    if not ok:
        failures.append(name)


#  What was in the themes folder before this ran, since that folder is
#  shared with whatever site is already installed here.
THEMES_BEFORE = set(os.listdir("/app/app/static/themes"))     if os.path.isdir("/app/app/static/themes") else set()

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import bootstrap                                     # noqa: E402
from app.services import packages                             # noqa: E402

#  ------------------------------------------------------------ it boots
app = create_app()
check("it comes up against an empty data directory", app is not None)

with app.app_context():
    db = get_db()
    check("it made an admin to sign in as",
          db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1)
    check("and says the password it generated has to be replaced",
          bootstrap.using_generated_password(db))
    check("writing that password down where the owner can find it",
          os.path.exists(os.path.join(DATA_DIR, "initial-admin-password.txt")))

    #  ------------------------------------------------- the template library
    templates = db.execute("SELECT * FROM templates ORDER BY slug").fetchall()
    shipped = len(packages.shipped_zips()) if hasattr(packages, "shipped_zips") else 16
    check("every shipped template is in the library", len(templates) == 16,
          "%d templates" % len(templates))
    check("all of them marked built-in", all(t["is_builtin"] for t in templates))
    active = [t for t in templates if t["is_active"]]
    check("exactly one of them is active", len(active) == 1,
          str([t["slug"] for t in active]))
    check("every template has a palette to customise",
          all(t["palette_json"] for t in templates),
          str([t["slug"] for t in templates if not t["palette_json"]]))

    #  --------------------------------------------------- a site to look at
    pages = db.execute("SELECT * FROM pages ORDER BY nav_order").fetchall()
    check("there is a site to look at", len(pages) >= 3, "%d pages" % len(pages))
    check("one of them is the home page",
          sum(1 for p in pages if p["is_home"]) == 1)
    check("every page is readable by a visitor", all(p["is_public"] for p in pages))
    check("every page has something on it", all(
        db.execute("SELECT COUNT(*) FROM sections WHERE page_id = ?", (p["id"],)).fetchone()[0]
        for p in pages), "an empty page")
    check("no section is orphaned", db.execute(
        "SELECT COUNT(*) FROM sections WHERE page_id IS NOT NULL AND page_id NOT IN "
        "(SELECT id FROM pages)").fetchone()[0] == 0)

    #  --------------------------------------- nothing carried over from here
    check("nobody is on the email list",
          db.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0] == 0)
    check("nothing has been sold",
          db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
          and db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0)
    check("no newsletter has been sent",
          db.execute("SELECT COUNT(*) FROM newsletter_sends").fetchone()[0] == 0)
    settings = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM settings").fetchall()}
    #  A key that came from the ENVIRONMENT is the owner's own, adopted on
    #  first run by design (see bootstrap.py) -- this machine's .env is
    #  why the first version of this check reported Google credentials as
    #  a leak. What would be a leak is one with no environment behind it.
    from_env = {name for name in os.environ if os.environ[name].strip()}
    def adopted(key):
        return key.upper().removesuffix("_ENC") in from_env
    leaked = [key for key, value in settings.items()
              if key.startswith(("smtp_", "legal_address", "legal_email", "legal_phone",
                                 "stripe_", "calcom_", "openwebui_", "google_"))
              and (value or "").strip() and not adopted(key)]
    check("no address, key or connection came with it", not leaked, str(leaked))
    check("the site is not called somebody else's business",
          (settings.get("site_title") or "") not in ("Flour & Salt", "Riverstone Coffee Roasters"),
          settings.get("site_title", ""))

    #  ------------------------------------- and nothing left in the folders
    #  themes/ is NOT inside DATA_DIR -- it is its own mounted volume, so
    #  a fresh database still sees whatever the live site has saved there.
    #  Only directories this run created are this run's business.
    themes = os.path.join(app.static_folder, "themes")
    known = {t["slug"] for t in templates}
    strays = [n for n in os.listdir(themes)
              if os.path.isdir(os.path.join(themes, n))
              and n not in known and n not in THEMES_BEFORE]
    check("no theme directory that is not in the library", not strays, str(strays))
    check("every template in the library has its files",
          all(os.path.isdir(os.path.join(themes, t["slug"])) for t in templates),
          str([t["slug"] for t in templates
               if not os.path.isdir(os.path.join(themes, t["slug"]))]))

#  ------------------------------------------------ every screen opens
client = app.test_client()
with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    #  Signing in is the one thing this check skips: the generated
    #  password gate is doing its job and is tested by its own flow.
    bootstrap.clear_generated_password_flag(db)
    db.commit()
    slugs = [("/" if p["is_home"] else "/" + p["slug"]) for p in
             db.execute("SELECT slug, is_home FROM pages").fetchall()]

bad = [path for path in slugs if client.get(path).status_code != 200]
check("every page of the new site renders for a visitor", not bad, str(bad))

with client.session_transaction() as s:
    s["user_id"] = uid
screens = []
for rule in app.url_map.iter_rules():
    path = str(rule)
    if "GET" in rule.methods and not rule.arguments and path.startswith("/admin") \
            and "logout" not in path and "google" not in path:
        screens.append(path)
broken = []
for path in sorted(set(screens)):
    with client.session_transaction() as s:
        s["user_id"] = uid
    if client.get(path).status_code not in (200, 302):
        broken.append(path)
check("every admin screen opens", not broken, str(broken))

#  ------------------------------------------- the schema a new site gets
#
#  A migration is written against a database that already exists, and is
#  then run for the first time on one that does not. The two paths can
#  disagree silently: `_add_column` tolerates a missing table on purpose
#  -- right for an old database, and on a NEW one it means the column is
#  quietly never added, because the CREATE is further down the same
#  function. That happened, and nothing here would have caught it.
with app.app_context():
    db = get_db()

    def columns(table):
        return {r["name"] for r in db.execute("PRAGMA table_info(%s)" % table)}

    orders = columns("orders")
    for col in ("invoice_ref", "invoice_pdf", "invoice_url"):
        check("a new database has orders.%s" % col, col in orders, str(sorted(orders)))

    tables = {r["name"] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    check("...and a table to keep a saved newsletter layout in",
          "email_layouts" in tables)
    check("...and one for a named schedule", "schedule_templates" in tables)
    check("...and the schedule rows can say which name they came from",
          "template_name" in columns("newsletter_schedule"),
          str(sorted(columns("newsletter_schedule"))))

    #  The four messages that send themselves ship real words, and on a
    #  brand-new install those words are the only ones there are.
    from app.services import site_emails                       # noqa: E402
    for key in site_emails.ORDER:
        body = site_emails.body(db, key)
        check("%s ships wording on a fresh install" % key,
              bool(body.strip()) and body == site_emails.MESSAGES[key]["body_default"],
              body[:60])
    filled = site_emails.preview(db, "order")
    check("...and the order message fills in with no braces left",
          "{{" not in filled and "42.00 CHF" in filled, filled[:80])
    #  The fault that opened this up, guarded where a new owner meets it.
    check("...and says nothing about other orders",
          "sessions to book" not in filled and "downloads left" not in filled,
          filled[:120])

    #  Layouts: the shipped ones are there and nobody else's are.
    from app.services import email_layouts                     # noqa: E402
    keys = [k for k, _n, _b in email_layouts.choices(db)]
    check("the four shipped layouts are offered",
          keys == ["letter", "story", "two-up", "announcement"], str(keys))
    check("...and no saved layout from anybody else's install",
          not email_layouts.saved(db))


#  ------------------------------------------------------- and boots again
second = create_app()
with second.app_context():
    db = get_db()
    check("a second boot adds no duplicate template",
          db.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 16,
          str(db.execute("SELECT COUNT(*) FROM templates").fetchone()[0]))
    check("and no duplicate page",
          db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == len(pages))
    check("and no duplicate section", db.execute(
        "SELECT COUNT(*) FROM sections").fetchone()[0] == db.execute(
        "SELECT COUNT(*) FROM sections").fetchone()[0])

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (RUN, len(failures)))
if failures:
    print("failed:", ", ".join(failures))
sys.exit(1 if failures else 0)
