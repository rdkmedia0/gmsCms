"""Can a buyer page the booking calendar a month at a time, and only as
far as the owner allows?

The calendar was a fixed fortnight from today. It is a whole month now,
with arrows to the months either side, up to a limit set on Store
settings. This walks the buyer's page with Cal.com stubbed: which month
opens, where the arrows go, that a month outside the window is clamped
to the nearest end rather than drawn empty, that Cal.com is asked only
for the bookable part of a month, and that the owner's limit is honoured
the moment it is saved.

Run inside the container:

    docker compose exec -T web python tools/booking_check.py
"""
import datetime
import os
import re
import sys
import tempfile

sys.path.insert(0, "/app")
DATA_DIR = tempfile.mkdtemp(prefix="booking-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import bootstrap                                     # noqa: E402
from app.services import integrations, commerce               # noqa: E402

app = create_app()
client = app.test_client()
passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    print("%-62s %s%s" % (what, "ok" if ok else "FAILED",
                          ("  " + str(detail)) if detail and not ok else ""))
    passed += bool(ok)
    failed += not ok


#  Cal.com stubbed: connected, and free at 10:00 on every day it is asked
#  about -- so what the page shows is exactly what it asked for.
asked = []


def fake_slots(db, event_type_id, start, end, timezone="UTC"):
    asked.append((start, end))
    out, day, stop = {}, datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    while day < stop:
        out[day.isoformat()] = [day.isoformat() + "T10:00:00Z"]
        day += datetime.timedelta(days=1)
    return out, None


integrations.calcom_slots = fake_slots
_really_configured = integrations.is_configured
integrations.is_configured = lambda db, name: True if name in ("calcom", "stripe") else _really_configured(db, name)
integrations.currencies_in_use = lambda db: ([], None)

with app.app_context():
    db = get_db()
    uid = db.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
    bootstrap.clear_generated_password_flag(db, uid)
    cid = db.execute("INSERT INTO customers (email, name) VALUES ('buyer@example.test', 'Sam')").lastrowid
    db.execute("INSERT INTO entitlements (customer_id, kind, granted, used, ref) "
               "VALUES (?, 'credit', 5, 0, '123')", (cid,))
    token = commerce.create_access_token(db, cid)
    db.commit()

today = datetime.date.today()
DAY = datetime.timedelta(days=1)


def month_of(day):
    return day.strftime("%Y-%m")


def add_months(day, n):
    m = day.month - 1 + n
    return datetime.date(day.year + m // 12, m % 12 + 1, 1)


def page(**args):
    asked.clear()
    args.setdefault("tz", "UTC")
    return client.get(f"/my/{token}", query_string=args).get_data(as_text=True)


def label(html):
    m = re.search(r'cms-cal-nav-label">([^<]+)<', html)
    return m.group(1) if m else None


def arrows(html):
    return re.findall(r'cms-cal-nav-btn" href="[^"]*month=(\d{4}-\d{2})', html)


this_month, next_month = today.replace(day=1), add_months(today, 1)
window_end = today + datetime.timedelta(days=integrations.DEFAULT_BOOKING_WINDOW_DAYS)

print("The month that opens")
print("-" * 70)
html = page()
check("the page opens on this month", label(html) == today.strftime("%B %Y"), label(html))
check("and asks Cal.com from today to the end of it, no further than the limit",
      asked == [(today.isoformat(), min(next_month, window_end).isoformat())], asked)
check("a day with a free time is offered", "cms-cal-day is-free" in html)
if today.day > 1:
    gone = (today - DAY).strftime("%A %d %B")
    check("yesterday is drawn but offers nothing",
          bool(re.search(r'is-out"\s+title="' + re.escape(gone) + '"', html)))
check("there is an arrow to the month after", month_of(next_month) in arrows(html), arrows(html))
check("but none to the month before today",
      month_of(add_months(today, -1)) not in arrows(html) and "cms-cal-nav-btn is-off" in html)

print()
print("Paging")
print("-" * 70)
html = page(month=month_of(next_month))
check("the month after opens", label(html) == next_month.strftime("%B %Y"), label(html))
check("and Cal.com is asked for that month only, up to the limit",
      asked == [(next_month.isoformat(), min(add_months(today, 2), window_end).isoformat())], asked)
check("with an arrow back to this month", month_of(this_month) in arrows(html), arrows(html))
last_month = (window_end - DAY).replace(day=1)
html = page(month="2099-01")
check("a month past the limit shows the last one that can be booked",
      label(html) == last_month.strftime("%B %Y"), label(html))
check("with no arrow forward", month_of(add_months(last_month, 1)) not in arrows(html), arrows(html))
check("a month in the past shows this month", label(page(month="2001-01")) == today.strftime("%B %Y"))
check("and so does nonsense", label(page(month="not-a-month")) == today.strftime("%B %Y"))

print()
print("Nothing free")
print("-" * 70)
integrations.calcom_slots = lambda db, e, s, t, timezone="UTC": ({}, None)
html = page()
check("says so, and points at the month after",
      "Nothing free in" in html and "try the month after" in html)
check("the grid is still drawn, so the arrows make sense", 'class="cms-cal"' in html)
integrations.calcom_slots = fake_slots

print()
print("The confirm step")
print("-" * 70)
when = next_month.isoformat() + "T10:00:00Z"
html = page(month=month_of(next_month), confirm=when).replace("&amp;", "&")
check("'pick a different time' returns to the month the time was in",
      f"month={month_of(next_month)}" in html and "Pick a different time" in html)

print()
print("The owner's limit")
print("-" * 70)
with client.session_transaction() as s:
    s["user_id"] = uid
r = client.post("/admin/commerce/booking-window", data={"days": "14"}, headers={"Origin": "http://localhost"})
check("saves from Store settings", r.status_code in (302, 303), r.status_code)
with app.app_context():
    check("and is read back", integrations.booking_window_days(get_db()) == 14)
html = client.get("/admin/commerce/settings").get_data(as_text=True)
check("the screen shows it selected", bool(re.search(r'<option value="14" selected', html)))
html = page()
fortnight_end = today + datetime.timedelta(days=14)
check("the calendar now reaches only as far as the fortnight",
      (month_of(next_month) in arrows(html)) == ((fortnight_end - DAY).replace(day=1) > this_month), arrows(html))
check("and Cal.com is asked no further",
      asked == [(today.isoformat(), min(next_month, fortnight_end).isoformat())], asked)
client.post("/admin/commerce/booking-window", data={"days": "0"}, headers={"Origin": "http://localhost"})
with app.app_context():
    check("blank falls back to the default rather than zero",
          integrations.booking_window_days(get_db()) == integrations.DEFAULT_BOOKING_WINDOW_DAYS)

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
