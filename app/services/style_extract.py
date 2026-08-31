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
            "User-Agent": AGENT, "Accept": "text/html,text/css,*/*",
            #  Asked for, and then actually undone below. A great many
            #  servers compress whether or not you ask -- python.org
            #  does -- and reading a gzip stream as text gives binary
            #  noise that parses as no colours and no stylesheets, which
            #  looks exactly like a page that simply had none.
            "Accept-Encoding": "gzip, deflate"})
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
            encoding = (response.headers.get("Content-Encoding") or "").lower()
        if len(body) > MAX_BYTES:
            body = body[:MAX_BYTES]
        return current, _decoded(body, encoding)


def _decoded(body, encoding):
    """The response as text, whatever it arrived compressed as.

    A truncated stream is normal here -- the byte cap cuts mid-block on
    purpose -- so a decompression that fails part way keeps what it got
    rather than throwing the lot away. Half a stylesheet still names
    colours.
    """
    if "gzip" in encoding:
        import gzip
        import zlib
        try:
            body = gzip.decompress(body)
        except Exception:                                     # noqa: BLE001
            try:
                body = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(body)
            except Exception:                                 # noqa: BLE001
                pass
    elif "deflate" in encoding:
        import zlib
        try:
            body = zlib.decompressobj().decompress(body)
        except Exception:                                     # noqa: BLE001
            pass
    return body.decode("utf-8", "replace")


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
#  The two ways colours are actually written now. Without these, a site
#  built on Tailwind v4 or anything using hsl() returns no colours at
#  all -- and returns them silently.
_HSL = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?[,\s]+([\d.]+)%[,\s]+([\d.]+)%", re.I)
_OKLCH = re.compile(r"oklch\(\s*([\d.]+)%?[,\s]+([\d.]+)[,\s]+([\d.]+)", re.I)
#  Up to the ; or } only. Quotes are part of a family name, not the
#  end of the declaration -- stopping at one read `font-family: "Spectral",
#  Georgia` as nothing at all.
_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_RADIUS = re.compile(r"border-radius\s*:\s*([0-9.]+)(px|rem|em|%)", re.I)
_SHADOW = re.compile(r"box-shadow\s*:\s*([^;}]+)", re.I)
#  Any <link> that IS a stylesheet and HAS an href, in either order.
#  It used to require rel before href, which is an assumption about how
#  somebody wrote their markup -- and python.org writes href first, so it
#  read zero stylesheets from a perfectly ordinary page and returned
#  nothing at all.
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)', re.I)


def _stylesheet_hrefs(html):
    """Every stylesheet a page links to, whatever order it wrote the
    attributes in."""
    out = []
    for tag in _LINK_TAG.findall(html):
        if "stylesheet" not in tag.lower():
            continue
        href = _HREF.search(tag)
        if href:
            out.append(href.group(1))
    return out


def _hex(r, g, b):
    return "#%02x%02x%02x" % (max(0, min(255, int(round(r)))),
                              max(0, min(255, int(round(g)))),
                              max(0, min(255, int(round(b)))))


def _from_hsl(h, s_, l_):
    """hsl() as it is actually written today, degrees and percentages."""
    h = (h % 360) / 360.0
    s_, l_ = s_ / 100.0, l_ / 100.0
    if s_ <= 0:
        v = l_ * 255
        return _hex(v, v, v)

    def channel(t):
        t = t % 1.0
        q = l_ * (1 + s_) if l_ < 0.5 else l_ + s_ - l_ * s_
        p = 2 * l_ - q
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    return _hex(channel(h + 1 / 3) * 255, channel(h) * 255, channel(h - 1 / 3) * 255)


def _from_oklch(light, chroma, hue):
    """oklch() as sRGB.

    Worth the arithmetic rather than skipping: Tailwind v4 and everything
    built on it writes colours this way, so a reader that only knows hex
    and rgb() returns NOTHING from a large and growing share of modern
    sites -- silently, which is the worst way to return nothing.
    """
    import math
    h = math.radians(hue)
    a, b = chroma * math.cos(h), chroma * math.sin(h)
    l_ = (light + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (light - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (light - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    def gamma(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

    return _hex(gamma(r) * 255, gamma(g) * 255, gamma(bl) * 255)


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
            key = _hex(int(r), int(g), int(b))
        except ValueError:
            continue
        counts[key] = counts.get(key, 0) + 1
    for h, sat, light in _HSL.findall(text):
        try:
            key = _from_hsl(float(h), float(sat), float(light))
        except (ValueError, ZeroDivisionError):
            continue
        counts[key] = counts.get(key, 0) + 1
    for light, chroma, hue in _OKLCH.findall(text):
        try:
            value = float(light)
            #  oklch() takes L as 0-1 or as a percentage.
            key = _from_oklch(value / 100 if value > 1 else value,
                              float(chroma), float(hue))
        except (ValueError, OverflowError):
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


_VAR_DEF = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")


def _fonts(text):
    """The families a page names, most used first, own names only.

    A `var(--font-body)` is not a typeface: it is a name for one, and
    showing it to an owner as "the typeface we found" is showing them
    somebody else's variable. Resolved where the page defines it in the
    CSS we read, and dropped when it does not -- which is what
    tailwindcss.com and stripe.com were coming back as.
    """
    variables = {}
    for name, value in _VAR_DEF.findall(text):
        variables.setdefault(name, value.strip())

    def resolve(value, depth=0):
        value = value.strip()
        if depth > 3 or not value.lower().startswith("var("):
            return value
        inside = value[4:].split(")")[0]
        name = inside.split(",")[0].strip()
        if name in variables:
            return resolve(variables[name], depth + 1)
        #  A fallback inside the var() is still a real family.
        if "," in inside:
            return inside.split(",", 1)[1].strip()
        return ""

    counts = {}
    for group in _FAMILY.findall(text):
        first = resolve(group.split(",")[0]).split(",")[0].strip().strip("\"' ")
        if first.lower().startswith("var("):
            continue
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
    for href in _stylesheet_hrefs(html)[:MAX_STYLESHEETS]:
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
