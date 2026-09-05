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

#  Crypto, for a supporter who would rather not go through PayPal. Hard-
#  coded for the same reason PAYPAL_URL is: a wallet address that lived
#  in a setting or a package could be pointed at somebody else's wallet,
#  and a wrong address is money gone with no way back. A chain with no
#  address is simply not offered -- fill one in and it appears.
#
#  `uri` is the scheme a wallet app understands when it scans the QR
#  (BIP-21 for bitcoin, EIP-681 for ethereum); it prefixes the address.
#  `note` is what to say about that chain under its address -- the one
#  that matters is which networks the address actually credits, because
#  a transfer on the wrong one is lost. These are Coinbase addresses; the
#  EVM one takes any EVM network Coinbase settles (Base, Polygon, ...).
CRYPTO_WALLETS = (
    {"name": "Bitcoin", "symbol": "BTC", "uri": "bitcoin:",
     "address": "bc1qkxc695rp49sjjuj2egwhp3k8w4we0359z0vmux",
     "note": "Bitcoin network only."},
    {"name": "Ethereum & EVM", "symbol": "ETH", "uri": "ethereum:",
     "address": "0xa2e66631f91673d549ae295773ca7fe7c60e7b76",
     "note": "ETH and any token on Ethereum, Base, Polygon or another EVM network."},
    {"name": "Litecoin", "symbol": "LTC", "uri": "litecoin:", "address": "", "note": ""},
    {"name": "Solana", "symbol": "SOL", "uri": "solana:", "address": "", "note": ""},
)

#  The coin's own mark, drawn in the centre of its QR so a wallet of
#  identical-looking codes is told apart at a glance. Each is (viewBox,
#  path, brand colour); a QR at 30% error correction reconstructs the
#  modules the mark covers, so the code still scans. Marks are the
#  FontAwesome brand glyphs (the whole coin for Bitcoin, the diamond for
#  Ethereum), drawn currentColour-free because a brand colour is the point.
_COIN_MARKS = {
    "BTC": ("0 0 512 512", "#F7931A",
            "M504 256c0 137-111 248-248 248S8 393 8 256 119 8 256 8s248 111 248 248zm-141.7-35.33c4.937-32.1-19.796-49.36-53.63-60.86l10.97-44.02-26.8-6.68-10.68 42.85c-7.05-1.76-14.29-3.42-21.48-5.06l10.75-43.13-26.79-6.68-10.98 44c-5.84-1.33-11.57-2.64-17.13-4.02l.03-.14-36.96-9.23-7.13 28.65s19.9 4.56 19.48 4.84c10.86 2.71 12.82 9.9 12.5 15.6l-12.51 50.14c.75.19 1.72.47 2.79.9-.9-.22-1.85-.46-2.83-.7l-17.55 70.29c-1.33 3.3-4.7 8.25-12.31 6.37.27.39-19.5-4.87-19.5-4.87l-13.31 30.7 34.85 8.69c6.48 1.63 12.83 3.33 19.08 4.94l-11.09 44.52 26.77 6.68 10.98-44.03c7.31 1.98 14.41 3.81 21.36 5.54l-10.94 43.83 26.8 6.68 11.09-44.43c45.7 8.65 80.08 5.16 94.54-36.17 11.64-33.27-.58-52.48-24.63-65.02 17.52-4.04 30.71-15.58 34.23-39.39zM255.6 300.98c-8.28 33.27-64.28 15.28-82.44 10.77l14.72-59c18.16 4.53 76.36 13.5 67.72 48.23zm8.29-45.52c-7.55 30.27-54.15 14.89-69.28 11.13l13.34-53.53c15.13 3.77 63.87 10.79 55.94 42.4z"),
    "ETH": ("0 0 320 512", "#627EEA",
            "M311.9 260.8L160 353.6 8 260.8 160 0l151.9 260.8zM160 383.4L8 290.6 160 512l152-221.4-152 92.8z"),
}

LICENSE_PATH = os.path.join(DATA_DIR, "license.json")


def wallet_qr_svg(text, symbol=""):
    """A QR code for a wallet URI, as inline SVG, with the coin's mark in
    the middle -- what a phone's wallet scans instead of forty typed
    characters. `qrcode` draws it without Pillow; an install without the
    package gets no picture and keeps the address and Copy, which still
    work. High error correction so the centre mark costs no readability."""
    try:
        import qrcode
    except ImportError:
        return ""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    #  Modules as one path of unit squares, in a viewBox n units wide, so
    #  the mark below can be placed in the same coordinates.
    cells = "".join("M%d %dh1v1h-1z" % (x, y)
                    for y, row in enumerate(matrix) for x, cell in enumerate(row) if cell)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'shape-rendering="crispEdges">' % (n, n),
             '<rect width="%d" height="%d" fill="#fff"/>' % (n, n),
             '<path d="%s" fill="#000"/>' % cells]
    mark = _COIN_MARKS.get(symbol)
    if mark:
        viewbox, colour, path = mark
        box = n * 0.24              # the mark
        clear = box * 1.32          # white plate cleared behind it
        parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" rx="%.3f" fill="#fff"/>'
                     % ((n - clear) / 2, (n - clear) / 2, clear, clear, clear * 0.16))
        #  A nested SVG scales and centres the brand path by its own
        #  viewBox, so a non-square mark (Ethereum is 320x512) sits right
        #  with no transform arithmetic here.
        parts.append('<svg x="%.3f" y="%.3f" width="%.3f" height="%.3f" viewBox="%s">'
                     '<path d="%s" fill="%s"/></svg>'
                     % ((n - box) / 2, (n - box) / 2, box, box, viewbox, path, colour))
    parts.append("</svg>")
    return "".join(parts)


def crypto_wallets():
    """The wallets with an address, each with its scan URI and QR."""
    out = []
    for w in CRYPTO_WALLETS:
        addr = (w.get("address") or "").strip()
        if not addr:
            continue
        uri = w["uri"] + addr
        out.append(dict(w, address=addr, scan=uri, qr_svg=wallet_qr_svg(uri, w["symbol"])))
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
