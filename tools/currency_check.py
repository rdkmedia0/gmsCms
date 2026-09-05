"""One shop, one currency — and a basket that refuses to add two.

The bug this is the net under is quiet and about money: `cart.lines()`
took the FIRST line's currency and added every later amount into one
subtotal regardless, so a basket holding 10 CHF and 10 EUR read
"20.00 CHF" — a number that is not a price in either currency. Nothing
raised; the customer was simply quoted the wrong thing.

It could happen because the currency was a per-product dropdown with CHF
first in the list, so a shop's currency was whatever each product
happened to be created with. There is one setting now, and this checks
both halves: that the setting is what a new product gets, and that a
basket cannot mix.

Run inside the container:

    docker compose exec -T web python tools/currency_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="currency-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                     # noqa: E402
from app.db import get_db                                      # noqa: E402
from app.services import cart, integrations                    # noqa: E402

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


app = create_app()

#  A catalogue this app can reason about without Stripe. The point of
#  these checks is what happens to two currencies in one basket, and a
#  network round trip proves nothing about that.
CATALOGUE = [
    {"price_id": "price_chf", "name": "A francs thing", "description": "",
     "image": "", "amount": 1000, "currency": "chf"},
    {"price_id": "price_chf2", "name": "Another francs thing", "description": "",
     "image": "", "amount": 500, "currency": "chf"},
    {"price_id": "price_eur", "name": "A euros thing", "description": "",
     "image": "", "amount": 1000, "currency": "eur"},
]


class FakeIntegrations(object):
    """Only what cart.lines() actually asks of it."""

    CURRENCIES = integrations.CURRENCIES
    base_currency = staticmethod(integrations.base_currency)

    @staticmethod
    def stripe_catalogue_cached(db):
        return CATALOGUE, None


with app.test_request_context("/"):
    db = get_db()

    print()
    print("A site has a currency, and refuses one it cannot charge in")
    print("-" * 70)
    check("there is a default before anybody chooses",
          integrations.base_currency(db) == integrations.DEFAULT_CURRENCY,
          integrations.base_currency(db))

    saved, error = integrations.set_base_currency(db, "eur")
    db.commit()
    check("it can be set", saved == "eur" and not error, str((saved, error)))
    check("...and it sticks", integrations.base_currency(db) == "eur")

    bad, bad_error = integrations.set_base_currency(db, "xyz")
    check("a currency this app cannot name is refused, not stored",
          bad is None and bad_error, str((bad, bad_error)))
    check("...and the refusal did not damage what was there",
          integrations.base_currency(db) == "eur")
    check("case does not matter", integrations.set_base_currency(db, "GBP")[0] == "gbp")

    integrations.set_base_currency(db, "chf")
    db.commit()

    print()
    print("A basket cannot add two currencies together")
    print("-" * 70)
    #  Two of the same: totals normally.
    cart.set_quantity("price_chf", 1)
    cart.set_quantity("price_chf2", 2)
    lines, currency, subtotal, problems = cart.lines(db, FakeIntegrations)
    check("one currency totals normally",
          currency == "chf" and subtotal == 2000 and len(lines) == 2,
          str((currency, subtotal, len(lines))))
    check("...with nothing to complain about", not problems, str(problems))

    #  Add a third in another currency: it must not be added in.
    cart.set_quantity("price_eur", 1)
    lines, currency, subtotal, problems = cart.lines(db, FakeIntegrations)
    check("the odd currency is not added to the total",
          subtotal == 2000, "%s %s" % (subtotal, currency))
    check("...it is taken out of the basket rather than quoted wrongly",
          all(line["price_id"] != "price_eur" for line in lines),
          str([line["price_id"] for line in lines]))
    check("...and the customer is told why, naming both currencies",
          any("EUR" in p and "CHF" in p for p in problems), str(problems))
    check("what is left is a real price in one currency",
          currency == "chf" and sum(line["line_total"] for line in lines) == subtotal,
          str((currency, subtotal)))
    check("and it stays out on the next look",
          "price_eur" not in (cart._basket() or {}), str(cart._basket()))

    print()
    print("Postage is quoted in the shop's own currency")
    print("-" * 70)
    #  It used to fall back to a hardcoded "chf", so a shop charging in
    #  euros quoted postage in francs.
    integrations.set_base_currency(db, "eur")
    db.commit()
    rate = cart.shipping_for(db, FakeIntegrations, [], 0, "")
    check("with nothing to go on, postage uses the site's currency",
          rate is None or rate.get("currency") == "eur", str(rate))

    print()
    print("A new product is priced in the site's currency")
    print("-" * 70)
    #  Read from the source rather than driven through Stripe: what is
    #  being checked is that the route no longer reads a form field that
    #  no longer exists, which is a statement about the code.
    routes = open("/app/app/routes/admin/settings.py", encoding="utf-8").read()
    screen = open("/app/app/templates/admin/commerce_fulfilment.html",
                  encoding="utf-8").read()
    #  The shop-wide currency setting and the stray-currency warning moved
    #  to the Store settings tab when Products was split from settings; the
    #  Products screen keeps only per-product repricing.
    settings_screen = open("/app/app/templates/admin/commerce_settings.html",
                           encoding="utf-8").read()
    check("creating a product takes the site's currency",
          "integrations.base_currency(db)," in routes)
    check("no product form asks for a currency any more",
          'name="currency"' not in screen, "a picker is still there")
    check("repricing keeps the price's own currency",
          'name="current_currency"' in screen and "current_currency" in routes)
    check("the setting has a screen", 'name="base_currency"' in settings_screen
          and "def commerce_currency" in routes)
    check("a stray currency is named rather than left quiet",
          "currencies_in_use" in settings_screen and "currencies_in_use" in routes)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
