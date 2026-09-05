"""Weight-based delivery pricing.

A flat fee is not what a parcel costs. What it costs depends on how heavy
it is, where it is going, and who carries it -- so the owner defines
SERVICES (a carrier + service, tied to a destination zone), each with a
table of weight BANDS, and the price for a basket is looked up from the
total weight of what has to be posted.

Stripe's hosted checkout cannot recalculate a price from the address the
buyer types on Stripe's own page -- the session is already made by then.
So destination is handled the way it CAN be: every applicable service
becomes an option the buyer PICKS at checkout, already priced from the
basket's weight. One service is one option, simply applied; several are a
short list to choose from, each naming its carrier and region.

Shipped with editable Swiss Post PostPac presets -- a starting point, not
the truth, because tariffs change -- and more carriers can be added.

This module takes `db` and plain arguments and never touches Flask; the
`integrations` module is passed in (for zones / base currency) rather than
imported, the same way cart.py avoids a cycle.
"""

#  Weight is stored in GRAMS; amounts in the shop's smallest currency unit,
#  the way Stripe counts. A band applies to any parcel at or under its
#  ceiling, and the CHEAPEST covering band wins (they are read in order).

#  Stripe Checkout accepts at most a handful of shipping options; offering
#  more would be a wall of near-identical lines anyway.
MAX_OPTIONS = 5


def list_services(db, enabled_only=False):
    """Every service with its weight bands attached, in display order."""
    sql = "SELECT * FROM shipping_services"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY sort_order, id"
    services = [dict(r) for r in db.execute(sql).fetchall()]
    for s in services:
        s["rates"] = [
            dict(r) for r in db.execute(
                "SELECT * FROM shipping_rates WHERE service_id = ? ORDER BY up_to_g",
                (s["id"],),
            ).fetchall()
        ]
    return services


def get_service(db, service_id):
    row = db.execute(
        "SELECT * FROM shipping_services WHERE id = ?", (service_id,)
    ).fetchone()
    if not row:
        return None
    s = dict(row)
    s["rates"] = [
        dict(r) for r in db.execute(
            "SELECT * FROM shipping_rates WHERE service_id = ? ORDER BY up_to_g",
            (service_id,),
        ).fetchall()
    ]
    return s


def rate_for_weight(rates, weight_g):
    """The price for this weight, or None when it is heavier than every
    band. `rates` is a service's own list (already ordered by ceiling)."""
    for r in sorted(rates, key=lambda x: x["up_to_g"]):
        if weight_g <= r["up_to_g"]:
            return r["amount"]
    return None


def max_band(rates):
    """The heaviest ceiling a service can carry, or 0 if it has no bands."""
    return max((r["up_to_g"] for r in rates), default=0)


#  ---- editing -------------------------------------------------------------

def create_service(db, name, carrier="", zone="ch"):
    order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM shipping_services"
    ).fetchone()[0]
    cur = db.execute(
        "INSERT INTO shipping_services (name, carrier, zone, enabled, sort_order) "
        "VALUES (?, ?, ?, 1, ?)",
        (name.strip()[:120] or "Delivery", carrier.strip()[:80], zone, order),
    )
    return cur.lastrowid


def update_service(db, service_id, name=None, carrier=None, zone=None, enabled=None):
    sets, args = [], []
    if name is not None:
        sets.append("name = ?"); args.append(name.strip()[:120] or "Delivery")
    if carrier is not None:
        sets.append("carrier = ?"); args.append(carrier.strip()[:80])
    if zone is not None:
        sets.append("zone = ?"); args.append(zone)
    if enabled is not None:
        sets.append("enabled = ?"); args.append(1 if enabled else 0)
    if not sets:
        return
    args.append(service_id)
    db.execute("UPDATE shipping_services SET %s WHERE id = ?" % ", ".join(sets), args)


def delete_service(db, service_id):
    #  A product may name this service; clearing the reference leaves the
    #  product priced by whatever services remain, rather than orphaned.
    db.execute(
        "UPDATE fulfilment_rules SET shipping_service_id = NULL WHERE shipping_service_id = ?",
        (service_id,),
    )
    db.execute("DELETE FROM shipping_rates WHERE service_id = ?", (service_id,))
    db.execute("DELETE FROM shipping_services WHERE id = ?", (service_id,))


def set_rates(db, service_id, bands):
    """Replace a service's whole band table. `bands` is an iterable of
    (up_to_g, amount) in the smallest currency unit; blanks are dropped and
    duplicate ceilings collapse to the last one given."""
    clean = {}
    for up_to_g, amount in bands:
        try:
            g = int(up_to_g)
            a = int(amount)
        except (TypeError, ValueError):
            continue
        if g > 0 and a >= 0:
            clean[g] = a
    db.execute("DELETE FROM shipping_rates WHERE service_id = ?", (service_id,))
    for g in sorted(clean):
        db.execute(
            "INSERT INTO shipping_rates (service_id, up_to_g, amount) VALUES (?, ?, ?)",
            (service_id, g, clean[g]),
        )


#  ---- pricing a basket ----------------------------------------------------

def _physical_rules(db):
    return {
        r["price_id"]: dict(r)
        for r in db.execute(
            "SELECT * FROM fulfilment_rules WHERE kind = 'physical'"
        ).fetchall()
    }


def quote(db, integrations, items, subtotal, currency, free_over=0):
    """What delivery could cost for a basket, or None when nothing in it
    has to be posted.

    `items` is [(price_id, quantity)] -- one for a Buy button, several for
    a basket. Returns:
        {
          "countries": [ISO codes to collect an address for],
          "options":   [{"amount", "label", "currency"}, ...],  # buyer picks
          "estimate":  cheapest amount, for the basket page's "from" line
          "weight_g":  total posted weight, for display
          "uncovered": True when something weighs more than any band can
                       carry (so the address is taken but nothing charged),
        }
    Options are already priced from the total weight; the buyer chooses one
    at checkout, which is how destination is handled within Stripe.
    """
    physical = _physical_rules(db)
    phys = [(pid, max(1, int(qty or 1))) for pid, qty in items if pid in physical]
    if not phys:
        return None

    weight_g = sum((physical[pid].get("weight_g") or 0) * qty for pid, qty in phys)
    currency = (currency or integrations.base_currency(db))

    #  A product may name the service it ships by; if any do, only those are
    #  offered, otherwise every enabled service applies shop-wide.
    named = {physical[pid].get("shipping_service_id") for pid, _ in phys
             if physical[pid].get("shipping_service_id")}
    if named:
        services = [s for s in (get_service(db, sid) for sid in named) if s and s["enabled"]]
    else:
        services = list_services(db, enabled_only=True)

    #  Free over a threshold is worked out here, not sent to Stripe as a
    #  rate it has to reason about, so the buyer sees "Free delivery".
    if free_over and subtotal >= free_over:
        countries = _countries_for(integrations, services) or ["CH", "LI"]
        return {"countries": countries, "weight_g": weight_g, "uncovered": False,
                "estimate": 0,
                "options": [{"amount": 0, "label": "Free delivery", "currency": currency}]}

    options, countries, uncovered = [], set(), False
    for s in services:
        amount = rate_for_weight(s["rates"], weight_g)
        if amount is None:
            if s["rates"]:
                uncovered = True  # this service exists but can't carry it
            continue
        label = s["name"]
        options.append({"amount": amount, "label": label, "currency": currency})
        countries |= set(_zone_countries(integrations, s["zone"]))

    options.sort(key=lambda o: o["amount"])
    options = options[:MAX_OPTIONS]

    if not options:
        #  Something is posted but no band covers it (or no service is set
        #  up). Collect an address so the owner can still fulfil it, charge
        #  nothing rather than dead-end the sale, and flag it so the admin
        #  can be told to extend the bands.
        countries = _countries_for(integrations, services) or ["CH", "LI"]
        return {"countries": sorted(countries), "options": [], "weight_g": weight_g,
                "estimate": 0, "uncovered": True}

    return {"countries": sorted(countries), "options": options, "weight_g": weight_g,
            "estimate": options[0]["amount"], "uncovered": uncovered}


def _zone_countries(integrations, zone):
    z = integrations.SHIPPING_ZONES.get(zone) or integrations.SHIPPING_ZONES["ch"]
    return z[1]


def _countries_for(integrations, services):
    out = set()
    for s in services:
        out |= set(_zone_countries(integrations, s["zone"]))
    return sorted(out)


#  ---- one-time presets ----------------------------------------------------

#  Editable Swiss Post PostPac domestic starting points (CHF, smallest
#  unit). Real enough to sell with today, and plainly the owner's to
#  correct -- Swiss Post's tariffs are not ours to guarantee.
SWISS_POST_PRESETS = [
    ("Swiss Post — PostPac Economy", "Swiss Post", "ch", [
        (2000, 850), (10000, 1050), (30000, 2100),
    ]),
    ("Swiss Post — PostPac Priority", "Swiss Post", "ch", [
        (2000, 1050), (10000, 1250), (30000, 2300),
    ]),
]


def seed_defaults(db):
    """Install the Swiss Post presets ONCE, ever. Guarded by a flag rather
    than by "is the table empty", so an owner who deletes every service is
    not given them back on the next boot."""
    seeded = db.execute(
        "SELECT value FROM settings WHERE key = 'shipping_seeded'"
    ).fetchone()
    if seeded:
        return
    for name, carrier, zone, bands in SWISS_POST_PRESETS:
        sid = create_service(db, name, carrier, zone)
        set_rates(db, sid, bands)
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('shipping_seeded', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'"
    )
