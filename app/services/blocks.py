"""
The content blocks a modern site is expected to have — pricing, proof,
people, process — each with a real form behind it.

Every tool in this app has to be usable by someone who will never type
HTML: a tile that drops markup on the page and leaves you to edit it by
hand is an Embed wearing a costume. But eight tools each needing a
builder, a parser, a config form, two update routes and a detection branch
is six hundred lines of the same wiring eight times, and every one of
those is somewhere the eighth tool differs from the first by accident.

So a block is DECLARED here — its fields, and how those fields become
markup — and one config form, one parser and one pair of routes serve all
of them. Adding a ninth tool is a dictionary entry.

The parser is the part worth understanding. Nothing is stored twice: the
markup a block builds carries `data-field` attributes on the elements
that hold content, and reading a block back means walking those
attributes. An <img> yields its src, an <a> its href and text, everything
else its text. So the page holds the content once, in the markup that
displays it, and the form is a view onto that rather than a second copy
liable to drift.
"""
import html as html_lib
import json

from bs4 import BeautifulSoup


def esc(value):
    return html_lib.escape((value or "").strip())


def _field(name, label, kind="text", **extra):
    """A field of a block.

    `kind` also decides WHERE it is edited. Text and textarea fields are
    words on the page, so they are edited on the page — click them and
    type, the same as a Text or Card section. Only the things that cannot
    be typed into a page go in the toolbar: which style, which picture,
    where a button points, and how many of something there are.

    That split is the rule this app already followed everywhere else, and
    the blocks broke it by asking for a heading in a toolbar box while the
    heading sat visible on the page an inch away.
    """
    return {"name": name, "label": label, "kind": kind, **extra}


#  The "somewhere else" entry on a link dropdown, and the schemes a typed
#  address may use. Anything else is treated as a bare domain and given
#  https:// -- a novice types "example.com", not a scheme, and silently
#  producing a relative link to a page that does not exist is worse than
#  assuming the obvious.
OTHER_LINK = "__other__"
BUTTON_SCHEMES = ("http://", "https://", "mailto:", "tel:", "/", "#")


#  Kinds whose value is words shown on the page, and so are edited there.
INLINE_KINDS = ("text", "textarea")


def is_inline(field):
    return field["kind"] in INLINE_KINDS


def toolbar_fields(key):
    """Only what belongs in a toolbar: styles, pictures, links, flags."""
    out = []
    for entry in BLOCKS[key]["fields"]:
        if "group" in entry:
            for i in range(1, entry["count"] + 1):
                for field in entry["fields"]:
                    if not is_inline(field):
                        out.append((f"{entry['group']}{i}_{field['name']}", field, i))
        elif not is_inline(entry):
            out.append((entry["name"], entry, None))
    return out


def _group(prefix, label, count, fields):
    """A repeated set — tiers, stats, people. Empty ones simply don't
    render, so "how many" never has to be asked as its own question: the
    admin fills in three and gets three."""
    return {"group": prefix, "label": label, "count": count, "fields": fields}


#  ---------------------------------------------------------------- builders

def _wrap(key, inner, **data):
    attrs = " ".join(f'data-{k}="{esc(str(v))}"' for k, v in data.items() if v not in (None, ""))
    return f'<div class="cms-block cms-block-{key}" {attrs}>{inner}</div>'


def _items(values, prefix, count, keys, flags=()):
    """The filled-in members of a repeated group, in order.

    `flags` names the tick-box fields, which do not count as content. An
    unticked box reads back as the string "0", and a string is truthy —
    so without this an untouched fourth plan looked filled and rendered
    as an empty card.
    """
    out = []
    for i in range(1, count + 1):
        item = {k: (values.get(f"{prefix}{i}_{k}") or "").strip() for k in keys}
        if any(v for k, v in item.items() if k not in flags):
            out.append(item)
    return out


def build_pricing(values):
    tiers = _items(values, "tier", 4,
                   ("name", "price", "period", "features", "cta", "link", "featured"),
                   flags=("featured",))
    cards = []
    for i, tier in enumerate(tiers, start=1):
        featured = (values.get(f"tier{i}_featured") or "") == "1"
        features = "".join(
            f'<li>{esc(line)}</li>' for line in (tier["features"] or "").splitlines() if line.strip()
        )
        button = ""
        if tier["cta"]:
            href = esc(tier["link"] or "#")
            button = (f'<a class="cms-price-btn" href="{href}" '
                      f'data-href-field="tier{i}_link">'
                      f'<span data-field="tier{i}_cta">{esc(tier["cta"])}</span></a>')
        #  The highlight is carried as a flag as well as a class, because a
        #  class is styling and the form has to be able to read the answer
        #  back — see parse_block.
        flag = f' data-flag="tier{i}_featured"' if featured else ""
        cards.append(
            f'<div class="cms-price-tier{" is-featured" if featured else ""}"{flag}>'
            f'<h3 class="cms-price-name" data-field="tier{i}_name">{esc(tier["name"])}</h3>'
            f'<p class="cms-price-amount"><span data-field="tier{i}_price">{esc(tier["price"])}</span>'
            f'<small data-field="tier{i}_period">{esc(tier["period"])}</small></p>'
            f'<ul class="cms-price-features" data-field="tier{i}_features">{features}</ul>'
            f'{button}</div>'
        )
    return _wrap("pricing", f'<div class="cms-price-grid">{"".join(cards)}</div>',
                 columns=len(cards) or 3)


def build_testimonial(values):
    style = values.get("style") or "card"
    photo = values.get("photo") or ""
    img = f'<img class="cms-quote-photo" src="{esc(photo)}" alt="" data-field="photo">' if photo else ""
    return _wrap(
        "testimonial",
        f'<figure class="cms-quote cms-quote-{esc(style)}">{img}'
        f'<blockquote data-field="quote">{esc(values.get("quote"))}</blockquote>'
        f'<figcaption><span class="cms-quote-name" data-field="name">{esc(values.get("name"))}</span>'
        f'<span class="cms-quote-role" data-field="role">{esc(values.get("role"))}</span></figcaption></figure>',
        style=style,
    )


def build_stats(values):
    stats = _items(values, "stat", 4, ("value", "label"))
    cells = "".join(
        f'<div class="cms-stat"><span class="cms-stat-value" data-field="stat{i}_value">{esc(s["value"])}</span>'
        f'<span class="cms-stat-label" data-field="stat{i}_label">{esc(s["label"])}</span></div>'
        for i, s in enumerate(stats, start=1)
    )
    return _wrap("stats", f'<div class="cms-stat-row">{cells}</div>', count=len(stats))


def build_logos(values):
    logos = _items(values, "logo", 6, ("image", "name", "link"))
    items = []
    for i, logo in enumerate(logos, start=1):
        if logo["image"]:
            inner = (f'<img src="{esc(logo["image"])}" alt="{esc(logo["name"])}" loading="lazy" '
                     f'data-field="logo{i}_image">')
        else:
            #  A name with no picture is shown as the name. Half the rows
            #  of this kind in the world are wordmarks — accreditations, a
            #  "featured in" line — and requiring a picture file for those
            #  meant an empty row with nothing but broken image icons in
            #  it, which is what the tool used to render.
            inner = f'<span class="cms-logo-name" data-field="logo{i}_name">{esc(logo["name"])}</span>'
        if logo["link"]:
            inner = (f'<a href="{esc(logo["link"])}" rel="noopener" data-href-field="logo{i}_link">{inner}</a>')
        items.append(f'<div class="cms-logo">{inner}</div>')
    muted = "1" if (values.get("muted") or "") == "1" else "0"
    return _wrap("logos", f'<div class="cms-logo-row{" is-muted" if muted == "1" else ""}">{"".join(items)}</div>',
                 muted=muted)


def build_team(values):
    people = _items(values, "person", 6, ("photo", "name", "role", "bio"))
    cards = []
    for i, person in enumerate(people, start=1):
        photo = (f'<img class="cms-person-photo" src="{esc(person["photo"])}" alt="" loading="lazy" '
                 f'data-field="person{i}_photo">') if person["photo"] else ""
        cards.append(
            f'<div class="cms-person">{photo}'
            f'<h3 class="cms-person-name" data-field="person{i}_name">{esc(person["name"])}</h3>'
            f'<p class="cms-person-role" data-field="person{i}_role">{esc(person["role"])}</p>'
            f'<p class="cms-person-bio" data-field="person{i}_bio">{esc(person["bio"])}</p></div>'
        )
    return _wrap("team", f'<div class="cms-team-grid">{"".join(cards)}</div>', count=len(cards))


def build_timeline(values):
    entries = _items(values, "step", 6, ("when", "title", "text"))
    items = "".join(
        f'<li class="cms-timeline-item">'
        f'<span class="cms-timeline-when" data-field="step{i}_when">{esc(e["when"])}</span>'
        f'<div class="cms-timeline-body">'
        f'<h3 data-field="step{i}_title">{esc(e["title"])}</h3>'
        f'<p data-field="step{i}_text">{esc(e["text"])}</p></div></li>'
        for i, e in enumerate(entries, start=1)
    )
    style = values.get("style") or "vertical"
    return _wrap("timeline", f'<ol class="cms-timeline cms-timeline-{esc(style)}">{items}</ol>', style=style)


def build_cta(values):
    href = esc(values.get("link") or "#")
    #  The words in a span inside the link, not on the link itself: the
    #  editor makes each [data-field] a caret target, and a control is a
    #  poor one. See parse_block for how the two facts are read now.
    button = (f'<a class="cms-cta-btn" href="{href}" data-href-field="link">'
              f'<span data-field="cta">{esc(values.get("cta"))}</span></a>') if values.get("cta") else ""
    tone = values.get("tone") or "solid"
    return _wrap(
        "cta",
        f'<div class="cms-cta cms-cta-{esc(tone)}">'
        f'<h2 data-field="heading">{esc(values.get("heading"))}</h2>'
        f'<p data-field="text">{esc(values.get("text"))}</p>{button}</div>',
        tone=tone,
    )


def build_newsletter(values):
    return _wrap(
        "newsletter",
        f'<div class="cms-newsletter">'
        f'<h2 data-field="heading">{esc(values.get("heading"))}</h2>'
        f'<p data-field="text">{esc(values.get("text"))}</p>'
        f'<form class="cms-newsletter-form" method="post" action="/subscribe">'
        f'<label class="cms-visually-hidden" for="cms-sub-email">Email address</label>'
        f'<input type="email" id="cms-sub-email" name="email" required '
        f'placeholder="{esc(values.get("placeholder") or "you@example.com")}" '
        f'data-attr-field="placeholder">'
        #  cms-action-btn, not cms-buy-btn. Signing up to a newsletter is
        #  not a purchase, and this button was wearing the Buy tool's own
        #  class -- so a change to how Buy looks silently restyled it, and
        #  the string "cms-buy" sat inside an Email sign-up's markup where
        #  a label test looks for it. The shared LOOK has a name of its
        #  own now; a tool's identity class stays that tool's.
        #  The label lives in a span, because a browser will not place a
        #  caret inside a <button>: with data-field on the button itself
        #  the editor marked it contenteditable and nothing happened when
        #  you clicked it. The panel's own hint promises that everything on
        #  the page can be clicked and typed into, and this was the one
        #  place that was not true.
        f'<button type="submit" class="cms-action-btn">'
        f'<span data-field="cta">{esc(values.get("cta") or "Sign up")}</span></button>'
        f'<input type="hidden" name="consent_text" value="{esc(values.get("consent") or "Yes, email me occasional updates. Unsubscribe any time.")}">'
        #  The same trap the contact form sets, and deliberately the same
        #  FIELD: a bot that has learned to leave `website` alone there
        #  has learned it here, rather than there being two traps that
        #  can disagree. Hidden with CSS rather than type="hidden", so a
        #  bot reading the markup cannot tell it apart from a real field.
        #  This form mails whatever address is typed into it, so what it
        #  is protecting is a STRANGER's inbox, not the owner's.
        f'<div class="cms-newsletter-hp" aria-hidden="true">'
        f'<label for="cms-sub-website">Website</label>'
        f'<input type="text" id="cms-sub-website" name="website" tabindex="-1" autocomplete="off">'
        f'</div>'
        #  A line, not a tick box. The box asked somebody to agree to
        #  signing up, on a form whose only purpose is signing up, having
        #  already pressed a button that says Sign up -- the same act,
        #  demanded twice. What consent actually requires is that the
        #  person is TOLD what they are agreeing to and that it can be
        #  evidenced afterwards: the wording is shown here, and the hidden
        #  consent_text above stores the exact words they were shown with
        #  their row, because this block will be edited later and the
        #  promise made to somebody last spring is the one that counts.
        #
        #  A tick box is the right control for the other case -- an email
        #  collected for something else (a contact form, a checkout) with
        #  marketing bundled alongside, where consent has to be unbundled
        #  and separately given. Nothing in this app does that today; if
        #  something ever does, it needs its own box, not this one back.
        f'<p class="cms-newsletter-consent" data-field="consent">'
        f'{esc(values.get("consent") or "Yes, email me occasional updates. Unsubscribe any time.")}</p>'
        #  Said BEFORE, not after. Signing up here does not put anybody on
        #  a list -- it sends them a mail with a link, and only that link
        #  does -- and somebody who is not told that has no reason to go
        #  and look for it. They fill the form in, see "thank you", and
        #  never hear from the site again, having done nothing wrong.
        #
        #  Fixed wording, not a field. Everything else in this block is
        #  the owner's to write; this one sentence describes how the
        #  mechanism actually behaves, and an owner editing it into "you
        #  are now subscribed" would make the site lie about its own
        #  process. If the process changes, this changes with it.
        f'<p class="cms-newsletter-howitworks">'
        f'We&rsquo;ll email you a link to confirm. Nothing else is sent until you follow it.</p>'
        #  Where the answer appears. Empty until there is one, and inside
        #  the form on purpose: the reply used to be a line at the top of
        #  the page after a full reload, which on a sign-up near the foot
        #  of a long page meant the page jumped away from what you were
        #  reading and the answer was somewhere you were not looking.
        f'<p class="cms-subscribe-note" data-subscribe-note role="status" hidden></p>'
        f'</form></div>',
    )


#  ---------------------------------------------------------------- registry

BLOCKS = {
    "pricing": {
        "name": "Pricing", "icon": "💲",
        "blurb": "Two to four plans side by side, with what each includes.",
        "build": build_pricing,
        "fields": [
            _group("tier", "Plan", 4, [
                _field("name", "Plan name", help="Starter, Standard, Full day…"),
                _field("price", "Price", help="Write it how you want it read: 45, CHF 45, From 45"),
                _field("period", "Per what", help="per month, per session — leave blank for a one-off"),
                _field("features", "What's included", "textarea", help="One per line"),
                _field("cta", "Button text", help="Leave blank for no button"),
                _field("link", "Button goes to", "link"),
                _field("featured", "Highlight this one", "checkbox"),
            ]),
        ],
        "defaults": {
            "tier1_name": "Starter", "tier1_price": "45", "tier1_period": "per session",
            "tier1_features": "One 60-minute session\nNotes afterwards\nEmail follow-up",
            "tier1_cta": "Book", "tier1_link": "#",
            "tier2_name": "Package of six", "tier2_price": "240", "tier2_period": "for six",
            "tier2_features": "Six 60-minute sessions\nNotes afterwards\nEmail between sessions\nBook at your own pace",
            "tier2_cta": "Book", "tier2_link": "#", "tier2_featured": "1",
            "tier3_name": "Full day", "tier3_price": "560", "tier3_period": "per day",
            "tier3_features": "A full day, start to finish\nWritten plan to take away\nA month of email support",
            "tier3_cta": "Enquire", "tier3_link": "#",
        },
    },
    "testimonial": {
        "name": "Testimonial", "icon": "❝",
        "blurb": "One quote from a real customer, said properly.",
        "build": build_testimonial,
        "fields": [
            _field("quote", "What they said", "textarea"),
            _field("name", "Who said it", help="A real name carries more than “a happy client”"),
            _field("role", "What they do", help="Optional — their job, company, or where they're from"),
            _field("photo", "Their photo", "image"),
            _field("style", "How it looks", "select",
                   options=[("card", "Card"), ("plain", "Plain quote"), ("large", "Large, centred")]),
        ],
        "defaults": {
            "quote": "I came in not knowing what I wanted and left with a plan I actually understood.",
            "name": "Sarah Kessler", "role": "Owner, Kessler & Co", "style": "card",
        },
    },
    "stats": {
        "name": "Numbers", "icon": "📊",
        "blurb": "Two to four figures worth stating plainly.",
        "build": build_stats,
        "fields": [
            _group("stat", "Figure", 4, [
                _field("value", "The number", help="12 years, 400+, 98%"),
                _field("label", "What it counts"),
            ]),
        ],
        "defaults": {
            "stat1_value": "12", "stat1_label": "Years doing this",
            "stat2_value": "400+", "stat2_label": "People helped",
            "stat3_value": "98%", "stat3_label": "Would recommend",
        },
    },
    "logos": {
        "name": "Logo row", "icon": "🏷️",
        "blurb": "Who you've worked with, or where you've been featured.",
        "build": build_logos,
        "fields": [
            _group("logo", "Logo", 6, [
                _field("image", "Picture", "image"),
                _field("name", "Whose it is", help="Used as the description for screen readers"),
                _field("link", "Links to", "link"),
            ]),
            _field("muted", "Show them greyed out", "checkbox",
                   help="Keeps a row of mismatched logos from fighting your own colours"),
        ],
        "defaults": {"muted": "1"},
    },
    "team": {
        "name": "The team", "icon": "👥",
        "blurb": "Who people will actually be dealing with.",
        "build": build_team,
        "fields": [
            _group("person", "Person", 6, [
                _field("photo", "Photo", "image"),
                _field("name", "Name"),
                _field("role", "What they do"),
                _field("bio", "A line about them", "textarea"),
            ]),
        ],
        "defaults": {
            "person1_name": "Your name", "person1_role": "What you do",
            "person1_bio": "A sentence about how you got here and what you're good at.",
        },
    },
    "timeline": {
        "name": "Timeline", "icon": "🕓",
        "blurb": "How it works, step by step — or the story so far.",
        "build": build_timeline,
        "fields": [
            _group("step", "Step", 6, [
                _field("when", "When or number", help="Step one, 2019, Week 1"),
                _field("title", "Heading"),
                _field("text", "What happens", "textarea"),
            ]),
            _field("style", "Direction", "select",
                   options=[("vertical", "Down the page"), ("horizontal", "Across the page")]),
        ],
        "defaults": {
            "step1_when": "Step one", "step1_title": "We talk",
            "step1_text": "Twenty minutes on the phone, no charge, to work out whether this is a fit at all.",
            "step2_when": "Step two", "step2_title": "A plan",
            "step2_text": "You get it in writing, with what it costs, before anything starts.",
            "step3_when": "Step three", "step3_title": "The work",
            "step3_text": "We get on with it, and you always know where it stands.",
            "style": "vertical",
        },
    },
    "cta": {
        "name": "Call to action", "icon": "📣",
        "blurb": "A band across the page asking for the one thing you want people to do.",
        "build": build_cta,
        "fields": [
            _field("heading", "Heading"),
            _field("text", "A line underneath", "textarea"),
            _field("cta", "Button text"),
            _field("link", "Button goes to", "link"),
            _field("tone", "How it looks", "select",
                   options=[("solid", "Solid colour"), ("soft", "Soft tint"), ("outline", "Outlined")]),
        ],
        "defaults": {
            "heading": "Ready when you are", "text": "Book a first session, or ask a question first — both are fine.",
            "cta": "Get in touch", "link": "/contact", "tone": "solid",
        },
    },
    "newsletter": {
        "name": "Email sign-up", "icon": "✉️",
        "blurb": "Collect email addresses, with consent asked for properly.",
        "build": build_newsletter,
        "fields": [
            _field("heading", "Heading"),
            _field("text", "A line underneath", "textarea"),
            _field("placeholder", "Greyed-out example in the box"),
            _field("cta", "Button text"),
            _field("consent", "What they're agreeing to", "textarea",
                   help="Shown under the form and stored with the sign-up, so what somebody agreed to can be shown later even after you reword this"),
        ],
        "defaults": {
            "heading": "Occasional updates", "text": "A few times a year, when there's something worth saying.",
            "placeholder": "you@example.com", "cta": "Sign up",
            "consent": "Yes, email me occasional updates. Unsubscribe any time.",
        },
    },
}


def flat_fields(key):
    """Every field of a block as (name, spec), groups expanded."""
    out = []
    for entry in BLOCKS[key]["fields"]:
        if "group" in entry:
            for i in range(1, entry["count"] + 1):
                for field in entry["fields"]:
                    out.append((f"{entry['group']}{i}_{field['name']}", field))
        else:
            out.append((entry["name"], entry))
    return out


def parse_block(content):
    """The values behind a block, read from the markup that displays them.

    Nothing is stored twice: the fields are read back off the elements
    that hold the content, so what the form shows is always what the page
    shows.
    """
    soup = BeautifulSoup(content or "", "html.parser")
    wrapper = soup.find(class_="cms-block")
    if wrapper is None:
        return None, {}
    key = next((c.replace("cms-block-", "") for c in (wrapper.get("class") or [])
                if c.startswith("cms-block-")), None)
    if key not in BLOCKS:
        return None, {}
    values = {k[5:]: v for k, v in wrapper.attrs.items() if k.startswith("data-") and k != "data-field"}
    for el in wrapper.select("[data-field]"):
        name = el.get("data-field")
        if el.name == "img":
            values[name] = el.get("src", "")
        elif el.name == "ul":
            values[name] = "\n".join(li.get_text() for li in el.find_all("li"))
        else:
            values[name] = el.get_text()
    #  Where a control points is read from the control, and what it SAYS is
    #  read from whatever holds the words. Those used to be assumed to be
    #  the same element, and are not: a button's label has to live in a
    #  span, because a browser will not put a caret inside a <button> and
    #  the label was therefore not editable at all. Scanning separately
    #  reads both the old markup (both attributes on the anchor) and the
    #  new (the words in a span inside it).
    for el in wrapper.select("[data-href-field]"):
        values[el.get("data-href-field")] = el.get("href", "")
    for el in wrapper.select("[data-attr-field]"):
        values[el.get("data-attr-field")] = el.get("placeholder", "")
    #  A flag has no text of its own — the element existing IS the value.
    #  Without this a "highlight this plan" tick survived only as a CSS
    #  class, so the form read it back as off and the next save lost it.
    for el in wrapper.select("[data-flag]"):
        values[el.get("data-flag")] = "1"
    #  A checkbox that is off is simply absent from the markup.
    for name, spec in flat_fields(key):
        if spec["kind"] == "checkbox":
            values.setdefault(name, "0")
    return key, values


def build(key, values):
    return BLOCKS[key]["build"](values)


def starter(key):
    return build(key, BLOCKS[key].get("defaults", {}))


def apply_form(key, form, current=""):
    """Rebuilds the block after a toolbar change.

    Merged over whatever is already on the page rather than built from the
    form alone: the words live in the markup now and the form never sends
    them, so building from the form would blank every heading the moment
    somebody changed a colour.
    """
    _, values = parse_block(current)
    values = dict(values or {})
    for name, spec in flat_fields(key):
        if is_inline(spec):
            continue  # edited on the page, not here
        if spec["kind"] == "checkbox":
            values[name] = "1" if form.get(name) else "0"
        elif name in form:
            chosen = (form.get(name) or "").strip()
            #  A link is picked from a list of this site's own pages. The
            #  last entry on that list is "somewhere else", which is the
            #  only case where a typed address is involved at all.
            if spec["kind"] == "link" and chosen == OTHER_LINK:
                chosen = (form.get(name + "__other") or "").strip()
                if chosen and not chosen.startswith(BUTTON_SCHEMES):
                    chosen = "https://" + chosen
            values[name] = chosen
    #  Adding or removing one of a repeated group — the same stepper
    #  pattern the FAQ and Video Gallery tools use.
    op = (form.get("op") or "").strip()
    if op.startswith("add_"):
        prefix = op[4:]
        group = next((e for e in BLOCKS[key]["fields"] if e.get("group") == prefix), None)
        if group:
            used = _group_count(values, group)
            if used < group["count"]:
                slot = used + 1
                for field in group["fields"]:
                    values.setdefault(f"{prefix}{slot}_{field['name']}",
                                      "" if not is_inline(field) else field.get("placeholder")
                                      or _starter_word(field))
                #  A brand new entry needs something in it, or it does not
                #  render at all and the button looks broken.
                first = group["fields"][0]
                values[f"{prefix}{slot}_{first['name']}"] = _starter_word(first)
    elif op.startswith("remove_"):
        prefix = op[7:]
        group = next((e for e in BLOCKS[key]["fields"] if e.get("group") == prefix), None)
        if group:
            used = _group_count(values, group)
            if used > 1:
                for field in group["fields"]:
                    values.pop(f"{prefix}{used}_{field['name']}", None)
    return build(key, values)


def _group_count(values, group):
    """How many of a repeated group actually have something in them."""
    count = 0
    for i in range(1, group["count"] + 1):
        if any((values.get(f"{group['group']}{i}_{f['name']}") or "").strip()
               for f in group["fields"] if is_inline(f)):
            count = i
    return count


def _starter_word(field):
    return field.get("starter") or field["label"]


def group_counts(key, values):
    """{prefix: how many are filled} — for the toolbar's steppers."""
    return {entry["group"]: _group_count(values, entry)
            for entry in BLOCKS[key]["fields"] if "group" in entry}
