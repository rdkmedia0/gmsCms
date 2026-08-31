"""Reading the STYLE of a page somebody points at. Never its substance.

You can hand the Theme Generator a site you like the look of, and it
takes signals from it: the colours and roughly what they are used for,
the typefaces, how round the corners are, how deep the shadows are. Those
become starting VALUES in the generator's own controls, every one of them
shown and editable before anything is made -- extraction is a guess, and
a guess somebody can correct is worth ten they cannot see.

**It never takes words, pictures or markup.** That boundary is not a
preference and it is not enforced by good intentions: this module cannot
return prose. It returns colours, font names, two numbers and a count.
There is nothing in its output that could carry somebody's copy, and
nothing that could carry their photographs. A look is fair to admire; the
words are their work and the pictures are their licence.

Fetching a URL is also a request this app makes on somebody's behalf, so:

  * http and https only -- no file://, no data:, no gopher;
  * the address is resolved and refused if it is loopback, private,
    link-local or otherwise not a public host, because "fetch this URL
    for me" is otherwise a way to ask a server to read its own network;
  * a redirect chain is followed at most three times and re-checked at
    every hop, since a public address can redirect to a private one;
  * a timeout, and a hard byte cap read incrementally rather than
    trusting Content-Length.
"""
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

#  Enough to read a look from. A page that needs more than this to show
#  its colours is a page whose colours are in an image.
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 8
MAX_REDIRECTS = 3
MAX_STYLESHEETS = 4

#  A real browser's, because a great many sites answer a bare urllib with
#  a block page -- and a block page's colours are not the site's.
AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


class RefusedError(Exception):
    """Why this address will not be fetched, in the owner's terms."""


def _public_or_refuse(url):
    """The parsed URL, or a refusal saying which rule it broke."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RefusedError("Only http:// and https:// addresses can be read.")
    if not parsed.hostname:
        raise RefusedError("That does not look like a web address.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise RefusedError("That address could not be found.")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        #  `is_global` rather than `not is_private`: Python calls the
        #  documentation ranges private and leaves carrier-grade NAT out
        #  of them. The same distinction TrustedProxyFix makes, for the
        #  same reason.
        if not ip.is_global:
            raise RefusedError(
                "That address is on this machine or its private network, so "
                "it will not be fetched.")
    return parsed


def fetch(url):
    """(final url, text). Refuses rather than surprises."""
    seen = 0
    current = url
    while True:
        _public_or_refuse(current)
        request = urllib.request.Request(current, headers={
            "User-Agent": AGENT, "Accept": "text/html,text/css,*/*"})
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            response = opener.open(request, timeout=TIMEOUT)
        except _Redirected as hop:
            seen += 1
            if seen > MAX_REDIRECTS:
                raise RefusedError("That address redirects too many times.")
            #  Re-checked at every hop: a public address can redirect to
            #  a private one, and checking only the first is checking the
            #  half an attacker does not control.
            current = urljoin(current, hop.location)
            continue
        except urllib.error.HTTPError as e:
            raise RefusedError("That page answered %s." % e.code)
        except Exception:                                     # noqa: BLE001
            raise RefusedError("That page could not be read — check the address.")
        with response:
            #  Read incrementally rather than trusting Content-Length,
            #  which is a number the other end chose.
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            body = body[:MAX_BYTES]
        return current, body.decode("utf-8", "replace")


class _Redirected(Exception):
    def __init__(self, location):
        self.location = location


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed by us, not by urllib -- so every hop can be
    checked against the same rules the first one was."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(newurl)


# ------------------------------------------------------ reading a look


_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB = re.compile(r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)")
#  Up to the ; or } only. Quotes are part of a family name, not the
#  end of the declaration -- stopping at one read `font-family: "Spectral",
#  Georgia` as nothing at all.
_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_RADIUS = re.compile(r"border-radius\s*:\s*([0-9.]+)(px|rem|em|%)", re.I)
_SHADOW = re.compile(r"box-shadow\s*:\s*([^;}]+)", re.I)
_LINKED_CSS = re.compile(
    r'<link[^>]+rel=["\']?stylesheet["\']?[^>]*href=["\']([^"\']+)', re.I)


def _norm(colour):
    """#abc -> #aabbcc, lowercased. One form, so two spellings of the
    same colour are one colour."""
    value = colour.lower()
    if len(value) == 4:
        return "#" + "".join(c * 2 for c in value[1:])
    return value


def _colours(text):
    """Every colour in the text, most used first."""
    counts = {}
    for match in _HEX.findall(text):
        key = _norm(match)
        counts[key] = counts.get(key, 0) + 1
    for r, g, b in _RGB.findall(text):
        try:
            key = "#%02x%02x%02x" % (int(r), int(g), int(b))
        except ValueError:
            continue
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts, key=lambda c: -counts[c])


def _interesting(colours):
    """Colours that are actually colours.

    Near-black, near-white and flat greys are the page's paper and ink,
    not its palette -- and every site has them, so leaving them in makes
    every extraction come back the same.
    """
    out = []
    for colour in colours:
        try:
            r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            continue
        if max(r, g, b) - min(r, g, b) < 24:
            continue
        if max(r, g, b) < 34 or min(r, g, b) > 226:
            continue
        out.append(colour)
    return out


def _fonts(text):
    """The families a page names, most used first, own names only."""
    counts = {}
    for group in _FAMILY.findall(text):
        first = group.split(",")[0].strip().strip("\"'")
        if not first or first.lower() in (
                "inherit", "initial", "unset", "sans-serif", "serif",
                "monospace", "system-ui", "-apple-system", "cursive"):
            continue
        counts[first] = counts.get(first, 0) + 1
    return sorted(counts, key=lambda f: -counts[f])[:4]


def _shape(text):
    """The nearest corner preset to what this page actually uses."""
    values = []
    for size, unit in _RADIUS.findall(text):
        try:
            px = float(size) * (16 if unit in ("rem", "em") else 1)
        except ValueError:
            continue
        if unit == "%":
            px = 999
        values.append(px)
    if not values:
        return ""
    values.sort()
    typical = values[len(values) // 2]
    if typical >= 100:
        return "pill"
    if typical >= 16:
        return "rounded"
    if typical >= 5:
        return "soft"
    return "sharp"


def _shadow(text):
    """The nearest depth preset."""
    shadows = [s for s in _SHADOW.findall(text) if "none" not in s.lower()]
    if not shadows:
        return "none"
    blurs = []
    for shadow in shadows:
        #  Every length in order, unit or not: "0 4px 28px" is three
        #  offsets and the third is the blur, but the first carries no
        #  unit -- matching only `px` read that shadow as two numbers and
        #  called a 28px blur subtle.
        head = shadow.split("rgb")[0].split("#")[0]
        #  No word-boundary escape here on purpose: a "\b" written into
        #  this file has arrived as a literal BACKSPACE character more
        #  than once, and a regex asking for a backspace matches
        #  nothing -- silently. It is not needed: the numbers are
        #  separated by spaces already.
        numbers = re.findall(r"(-?[0-9.]+)(?:px|rem|em)?", head)
        if len(numbers) >= 3:
            try:
                blurs.append(abs(float(numbers[2])))
            except ValueError:
                pass
    if not blurs:
        return "subtle"
    blurs.sort()
    typical = blurs[len(blurs) // 2]
    return "floating" if typical >= 24 else ("raised" if typical >= 8 else "subtle")


def signals(url):
    """What a page's look is made of. Never what it says.

    Returns colours, font names, a corner preset and a depth preset --
    and a note saying where they came from, because a value that arrived
    from somewhere else should say so on the screen it appears on.
    """
    final, html = fetch(url)
    text = html
    #  Stylesheets too: a modern page keeps almost nothing in its markup,
    #  so reading only the HTML reads almost nothing. Capped, and each
    #  one goes through the same address rules.
    for href in _LINKED_CSS.findall(html)[:MAX_STYLESHEETS]:
        try:
            _, css = fetch(urljoin(final, href))
        except RefusedError:
            continue
        text += css

    palette = _interesting(_colours(text))[:3]
    return {
        "source": final,
        "colours": palette,
        "fonts": _fonts(text),
        "shape": _shape(text),
        "shadow": _shadow(text),
        #  Said plainly on the screen, because somebody handing over a
        #  competitor's address is entitled to know exactly what was
        #  taken from it.
        "note": ("Colours, typefaces, corners and depth only. None of that "
                 "page's words, pictures or layout were read or kept."),
    }
