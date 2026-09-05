"""The supporter's key itself: how one is made and how one is read.

Standard library only, on purpose. tools/make_license.py runs this on
the developer's own machine, which has no Flask in it, and services/
support.py runs it inside the app; one file both can import is what
keeps a key made on one side readable on the other. Everything about
WHERE a key is kept, and what it removes, is in services/support.py.

A key is `GMS-YYYYMMDD-<16 hex>`: the day it runs out and an HMAC of that
day under the signing key below. This is a courtesy lock, not copy
protection -- the signing key lives in this (private) repository, and an
owner who edits the source can remove the line by hand. The line asks;
it does not enforce.
"""
import re
import hmac
import hashlib
import datetime

#  Changing this invalidates every key ever issued, which is the one thing
#  never to do by accident.
_SIGNING_KEY = b"gmscms-supporter-key-v1-2026-09"
_KEY_RE = re.compile(r"^GMS-(\d{8})-([0-9A-F]{16})$")


def _sig(until_iso):
    return hmac.new(_SIGNING_KEY, f"gmscms-license:{until_iso}".encode(),
                    hashlib.sha256).hexdigest()[:16].upper()


def make_key(until):
    """A key that removes the line until `until` (a date)."""
    return f"GMS-{until:%Y%m%d}-{_sig(until.isoformat())}"


def parse_key(key):
    """The expiry date a key carries, or None if it is not one of ours.
    Whitespace and case are forgiven -- a key is typed or pasted."""
    m = _KEY_RE.match((key or "").strip().upper())
    if not m:
        return None
    try:
        until = datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None
    if not hmac.compare_digest(m.group(2), _sig(until.isoformat())):
        return None
    return until
