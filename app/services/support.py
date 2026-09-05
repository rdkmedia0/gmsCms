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

#  ONE crypto link that takes many currencies: a Coinbase Commerce
#  checkout (commerce.coinbase.com/checkout/<id>), where the person paying
#  picks the coin and the network and it lands in the project's Coinbase
#  account. Preferred over per-coin addresses because there is one thing
#  to check and nothing to get wrong about networks. Empty = not offered.
COINBASE_COMMERCE_URL = ""

#  Crypto, for a supporter who would rather not go through PayPal. Hard-
#  coded for the same reason PAYPAL_URL is: a wallet address that lived
#  in a setting or a package could be pointed at somebody else's wallet,
#  and a wrong address is money gone with no way back. A chain with no
#  address is simply not offered -- fill one in and it appears.
#
#  `uri` is the scheme a wallet app understands when it scans the QR
#  (BIP-21 for bitcoin, EIP-681 for ethereum); it prefixes the address.
CRYPTO_WALLETS = (
    {"name": "Bitcoin", "symbol": "BTC", "uri": "bitcoin:", "address": ""},
    {"name": "Ethereum", "symbol": "ETH", "uri": "ethereum:", "address": ""},
    {"name": "Litecoin", "symbol": "LTC", "uri": "litecoin:", "address": ""},
    {"name": "Solana", "symbol": "SOL", "uri": "solana:", "address": ""},
)

LICENSE_PATH = os.path.join(DATA_DIR, "license.json")


def wallet_qr_svg(text):
    """A QR code for a wallet URI, as inline SVG -- what a phone's wallet
    scans instead of typing forty characters. `qrcode` draws it without
    Pillow; an install without the package gets no picture and keeps the
    address and Copy, which still work."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=10, border=2)
    return img.to_string(encoding="unicode")


def crypto_wallets():
    """The wallets with an address, each with its scan URI and QR."""
    out = []
    for w in CRYPTO_WALLETS:
        addr = (w.get("address") or "").strip()
        if not addr:
            continue
        uri = w["uri"] + addr
        out.append(dict(w, address=addr, scan=uri, qr_svg=wallet_qr_svg(uri)))
    return out


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
