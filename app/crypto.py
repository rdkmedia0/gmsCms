"""
Encrypts secrets (AI provider API keys, and anything similar going
forward) before they're written to the database, so a copy of the DB file
alone — a backup, a leaked volume, a bug that dumps a table — doesn't hand
over live credentials in plaintext. Separate from Flask's own SECRET_KEY
(app/__init__.py's .secret_key file): that one signs sessions and is
already effectively "public" in the sense that a stolen session cookie is
the actual risk, not the key itself sitting on disk; this one gates
actual third-party API keys, so it gets its own file and its own purpose.

Fernet (AES-128-CBC + HMAC, both keyed, via the `cryptography` package) —
authenticated symmetric encryption: a tampered or corrupted ciphertext
fails to decrypt instead of silently returning garbage.
"""
import os
import stat
from cryptography.fernet import Fernet, InvalidToken

from .db import DATA_DIR

KEY_PATH = os.path.join(DATA_DIR, ".encryption_key")

_fernet = None


def key_source():
    """Where the key is coming from, for the admin screens and the log."""
    if (os.environ.get("ENCRYPTION_KEY") or "").strip():
        return "environment"
    return "file" if os.path.exists(KEY_PATH) else "generated"


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet

    #  An environment key wins over the file, and is never written to
    #  disk. That is the whole point: with the key beside the database,
    #  anyone who copies the volume — a backup, a snapshot, a support
    #  bundle — has both halves and the encryption bought nothing.
    #  Supplied this way (a Docker secret, or the compose environment) the
    #  two live in genuinely different places.
    supplied = (os.environ.get("ENCRYPTION_KEY") or "").strip()
    if supplied:
        try:
            _fernet = Fernet(supplied.encode())
            return _fernet
        except (ValueError, TypeError) as e:
            #  Refuse rather than fall through to the file: quietly using
            #  a different key than the one the operator thinks is in use
            #  is how a database ends up half-readable.
            raise RuntimeError(
                "ENCRYPTION_KEY is set but is not a valid Fernet key "
                "(44 url-safe base64 characters). Refusing to start with the wrong key."
            ) from e

    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            key = f.read().strip()
    else:
        key = Fernet.generate_key()
        # Written before world/group-readable perms can be assumed away —
        # O_CREAT|O_EXCL avoids a race where two gunicorn workers booting
        # at once both see "missing" and both generate a different key,
        # which would make whichever wrote second silently unable to
        # decrypt anything the first had already encrypted moments earlier.
        try:
            fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        except FileExistsError:
            with open(KEY_PATH, "rb") as f:
                key = f.read().strip()
        else:
            try:
                os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
    _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext):
    """str -> str (base64 token), or None for falsy input — so callers can
    write straight to a nullable column without an extra branch."""
    if not plaintext:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token):
    """str -> str, or None if there's nothing to decrypt or the token is
    invalid/from a different key (e.g. the key file was regenerated) —
    callers treat that the same as "not configured" rather than crashing
    the page that needed it."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
