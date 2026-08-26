"""
Where this site lives, as far as the outside world is concerned.

Any URL that leaves this site — a Stripe return address, the webhook
Stripe calls back on, a link emailed to a buyer, a product picture Stripe
fetches — has to be one that works from somewhere else. `url_for(...,
_external=True)` cannot answer that: it builds from whichever host the
CURRENT request arrived on, so an order email resent from the admin's own
browser at localhost bakes "localhost" into a link the buyer opens on
their phone, and a checkout started from a LAN address sends the buyer
back to an address their network has never heard of.

So the address is configured once, here, and everything outward-facing
reads it from the same place. It is expected to change — a tunnel today, a
real domain later — which is exactly why it is one setting rather than a
value copied into Stripe, into an email template, and into a webhook
registration separately.
"""
import ipaddress
import re
import urllib.parse

SETTING_KEY = "site_public_url"

#  Hosts that mean "this machine" and therefore mean nothing to anyone
#  else. A LAN hostname cannot be detected this way — tlc.example.win
#  looks exactly like a public domain from here — so this catches the
#  obvious cases and the owner is trusted for the rest.
LOCAL_NAMES = {"localhost", "localhost.localdomain", "0.0.0.0", "::1"}

#  A host is letters, digits, dots and hyphens, with an optional port.
#  Without this check a typo like "my new site" parses happily and is
#  saved as an address nothing can ever reach.
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*(:\d{1,5})?$")


def normalize(value):
    """A typed address into one that can be joined to a path.

    People type "example.com", "https://example.com/", and everything in
    between; all three mean the same site.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parts = urllib.parse.urlsplit(value)
    if not parts.netloc or not HOST_RE.match(parts.netloc):
        return ""
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def host_of(value):
    return urllib.parse.urlsplit(normalize(value)).hostname or ""


def is_public_host(value):
    """False for anything that only resolves on this machine or this
    network — the addresses that produce links nobody else can open."""
    host = (host_of(value) or "").lower()
    if not host or host in LOCAL_NAMES or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True  # a name, not an address: assume the owner means it
    return not (address.is_loopback or address.is_private or address.is_link_local)


def public_base(db, fallback=None):
    """The address to build outward-facing links from.

    Three sources, in order of how much they can be trusted to mean it:
    what the owner configured, what the site has actually been reached on
    (learned from admin requests — see remember_detected), and failing
    both, whatever host this request came in on. The last is what makes
    development work; the middle is what means a real deployment never has
    to be told its own address at all.
    """
    row = db.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    configured = normalize(row["value"] if row else "")
    if configured:
        return configured
    learned = detected_base(db)
    if learned:
        return learned
    return normalize(fallback) if fallback else ""


def is_configured(db):
    return bool(public_base(db))


def absolute(db, path, fallback=None):
    """Joins a site-relative path (from url_for) to the public address."""
    base = public_base(db, fallback)
    if not base:
        return path
    return base + (path if path.startswith("/") else "/" + path)


def set_base(db, value):
    """(saved_value, error)."""
    normalized = normalize(value)
    if value and not normalized:
        return None, "That doesn't look like a web address."
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, normalized),
    )
    return normalized, None


DETECTED_KEY = "site_detected_url"


def remember_detected(db, request_base, is_admin):
    """Learns the address this site is actually reached on, so nobody has
    to type it. Returns True if it changed.

    Only from a signed-in admin's own request, and never a local one. The
    Host header is supplied by whoever is talking to us, so learning it
    from any passer-by would let a stranger point every emailed link and
    every Stripe return at a domain of their choosing — a classic
    host-header poisoning, with real money at the end of it. An attacker
    would need the admin's session to reach this, by which point the URL
    is the least of it.

    An explicitly configured address always wins over this; this only
    fills the gap where none was set.
    """
    if not is_admin:
        return False
    base = normalize(request_base)
    if not base or not is_public_host(base):
        return False
    row = db.execute("SELECT value FROM settings WHERE key = ?", (DETECTED_KEY,)).fetchone()
    if row and (row["value"] or "") == base:
        return False
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (DETECTED_KEY, base),
    )
    return True


def detected_base(db):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (DETECTED_KEY,)).fetchone()
    return normalize(row["value"] if row else "")
