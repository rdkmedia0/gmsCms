"""
The pages a shop is required to have, written from what the owner tells us.

Selling to consumers in the EU or Switzerland means saying certain things
in writing before someone pays: who you are, what happens if they change
their mind, and what you do with their details. Most small sellers either
copy a competitor's wording — which is someone else's company name and
someone else's returns policy — or leave it out entirely.

So this generates a real starting point from a handful of plain questions,
and produces ORDINARY PAGES made of ordinary Text sections. Not a special
locked page type: the owner opens them in the normal editor and changes
whatever they like, because the wording has to end up being theirs. That
is also why the generated text hedges nothing it does not have to and
avoids clause numbering — it is meant to be read by a customer, and edited
by someone who is not a lawyer.

The wording follows the EU Consumer Rights Directive's distance-selling
rules, which is the strictest of the regimes a small European seller is
likely to meet, and the one Swiss sellers still owe to EU customers. It is
a starting point, not legal advice, and the admin screen says so.
"""
import datetime
import re

from flask import render_template

#  slug -> (title, template, which sellers need it)
DOCUMENTS = {
    "refunds": ("Cancelling and refunds", "legal/refunds.j2", "Everyone selling anything"),
    "terms": ("Terms", "legal/terms.j2", "Everyone selling anything"),
    "privacy": ("Privacy", "legal/privacy.j2", "Everyone, whether you sell or not"),
    "imprint": ("Site details", "legal/imprint.j2", "Required in Germany, Austria and Switzerland"),
}

SETTINGS_KEYS = (
    "legal_business", "legal_address", "legal_email", "legal_phone",
    "legal_vat_number", "legal_company_number", "legal_responsible",
    "legal_country", "legal_withdrawal_days", "legal_booking_notice_hours",
    "legal_retention_years", "legal_currency", "legal_governing_law",
)

EU_COUNTRIES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}
OTHER_COUNTRIES = {"CH": "Switzerland", "GB": "United Kingdom", "NO": "Norway",
                   "US": "United States", "OTHER": "Somewhere else"}
COUNTRIES = {**EU_COUNTRIES, **OTHER_COUNTRIES}


def whatsapp_link(phone):
    """A working wa.me link built from a phone number, or "".

    Why this exists rather than "paste a link into a Button": a `wa.me`
    address is `https://`, so a Button or a Menu item already accepts one
    and no new tool is needed. What people get WRONG is the number.
    wa.me takes the full international number and NOTHING else -- no
    plus, no spaces, no dashes, no brackets, no leading zero -- and a
    number with any of those in it produces a link that opens WhatsApp to
    nobody at all, with no error and nothing to see. It is the one part a
    person cannot be expected to know.

    So this does the one thing, from the number the site already has, and
    the screen offers the result to copy. Anything further -- a chat
    widget, the Business API -- is a decision about whether this product
    holds customer conversations, which is not a formatting problem.

    Returns "" rather than a broken link when the number cannot be a
    international one: a link that silently goes nowhere is worse than no
    link, which is the whole fault being fixed.
    """
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits:
        return ""
    #  A number written for local dialling starts with a trunk 0, which
    #  is not part of the international number. Without a country code in
    #  front of it there is nothing to replace that 0 with, so this
    #  refuses rather than guessing a country -- guessing would produce a
    #  link that reaches somebody, just not the right somebody.
    international = (phone or "").strip().startswith("+") or (phone or "").strip().startswith("00")
    if not international:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    #  Shortest real international number is 7 digits + country code.
    if len(digits) < 8 or len(digits) > 15:
        return ""
    return "https://wa.me/" + digits


def settings_for(db):
    rows = {
        r["key"]: r["value"]
        for r in db.execute(
            "SELECT key, value FROM settings WHERE key IN (" + ",".join("?" * len(SETTINGS_KEYS)) + ")",
            SETTINGS_KEYS,
        ).fetchall()
    }
    #  One install is one website, so it has ONE name -- but it is stored
    #  in two places (site_title and the legal_* settings), and two places
    #  that can disagree eventually do: this very install
    #  had a tab reading one business and a Terms page naming another.
    #
    #  So the legal name FALLS BACK to the site's rather than standing
    #  empty beside it. They are still allowed to differ -- a trading
    #  name and a legal entity are genuinely two things, "Flour & Salt"
    #  and "Flour & Salt GmbH" -- but differing is now something the
    #  owner typed, not something that happened to them.
    site_name = db.execute(
        "SELECT value FROM settings WHERE key = 'site_title'").fetchone()
    #  Whether the postal address is repeated at the bottom of EMAILS. It
    #  stays on the website either way (the Impressum needs it); an email is
    #  a separate question -- see newsletter.sender_line. Default on, the
    #  safe/compliant choice; the owner can switch it off.
    include_addr = db.execute(
        "SELECT value FROM settings WHERE key = 'email_include_address'").fetchone()
    return {
        "email_include_address": (include_addr["value"] if include_addr else "1"),
        "business": rows.get("legal_business") or (site_name["value"] if site_name else "") or "",
        "address": rows.get("legal_address") or "",
        "email": rows.get("legal_email") or "",
        "phone": rows.get("legal_phone") or "",
        "vat_number": rows.get("legal_vat_number") or "",
        "company_number": rows.get("legal_company_number") or "",
        "responsible": rows.get("legal_responsible") or "",
        "country": rows.get("legal_country") or "CH",
        #  Fourteen days is the EU statutory minimum. Offering less is not
        #  a policy choice, it is unenforceable, so the field starts here
        #  and the form only allows going up.
        "withdrawal_days": int(rows.get("legal_withdrawal_days") or 14),
        "booking_notice_hours": int(rows.get("legal_booking_notice_hours") or 24),
        "retention_years": int(rows.get("legal_retention_years") or 10),
        "currency": rows.get("legal_currency") or "",
        "governing_law": rows.get("legal_governing_law") or "",
    }


def save_settings(db, form):
    def _clean(key, default=""):
        return (form.get(key) or "").strip() or default

    values = {
        "legal_business": _clean("business"),
        "legal_address": _clean("address"),
        "legal_email": _clean("email"),
        "legal_phone": _clean("phone"),
        "legal_vat_number": _clean("vat_number"),
        "legal_company_number": _clean("company_number"),
        "legal_responsible": _clean("responsible"),
        "legal_country": _clean("country", "CH"),
        "legal_withdrawal_days": str(max(14, int(form.get("withdrawal_days") or 14))),
        "legal_booking_notice_hours": str(max(0, int(form.get("booking_notice_hours") or 24))),
        "legal_retention_years": str(max(0, int(form.get("retention_years") or 10))),
        "legal_currency": _clean("currency"),
        "legal_governing_law": _clean("governing_law"),
    }
    for key, value in values.items():
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def what_is_sold(db):
    """Which sections the documents need, read from what the site actually
    sells rather than asked again — the fulfilment rules already say."""
    kinds = {
        r["kind"] for r in db.execute("SELECT DISTINCT kind FROM fulfilment_rules").fetchall()
    }
    return {
        "sells_services": "credit" in kinds,
        "sells_digital": "download" in kinds,
        "sells_physical": "physical" in kinds,
    }


def render_document(db, slug):
    """The finished text for one document."""
    title, template, _ = DOCUMENTS[slug]
    context = settings_for(db)
    context.update(what_is_sold(db))
    context["in_eu"] = context["country"] in EU_COUNTRIES
    context["in_ch"] = context["country"] == "CH"
    #  Where Terms points at the refunds wording. On one page that is
    #  an anchor; on separate pages it is the page itself.
    combined = db.execute(
        "SELECT 1 FROM sections s JOIN pages p ON p.id = s.page_id "
        "WHERE p.slug = ? AND s.content LIKE ?", (COMBINED_SLUG, "%data-legal-doc%")
    ).fetchone()
    context["refunds_href"] = (f"/{COMBINED_SLUG}#refunds" if combined else "/refunds")
    context["refunds_slug"] = "refunds"
    context["refunds_title"] = DOCUMENTS["refunds"][0]
    if not context["business"]:
        context["business"] = "this site"
    return render_template(template, **context)


def missing_details(db):
    """What has to be filled in before the documents say anything useful."""
    settings = settings_for(db)
    missing = []
    if not settings["business"]:
        missing.append("the name you trade under")
    if not settings["email"]:
        missing.append("an email address customers can use")
    if not settings["address"] and settings["country"] in ("DE", "AT", "CH"):
        missing.append("a postal address (required where you are)")
    return missing


#  "Legal" is what the folder of documents is called; "Terms &
#  Conditions" is what a visitor is looking for a link to. The address
#  follows the title rather than the folder, so the page says what it is
#  in the place people read it.
COMBINED_SLUG = "terms-and-conditions"
COMBINED_TITLE = "Terms & Conditions"


def write_pages(db, slugs, combined=True):
    """Creates or refreshes the chosen documents. Returns what it did.

    The content goes in as a normal section on a normal page, so from the
    moment it exists it is editable like anything else on the site — which
    matters, because generated legal wording is a first draft of something
    the owner is responsible for, not a finished artefact.

    `combined` puts every document on one page called Legal, each as its
    own section under its own heading, rather than scattering four pages
    through the navigation of a site that might have five pages of its
    own. It is the default because that is what most sites do, and because
    four extra entries in a menu is a real cost for a small business.

    A page for each is still there for the case that genuinely needs it:
    an Impressum is expected to be reachable under its own clearly
    labelled link in Germany and Austria, and burying it inside a longer
    page is a worse answer there than an extra entry in the footer.

    Either way each document keeps its own marked section, so refreshing
    one rewrites only that one and leaves everything around it alone.
    """
    if combined:
        return _write_combined(db, slugs)
    written, updated = [], []
    for slug in slugs:
        if slug not in DOCUMENTS:
            continue
        title = DOCUMENTS[slug][0]
        html = render_document(db, slug)
        page = db.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
        if page:
            #  Replace only the section this tool wrote, leaving anything
            #  the owner added to the page alone.
            existing = db.execute(
                "SELECT id FROM sections WHERE page_id = ? AND content LIKE ? ORDER BY position LIMIT 1",
                (page["id"], "%data-legal-doc%"),
            ).fetchone()
            if existing:
                db.execute("UPDATE sections SET content = ? WHERE id = ?",
                           (_wrap(html, slug), existing["id"]))
            else:
                _append_section(db, page["id"], html, slug)
            updated.append(title)
        else:
            cur = db.execute(
                "INSERT INTO pages (title, slug, nav_order, page_type) "
                "VALUES (?, ?, (SELECT COALESCE(MAX(nav_order),0)+1 FROM pages), 'standard')",
                (title, slug),
            )
            _append_section(db, cur.lastrowid, html, slug)
            written.append(title)
    return written, updated


def _write_combined(db, slugs):
    """Every chosen document on one page, in the order they are declared.

    Each keeps its own section and its own marker, which is what makes a
    refresh surgical: rewriting Privacy touches the Privacy section and
    nothing else on the page, including anything the owner has written
    between them.
    """
    written, updated = [], []
    #  Sites written before the rename have this page as "legal". Renamed
    #  rather than left beside a new one: two pages of the same wording is
    #  exactly what the combined page exists to avoid.
    old_page = db.execute("SELECT id FROM pages WHERE slug = 'legal'").fetchone()
    if old_page and not db.execute(
        "SELECT 1 FROM pages WHERE slug = ?", (COMBINED_SLUG,)
    ).fetchone():
        db.execute("UPDATE pages SET slug = ?, title = ? WHERE id = ?",
                   (COMBINED_SLUG, COMBINED_TITLE, old_page["id"]))
    page = db.execute("SELECT * FROM pages WHERE slug = ?", (COMBINED_SLUG,)).fetchone()
    if page:
        page_id = page["id"]
    else:
        cur = db.execute(
            "INSERT INTO pages (title, slug, nav_order, page_type) "
            "VALUES (?, ?, (SELECT COALESCE(MAX(nav_order),0)+1 FROM pages), 'standard')",
            (COMBINED_TITLE, COMBINED_SLUG),
        )
        page_id = cur.lastrowid

    for slug in DOCUMENTS:
        if slug not in slugs:
            continue
        title = DOCUMENTS[slug][0]
        #  Its own anchor, so a link can point straight at one document
        #  rather than at the top of a long page -- put ON the heading the
        #  document already has, rather than in front of it. Prepending
        #  one gave every document on the combined page two identical
        #  headings, one under the other, since each template opens with
        #  its own <h2> and DOCUMENTS holds the same words.
        html = _anchored(render_document(db, slug), slug, title)
        existing = db.execute(
            "SELECT id FROM sections WHERE page_id = ? AND content LIKE ? ORDER BY position LIMIT 1",
            (page_id, f'%data-legal-doc="{slug}"%'),
        ).fetchone()
        if existing:
            db.execute("UPDATE sections SET content = ? WHERE id = ?",
                       (_wrap(html, slug), existing["id"]))
            updated.append(title)
        else:
            _append_section(db, page_id, html, slug)
            written.append(title)

    _retire_separate_legal_pages(db, slugs)
    return written, updated


def _anchored(html, slug, title):
    """Gives a document's own first heading the id a link can point at.

    Falls back to adding a heading only if the document has none -- every
    one of them does today, and if a new one arrives without, it should
    still be findable rather than silently unlabelled.
    """
    match = re.search(r"<h2\b([^>]*)>", html)
    if not match:
        return f'<h2 id="{slug}">{title}</h2>' + html
    if "id=" in match.group(1):
        return html
    return html[:match.start()] + f'<h2 id="{slug}"{match.group(1)}>' + html[match.end():]


def _retire_separate_legal_pages(db, slugs):
    """Removes the old one-page-each versions, when they are only that.

    Moving to a single page leaves the previous pages behind, duplicating
    the same wording at a second address — which for legal text is worse
    than clutter, because the two will drift and only one of them is
    right.

    A page is only removed if it holds nothing but the section this tool
    wrote. If the owner has added anything of their own to it, it stays
    and is reported, because deleting somebody's writing to tidy up is
    never the right trade.
    """
    for slug in slugs:
        if slug == COMBINED_SLUG:
            continue
        page = db.execute("SELECT id FROM pages WHERE slug = ?", (slug,)).fetchone()
        if not page:
            continue
        sections = db.execute(
            "SELECT id, content FROM sections WHERE page_id = ?", (page["id"],)
        ).fetchall()
        only_ours = sections and all("data-legal-doc" in (r["content"] or "") for r in sections)
        if only_ours:
            db.execute("DELETE FROM sections WHERE page_id = ?", (page["id"],))
            db.execute("DELETE FROM pages WHERE id = ?", (page["id"],))


def _wrap(html, slug):
    #  The marker is how a refresh finds its own section again without
    #  touching anything the owner has added alongside it.
    stamp = datetime.date.today().isoformat()
    return f'<div data-legal-doc="{slug}" data-written="{stamp}">{html}</div>'


def _append_section(db, page_id, html, slug):
    #  A Text tool, not HTML/Embed. What this writes is prose --
    #  headings, paragraphs and lists -- which is exactly what the Text
    #  tool is for, and an owner opening it should get bold, italic and a
    #  heading button like anywhere else on their site. As an Embed they
    #  got a code box, which is this app's marker for "third-party
    #  script", offered to somebody looking at their own refund policy.
    #  Embed is for real third-party code only, and this was breaking
    #  that rule.
    db.execute(
        "INSERT INTO sections (page_id, type, title, content, position) "
        "VALUES (?, 'text', '', ?, (SELECT COALESCE(MAX(position),0)+1 FROM sections WHERE page_id = ?))",
        (page_id, _wrap(html, slug), page_id),
    )


def existing_pages(db):
    """Which of the documents are already on the site."""
    #  Built with a plain join rather than %-formatting: the LIKE pattern
    #  contains a literal % and "%d" in "%data-legal-doc%" is a format
    #  spec to Python long before it is a wildcard to SQLite.
    placeholders = ",".join("?" * len(DOCUMENTS))
    rows = db.execute(
        "SELECT p.slug, p.id, MAX(s.content) AS content FROM pages p "
        "LEFT JOIN sections s ON s.page_id = p.id AND s.content LIKE ? "
        "WHERE p.slug IN (" + placeholders + ") GROUP BY p.id",
        ("%data-legal-doc%",) + tuple(DOCUMENTS),
    ).fetchall()
    out = {}
    for row in rows:
        written = ""
        if row["content"] and 'data-written="' in row["content"]:
            written = row["content"].split('data-written="', 1)[1][:10]
        out[row["slug"]] = {"id": row["id"], "written": written}
    return out
