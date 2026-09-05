"""Showing appreciation, and the small credit line under the footer.

gmsCms is free. It carries one small credit line under a site's footer by
default -- and the owner can switch it off whenever they like, no strings.
Donations are a separate thing entirely: a gift if the tool has been
useful, never a price and never tied to the line.

This used to be a licence: the line was removed by a signed KEY, issued
per payment, verified on-chain or by hand. That was a lot of machinery
(keys, a signing secret, blockchain lookups, a claims file) for a
thank-you, and it dressed a courtesy up as a lock it never really was --
the secret shipped in the code, so any install could mint its own key.
It is gone. The line is now a plain preference: on by default, off by one
click. Appreciation is asked for, not charged.

Two things stay deliberate:

  * **The way to give is hard-coded.** PAYPAL_URL and CRYPTO_WALLETS are
    constants in this file, not settings: nothing on a site, no template,
    no import can point a donate link or a wallet at somebody else's
    account. A wrong crypto address is money gone with no way back, so it
    must not be editable from anywhere a mistake or a package could reach.
  * **The preference is a FILE in DATA_DIR**, beside the database, so the
    owner's choice to hide the line survives an image upgrade the way
    their content does.
"""
import os
import json

from ..db import DATA_DIR

#  Where support goes. Hard-coded on purpose -- see the module note.
#
#  A raw `business=<email>` donate link shows the address on the URL and
#  on PayPal's own page. A PayPal.Me handle (works on a personal account)
#  hides it -- the link is just paypal.me/<handle>. A hosted button
#  (business account) hides it behind an id. The email form is the
#  last-resort fallback so a donate link always exists.
PAYPAL_ME_HANDLE = "rdkmedia0"
PAYPAL_HOSTED_BUTTON_ID = ""
if PAYPAL_ME_HANDLE:
    PAYPAL_URL = "https://www.paypal.com/paypalme/" + PAYPAL_ME_HANDLE
elif PAYPAL_HOSTED_BUTTON_ID:
    PAYPAL_URL = ("https://www.paypal.com/donate/?hosted_button_id="
                  + PAYPAL_HOSTED_BUTTON_ID)
else:
    PAYPAL_URL = ("https://www.paypal.com/donate/?business=rdkmedia0%40gmail.com"
                  "&no_recurring=1&item_name=gmsCms")

#  The project itself, for a "made by" link.
GITHUB_CONTACT_URL = "https://github.com/rdkmedia0/gmsCms"

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
#  a transfer on the wrong one is lost. These are Coinbase addresses.
CRYPTO_WALLETS = (
    {"name": "Bitcoin", "symbol": "BTC", "uri": "bitcoin:",
     "address": "bc1qkxc695rp49sjjuj2egwhp3k8w4we0359z0vmux",
     "note": "Bitcoin network only."},
    {"name": "Ethereum & EVM", "symbol": "ETH", "uri": "ethereum:",
     "address": "0xa2e66631f91673d549ae295773ca7fe7c60e7b76",
     "note": "ETH on Ethereum or Base, or POL on Polygon. The network's own coin only — not tokens."},
    {"name": "Litecoin", "symbol": "LTC", "uri": "litecoin:", "address": "", "note": ""},
    {"name": "Solana", "symbol": "SOL", "uri": "solana:", "address": "", "note": ""},
)

#  The coin's own mark, in the centre of its QR, drawn app-icon style --
#  a rounded-square tile in the brand colour with a clean white glyph, the
#  way a wallet like Coinbase Base shows it. Each is (tile colour, glyph
#  viewBox, glyph path); the glyph is the FontAwesome mark (the ₿ sign for
#  Bitcoin, the diamond for Ethereum), painted white on the tile. A QR at
#  30% error correction reconstructs the modules the tile covers, so the
#  code still scans.
_COIN_MARKS = {
    "BTC": ("#F7931A", "0 0 320 512",
            "M48 32C48 14.3 62.3 0 80 0s32 14.3 32 32V64h32V32c0-17.7 14.3-32 32-32s32 14.3 32 32V64c0 1.5-.1 3.1-.3 4.5C254.1 82.2 288 125.1 288 176c0 24.2-7.7 46.6-20.7 64.9c31.7 19.8 52.7 55 52.7 95.1c0 61.9-50.1 112-112 112v32c0 17.7-14.3 32-32 32s-32-14.3-32-32V448H112v32c0 17.7-14.3 32-32 32s-32-14.3-32-32V448H41.7C18.7 448 0 429.3 0 406.3V288 265.7 224 101.6C0 80.8 16.8 64 37.6 64H48V32zM64 224H176c26.5 0 48-21.5 48-48s-21.5-48-48-48H64v96zm112 64H64v96H208c26.5 0 48-21.5 48-48s-21.5-48-48-48H176z"),
    "ETH": ("#627EEA", "0 0 320 512",
            "M311.9 260.8L160 353.6 8 260.8 160 0l151.9 260.8zM160 383.4L8 290.6 160 512l152-221.4-152 92.8z"),
}


def wallet_qr_svg(text, symbol=""):
    """A QR code for a wallet URI, as inline SVG, with the coin's mark in
    the middle. `qrcode` draws it without Pillow; an install without the
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
    cells = "".join("M%d %dh1v1h-1z" % (x, y)
                    for y, row in enumerate(matrix) for x, cell in enumerate(row) if cell)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'shape-rendering="crispEdges">' % (n, n),
             '<rect width="%d" height="%d" fill="#fff"/>' % (n, n),
             '<path d="%s" fill="#000"/>' % cells]
    mark = _COIN_MARKS.get(symbol)
    if mark:
        colour, viewbox, path = mark
        tile = n * 0.26
        clear = tile * 1.16
        c = n / 2
        parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" rx="%.3f" fill="#fff"/>'
                     % (c - clear / 2, c - clear / 2, clear, clear, clear * 0.30))
        parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" rx="%.3f" fill="%s"/>'
                     % (c - tile / 2, c - tile / 2, tile, tile, tile * 0.28, colour))
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


# --- The footer credit line -----------------------------------------------
#
#  On by default; the owner can switch it off. The choice is one flag in a
#  small file beside the database, so it survives an upgrade.

PREFS_PATH = os.path.join(DATA_DIR, "support.json")


def _prefs():
    try:
        with open(PREFS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def notice_hidden():
    """Whether the owner has switched the footer credit off."""
    return bool(_prefs().get("hidden"))


def set_notice_hidden(hidden):
    """Show or hide the footer credit."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump({"hidden": bool(hidden)}, f, indent=2)


def notice():
    """What the public page renders under the footer: the project + donate
    link, or None when the owner has turned it off. A plain credit now --
    no payment removes it, a click does."""
    if notice_hidden():
        return None
    return {"url": PAYPAL_URL, "project_url": GITHUB_CONTACT_URL}
