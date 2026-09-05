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
import time
import hashlib
import datetime
import urllib.request
import urllib.error

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


# --- Claim a key with a payment ------------------------------------------
#
#  A supporter who has paid pastes their transaction id, and the app
#  checks it against the project's hard-coded addresses on a public block
#  explorer -- confirmed, and paid to us -- then issues the key itself and
#  removes the line. No email, no central server, instant.
#
#  This runs on the OWNER's own install and the app already carries the
#  key-signing code, so on-chain verification is a courtesy gate, not
#  protection: it asks somebody to have paid before it hands them the
#  key it could always have made. That is the same footing the whole
#  scheme stands on (the footer line is not enforced either).
#
#  What is checked: a NATIVE-coin payment (BTC, or ETH/POL on Ethereum,
#  Base or Polygon) whose output/`to` is our address. A token transfer
#  (USDC and the like) calls a contract rather than paying our address
#  directly, so it does not validate here and falls back to the email
#  steps -- said as much on the screen.

CLAIMS_PATH = os.path.join(DATA_DIR, "support_claims.json")
_HTTP_TIMEOUT = 8

#  Public, keyless endpoints. Each chain lists more than one so a single
#  explorer being down or rate-limiting is not the whole feature failing.
_BTC_APIS = ("https://mempool.space/api", "https://blockstream.info/api")
_EVM_CHAINS = (
    ("Ethereum", ("https://ethereum-rpc.publicnode.com", "https://cloudflare-eth.com")),
    ("Base", ("https://base-rpc.publicnode.com", "https://mainnet.base.org")),
    ("Polygon", ("https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com")),
)


def _addr_for(symbol):
    for w in CRYPTO_WALLETS:
        if w["symbol"] == symbol:
            return (w.get("address") or "").strip()
    return ""


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "gmsCms-support"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "gmsCms-support"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode()).get("result")


def _looks_like_evm(txid):
    return txid.startswith("0x") and len(txid) == 66


def _verify_btc(txid):
    """(ok, detail). Confirmed, and an output pays our BTC address."""
    ours = _addr_for("BTC")
    if not ours:
        return False, ""
    for base in _BTC_APIS:
        try:
            tx = _get_json("%s/tx/%s" % (base, txid))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "No Bitcoin transaction with that id was found. Check you copied all of it."
            continue
        except Exception:  # noqa: BLE001 -- try the next explorer
            continue
        if not (tx.get("status") or {}).get("confirmed"):
            return False, "That transaction hasn't confirmed yet. Try again once it has a confirmation."
        paid = any(o.get("scriptpubkey_address") == ours for o in tx.get("vout") or [])
        if paid:
            return True, "Bitcoin"
        return False, "That transaction didn't pay this site's Bitcoin address."
    return False, ""  # no explorer answered -- caller reports a soft failure


def _verify_evm(txid):
    """(ok, detail). A confirmed native-coin transfer to our address on any
    of the EVM chains we watch."""
    ours = _addr_for("ETH").lower()
    if not ours:
        return False, ""
    reached = False        # at least one RPC answered us
    seen_anywhere = False   # the tx exists on some chain
    for name, urls in _EVM_CHAINS:
        for url in urls:
            try:
                tx = _rpc(url, "eth_getTransactionByHash", [txid])
            except Exception:  # noqa: BLE001
                continue
            reached = True
            if not tx:
                break  # this chain answered "no such tx"; try the next chain
            seen_anywhere = True
            to = (tx.get("to") or "").lower()
            value = int(tx.get("value") or "0x0", 16)
            if to != ours:
                break  # found, but not a native payment to us (maybe a token) -> next chain
            try:
                receipt = _rpc(url, "eth_getTransactionReceipt", [txid])
            except Exception:  # noqa: BLE001
                receipt = None
            if not receipt or not receipt.get("blockNumber"):
                return False, "That transaction hasn't confirmed yet. Try again in a moment."
            if receipt.get("status") not in ("0x1", None):
                return False, "That transaction failed on-chain, so nothing was received."
            if value <= 0:
                return False, "That looks like a token transfer — those can't be checked here. Use the email steps below."
            return True, name
    if seen_anywhere:
        return False, "That transaction didn't pay this site's Ethereum address. A token transfer? Use the email steps below."
    if reached:
        return False, "No transaction with that id was found on Ethereum, Base or Polygon. Check you copied all of it."
    return False, ""


def verify_payment(txid):
    """(ok, detail). detail is the chain name on success, or a sentence to
    show the owner on failure. An empty detail means no explorer could be
    reached -- a soft failure the screen frames as 'try again'."""
    txid = (txid or "").strip().split()[0] if (txid or "").strip() else ""
    if not txid:
        return False, "Paste the transaction id first."
    if _looks_like_evm(txid):
        return _verify_evm(txid)
    #  A bare 64-hex string is a Bitcoin txid (with or without an 0x the
    #  EVM branch already took).
    if len(txid) == 64 and all(c in "0123456789abcdefABCDEF" for c in txid):
        return _verify_btc(txid.lower())
    return False, "That doesn't look like a transaction id. Copy it from your wallet or Coinbase — a long string of letters and numbers."


def _claims():
    try:
        with open(CLAIMS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def claim_with_txid(txid):
    """Verify a payment and, if it is good, issue the key for it and remove
    the line. Returns (ok, message). The key is derived from the txid, so
    the same payment always produces the same key and a re-submit is
    harmless. Each txid is written down so it reads as one payment, one
    key."""
    txid = (txid or "").strip()
    key_id = txid.lower().split()[0] if txid.split() else ""
    claims = _claims()
    if key_id and key_id in claims and state()["valid"]:
        return True, "This payment has already unlocked your site — you're all set."
    ok, detail = verify_payment(txid)
    if not ok:
        if not detail:
            return False, "Couldn't reach a block explorer just now. Wait a moment and try again, or use the email steps below."
        return False, detail
    nonce = hashlib.sha256(("gmscms-tx:" + key_id).encode()).hexdigest()[:8]
    install_key(make_key(nonce))
    claims[key_id] = {"chain": detail, "at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CLAIMS_PATH, "w", encoding="utf-8") as f:
            json.dump(claims, f, indent=2)
    except OSError:
        pass  # the key is installed; failing to note the txid is not worth undoing that
    return True, "Payment confirmed on %s. Your key is applied and the line under your footer is gone. Thank you!" % detail
