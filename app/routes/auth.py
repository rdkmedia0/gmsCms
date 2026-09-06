import os
import datetime
import json
import secrets
import urllib.error
import urllib.request
import urllib.parse
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .. import bootstrap
from ..db import get_db
from .. import crypto

bp = Blueprint("auth", __name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def get_google_settings(db):
    """Client ID/secret, Dashboard-configured (encrypted — see app/crypto.py)
    taking priority, with the original GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET
    env vars as a fallback so an existing docker-compose deployment keeps
    working unless/until the admin saves something here instead — same
    shape as assistant.get_ai_settings."""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ('google_client_id', 'google_client_secret_enc')"
    ).fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    client_id = raw.get("google_client_id") or os.environ.get("GOOGLE_CLIENT_ID", "")
    return {
        # Used internally (building the OAuth redirect, the token exchange) —
        # never handed to a template. get_google_settings_display() below is
        # what templates get instead, so a page render can't leak either one.
        "client_id": client_id,
        "client_secret": crypto.decrypt(raw.get("google_client_secret_enc")) or os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "client_id_set": bool(client_id),
        "client_secret_set": bool(raw.get("google_client_secret_enc") or os.environ.get("GOOGLE_CLIENT_SECRET")),
    }


def get_google_settings_display(db):
    """What the settings page is allowed to see: whether each is set, never
    the actual value — client_id included, even though it's not secret in
    the OAuth sense, because it's still only ever meant to be typed once
    and left alone, not re-displayed on every page load."""
    s = get_google_settings(db)
    return {"client_id_set": s["client_id_set"], "client_secret_set": s["client_secret_set"]}


def save_google_settings(db, form):
    # Blank submit on either field = keep whatever's already saved — this
    # page never puts either value back in the browser to begin with, so a
    # blank field can only mean "didn't change this", not "clear it".
    new_client_id = form.get("google_client_id", "").strip()
    if new_client_id:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('google_client_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (new_client_id,),
        )
    new_secret = form.get("google_client_secret", "").strip()
    if new_secret:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('google_client_secret_enc', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (crypto.encrypt(new_secret),),
        )
    db.commit()


def google_oauth_configured(db):
    s = get_google_settings(db)
    return bool(s["client_id"] and s["client_secret"])


#  How long password sign-in stays available after Google has been shown
#  to be unreachable. Long enough to get in and sort something out, short
#  enough that an outage does not quietly leave the door open for a week.
FALLBACK_MINUTES = 60

GOOGLE_PROBE_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _safe_next(target, fallback_endpoint="admin.dashboard"):
    """Where it is safe to send someone after signing in.

    `?next=` is attacker-supplied. Following it anywhere means this site
    will bounce a freshly-signed-in admin to a page of someone else's
    choosing — the classic setup for a convincing phishing page, since
    the victim arrives having genuinely just logged into the real site.

    Only same-site paths are allowed. "//evil.example" is rejected as well
    as "https://evil.example": a protocol-relative URL starts with a
    slash and is still another origin, which is the mistake this check
    usually gets wrong.
    """
    target = (target or "").strip()
    if (target.startswith("/")
            and not target.startswith("//")
            and not target.startswith("/\\")):
        return target
    return url_for(fallback_endpoint)


def password_login_disabled(db):
    """Whether the password form should be refused right now.

    Disabled by the owner, EXCEPT while a Google outage has been
    established — see open_fallback_window. Then the password works
    again, because the alternative is an owner locked out of their own
    site by somebody else's service being down.
    """
    row = db.execute("SELECT value FROM settings WHERE key = 'password_login_disabled'").fetchone()
    if not (row and row["value"] == "1"):
        return False
    return not fallback_open(db)


def fallback_open(db):
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'password_login_fallback_until'"
    ).fetchone()
    if not row or not row["value"]:
        return False
    try:
        return datetime.datetime.utcnow() < datetime.datetime.fromisoformat(row["value"])
    except ValueError:
        return False


def open_fallback_window(db, reason):
    """Lets the password back in for a while, because Google could not be
    reached. Returns when it closes.

    Only ever called after a request from THIS SERVER to Google has
    failed. That distinction is the whole security of it: a stranger can
    make Google reject them as easily as they like — wrong account,
    cancelled consent, a made-up code — and none of that opens anything,
    because none of it says Google is down. Only Google failing to answer
    us does.
    """
    until = datetime.datetime.utcnow() + datetime.timedelta(minutes=FALLBACK_MINUTES)
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('password_login_fallback_until', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (until.isoformat(),),
    )
    db.commit()
    current_app.logger.warning(
        "Google sign-in unreachable (%s) - password sign-in re-opened until %s UTC",
        reason, until.strftime("%H:%M"),
    )
    return until


def google_service_unreachable():
    """(unreachable, detail). Asks Google directly, from this server.

    A configuration document, not a login: it answers "is Google
    answering?" without involving anyone's account, so the check cannot be
    steered by whoever is asking.
    """
    try:
        req = urllib.request.Request(GOOGLE_PROBE_URL, headers={"User-Agent": "cms-health-check"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status >= 500:
                return True, f"Google returned {resp.status}"
        return False, "Google is responding normally"
    except urllib.error.HTTPError as e:
        #  4xx from a public document still means Google answered.
        return (e.code >= 500), f"Google returned {e.code}"
    except Exception as e:  # noqa: BLE001 - any failure to reach it counts
        return True, f"{type(e).__name__}"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


LOGIN_ATTEMPT_LIMIT = 8
LOGIN_ATTEMPT_WINDOW_MINUTES = 15


def _client_ip():
    # ProxyFix (x_for=1 in create_app) already rewrites this from
    # X-Forwarded-For when behind nginx, so this is the real client
    # address either way, not the proxy's.
    return request.remote_addr or "unknown"


def _record_failed_login(db, ip):
    db.execute("INSERT INTO login_attempts (ip, kind) VALUES (?, 'admin')", (ip,))
    # Opportunistic cleanup — cheap, and keeps the table from growing
    # forever on a public-facing login form without needing a cron job.
    db.execute("DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-1 hour')")
    db.commit()


def _login_rate_limited(db, ip):
    row = db.execute(
        "SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND kind = 'admin' "
        "AND attempted_at > datetime('now', ?)",
        (ip, f"-{LOGIN_ATTEMPT_WINDOW_MINUTES} minutes"),
    ).fetchone()
    return row["n"] >= LOGIN_ATTEMPT_LIMIT


@bp.route("/admin/login", methods=["GET", "POST"])
def login():
    db = get_db()
    disabled = password_login_disabled(db)
    if request.method == "POST":
        # Checked even though the form is hidden once disabled — a direct
        # POST (bypassing the UI) must not still work.
        if disabled:
            flash("Username/password sign-in is disabled. Use Google Sign-In.", "error")
            return render_template(
                "admin/login.html", google_oauth_configured=google_oauth_configured(db), password_login_disabled=True
            )
        ip = _client_ip()
        if _login_rate_limited(db, ip):
            flash(f"Too many failed attempts. Please wait {LOGIN_ATTEMPT_WINDOW_MINUTES} minutes and try again.", "error")
            return render_template(
                "admin/login.html", google_oauth_configured=google_oauth_configured(db), password_login_disabled=False
            ), 429
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            if bootstrap.using_generated_password(db, user["id"]):
                #  Straight to the one screen that fixes it. The password
                #  they just used is sitting in a file in the data volume
                #  and was printed to the container log, so it should stop
                #  being the password as soon as someone is in a position
                #  to change it.
                flash("You're signed in with the password this site generated for you. "
                      "Set your own now — the generated one is written in plain text in "
                      "the container log and in data/initial-admin-password.txt.", "warning")
                return redirect(url_for("auth.account"))
            return redirect(_safe_next(request.args.get("next")))
        _record_failed_login(db, ip)
        flash("Wrong username or password. Please try again.", "error")
    return render_template(
        "admin/login.html",
        google_oauth_configured=google_oauth_configured(db),
        password_login_disabled=disabled,
        fallback_open=fallback_open(db),
    )


@bp.route("/admin/login/google")
def google_login():
    db = get_db()
    google_settings = get_google_settings(db)
    if not (google_settings["client_id"] and google_settings["client_secret"]):
        flash("Google sign-in isn't configured on this server.", "error")
        return redirect(url_for("auth.login"))
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": google_settings["client_id"],
        "redirect_uri": url_for("auth.google_callback", _external=True),
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@bp.route("/admin/login/google/callback")
def google_callback():
    db = get_db()
    google_settings = get_google_settings(db)
    if not (google_settings["client_id"] and google_settings["client_secret"]):
        flash("Google sign-in isn't configured on this server.", "error")
        return redirect(url_for("auth.login"))

    error = request.args.get("error")
    if error:
        flash("Google sign-in was cancelled.", "error")
        return redirect(url_for("auth.login"))

    state = request.args.get("state")
    if not state or state != session.pop("oauth_state", None):
        flash("Sign-in request expired — please try again.", "error")
        return redirect(url_for("auth.login"))

    code = request.args.get("code")
    if not code:
        flash("Google didn't return a sign-in code — please try again.", "error")
        return redirect(url_for("auth.login"))

    token_body = urllib.parse.urlencode({
        "client_id": google_settings["client_id"],
        "client_secret": google_settings["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": url_for("auth.google_callback", _external=True),
    }).encode()

    try:
        req = urllib.request.Request(GOOGLE_TOKEN_URL, data=token_body, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            token_data = json.loads(resp.read().decode())

        access_token = token_data["access_token"]
        info_req = urllib.request.Request(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        with urllib.request.urlopen(info_req, timeout=8) as resp:
            userinfo = json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001 - classified below, not ignored
        #  Two very different failures arrive here and must not be treated
        #  alike. Google being unreachable, or answering with a 5xx, or
        #  rejecting OUR client credentials, means Google cannot be used
        #  by anyone right now — that reopens password sign-in. A bad or
        #  reused authorisation code (invalid_grant) means someone's
        #  attempt failed, which anyone can cause on purpose, so it opens
        #  nothing.
        detail = ""
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail = e.read().decode(errors="ignore")[:200]
            except Exception:  # noqa: BLE001
                detail = ""
        attacker_inducible = "invalid_grant" in detail or "redirect_uri_mismatch" in detail
        if not attacker_inducible:
            unreachable, reason = google_service_unreachable()
            if unreachable or "invalid_client" in detail:
                open_fallback_window(db, reason if unreachable else "Google rejected this site's client credentials")
                flash("Google sign-in isn't working just now, so password sign-in has been "
                      "switched back on temporarily. Sign in with your password below.", "warning")
                return redirect(url_for("auth.login"))
        flash("Couldn't reach Google to finish signing in — please try again.", "error")
        return redirect(url_for("auth.login"))

    email = (userinfo.get("email") or "").lower().strip()
    if not email or not userinfo.get("email_verified"):
        flash("That Google account isn't authorized to manage this site.", "error")
        return redirect(url_for("auth.login"))

    # Any admin whose own google_email matches — supports multiple admins,
    # each with their own Google account (see admin.py's Manage Admins
    # page). ADMIN_GOOGLE_EMAIL is only a fallback for a user id=1 that's
    # never had a google_email set at all (pre-multi-admin deployments
    # that haven't been migrated — normally handled automatically by
    # db.py's backfill, this only matters if that env var changed since).
    user = db.execute("SELECT * FROM users WHERE google_email = ?", (email,)).fetchone()
    if not user:
        legacy_email = os.environ.get("ADMIN_GOOGLE_EMAIL", "").lower().strip()
        if legacy_email and email == legacy_email:
            user = db.execute("SELECT * FROM users WHERE id = 1 AND google_email IS NULL").fetchone()
    if not user:
        flash("That Google account isn't authorized to manage this site.", "error")
        return redirect(url_for("auth.login"))

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    flash("Signed in with Google!", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/admin/view-mode/<mode>")
@login_required
def set_view_mode(mode):
    if mode in ("editing", "viewing"):
        session["view_mode"] = mode
    next_url = request.args.get("next")
    if next_url:
        return redirect(_safe_next(next_url))
    return redirect(url_for("public.home"))


@bp.route("/admin/preview-view/<view>")
@login_required
def set_preview_view(view):
    #  The screen size the admin is looking at, kept in the session so it
    #  survives the editing<->viewing switch and page-to-page navigation:
    #  pick Mobile, then switch to Viewing, and the page is shown at that
    #  size (see the view selector in public/page.html). Desktop is the
    #  base; mobile carries its own per-view edits on top of it.
    if view in ("desktop", "laptop", "tablet", "mobile"):
        session["preview_view"] = view
    next_url = request.args.get("next")
    if next_url:
        return redirect(_safe_next(next_url))
    return redirect(url_for("public.home"))


@bp.route("/admin/login/google-check", methods=["POST"])
def google_check():
    """"Google isn't working — let me in another way", verified rather than
    believed.

    If Google is fully down, nobody ever comes back to the callback: the
    browser is stuck at Google's own page, so the app never sees a failure
    to classify. This is the way an owner reports that from the outside —
    and it does not take their word for it. The app asks Google itself,
    and only opens password sign-in if Google really does not answer.
    Anyone can press this button; only Google being down changes anything.
    """
    db = get_db()
    if not password_login_disabled(db) and not fallback_open(db):
        return redirect(url_for("auth.login"))
    unreachable, reason = google_service_unreachable()
    if unreachable:
        open_fallback_window(db, reason)
        flash(f"Confirmed — Google isn't responding ({reason}). Password sign-in is available "
              f"for the next {FALLBACK_MINUTES} minutes.", "warning")
    else:
        flash("Google is responding normally, so password sign-in stays off. If signing in "
              "still fails, the problem is with the account rather than with Google.", "error")
    return redirect(url_for("auth.login"))


@bp.route("/admin/account", methods=["GET", "POST"])
@login_required
def account():
    db = get_db()
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), user["id"]),
            )
            #  Whatever it is now, it is no longer the one this app
            #  generated, so the reminder stops.
            bootstrap.clear_generated_password_flag(db, user["id"])
            db.commit()
            flash("Password updated!", "success")
    return render_template(
        "admin/account.html",
        using_generated_password=bootstrap.using_generated_password(db, session["user_id"]),
        fallback_open=fallback_open(db),
        password_login_env=bootstrap.password_login_env(),
        google_oauth_configured=google_oauth_configured(db),
        password_login_disabled=password_login_disabled(db),
        admin_users=db.execute("SELECT * FROM users ORDER BY id").fetchall(),
        me=db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone(),
        google_settings=get_google_settings_display(db),
    )


@bp.route("/admin/account/google-address", methods=["POST"])
@login_required
def set_own_google_address():
    """Links the signed-in admin's own account to their Google address.

    Without this the only way to attach one was the ADMIN_GOOGLE_EMAIL
    environment variable, read once when the very first admin was
    created — so an owner who set the site up entirely through these
    screens could configure the Google client, see a working Sign in with
    Google button, and still be refused by it, because no account claimed
    their address. The alternative on offer was creating a second admin
    just to own the email, which is a strange thing to have to do to
    yourself.
    """
    db = get_db()
    email = (request.form.get("google_email") or "").strip().lower()
    user_id = session["user_id"]

    if not email:
        #  Unlinking while the password is switched off would leave no way
        #  in at all — the same lockout the disable toggle already guards.
        if password_login_disabled(db):
            flash("Turn password sign-in back on before unlinking your Google account, "
                  "or you'd have no way to sign in.", "error")
            return redirect(url_for("auth.account"))
        db.execute("UPDATE users SET google_email = NULL WHERE id = ?", (user_id,))
        db.commit()
        flash("Google account unlinked.", "success")
        return redirect(url_for("auth.account"))

    if "@" not in email:
        flash("That doesn't look like an email address.", "error")
        return redirect(url_for("auth.account"))
    taken = db.execute(
        "SELECT username FROM users WHERE google_email = ? AND id != ?", (email, user_id)
    ).fetchone()
    if taken:
        flash(f'"{email}" is already linked to the admin "{taken["username"]}".', "error")
        return redirect(url_for("auth.account"))

    db.execute("UPDATE users SET google_email = ? WHERE id = ?", (email, user_id))
    db.commit()
    if google_oauth_configured(db):
        flash(f"Linked. You can now sign in with {email}.", "success")
    else:
        flash(f"Linked {email}. Add your Google Client ID and Secret below to switch it on.", "success")
    return redirect(url_for("auth.account"))


@bp.route("/admin/account/password-login", methods=["POST"])
@login_required
def toggle_password_login():
    db = get_db()
    disable = request.form.get("disable") == "1"
    if disable:
        #  Three things have to be true before the password stops being a
        #  way in, and each one is a different way of being locked out.
        me = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if bootstrap.using_generated_password(db, me["id"] if me else None):
            flash("Change your password first. Turning this off while the generated password "
                  "is still in place would leave that password sitting in the container log "
                  "and the data volume as the only thing standing between anyone and this site.",
                  "error")
            return redirect(url_for("auth.account"))
        if not google_oauth_configured(db):
            flash("Set up Google Sign-In below before disabling password sign-in.", "error")
            return redirect(url_for("auth.account"))
        if not (me and me["google_email"]):
            flash("Link your own Google address first — otherwise Google sign-in works for "
                  "this site but not for you, and you would have no way in.", "error")
            return redirect(url_for("auth.account"))
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('password_login_disabled', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("1" if disable else "0",),
    )
    #  Any open outage window ends with a deliberate decision either way.
    db.execute("DELETE FROM settings WHERE key = 'password_login_fallback_until'")
    db.commit()
    flash("Password sign-in disabled — use Google Sign-In from now on." if disable else "Password sign-in re-enabled.", "success")
    return redirect(url_for("auth.account"))
