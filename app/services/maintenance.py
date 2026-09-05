"""Maintenance mode: a holding page for visitors while the owner works.

One switch and one message, both in `settings`. When it is on:

  * a visitor sees the message and an HTTP **503** -- so a search engine
    treats the site as temporarily down and comes back, rather than
    reading a normal 200 page and possibly indexing "we're closed", or a
    404/410 and dropping the page. A `Retry-After` rides with it.
  * the OWNER, being signed in, keeps seeing the real site, so they can
    do the work and switch it back off from the same browser.
  * `healthz` is never gated, so uptime monitoring still sees the process
    is alive.

Read-only here (is it on, what does it say); the writing is one settings
row each and stays in the route, because a service never reaches up into
request/flash/redirect (see CLAUDE.md, import direction).
"""

#  The words the site ships with -- a real, friendly message an owner can
#  leave alone, or write over. The owner asked for this one by name.
DEFAULT_MESSAGE = ("Fraggles have taken down the scaffolding, we'll be back "
                   "up and running as soon as the Doozers rebuild.")


def is_on(db):
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'maintenance_mode'").fetchone()
    return bool(row) and row["value"] == "1"


def message(db):
    """What the holding page says -- the owner's words, or the default."""
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'maintenance_message'").fetchone()
    return ((row["value"] if row else "") or "").strip() or DEFAULT_MESSAGE
