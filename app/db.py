import re
import sqlite3
import os
import json
from flask import g, current_app

# DATA_DIR lets Docker mount one persistent volume for everything that must
# survive a container restart (db, secret key). Defaults to the project
# root for local/dev use, unchanged from before this existed.
DATA_DIR = os.environ.get(
    "DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
DB_PATH = os.path.join(DATA_DIR, "cms.db")


#  How long a connection waits for another one to finish writing before
#  giving up with "database is locked". The default is five seconds,
#  which is short: this app writes on paths that are not obviously
#  writes -- the scheduled backup runs from an after_request hook, and
#  installing sixteen template packages happens during a boot that is
#  already serving. Thirty seconds turns a contended moment into a slow
#  request instead of a 500.
BUSY_TIMEOUT_MS = 30_000


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_MS / 1000)
        g.db.row_factory = sqlite3.Row
        #  FIRST, before anything that can be refused. This was set below
        #  the journal_mode switch, which meant the one setting that makes
        #  a contended pragma wait was not yet in effect for the only
        #  pragma here that needs an exclusive lock -- and a first boot,
        #  where two workers migrate and seed at the same moment, died on
        #  it with "database is locked".
        g.db.execute("PRAGMA busy_timeout = %d" % BUSY_TIMEOUT_MS)
        g.db.execute("PRAGMA foreign_keys = ON")
        #  The app runs two gunicorn workers against one database file.
        #  Under the default rollback journal a writer blocks every
        #  reader, so an admin saving a page could 500 a visitor reading
        #  one -- the failure gets likelier the busier the site is, which
        #  is the worst possible shape for a fault. WAL lets readers carry
        #  on through a write; only writers queue against each other.
        #
        #  Set per connection because it is cheap and self-healing: the
        #  mode is a property of the FILE, so a database restored from a
        #  backup, or copied from an older install, is brought into line
        #  the first time it is opened rather than staying slow silently.
        #
        #  Two things to know. WAL wants a real local filesystem -- it
        #  needs shared memory beside the database -- so a data directory
        #  on NFS or an SMB share will refuse it and fall back, which is
        #  why the return value is not asserted on. And it puts two more
        #  files next to cms.db (-wal, -shm); backups go through
        #  VACUUM INTO and SQLite's backup API precisely so that they
        #  capture a consistent database rather than a file that is
        #  missing its log.
        #
        #  Asked before it is set, because SETTING it takes an exclusive
        #  lock on the database and reading it takes nothing. Since the
        #  mode belongs to the file, the answer is already "wal" on every
        #  boot after the first, so the lock is never even requested in
        #  the ordinary case.
        try:
            if (g.db.execute("PRAGMA journal_mode").fetchone()[0] or "").lower() != "wal":
                g.db.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            #  Somebody else is holding the database while it converts, or
            #  the filesystem cannot do WAL at all. Both mean this
            #  connection runs in the old journal mode, which is slower
            #  and completely correct -- and neither is a reason to refuse
            #  to serve the site.
            pass
        #  With WAL, NORMAL syncs at checkpoints rather than at every
        #  commit. The exposure is the last few transactions on a power
        #  cut -- not corruption -- and it is the difference between a
        #  page save feeling instant and feeling like a form submission.
        g.db.execute("PRAGMA synchronous = NORMAL")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# (name, icon, section_type, block_key) — the always-present tools in the
# side Tools panel. block_key refers to admin.BLOCK_LIBRARY starter content;
# None means the section type's own empty default. Kept as plain data here
# (not imported from routes/admin.py) to avoid a circular import.
CONTACT_TOOL_STARTER = ('<div class="cms-contact-tool cms-contact-empty">Add a phone number, '
                        'email, address, or social link by editing this block.</div>')

TEXT_TOOL_STARTER = "<p>New text — click to edit.</p>"
MENU_TOOL_STARTER = '<nav class="cms-menu" data-page-ids="" data-menu-style="plain"></nav>'
BREADCRUMB_TOOL_STARTER = '<nav class="cms-breadcrumb cms-breadcrumb-medium cms-breadcrumb-style-plain">%%CMS_BREADCRUMB%%</nav>'
BANNER_TOOL_STARTER = (
    '<div class="cms-banner cms-banner-placeholder">'
    '<div class="cms-banner-overlay"><h2>Your Headline</h2><p>A short supporting line.</p></div></div>'
)
CARD_TOOL_STARTER = '<div class="cms-card-shape"><p>Write here</p></div>'
DIVIDER_TOOL_STARTER = '<hr class="cms-content-divider cms-divider-solid cms-divider-medium cms-divider-spacing-medium">'

#  Which drawer a tool lives in, in the order the panel groups them. A
#  tool's neighbours are the other tools somebody reaches for at the same
#  moment — Menu next to Breadcrumb, Shop next to Basket — so grouping by
#  this is what "related tools closer together" actually means, not
#  alphabetising or leaving them in whatever order they were built.
#  The names are the ones somebody has already met somewhere else: Text,
#  Media, Layout, Navigation, Sections, Forms, Commerce is close to what
#  WordPress, Wix, Squarespace and Webflow all call these drawers, give or
#  take a synonym. The earlier set was ours alone ("Layout & navigation",
#  "FAQ & search", "Content blocks") and had to be read before it could be
#  used. Single words also matter now that a group's name is printed
#  sideways in a 26px spine — the label has to fit the same height as the
#  tools beside it, so the wording gives way rather than the layout.
TOOL_CATEGORIES = (
    ("text", "Text"),
    ("media", "Media"),
    ("layout", "Layout"),
    ("navigation", "Navigation"),
    ("sections", "Sections"),
    ("forms", "Forms"),
    ("commerce", "Commerce"),
    #  Not a real drawer — nothing is ever seeded into it. It exists so a
    #  tool imported from a Toolkit or a Template Package, which carries
    #  no category of its own, has a legible label instead of blank space
    #  in the category filter.
    ("custom", "Custom"),
)

#  name -> category key, for every builtin tool. Looked up at seed time
#  and by the migration that groups an existing site's tools; a name
#  missing from here (a custom tool) is "custom", never a guess.
TOOL_CATEGORY_BY_NAME = {
    "Text": "text", "FAQ Content": "text", "FAQ Reader": "text",
    "Image": "media", "Media Player": "media", "Video Gallery": "media",
    "Accordion": "media", "File / Download": "media",
    "Divider": "layout", "Card": "layout", "Banner": "layout",
    "Table (Data)": "layout", "Embed": "layout",
    "Menu": "navigation", "Breadcrumb": "navigation", "Search": "navigation",
    "Pricing": "sections", "Testimonial": "sections", "Numbers": "sections",
    "Logo row": "sections", "The team": "sections", "Timeline": "sections",
    "Call to action": "sections", "Blog": "sections",
    "Contact Form": "forms", "Email sign-up": "forms", "Contact Info": "forms",
    "Shop": "commerce", "Buy Button": "commerce", "Basket": "commerce",
}


def tool_category(name):
    return TOOL_CATEGORY_BY_NAME.get(name, "custom")


#  Grouped by TOOL_CATEGORIES, in that order, and within a group in the
#  order somebody would reach for them — this list's own order is a
#  fresh install's default panel order, via the enumerate() below.
DEFAULT_TOOLS = [
    ("Text", "📝", "text", None),
    ("Image", "🖼️", "image", None),
    ("Media Player", "🎬", "media", None),
    ("File / Download", "📎", "file", None),
    ("Table (Data)", "▦", "html", "table"),
    ("Video Gallery", "🎞️", "html", "video-gallery"),
    ("Accordion", "🖼️", "html", "image-accordion"),
    ("Embed", "</>", "html", None),
    ("Menu", "📋", "html", None),
    ("Breadcrumb", "🧭", "html", None),
    ("Banner", "🏞️", "banner", None),
    ("Card", "🃏", "card", None),
    #  Writing questions and showing them are different jobs with
    #  different controls, so they are different tools. Content holds the
    #  questions; Reader shows a chosen set of them from wherever they
    #  were written, with its own display options.
    ("FAQ Content", "❓", "html", "faq"),
    ("FAQ Reader", "📖", "html", "faq-reader"),
    ("Search", "🔍", "html", "search"),
    ("Blog", "📰", "html", "blog"),
    ("Contact Form", "✉️", "html", "contact-form"),
    #  The details themselves — phone, email, address, the social row.
    #  Ten templates ship one in their footer and the editor has always
    #  named it "Contact Info", but it was only ever built by
    #  _apply_footer_layout, so an owner starting a page could not reach
    #  it. A feature of a template that cannot be reproduced from the
    #  tool menu is a feature the tool menu is lying about.
    ("Contact Info", "📇", "html", "contact-info"),
    #  The declared blocks (services/blocks.py). One entry each, and the
    #  form behind each is generated from its own field list.
    ("Pricing", "💲", "html", "block:pricing"),
    ("Testimonial", "❝", "html", "block:testimonial"),
    ("Numbers", "📊", "html", "block:stats"),
    ("Logo row", "🏷️", "html", "block:logos"),
    ("The team", "👥", "html", "block:team"),
    ("Timeline", "🕓", "html", "block:timeline"),
    ("Call to action", "📣", "html", "block:cta"),
    ("Email sign-up", "✉️", "html", "block:newsletter"),
    ("Buy Button", "🛒", "html", "buy-button"),
    ("Shop", "🏬", "html", "shop"),
    ("Basket", "🛒", "html", "basket"),
]


def _add_column(db, table, col, coldef):
    """ALTER TABLE ... ADD COLUMN, safe against the race where gunicorn's
    multiple workers each run _migrate() at boot: the existing-columns check
    and the ALTER aren't atomic across processes, so two workers can both
    decide a column is missing and both try to add it. SQLite raises
    'duplicate column' for the loser instead of a no-op, so swallow exactly
    that instead of pre-checking a column list computed before this call.

    A missing TABLE is also tolerated, for a different reason: these
    ALTERs exist to bring an OLDER database up to date, and on a brand new
    one the table may not have been created yet (it is created further
    down this same function). Refusing to boot in that case would mean a
    fresh install could never start — which is exactly what happened until
    a clean-database test caught it.
    """
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
    except sqlite3.OperationalError as e:
        message = str(e)
        if "duplicate column" not in message and "no such table" not in message:
            raise


def _migrate(db):
    """Add columns introduced after initial release, without touching existing data."""
    # Header/footer chunks used to live in their own JSON-blob columns on
    # `templates` (header_sections/footer_sections), a completely separate
    # system from body `sections` — meaning Divide/Rows/per-cell tools only
    # ever worked in the body. Unify them: header/footer become real
    # `sections` rows too (template_id+zone instead of page_id), sharing
    # every tool/route/template macro body already has. This needs
    # sections.page_id to become nullable, which SQLite can only do via a
    # full table rebuild (no ALTER TABLE ... DROP NOT NULL) — guarded so it
    # only runs once (checked via the template_id column not existing yet)
    # and tolerates the same multi-worker race _add_column does.
    cols = [row[1] for row in db.execute("PRAGMA table_info(sections)").fetchall()]
    if "template_id" not in cols:
        try:
            db.execute(
                """CREATE TABLE sections_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
                    template_id INTEGER REFERENCES templates(id) ON DELETE CASCADE,
                    zone TEXT NOT NULL DEFAULT 'body',
                    type TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    position INTEGER NOT NULL DEFAULT 0,
                    width TEXT NOT NULL DEFAULT 'normal',
                    link_url TEXT,
                    animation TEXT NOT NULL DEFAULT 'none',
                    file_size INTEGER,
                    file_display TEXT NOT NULL DEFAULT 'card',
                    mask_shape TEXT NOT NULL DEFAULT 'none',
                    media_type TEXT NOT NULL DEFAULT 'youtube',
                    bg_color TEXT
                )"""
            )
            db.execute(
                """INSERT INTO sections_new
                    (id, page_id, template_id, zone, type, title, content, position,
                     width, link_url, animation, file_size, file_display, mask_shape, media_type, bg_color)
                   SELECT id, page_id, NULL, 'body', type, title, content, position,
                     width, link_url, animation, file_size, file_display, mask_shape, media_type, bg_color
                   FROM sections"""
            )
            db.execute("DROP TABLE sections")
            db.execute("ALTER TABLE sections_new RENAME TO sections")
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e) and "no such table" not in str(e):
                raise

    _add_column(db, "templates", "sections_migrated", "INTEGER NOT NULL DEFAULT 0")
    for tpl in db.execute("SELECT * FROM templates WHERE sections_migrated = 0").fetchall():
        for zone, col in (("header", "header_sections"), ("footer", "footer_sections")):
            raw = tpl[col] if col in tpl.keys() else None
            try:
                chunks = json.loads(raw) if raw else []
            except ValueError:
                chunks = []
            for i, chunk_html in enumerate(chunks):
                db.execute(
                    "INSERT INTO sections (template_id, zone, type, content, position) VALUES (?, ?, 'html', ?, ?)",
                    (tpl["id"], zone, chunk_html, i),
                )
        db.execute("UPDATE templates SET sections_migrated = 1 WHERE id = ?", (tpl["id"],))
    db.commit()

    for col in (
        "header_html", "footer_html", "layout_json", "header_sections", "footer_sections",
        "palette_json", "color_overrides", "google_fonts_url",
    ):
        _add_column(db, "templates", col, "TEXT")

    _add_column(db, "sections", "width", "TEXT NOT NULL DEFAULT 'normal'")
    _add_column(db, "sections", "link_url", "TEXT")
    _add_column(db, "sections", "animation", "TEXT NOT NULL DEFAULT 'none'")
    _add_column(db, "sections", "file_size", "INTEGER")
    _add_column(db, "sections", "file_display", "TEXT NOT NULL DEFAULT 'card'")
    _add_column(db, "sections", "mask_shape", "TEXT NOT NULL DEFAULT 'none'")
    #  A line under a picture, saying what it is. Its own column rather
    #  than part of `content` (which for an image section IS the file's
    #  URL) or of `title` (which is a heading ABOVE the picture, and reads
    #  as one). Two built-in templates wanted a captioned picture, found
    #  no way to ask for one, and hand-wrote a <figure> into `content` —
    #  where it was used as the img's src, so both shipped a broken image.
    _add_column(db, "sections", "caption", "TEXT")
    #  Corners has three levels, and the middle two are different boxes on
    #  the same row: `corner_style` shapes the SECTION (its background band,
    #  and by inheritance everything in it), `tool_corner_style` shapes just
    #  the tool sitting inside it. So a sharp section can hold a pill card.
    #  A Columns cell keeps its own on the cell dict, since a cell is a tool
    #  too. See the [data-corner-style] block in site-base.css: the value is
    #  a custom property, so the innermost element that sets one wins for
    #  its own subtree, and the levels need no precedence code of their own.
    _add_column(db, "sections", "tool_corner_style", "TEXT")
    #  Depth's tool level, the counterpart to tool_corner_style: a raised
    #  card inside a flat section. Same three tiers as Corners, resolved
    #  the same way — by which element sets --site-shadow closest.
    _add_column(db, "sections", "tool_shadow_style", "TEXT")
    #  How colourful the shades derived from each palette colour are
    #  (SHADE_SPREADS in services/design.py). NULL means "balanced", which
    #  is exactly what every site got before the control existed.
    _add_column(db, "templates", "shade_spread", "TEXT")
    _add_column(db, "sections", "media_type", "TEXT NOT NULL DEFAULT 'youtube'")
    _add_column(db, "sections", "bg_color", "TEXT")
    _add_column(db, "sections", "layout_width", "TEXT NOT NULL DEFAULT 'auto'")
    _add_column(db, "sections", "layout_width_pct", "INTEGER")
    _add_column(db, "sections", "sidebar_width", "TEXT NOT NULL DEFAULT 'auto'")
    _add_column(db, "sections", "sidebar_width_px", "INTEGER")
    _add_column(db, "sections", "content_height_px", "INTEGER")

    _add_column(db, "users", "google_email", "TEXT")
    # One admin per Google account — without this, two admin rows could
    # both claim the same google_email and Google sign-in would always
    # resolve to whichever row SQLite happens to find first.
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_email "
        "ON users(google_email) WHERE google_email IS NOT NULL"
    )
    # Backfill: deployments that were already using the single-admin
    # ADMIN_GOOGLE_EMAIL env var (Google sign-in hardcoded to user id=1)
    # keep working unchanged after upgrading — their existing admin just
    # gets that same email attached as a real row instead of an env-only
    # special case. Only fires once (google_email IS NULL guards re-runs).
    legacy_email = (os.environ.get("ADMIN_GOOGLE_EMAIL") or "").lower().strip()
    if legacy_email:
        db.execute(
            "UPDATE users SET google_email = ? WHERE id = 1 AND google_email IS NULL",
            (legacy_email,),
        )

    #  Which template pack put this page here, if any. Without it,
    #  switching templates leaves the last one's pages behind — a coffee
    #  shop with an Education page — because content is merged per page
    #  and nothing knows which pages stopped being relevant.
    _add_column(db, "pages", "source_template", "TEXT")
    _backfill_page_origins(db)
    _a_copy_owns_its_pages(db)
    _repair_tool_markup(db)
    _strip_stored_editor_markup(db)
    _backfill_faq_ids(db)
    _retire_faq_page_type(db)
    _drop_handwritten_contact_blocks(db)
    _retire_newsletter_consent_box(db)
    _signup_says_a_link_is_coming(db)
    _one_heading_per_legal_document(db)
    _legal_documents_are_text(db)
    _blogs_become_tools(db)
    _blog_posts_drop_page_id(db)
    _contact_pages_become_tools(db)
    _shops_get_a_basket(db)
    _group_tools_by_category(db)
    _shorten_accordion_name(db)
    _cutouts_are_not_corners(db)
    _recategorise_tools_v2(db)
    _add_column(db, "pages", "page_type", "TEXT NOT NULL DEFAULT 'standard'")
    _add_column(db, "pages", "blog_card_style", "TEXT NOT NULL DEFAULT 'grid-3'")
    _add_column(db, "pages", "bg_color", "TEXT")
    #  A picture behind the WHOLE page, not just one section. `bg_attach`
    #  decides whether it sits still while the page scrolls over it or
    #  travels with the content; `bg_surface` decides how the content
    #  survives being on top of it, which is the question that makes the
    #  difference between a usable backdrop and an unreadable one.
    _add_column(db, "pages", "bg_image", "TEXT")
    _add_column(db, "pages", "bg_attach", "TEXT")
    _add_column(db, "pages", "bg_overlay", "TEXT")
    _add_column(db, "pages", "bg_surface", "TEXT")
    _add_column(db, "pages", "meta_description", "TEXT")
    #  Whether a visitor can read this page at all. Every page has the
    #  question; a newsletter is just the page that raises it -- an issue
    #  can be something the list gets and the site never shows, or a page
    #  anybody can read and link to, and that is the owner's call rather
    #  than something its kind decides for them.
    _add_column(db, "pages", "is_public", "INTEGER NOT NULL DEFAULT 1")
    #  When a section last changed, so "send the latest one" can mean
    #  something. Kept by a trigger rather than by the code that writes
    #  sections: there are a dozen routes that update one, and a rule
    #  enforced in the database cannot be forgotten by the thirteenth.
    _add_column(db, "sections", "updated_at", "TEXT")
    db.execute("UPDATE sections SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
    #  SQLite will not take a non-constant DEFAULT on an added column, so
    #  new rows are stamped by a trigger too. Neither trigger recurses:
    #  recursive_triggers is off by default, so the UPDATE inside does not
    #  fire the UPDATE trigger again.
    #
    #  To the MILLISECOND, not CURRENT_TIMESTAMP's whole second. Three
    #  sections written in the same second all carried the same stamp,
    #  and "send the latest" then fell back to whichever had the highest
    #  id -- the newest ADDED rather than the most recently CHANGED,
    #  which is a different thing and the wrong one. A backfilled row
    #  with no milliseconds still sorts correctly against these, since
    #  "…:02" is less than "…:02.123" as text.
    #  ...and a COUNTER beside the clock, because a clock ties.
    #
    #  The millisecond stamp above was the second attempt at this (whole
    #  seconds tied first), and it has the same flaw one decimal place
    #  further down: two writes in the same millisecond carry the same
    #  stamp, and the tie-break falls back to the row id -- the newest
    #  ADDED rather than the most recently CHANGED, which is the precise
    #  thing this was supposed to stop meaning. It stopped being
    #  theoretical the moment the database was put into WAL mode: writes
    #  got fast enough that three of them land inside one millisecond, and
    #  "send the latest section" started picking the wrong one.
    #
    #  A clock cannot fix this at any resolution -- there is always a
    #  faster machine. A counter can: MAX + 1 is strictly greater than
    #  every value already there, including the row's own, so the order is
    #  total and it is genuinely the order things were written in.
    #
    #  updated_at stays: it is the human-readable "when", shown to the
    #  owner. changed_seq is the "in what order", read by the code.
    _add_column(db, "sections", "changed_seq", "INTEGER")
    #  The triggers come off BEFORE the backfill, and this ordering is the
    #  whole of it. The first version of this migration backfilled with
    #  the old timestamp trigger still installed, so every row it wrote
    #  fired that trigger, which set that row's updated_at to "now" --
    #  moving it to the front of the exact ordering the NEXT row was
    #  about to be ranked against. Each row in turn found itself alone at
    #  the end of time and took rank 1: twenty-eight sections numbered 1.
    #  It also rewrote every section's updated_at to the moment of the
    #  migration, which is the half that actually matters: a migration is
    #  not allowed to destroy the data it exists to preserve.
    db.execute("DROP TRIGGER IF EXISTS sections_stamp_insert")
    db.execute("DROP TRIGGER IF EXISTS sections_stamp_update")
    #  Backfill in the order the old stamp implies -- a dense rank over
    #  (updated_at, id), which is exactly what the old comparison did, so
    #  nothing REORDERS on upgrade. It only stops tying from here on.
    #
    #  Re-run whenever the numbering is not a total order, rather than
    #  only when it is missing: that repairs a database upgraded by the
    #  broken version above, which left real values that were simply all
    #  the same. Cheap to ask -- two counts over a table with as many
    #  rows as the site has blocks.
    total, distinct = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT changed_seq) FROM sections").fetchone()
    if total != distinct:
        db.execute("""
            UPDATE sections SET changed_seq = (
                SELECT COUNT(*) FROM sections AS other
                 WHERE IFNULL(other.updated_at, '') < IFNULL(sections.updated_at, '')
                    OR (IFNULL(other.updated_at, '') = IFNULL(sections.updated_at, '')
                        AND other.id <= sections.id))
        """)
    db.execute("""
        CREATE TRIGGER sections_stamp_insert AFTER INSERT ON sections
        BEGIN UPDATE sections
                 SET updated_at = COALESCE(updated_at, strftime('%Y-%m-%d %H:%M:%f', 'now')),
                     changed_seq = (SELECT IFNULL(MAX(changed_seq), 0) + 1 FROM sections)
               WHERE id = NEW.id; END
    """)
    db.execute("""
        CREATE TRIGGER sections_stamp_update AFTER UPDATE ON sections
        BEGIN UPDATE sections
                 SET updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now'),
                     changed_seq = (SELECT IFNULL(MAX(changed_seq), 0) + 1 FROM sections)
               WHERE id = NEW.id; END
    """)
    _add_column(db, "templates", "nav_layout", "TEXT NOT NULL DEFAULT 'topbar'")
    # Per-page layout overrides — NULL/0 means "use the site-wide default"
    # (see get_nav_layout) for every existing page. A page can swap its own
    # header arrangement, or hide a zone the active template otherwise
    # renders everywhere (a landing page with no sidebar on an otherwise
    # sidebar'd site) — the zone's actual section content stays shared
    # per-template, this only toggles whether THIS page shows it.
    _add_column(db, "pages", "nav_layout_override", "TEXT")
    _add_column(db, "pages", "hide_sidebar", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "pages", "hide_sidebar_right", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "pages", "hide_footer", "INTEGER NOT NULL DEFAULT 0")
    # Admin-facing customization layered on top of a template's own fonts/
    # corner-radius, the same override-on-top-of-default relationship
    # color_overrides already has with palette_json. Both are preset-only
    # (FONT_PAIRINGS/SHAPE_PRESETS in services/design.py) — no free-
    # form font name or radius value — so there's no "invalid font string"
    # to guard against, unlike colors' arbitrary hex input.
    _add_column(db, "templates", "font_overrides", "TEXT")
    _add_column(db, "templates", "shape_override", "TEXT")
    # Elevation, the same preset-only override as shape_override above
    # (SHADOW_PRESETS). NULL means "whatever the theme itself does".
    _add_column(db, "templates", "shadow_override", "TEXT")
    # Per-section corner-style override, one level further down the same
    # cascade: theme's own default -> site-wide shape_override above ->
    # this. NULL means "inherit whatever the site currently resolves to" —
    # only Banner and the generic block-html tools (Table/Menu/Divider/
    # Breadcrumb/Video Gallery/Image Accordion/Embed) read it; Card
    # already has its own per-instance shape select (rectangle/rounded/
    # oval/circle/pill) that already overrides the site default via plain
    # CSS specificity, so it doesn't need this too.
    _add_column(db, "sections", "corner_style", "TEXT")
    # Per-section elevation override, the same one-level-further-down
    # cascade corner_style has: theme default -> site-wide
    # shadow_override -> this.
    #  A section can carry a picture behind it, not only a Banner. This is
    #  what lets a whole page alternate between image-backed bands and
    #  quiet ones, which is most of what a distinctive site actually is.
    #  The overlay is stored with it because a photograph behind text
    #  without one is unreadable about half the time, and "about half"
    #  is not a standard anyone can design against.
    _add_column(db, "sections", "bg_image", "TEXT")
    #  After the columns above, not with the other rewrites near the top:
    #  this one READS sections.bg_image/pages.bg_image, and on a brand new
    #  database those columns do not exist until _add_column has made
    #  them.
    _template_pictures_live_in_their_package(db)
    _add_column(db, "sections", "bg_overlay", "TEXT")
    _add_column(db, "sections", "bg_position", "TEXT")
    _add_column(db, "sections", "shadow_style", "TEXT")

    #  ---- Commerce -----------------------------------------------------
    #  Stripe owns money and the payer's details; this side owns what the
    #  payer is OWED. A buyer is identified by the email Stripe collected —
    #  there are no customer accounts and no passwords, so "customers" here
    #  is a ledger key, not a login.
    db.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  provider_ref is the Stripe Checkout Session id, and it is UNIQUE
    #  precisely so a webhook replayed by Stripe (which happens routinely)
    #  cannot create a second order.
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'stripe',
            provider_ref TEXT NOT NULL UNIQUE,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            amount_total INTEGER,
            currency TEXT,
            status TEXT NOT NULL DEFAULT 'paid',
            line_items TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  One row per thing a buyer may do: download a file, or book a
    #  session. `granted` versus `used` is what a download limit and a
    #  session balance both reduce to, which is why they share a table.
    db.execute("""
        CREATE TABLE IF NOT EXISTS entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            ref TEXT,
            granted INTEGER NOT NULL DEFAULT 1,
            used INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  What a given Stripe price actually delivers. Stripe knows the price
    #  exists and that it was paid; it has no idea "10 Coaching Sessions"
    #  should become ten bookable credits. Without this table the webhook
    #  would need a special case per product.
    db.execute("""
        CREATE TABLE IF NOT EXISTS fulfilment_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price_id TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            ref TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            stock INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  What was sent, to how many, and when. A newsletter is a page; this
    #  is the history of it having gone out, which is the one thing the
    #  page itself cannot record.
    db.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            subject TEXT,
            recipients INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  Who asked to hear from you, and what they agreed to when they
    #  did. See services/subscribers.py.
    db.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            token TEXT NOT NULL UNIQUE,
            consent_text TEXT,
            source TEXT,
            ip TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            unsubscribed_at TEXT
        )
    """)
    _confirm_before_subscribed(db)
    #  The files a site sells. Deliberately NOT in static/uploads: that
    #  directory is served to anyone with the URL, which would give a
    #  paid file away the first time a buyer shared the link. See
    #  services/downloads.py.
    db.execute("""
        CREATE TABLE IF NOT EXISTS digital_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stored_name TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            size INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  Which booking a session was spent on. Without this a cancellation
    #  cannot give the session back — the ledger would say "used" forever
    #  while the calendar says the meeting never happened.
    db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL DEFAULT 'calcom',
            provider_uid TEXT NOT NULL UNIQUE,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            entitlement_id INTEGER REFERENCES entitlements(id) ON DELETE SET NULL,
            event_type_ref TEXT,
            starts_at TEXT,
            timezone TEXT,
            status TEXT NOT NULL DEFAULT 'accepted',
            credit_returned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _add_column(db, "bookings", "timezone", "TEXT")

    #  How a buyer with no account reaches what they bought. The raw token
    #  is emailed and never stored — only its hash — so a stolen copy of
    #  this database cannot open anyone's page, the same reasoning a
    #  password reset link follows.
    db.execute("""
        CREATE TABLE IF NOT EXISTS access_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            last_used_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    #  Idempotency for every provider webhook: an event id we have already
    #  processed is dropped rather than replayed.
    db.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_type TEXT,
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (provider, event_id)
        )
    """)
    # Per-section border color, same override-the-default relationship as
    # bg_color above — NULL means no border at all, not "inherit a theme
    # border", since sections don't have a themed border of their own to
    # inherit in the first place.
    _add_column(db, "sections", "border_color", "TEXT")
    # Zone-level (header/footer/sidebar/sidebar_right) bg/border overrides
    # — a template's zone backgrounds have always been hardcoded per
    # theme.css (usually a plain color, sometimes tied to --primary), with
    # no way to change just that one area without recoloring the whole
    # brand palette. One JSON blob (like color_overrides/font_overrides)
    # rather than a column per zone per property, since it's the same
    # override-on-default shape repeated 4x2 times: {"header": {"bg":
    # "#hex", "border": "#hex"}, "footer": {...}, ...}. NULL/missing key
    # means "use whatever this theme's own CSS already resolves to."
    _add_column(db, "templates", "zone_style_overrides", "TEXT")

    db.execute(
        """CREATE TABLE IF NOT EXISTS blogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS content_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '🧰',
            section_type TEXT NOT NULL,
            block_key TEXT,
            starter_content TEXT,
            is_builtin INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT ''
        )"""
    )
    #  An existing database already has this table without the column
    #  above — CREATE TABLE IF NOT EXISTS is a no-op against it.
    _add_column(db, "content_tools", "category", "TEXT NOT NULL DEFAULT ''")
    # A UNIQUE index (not an "is the table empty" check) is what actually
    # makes this seed idempotent: gunicorn's multiple workers each run
    # _migrate() at boot, and "SELECT 1 ... LIMIT 1" is not atomic across
    # processes — two workers can both see an empty table at the same
    # instant and both insert the full DEFAULT_TOOLS list, duplicating
    # every built-in tool. INSERT OR IGNORE against this index means only
    # the first insert of each builtin name ever lands, no matter how many
    # workers race here. Scoped to is_builtin so an admin's own custom
    # tools are never constrained to unique names.
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_content_tools_builtin_name "
        "ON content_tools(name) WHERE is_builtin = 1"
    )
    for i, (name, icon, section_type, block_key) in enumerate(DEFAULT_TOOLS):
        db.execute(
            "INSERT OR IGNORE INTO content_tools "
            "(name, icon, section_type, block_key, is_builtin, position, category) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (name, icon, section_type, block_key, i, tool_category(name)),
        )
    #  The FAQ tool became FAQ Content when reading moved into a tool of
    #  its own. A site must end up with one of them, not both, and this
    #  runs after the seed above has already inserted the new name — so
    #  the leftover is dropped first and the rename only has to cover the
    #  case where the insert did not happen. Both statements are safe in
    #  either order and on a site that has already been through this.
    #  Only ever the builtin row: an admin's own tools are never touched,
    #  and nothing references a tool by id (sections store their content,
    #  and a cell stores its tool's name as text), so dropping the stale
    #  row cannot orphan anything.
    db.execute(
        "DELETE FROM content_tools WHERE is_builtin = 1 AND name = 'FAQ' "
        "AND EXISTS (SELECT 1 FROM content_tools WHERE is_builtin = 1 AND name = 'FAQ Content')"
    )
    db.execute("UPDATE content_tools SET name = 'FAQ Content' WHERE is_builtin = 1 AND name = 'FAQ'")
    # The Text tool had no starter_content, so dropping it into a Columns
    # cell stored an empty string — indistinguishable from the cell never
    # having been touched, since the "Drop a tool here" hint is gated on
    # the cell's content being falsy. Backfill it (builtin only, and only
    # while still empty, so it never clobbers a user's own edit).
    db.execute(
        "UPDATE content_tools SET starter_content = ? WHERE is_builtin = 1 AND name = 'Text' "
        "AND (starter_content IS NULL OR starter_content = '')",
        (TEXT_TOOL_STARTER,),
    )
    #  Dropped on a page it has to show something to click, or the block
    #  is invisible until it has content and nothing can be typed into
    #  it. Builtin only, and only while still empty, so an admin's own
    #  edit is never clobbered.
    db.execute(
        "UPDATE content_tools SET starter_content = ? WHERE is_builtin = 1 AND name = 'Contact Info' "
        "AND (starter_content IS NULL OR starter_content = '')",
        (CONTACT_TOOL_STARTER,),
    )
    # Menu/Breadcrumb/Banner/Card used to be created via their own sidebar
    # forms (pick pages/style/shape, then create) instead of being plain
    # tool tiles — they're now ordinary content_tools rows placed empty and
    # configured afterward in-place. Being added to DEFAULT_TOOLS means the
    # fresh-install seed loop above already inserts a row for each of them,
    # but that INSERT never sets starter_content — so on a truly fresh
    # install these rows exist with a NULL starter_content, exactly the
    # "backfill" case, not an "insert if missing" one. (This was the actual
    # bug behind Menu never resolving as a menu: _resolve_tool_content sees
    # starter_content IS NULL and falls through to plain empty content,
    # so nothing ever marked the section as `is_menu`.)
    for name, icon, section_type, starter in (
        ("Menu", "📋", "html", MENU_TOOL_STARTER),
        ("Breadcrumb", "🧭", "html", BREADCRUMB_TOOL_STARTER),
        ("Banner", "🏞️", "banner", BANNER_TOOL_STARTER),
        ("Card", "🃏", "card", CARD_TOOL_STARTER),
        ("Divider", "➖", "html", DIVIDER_TOOL_STARTER),
    ):
        if not db.execute("SELECT 1 FROM content_tools WHERE is_builtin = 1 AND name = ?", (name,)).fetchone():
            max_pos = db.execute("SELECT COALESCE(MAX(position), -1) FROM content_tools").fetchone()[0]
            db.execute(
                "INSERT INTO content_tools "
                "(name, icon, section_type, block_key, starter_content, is_builtin, position, category) "
                "VALUES (?, ?, ?, NULL, ?, 1, ?, ?)",
                (name, icon, section_type, starter, max_pos + 1, tool_category(name)),
            )
        else:
            db.execute(
                "UPDATE content_tools SET starter_content = ? WHERE is_builtin = 1 AND name = ? "
                "AND (starter_content IS NULL OR starter_content = '')",
                (starter, name),
            )
    # Retired default tools — remove from DBs that were seeded before these
    # were dropped (Table Layout / old table-plain block removed entirely;
    # Cards Row replaced by the per-cell Card background-shape tool).
    db.execute(
        "DELETE FROM content_tools WHERE is_builtin = 1 AND block_key IN "
        "('table-plain', 'cards-2', 'cards-3')"
    )
    # Columns is a section-layout concern (the section's own "Divide"
    # control), not something a tool should offer — remove the leftover
    # builtin tile from DBs seeded before this was corrected.
    db.execute("DELETE FROM content_tools WHERE is_builtin = 1 AND name = 'Columns'")
    # Simplified label — the tool itself doesn't need to enumerate examples.
    db.execute(
        "UPDATE content_tools SET name = 'Embed' WHERE is_builtin = 1 AND name = 'Embed (Cal.com, etc.)'"
    )
    # Renamed to make its scope explicit — for embedding third-party widgets
    # (Cal.com, etc.) specifically, not a general-purpose styling escape
    # hatch (that's what Image/Text/Card/Banner and the rest are for).
    db.execute(
        "UPDATE content_tools SET name = 'Embed (Cal.com, etc.)' "
        "WHERE is_builtin = 1 AND section_type = 'html' AND block_key IS NULL AND name = 'Code / HTML'"
    )

    db.execute(
        """CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            slug TEXT NOT NULL,
            excerpt TEXT,
            content TEXT,
            featured_image TEXT,
            published_at TEXT,
            position INTEGER NOT NULL DEFAULT 0,
            UNIQUE(page_id, slug)
        )"""
    )

    db.execute(
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )

    db.execute(
        """CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0
        )"""
    )
    if not db.execute("SELECT 1 FROM menus LIMIT 1").fetchone():
        cur = db.execute("INSERT INTO menus (name) VALUES ('Main Menu')")
        menu_id = cur.lastrowid
        for i, page in enumerate(db.execute("SELECT id FROM pages ORDER BY nav_order, title")):
            db.execute(
                "INSERT INTO menu_items (menu_id, page_id, position) VALUES (?, ?, ?)",
                (menu_id, page["id"], i),
            )

    # Retired built-in theme-only packages (simple/saas/editorial/corporate/
    # dark-studio/warm) — each one's look has been folded directly into the
    # single content pack it was always paired with 1:1 (see the paired
    # slug each now lives under, e.g. editorial's design is now coaching's
    # own theme.css), so the generic shell is no longer a separate
    # library entry. Their `templates` rows only exist on installs that
    # booted before this change; a fresh install never creates them since
    # app/data/templates/ no longer has these directories. Cascades to
    # their header/sidebar/footer sections (ON DELETE CASCADE); if one
    # happened to be the active template, fall back to whichever template
    # sorts first so the site is never left with zero active templates.
    retired_slugs = ("simple", "saas", "editorial", "corporate", "dark-studio", "warm")
    placeholders = ",".join("?" * len(retired_slugs))
    retired_ids = [
        r["id"] for r in
        db.execute(f"SELECT id FROM templates WHERE slug IN ({placeholders}) AND is_builtin = 1", retired_slugs)
    ]
    if retired_ids:
        id_placeholders = ",".join("?" * len(retired_ids))
        still_active = db.execute(
            f"SELECT 1 FROM templates WHERE id IN ({id_placeholders}) AND is_active = 1", retired_ids
        ).fetchone()
        if still_active:
            fallback = db.execute(
                f"SELECT id FROM templates WHERE id NOT IN ({id_placeholders}) ORDER BY id LIMIT 1", retired_ids
            ).fetchone()
            if fallback:
                db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (fallback["id"],))
        db.execute(f"DELETE FROM templates WHERE id IN ({id_placeholders})", retired_ids)


def _installed_package_dirs():
    """Every installed template's package folder, as (slug, path).

    Where these files actually are at runtime, which is not where a
    couple of readers were looking. `app/data/templates/` is the
    AUTHORING tree: the packager stage builds it into zips and deletes it,
    so on any real install it does not exist, and code globbing it found
    nothing and returned quietly. A missing folder is not an error, so
    nothing ever said so -- see BOW.md, 2026-08-25, where the same mistake
    had silently disabled a guard in `_apply_pack_identity`.

    Installed packages unpack to `static/themes/<slug>/`, builtin and
    imported alike, and carry the same `manifest.json`, `pages/` and
    `media/` the source folder did. Reading from there also covers a
    template somebody uploaded, which the source tree never contained.

    Boot order is worth knowing: `init_db` runs before `_seed` installs
    the packages, so on the very FIRST boot of a brand new install this
    returns nothing. That is harmless -- both callers exist to repair data
    from older versions, and a brand new install has none.
    """
    try:
        root = os.path.join(current_app.static_folder, "themes")
        return sorted(
            (name, os.path.join(root, name))
            for name in os.listdir(root)
            if os.path.isfile(os.path.join(root, name, "manifest.json"))
        )
    except (OSError, RuntimeError):
        return []


def init_db(app):
    with app.app_context():
        db = get_db()
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
        with open(schema_path, "r") as f:
            db.executescript(f.read())
        _migrate(db)
        db.commit()
    app.teardown_appcontext(close_db)


def _backfill_page_origins(db):
    """Works out which template each page came from, by comparing content.

    A site that has had several templates applied is carrying their pages
    — an Education page on a coffee shop — and those pages predate the
    column that would identify them. Matching on the slug alone is not
    enough: several templates ship a "services" page, and so do plenty of
    real businesses.

    So the first section's text is compared against what each pack ships
    for that slug. Demo content matches exactly, because nobody has
    touched it. A page somebody wrote themselves matches nothing and stays
    unattributed — and so does a demo page they have since edited, which
    is the right answer too: once someone has put work into a page it is
    theirs, whatever it started as.

    Runs for pages that are still unattributed, so a site picks up
    whatever it can each time templates change, rather than once ever.
    """
    try:
        shipped = {}   # slug_suffix -> {template_slug: fingerprint of first section}
        for template_slug, pkg_dir in _installed_package_dirs():
            pages_dir = os.path.join(pkg_dir, "pages")
            if not os.path.isdir(pages_dir):
                continue
            for filename in os.listdir(pages_dir):
                try:
                    with open(os.path.join(pages_dir, filename), encoding="utf-8") as handle:
                        spec = json.load(handle)
                except (OSError, ValueError):
                    continue
                suffix, sections = spec.get("slug_suffix"), spec.get("sections") or []
                if suffix and sections:
                    shipped.setdefault(suffix, {})[template_slug] = _fingerprint(sections[0][2])

        for page in db.execute(
            "SELECT id, slug, is_home FROM pages WHERE source_template IS NULL"
        ).fetchall():
            candidates = shipped.get("home" if page["is_home"] else page["slug"])
            if not candidates:
                continue
            first = db.execute(
                "SELECT content FROM sections WHERE page_id = ? ORDER BY position LIMIT 1",
                (page["id"],),
            ).fetchone()
            if not first:
                continue
            mine = _fingerprint(first["content"])
            if not mine:
                continue
            for template_slug, theirs in candidates.items():
                if mine == theirs:
                    db.execute("UPDATE pages SET source_template = ? WHERE id = ?",
                               (template_slug, page["id"]))
                    break
    except sqlite3.Error:
        #  A best-effort tidy, never a reason to fail a boot.
        pass


def _fingerprint(content):
    """Enough of a section's text to tell shipped content from edited."""
    text = re.sub(r"<[^>]+>", " ", content or "")
    return re.sub(r"\s+", " ", text).strip()[:120]


def _repair_tool_markup(db):
    """Rewrites FAQ and accordion sections that were written in a shape
    their own tools cannot read.

    Content generated for the built-in templates used hand-written markup
    instead of the builders those tools use, and the tools read their
    settings from classes it did not carry — cms-faq-item / cms-faq-q /
    cms-faq-a for a question, cms-accordion-style-* for the display. The
    packages were corrected, but a site built from them already has the
    old markup in its own pages, where correcting the package cannot reach
    it: the FAQ toolbar shows nought questions above three that are
    plainly on the page, and saving would replace them with an empty
    default.

    So the sections themselves are repaired, once, in place. Only the
    wrapper changes; every question, answer, picture and caption is
    carried across.
    """
    try:
        rows = db.execute(
            "SELECT id, content FROM sections WHERE content LIKE '%cms-faq%' "
            "OR content LIKE '%cms-image-accordion%'"
        ).fetchall()
    except sqlite3.Error:
        return
    for row in rows:
        content = row["content"] or ""
        fixed = content
        if 'class="cms-faq"' in content and "cms-faq-item" not in content:
            items = []
            for chunk in re.findall(r"<details[^>]*>(.*?)</details>", content, re.S):
                question = re.search(r"<summary[^>]*>(.*?)</summary>", chunk, re.S)
                after = chunk.split("</summary>")[-1]
                answer = re.search(r"<(?:div|p)[^>]*>(.*?)</(?:div|p)>", after, re.S)
                if question:
                    items.append((
                        re.sub(r"<[^>]+>", "", question.group(1)).strip(),
                        re.sub(r"<[^>]+>", "", answer.group(1)).strip() if answer else "",
                    ))
            style = re.search(r'data-style="([^"]+)"', content)
            style = style.group(1) if style else "list"
            style = style if style in ("list", "cards", "plain") else "list"
            group = f' name="cms-faq-{row["id"]}"'
            body = "".join(
                f'<details class="cms-faq-item"{group}>'
                f'<summary class="cms-faq-q">{q}</summary>'
                f'<div class="cms-faq-a">{a}</div></details>' for q, a in items
            )
            fixed = f'<div class="cms-faq cms-faq-style-{style}">{body}</div>'
        elif 'class="cms-image-accordion"' in content and "cms-accordion-style-" not in content:
            panels = re.findall(
                r"background-image:url\('([^']+)'\)[^>]*>\s*<span[^>]*>([^<]*)</span>", content)
            style = re.search(r'data-style="([^"]+)"', content)
            style = style.group(1) if style else "panels"
            style = style if style in ("panels", "carousel", "masonry") else "panels"
            body = "".join(
                f'<div class="cms-accordion-panel" tabindex="0" '
                f"style=\"background-image:url('{url}')\">"
                f'<span class="cms-accordion-caption">{caption}</span></div>'
                for url, caption in panels
            )
            fixed = (f'<div class="cms-image-accordion cms-accordion-style-{style} '
                     f'cms-accordion-lightbox">{body}</div>')
        if fixed != content:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (fixed, row["id"]))


def _strip_stored_editor_markup(db):
    """Cleans editing scaffolding out of content already saved with it.

    Inline block editing stored each block's own outerHTML, and that
    markup carried the editor's contenteditable attributes and its
    cms-block-editable class straight into the database, where they were
    then served to visitors. Fixed at the point of saving; this clears
    what was written before that.
    """
    try:
        from .services.sections import strip_editor_markup
        rows = db.execute(
            "SELECT id, content FROM sections WHERE content LIKE '%contenteditable%' "
            "OR content LIKE '%cms-block-editable%'"
        ).fetchall()
    except (sqlite3.Error, ImportError):
        return
    for row in rows:
        cleaned = strip_editor_markup(row["content"] or "")
        if cleaned != row["content"]:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (cleaned, row["id"]))


def _backfill_faq_ids(db):
    """Moves FAQ blocks written before the document existed onto it.

    An FAQ is one document now. Blocks from before that stored their
    questions as rows and nothing else, so they are converted once —
    faq_document_source turns those rows back into the document they
    always were underneath, and it is stored properly from then on.

    Only blocks that have no document yet. An earlier version of this
    keyed off a marker that document blocks do not carry, so it rebuilt
    them through the old row builder on every boot — quietly throwing away
    the document, the set's name and its introduction each time the app
    restarted. A migration that cannot tell "already done" from "never
    done" is worse than no migration.
    """
    try:
        from .services.sections import (build_faq_document, faq_document_source,
                                        faq_settings)
        rows = db.execute(
            "SELECT id, content FROM sections WHERE content LIKE '%cms-faq-item%' "
            "AND content NOT LIKE '%cms-faq-mirror%' AND content NOT LIKE '%data-faq-md%'"
        ).fetchall()
    except (sqlite3.Error, ImportError):
        return
    for row in rows:
        settings = faq_settings(row["content"] or "")
        document = faq_document_source(row["content"] or "")
        if not document.strip():
            continue
        rebuilt = build_faq_document(document, settings["style"],
                                     settings["one_at_a_time"], settings["name"])
        db.execute("UPDATE sections SET content = ? WHERE id = ?", (rebuilt, row["id"]))


def _confirm_before_subscribed(db):
    """Gives the list a confirmed state, and a token to confirm with.

    Switzerland requires that somebody who is sent advertising actually
    asked for it, and the way that is demonstrated is double opt-in: the
    address is written down, a single mail goes to it with a link, and
    nothing else is ever sent until that link is followed. An address that
    never answers is not a subscriber -- it stays on the list marked
    unconfirmed and is never written to again.

    Rows that predate this stay UNCONFIRMED, which is the strict reading
    and the one this project takes. They were added under a flow that
    never asked twice, so there is no confirmation to point at -- and the
    rule is about being able to show that the person asked, not about
    whether they probably did. Nothing is deleted and nothing is silent:
    they appear on the Subscribers screen as waiting to confirm, and a
    send skips them.

    The alternative -- marking them confirmed because they were live
    yesterday -- was written first and taken back out. It is the sort of
    decision that should be made by the owner of a list, deliberately, and
    not by an upgrade on their behalf while they are not looking.
    """
    _add_column(db, "subscribers", "confirmed_at", "TEXT")
    _add_column(db, "subscribers", "confirm_token", "TEXT")
    #  What an audit asks for is the sequence, not the outcome: when the
    #  invitation went out, and where the answer came from.
    _add_column(db, "subscribers", "confirm_sent_at", "TEXT")
    _add_column(db, "subscribers", "confirm_ip", "TEXT")
    #  The owner's own answer to "is this person a customer", for the
    #  cases the orders table cannot know about: somebody who paid in the
    #  shop, ordered by telephone, or signed up with a different address
    #  from the one they bought with. It sits BESIDE what the orders say
    #  rather than replacing it -- see subscribers.is_customer.
    _add_column(db, "subscribers", "is_customer", "INTEGER NOT NULL DEFAULT 0")
    #  Who a send went to. Without it the history says "sent to 40" and
    #  cannot say whether that was the whole list or the customers on it.
    _add_column(db, "newsletter_sends", "audience", "TEXT")
    _sends_can_be_posts(db)


def _drop_handwritten_contact_blocks(db):
    """Removes the Contact Info blocks that were never Contact Info tools.

    Ten templates shipped a contact page carrying, in its body, a div
    wearing the Contact Info tool's class with three hand-written <p> tags
    inside it -- a name and street, some opening hours, an email. It looked
    like the tool and was not: the real one renders `cms-contact-detail`
    rows, each with its own icon and its own link. This had no icons, no
    links, and could not survive being edited -- opening its panel reads no
    rows out of it, so saving would have replaced the lot with an empty
    block.

    Which makes it the thing CLAUDE.md warns against in as many words:
    markup hand-built to look like a tool instead of composed from one. The
    templates no longer ship it, and the address it carried now travels in
    the footer's real Contacts tool, which is where these sites already
    show the rest of their details.

    Matched precisely rather than by class alone: a block holding real
    `cms-contact-detail` rows is the genuine tool and is left alone.
    """
    rows = db.execute(
        "SELECT id, content FROM sections WHERE content LIKE '%cms-contact-tool%'"
    ).fetchall()
    doomed = [r["id"] for r in rows if "cms-contact-detail" not in (r["content"] or "")]
    for section_id in doomed:
        db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    return len(doomed)


def _a_copy_owns_its_pages(db):
    """Points a forked site's pages at the copy, not at the built-in.

    The first content edit on a site running a built-in takes a copy of it
    -- "Bakery (your copy)" -- so the stock template is never quietly
    modified. The copy took the look, the colours and the header and
    footer with it, but not the one line on each page saying which
    template it arrived with. Those pages went on naming the built-in.

    Nothing broke, but the Dashboard reads that line, and so every page on
    the site was labelled as having come from a template that is "not in
    use" at the exact moment all of them were most in use. The fork sets
    this correctly now; this is for the sites that were forked before it
    did.

    Narrow, and by the one thing that identifies a fork rather than a
    guess: the active template is not a built-in, its name is exactly
    "<something> (your copy)", and "<something>" is the name of a
    built-in whose slug those pages actually name. Anything else is left
    alone -- a template somebody imported and happened to name that way
    still has to match a real built-in by name AND by what the pages say.
    """
    active = db.execute(
        "SELECT slug, name FROM templates WHERE is_active = 1 AND is_builtin = 0"
    ).fetchone()
    if not active or not active["name"].endswith(" (your copy)"):
        return
    parent = db.execute(
        "SELECT slug FROM templates WHERE name = ? AND is_builtin = 1",
        (active["name"][: -len(" (your copy)")],),
    ).fetchone()
    if not parent:
        return
    moved = db.execute(
        "UPDATE pages SET source_template = ? WHERE source_template = ?",
        (active["slug"], parent["slug"]),
    ).rowcount
    if moved:
        db.commit()


def _restore_opening_hours(db):
    """Gives a contact page back the opening hours that were deleted with
    the block holding them.

    `_drop_handwritten_contact_blocks` removed a div that was pretending
    to be the Contact Info tool. That was right -- but the thing it
    removed also carried a business's opening hours, and deleting content
    somebody's visitors were reading is not something a cleanup gets to do
    on the way past. The templates carry those hours again as an ordinary
    Text section; this is what puts them on a site that already existed
    when the block was deleted.

    Narrow on purpose. A page only gets this if it came from a template
    (`source_template`), that template's installed package ships a section
    titled "Opening hours", and the page does not already have one.

    And it happens ONCE, ever, recorded in settings. Not because repeating
    it would duplicate anything -- it checks -- but because an owner who
    deletes the section has said something, and a repair that runs every
    boot would put it back every time and look like the site arguing with
    them. A repair is for the damage it was written for, not a rule the
    site now lives under.
    """
    #  The claim is made FIRST and atomically, because gunicorn runs more
    #  than one worker and each builds the app. A SELECT-then-INSERT is
    #  not atomic across processes: two workers both read "not done", both
    #  add the section, and the page ends up with two. That is not
    #  hypothetical -- it happened here, and it is the same race
    #  `_add_column` documents and the same one that once made a fresh
    #  install print a password that opened nothing. INSERT OR IGNORE has
    #  one winner, and rowcount is how the winner finds out.
    claimed = db.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('opening_hours_restored', '1')"
    ).rowcount
    if not claimed:
        return 0
    import glob
    import json as _json
    import os as _os

    try:
        root = _os.path.join(current_app.static_folder, "themes")
    except RuntimeError:
        return 0
    added = 0
    pages = db.execute(
        "SELECT id, slug, is_home, source_template FROM pages WHERE source_template IS NOT NULL"
    ).fetchall()
    for page in pages:
        if db.execute(
            "SELECT 1 FROM sections WHERE page_id = ? AND title = 'Opening hours' LIMIT 1",
            (page["id"],),
        ).fetchone():
            continue
        suffix = "home" if page["is_home"] else page["slug"]
        wanted = None
        for path in sorted(glob.glob(_os.path.join(root, page["source_template"], "pages", "*.json"))):
            try:
                with open(path, encoding="utf-8") as handle:
                    spec = _json.load(handle)
            except (OSError, ValueError):
                continue
            if spec.get("slug_suffix") != suffix:
                continue
            for section in spec.get("sections") or []:
                if isinstance(section, list) and len(section) > 2 and section[1] == "Opening hours":
                    wanted = section
            break
        if wanted is None:
            continue
        #  Above the contact form, where it was: somebody checks whether
        #  you are open before deciding to write to you.
        form = db.execute(
            "SELECT position FROM sections WHERE page_id = ? AND content LIKE '%cms-contact-form-tool%' "
            "ORDER BY position LIMIT 1", (page["id"],)
        ).fetchone()
        at = form["position"] if form else (db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS n FROM sections WHERE page_id = ?",
            (page["id"],)).fetchone()["n"])
        db.execute("UPDATE sections SET position = position + 1 WHERE page_id = ? AND position >= ?",
                   (page["id"], at))
        db.execute(
            "INSERT INTO sections (page_id, type, title, content, position) VALUES (?, ?, ?, ?, ?)",
            (page["id"], wanted[0], wanted[1], wanted[2], at),
        )
        added += 1
    return added


def _retire_newsletter_consent_box(db):
    """Turns the sign-up form's required tick box back into a line of text.

    The box asked somebody to agree to signing up, on a form whose only
    purpose is signing up, next to a button reading Sign up -- the same act
    demanded twice. What consent needs is that the person is told what they
    are agreeing to and that it can be evidenced, and both of those are the
    wording, which stays: shown on the form, and stored with each row as it
    was worded at the time.

    Parsed rather than pattern-matched, which is the whole reason the first
    attempt did nothing. It looked for `<input type="checkbox"`, and a
    page does not store what the builder wrote -- every save goes through
    BeautifulSoup, which alphabetises attributes and closes empty tags, so
    what is actually on disk reads `<input name="consent" required=""
    type="checkbox" value="1"/>`. The regex could not match it, the
    migration reported nothing to do, and the box stayed exactly where it
    was. Markup that has been through a parser should be matched with one.
    """
    from bs4 import BeautifulSoup

    rows = db.execute(
        "SELECT id, content FROM sections WHERE content LIKE '%cms-newsletter-consent%'"
    ).fetchall()
    changed = 0
    for row in rows:
        content = row["content"] or ""
        soup = BeautifulSoup(content, "html.parser")
        touched = False
        for label in soup.find_all("label", class_="cms-newsletter-consent"):
            words = label.find(attrs={"data-field": "consent"})
            line = soup.new_tag("p")
            line["class"] = "cms-newsletter-consent"
            line["data-field"] = "consent"
            line.string = (words.get_text() if words else label.get_text()).strip()
            label.replace_with(line)
            touched = True
        if touched:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (str(soup), row["id"]))
            changed += 1
    return changed


def _signup_says_a_link_is_coming(db):
    """Rebuilds every Email sign-up so it says a confirmation link is coming.

    Signing up here does not put anybody on a list -- it sends them a mail
    with a link, and only that link does. Somebody who is not told that
    has no reason to go and look for it: they fill the form in, see a
    thank-you, and never hear from the site again, having done nothing
    wrong. That is what happened, which is how this was found.

    A block's markup IS its stored value, so changing the builder reaches
    a page that already exists only if the page is written again. Read
    back through the block's own parser and rebuilt with its own builder,
    never patched as text -- the same lesson `_retire_newsletter_consent_box`
    records: what is on disk has been through BeautifulSoup and does not
    look like what the builder wrote. Anything that does not survive the
    round trip is left exactly as it is.
    """
    from .services import blocks

    rows = db.execute(
        "SELECT id, content FROM sections WHERE content LIKE '%cms-block-newsletter%'"
    ).fetchall()
    changed = 0
    for row in rows:
        content = row["content"] or ""
        try:
            key, values = blocks.parse_block(content)
            if key != "newsletter":
                continue
            rebuilt = blocks.BLOCKS["newsletter"]["build"](values)
            #  The honest test that nothing was lost: read the new markup
            #  back and it has to say what the old markup said.
            key2, values2 = blocks.parse_block(rebuilt)
            if key2 != key or values2 != values:
                continue
        except Exception:  # noqa: BLE001 - a page must never fail to boot over this
            continue
        if rebuilt != content:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (rebuilt, row["id"]))
            changed += 1
    return changed


def _one_heading_per_legal_document(db):
    """Removes the duplicate heading from a legal page already written.

    Putting every document on one page gave each an anchor by prepending
    "<h2 id=slug>Title</h2>" to it -- and each document template already
    opens with its own <h2> saying exactly the same words. So a Terms &
    Conditions page carried "Cancelling and refunds" twice, one line
    under the other, for every document on it.

    The generator is fixed; this is for the pages it already wrote. Only
    a pair is touched, and only when the two say the same thing: the
    first is dropped and its id moves to the one that stays, so links
    into the page keep working.
    """
    from bs4 import BeautifulSoup

    rows = db.execute(
        "SELECT id, content FROM sections WHERE content LIKE '%data-legal-doc%'"
    ).fetchall()
    changed = 0
    for row in rows:
        content = row["content"] or ""
        soup = BeautifulSoup(content, "html.parser")
        touched = False
        for wrapper in soup.select("[data-legal-doc]"):
            headings = wrapper.find_all("h2", recursive=False)
            if len(headings) < 2:
                continue
            first, second = headings[0], headings[1]
            #  Only a true duplicate, and only when they are next to each
            #  other -- two <h2>s further apart are the document's own
            #  structure and none of this migration's business.
            if first.get_text(strip=True) != second.get_text(strip=True):
                continue
            if first.find_next_sibling() is not second:
                continue
            if first.get("id") and not second.get("id"):
                second["id"] = first["id"]
            first.decompose()
            touched = True
        if touched:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (str(soup), row["id"]))
            changed += 1
    return changed


def _legal_documents_are_text(db):
    """Moves a written legal document out of HTML/Embed and into Text.

    The generator inserted these as `type='html'`, so opening a refund
    policy showed the Embed tool -- a `</>` code box, which is this app's
    marker for "third-party script goes here", above somebody's own
    writing. HTML/Embed is for a booking widget or a payment button;
    prose belongs in the Text tool, with bold, italic and a heading
    button like every other piece of writing on the site.

    Only sections carrying the legal marker are touched, so nothing an
    owner made themselves is reclassified underneath them.
    """
    try:
        db.execute(
            "UPDATE sections SET type = 'text' "
            "WHERE type = 'html' AND content LIKE '%data-legal-doc%'"
        )
    except sqlite3.Error:
        pass


def _sends_can_be_posts(db):
    """Lets the record of a send say WHAT was sent, not assume a page.

    `newsletter_sends.page_id` was NOT NULL REFERENCES pages(id), which
    was fine while a newsletter could only be a page. A blog post is not
    a page -- it belongs to a blog -- so that column points at the wrong
    owner the moment a post can be sent. This codebase has met that tell
    before: `blog_posts.page_id` was NOT NULL for the same reason, and
    the table had to be rebuilt then too. See CLAUDE.md, "Features are
    tools, never page types".

    So: a kind and an id. The foreign key goes with it, deliberately --
    the target is polymorphic, and more to the point a record that you
    emailed forty people should survive the page being deleted. That is
    what the record is FOR. Queries that show history join outwards and
    fall back to the subject they stored.
    """
    columns = [r[1] for r in db.execute("PRAGMA table_info(newsletter_sends)").fetchall()]
    if not columns or "page_id" not in columns:
        return
    db.execute("""
        CREATE TABLE newsletter_sends_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_kind TEXT NOT NULL DEFAULT 'page',
            target_id INTEGER NOT NULL,
            subject TEXT,
            recipients INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            audience TEXT,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        INSERT INTO newsletter_sends_new
            (id, target_kind, target_id, subject, recipients, failed, audience, sent_at)
        SELECT id, 'page', page_id, subject, recipients, failed,
               COALESCE(audience, 'all'), sent_at FROM newsletter_sends
    """)
    db.execute("DROP TABLE newsletter_sends")
    db.execute("ALTER TABLE newsletter_sends_new RENAME TO newsletter_sends")


def _retire_faq_page_type(db):
    """Turns any page created as an "FAQ page" back into an ordinary one.

    FAQ was briefly a page type. It is a tool now — an FAQ Content tool on
    a normal page — which is a better fit and the rule this app follows:
    what a page can do comes from what is on it, not from what it was
    declared to be. The pages themselves are untouched; only the label
    that no longer means anything is cleared, so they stop being offered
    behaviour that has moved elsewhere.
    """
    try:
        db.execute("UPDATE pages SET page_type = 'standard' WHERE page_type = 'faq'")
    except sqlite3.Error:
        pass


def _blogs_become_tools(db):
    """Turns each blog-type page into a blog plus a tool that shows it.

    A blog was a kind of page, which made "this site has a blog" and "this
    page is the blog" the same statement: one per site, at one address,
    and nothing else could show its posts. A blog is now a named set of
    posts, and the Blog tool is one place a set is shown — so a site can
    have several, a page can show more than one, and the same blog can
    appear twice without its posts being copied.

    Existing sites are carried across whole. Each blog page becomes a blog
    named after it, keeping its slug — which is what post addresses are
    built from, so every link to every existing post still works — and
    gains a Blog tool at the foot of the page it used to be, carrying the
    card style that page had chosen. The page itself becomes ordinary.
    """
    try:
        _add_column(db, "blog_posts", "blog_id", "INTEGER")
        pages = db.execute("SELECT * FROM pages WHERE page_type = 'blog'").fetchall()
    except sqlite3.Error:
        return
    from .services.blog import build_blog, create_blog
    for page in pages:
        try:
            existing = db.execute("SELECT id FROM blogs WHERE slug = ?", (page["slug"],)).fetchone()
            blog_id = existing["id"] if existing else create_blog(db, page["title"], page["slug"])
            db.execute("UPDATE blog_posts SET blog_id = ? WHERE page_id = ? AND blog_id IS NULL",
                       (blog_id, page["id"]))
            #  Only if the page is not already showing this blog — the
            #  migration must be safe to run again.
            has_tool = db.execute(
                "SELECT 1 FROM sections WHERE page_id = ? AND content LIKE ?",
                (page["id"], f'%data-blog-id="{blog_id}"%'),
            ).fetchone()
            if not has_tool:
                pos = db.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 p FROM sections WHERE page_id = ?",
                    (page["id"],),
                ).fetchone()["p"]
                style = None
                try:
                    style = page["blog_card_style"]
                except (IndexError, KeyError):
                    style = None
                db.execute(
                    "INSERT INTO sections (page_id, type, title, content, position) "
                    "VALUES (?, 'html', '', ?, ?)",
                    (page["id"], build_blog(blog_id, style or "cards"), pos),
                )
            db.execute("UPDATE pages SET page_type = 'standard' WHERE id = ?", (page["id"],))
        except sqlite3.Error:
            continue


def _blog_posts_drop_page_id(db):
    """Rebuilds blog_posts around the blog it belongs to, not a page.

    page_id was NOT NULL, which stopped being true the moment posts
    belonged to a blog instead: writing a post raised an integrity error
    on a column that no longer meant anything. SQLite cannot relax a
    constraint in place, so the table is rebuilt — the standard rename
    dance, inside the migration transaction, so a failure leaves the old
    table untouched rather than half a new one.

    Runs after _blogs_become_tools, which is what fills blog_id in. Any
    post it could not account for — one whose page was deleted, say — is
    given a blog of its own rather than dropped, because a post nobody can
    reach is still somebody's writing and losing it silently would be the
    worst outcome here.
    """
    try:
        cols = [r["name"] for r in db.execute("PRAGMA table_info(blog_posts)")]
    except sqlite3.Error:
        return
    if "page_id" not in cols or "blog_id" not in cols:
        return  # already rebuilt, or too early to

    from .services.blog import create_blog
    try:
        orphans = db.execute(
            "SELECT DISTINCT page_id FROM blog_posts WHERE blog_id IS NULL"
        ).fetchall()
        for row in orphans:
            page = db.execute("SELECT title, slug FROM pages WHERE id = ?", (row["page_id"],)).fetchone()
            name = page["title"] if page else "Recovered posts"
            slug = page["slug"] if page else "recovered-posts"
            existing = db.execute("SELECT id FROM blogs WHERE slug = ?", (slug,)).fetchone()
            blog_id = existing["id"] if existing else create_blog(db, name, slug)
            db.execute("UPDATE blog_posts SET blog_id = ? WHERE page_id = ? AND blog_id IS NULL",
                       (blog_id, row["page_id"]))

        db.execute(
            """CREATE TABLE blog_posts_rebuilt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blog_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                slug TEXT NOT NULL,
                excerpt TEXT,
                content TEXT,
                featured_image TEXT,
                published_at TEXT,
                position INTEGER NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            "INSERT INTO blog_posts_rebuilt "
            "(id, blog_id, title, slug, excerpt, content, featured_image, published_at, position) "
            "SELECT id, blog_id, title, slug, excerpt, content, featured_image, published_at, "
            "COALESCE(position, 0) FROM blog_posts WHERE blog_id IS NOT NULL"
        )
        db.execute("DROP TABLE blog_posts")
        db.execute("ALTER TABLE blog_posts_rebuilt RENAME TO blog_posts")
    except sqlite3.Error:
        #  Leave the old table exactly as it was; the next boot tries again.
        try:
            db.execute("DROP TABLE IF EXISTS blog_posts_rebuilt")
        except sqlite3.Error:
            pass


def _contact_pages_become_tools(db):
    """Gives each contact page the form it used to draw automatically.

    A contact page rendered a form because of what it was, so nothing on
    the page said the form was there. Now that the form is a tool, the
    page has to actually carry one — otherwise a site would come back from
    this change with its contact form silently gone, which is the sort of
    thing an owner discovers from a customer who could not reach them.

    The tool is added at the end, after whatever the page already says.
    """
    try:
        pages = db.execute("SELECT id FROM pages WHERE page_type = 'contact'").fetchall()
    except sqlite3.Error:
        return
    for page in pages:
        try:
            has_form = db.execute(
                "SELECT 1 FROM sections WHERE page_id = ? AND content LIKE '%cms-contact-form-tool%'",
                (page["id"],),
            ).fetchone()
            if not has_form:
                pos = db.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 p FROM sections WHERE page_id = ?",
                    (page["id"],),
                ).fetchone()["p"]
                db.execute(
                    "INSERT INTO sections (page_id, type, title, content, position) "
                    "VALUES (?, 'html', '', '<div class=\"cms-contact-form-tool\"></div>', ?)",
                    (page["id"], pos),
                )
            db.execute("UPDATE pages SET page_type = 'standard' WHERE id = ?", (page["id"],))
        except sqlite3.Error:
            continue


def _group_tools_by_category(db):
    """Backfills a category onto every tool, and groups the panel by it
    once.

    A tool's category tells the Tools panel's filter and default sort what
    drawer it lives in — Menu next to Breadcrumb, Shop next to Basket —
    which is what makes "related tools closer together" true by default
    rather than by luck of insertion order.

    Categorising is safe to redo forever: it only ever fills in a blank.
    Reordering the panel's `position` values is not — an admin may have
    already dragged their own order, and re-grouping on every boot would
    silently undo that. So the reorder happens exactly once, guarded by a
    settings flag, the same pattern the nav_layout carry-over above uses.
    """
    try:
        for row in db.execute(
            "SELECT id, name, is_builtin FROM content_tools WHERE category = '' OR category IS NULL"
        ).fetchall():
            category = tool_category(row["name"]) if row["is_builtin"] else "custom"
            db.execute("UPDATE content_tools SET category = ? WHERE id = ?", (category, row["id"]))

        already_grouped = db.execute(
            "SELECT 1 FROM settings WHERE key = 'tools_grouped_v1'"
        ).fetchone()
        if already_grouped:
            return

        order = [key for key, _ in TOOL_CATEGORIES]
        builtin = db.execute(
            "SELECT id, name, category FROM content_tools WHERE is_builtin = 1 ORDER BY position, id"
        ).fetchall()

        def sort_key(row):
            #  Within a category, DEFAULT_TOOLS' own order — the order
            #  somebody would reach for them — with anything DEFAULT_TOOLS
            #  does not know about (a retired tool still on an old site)
            #  kept at the end of its group rather than crashing.
            names = [n for n, *_ in DEFAULT_TOOLS]
            within = names.index(row["name"]) if row["name"] in names else len(names)
            cat_rank = order.index(row["category"]) if row["category"] in order else len(order)
            return (cat_rank, within)

        for position, row in enumerate(sorted(builtin, key=sort_key)):
            db.execute("UPDATE content_tools SET position = ? WHERE id = ?", (position, row["id"]))

        #  Custom tools follow, keeping whatever relative order they
        #  already had — nothing about a category grouping should
        #  reshuffle tools somebody built themselves.
        custom = db.execute(
            "SELECT id FROM content_tools WHERE is_builtin = 0 ORDER BY position, id"
        ).fetchall()
        for offset, row in enumerate(custom):
            db.execute("UPDATE content_tools SET position = ? WHERE id = ?",
                       (len(builtin) + offset, row["id"]))

        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tools_grouped_v1', '1')")
    except sqlite3.Error:
        pass


def _recategorise_tools_v2(db):
    """Move an existing site onto the revised category names.

    The drawers were renamed and their contents redistributed (see
    TOOL_CATEGORIES) — "Content" split into Text, Media and Layout,
    "FAQ & search" dissolved into Text and Navigation, and so on. An
    existing site's tools carry the old keys, which are no longer in the
    list, so without this they would all fall through to "Custom".

    Only builtin tools are touched, and only their category: a custom
    tool stays custom, and nobody's dragged panel order is disturbed —
    the panel's Grouped switch regroups on demand, so the stored
    positions can stay as they are. Guarded by its own flag so it runs
    once and never argues with a later change.
    """
    try:
        if db.execute("SELECT 1 FROM settings WHERE key = 'tools_categories_v2'").fetchone():
            return
        for row in db.execute(
            "SELECT id, name FROM content_tools WHERE is_builtin = 1"
        ).fetchall():
            db.execute("UPDATE content_tools SET category = ? WHERE id = ?",
                       (tool_category(row["name"]), row["id"]))
        db.execute("UPDATE content_tools SET category = 'custom' WHERE is_builtin = 0")

        #  Re-sort as well as re-label. The panel renders a heading each
        #  time the category changes as it walks the list in stored order,
        #  so tools have to be CONTIGUOUS by category or one drawer opens
        #  several times over — reassigning the labels alone turned eight
        #  groups into fourteen, "Text ... Media ... Layout ... Media"
        #  again. The old order was itself the old grouping, so there is
        #  nothing of an admin's own here to preserve.
        order = [key for key, _ in TOOL_CATEGORIES]
        names = [n for n, *_ in DEFAULT_TOOLS]

        def sort_key(row):
            cat = tool_category(row["name"])
            cat_rank = order.index(cat) if cat in order else len(order)
            within = names.index(row["name"]) if row["name"] in names else len(names)
            return (cat_rank, within)

        builtin = db.execute(
            "SELECT id, name FROM content_tools WHERE is_builtin = 1 ORDER BY position, id"
        ).fetchall()
        for position, row in enumerate(sorted(builtin, key=sort_key)):
            db.execute("UPDATE content_tools SET position = ? WHERE id = ?", (position, row["id"]))
        for offset, row in enumerate(db.execute(
            "SELECT id FROM content_tools WHERE is_builtin = 0 ORDER BY position, id"
        ).fetchall()):
            db.execute("UPDATE content_tools SET position = ? WHERE id = ?",
                       (len(builtin) + offset, row["id"]))

        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tools_categories_v2', '1')")
        db.commit()
    except sqlite3.Error:
        pass


def _template_pictures_live_in_their_package(db):
    """Point existing content at the pictures where they live now:
    /static/themes/<slug>/media/<slug>-<name>.

    A template's pictures used to sit in one shared folder in the app,
    under whatever name they were given — some of them prefixed with only
    part of their template's name ("hair-band-1" for hair-salon). That
    made a template an incomplete thing in two ways: export it and the zip
    had its words but not its photographs, and the only reason an import
    looked right was that the receiving install happened to ship the same
    folder; and a picture called "banner" could only ever mean one
    template's banner. They live in their own package now, named after it.

    Pages already built from a template still hold the old URL, and there
    is nothing behind it any more, so without this an existing site comes
    back from an upgrade with every template picture broken. The owner's
    own uploads are untouched — they were never in that folder.
    """
    columns = (("sections", "content"), ("sections", "bg_image"), ("pages", "bg_image"))
    installed = _installed_package_dirs()
    if not installed:
        return

    #  Only the two forms this rewrites: the old shared folder, and a
    #  template's own folder still holding a shortened name. Anything
    #  else, including every picture the owner uploaded themselves, is
    #  none of this function's business — so on a site that has already
    #  been through it, or one that never saw the old layout, it looks
    #  once and does nothing.
    stale = ["%/static/img/templates/%"]
    for slug, _pkg_dir in installed:
        for short in {slug.split("-")[0], slug.replace("-", "")} - {slug}:
            stale.append(f"%/themes/{slug}/media/{short}-%")
    if not any(db.execute(f"SELECT 1 FROM {t} WHERE {c} LIKE ? LIMIT 1", (like,)).fetchone()
               for t, c in columns for like in stale):
        return
    for slug, pkg_dir in installed:
        media = os.path.join(pkg_dir, "media")
        if not os.path.isdir(media):
            continue
        for fname in sorted(os.listdir(media)):
            new = f"/static/themes/{slug}/media/{fname}"
            #  What this file used to be called. Two shortened prefixes
            #  were in use — the slug's first word (hair-salon -> "hair")
            #  and the slug with its hyphen closed up (self-help ->
            #  "selfhelp") — and each could appear either in the old
            #  shared folder or, for a site upgraded once already, in this
            #  template's own folder under the old name.
            names = {fname}
            if fname.startswith(slug + "-"):
                rest = fname[len(slug) + 1:]
                names |= {f"{slug.split('-')[0]}-{rest}", f"{slug.replace('-', '')}-{rest}"}
            olds = {f"/static/img/templates/{n}" for n in names}
            olds |= {f"/static/themes/{slug}/media/{n}" for n in names}
            for old in sorted(olds - {new}):
                for table, column in columns:
                    db.execute(
                        f"UPDATE {table} SET {column} = REPLACE({column}, ?, ?) WHERE {column} LIKE ?",
                        (old, new, f"%{old}%"),
                    )
    db.commit()


def _cutouts_are_not_corners(db):
    """mask_shape 'rounded'/'square' -> corner_style 'rounded'/'sharp'.

    The picture "Shape / cutout" list used to carry two entries that were
    not cutouts at all but corner styles, at values of their own: a
    "Rounded" picture was a fixed 16px whatever the site's Corners setting
    said, because the mask rule wrote a literal radius and the Corners
    setting is a variable nothing in that rule read. So the same word
    meant two different things depending on which control you reached
    for, and one of them silently beat the other.

    Corners now owns every radius in the app, so those two move across to
    it and the cutout list keeps only the shapes a radius genuinely
    cannot express. An existing site's pictures keep the look they had —
    'rounded' becomes the Rounded corner style (22px rather than 16px,
    the one value that word now means) and 'square' becomes Sharp, which
    is what it did.

    Only touches sections that have no corner_style of their own, so an
    admin who had already set one keeps it.
    """
    try:
        db.execute(
            "UPDATE sections SET corner_style = 'rounded', mask_shape = 'none' "
            "WHERE mask_shape = 'rounded' AND (corner_style IS NULL OR corner_style = '')"
        )
        db.execute(
            "UPDATE sections SET corner_style = 'sharp', mask_shape = 'none' "
            "WHERE mask_shape = 'square' AND (corner_style IS NULL OR corner_style = '')"
        )
        #  One that already had a corner style keeps it; the retired cutout
        #  just stops being a second opinion.
        db.execute(
            "UPDATE sections SET mask_shape = 'none' "
            "WHERE mask_shape IN ('rounded', 'square')"
        )
        db.commit()
    except sqlite3.Error:
        pass

def _shorten_accordion_name(db):
    """"Image Accordion" -> "Accordion".

    The tool's name is what a chip in the Tools panel has to fit, and this
    was the only one long enough to need two lines, which made it the odd
    one out in a grid of otherwise identical tiles. Nothing is lost by the
    shorter name: there is no other accordion, and the icon already says
    it is about pictures. The block_key ("image-accordion") is the tool's
    real identity and is deliberately NOT touched — only the label.

    Matched on the old name, so it runs once and leaves a tool an admin
    has since renamed themselves alone.
    """
    try:
        db.execute(
            "UPDATE content_tools SET name = 'Accordion' WHERE name = 'Image Accordion'"
        )
        db.commit()
    except sqlite3.Error:
        pass


def _shops_get_a_basket(db):
    """Puts a basket in the header of any site that sells something.

    A shop without a visible basket is the one arrangement no shopping
    site uses: someone who has put something aside needs to see that it is
    still there while they carry on looking, and a link at the foot of the
    products page is not that.

    Added to the header zone, so it is at the top of every page. Only for
    sites that actually have a Shop tool, and only once — a site that has
    a basket already, wherever it was put, is left alone, including one
    where the owner deliberately moved it somewhere else.
    """
    try:
        from .services.cart import build_basket
        has_shop = db.execute(
            "SELECT 1 FROM sections WHERE content LIKE '%cms-shop%' LIMIT 1"
        ).fetchone()
        has_basket = db.execute(
            "SELECT 1 FROM sections WHERE content LIKE '%cms-basket%' LIMIT 1"
        ).fetchone()
    except (sqlite3.Error, ImportError):
        return
    if not has_shop or has_basket:
        return
    template = db.execute("SELECT id FROM templates WHERE is_active = 1").fetchone()
    if not template:
        return
    try:
        position = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 p FROM sections "
            "WHERE template_id = ? AND zone = 'header'", (template["id"],)
        ).fetchone()["p"]
        db.execute(
            "INSERT INTO sections (page_id, template_id, zone, type, title, content, position) "
            "VALUES (NULL, ?, 'header', 'html', '', ?, ?)",
            (template["id"], build_basket(), position),
        )
    except sqlite3.Error:
        pass
