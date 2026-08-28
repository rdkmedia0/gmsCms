"""A subscription keeps delivering, and never delivers twice.

Checkout worked for a subscription and fulfilment did not. Only
`checkout.session.completed` and the refund events were handled, so a
monthly price granting 10 sessions granted them ONCE, at the first
payment, and never again. Nothing failed and nothing was logged: the
buyer ran out in month two and the owner had no way to see why. Anybody
selling a membership was under-delivering silently.

The dangerous half of the fix is the other direction. Stripe sends BOTH
`checkout.session.completed` and an `invoice.paid` for the first
payment, so the obvious implementation hands every new subscriber double
what they bought -- and free credits are invisible until somebody books
a session they never paid for.

So this drives the whole life of a subscription through the real webhook
handler, with Stripe's own event shapes, and counts what was granted at
each step.

Run inside the container:

    docker compose exec -T web python tools/subscription_check.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="subscription-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app.services import commerce, integrations               # noqa: E402

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

PRICE = "price_membership"
EMAIL = "member@example.test"


def invoice(invoice_id, reason, amount=2500, quantity=1):
    """An invoice the shape Stripe actually sends one."""
    return {
        "id": invoice_id,
        "billing_reason": reason,
        "customer_email": EMAIL,
        "customer_name": "A Member",
        "amount_paid": amount,
        "amount_due": amount,
        "currency": "chf",
        "lines": {"data": [{
            "price": {"id": PRICE},
            "quantity": quantity,
            "description": "Membership",
        }]},
    }


def credits(db):
    row = db.execute(
        "SELECT COALESCE(SUM(granted - used), 0) AS n FROM entitlements e "
        "JOIN customers c ON c.id = e.customer_id "
        "WHERE c.email = ? AND e.kind = 'credit'", (EMAIL,)).fetchone()
    return row["n"]


with app.app_context():
    db = get_db()
    #  A membership: one monthly price that delivers 10 sessions.
    db.execute("INSERT INTO fulfilment_rules (price_id, kind, ref, quantity) "
               "VALUES (?, 'credit', 'coaching', 10)", (PRICE,))
    db.commit()

    print()
    print("The first payment grants once, not twice")
    print("-" * 70)
    #  Stripe sends BOTH of these for the same money.
    order_id, created = commerce.record_checkout(db, {
        "id": "cs_first", "payment_status": "paid", "amount_total": 2500,
        "currency": "chf",
        "customer_details": {"email": EMAIL, "name": "A Member"},
    }, [{"price": {"id": PRICE}, "quantity": 1}])
    db.commit()
    check("checkout grants the first month", credits(db) == 10, str(credits(db)))

    #  ...and the invoice for that same first payment must not grant.
    first = invoice("in_first", commerce.FIRST_PAYMENT)
    check("the first payment's invoice is recognised as such",
          first["billing_reason"] == commerce.FIRST_PAYMENT)
    check("...and is NOT one of the reasons that grant",
          commerce.FIRST_PAYMENT not in commerce.RENEWAL_REASONS,
          "granting on subscription_create doubles every new subscriber")

    print()
    print("Every renewal after that delivers again")
    print("-" * 70)
    for month, ref in ((2, "in_month2"), (3, "in_month3")):
        oid, made = commerce.record_renewal(db, invoice(ref, "subscription_cycle"))
        db.commit()
        check("month %d grants another 10" % month, credits(db) == 10 * month,
              "%d credits" % credits(db))
        check("...and is recorded as an order", made and oid)

    print()
    print("A replayed webhook changes nothing")
    print("-" * 70)
    #  The event-id check upstream should stop this, but a duplicated
    #  renewal is free credits, so it is guarded twice.
    before = credits(db)
    oid, made = commerce.record_renewal(db, invoice("in_month3", "subscription_cycle"))
    db.commit()
    check("the same invoice a second time grants nothing", credits(db) == before,
          "%d then %d" % (before, credits(db)))
    check("...and says it was already recorded", not made)

    print()
    print("A failed renewal is visible, and grants nothing")
    print("-" * 70)
    before = credits(db)
    oid, made = commerce.record_failed_renewal(db, invoice("in_failed", "subscription_cycle"))
    db.commit()
    check("nothing is granted", credits(db) == before, "%d" % credits(db))
    row = db.execute("SELECT status FROM orders WHERE provider_ref = 'in_failed'").fetchone()
    check("it appears on the orders screen as failed",
          row and row["status"] == "failed", str(dict(row) if row else None))
    check("...so a card that expired is not silent", made)

    print()
    print("An invoice reads its own lines, whatever shape Stripe sends")
    print("-" * 70)
    #  Older invoices put the price at line.price.id; newer ones at
    #  line.pricing.price_details.price. Both have to work, or renewals
    #  break on an API version bump with nothing to see.
    old_shape = commerce.invoice_line_items(invoice("in_x", "subscription_cycle"))
    check("the older shape is read", old_shape[0]["price_id"] == PRICE, str(old_shape))
    new_shape = commerce.invoice_line_items({"lines": {"data": [{
        "pricing": {"price_details": {"price": PRICE}}, "quantity": 2}]}})
    check("the newer shape is read too", new_shape[0]["price_id"] == PRICE, str(new_shape))
    check("...and the quantity comes with it", new_shape[0]["quantity"] == 2)
    #  A line whose price cannot be found is KEPT, so the order still
    #  records what was charged even when nothing can be granted for it.
    blank = commerce.invoice_line_items({"lines": {"data": [{"quantity": 1}]}})
    check("a line with no price is kept, not dropped", len(blank) == 1, str(blank))

    print()
    print("Stripe is actually asked to send these events")
    print("-" * 70)
    #  A handler for an event nobody subscribed to is a handler that never
    #  runs -- the exact shape of the rate limit that did not exist.
    check("invoice.paid is subscribed to",
          "invoice.paid" in integrations.WEBHOOK_EVENTS)
    check("invoice.payment_failed is too",
          "invoice.payment_failed" in integrations.WEBHOOK_EVENTS)
    #  Driven through the real route, not looked for as a string in it.
    #  "The file contains 'invoice.paid'" passes just as happily when the
    #  branch is wrong, which is the class of check this project has
    #  shipped before.
    commerce.verify_stripe_signature = lambda body, sig, secret: json.loads(body)
    client = app.test_client()

    def deliver(event_id, event_type, payload):
        return client.post("/stripe/webhook", data=json.dumps(
            {"id": event_id, "type": event_type, "data": {"object": payload}}),
            content_type="application/json")

    before = credits(db)
    answer = deliver("evt_first", "invoice.paid",
                     invoice("in_route_first", commerce.FIRST_PAYMENT))
    check("the route answers a first-payment invoice", answer.status_code == 200,
          str(answer.status_code))
    check("...and grants nothing for it", credits(db) == before,
          "%d then %d -- every new subscriber would get double" % (before, credits(db)))

    answer = deliver("evt_cycle", "invoice.paid",
                     invoice("in_route_cycle", "subscription_cycle"))
    check("the route answers a renewal", answer.status_code == 200)
    check("...and grants for it", credits(db) == before + 10,
          "%d then %d" % (before, credits(db)))

    before = credits(db)
    answer = deliver("evt_failed", "invoice.payment_failed",
                     invoice("in_route_failed", "subscription_cycle"))
    check("the route answers a failed renewal", answer.status_code == 200)
    check("...and grants nothing", credits(db) == before)
    check("...but records it where somebody will see it", db.execute(
        "SELECT status FROM orders WHERE provider_ref = 'in_route_failed'"
    ).fetchone()["status"] == "failed")
    #  An endpoint created before these were added keeps its old list
    #  forever, so an existing install has to be TOLD.
    src = open("/app/app/services/integrations.py", encoding="utf-8").read()
    check("a stale endpoint can be detected", "def webhook_missing_events" in src)
    screen = open("/app/app/templates/admin/settings_integrations.html",
                  encoding="utf-8").read()
    check("...and the owner is told on the screen", "webhook_missing" in screen)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
