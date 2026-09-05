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

#  Where a supporter writes to claim their key. The same address the
#  PayPal link already exposes, so this reveals nothing new, and the
#  Support screen is admin-only regardless.
SUPPORT_EMAIL = "rdkmedia0@gmail.com"

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

#  The coin's own mark, in the centre of its QR, drawn app-icon style --
#  a rounded-square tile in the brand colour with a clean white glyph, the
#  way a wallet like Coinbase Base shows it -- so a wallet of identical-
#  looking codes is told apart at a glance. Each is (tile colour, glyph
#  viewBox, glyph path); the glyph is the FontAwesome mark (the ₿ sign for
#  Bitcoin, the diamond for Ethereum), painted white on the tile. A QR at
#  30% error correction reconstructs the modules the tile covers, so the
#  code still scans -- proved by decoding the rendered SVG.
_COIN_MARKS = {
    "BTC": ("#F7931A", "0 0 320 512",
            "M48 32C48 14.3 62.3 0 80 0s32 14.3 32 32V64h32V32c0-17.7 14.3-32 32-32s32 14.3 32 32V64c0 1.5-.1 3.1-.3 4.5C254.1 82.2 288 125.1 288 176c0 24.2-7.7 46.6-20.7 64.9c31.7 19.8 52.7 55 52.7 95.1c0 61.9-50.1 112-112 112v32c0 17.7-14.3 32-32 32s-32-14.3-32-32V448H112v32c0 17.7-14.3 32-32 32s-32-14.3-32-32V448H41.7C18.7 448 0 429.3 0 406.3V288 265.7 224 101.6C0 80.8 16.8 64 37.6 64H48V32zM64 224H176c26.5 0 48-21.5 48-48s-21.5-48-48-48H64v96zm112 64H64v96H208c26.5 0 48-21.5 48-48s-21.5-48-48-48H176z"),
    "ETH": ("#627EEA", "0 0 320 512",
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
        colour, viewbox, path = mark
        tile = n * 0.26                    # the coloured squircle
        clear = tile * 1.16                # a little white gap around it
        c = n / 2
        parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" rx="%.3f" fill="#fff"/>'
                     % (c - clear / 2, c - clear / 2, clear, clear, clear * 0.30))
        parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" rx="%.3f" fill="%s"/>'
                     % (c - tile / 2, c - tile / 2, tile, tile, tile * 0.28, colour))
        #  A nested SVG scales and centres the white glyph by its own
        #  viewBox (xMidYMid meet), so a tall mark like the ₿ sign sits
        #  centred in the square tile with no transform arithmetic here.
        g = tile * 0.62
        parts.append('<svg x="%.3f" y="%.3f" width="%.3f" height="%.3f" viewBox="%s">'
                     '<path d="%s" fill="#fff"/></svg>'
                     % (c - g / 2, c - g / 2, g, g, viewbox, path))
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
