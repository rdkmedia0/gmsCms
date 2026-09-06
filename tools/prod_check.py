"""Prove the production pass, against a throwaway install.

Each thing is checked by making it happen, not by reading the setting
that ought to cause it: a cookie is asked for its Secure flag over both
schemes, the password file is looked for on disk after a real password
change, and two connections are made to fight over the database.
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, "/app")
DATA_DIR = tempfile.mkdtemp(prefix="prod-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                      # noqa: E402
from app.db import get_db, DB_PATH                              # noqa: E402
from app import bootstrap                                       # noqa: E402
from werkzeug.security import generate_password_hash            # noqa: E402

app = create_app()

#  Both probes are registered here, before anything is asked of the app:
#  Flask refuses a new route once it has served its first request, and the
#  first section below serves several.
from flask import request as flask_request                       # noqa: E402
from app import TrustedProxyFix, FORWARDED_HEADERS, SECRET_KEY_PATH  # noqa: E402


@app.route("/__scheme_probe")
def _scheme_probe():
    return "%s|%s|%s" % (flask_request.scheme, flask_request.host,
                         "forwarded" if any(
                             h in flask_request.environ for h in FORWARDED_HEADERS) else "clean")


from flask import session as flask_session                       # noqa: E402


@app.route("/__cookie_probe")
def _cookie_probe():
    flask_session["probe"] = "1"
    return "x"


passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print("  %-56s %s%s" % (what, "ok" if ok else "FAILED",
                            ("   " + detail) if detail and not ok else ""))


print()
print("The database, with two workers on it")
print("-" * 60)
with app.app_context():
    db = get_db()
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    busy = db.execute("PRAGMA busy_timeout").fetchone()[0]
    sync = db.execute("PRAGMA synchronous").fetchone()[0]
    check("readers do not block on a writer (WAL)", mode.lower() == "wal", mode)
    check("a contended write waits instead of failing", busy >= 30000, str(busy))
    check("and still syncs at checkpoints", sync == 1, str(sync))

#  A real contention: hold a write transaction open on one connection and
#  read from another, which is exactly the admin-saves-while-visitor-reads
#  case that used to 500.
import sqlite3                                                  # noqa: E402

held = threading.Event()
done = threading.Event()


def writer():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO settings (key, value) VALUES ('prod_check', '1') "
                 "ON CONFLICT(key) DO UPDATE SET value = '1'")
    held.set()
    time.sleep(1.5)          # the write is open for a good long moment
    conn.commit()
    conn.close()
    done.set()


thread = threading.Thread(target=writer)
thread.start()
held.wait(5)
started = time.time()
reader = sqlite3.connect(DB_PATH, timeout=30)
rows = reader.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
took = time.time() - started
reader.close()
thread.join()
check("a visitor reads straight through an open write", took < 0.5,
      "took %.2fs" % took)
check("and gets real rows while it is open", rows > 0)

print()
print("Ordering, now that writes are fast")
print("-" * 60)
#  Three writes as fast as the machine can make them -- which is what
#  "the same millisecond" means in practice, and what broke `send the
#  latest section` the moment WAL made writes quick.
with app.app_context():
    db = get_db()
    page = db.execute("SELECT id FROM pages LIMIT 1").fetchone()["id"]
    ids = []
    for n in range(3):
        cur = db.execute("INSERT INTO sections (page_id, type, title, content, position) "
                         "VALUES (?, 'text', ?, '<p>x</p>', ?)", (page, "S%d" % n, 500 + n))
        ids.append(cur.lastrowid)
    db.commit()
    #  Touch the FIRST one last: the newest change is now the oldest row,
    #  which is precisely the case a row-id tie-break gets backwards.
    db.execute("UPDATE sections SET title = 'S0 again' WHERE id = ?", (ids[0],))
    db.commit()
    rows = db.execute("SELECT id, title, updated_at, changed_seq FROM sections "
                      "WHERE id IN (%s) ORDER BY id" % ",".join("?" * len(ids)), ids).fetchall()
    stamps = {r["updated_at"] for r in rows}
    seqs = [r["changed_seq"] for r in rows]
    check("the clock does tie at this speed (that is the point)", len(stamps) < len(rows),
          "%d distinct stamps for %d rows" % (len(stamps), len(rows)))
    check("the counter never ties", len(set(seqs)) == len(seqs), str(seqs))
    from app.services import newsletter                                # noqa: E402
    picked, _what = newsletter.sections_for(rows, "latest")
    check("'the latest' is the one changed last, not the one added last",
          picked and picked[0]["id"] == ids[0], "picked id %s, wanted %s" % (
              picked[0]["id"] if picked else None, ids[0]))
    for section_id in ids:
        db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    db.commit()

print()
print("Who is allowed to say what the request looked like")
print("-" * 60)
#  The same spoof from two different peers. A proxy on the docker network
#  or the LAN reaches this from a private address; a visitor arriving at
#  a directly-exposed container does not -- and their X-Forwarded-Proto is
#  a claim about themselves.
SPOOF = {"HTTP_X_FORWARDED_PROTO": "https", "HTTP_X_FORWARDED_HOST": "evil.example"}


def probe(remote):
    environ = dict(SPOOF, REMOTE_ADDR=remote)
    return app.test_client().get("/__scheme_probe",
                                 environ_overrides=environ).get_data(as_text=True).split("|")


scheme, host, headers = probe("10.1.2.3")
check("a proxy on the LAN is believed", scheme == "https", scheme)
check("including about the host it was asked for", host == "evil.example", host)

scheme, host, headers = probe("93.184.216.34")
check("a stranger from the internet is not", scheme == "http", scheme)
check("and cannot rewrite the host either", host != "evil.example", host)
check("the headers are removed, not merely ignored", headers == "clean", headers)

check("TRUST_PROXY=never believes nobody",
      not TrustedProxyFix(app.wsgi_app, "never").trusts({"REMOTE_ADDR": "10.1.2.3"}))
check("TRUST_PROXY=always believes anybody",
      TrustedProxyFix(app.wsgi_app, "always").trusts({"REMOTE_ADDR": "93.184.216.34"}))
check("a peer with no address at all is not believed",
      not TrustedProxyFix(app.wsgi_app, "auto").trusts({}))
check("and neither is a garbled one",
      not TrustedProxyFix(app.wsgi_app, "auto").trusts({"REMOTE_ADDR": "not-an-address"}))

print()
print("The session cookie")
print("-" * 60)
with app.app_context():
    uid = get_db().execute("SELECT id FROM users LIMIT 1").fetchone()["id"]


#  A cookie is only WRITTEN on a request that changes the session, so the
#  probe has to change it -- asking a page that happens not to leaves no
#  Set-Cookie at all and every assertion about it passes vacuously.
def cookie_for(**environ):
    response = app.test_client().get("/__cookie_probe", environ_overrides=environ)
    return "; ".join(response.headers.getlist("Set-Cookie")) or ""


plain = cookie_for()
secure = cookie_for(**{"HTTP_X_FORWARDED_PROTO": "https"})
check("not marked Secure over plain http (local admin still works)",
      "Secure" not in plain, plain[:60])
check("marked Secure the moment a request arrives over https",
      "Secure" in secure, secure[:60] or "(no cookie set)")
check("HttpOnly either way", "HttpOnly" in (plain or secure))

print()
print("Headers")
print("-" * 60)
plain_headers = app.test_client().get("/healthz").headers
https_headers = app.test_client().get(
    "/healthz", environ_overrides={"HTTP_X_FORWARDED_PROTO": "https"}).headers
check("no HSTS on a plain-http site (it would strand it)",
      "Strict-Transport-Security" not in plain_headers)
check("HSTS once it is served over https",
      https_headers.get("Strict-Transport-Security", "").startswith("max-age="))
check("and without includeSubDomains or preload",
      "includeSubDomains" not in https_headers.get("Strict-Transport-Security", ""))
#  form-action is enforced across a form's whole redirect chain, so
#  'self' alone refuses the 303 that hands a buyer to Stripe -- in a
#  browser only. Every command-line check passes while nobody can pay.
_csp = https_headers.get("Content-Security-Policy", "")
_form_action = next((d.strip() for d in _csp.split(";") if d.strip().startswith("form-action")), "")
check("checkout may reach Stripe (form-action covers redirects)",
      "checkout.stripe.com" in _form_action, _form_action or "no form-action set")

#  The site frames its own pages -- that is what the responsive preview
#  in the editor IS -- and a page that refuses every framer refuses
#  itself. It came up as a broken document at every width. 'self' still
#  refuses every OTHER origin, which is the clickjacking protection the
#  rule exists for, so nothing is given away by allowing it.
_frame_ancestors = next((d.strip() for d in _csp.split(";")
                         if d.strip().startswith("frame-ancestors")), "")
check("the site may frame its own pages (the preview)",
      "'self'" in _frame_ancestors, _frame_ancestors or "no frame-ancestors set")
check("nobody else may frame them",
      "*" not in _frame_ancestors and "http" not in _frame_ancestors,
      _frame_ancestors)
#  The older header has to AGREE: a browser reading both applies the
#  stricter, so DENY beside frame-ancestors 'self' would still block it.
_xfo = https_headers.get("X-Frame-Options", "")
check("the older header says the same thing", _xfo.upper() == "SAMEORIGIN",
      _xfo or "not set")
#  frame-ancestors is only half of it: that says who may frame US, and
#  frame-src says what WE may frame. The preview needs both to name the
#  site itself. It said `https:` alone, which happens to match this
#  origin over https and matches nothing over http -- so the preview was
#  empty on every install without a certificate, for a reason no part of
#  the page could report.
_frame_src = next((d.strip() for d in _csp.split(";")
                   if d.strip().startswith("frame-src")), "")
check("the site may frame its own pages over either scheme",
      "'self'" in _frame_src, _frame_src or "no frame-src set")
check("and forms still may not post anywhere else",
      "*" not in _form_action and "https:" not in _form_action.replace("https://", ""),
      _form_action)
check("the health answer is not cached", https_headers.get("Cache-Control") == "no-store")
check("and says nothing about the site",
      app.test_client().get("/healthz").get_data(as_text=True).strip() == "ok")

print()
print("The generated password")
print("-" * 60)
check("it was written down for the owner", os.path.exists(bootstrap.PASSWORD_FILE))
with app.app_context():
    db = get_db()
    check("and every screen says it is still in use", bootstrap.using_generated_password(db, uid))
    #  What the Account screen does when somebody sets their own.
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash("a real password"), uid))
    bootstrap.clear_generated_password_flag(db, uid)
    db.commit()
    check("changing it stops the reminder", not bootstrap.using_generated_password(db, uid))
check("and takes the plaintext file with it", not os.path.exists(bootstrap.PASSWORD_FILE))

print()
print("Resetting it from the server")
print("-" * 60)
with open(SECRET_KEY_PATH, encoding="utf-8") as _fh:
    old_secret = _fh.read()
with app.app_context():
    db = get_db()
    ok, lines = bootstrap.reset_admin_password(db, app, "no-such-admin")
    check("an unknown name is refused and the real ones are listed",
          not ok and "'admin'" in " ".join(lines), " ".join(lines))
    db.execute("INSERT INTO settings (key, value) VALUES ('password_login_disabled', '1') "
               "ON CONFLICT(key) DO UPDATE SET value = '1'")
    db.commit()
    ok, lines = bootstrap.reset_admin_password(db, app, None)
    check("with one admin the name may be left out", ok, " ".join(lines))
    check("the one-use password was written down again", os.path.exists(bootstrap.PASSWORD_FILE))
    check("and that admin is back on a generated password", bootstrap.using_generated_password(db, uid))
    check("password sign-in was switched back on",
          db.execute("SELECT value FROM settings WHERE key = 'password_login_disabled'").fetchone()["value"] == "0")
    with open(SECRET_KEY_PATH, encoding="utf-8") as _fh:
        check("the session key was rotated, so every session ends on restart", _fh.read() != old_secret)
    check("and the reset is in the Activity log",
          db.execute("SELECT 1 FROM admin_notes WHERE message LIKE '%reset from the server%'").fetchone() is not None)
    #  The flag names ONE admin. A colleague is not marched to the Account
    #  screen for a password that was never theirs, and changing their own
    #  must not delete the one-use password out from under the admin it
    #  was made for.
    other = db.execute("INSERT INTO users (username, password_hash) VALUES ('second', ?)",
                       (generate_password_hash("theirs"),)).lastrowid
    check("another admin is not told to change theirs", not bootstrap.using_generated_password(db, other))
    bootstrap.clear_generated_password_flag(db, other)
    check("and cannot clear it for them", bootstrap.using_generated_password(db, uid)
          and os.path.exists(bootstrap.PASSWORD_FILE))
    ok, lines = bootstrap.reset_admin_password(db, app, None)
    check("with two admins the name is required", not ok and "'second'" in " ".join(lines))
    db.execute("DELETE FROM users WHERE id = ?", (other,))
    bootstrap.clear_generated_password_flag(db, uid)
    db.commit()

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
