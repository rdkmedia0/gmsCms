"""Saying thanks, and the one line on every site until somebody does.

gmsCms is free to use. What it asks in return is a single small line under
the site's footer -- "Built with gmsCms, which is free to use. Site owners
can remove this line by supporting the project." -- and a supporter gets
a KEY that removes it. Once, for good: the key is one-off, not a
subscription and not renewable. A second site is a second key, and
giving again afterwards is welcome and entirely optional.

Three things are deliberate about how this is built:

  * **The way to pay is hard-coded.** PAYPAL_URL is a constant in this
    file, not a setting: nothing on a site, no template, no import, no
    admin screen can point the credit line anywhere else. A package that
    could carry a donation link is a package that could carry somebody
    else's.
  * **The key is signed and checked here, offline.** No server is
    called, no account exists, nothing phones home. What a key IS lives
    in support_key.py (standard library only, so tools/make_license.py
    can make one on a machine with no Flask); this module only ever
    checks one. It is a courtesy lock, not copy protection -- the line
    asks; it does not enforce.
  * **The state is a FILE in DATA_DIR**, beside the database, because it
    belongs to this install and must survive an image upgrade the way the
    database does. `license.json` holds the key.

There is nothing to expire and nothing to revoke: the same screen that
applies a key can take it off again, and that is the whole mechanism.
"""
import os
import json
import datetime

from ..db import DATA_DIR
from .support_key import make_key, parse_key  # noqa: F401 -- re-exported

#  Where support goes. Hard-coded on purpose -- see the module note. A
#  PayPal donate link to the project's own account; `no_recurring=1`
#  because a supporter's key is one-off and the ask should look like it.
PAYPAL_URL = ("https://www.paypal.com/donate/?business=rdkmedia0%40gmail.com"
              "&no_recurring=1&item_name=gmsCms")

LICENSE_PATH = os.path.join(DATA_DIR, "license.json")


def _read():
    try:
        with open(LICENSE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def state():
    """{installed, valid, key, since}. `valid` is what everything else
    reads: a genuine key is on file. A file that does not parse counts as
    no file; a key that is not ours is `installed` but not `valid`, so the
    screen can say so rather than show the line with no explanation."""
    data = _read()
    key = (data.get("key") or "").strip()
    return {
        "installed": bool(key),
        "valid": bool(key) and parse_key(key),
        "key": key or None,
        "since": data.get("installed"),
    }


def notice():
    """What the public page renders under the footer: the link, or None
    while a supporter's key is on file."""
    if state()["valid"]:
        return None
    return {"url": PAYPAL_URL}


def install_key(key):
    """Write a key to the install. Raises ValueError, in the owner's words,
    for a key that is not genuine -- a key that cannot remove the line is
    not installed, so the screen never says 'saved' about something that
    changed nothing."""
    if not parse_key(key):
        raise ValueError("That isn't a gmsCms supporter key. Check for a missed character — it looks like GMS-1A2B3C4D-A1B2C3D4E5F60718.")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LICENSE_PATH, "w", encoding="utf-8") as f:
        json.dump({"key": key.strip().upper(),
                   "installed": datetime.date.today().isoformat()}, f, indent=2)


def remove():
    """Take the key off the install; the line returns. Returns True if
    there was one to remove."""
    try:
        os.remove(LICENSE_PATH)
    except FileNotFoundError:
        return False
    return True
