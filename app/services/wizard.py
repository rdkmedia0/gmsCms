"""The walk from "I installed this" to "this is my website".

Everything this asks about already works and is already reachable from
some screen. What nothing does is INTRODUCE it: somebody who has just
installed this app is looking at a bakery's demo content with no idea
that the palette, the fonts, the layout, the site address, email and
Stripe are all things they are allowed to touch. So the wizard is as
much an introduction as a configuration -- an owner who finishes should
know the Tools panel exists, know the Colors panel exists, and know
which integrations they have not set up.

Three rules shape the whole thing (see BOW.md's specification):

* **One install is one website.** The name, the business details and the
  contact are captured ONCE here and are then what everything else
  reads. They are the site's own -- activating a template brings a look
  and some pages, never an identity -- so `_apply_pack_identity` stands
  down permanently once this has recorded that the owner stated theirs.
* **It orchestrates, it does not reimplement.** Every step writes
  through the same service or settings the ordinary screen writes
  through. A step that needs new behaviour is a step doing something the
  app cannot already do, which is a design smell rather than a feature.
* **It must be abandonable.** Somebody who leaves at step four has a
  coherent site and a wizard that remembers where they were. Nothing is
  applied that was not chosen, and no step is required.
"""

STEPS = (
    ("name", "What is this site called?"),
    ("look", "How should it look?"),
    ("details", "Who is behind it"),
    ("address", "Where the site lives"),
    ("email", "Sending email"),
    ("extras", "Payments, bookings and AI"),
    ("done", "That is the lot"),
)

STEP_KEYS = [key for key, _title in STEPS]

#  Where the wizard's own state lives. Three settings, no table: it is a
#  position in a walk, not data anybody keeps.
STEP_SETTING = "setup_step"
DONE_SETTING = "setup_done"
IDENTITY_SETTING = "setup_identity_stated"


def _setting(db, key, default=""):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return (row["value"] if row else default) or default


def _write(db, key, value):
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def state(db):
    """Where the walk has got to."""
    step = _setting(db, STEP_SETTING) or STEP_KEYS[0]
    if step not in STEP_KEYS:
        step = STEP_KEYS[0]
    return {
        "step": step,
        "done": _setting(db, DONE_SETTING) == "1",
        "started": bool(_setting(db, STEP_SETTING)),
        "index": STEP_KEYS.index(step),
        "count": len(STEPS) - 1,  # the last one is a summary, not a question
    }


def remember(db, step):
    """Where to come back to. Written on arrival at a step, so leaving in
    the middle of one returns to that step rather than the one after."""
    if step in STEP_KEYS:
        _write(db, STEP_SETTING, step)


def next_step(step):
    index = STEP_KEYS.index(step) if step in STEP_KEYS else 0
    return STEP_KEYS[min(index + 1, len(STEP_KEYS) - 1)]


def previous_step(step):
    index = STEP_KEYS.index(step) if step in STEP_KEYS else 0
    return STEP_KEYS[max(index - 1, 0)]


def finish(db):
    _write(db, DONE_SETTING, "1")
    _write(db, STEP_SETTING, STEP_KEYS[-1])


def restart(db):
    """Re-runnable, always: somebody changing template a year later wants
    the same walk-through. Only the position is reset -- never anything
    they have set."""
    _write(db, DONE_SETTING, "")
    _write(db, STEP_SETTING, STEP_KEYS[0])


def identity_stated(db):
    """Whether the owner has told this site its own name.

    `_apply_pack_identity` guesses at this -- it replaces a name only
    while it is still "", "My Site" or some template's demo name -- which
    is a good guess in the absence of an answer. This IS the answer, so
    once it is recorded that path stands down and a template can never
    rename somebody's site again.
    """
    return _setting(db, IDENTITY_SETTING) == "1"


def record_identity(db):
    _write(db, IDENTITY_SETTING, "1")


def is_fresh(db):
    """A brand-new site, or one somebody has been running.

    The difference decides how bold a step may be: on a fresh install
    nothing is at risk, while on a site with real content every
    destructive step needs asking about first. Judged on what the site
    has DONE -- sold something, sent something, collected somebody's
    address -- rather than on how old it is.
    """
    for table in ("orders", "subscribers", "newsletter_sends"):
        try:
            if db.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]:
                return False
        except Exception:  # noqa: BLE001 - a table that does not exist yet is not use
            continue
    return True


#  What the site has been built to DO, read off its own pages.
#
#  A block lives in a section's markup (a Shop is `cms-shop`, a Buy button
#  is `cms-buy`, a sign-up form is `cms-newsletter`), so what a site is
#  for is a question its own content can answer. This is the difference
#  between a summary that nags everybody about Stripe and one that says
#  "there is a Shop on your site and nobody can pay on it".
SIGNS = {
    "sells": ("cms-shop", "cms-buy", "cms-basket"),
    "books": ("cal.com", "cms-booking"),
    "collects_email": ("cms-newsletter", "cms-contact-form-tool"),
}


def what_this_site_does(db):
    """Which of the things above this site already has on a page.

    Cheap and deliberately shallow: it is looking for a marker in markup
    the app itself wrote, not parsing anything. A false negative costs an
    amber badge where a red one was due, which is the safe way round --
    it never invents an alarm about a feature nobody is using.
    """
    found = {key: False for key in SIGNS}
    try:
        rows = db.execute("SELECT content FROM sections").fetchall()
    except Exception:  # noqa: BLE001 - a site mid-migration has no sections yet
        return found
    for row in rows:
        markup = (row["content"] or "").lower()
        for key, markers in SIGNS.items():
            if not found[key] and any(marker in markup for marker in markers):
                found[key] = True
    #  Somebody on the list is the same statement as a sign-up form on a
    #  page: this site is emailing people either way.
    if not found["collects_email"]:
        try:
            found["collects_email"] = bool(
                db.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0])
        except Exception:  # noqa: BLE001
            pass
    return found


def summary(db):
    """What is set and what is not, for the last step to say plainly.

    Each entry is (what it is, whether it is set, where to go). Read by
    the final step and by the Dashboard's nudge, so the two cannot
    disagree about what is still missing.
    """
    from . import site as site_service

    site_title = _setting(db, "site_title")
    does = what_this_site_does(db)
    #  `needed` is the difference between amber and red, and it is a claim
    #  about THIS site: red only where the gap breaks something already on
    #  a page. `because` is that claim in words, said on the row, because
    #  a red badge with no reason is just a louder nag.
    return [
        {"what": "The site's name", "set": bool(site_title and site_title != "My Site"),
         "value": site_title, "where": "admin.dashboard",
         "why": "It is the browser tab, the heading of every email, and the name on your legal pages.",
         "needed": True,
         "because": "Every page of your site and every email from it carries this name."},
        {"what": "Your postal address", "set": bool(_setting(db, "legal_address")),
         "value": _setting(db, "legal_address").splitlines()[0] if _setting(db, "legal_address") else "",
         "where": "admin.legal_pages",
         "why": "A newsletter is refused without one -- an email to a list has to carry it.",
         "needed": does["collects_email"],
         "because": "This site collects email addresses, and a send is refused without a postal "
                    "address on it."},
        {"what": "The site's web address", "set": site_service.is_configured(db),
         "value": site_service.public_base(db) or "", "where": "admin.dashboard",
         "why": "Every link that leaves this app is built from it: payment returns, email links, previews.",
         "needed": True,
         "because": "Until this is set, every link this app sends out is a guess at where your "
                    "site lives."},
        {"what": "Sending email", "set": bool(_setting(db, "smtp_host")),
         "value": _setting(db, "smtp_host"), "where": "admin.settings_email",
         "why": "Contact forms and newsletters do nothing without it.",
         "needed": does["collects_email"],
         "because": "There is a form on your site asking visitors for their address, and nothing "
                    "they send can reach you."},
        {"what": "Taking payments", "set": bool(_setting(db, "stripe_secret_key_enc")),
         "value": "", "where": "admin.settings_integrations",
         "why": "Only if you sell something. A Shop or a Buy button needs it; nothing else does.",
         "needed": does["sells"],
         "because": "There is a Shop or a Buy button on your site and no way for anybody to pay."},
        {"what": "Taking bookings", "set": bool(_setting(db, "calcom_api_key_enc")),
         "value": "", "where": "admin.settings_integrations",
         "why": "Only if people book time with you.",
         "needed": does["books"],
         "because": "There is a booking block on your site that is not connected to anything."},
        {"what": "AI help", "set": bool(_setting(db, "openwebui_url")),
         "value": "", "where": "admin.settings_ai",
         "why": "Optional everywhere. Writing, pictures and the theme generator use it if it is there.",
         "needed": False,
         "because": ""},
    ]
