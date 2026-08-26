"""
First-boot setup for a deployment that has no shell and no .env file.

This ships as a Docker image, so the only thing a new owner can hand it is
environment variables in their compose file. Everything here reads those
ONCE, at first boot, writes the result into the database — encrypted, for
anything secret — and then gets out of the way. The admin UI is the
authority from that moment on.

That is deliberate, and it is the answer to "why not just read the env var
every time?". An API key living permanently in a compose file is a
plaintext secret in a file people copy, back up, and paste into forums
when asking for help; it is also a key that can only be rotated by editing
YAML and recreating a container, when rotating a Stripe key should be
pasting a new one into a form. Adopting it once gives a declarative first
run without either of those costs. Change a variable later and it is
ignored — by design, so that a stale value in a compose file cannot
silently override what the owner has since set in the UI.
"""
import os
import secrets

from werkzeug.security import generate_password_hash

from .db import get_db, DATA_DIR
from . import crypto

#  env var -> (provider, field) in services/integrations.PROVIDERS
PROVIDER_ENV = {
    "STRIPE_SECRET_KEY": ("stripe", "secret_key"),
    "STRIPE_WEBHOOK_SECRET": ("stripe", "webhook_secret"),
    "CALCOM_API_KEY": ("calcom", "api_key"),
}

#  env var -> plain settings key. Secrets among these are marked below.
SETTING_ENV = {
    "GOOGLE_CLIENT_ID": ("google_client_id", False),
    "GOOGLE_CLIENT_SECRET": ("google_client_secret_enc", True),
    "SMTP_HOST": ("smtp_host", False),
    "SMTP_PORT": ("smtp_port", False),
    "SMTP_USERNAME": ("smtp_username", False),
    "SMTP_PASSWORD": ("smtp_password", False),
    "SMTP_FROM_EMAIL": ("from_email", False),
    "CONTACT_TO_EMAIL": ("to_email", False),
    "SITE_PUBLIC_URL": ("site_public_url", False),
}

PASSWORD_FILE = os.path.join(DATA_DIR, "initial-admin-password.txt")


def _missing(db, key):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return not (row and (row["value"] or "").strip())


def _write(db, key, value, secret=False):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, crypto.encrypt(value) if secret else value),
    )


def adopt_environment(app):
    """Takes anything supplied by environment that isn't already set."""
    with app.app_context():
        db = get_db()
        adopted = []

        for env_name, (provider, field) in PROVIDER_ENV.items():
            value = (os.environ.get(env_name) or "").strip()
            key = f"integration_{provider}_{field}"
            if value and _missing(db, key):
                _write(db, key, value, secret=True)
                adopted.append(env_name)

        for env_name, (key, is_secret) in SETTING_ENV.items():
            value = (os.environ.get(env_name) or "").strip()
            if value and _missing(db, key):
                _write(db, key, value, secret=is_secret)
                adopted.append(env_name)

        db.commit()
        if adopted:
            #  Names only. Never the values — this goes to the container
            #  log, which is the one place a secret must not end up.
            app.logger.info("Adopted settings from environment: %s", ", ".join(sorted(adopted)))
        return adopted


def initial_admin_password():
    """The password to seed the admin with, and whether it was generated.

    A fixed default ("changeme123") on an image anyone can pull is not a
    default, it is a published password: every install that has not
    changed it yet shares it. A generated one is unique per install and
    useless to anyone who cannot read that install's own logs or volume.
    """
    supplied = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if supplied:
        return supplied, False
    return secrets.token_urlsafe(12), True


def announce_admin_password(app, password, generated, username):
    """Tells the owner what their password is, twice, because a container
    log scrolls away and a file does not.

    It is a one-use credential by design: the first sign-in with it goes
    to the account screen and nothing else opens until it has been
    replaced, so this file stops being a way in as soon as the owner has
    used it once. That is why it can be written down at all.

    Never shown in the admin UI: by the time anyone can see that screen
    they are already signed in, and a password on screen is one shoulder
    away from being someone else's.
    """
    if not generated:
        return
    state = (
        "  Change it under Account after signing in — you will be made to before\n"
        "  anything else opens — then delete this file.\n"
    )
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PASSWORD_FILE, "w", encoding="utf-8") as handle:
            handle.write(
                f"Sign in at /admin with:\n\n  username: {username}\n  password: {password}\n\n  {state}"
            )
    except OSError as e:  # noqa: BLE001 - the log line below still gets there
        app.logger.warning("Could not write %s: %s", PASSWORD_FILE, e)
    app.logger.warning(
        "\n" + "=" * 62 +
        f"\n  FIRST RUN: sign in at /admin as '{username}' with password:\n\n    {password}\n\n"
        f"  Also saved to {PASSWORD_FILE}\n  {state}" + "=" * 62
    )


#  Set while the admin is still using the password this app generated for
#  them, so every screen can say so until they change it.
GENERATED_FLAG = "admin_password_is_generated"


def seed_admin(db, app):
    """Creates the one admin, if there is none yet. Returns True if made.

    The image runs more than one worker, and on a first boot they all
    start with an empty database, so they all get here and each one
    generates a password of its own. Exactly one of those passwords ends
    up being the admin's: the row is written once and the UNIQUE username
    turns every later attempt into a no-op.

    Which is why the INSERT decides who announces, not the SELECT above.
    A worker that read "no users yet" a moment before another worker
    wrote one has a password that opens nothing, and announcing it
    overwrites the file and the log of the worker whose password actually
    works — leaving the owner locked out of a fresh install with the
    printed password in their hand. rowcount is the one answer that comes
    after the write instead of before it.
    """
    if db.execute("SELECT id FROM users LIMIT 1").fetchone():
        return False
    email = (os.environ.get("ADMIN_GOOGLE_EMAIL") or "").strip().lower() or None
    username = (os.environ.get("ADMIN_USERNAME") or "").strip() or "admin"
    password, generated = initial_admin_password()
    made = db.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, google_email) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), email),
    ).rowcount
    if not made:
        return False
    if generated:
        _write(db, GENERATED_FLAG, "1")
    announce_admin_password(app, password, generated, username)
    return True


def using_generated_password(db):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (GENERATED_FLAG,)).fetchone()
    return bool(row and row["value"] == "1")


def clear_generated_password_flag(db):
    """The generated password is no longer the password -- so stop saying
    it is, and stop keeping it.

    The file was always meant to be deleted by the owner ("then delete
    this file"), which means it survives on every install whose owner did
    not get round to it: a plaintext credential sitting in the data
    volume, in every filesystem backup of it, long after it stopped being
    needed. It is not web-reachable -- data/ is outside both served
    static directories -- but "not reachable today" is a weak thing to be
    relying on. The moment the password changes there is nothing in it
    worth keeping, so this removes it rather than asking again.
    """
    db.execute("DELETE FROM settings WHERE key = ?", (GENERATED_FLAG,))
    try:
        os.remove(PASSWORD_FILE)
    except OSError:
        #  Already gone (the usual case, once an owner has followed the
        #  instruction), or not ours to delete. Neither is worth an error
        #  on a password change that otherwise succeeded.
        pass


TRUE_WORDS = {"1", "true", "yes", "on", "enabled"}
FALSE_WORDS = {"0", "false", "no", "off", "disabled"}


def password_login_env():
    """True / False / None from PASSWORD_LOGIN — None meaning "not my
    call", which is the default and leaves it to the admin screens."""
    value = (os.environ.get("PASSWORD_LOGIN") or "").strip().lower()
    if value in TRUE_WORDS:
        return True
    if value in FALSE_WORDS:
        return False
    return None


def apply_password_login_policy(db, app=None):
    """Applies PASSWORD_LOGIN from the compose file, if it says anything.

    Three ways username sign-in can be available, and this is one of them:
    switched on in the admin screens (the default), switched on here, or —
    when it is off — switched back on by the app itself for as long as
    Google cannot be reached (see routes/auth.py).

    Setting it applies on every boot, deliberately: an override that the
    admin screens could quietly outvote would be worse than no override,
    because the compose file would then describe a state the site is not
    in.

    Turning it OFF is refused unless Google can actually take over —
    configured client, and an admin who has linked their own address.
    Anything else is a locked-out owner on the next restart, which is not
    a thing a config file should be able to do by accident.
    """
    wanted = password_login_env()
    if wanted is None:
        return None
    current_off = (db.execute(
        "SELECT value FROM settings WHERE key = 'password_login_disabled'"
    ).fetchone() or {"value": "0"})["value"] == "1"

    if wanted:
        db.execute("DELETE FROM settings WHERE key = 'password_login_fallback_until'")
        _write(db, "password_login_disabled", "0")
        return "on" if current_off else "on-already"

    google_ready = (
        not _missing(db, "google_client_id")
        and not _missing(db, "google_client_secret_enc")
        and db.execute(
            "SELECT 1 FROM users WHERE google_email IS NOT NULL AND google_email != ''"
        ).fetchone()
    )
    if not google_ready:
        return "refused"
    _write(db, "password_login_disabled", "1")
    return "off" if not current_off else "off-already"


def tighten_permissions(app):
    """Makes the database and keys readable only by the account running
    this app.

    Done here rather than in the entrypoint because the entrypoint runs as
    root, and root cannot change the mode of a file it does not own
    without CAP_FOWNER — a capability deliberately dropped in the compose
    file. This process IS the owner, so it can simply do it, and no
    capability has to be handed back to get it.
    """
    import stat as stat_module
    from .db import DATA_DIR as data_dir
    for name in ("cms.db", ".encryption_key", ".secret_key"):
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            continue
        try:
            mode = os.stat(path).st_mode
            if mode & (stat_module.S_IRGRP | stat_module.S_IROTH):
                os.chmod(path, stat_module.S_IRUSR | stat_module.S_IWUSR)
        except OSError as e:  # noqa: BLE001 - a bind mount may refuse; not fatal
            app.logger.debug("Could not tighten %s: %s", path, e)


def check_storage(app):
    """Warns when the things that must persist are not persisting.

    Two failures this catches, both of which are otherwise silent:

    A lost encryption key. The stored API keys are still there, still
    encrypted, and still unreadable — `decrypt` returns None for a token
    from a different key, which every caller correctly treats as "not
    configured". So the whole site reports Stripe and Cal.com as
    disconnected, the keys look absent in the admin screens, and nothing
    anywhere says why. That happens the first time a container is
    recreated without /app/data being a real volume.

    An unwritable data directory, which fails later and further away —
    at the first upload or the first order.

    Returns a list of messages; also logged, because on a Docker install
    the log is the only thing anyone reads before the site is even up.
    """
    from .db import DATA_DIR, get_db
    problems = []
    with app.app_context():
        db = get_db()
        probe = os.path.join(DATA_DIR, ".write-test")
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
        except OSError as e:  # noqa: BLE001
            problems.append(
                f"{DATA_DIR} is not writable ({e}). Uploads and orders will fail. "
                "Check the volume mount."
            )

        stored = db.execute(
            "SELECT key, value FROM settings WHERE (key LIKE 'integration_%' OR key LIKE '%_enc') "
            "AND value IS NOT NULL AND value != ''"
        ).fetchall()
        unreadable = [
            row["key"] for row in stored
            if str(row["value"]).startswith("gAAAA") and crypto.decrypt(row["value"]) is None
        ]
        if unreadable:
            problems.append(
                f"{len(unreadable)} saved credential(s) cannot be decrypted — they were encrypted "
                f"with a different key than the one now in {DATA_DIR}. This is what a container "
                "recreated without a persistent volume looks like. Re-enter them in the admin "
                "screens, and make sure that directory is a mounted volume."
            )
    for problem in problems:
        app.logger.error("STORAGE: %s", problem)
    return problems


def storage_problems(db):
    """The same check, for showing in the admin screens rather than a log."""
    from .db import DATA_DIR
    rows = db.execute(
        "SELECT key, value FROM settings WHERE (key LIKE 'integration_%' OR key LIKE '%_enc') "
        "AND value IS NOT NULL AND value != ''"
    ).fetchall()
    unreadable = [r["key"] for r in rows
                  if str(r["value"]).startswith("gAAAA") and crypto.decrypt(r["value"]) is None]
    if not unreadable:
        return None
    return (f"{len(unreadable)} saved credential(s) can't be read: they were encrypted with a "
            f"different key than the one in {DATA_DIR}. That usually means this container was "
            "recreated without its data volume. Re-enter them below.")
