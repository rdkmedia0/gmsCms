"""
Third-party providers the site owner connects: payments, scheduling, and
whatever comes later.

One registry, not a settings page per provider. Every provider here is
the same shape — a name, some credentials, a set of capabilities — so a
tool asks "who can take a payment?" rather than naming Stripe, and adding
a provider later is a REGISTRY entry plus a client module, not another
admin screen. Same reasoning that made the AI provider pluggable instead
of hardcoding Open WebUI.

Credentials are encrypted at rest through crypto.py (never written to a
config file, never logged) and stored in the same settings table
everything else uses, under `integration_<provider>_<field>`.

Live/test mode is DERIVED from the key rather than being its own toggle:
a Stripe secret key announces which mode it is in its prefix, and a
separate switch would only create a way for the two to disagree.
"""
import datetime
import zoneinfo
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

from .. import crypto

#  api.cal.com sits behind Cloudflare, which rejects the default Python
#  user-agent outright (403, error code 1010) before the request reaches
#  the API — an error that reads exactly like a bad key. Every outbound
#  call here sends a browser UA for that reason.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

#  Cal.com pins an API version PER ENDPOINT. Sending one endpoint's
#  version to another returns "404 Cannot GET /v2/event-types", which
#  reads as a wrong path rather than a wrong header — so this map is the
#  difference between a working call and an hour of confusion.
CALCOM_API_BASE = "https://api.cal.com/v2"
CALCOM_VERSIONS = {
    "/event-types": "2024-06-14",
    "/slots": "2024-09-04",
    "/bookings": "2026-02-25",
}
CALCOM_DEFAULT_VERSION = "2024-06-14"

STRIPE_API_BASE = "https://api.stripe.com/v1"


PROVIDERS = {
    "stripe": {
        "name": "Stripe",
        "icon": "💳",
        "capabilities": ("payments",),
        "blurb": "Takes the payment on Stripe's own checkout page, so no card details ever reach this site.",
        "docs": "https://dashboard.stripe.com/apikeys",
        "fields": (
            {
                "key": "secret_key",
                "label": "Secret key",
                "secret": True,
                "hint": "Starts sk_test_ for testing or sk_live_ for real payments — the mode is read from this.",
                "placeholder": "sk_test_…",
            },
            {
                "key": "webhook_secret",
                "label": "Webhook signing secret",
                "secret": True,
                "hint": "From the webhook endpoint you add in Stripe. Payments are only confirmed by a signed webhook, never by the browser coming back.",
                "placeholder": "whsec_…",
            },
        ),
    },
    "calcom": {
        "name": "Cal.com",
        "icon": "📅",
        "capabilities": ("scheduling",),
        "blurb": "Owns availability, bookings, reminders and the meeting link. This site only reads slots and creates bookings.",
        "docs": "https://app.cal.com/settings/developer/api-keys",
        "fields": (
            {
                "key": "api_key",
                "label": "API key",
                "secret": True,
                "hint": "A personal API key is enough — the paid Platform tier is only for managing other people's calendars.",
                "placeholder": "cal_live_…",
            },
        ),
    },
}


def _setting_key(provider, field):
    return f"integration_{provider}_{field}"


def get_provider_settings(db, provider):
    """Every field for one provider, decrypted. Missing fields come back
    as empty strings so callers can treat "unset" and "blank" alike."""
    spec = PROVIDERS.get(provider)
    if not spec:
        return {}
    keys = [_setting_key(provider, f["key"]) for f in spec["fields"]]
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ({})".format(",".join("?" * len(keys))),
        keys,
    ).fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    out = {}
    for field in spec["fields"]:
        stored = raw.get(_setting_key(provider, field["key"]))
        out[field["key"]] = (crypto.decrypt(stored) if field["secret"] else stored) or ""
    return out


def save_provider_settings(db, provider, form):
    """Writes whatever the form supplied. A blank secret means "leave the
    stored one alone" — otherwise every save of an unrelated field would
    wipe a key the admin can no longer read back to retype."""
    spec = PROVIDERS.get(provider)
    if not spec:
        return
    for field in spec["fields"]:
        value = (form.get(field["key"]) or "").strip()
        if field["secret"] and not value:
            continue
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_setting_key(provider, field["key"]), crypto.encrypt(value) if field["secret"] else value),
        )
    db.commit()


def clear_provider(db, provider):
    spec = PROVIDERS.get(provider)
    if not spec:
        return
    for field in spec["fields"]:
        db.execute("DELETE FROM settings WHERE key = ?", (_setting_key(provider, field["key"]),))
    db.commit()


def record_test(db, provider, ok):
    """Remember whether the last real call to this provider worked.

    Kept so a badge can say "Connected" only when something actually
    connected. Cleared rather than set to 0 on failure: absence reads as
    "not verified", which is the honest state for a key that has never
    been tried.
    """
    key = "%s_verified" % provider
    if ok:
        db.execute("INSERT INTO settings (key, value) VALUES (?, '1') "
                   "ON CONFLICT(key) DO UPDATE SET value = '1'", (key,))
    else:
        db.execute("DELETE FROM settings WHERE key = ?", (key,))


def is_verified(db, provider):
    """Whether a real call to this provider has succeeded."""
    row = db.execute("SELECT value FROM settings WHERE key = ?",
                     ("%s_verified" % provider,)).fetchone()
    return bool(row and row["value"] == "1")


def is_configured(db, provider):
    """Configured means the provider could actually be called — every
    field it needs is present, not merely that the row exists."""
    settings = get_provider_settings(db, provider)
    spec = PROVIDERS.get(provider)
    if not spec or not settings:
        return False
    if provider == "stripe":
        return bool(settings.get("secret_key"))
    return all(settings.get(f["key"]) for f in spec["fields"])


def providers_with(db, capability):
    """Which configured providers can do a thing — the question a tool
    asks instead of naming a provider."""
    return [
        key for key, spec in PROVIDERS.items()
        if capability in spec["capabilities"] and is_configured(db, key)
    ]


def stripe_mode(db):
    """"test", "live", or "" — read from the key's own prefix so the badge
    in the admin can never disagree with what will actually be charged."""
    key = get_provider_settings(db, "stripe").get("secret_key") or ""
    if key.startswith("sk_live_"):
        return "live"
    if key.startswith("sk_test_"):
        return "test"
    return ""


#  Prefix on an error that never reached the provider. Ugly, and the
#  alternative is a third return value threaded through every call site.
UNREACHABLE = "[could-not-reach] "


def _why_no_dns():
    """The one cause of a name lookup failing that this app can identify.

    A container's /etc/resolv.conf is copied from its host, mode and all.
    A host that has tightened it to 0640 hands the container a resolver
    config the app's own unprivileged user cannot read -- and glibc, given
    an unreadable resolv.conf, does not complain: it falls back to
    127.0.0.1:53, which is nothing here, and every lookup fails with
    "Temporary failure in name resolution".

    Everything else then looks broken for no reason -- payments, bookings,
    email -- and every test in the container passes, because anyone
    debugging runs as root and root can read the file whatever its mode.
    """
    path = "/etc/resolv.conf"
    try:
        if os.path.exists(path) and not os.access(path, os.R_OK):
            mode = oct(os.stat(path).st_mode & 0o777)[2:]
            return (" The cause is on this machine: %s is mode %s and cannot be read by "
                    "the user this app runs as (uid %d), so no name can be looked up. "
                    "Run: chmod 644 %s on the host, then restart the container."
                    % (path, mode, os.getuid(), path))
    except OSError:
        pass
    return ""


def explain(error, name="the provider"):
    """Any provider error, phrased for a person.

    An error that never reached the provider carries a marker so callers
    can tell "it said no" from "nothing answered". The marker is internal
    and must never be read by anybody, so every surface that shows an
    error goes through here; anything else is returned unchanged, since
    most callers already have their own sentence to put it in.
    """
    if error and error.startswith(UNREACHABLE):
        return (f"could not reach {name} at all — this is a network problem "
                f"on the machine running this site, not a problem with your key "
                f"({error[len(UNREACHABLE):]})")
    return error


def _reachability(error, name):
    """The human half of an error: what happened, and whose problem it is."""
    if error.startswith(UNREACHABLE):
        detail = error[len(UNREACHABLE):]
        return ("Could not reach %s at all, so the key was never tested. That is a "
                "network problem on the machine running this site, not a problem "
                "with your key — %s%s" % (name, detail, _why_no_dns()))
    if error.startswith(("401", "403")):
        return "%s refused the key — %s" % (name, error)
    return "%s answered with an error — %s" % (name, error)


def _request(url, headers, data=None, method=None, timeout=20):
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", {}).get("message") or parsed.get("message") or detail
        except ValueError:
            pass
        return None, f"{e.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        #  UNREACHABLE: the request never got an answer -- no DNS, no
        #  route, a timeout. Marked so the caller does not report it
        #  as the provider saying no: that is a different problem
        #  with a different fix, and it sends people off to
        #  regenerate a key that was never wrong.
        return None, f"{UNREACHABLE}{type(e).__name__}: {e}"


def stripe_connected(db):
    """Whether this site has a Stripe key at all.

    Asked rather than inferred from an error message: "Stripe isn't
    connected yet" and "Stripe is not answering" are different situations
    and only one of them means the shop has never been set up.
    """
    return bool(get_provider_settings(db, "stripe").get("secret_key"))


def stripe_call(db, path, data=None, method=None):
    key = get_provider_settings(db, "stripe").get("secret_key")
    if not key:
        return None, "Stripe isn't connected yet."
    headers = {
        "Authorization": f"Bearer {key}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return _request(f"{STRIPE_API_BASE}{path}", headers, data=data, method=method)


def calcom_call(db, path, timeout=20):
    key = get_provider_settings(db, "calcom").get("api_key")
    if not key:
        return None, "Cal.com isn't connected yet."
    version = next(
        (v for prefix, v in CALCOM_VERSIONS.items() if path.startswith(prefix)),
        CALCOM_DEFAULT_VERSION,
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "cal-api-version": version,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    return _request(f"{CALCOM_API_BASE}{path}", headers, timeout=timeout)


def test_connection(db, provider):
    """(ok, message) — a real call to the provider, phrased for a human.
    Deliberately reads something the admin will recognise (their own
    products, their own event types) so a pass proves the key reaches the
    right account, not merely that it authenticates."""
    if provider == "stripe":
        data, error = stripe_call(db, "/products?limit=3&active=true")
        if error:
            return False, _reachability(error, "Stripe")
        count = len(data.get("data", []))
        mode = stripe_mode(db)
        which = "test mode" if mode == "test" else "LIVE mode"
        if count == 0:
            return True, f"Connected in {which}, but this account has no active products yet."
        names = ", ".join(p.get("name", "?") for p in data["data"][:3])
        return True, f"Connected in {which}. Found {count} product(s): {names}"
    if provider == "calcom":
        data, error = calcom_call(db, "/event-types")
        if error:
            return False, _reachability(error, "Cal.com")
        payload = data.get("data", data)
        groups = payload if isinstance(payload, list) else payload.get("eventTypeGroups", []) or []
        types = []
        for entry in groups:
            if isinstance(entry, dict) and "eventTypes" in entry:
                types.extend(entry["eventTypes"])
            else:
                types.append(entry)
        if not types:
            return True, "Connected, but this account has no event types yet."
        titles = ", ".join(str(t.get("title", "?")) for t in types[:3])
        return True, f"Connected. Found {len(types)} event type(s): {titles}"
    return False, "Unknown provider."


_CATALOGUE_CACHE = {"at": 0.0, "items": None, "error": None}
CATALOGUE_TTL_S = 60


def stripe_catalogue_cached(db, force=False):
    """The catalogue as the editor sees it. Cached briefly because the
    config form is re-rendered on every page load in edit mode, and an
    admin nudging a section should not cost a round trip to Stripe each
    time. The Refresh button passes force=True."""
    now = time.time()
    if not force and _CATALOGUE_CACHE["items"] is not None and now - _CATALOGUE_CACHE["at"] < CATALOGUE_TTL_S:
        return _CATALOGUE_CACHE["items"], _CATALOGUE_CACHE["error"]
    items, error = stripe_catalogue(db)
    _CATALOGUE_CACHE.update({"at": now, "items": items, "error": error})
    return items, error


def stripe_catalogue(db, limit=100):
    """(items, error) — the account's real, active prices, shaped for a
    dropdown. This is the "no pasting IDs" rule: an admin picks a product
    they recognise, and the id never appears in the UI at all.

    Prices are expanded with their product so one call fills the list;
    a product with several prices appears once per price, because a price
    is what actually gets charged.
    """
    data, error = stripe_call(db, f"/prices?active=true&limit={limit}&expand[]=data.product")
    if error:
        return [], error
    items = []
    for price in data.get("data", []):
        product = price.get("product") or {}
        if isinstance(product, str) or product.get("active") is False:
            continue
        amount = price.get("unit_amount")
        currency = (price.get("currency") or "").upper()
        if amount is None:
            label_price = "customer chooses"
        else:
            label_price = f"{amount / 100:.2f} {currency}"
        recurring = price.get("recurring") or {}
        if recurring:
            label_price += f" / {recurring.get('interval', 'period')}"
        items.append({
            "price_id": price.get("id"),
            "product_id": product.get("id"),
            "name": product.get("name") or "(unnamed)",
            "description": product.get("description") or "",
            "image": (product.get("images") or [None])[0],
            "amount": amount,
            "currency": currency,
            "label": f"{product.get('name') or '(unnamed)'} — {label_price}",
        })
    items.sort(key=lambda i: i["name"].lower())
    return items, None


#  Where a shop will post things. Stripe needs the countries listed
#  explicitly, so these are presets rather than a free-text box — an owner
#  picks where they ship, not a list of ISO codes.
_EUROPE = [
    "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GB", "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT",
    "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
]
SHIPPING_ZONES = {
    "ch": ("Switzerland and Liechtenstein", ["CH", "LI"]),
    "europe": ("Europe", _EUROPE),
    "uk": ("United Kingdom", ["GB"]),
    "usa": ("United States", ["US"]),
    "north-america": ("North America", ["US", "CA", "MX"]),
    "wide": ("Europe and the main overseas markets", _EUROPE + [
        "AE", "AU", "BR", "CA", "HK", "IL", "JP", "KR", "MX", "NZ", "SG", "US", "ZA",
    ]),
    "worldwide": ("Worldwide", _EUROPE + [
        "AE", "AR", "AU", "BR", "CA", "CL", "CN", "HK", "ID", "IL", "IN", "JP",
        "KR", "MX", "MY", "NZ", "PH", "SA", "SG", "TH", "TR", "US", "VN", "ZA",
    ]),
}


def stripe_checkout_session(db, items, success_url, cancel_url, shipping=None):
    """(url, error) for a hosted checkout page.

    Everything about the payment happens on Stripe's side: card entry,
    3-D Secure, wallets, tax. This site only says what is being bought and
    where to come back to, which is what keeps it out of PCI scope
    entirely.

    `items` is [(price_id, quantity)] — one for a Buy button, several for
    a basket, the same call either way. `shipping`, when a basket holds
    something that has to be posted, carries the zone to collect an
    address for and the rate to charge; it is built from settings rather
    than from anything the page sent, because a delivery charge in the
    page is a number a visitor can edit.
    """
    items = [(pid, max(1, int(qty or 1))) for pid, qty in items if pid]
    if not items:
        return None, "There is nothing to buy."
    #  A recurring price must be checked out in subscription mode; Stripe
    #  rejects the whole session otherwise, with an error a site visitor
    #  would see as a dead end. The price itself says which it is, so the
    #  mode is read from Stripe rather than assumed here.
    mode = "payment"
    for price_id, _ in items:
        price, price_error = stripe_call(db, f"/prices/{urllib.parse.quote(price_id)}")
        if price_error:
            return None, f"That product could not be read from Stripe — {price_error}"
        if price.get("recurring"):
            mode = "subscription"
    data = {
        "mode": mode,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    for n, (price_id, quantity) in enumerate(items):
        data[f"line_items[{n}][price]"] = price_id
        data[f"line_items[{n}][quantity]"] = quantity
    if mode == "payment":
        #  Stripe collects the email, and that email is the ledger key on
        #  this side — so it must always be asked for, even though the
        #  buyer never makes an account. Subscription mode always creates a
        #  customer, and rejects the parameter as redundant.
        data["customer_creation"] = "always"
        #  A receipt is not an invoice. Stripe emails a receipt only if
        #  the account has that switched on, and a receipt is not a
        #  numbered document somebody can put through their books. Asking
        #  for an invoice makes Stripe produce and send a real one, with
        #  the seller's own business details on it, at no cost to this
        #  app -- which has no business generating tax documents itself.
        #  Subscription mode invoices every cycle already, and rejects
        #  this parameter as redundant.
        data["invoice_creation[enabled]"] = "true"
    if shipping:
        for n, code in enumerate(shipping["countries"]):
            data[f"shipping_address_collection[allowed_countries][{n}]"] = code
        #  Each priced service is one option the buyer picks on Stripe's
        #  page -- which is how destination is handled, since Stripe cannot
        #  re-price from the address typed there. No options (a weight no
        #  band covers) still collects an address so the owner can fulfil,
        #  but charges nothing rather than dead-ending the sale.
        for i, opt in enumerate(shipping.get("options", [])):
            rate = f"shipping_options[{i}][shipping_rate_data]"
            data[f"{rate}[type]"] = "fixed_amount"
            data[f"{rate}[fixed_amount][amount]"] = int(opt["amount"])
            data[f"{rate}[fixed_amount][currency]"] = (opt.get("currency") or "chf").lower()
            data[f"{rate}[display_name]"] = opt["label"]
    data.update({
        #  Let Stripe work out VAT rather than us. Silently ignored on
        #  accounts that have not enabled Stripe Tax.
        "automatic_tax[enabled]": "true",
    })
    result, error = stripe_call(db, "/checkout/sessions", data=data, method="POST")
    if error:
        #  Retry without automatic tax: an account that has not set up
        #  Stripe Tax rejects the whole session rather than ignoring the
        #  flag, and a shop that cannot sell is worse than one that has to
        #  put tax in the price.
        if "automatic_tax" in str(error) or "Tax" in str(error):
            data.pop("automatic_tax[enabled]", None)
            result, error = stripe_call(db, "/checkout/sessions", data=data, method="POST")
        if error:
            return None, error
    return result.get("url"), None


#  Events this site actually acts on. Subscribing to everything would mean
#  Stripe delivering hundreds of events we ignore, and every ignored
#  delivery is still a request to verify and answer.
WEBHOOK_EVENTS = (
    "checkout.session.completed",
    "charge.refunded",
    "checkout.session.async_payment_failed",
    #  A subscription renewing. Without these two, a monthly price
    #  granting 10 sessions grants them once at the first payment and
    #  never again -- and the handler for them would never run, because
    #  Stripe only sends what it has been asked for. An endpoint created
    #  before these were added does not have them: see
    #  webhook_missing_events, which is why a site that has been selling
    #  memberships for a month is told rather than left to find out.
    "invoice.paid",
    "invoice.payment_failed",
)


def webhook_missing_events(db, url):
    """(missing, error) -- events this site acts on that Stripe is not
    sending to it.

    An endpoint registered before a new event was added keeps its
    original list forever: Stripe has no reason to update it and this app
    cannot silently change somebody's Stripe account. So the honest thing
    is to look, and say. Otherwise a feature that depends on a new event
    is a feature that works on new installs and quietly does nothing on
    every existing one -- which is the worst kind of release.
    """
    endpoints, error = stripe_webhooks(db)
    if error:
        return [], error
    for endpoint in endpoints:
        if endpoint.get("url") != url:
            continue
        have = set(endpoint.get("enabled_events") or [])
        #  Stripe writes "*" when an endpoint takes everything.
        if "*" in have:
            return [], None
        return [e for e in WEBHOOK_EVENTS if e not in have], None
    return [], None


def stripe_webhooks(db):
    """(endpoints, error) — what this Stripe account already sends, so the
    panel can show whether this site is among them rather than making the
    admin go and look."""
    data, error = stripe_call(db, "/webhook_endpoints?limit=20")
    if error:
        return [], error
    return data.get("data", []), None


def stripe_create_webhook(db, url):
    """Registers this site with Stripe and stores the signing secret.

    Done over the API rather than by hand because Stripe returns the
    secret exactly ONCE, at creation — a copy-paste step is therefore also
    the step where a mistyped secret produces a webhook that fails
    signature verification with no obvious cause.

    An endpoint already pointing at this URL is reused rather than
    duplicated: Stripe would happily deliver every event twice.
    """
    if not url or not url.startswith("https://"):
        return False, "Stripe only delivers to an https address, so this site needs its public URL first."
    existing, error = stripe_webhooks(db)
    if error:
        return False, f"Couldn't read existing webhooks — {error}"
    for endpoint in existing:
        if endpoint.get("url") == url:
            return False, (
                "Stripe already has a webhook for this address. Its signing secret is only "
                "shown once, at creation — delete it in Stripe and create it again here, or "
                "paste the secret in by hand."
            )
    data = {"url": url, "api_version": "2024-06-20", "description": "Website orders"}
    for i, event in enumerate(WEBHOOK_EVENTS):
        data[f"enabled_events[{i}]"] = event
    result, error = stripe_call(db, "/webhook_endpoints", data=data, method="POST")
    if error:
        return False, f"Stripe refused to create the webhook — {error}"
    secret = result.get("secret")
    if not secret:
        return False, "Stripe created the webhook but returned no signing secret."
    save_provider_settings(db, "stripe", {"secret_key": "", "webhook_secret": secret})
    return True, f"Webhook created and its signing secret saved. Stripe will now confirm payments to {url}"


def calcom_event_types(db):
    """(items, error) — the account's bookable event types, for a
    dropdown. Same rule as the Stripe catalogue: an admin picks a meeting
    they recognise, never an id."""
    data, error = calcom_call(db, "/event-types")
    if error:
        return [], error
    payload = data.get("data", data)
    groups = payload if isinstance(payload, list) else payload.get("eventTypeGroups", []) or []
    types = []
    for entry in groups:
        if isinstance(entry, dict) and "eventTypes" in entry:
            types.extend(entry["eventTypes"])
        else:
            types.append(entry)
    items = []
    for t in types:
        if not isinstance(t, dict) or not t.get("id"):
            continue
        minutes = t.get("lengthInMinutes") or t.get("length")
        items.append({
            "id": str(t["id"]),
            "title": t.get("title") or "(untitled)",
            "minutes": minutes,
            "label": f"{t.get('title') or '(untitled)'}" + (f" — {minutes} min" if minutes else ""),
        })
    items.sort(key=lambda i: i["title"].lower())
    return items, None


def calcom_slots(db, event_type_id, start, end, timezone="UTC"):
    """(slots_by_day, error) — real free times from Cal.com.

    We never work out availability ourselves. Cal.com already knows the
    working hours, the buffers, the existing bookings, the timezone and
    daylight saving; reimplementing any of that would be inventing a
    scheduler, which is the one thing this design deliberately does not
    do.
    """
    query = urllib.parse.urlencode({
        "eventTypeId": event_type_id,
        "start": start,
        "end": end,
        "timeZone": timezone,
    })
    data, error = calcom_call(db, f"/slots?{query}")
    if error:
        return {}, error
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return {}, None
    out = {}
    for day, slots in payload.items():
        times = []
        for slot in slots or []:
            when = slot.get("start") if isinstance(slot, dict) else slot
            if when:
                times.append(when)
        if times:
            out[day] = times
    return out, None


def _calcom_post(db, path, body, timeout=30):
    """Cal.com takes JSON; `_request` form-encodes because that is what
    Stripe wants. One helper for every Cal.com write rather than each one
    hand-rolling the same headers."""
    key = get_provider_settings(db, "calcom").get("api_key")
    if not key:
        return None, "Cal.com isn't connected."
    version = next(
        (v for prefix, v in CALCOM_VERSIONS.items() if path.startswith(prefix)),
        CALCOM_DEFAULT_VERSION,
    )
    req = urllib.request.Request(
        f"{CALCOM_API_BASE}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "cal-api-version": version,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        try:
            parsed = json.loads(detail)
            detail = (parsed.get("error") or {}).get("message") or parsed.get("message") or detail
        except ValueError:
            pass
        return None, f"{e.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return None, f"{type(e).__name__}: {e}"


def calcom_cancel_booking(db, uid, reason=None):
    """Cancels through Cal.com, which is the only cancellation that
    counts.

    Deleting the event in Google Calendar does NOT reach Cal.com — the
    sync writes one way — so a meeting deleted there stays live in Cal.com
    and the session stays spent while the meeting never happens. Every
    cancel surface in this app therefore goes through this call rather
    than any calendar the booking was mirrored into.
    """
    return _calcom_post(db, f"/bookings/{uid}/cancel",
                        {"cancellationReason": reason or "Cancelled by request"})


def calcom_create_booking(db, event_type_id, start, name, email, timezone="UTC"):
    """(booking, error). Cal.com sends the confirmation and creates the
    meeting link — this site never emails an invitation of its own, which
    is exactly why the scheduler is worth renting rather than building."""
    return _calcom_post(db, "/bookings", {
        "start": start,
        "eventTypeId": int(event_type_id),
        "attendee": {"name": name or "Guest", "email": email, "timeZone": timezone},
    })


WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def slots_calendar(slots_by_day, start_date, days):
    """Lays Cal.com's free times out as a real month grid.

    A flat list of days reads as a form; a calendar reads as a calendar —
    people already know how to use one, and can see at a glance that
    Tuesday is full and Thursday is wide open. The grid covers exactly the
    bookable window (no paging into months that cannot be booked), padded
    to whole weeks so the columns line up under Mon..Sun.
    """
    end = start_date + datetime.timedelta(days=days)
    cursor = start_date - datetime.timedelta(days=start_date.weekday())
    weeks, week = [], []
    while cursor < end or week:
        iso = cursor.isoformat()
        times = list(slots_by_day.get(iso) or [])
        week.append({
            "iso": iso,
            "day": cursor.day,
            "label": cursor.strftime("%A %d %B"),
            "bookable": start_date <= cursor < end,
            "times": times,
        })
        cursor += datetime.timedelta(days=1)
        if len(week) == 7:
            weeks.append(week)
            week = []
    return weeks


def describe_slot(when, timezone=None):
    """"Monday 24 August at 14:00" — what a person needs to read back
    before committing, rather than an ISO timestamp.

    A named timezone CONVERTS the time into that zone; it used to only
    append the name, which meant asking for a Zurich time and being handed
    a UTC one wearing a Zurich label. A booking somebody reads and turns
    up for is the last place to be casual about this.

    An unlabelled time is a hazard of the same kind, so a time in UTC says
    so unless the reader has already been told which zone they are in.
    """
    try:
        parsed = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return when
    if timezone:
        try:
            zone = zoneinfo.ZoneInfo(timezone)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            parsed = parsed.astimezone(zone)
        except Exception:
            #  An unknown zone name, or an image with no tz database. Show
            #  the time as it came rather than pretend it was converted.
            timezone = None
    text = parsed.strftime("%A %d %B at %H:%M")
    if timezone and timezone != "UTC":
        return f"{text} ({timezone})"
    if parsed.tzinfo is not None and parsed.utcoffset() == datetime.timedelta(0):
        return f"{text} UTC"
    return text


def calcom_bookings(db, status="upcoming", take=50):
    """(bookings, error) — what is actually in the diary.

    Read straight from Cal.com rather than kept in a table here. Cal.com
    is already the calendar of record: it holds bookings made through this
    site AND ones made through the owner's own booking page, and it is
    what syncs to their Google or Outlook calendar. A local copy could
    only ever be a stale subset of it.
    """
    data, error = calcom_call(db, f"/bookings?take={int(take)}&status={status}")
    if error:
        return [], error
    items = data.get("data", data) or []
    if not isinstance(items, list):
        items = items.get("bookings", []) or []
    out = []
    for b in items:
        attendees = b.get("attendees") or []
        out.append({
            "uid": b.get("uid"),
            "title": b.get("title") or "Meeting",
            "start": b.get("start"),
            #  The zone the buyer booked in, so the owner reads the same
            #  clock their visitor did rather than a bare UTC time that
            #  looks local and is two hours out in summer.
            "when": describe_slot(b.get("start"),
                                  (attendees[0].get("timeZone") if attendees else None)),
            "status": b.get("status"),
            "name": (attendees[0].get("name") if attendees else None),
            "email": (attendees[0].get("email") if attendees else None),
            "url": f"https://app.cal.com/booking/{b.get('uid')}" if b.get("uid") else None,
        })
    return out, None


def calcom_booking(db, uid):
    """(booking, missing, error) for one booking.

    `missing` is True only for a definite 404 — Cal.com saying this
    booking does not exist. Every other failure leaves it False, because a
    network blip, an expired key or a 500 must never be read as "deleted":
    that would hand sessions back for meetings still sitting in the diary.
    """
    data, error = calcom_call(db, f"/bookings/{uid}")
    if error:
        return None, error.startswith("404"), error
    return data.get("data", data) or {}, False, None


def invalidate_catalogue():
    """Forget the cached catalogue after a write, so the page that just
    changed something shows the change rather than the last minute."""
    _CATALOGUE_CACHE.update({"at": 0.0, "items": None, "error": None})


CURRENCIES = (("chf", "CHF"), ("eur", "EUR"), ("usd", "USD"), ("gbp", "GBP"))

#  What this shop charges in. One setting, because one shop is one
#  currency: it is the default for every new product and the thing a
#  basket refuses to depart from. Nothing here converts anything --
#  conversion and regional detection are separate features.
BASE_CURRENCY_KEY = "base_currency"
DEFAULT_CURRENCY = "chf"


def base_currency(db):
    row = db.execute("SELECT value FROM settings WHERE key = ?",
                     (BASE_CURRENCY_KEY,)).fetchone()
    value = (row["value"] if row else "") or ""
    return value if value in dict(CURRENCIES) else DEFAULT_CURRENCY


def set_base_currency(db, value):
    """(saved, error). Refused rather than coerced: a currency this app
    cannot name is one Stripe would reject at the payment step, which is
    the worst possible moment to find out."""
    value = (value or "").strip().lower()
    if value not in dict(CURRENCIES):
        return None, "That isn't a currency this site can charge in."
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
               (BASE_CURRENCY_KEY, value))
    return value, None


def currencies_in_use(db):
    """Every currency the live catalogue actually prices in.

    Read from Stripe rather than from anything this app stores, because
    Stripe is where a price lives and a product could have been repriced
    there. Sorted so the screen does not shuffle between visits.
    """
    catalogue, error = stripe_catalogue_cached(db)
    if error:
        return [], error
    return sorted({(item.get("currency") or "").lower()
                   for item in catalogue if item.get("currency")}), None
INTERVALS = (("", "One-off payment"), ("month", "Every month"), ("year", "Every year"))


def stripe_create_product(db, name, description="", amount=0, currency="chf",
                          interval="", image_url=None):
    """Creates the product AND its first price in one go. (price_id, error).

    Two objects, because that is how Stripe models it — a product is the
    thing, a price is what it costs — but an owner adding something to
    sell should not have to learn that.
    """
    data = {"name": (name or "").strip()[:250]}
    if not data["name"]:
        return None, "Give the product a name."
    if description:
        data["description"] = description.strip()[:500]
    if image_url:
        data["images[0]"] = image_url
    product, error = stripe_call(db, "/products", data=data, method="POST")
    if error:
        return None, error
    price_id, error = stripe_create_price(db, product["id"], amount, currency, interval)
    invalidate_catalogue()
    return price_id, error


def stripe_create_price(db, product_id, amount, currency="chf", interval="", set_default=True):
    """(price_id, error). Also makes it the product's default price, which
    is what "the price of this thing" means to everyone except Stripe."""
    data = {
        "product": product_id,
        "unit_amount": int(amount),
        "currency": (currency or "chf").lower(),
    }
    if interval:
        data["recurring[interval]"] = interval
    price, error = stripe_call(db, "/prices", data=data, method="POST")
    if error:
        return None, error
    if set_default:
        stripe_call(db, f"/products/{product_id}",
                    data={"default_price": price["id"]}, method="POST")
    invalidate_catalogue()
    return price["id"], None


def stripe_update_product(db, product_id, name=None, description=None, image_url=None):
    """Name, description and picture can be edited in place — unlike the
    price, which Stripe will not let anyone change. See stripe_reprice."""
    data = {}
    if name is not None:
        data["name"] = name.strip()[:250]
    if description is not None:
        data["description"] = description.strip()[:500]
    if image_url is not None:
        data["images[0]"] = image_url
    if not data:
        return True, None
    _, error = stripe_call(db, f"/products/{product_id}", data=data, method="POST")
    invalidate_catalogue()
    return (not error), error


def stripe_reprice(db, product_id, old_price_id, amount, currency="chf", interval=""):
    """Changes what something costs. (new_price_id, error).

    A Stripe price is immutable — once anything has been sold at it, it
    can never be edited, which is deliberate on their part: an invoice
    from last year must still say what it said. So "changing the price" is
    really: make a new price, make it the default, and retire the old one
    so nothing new can be bought at it. Existing subscriptions on the old
    price keep running, which is the correct behaviour and the reason the
    old price is archived rather than deleted.

    The caller has to re-point anything that referred to the old price id
    — see commerce_product_reprice, which moves the fulfilment rule across
    so the new price still delivers whatever the old one did.
    """
    new_id, error = stripe_create_price(db, product_id, amount, currency, interval)
    if error:
        return None, error
    if old_price_id and old_price_id != new_id:
        _, archive_error = stripe_call(db, f"/prices/{old_price_id}",
                                       data={"active": "false"}, method="POST")
        if archive_error:
            #  Not fatal: the new price is live and default. An old price
            #  left active is untidy, not broken.
            current_app.logger.warning("Old price %s not archived: %s", old_price_id, archive_error)
    invalidate_catalogue()
    return new_id, None


def stripe_archive_product(db, product_id, active=False):
    """Stops something being sold without deleting the history of it
    having been. Stripe refuses to delete a product that has ever been
    bought, and it is right to."""
    _, error = stripe_call(db, f"/products/{product_id}",
                           data={"active": "true" if active else "false"}, method="POST")
    invalidate_catalogue()
    return (not error), error


def stripe_products(db, include_inactive=True, limit=100):
    """(products, error) for the manage screen — one entry per product
    (not per price, the way the buying catalogue lists them), each with
    its current default price.
    """
    query = f"/products?limit={limit}&expand[]=data.default_price"
    if not include_inactive:
        query += "&active=true"
    data, error = stripe_call(db, query)
    if error:
        return [], error
    items = []
    for product in data.get("data", []):
        price = product.get("default_price") or {}
        if isinstance(price, str):
            price = {}
        recurring = price.get("recurring") or {}
        items.append({
            "product_id": product.get("id"),
            "price_id": price.get("id"),
            "name": product.get("name") or "(unnamed)",
            "description": product.get("description") or "",
            "image": (product.get("images") or [None])[0],
            "amount": price.get("unit_amount"),
            "currency": (price.get("currency") or "").upper(),
            "interval": recurring.get("interval") or "",
            "active": bool(product.get("active")),
        })
    items.sort(key=lambda i: (not i["active"], i["name"].lower()))
    return items, None


def stripe_update_webhook(db, webhook_id, url):
    """Points an existing webhook registration at a new address. (ok, error).

    Used when the site's domain changes. Re-pointing beats deleting and
    recreating, because recreating issues a NEW signing secret — and every
    webhook would fail verification until the new secret was saved, with
    the only symptom being orders quietly not being recorded.
    """
    _, error = stripe_call(db, f"/webhook_endpoints/{webhook_id}",
                           data={"url": url}, method="POST")
    return (not error), (error or f"Now calling back on {url}")
