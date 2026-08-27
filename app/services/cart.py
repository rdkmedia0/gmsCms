"""
The shopping basket.

Kept in the visitor's signed session cookie, not in a table. A basket is
not a record of anything — it is a scratchpad someone abandons far more
often than they check out — and giving every passer-by a database row (and
a row to clean up later) buys nothing. What it holds is only price ids and
quantities: no names, no amounts. Prices are read from Stripe every time
the basket is shown, so nothing here can be edited into a discount, and a
price changed in Stripe is right on the next page load.

Stock is the one thing Stripe genuinely does not know — it has no
inventory field at all — so it lives in `fulfilment_rules.stock` and is
checked here, both when something goes in the basket and again at
checkout, because a basket can sit open for a day.
"""
from flask import session

SESSION_KEY = "cart"
MAX_PER_LINE = 99


def _basket():
    return session.get(SESSION_KEY) or {}


def _save(basket):
    session[SESSION_KEY] = basket
    session.modified = True


def add(price_id, quantity=1):
    basket = _basket()
    basket[price_id] = min(MAX_PER_LINE, basket.get(price_id, 0) + max(1, int(quantity or 1)))
    _save(basket)


def set_quantity(price_id, quantity):
    basket = _basket()
    quantity = max(0, int(quantity or 0))
    if quantity:
        basket[price_id] = min(MAX_PER_LINE, quantity)
    else:
        basket.pop(price_id, None)
    _save(basket)


def remove(price_id):
    set_quantity(price_id, 0)


def clear():
    session.pop(SESSION_KEY, None)
    session.modified = True


def count():
    return sum(_basket().values())


def stock_for(db, price_id):
    """How many are left, or None when this is not something that runs
    out — a download, a booking, an unlimited item."""
    row = db.execute(
        "SELECT stock FROM fulfilment_rules WHERE price_id = ?", (price_id,)
    ).fetchone()
    return row["stock"] if row else None


def _stock_map(db):
    return {
        r["price_id"]: r["stock"]
        for r in db.execute(
            "SELECT price_id, stock FROM fulfilment_rules WHERE stock IS NOT NULL"
        ).fetchall()
    }


def lines(db, integrations):
    """(lines, currency, subtotal, problems).

    Every amount comes from Stripe here and now, never from the cookie.
    `problems` names anything that cannot be bought in the quantity asked
    for, so the basket page can say so plainly instead of the visitor
    discovering it at the payment step.
    """
    basket = _basket()
    if not basket:
        return [], "", 0, []
    catalogue, error = integrations.stripe_catalogue_cached(db)
    if error:
        return [], "", 0, ["We couldn't load prices just now. Please try again in a moment."]
    by_price = {item["price_id"]: item for item in catalogue}
    stock = _stock_map(db)
    out, subtotal, currency, problems = [], 0, "", []
    for price_id, quantity in list(basket.items()):
        item = by_price.get(price_id)
        if not item:
            #  Withdrawn from Stripe while it sat in someone's basket.
            remove(price_id)
            problems.append("Something in your basket is no longer for sale, so we've taken it out.")
            continue
        left = stock.get(price_id)
        if left is not None and quantity > left:
            quantity = max(0, left)
            set_quantity(price_id, quantity)
            problems.append(
                f"Only {left} of {item['name']} left, so we've adjusted your basket."
                if left else f"{item['name']} has just sold out."
            )
            if not quantity:
                continue
        amount = item["amount"] or 0
        currency = currency or item["currency"]
        subtotal += amount * quantity
        out.append({
            "price_id": price_id,
            "name": item["name"],
            "description": item["description"],
            "image": item["image"],
            "amount": amount,
            "currency": item["currency"],
            "quantity": quantity,
            "line_total": amount * quantity,
            "stock": left,
        })
    return out, currency, subtotal, problems


#  What a Shop tool shows before there is anything to sell.
#
#  A storefront with no products in it demonstrates nothing — the tool is
#  a grid, and an empty grid is a sentence saying "nothing here". So an
#  unconnected shop shows examples, which is the only way somebody
#  choosing a template can see what the tool does.
#
#  They are shown ONLY while editing. A published site with no payments
#  set up must not advertise things nobody can buy: a visitor seeing a
#  price and a basket button that leads nowhere is worse than a visitor
#  seeing an honest "nothing is for sale yet".
EXAMPLE_PRODUCTS = (
    {"name": "House blend, 250g", "description": "Roasted weekly. Chocolate, orange, a long finish.",
     "amount": 950, "currency": "GBP"},
    {"name": "Filter subscription", "description": "A different single origin each month, posted on the first.",
     "amount": 2400, "currency": "GBP"},
    {"name": "Gift card", "description": "Any amount, spent in the shop or against a class.",
     "amount": None, "currency": "GBP"},
)


def example_products():
    """The examples, shaped exactly like real ones.

    Same keys a Stripe product arrives with, so the storefront renders
    them through the same code and nothing downstream needs a special
    case — except the one thing that must differ: no price id, so there is
    nothing for a basket to be given.
    """
    return [
        {"price_id": "", "product_id": "", "image": "", "stock": None,
         "sold_out": False, "example": True, **item}
        for item in EXAMPLE_PRODUCTS
    ]


def shop_products(db, integrations, limit=None, editing=False):
    """The catalogue as a storefront sees it: what is on sale, what is
    running low, what has gone."""
    if not integrations.stripe_connected(db):
        #  Nothing has ever been set up here. While editing that is worth
        #  showing as examples; to a visitor it is simply an empty shop.
        return (example_products() if editing else []), None
    catalogue, error = integrations.stripe_catalogue_cached(db)
    if error:
        return [], error
    stock = _stock_map(db)
    items = []
    for item in catalogue:
        left = stock.get(item["price_id"])
        items.append({**item, "stock": left, "sold_out": left == 0})
    return (items[:limit] if limit else items), None


#  Postage settings, with the defaults a small seller would pick anyway.
SHIPPING_KEYS = ("shop_shipping_zone", "shop_shipping_amount", "shop_shipping_label", "shop_free_over")


def shipping_settings(db):
    rows = {
        r["key"]: r["value"]
        for r in db.execute(
            "SELECT key, value FROM settings WHERE key IN (%s)" % ",".join("?" * len(SHIPPING_KEYS)),
            SHIPPING_KEYS,
        ).fetchall()
    }
    return {
        "zone": rows.get("shop_shipping_zone") or "ch",
        "amount": int(rows.get("shop_shipping_amount") or 0),
        "label": rows.get("shop_shipping_label") or "Standard delivery",
        "free_over": int(rows.get("shop_free_over") or 0),
    }


def physical_price_ids(db):
    return {
        r["price_id"]
        for r in db.execute(
            "SELECT price_id FROM fulfilment_rules WHERE kind = 'physical'"
        ).fetchall()
    }


def shipping_for(db, integrations, lines_, subtotal, currency):
    """What to charge for postage, or None when nothing needs posting.

    Only a basket with something physical in it gets an address step at
    all — asking a buyer downloading an ebook for their street is the kind
    of friction that loses the sale. Free-over-a-threshold is worked out
    here rather than sent as a rate Stripe has to reason about, so the
    buyer sees "Free delivery" as a line rather than a discount.
    """
    physical = physical_price_ids(db)
    if not any(line["price_id"] in physical for line in lines_):
        return None
    settings = shipping_settings(db)
    zone = integrations.SHIPPING_ZONES.get(settings["zone"]) or integrations.SHIPPING_ZONES["ch"]
    free = settings["free_over"] and subtotal >= settings["free_over"]
    return {
        "countries": zone[1],
        "amount": 0 if free else settings["amount"],
        "label": "Free delivery" if free else settings["label"],
        "currency": currency or "chf",
    }


#  ---------------------------------------------------------------------
#  The basket, as a thing on the page
#  ---------------------------------------------------------------------
#  A shop needs a basket you can see from anywhere, not a link at the foot
#  of the one page that lists products — that is how every shopping site
#  works, because a person who has put something in a basket needs to know
#  it is still there while they carry on looking.
#
#  It is a tool, like everything else here, so where it goes is a decision
#  rather than something baked in. Dropped in the header zone it appears
#  at the top of every page, which is the conventional place and what a
#  shop template ships with.
#
#  Like the Shop tool it stores a marker, never a number: a count frozen
#  into the page would be somebody else's basket the moment the page was
#  cached or the section copied.

BASKET_STYLES = (
    ("icon", "Basket and a count"),
    ("count", "Just the count"),
    ("full", "Basket, count and the word"),
    ("bag", "Just the basket, no number"),
    ("button", "A button saying Basket"),
    ("text", "The word and a count, no picture"),
)
BASKET_STYLE_PREFIX = "cms-basket-style-"

#  Where in its row the basket sits. Right is the default because that is
#  where a shopper looks first — top-right is the one near-universal
#  convention across shopping sites — but a header built right-to-left, or
#  one that already puts something else on the right, needs the other two.
BASKET_ALIGNS = (
    ("right", "Right"),
    ("center", "Center"),
    ("left", "Left"),
)
BASKET_ALIGN_PREFIX = "cms-basket-align-"


#  What the basket is a picture OF. A bakery, a bookshop and a hardware
#  supplier all call it something different and reach for a different
#  shape, and the icon is the one part a shopper reads before any word.
#  Stroke-only paths on a 24x24 grid, so every one of them sits at the
#  same weight beside the others and takes the surrounding colour.
BASKET_ICONS = (
    ("bag", "Shopping bag"),
    ("basket", "Basket"),
    ("trolley", "Trolley"),
    ("box", "Parcel"),
    ("tag", "Price tag"),
)
BASKET_ICON_PATHS = {
    "bag": '<path d="M6 8h12l-1 12H7L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    "basket": ('<path d="M3 9h18l-1.4 8.6a2 2 0 0 1-2 1.7H6.4a2 2 0 0 1-2-1.7L3 9Z"/>'
               '<path d="m8 9 2-5m6 5-2-5"/><path d="M10 12.5v3.5m4-3.5v3.5"/>'),
    "trolley": ('<path d="M2.5 4h2.2l2.4 10.4a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.5L20.5 8H6"/>'
                '<circle cx="10" cy="19.2" r="1.3"/><circle cx="17" cy="19.2" r="1.3"/>'),
    "box": ('<path d="M3 8.4 12 4l9 4.4v7.2L12 20l-9-4.4V8.4Z"/>'
            '<path d="M3 8.4 12 12.8l9-4.4"/><path d="M12 12.8V20"/>'),
    "tag": ('<path d="M4 4h7.2l8.4 8.4a1.8 1.8 0 0 1 0 2.5l-4.7 4.7a1.8 1.8 0 0 1-2.5 0L4 11.2V4Z"/>'
            '<circle cx="8.2" cy="8.2" r="1.2"/>'),
}
BASKET_ICON_PREFIX = "cms-basket-icon-"

def build_basket(style="icon", hide_when_empty=False, align="right", icon="bag"):
    style = style if style in dict(BASKET_STYLES) else "icon"
    align = align if align in dict(BASKET_ALIGNS) else "right"
    icon = icon if icon in BASKET_ICON_PATHS else "bag"
    empty = "1" if str(hide_when_empty) == "1" else "0"
    return (f'<div class="cms-basket {BASKET_STYLE_PREFIX}{style} {BASKET_ALIGN_PREFIX}{align} '
            f'{BASKET_ICON_PREFIX}{icon}" '
            f'data-basket-tool data-hide-empty="{empty}"></div>')


def basket_settings(content):
    """Style, position and the when-empty choice, read back off the markup."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-basket")
    if box is None:
        return {"style": "icon", "align": "right", "hide_when_empty": False, "icon": "bag"}
    classes = box.get("class") or []
    style = next((key for key, _ in BASKET_STYLES
                  if BASKET_STYLE_PREFIX + key in classes), "icon")
    align = next((key for key, _ in BASKET_ALIGNS
                  if BASKET_ALIGN_PREFIX + key in classes), "right")
    icon = next((key for key, _ in BASKET_ICONS
                 if BASKET_ICON_PREFIX + key in classes), "bag")
    return {"style": style, "align": align, "icon": icon,
            "hide_when_empty": box.get("data-hide-empty") == "1"}


def apply_basket_form(form):
    return build_basket(form.get("basket_style"), "1" if form.get("hide_when_empty") else "0",
                        form.get("basket_align"), form.get("basket_icon"))


def render_basket(content, cart_url, editing=False):
    """What a visitor sees: the basket, and how much is in theirs.

    Worked out per request, because the count belongs to whoever is
    looking rather than to the page.
    """
    settings = basket_settings(content)
    items = count()
    if settings["hide_when_empty"] and not items and not editing:
        return ""
    #  A bag by default -- it reads at small sizes, and this is as likely
    #  to be a bakery as a supermarket -- but the owner picks the shape,
    #  because what a shop calls its basket is the shop's own word.
    icon = ('<svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
            'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">'
            + BASKET_ICON_PATHS.get(settings["icon"], BASKET_ICON_PATHS["bag"])
            + '</svg>')
    style = settings["style"]
    parts = []
    if style in ("icon", "full", "bag", "button"):
        parts.append(icon)
    if style in ("full", "button", "text"):
        parts.append('<span class="cms-basket-word">Basket</span>')
    #  "bag" is the one style with no number at all: a header that only
    #  ever shows a bag, for a site that would rather not put a running
    #  total in front of somebody who is still reading.
    if style != "bag":
        parts.append(f'<span class="cms-basket-count"{"" if items else " data-empty=\"1\""}>{items}</span>')
    label = f"{items} item in your basket" if items == 1 else f"{items} items in your basket"
    #  The alignment class has to land on what actually renders. It is
    #  stored on the tool's own marker div (basket_settings reads it back
    #  from there), but the marker itself is never shown to a visitor —
    #  this <a> replaces it entirely — so the class is repeated here, or
    #  the CSS that positions the basket has nothing in the live page to
    #  select.
    #  The style class travels onto the rendered <a> for the same reason
    #  the alignment one does: the marker div holding it is never what a
    #  visitor sees, so CSS keyed off it would match nothing live.
    return (f'<a class="cms-basket-link {BASKET_STYLE_PREFIX}{style} '
            f'{BASKET_ALIGN_PREFIX}{settings["align"]}" '
            f'href="{cart_url}" title="{label}" aria-label="{label}">'
            + "".join(parts) + "</a>")
