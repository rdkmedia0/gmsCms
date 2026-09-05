"""The supporter's key itself: how one is made and how one is read.

Standard library only, on purpose. tools/make_license.py runs this on
the developer's own machine, which has no Flask in it, and services/
support.py runs it inside the app; one file both can import is what
keeps a key made on one side readable on the other. Everything about
WHERE a key is kept, and what it removes, is in services/support.py.

A key is ONE-OFF and permanent: `GMS-<8 hex>-<16 hex>`, a random
nonce and an HMAC of it under the signing key below. It carries no date
and never runs out -- a supporter paid once and the line is gone for
good on that site; a second site is a second key, and giving again is a
choice, not a renewal. This is a courtesy lock, not copy protection --
the signing key lives in this (private) repository, and an owner who
edits the source can remove the line by hand. The line asks; it does
not enforce.
"""
import re
import hmac
import secrets
import hashlib

#  Changing this invalidates every key ever issued, which is the one thing
#  never to do by accident.
_SIGNING_KEY = b"gmscms-supporter-key-v1-2026-09"
_KEY_RE = re.compile(r"^GMS-([0-9A-F]{8})-([0-9A-F]{16})$")


def _sig(nonce):
    return hmac.new(_SIGNING_KEY, f"gmscms-license:{nonce}".encode(),
                    hashlib.sha256).hexdigest()[:16].upper()


def make_key(nonce=None):
    """A key. With no nonce it is fresh and random (a person issuing keys
    by hand gets a different one each time); with a nonce it is
    deterministic, so the same source -- e.g. one blockchain payment --
    always yields the same key rather than a new one on every retry."""
    nonce = (nonce or secrets.token_hex(4)).upper()[:8].rjust(8, "0")
    return f"GMS-{nonce}-{_sig(nonce)}"


def parse_key(key):
    """True for a genuine key, False for anything else. Whitespace and
    case are forgiven -- a key is typed or pasted."""
    m = _KEY_RE.match((key or "").strip().upper())
    if not m:
        return False
    return hmac.compare_digest(m.group(2), _sig(m.group(1)))
