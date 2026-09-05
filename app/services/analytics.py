"""Visitor stats: how many people, when, where from -- kept privately.

Two deliberate choices, both about privacy:

  * **No raw IP is ever stored.** A visit is reduced to (day, country,
    page) and counted; the address that produced the country is used in
    memory and thrown away. So there is no log of who visited, only how
    many, from where, to what -- which is what a stats screen needs and
    the most a GDPR-minded owner should keep.
  * **The country is worked out on THIS server**, from a small offline
    database bundled with the app (data/ip-country-ipv4.bin, a CC0
    IP->country set). Nothing about a visitor is sent to a third party --
    the same reason the fonts are self-hosted. A reverse proxy that
    already did the lookup (Cloudflare's CF-IPCountry and friends) is
    trusted when present, which also covers IPv6.

The store is an AGGREGATE, upserted: one row per (day, country, page)
with a hit count, so it stays small no matter the traffic and holds
nothing that identifies anyone.
"""
import os
import sys
import array
import struct
import bisect
import ipaddress

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ip-country-ipv4.bin")
_geo = None  # (starts, ends, ccs) loaded once

#  Headers a reverse proxy sets with a country it worked out itself. Read
#  when present -- a proxy that fronts THIS deployment is the intended
#  source, and it covers IPv6, which the bundled IPv4 table does not.
#
#  Note the trust is UNCONDITIONAL: unlike X-Forwarded-*, these are not
#  stripped from an untrusted peer (TrustedProxyFix only touches the
#  forwarded set), so on an install exposed directly with no proxy a
#  visitor could send their own CF-IPCountry. That is accepted on
#  purpose: the only thing it can affect is which bucket an anonymous
#  visit is counted in (the value is gated to two letters below, so
#  nothing but a country code can get through), and a stats aggregate is
#  not a security boundary. A proxy-fronted install -- where these
#  headers are worth having -- is exactly where they are trustworthy.
_PROXY_COUNTRY_HEADERS = ("CF-IPCountry", "X-Country-Code", "X-Geo-Country")


def _load():
    global _geo
    if _geo is not None:
        return _geo
    try:
        with open(_DB_PATH, "rb") as f:
            n = struct.unpack("<I", f.read(4))[0]
            starts = array.array("I"); starts.frombytes(f.read(n * 4))
            ends = array.array("I"); ends.frombytes(f.read(n * 4))
            ccs = f.read(n * 2)
        if sys.byteorder != "little":
            starts.byteswap(); ends.byteswap()
        _geo = (starts, ends, ccs)
    except (OSError, struct.error):
        _geo = (array.array("I"), array.array("I"), b"")  # no DB -> everyone Unknown
    return _geo


def _country_for_ipv4(ip_int):
    starts, ends, ccs = _load()
    i = bisect.bisect_right(starts, ip_int) - 1
    if i >= 0 and ends[i] >= ip_int:
        cc = ccs[2 * i:2 * i + 2].decode("ascii", "replace").strip()
        return cc if cc and cc != "ZZ" else None
    return None


def country_for_request(request):
    """A 2-letter country code for the visitor, or None (local address, or
    an IP the offline table doesn't cover). No address is stored or logged
    -- only the code is returned, for the aggregate."""
    for h in _PROXY_COUNTRY_HEADERS:
        v = (request.headers.get(h) or "").strip().upper()
        if len(v) == 2 and v.isalpha() and v not in ("XX", "T1"):
            return v
    ip = (request.remote_addr or "").strip()
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version != 4 or addr.is_private or addr.is_loopback or addr.is_reserved:
        return None
    return _country_for_ipv4(int(addr))


#  Display: a flag emoji from the two letters (regional indicators), plus
#  the code -- no country-name table to keep in step. "ZZ" is the store's
#  stand-in for local/unknown.
def flag(cc):
    cc = (cc or "").upper()
    if len(cc) == 2 and cc.isalpha() and cc != "ZZ":
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)
    return "🏳"


def label(cc):
    cc = (cc or "ZZ").upper()
    if cc == "ZZ":
        return "🏳 Local / unknown"
    return "%s %s" % (flag(cc), cc)


# --- recording and reading ------------------------------------------------

_UNKNOWN = "ZZ"


def _norm_path(path):
    path = (path or "/").split("?", 1)[0].split("#", 1)[0] or "/"
    return path[:200]


def record_visit(db, path, country):
    """Count one page view: +1 on (today, country, page). Never a raw IP,
    never a timestamp finer than the day. Best-effort -- a stats write must
    never break a page, so the caller wraps this."""
    day = __import__("datetime").date.today().isoformat()
    cc = (country or _UNKNOWN).upper()[:2]
    db.execute(
        "INSERT INTO visit_stats (day, country, path, hits) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(day, country, path) DO UPDATE SET hits = hits + 1",
        (day, cc, _norm_path(path)))
    db.commit()


def _since(days):
    import datetime
    return (datetime.date.today() - datetime.timedelta(days=max(1, days) - 1)).isoformat()


def summary(db, days=30):
    """Everything the Visitors screen shows, for the last `days` days:
    total, a per-day series (oldest first, gaps filled with 0), the top
    countries and the top pages."""
    import datetime
    start = _since(days)
    total = db.execute("SELECT COALESCE(SUM(hits), 0) n FROM visit_stats WHERE day >= ?",
                       (start,)).fetchone()["n"]
    per_day = {r["day"]: r["n"] for r in db.execute(
        "SELECT day, SUM(hits) n FROM visit_stats WHERE day >= ? GROUP BY day", (start,)).fetchall()}
    series = []
    d0 = datetime.date.fromisoformat(start)
    for i in range(days):
        d = (d0 + datetime.timedelta(days=i)).isoformat()
        series.append({"day": d, "hits": per_day.get(d, 0)})
    countries = [dict(r) for r in db.execute(
        "SELECT country, SUM(hits) hits FROM visit_stats WHERE day >= ? "
        "GROUP BY country ORDER BY hits DESC LIMIT 12", (start,)).fetchall()]
    for c in countries:
        c["label"] = label(c["country"])
    pages = [dict(r) for r in db.execute(
        "SELECT path, SUM(hits) hits FROM visit_stats WHERE day >= ? "
        "GROUP BY path ORDER BY hits DESC LIMIT 12", (start,)).fetchall()]
    return {"days": days, "total": total, "series": series,
            "countries": countries, "pages": pages,
            "peak": max((s["hits"] for s in series), default=0)}
