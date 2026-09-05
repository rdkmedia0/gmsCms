"""Saying thanks, and the one line on every site until somebody does.

gmsCms is free to use. What it asks in return is a single small line under
the site's footer -- "Built with gmsCms, which is free to use. Site owners
can remove this line by supporting the project." -- and a supporter gets
a KEY that removes it for the period their support covers.

Three things are deliberate about how this is built:

  * **The way to pay is hard-coded.** PAYPAL_URL is a constant in this
    file, not a setting: nothing on a site, no template, no import, no
    admin screen can point the credit line anywhere else. A package that
    could carry a donation link is a package that could carry somebody
    else's.
  * **The key is a signed date, checked here, offline.** No server is
    called, no account exists, nothing phones home. What a key IS lives
    in support_key.py (standard library only, so tools/make_license.py
    can make one on a machine with no Flask); this module only ever
    checks one. It is a courtesy lock, not copy protection -- the line
    asks; it does not enforce.
  * **The state is a FILE in DATA_DIR**, beside the database, because it
    belongs to this install and must survive an image upgrade the way the
    database does. `license.json` holds the key and the day it expires.

The line comes back by itself when the key runs out. That is the whole
"period of support" mechanism; there is nothing to revoke.
"""
import os
import json
import datetime

from ..db import DATA_DIR
from .support_key import make_key, parse_key  # noqa: F401 -- re-exported

#  Where support goes. Hard-coded on purpose -- see the module note.
PAYPAL_URL = "https://www.paypal.com/paypalme/REPLACE-WITH-YOUR-PAYPAL-PATH"

LICENSE_PATH = os.path.join(DATA_DIR, "license.json")


def _read():
    try:
        with open(LICENSE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def state(today=None):
    """{installed, valid, until, days_left, key}. `valid` is what everything
    else reads: the key on file is genuine AND has not run out. A file
    that does not parse counts as no file."""
    today = today or datetime.date.today()
    data = _read()
    until = parse_key(data.get("key")) if data else None
    installed = bool(data.get("key"))
    valid = until is not None and until >= today
    return {
        "installed": installed,
        "valid": valid,
        "until": until,
        "days_left": (until - today).days if valid else None,
        "key": data.get("key") if installed else None,
    }


def notice():
    """What the public page renders under the footer: the link, or None
    while a supporter's key is in force."""
    if state()["valid"]:
        return None
    return {"url": PAYPAL_URL}


def install_key(key):
    """Write a key to the install. Raises ValueError, in the owner's words,
    for a key that is not genuine or has already run out -- a key that
    cannot remove the line is not installed, so the screen never says
    'saved' about something that changed nothing."""
    until = parse_key(key)
    if until is None:
        raise ValueError("That isn't a gmsCms supporter key. Check for a missed character — it looks like GMS-20270101-A1B2C3D4E5F60718.")
    if until < datetime.date.today():
        raise ValueError(f"That key ran out on {until:%d %B %Y}. A newer one is needed.")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LICENSE_PATH, "w", encoding="utf-8") as f:
        json.dump({"key": key.strip().upper(), "until": until.isoformat(),
                   "installed": datetime.date.today().isoformat()}, f, indent=2)
    return until


def remove():
    """Take the key off the install; the line returns. Returns True if
    there was one to remove."""
    try:
        os.remove(LICENSE_PATH)
    except FileNotFoundError:
        return False
    return True
