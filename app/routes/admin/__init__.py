"""Admin blueprint package. `bp` and the constants/helpers below are shared
across the domain route modules imported at the bottom of this file (see
CLAUDE.md's Template Packages / no-monolith rules) — each of those modules
does `from . import bp` plus whichever of these names it needs."""
import os
import re
import glob
import json
import uuid
import datetime
from html import escape as html_escape
from flask import Blueprint, request, redirect, url_for, flash, jsonify, current_app

from ...db import get_db
from ..auth import login_required
from ... import assistant
from ... import icons
from ...services import legal
from ...services.menu import _build_menu_links_html
from ...services.sections import build_contact_tool, LEGACY_KIND_ICONS

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Page slugs render at the bare /<slug> URL (see routes/public.py's `page`
# route) — these top-level path segments are already claimed by other
# blueprints/routes, so a page slug matching one would silently be
# unreachable at its own URL (the other route always wins first).
#  Addresses a page may not take, because something else already answers
#  at exactly that path.
#
#  "blog" and "contact" are deliberately NOT here. They read like they
#  should be, but the routes that made them look taken are
#  /blog/<blog>/<post> and /contact/<page>/submit — neither of which a
#  page at /blog or /contact can shadow. Reserving them meant every
#  template installed its contact page as "contact-2", which is a wrong
#  address on a fresh install of nearly every built-in template.
RESERVED_SLUGS = {
    "admin", "auth", "static", "page", "login", "logout",
    "account", "home", "api", "favicon.ico", "robots.txt", "sitemap.xml",
}

#  The fixed sets of design choices an admin picks from — colour
#  schemes, font pairings, fonts, corner styles, depth. They live in
#  services/design.py because they are data, not routing; re-exported
#  here so the many `from . import SHAPE_PRESETS` call sites keep
#  working unchanged.
from ...services.design import (  # noqa: F401  (re-exported)
    COLOR_PRESETS, FONT_PAIRINGS, GOOGLE_FONT_CHOICES, SHAPE_PRESETS, SHADOW_PRESETS,
    COMPOSITION_PRESETS,
    SHAPE_SMALL_SCREEN_MAX,
    SHADE_SPREADS,
    _google_fonts_stylesheet_url,
)



@bp.context_processor
def inject_admin_theme():
    return {
        "assistant_configured": assistant.is_configured(get_db()),
        "content_tools": _list_tools(get_db()),
        # source/style are unused now (the SVG-icon-set design's params —
        # see icons.py), kept only because every icon_svg()/icon_choices_for()
        # call site already expects them.
        "icon_choices": icons.icon_choices_for(),
    }







def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or uuid.uuid4().hex[:8]


def wants_json():
    return request.headers.get("X-Inline-Edit") == "1"


def _redirect_next(default_endpoint, anchor=None, **default_kwargs):
    next_url = request.form.get("next")
    if not (next_url and next_url.startswith("/") and not next_url.startswith("//")):
        # `next` is missing/unsafe. These actions come from the LIVE editor
        # (View Site), so landing on the admin dashboard is jarring and reads
        # as a bug — a header/footer section has no page_id, which used to
        # fall straight to the dashboard and was exactly how "dropping a tool
        # into the footer opened the admin page" happened. Prefer the public
        # page the request came FROM, and only fall back to an admin screen
        # when there is no safe referrer at all.
        next_url = _safe_editor_referrer()
        if not next_url:
            if "page_id" in default_kwargs and default_kwargs["page_id"] is None:
                next_url = url_for("admin.dashboard")
            else:
                next_url = url_for(default_endpoint, **default_kwargs)
    if anchor:
        next_url = f"{next_url}#{anchor}"
    return redirect(next_url)


def _safe_editor_referrer():
    """The path the request came from, if it is a same-origin, non-admin page
    (i.e. the live editor). Used so a section action never dumps the admin on
    the dashboard when its `next` is missing. Returns None if there is no such
    referrer."""
    ref = request.referrer
    if not ref:
        return None
    try:
        from urllib.parse import urlparse
        here = urlparse(request.host_url)
        there = urlparse(ref)
    except ValueError:
        return None
    if (there.scheme, there.netloc) != (here.scheme, here.netloc):
        return None
    path = there.path or "/"
    if path.startswith("/admin"):
        return None
    return path + (("?" + there.query) if there.query else "")



# ---------- Undo ----------
# A short global stack (3 deep) covering section-structure changes —
# reorders, a tool dropped onto a section that overwrites what was
# there, delete/clear/divide. Every mutating route that can lose real
# work calls _undo_snapshot with the CURRENT state right before it makes
# its change; Ctrl+Z (see inline-editor.js) posts to /admin/undo, which
# pops the newest snapshot and replaces that scope's sections with
# exactly what they were.
UNDO_STACK_DEPTH = 3


def _undo_snapshot(db, description, page_id=None, template_id=None, zone=None, next_url=None):
    if page_id is not None:
        rows = db.execute("SELECT * FROM sections WHERE page_id = ?", (page_id,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM sections WHERE template_id = ? AND zone = ?", (template_id, zone)
        ).fetchall()
    sections_json = json.dumps([dict(r) for r in rows])
    db.execute(
        "INSERT INTO undo_log (description, page_id, template_id, zone, next_url, sections_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (description, page_id, template_id, zone, next_url, sections_json),
    )
    old_ids = [
        r["id"] for r in db.execute(
            "SELECT id FROM undo_log ORDER BY id DESC LIMIT -1 OFFSET ?", (UNDO_STACK_DEPTH,)
        ).fetchall()
    ]
    if old_ids:
        db.execute(f"DELETE FROM undo_log WHERE id IN ({', '.join('?' for _ in old_ids)})", old_ids)


@bp.route("/undo", methods=["POST"])
@login_required
def undo():
    db = get_db()
    row = db.execute("SELECT * FROM undo_log ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        if wants_json():
            return jsonify({"ok": False, "error": "Nothing to undo."})
        flash("Nothing to undo.", "error")
        return _redirect_next("admin.dashboard")

    if row["page_id"] is not None:
        db.execute("DELETE FROM sections WHERE page_id = ?", (row["page_id"],))
    else:
        db.execute(
            "DELETE FROM sections WHERE template_id = ? AND zone = ?", (row["template_id"], row["zone"])
        )
    for s in json.loads(row["sections_json"]):
        cols = list(s.keys())
        db.execute(
            f"INSERT INTO sections ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [s[c] for c in cols],
        )
    db.execute("DELETE FROM undo_log WHERE id = ?", (row["id"],))
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "next_url": row["next_url"]})
    flash(f'Undid: {row["description"]}.', "success")
    if row["next_url"]:
        return redirect(row["next_url"])
    return _redirect_next("admin.dashboard")



NAV_LAYOUTS = {
    # Purely how the *header zone's own content* is arranged — not a
    # position for a sidebar, which isn't a "layout" choice at all now:
    # it's its own always-available zone (like header/footer), present
    # whenever it has sections in it and empty otherwise. Zones start
    # (and stay) empty until the admin manually adds a section — no
    # auto-seeded content, ever. See the zone wiring in page.html.
    "topbar": ("Top bar", "Classic — left-aligned menu. Width comes from the section width picker, same as any other section."),
    "split": ("Split", "Menu links spread edge-to-edge (first left, last right) — common on SaaS/product sites."),
    "centered": ("Centered", "Menu links centered — editorial/magazine feel."),
    "minimal": ("Minimal (hamburger)", "Hidden behind a ☰ toggle button (top-right) until clicked — same in edit and live view."),
}


def get_nav_layout(db):
    """Where the logo/nav sit — a single site-wide choice, independent of
    which theme is active (a layout is reusable structure, not something
    that belongs to one theme — any theme can be paired with any layout).
    Was briefly a per-template column; moved here after using it showed
    the same 5 choices repeated identically under every theme in the
    Dashboard, which was just confusing duplication of one global setting."""
    row = db.execute("SELECT value FROM settings WHERE key = 'nav_layout'").fetchone()
    layout = row["value"] if row else "topbar"
    return layout if layout in NAV_LAYOUTS else "topbar"



# ---------- Sidebar layout presets ----------
# Structural starting points built from patterns real sites actually use —
# not decoration, a genuine navigational shape: a full-height left nav
# rail (SaaS app shell — Notion/Linear/Vercel-style dashboards), a dual
# rail with page nav on the left and an on-page/"On this page" outline on
# the right (developer docs — Stripe/GitBook-style), and a right-hand
# widgets rail alongside normal body content (classic blog/publisher
# layout — WordPress default themes, most news sites). Applying one just
# inserts a single, completely ordinary Menu tool section into the
# relevant zone(s) of the ACTIVE template — the exact same section a
# manual "+" click would create, with sensible style/direction/reach
# already chosen — never anything the admin can't immediately see, edit,
# resize, or delete like any other section. Never overwrites a zone that
# already has a section, matching the single-section-per-rail rule.
SIDEBAR_LAYOUT_PRESETS = {
    "none": {
        "name": "No sidebar",
        "description": "Full-width content, no rails — the default single-column page.",
        "sides": {},
    },
    "app-shell": {
        "name": "App shell",
        "description": "Full-height left nav rail — the shape behind most modern SaaS dashboards (Notion, Linear, Vercel).",
        "sides": {"sidebar": {"reach": "full", "align": "left"}},
    },
    "docs": {
        "name": "Documentation",
        "description": "Page nav on the left, an on-page outline on the right — the shape most developer docs use (Stripe, GitBook).",
        "sides": {
            "sidebar": {"reach": "auto", "align": "left"},
            "sidebar_right": {"reach": "auto", "align": "left"},
        },
    },
    "publisher": {
        "name": "Publisher",
        "description": "A widgets rail on the right beside normal body content — the classic blog/news layout most WordPress themes ship with.",
        "sides": {"sidebar_right": {"reach": "auto", "align": "left"}},
    },
    "sidebar-blog": {
        "name": "Sidebar blog",
        "description": "A single body-height nav rail on the left beside the content — the other classic WordPress arrangement, categories/pages on the left instead of the right.",
        "sides": {"sidebar": {"reach": "auto", "align": "left"}},
    },
    "workspace": {
        "name": "Workspace",
        "description": "Full-height rails on both sides — navigation on the left, a details/inspector panel on the right, content in between. The shape behind tools like Figma and most IDEs.",
        "sides": {
            "sidebar": {"reach": "full", "align": "left"},
            "sidebar_right": {"reach": "full", "align": "left"},
        },
    },
}



def _apply_sidebar_layout(db, template_id, preset_key, page_ids=None, force=True):
    """Shared by the Page Layout picker route and demo-pack loading —
    the latter passes `page_ids` (that pack's own pages, in pack order)
    so a demo's rail menu matches its own site, not every page across
    the whole install. `page_ids=None` keeps the route's original
    "every real page" behavior. Returns (applied, skipped) zone lists."""
    preset = SIDEBAR_LAYOUT_PRESETS[preset_key]
    if page_ids is not None:
        rows = db.execute(
            f"SELECT id FROM pages WHERE id IN ({', '.join('?' for _ in page_ids)})", page_ids
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        pages = [by_id[pid] for pid in page_ids if pid in by_id]
    else:
        pages = db.execute("SELECT id FROM pages ORDER BY nav_order, title").fetchall()
    items = [{"key": f"p{p['id']}", "type": "page", "id": p["id"], "icon": "", "parent": None} for p in pages]
    applied, skipped = [], []
    # A preset defines the WHOLE sidebar structure, not just an addition —
    # e.g. switching from Workspace (both rails) to Sidebar blog (left
    # only) must actually remove the right rail Workspace left behind, or
    # the result is neither preset, just a mix of whatever was clicked
    # last. Clear any sidebar zone this preset does NOT use too, same
    # force-gated confirmation as replacing the ones it does.
    for other_zone in ("sidebar", "sidebar_right"):
        if other_zone in preset["sides"]:
            continue
        if db.execute(
            "SELECT 1 FROM sections WHERE template_id = ? AND zone = ? LIMIT 1", (template_id, other_zone)
        ).fetchone():
            if force:
                db.execute("DELETE FROM sections WHERE template_id = ? AND zone = ?", (template_id, other_zone))
            else:
                skipped.append(other_zone)
    for zone, opts in preset["sides"].items():
        existing = db.execute(
            "SELECT 1 FROM sections WHERE template_id = ? AND zone = ? LIMIT 1", (template_id, zone)
        ).fetchone()
        if existing:
            if not force:
                skipped.append(zone)
                continue
            # The admin explicitly confirmed replacing what's there (see
            # the confirm() prompt in template_panel.html/dashboard.html) —
            # without this, a rail that already has a section (the normal
            # case once anyone has actually used the sidebar) silently did
            # nothing at all when a preset was clicked, with zero feedback
            # that anything was even blocked.
            db.execute("DELETE FROM sections WHERE template_id = ? AND zone = ?", (template_id, zone))
        direction = "vertical"
        content = _build_menu_links_html(
            db, items, style="plain", align=opts["align"], direction=direction,
        )
        db.execute(
            "INSERT INTO sections (template_id, zone, type, content, position, layout_width) VALUES (?, ?, 'html', ?, 0, ?)",
            (template_id, zone, content, opts["reach"]),
        )
        applied.append(zone)
    return applied, skipped



# ---------- Footer layout presets ----------
# Same idea and same mechanism as SIDEBAR_LAYOUT_PRESETS above — real,
# ordinary, immediately-editable sections (a Menu, a Contact block, a
# Columns section), never a separate "footer template" concept. Widths
# are never touched here either — the section width picker already owns
# that. "Columns" reuses the existing Columns section type (the same
# "Divide" control every section has) instead of teaching the footer
# zone any row/side-by-side behavior of its own, matching the rule that
# a zone's sections always stack full-width; only a section's own
# content (like a Columns section) may lay itself out side by side.
FOOTER_LAYOUT_PRESETS = {
    "simple": {
        "name": "Simple",
        "description": "One plain, centered menu row — the minimal footer most small sites need.",
    },
    "columns": {
        "name": "Columns",
        "description": "Three columns — menu links, contact & social icons, a closing note — the common multi-column footer (most WordPress/SaaS sites).",
    },
    "centered": {
        "name": "Centered",
        "description": "A centered menu with contact/social icons beneath it — compact and symmetrical.",
    },
}



def _default_layout_conflicts(db, template_id, manifest):
    """Read-only: would applying this template's own declared default
    layout replace a zone section that's already there? Two sources: a
    package saved via "Save current site as a new template" carries its
    exact captured header/sidebar/sidebar_right/footer sections
    (`manifest["zone_sections"]`, see _build_package_dir/
    save_current_site_as_package) — any non-empty zone it touches that
    already has a section is a conflict. A hand-authored content pack
    instead declares page_layout/footer_layout PRESET keys. Shared by
    _apply_default_layout (to decide whether to require force=1) and the
    Dashboard (to decide, before any click, whether "Use This Look" needs
    to warn first)."""
    if not manifest:
        return False

    def zone_has_content(zone):
        return bool(db.execute(
            "SELECT 1 FROM sections WHERE template_id = ? AND zone = ? LIMIT 1", (template_id, zone)
        ).fetchone())

    zone_sections = manifest.get("zone_sections")
    if zone_sections:
        touched_zones = {z["zone"] for z in zone_sections}
        return any(zone_has_content(zone) for zone in touched_zones)

    page_layout = manifest.get("page_layout")
    footer_layout = manifest.get("footer_layout")
    if page_layout and page_layout in SIDEBAR_LAYOUT_PRESETS:
        if any(zone_has_content(zone) for zone in ("sidebar", "sidebar_right")):
            return True
    if footer_layout and zone_has_content("footer"):
        return True
    if manifest.get("sidebar_widget") and any(zone_has_content(zone) for zone in ("sidebar", "sidebar_right")):
        return True
    return False



def _apply_zone_sections(db, template_id, zone_sections):
    """Re-inserts a saved template's exact captured header/sidebar/
    sidebar_right/footer sections onto `template_id` verbatim — the
    zone-section counterpart to _apply_pack_content's page loop. Clears
    each zone this pack actually has content for first (same
    force-already-confirmed contract as _apply_sidebar_layout/
    _apply_footer_layout — caller only reaches here once
    _default_layout_conflicts has been checked)."""
    touched_zones = {z["zone"] for z in zone_sections}
    for zone in touched_zones:
        db.execute("DELETE FROM sections WHERE template_id = ? AND zone = ?", (template_id, zone))
    for pos, z in enumerate(zone_sections):
        db.execute(
            "INSERT INTO sections (template_id, zone, type, title, content, position, layout_width) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template_id, z["zone"], z["type"], z["title"], z["content"], pos, z.get("layout_width", "auto")),
        )



def _retire_foreign_pack_pages(db, slug):
    """Removes pages left behind by whichever template was here before.

    Activating a template replaces the content of the pages it knows
    about, but until now said nothing about the ones it does not: switch
    from the CV template to the coffee shop and the site keeps an
    Education page, in the navigation, for a business that teaches
    nothing. Only pages a DIFFERENT pack put there are removed — a page
    the owner made themselves has no source template and is never touched,
    and neither is the home page.

    Returns (removed, kept) titles, so the flash can say what happened
    rather than have pages quietly vanish -- and can say what it SPARED,
    which is the more surprising half.
    """
    #  A TEMPLATE IS A STRUCTURED WEBSITE, PAGES INCLUDED. Loading one
    #  loads its pages, and the previous template's pages go -- ALL of
    #  them. The only way to keep what is there is to choose just the
    #  look, which is what that option is for.
    #
    #  This used to spare any page carrying `owner_edited = 1`, on the
    #  reasoning that a page somebody has written in is the site's now.
    #  Two things were wrong with it. The flag was set by a trigger on
    #  `sections`, so an older bug that cleared it before writing a
    #  pack's own sections marked EVERY page of every pack as edited --
    #  and a spared page is spared forever, by every future switch. That
    #  is how a saxophone template's "The library" survived onto a
    #  wedding barn, a bicycle workshop and a pottery studio, carrying
    #  its own heading, with nothing on any screen explaining why.
    #
    #  And the second is that it made the feature mean two different
    #  things depending on history nobody can see. "Load the template"
    #  either loads the template or it does not.
    #
    #  The care that rule was reaching for has a better home: the flag
    #  still says which of these pages had the owner's own writing in
    #  them, and the caller WARNS with that instead of vetoing. The
    #  confirm dialog already offers to save the current site as a new
    #  template first, which is this app's undo (see CLAUDE.md) -- so
    #  the work is recoverable, by an act the owner chose, rather than
    #  preserved by a flag they cannot see.
    doomed = db.execute(
        "SELECT id, title FROM pages WHERE source_template IS NOT NULL "
        "AND source_template != ? AND is_home = 0", (slug,)
    ).fetchall()
    written_in = db.execute(
        "SELECT title FROM pages WHERE source_template IS NOT NULL "
        "AND source_template != ? AND is_home = 0 AND owner_edited = 1", (slug,)
    ).fetchall()
    for page in doomed:
        db.execute("DELETE FROM sections WHERE page_id = ?", (page["id"],))
        db.execute("DELETE FROM pages WHERE id = ?", (page["id"],))
    #  (removed, had your own writing in them) -- the second is a subset
    #  of the first now, and is a warning rather than a list of survivors.
    return [p["title"] for p in doomed], [p["title"] for p in written_in]


def demo_identity_names(db):
    """Every name that belongs to a template rather than to this site.

    The empty string and the two placeholders, plus the business name in
    every installed template's manifest. Worked out inside
    _apply_pack_identity and thrown away there; it is named here because
    a screen wants the same question answered -- "is the name on this
    site still an example?" -- and answering it twice in two places is
    how the two come to disagree.
    """
    names = {"", "My Site", "Your Business Name"}
    for row in db.execute("SELECT slug FROM templates").fetchall():
        path = os.path.join(current_app.static_folder, "themes", row["slug"], "manifest.json")
        try:
            with open(path, encoding="utf-8") as handle:
                installed = json.load(handle)
        except (OSError, ValueError):
            continue
        names.add((installed.get("business_name") or "").strip())
    return names


def site_still_has_a_borrowed_name(db):
    """The name on this site, if it is still a template's example one."""
    row = db.execute("SELECT value FROM settings WHERE key = 'site_title'").fetchone()
    current = ((row["value"] if row else "") or "").strip()
    return current if current in demo_identity_names(db) else ""


def _apply_pack_identity(db, manifest):
    """Gives the site the template's own name, but only if the name on it
    is still somebody else's demo.

    Activating a template means "make my site look like this", and leaving
    a coffee roaster's name across a consulting firm's pages is the first
    thing anyone notices. But an owner who has typed their own name must
    never lose it to a click on a theme — so this replaces a name only
    when it is untouched, or when it is the demo name from another
    built-in template. Anything else is treated as the owner's own and
    left alone.
    """
    demo_names = demo_identity_names(db)
    demo_taglines = {""}
    #  Read from where the manifests actually ARE, which is not where this
    #  used to look. It globbed `data/templates/*/manifest.json` — the
    #  authoring sources — and those are deleted from the runtime image by
    #  the packager stage, because templates ship as zips now. So the glob
    #  matched nothing on every real install and this set held only the
    #  three hardcoded strings: the whole "another template's demo name"
    #  half of the guard had been dead since packaging changed. Activating
    #  a second template left the first one's name across it, which is the
    #  exact thing the docstring above says this exists to prevent.
    #
    #  Every installed template unpacks to static/themes/<slug>/, builtin
    #  or imported alike (see packages.template_package_dir), so reading
    #  from there also covers a template somebody uploaded — which the
    #  source glob never could.
    for row in db.execute("SELECT slug FROM templates").fetchall():
        path = os.path.join(current_app.static_folder, "themes", row["slug"], "manifest.json")
        try:
            with open(path, encoding="utf-8") as handle:
                installed = json.load(handle)
        except (OSError, ValueError):
            continue
        demo_taglines.add((installed.get("tagline") or "").strip())

    current = db.execute("SELECT value FROM settings WHERE key = 'site_title'").fetchone()
    current_title = (current["value"] if current else "").strip()
    if current_title and current_title not in demo_names:
        return False
    name = (manifest.get("business_name") or "").strip()
    if not name:
        return False
    def put(key, value):
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    put("site_title", name)
    #  The tagline is judged on itself, which it was not. The guard above
    #  tests the TITLE, and the write used to cover both -- so an owner who
    #  had typed a tagline while the title was still "My Site" lost it the
    #  next time any template was activated. Their name was protected and
    #  the line underneath it was not.
    tag_row = db.execute("SELECT value FROM settings WHERE key = 'site_tagline'").fetchone()
    current_tagline = (tag_row["value"] if tag_row else "").strip()
    if current_tagline in demo_taglines:
        put("site_tagline", (manifest.get("tagline") or "").strip())
    return True


def _apply_default_layout(db, template_id, manifest, force=False):
    """Applied right after a template becomes active, when its own package
    manifest declares a default look: either a saved template's exact
    captured zone sections + nav_layout (see save_current_site_as_package)
    or a hand-authored content pack's nav_layout/page_layout/footer_layout/
    header_menu/sidebar_widget keys. This is the ONE place any of a
    manifest's layout keys get applied, always scoped to `template_id` —
    the template actually being activated. It used to also run a second
    time from inside _apply_pack_content, keyed off the pack's own
    `theme_name` field, which could silently re-activate and apply layout
    to a DIFFERENT template than the one just requested (a content pack
    naming a companion theme by name was never guaranteed to be "whichever
    template the admin just clicked Activate on"). That duplicate path,
    and the companion-theme-by-name indirection itself, are both gone —
    every built-in content pack now ships its own theme.css/palette
    directly (see CLAUDE.md's Template Packages section) and a content
    pack's layout keys apply to its own template, same as a saved
    template's do, via this one function only.

    page_ids=None throughout (the site's real pages, current at the
    moment of activation) since activating a look isn't tied to any
    particular set of pages — recomputed fresh here rather than reusing
    whatever _apply_pack_content most recently touched.

    force=False (the default) refuses to touch a zone that already has
    sections and returns True without applying anything, so the caller
    can prompt for confirmation first — matching every other layout
    preset's existing confirm-before-replace behavior. The caller passes
    force=True only once the admin has confirmed (see
    template-panel.js's apply()). Returns whether applying is/would be
    destructive, regardless of whether force let it actually proceed."""
    if not manifest:
        return False
    destructive = _default_layout_conflicts(db, template_id, manifest)
    if destructive and not force:
        return True

    if manifest.get("nav_layout"):
        _set_setting(db, "nav_layout", manifest["nav_layout"])

    zone_sections = manifest.get("zone_sections")
    if zone_sections:
        _apply_zone_sections(db, template_id, zone_sections)
        return destructive

    page_ids = [p["id"] for p in db.execute("SELECT id FROM pages ORDER BY nav_order, title").fetchall()]
    page_layout = manifest.get("page_layout")
    footer_layout = manifest.get("footer_layout")
    if page_layout and page_layout in SIDEBAR_LAYOUT_PRESETS:
        _apply_sidebar_layout(db, template_id, page_layout, page_ids=page_ids, force=True)
    if footer_layout and footer_layout in FOOTER_LAYOUT_PRESETS:
        _apply_footer_layout(
            db, template_id, footer_layout, page_ids=page_ids, contact_form=manifest.get("footer_contact"),
            business_name=manifest.get("business_name"), blurb=manifest.get("footer_blurb"),
        )
    if manifest.get("header_menu") is False:
        db.execute("DELETE FROM sections WHERE template_id = ? AND zone = 'header'", (template_id,))
    elif page_layout or footer_layout or manifest.get("header_menu"):
        # A content pack that declares any default layout wants a real
        # page-nav menu built into its header too (header_menu defaults
        # to True for those — see CLAUDE.md) — a saved template without
        # its own page_layout/footer_layout preset (e.g. a plain theme)
        # has no opinion here and leaves the header alone.
        _demo_set_header_menu(db, template_id, page_ids)
    if manifest.get("sidebar_widget"):
        # Replaces whichever zone(s) the preset just filled with a Menu —
        # a widgets rail (see pack comment) shouldn't get one — with the
        # cards the pack wants there. A sidebar zone holds exactly ONE
        # top-level section (see render_zone_list's single=true call for
        # sidebar_right in page.html — additional rows come from Divide,
        # not a second top-level section), so multiple cards is one
        # Columns section whose cells stack vertically in that zone
        # (.site-sidebar-zone .cms-columns-N uses grid-template-rows —
        # see site-base.css), exactly what clicking "Divide" on a Card
        # section there produces.
        for zone in ("sidebar", "sidebar_right"):
            has_zone = db.execute(
                "SELECT 1 FROM sections WHERE template_id = ? AND zone = ? LIMIT 1", (template_id, zone)
            ).fetchone()
            if not has_zone:
                continue
            db.execute("DELETE FROM sections WHERE template_id = ? AND zone = ?", (template_id, zone))
            db.execute(
                "INSERT INTO sections (template_id, zone, type, content, position, layout_width) VALUES (?, ?, 'columns', ?, 0, 'auto')",
                (template_id, zone, json.dumps({"columns": manifest["sidebar_widget"]})),
            )
    return destructive



def _apply_footer_layout(db, template_id, preset_key, page_ids=None, contact_form=None, business_name=None, blurb=None):
    """Shared by the footer-layout picker route and demo-pack loading —
    the latter passes `page_ids` (that pack's own pages, in pack order)
    so a demo's footer menu links match its own site instead of every
    page across the whole install, old test pages and other packs'
    leftovers included. `page_ids=None` (the route's case) keeps the
    original "every real page" behavior. `contact_form`/`business_name`/
    `blurb` are demo-only too — the manual route has no real contact
    info or tagline to seed yet (an empty Contact block prompting the
    admin to fill it in is the CORRECT state there, and a full page menu
    is the only generic default available), but a demo pack claiming to
    be production-ready can't leave that same "Add a phone number..."
    placeholder, a literal "Your Business Name" copyright, or — the
    other thing a real footer essentially never does — the ENTIRE
    primary nav repeated verbatim right under itself. `blurb`, when
    given, replaces that repeated menu with a one-line tagline instead,
    same as any real site's footer would actually have."""
    #  Applied by hand, `contact_form` is None -- and the Columns and
    #  Centered presets both DESCRIBE a contact column, so both used to
    #  describe something they did not build. The reason given at the
    #  time was that there was no real contact information to seed, and
    #  that is no longer true: the site's own details are on file from
    #  the Legal pages screen, and they belong to the site rather than to
    #  whichever template is being tried on.
    #
    #  With nothing on file it still builds the column, empty, because an
    #  empty Contacts tool asking to be filled in is a truthful third
    #  column and a missing one is not.
    if contact_form is None and preset_key in ("columns", "centered"):
        own = legal.settings_for(db)
        contact_form = {kind: own[kind] for kind in ("phone", "email", "address")
                        if (own.get(kind) or "").strip()}
    db.execute("DELETE FROM sections WHERE template_id = ? AND zone = 'footer'", (template_id,))
    if page_ids is not None:
        rows = db.execute(
            f"SELECT id FROM pages WHERE id IN ({', '.join('?' for _ in page_ids)})", page_ids
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        pages = [by_id[pid] for pid in page_ids if pid in by_id]
    else:
        pages = db.execute("SELECT id FROM pages ORDER BY nav_order, title").fetchall()
    items = [{"key": f"p{p['id']}", "type": "page", "id": p["id"], "icon": "", "parent": None} for p in pages]
    pos = 0
    menu_or_blurb_html = (
        f'<p>{blurb}</p>' if blurb
        else _build_menu_links_html(db, items, style="plain", align="center", direction="horizontal")
    )
    copyright_html = f'<p>&copy; {html_escape(business_name or "Your Business Name")}</p>'
    # ONE Columns section, cells dividing the content — the Columns tool's
    # own actual purpose, not separately stacked sections fighting each
    # other's default block spacing with custom CSS. Whatever cells this
    # preset calls for (nav/tagline, contact, copyright), they're all
    # cells of the same Columns block, exactly what picking "Columns" from
    # the tool menu and filling in 2 or 3 cells produces for any admin.
    if preset_key == "simple":
        cells = [menu_or_blurb_html]
        #  Simple means the fewest cells, not "throw away the details this
        #  template shipped". It used to be the one preset that ignored
        #  footer_contact entirely, so four templates declared an email, a
        #  phone or a website in their manifest and their footer showed
        #  none of it -- the manifest said one thing and the site another.
        #  Two of those four now carry their address here, having had it
        #  taken off their contact page, so this is also what stops that
        #  address landing nowhere.
        if contact_form is not None:
            cells.append(build_contact_tool(
                [{"value": v, "icon": LEGACY_KIND_ICONS.get(k, "")}
                 for k, v in (contact_form or {}).items()]))
        cells.append(copyright_html)
    elif preset_key == "centered":
        cells = [menu_or_blurb_html]
        if contact_form is not None:
            #  A manifest's footer_contact is already {kind: value}, which
            #  is a Contacts block's rows -- so a template's footer is
            #  built by the same function the tool uses, and the tool can
            #  read and edit what a template shipped.
            cells.append(build_contact_tool(
                [{"value": v, "icon": LEGACY_KIND_ICONS.get(k, "")}
                 for k, v in (contact_form or {}).items()]))
        cells.append(copyright_html)
    else:  # "columns"
        cells = [menu_or_blurb_html]
        if contact_form is not None:
            #  A manifest's footer_contact is already {kind: value}, which
            #  is a Contacts block's rows -- so a template's footer is
            #  built by the same function the tool uses, and the tool can
            #  read and edit what a template shipped.
            cells.append(build_contact_tool(
                [{"value": v, "icon": LEGACY_KIND_ICONS.get(k, "")}
                 for k, v in (contact_form or {}).items()]))
        cells.append(copyright_html)
    db.execute(
        "INSERT INTO sections (template_id, zone, type, content, position, layout_width) VALUES (?, 'footer', 'columns', ?, ?, 'auto')",
        (template_id, json.dumps({"columns": cells}), pos),
    )



# ---------- Template package content ----------
# The pages/sections themselves are content data (see app/data/templates/
# <slug>/, loaded via app/services/packages.py) — this is the algorithm
# that merges a package's page content into the SITE'S OWN pages (see
# routes/admin/templates.py's load-content route), never a separate
# parallel "demo-*" site. There is no undo tracking any more — a Snapshot
# taken before loading (the route prompts for one) is the way back. The
# placeholder image path below must match the one baked into every
# package's section HTML (see app/data/templates/*/pages/*.json) — it's
# how an already-generated real image gets swapped back in for a matching
# prompt.
DEMO_PLACEHOLDER_IMG = "/static/img/placeholder.svg"


def _demo_set_header_menu(db, template_id, page_ids):
    """Points the header's own nav at exactly this pack's pages, in pack
    order — without this, activating a different theme either leaves
    that theme's OWN header Menu (a different, unrelated page list, or
    none at all) or — worse — a Menu built for a completely different
    demo pack still sitting there from before. Reuses whichever Menu
    section already lives in this template's header if there is one
    (keeps its style/size/align choices), otherwise adds a plain one."""
    items = [{"key": f"p{pid}", "type": "page", "id": pid, "icon": "", "parent": None} for pid in page_ids]
    header_sections = db.execute(
        "SELECT id, content FROM sections WHERE template_id = ? AND zone = 'header' ORDER BY position",
        (template_id,),
    ).fetchall()
    menu_section = next((s for s in header_sections if "cms-menu" in (s["content"] or "")), None)
    if menu_section:
        align_match = re.search(r"cms-menu-align-(\w+)", menu_section["content"] or "")
        direction_match = re.search(r"cms-menu-direction-(\w+)", menu_section["content"] or "")
        style = "dropdown" if "cms-menu-dropdown" in (menu_section["content"] or "") else (
            "buttons" if "cms-menu-buttons" in (menu_section["content"] or "") else "plain"
        )
        align = align_match.group(1) if align_match else "left"
        direction = direction_match.group(1) if direction_match else "horizontal"
        content = _build_menu_links_html(db, items, style=style, align=align, direction=direction)
        db.execute("UPDATE sections SET content = ? WHERE id = ?", (content, menu_section["id"]))
    else:
        content = _build_menu_links_html(db, items, style="plain", align="left", direction="horizontal")
        db.execute(
            "INSERT INTO sections (template_id, zone, type, content, position) VALUES (?, 'header', 'html', ?, 0)",
            (template_id, content),
        )



def _apply_pack_content(db, pack, page_slugs=None):
    """Merges a package's content into the SITE'S OWN pages — the actual
    homepage gets the pack's "home" content, and each other pack page
    reuses an existing page with a matching slug if there is one (so a
    site that already has a Menu/Contact/etc. page gets that page filled
    in, not a second parallel one) or creates a plain new page otherwise.
    Never creates a separate "demo-*" shadow site. `page_slugs`, when
    given, restricts this to just those pack pages (their own
    `slug_suffix`, e.g. "home", "about") — the content-load picker's
    selection; None (the default) applies every page the pack ships.
    Returns [{"id", "created", "blog"}, ...] for whichever pages this
    call actually touched — purely informational now (e.g. a flash
    message's page count); nothing persists it for later undo. Saving the
    current site as a new template beforehand (see the load-content
    route) is the way back. Only touches PAGE content — a pack's own
    look/layout (nav_layout/page_layout/footer_layout/header_menu/
    sidebar_widget keys, plus its own theme.css/palette/google_fonts_url,
    installed straight onto its `templates` row by install_theme_package)
    is applied separately by _apply_default_layout, scoped to whichever
    template is actually being activated, not looked up by name from
    here."""
    pages_to_apply = pack["pages"]
    if page_slugs is not None:
        pages_to_apply = [p for p in pages_to_apply if p["slug_suffix"] in page_slugs]

    touched = []  # [{"id": page_id, "created": bool, "blog": bool}, ...]
    for page_spec in pages_to_apply:
        if page_spec["slug_suffix"] == "home":
            target = db.execute("SELECT id FROM pages WHERE is_home = 1").fetchone()
        else:
            target = db.execute("SELECT id FROM pages WHERE slug = ?", (page_spec["slug_suffix"],)).fetchone()

        if target:
            page_id = target["id"]
            db.execute(
                #  The TITLE comes too. Without it a reused page keeps
                #  whatever the previous template called it, so loading
                #  the coaching pack over a landscaping site left its
                #  journal page titled "Yard Notes" -- the right page,
                #  the right content, the old template's name on it, in
                #  the navigation. Loading a template's content is
                #  all-or-nothing by design; the name is part of it.
                "UPDATE pages SET title = ?, meta_description = ?, page_type = ? WHERE id = ?",
                (page_spec["title"], page_spec["meta_description"],
                 page_spec["page_type"], page_id),
            )
            created = False
        else:
            slug = page_spec["slug_suffix"]
            base_slug, i = slug, 2
            while db.execute("SELECT 1 FROM pages WHERE slug = ?", (slug,)).fetchone() or slug in RESERVED_SLUGS:
                slug = f"{base_slug}-{i}"
                i += 1
            cur = db.execute(
                "INSERT INTO pages (title, slug, nav_order, page_type, meta_description) "
                "VALUES (?, ?, (SELECT COALESCE(MAX(nav_order),0)+1 FROM pages), ?, ?)",
                (page_spec["title"], slug, page_spec["page_type"], page_spec["meta_description"]),
            )
            page_id = cur.lastrowid
            created = True

        # Only a package saved via "Save current site as a new template"
        # carries these (see _build_package_dir's capture_layout) — a
        # hand-authored content pack's page JSON never has them, so this
        # is a no-op for those.
        if "nav_layout_override" in page_spec:
            db.execute(
                "UPDATE pages SET nav_layout_override = ?, hide_sidebar = ?, hide_sidebar_right = ?, "
                "hide_footer = ? WHERE id = ?",
                (
                    page_spec["nav_layout_override"], int(page_spec.get("hide_sidebar", False)),
                    int(page_spec.get("hide_sidebar_right", False)), int(page_spec.get("hide_footer", False)),
                    page_id,
                ),
            )

        #  Stamped whether the page was created here or already existed:
        #  either way its content is now this pack's, and that is what
        #  makes it removable when a different template takes over.
        #  Written by the pack, so it is the pack's copy again -- the
        #  trigger on `sections` has just marked it edited, and that was
        #  this code writing, not a person. Load Content putting a page
        #  back is exactly the act that un-edits it.
        db.execute("UPDATE pages SET source_template = ? WHERE id = ?",
                   (pack.get("slug"), page_id))
        #  A page can arrive with its own backdrop — a picture behind the
        #  whole page, and how the content sits on it. Without this a
        #  template could describe the look and never deliver it.
        if any(page_spec.get(key) for key in ("bg_image", "bg_color")):
            db.execute(
                "UPDATE pages SET bg_image = ?, bg_attach = ?, bg_overlay = ?, "
                "bg_surface = ?, bg_color = ? WHERE id = ?",
                (page_spec.get("bg_image"), page_spec.get("bg_attach"),
                 page_spec.get("bg_overlay"), page_spec.get("bg_surface"),
                 page_spec.get("bg_color"), page_id),
            )
        db.execute("DELETE FROM sections WHERE page_id = ?", (page_id,))
        for pos, (s_type, title, content, extra) in enumerate(page_spec["sections"]):
            extra = dict(extra)
            #  Popped, not used: a leftover key in the package data would
            #  otherwise be taken for a column name by the insert below.
            extra.pop("_prompt", None)
            cols = ["page_id", "type", "title", "content", "position"] + list(extra.keys())
            vals = [page_id, s_type, title, content, pos] + list(extra.values())
            cur = db.execute(
                f"INSERT INTO sections ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                vals,
            )
        #  AFTER the sections, not before them.
        #
        #  The trigger on `sections` sets owner_edited on any write, and
        #  the inserts above are writes -- so clearing the flag first
        #  cleared it and then immediately set it again, on every page of
        #  every pack. The effect was invisible here and total elsewhere:
        #  `_retire_foreign_pack_pages` spares a page somebody has
        #  written in, so with every page falsely marked edited it spared
        #  ALL of them, and the previous template's pages stayed. Switch
        #  template five times and the menu carries five templates' pages
        #  -- twenty-seven of them on this install, which is how it was
        #  found.
        #
        #  This code writing a pack's own content is not a person writing
        #  in a page, which is exactly what the comment above the old
        #  line said it meant. It was in the wrong place to mean it.
        db.execute("UPDATE pages SET owner_edited = 0 WHERE id = ?", (page_id,))
        touched.append({"id": page_id, "created": created, "blog": False})

        #  A template's content is what the package ships, on every host.
        #
        #  This used to reach into generated_images and, where a section's
        #  prompt matched one somebody had generated on THIS machine,
        #  swap the shipped placeholder for that machine's own picture.
        #  Convenient, and it meant the same template rendered differently
        #  depending on who had pressed Generate on the server before —
        #  sixteen sections carried such a prompt, and fourteen of them
        #  matched on the development host, so its templates already did
        #  not look like a fresh install's. A package that cannot be
        #  restored identically is not a package.
        #
        #  Generating a real photo for a section is still the admin's own
        #  call, through that section's own Generate button, and the
        #  Media Library still holds everything ever generated.

    # A blog-type page (e.g. "Journal") gets real posts too, not just
    # sections — blog_posts is a separate table entirely, so this can't
    # go through the generic page-sections loop above.
    #  A package's posts go into a blog, which is a thing of its own now
    #  rather than a kind of page. A package cannot know what id a blog
    #  will get on somebody else's install, so it ships its Blog tool
    #  unconfigured and the id is filled in here — which also means a
    #  package imported without its posts renders "no blog chosen yet"
    #  instead of a dangling reference.
    if pack.get("blog_posts"):
        from ...services import blog as blog_service
        #  Named after the page that carries the tool, so the blog is
        #  called what the template calls it rather than "Blog".
        host = db.execute(
            "SELECT p.id, p.title, p.slug FROM sections s JOIN pages p ON p.id = s.page_id "
            "WHERE s.content LIKE '%cms-blog%' AND s.content LIKE '%data-blog-id=\"\"%' LIMIT 1"
        ).fetchone()
        wanted_slug = host["slug"] if host else "blog"
        wanted_name = host["title"] if host else "Blog"
        existing = blog_service.get_blog_by_slug(db, wanted_slug)
        blog_id = existing["id"] if existing else blog_service.create_blog(db, wanted_name, wanted_slug)

        db.execute("DELETE FROM blog_posts WHERE blog_id = ?", (blog_id,))
        today = datetime.date.today().isoformat()
        for pos, post in enumerate(pack["blog_posts"]):
            db.execute(
                "INSERT INTO blog_posts (blog_id, title, slug, excerpt, content, published_at, position) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (blog_id, post["title"], slugify(post["title"]), post["excerpt"],
                 post["content"], today, pos),
            )
        #  Every unconfigured Blog tool this package just installed now
        #  points at it. More than one is fine — the same posts shown in
        #  two places is exactly what the tool is for.
        for row in db.execute(
            "SELECT id, content FROM sections WHERE content LIKE '%cms-blog%' "
            "AND content LIKE '%data-blog-id=\"\"%'"
        ).fetchall():
            db.execute(
                "UPDATE sections SET content = ? WHERE id = ?",
                (row["content"].replace('data-blog-id=""', f'data-blog-id="{blog_id}"'), row["id"]),
            )
        if host:
            already_touched = next((t for t in touched if t["id"] == host["id"]), None)
            if already_touched:
                already_touched["blog"] = True
            else:
                touched.append({"id": blog_page_id, "created": False, "blog": True})

    #  Pages have just appeared and disappeared, so every menu on the site
    #  is re-pointed at what exists now. Without this a template change
    #  leaves the navigation advertising the previous template's pages —
    #  which is how a coffee shop came to have a Services link.
    from ...services.menu import refresh_site_menus
    refresh_site_menus(db)
    return touched



EMAIL_SETTINGS_KEYS = (
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_use_tls", "from_email", "from_name", "to_email",
    #  Not an email field as such — the address emailed LINKS are built
    #  from. Lives here because this is where the sending is configured.
    "site_public_url",
)


def get_email_settings(db):
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ({})".format(
            ",".join("?" * len(EMAIL_SETTINGS_KEYS))
        ),
        EMAIL_SETTINGS_KEYS,
    ).fetchall()
    settings = {k: "" for k in EMAIL_SETTINGS_KEYS}
    settings.update({r["key"]: r["value"] for r in rows})
    #  Real defaults, not placeholder text. The setup instructions on that
    #  page are written for Gmail, and a greyed-out "smtp.gmail.com"
    #  placeholder reads exactly like a filled-in value — an install got
    #  saved with every field set except the host, which meant mail was
    #  silently skipped while the page looked configured.
    for key, default in (("smtp_host", "smtp.gmail.com"), ("smtp_port", "587"), ("smtp_use_tls", "1")):
        if not (settings.get(key) or "").strip():
            settings[key] = default
    #  Where a contact form's messages land falls back to the address the
    #  site sends AS. The two are different questions -- one is identity,
    #  the other is a destination, and a bigger business really does send
    #  as hello@ and read enquiries at sales@ -- but for almost everybody
    #  they are the same address typed twice.
    #
    #  It was not merely duplicated, it was REQUIRED: mailer.is_configured
    #  asks for to_email, so leaving it blank made a fully-configured
    #  mail setup report itself as not configured, and contact forms
    #  silently did nothing. A field nobody can leave blank is not
    #  optional, whatever the screen says.
    if not (settings.get("to_email") or "").strip():
        settings["to_email"] = (settings.get("from_email") or "").strip()
    return settings


SITE_SETTINGS_KEYS = ("site_title", "site_tagline", "favicon_url",
                      "maintenance_mode", "maintenance_message")


def get_site_settings(db):
    """The site's own name/tagline/favicon — shown in the header brand
    link, the browser tab title/icon, and anywhere else the public
    templates used to have a hardcoded "My Site". Same read/write shape as
    get_email_settings."""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ({})".format(
            ",".join("?" * len(SITE_SETTINGS_KEYS))
        ),
        SITE_SETTINGS_KEYS,
    ).fetchall()
    settings = {"site_title": "My Site", "site_tagline": "", "favicon_url": ""}
    settings.update({r["key"]: r["value"] for r in rows if r["value"]})
    return settings


def _set_setting(db, key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )



LAYOUT_SETTINGS_KEYS = ("default_section_width", "default_section_width_pct")


def get_layout_settings(db):
    """Site-wide fallback for a section's own layout_width, used whenever a
    section hasn't been given an explicit width of its own (layout_width
    IS NULL — every section starts this way) — see _effective_section_width.
    Same read/write shape as get_email_settings."""
    rows = db.execute(
        "SELECT key, value FROM settings WHERE key IN ({})".format(
            ",".join("?" * len(LAYOUT_SETTINGS_KEYS))
        ),
        LAYOUT_SETTINGS_KEYS,
    ).fetchall()
    settings = {"default_section_width": "auto", "default_section_width_pct": "100"}
    settings.update({r["key"]: r["value"] for r in rows if r["value"]})
    return settings



# ---------- Content Tools (the Tools side panel) ----------

def _list_tools(db):
    return db.execute("SELECT * FROM content_tools ORDER BY is_builtin DESC, position, id").fetchall()




# Route registration — each import below runs its module top-to-bottom,
# registering that module's @bp.route functions on the `bp` defined above
# as a side effect. Import order doesn't matter (every route decorator
# just appends to the same Blueprint); kept alphabetical for readability.
from . import assistant_routes  # noqa: E402,F401
from . import backups  # noqa: E402,F401
from . import schedules  # noqa: E402,F401
from . import legal_routes  # noqa: E402,F401
from . import newsletters  # noqa: E402,F401
from . import dashboard  # noqa: E402,F401
from . import pages  # noqa: E402,F401
from . import sections  # noqa: E402,F401
from . import settings  # noqa: E402,F401
from . import support  # noqa: E402,F401
from . import templates  # noqa: E402,F401
from . import wizard  # noqa: E402,F401


@bp.app_context_processor
def inject_password_warning():
    """Every admin screen says so while the generated password is still in
    use. One flash at login is easy to click past; this stays until the
    thing it is about is actually fixed."""
    try:
        from ... import bootstrap
        from ...db import get_db as _get_db
    except ImportError:
        return {}
    #  NOBODY who is not signed in gets any of this. It is an
    #  app_context_processor, so it runs for every template in the app --
    #  including the login page, which is how a bar naming the file the
    #  generated password is written in came to be rendered for anyone who
    #  loaded /admin/login. Telling an unauthenticated visitor that this
    #  install is still on its generated password, and where that password
    #  is kept, is help offered to exactly the wrong person.
    from flask import session as _session
    if not _session.get("user_id"):
        return {}
    try:
        db = _get_db()
        from ...services import wizard as wizard_service
        setup = wizard_service.state(db)
        return {"using_generated_password": bootstrap.using_generated_password(db, _session.get("user_id")),
                #  Offered until it has been finished once, and never on
                #  the walk-through's own screens.
                "setup_offer": not setup["done"],
                #  The site's own name, for the bar at the top. The public
                #  blueprint has had this for ever; the admin never did,
                #  which is why every admin screen said "My Site" however
                #  the owner had named theirs.
                "site_settings": get_site_settings(db),
                #  A site opens with a look already on, which means it also
                #  opens with that look's example business name. Said out
                #  loud until the owner replaces it, because the one thing
                #  worse than a placeholder name is a placeholder name
                #  nobody mentioned.
                "borrowed_site_name": site_still_has_a_borrowed_name(db)}
    except Exception:  # noqa: BLE001 - a banner must never break a page
        return {"using_generated_password": False}


#  Editing a built-in template's site forks it, once.
#
#  A built-in is reinstalled from the image on every boot, so it can never
#  hold somebody's changes — and until now the first edit put a site in a
#  strange position: the pages were theirs, the template they were "on"
#  was a stock one that would come back untouched, and nothing said so.
#  The moment content changes, the site gets a template of its own: a copy
#  of the one they were using, activated in its place. From then on they
#  are editing their own site, and Save can update that template or make
#  another.
#
#  Deliberately a copy of the PACKAGE rather than a fresh capture of the
#  site: a capture would rescan and re-copy every picture on the first
#  keystroke, and the useful thing to own at that moment is the template
#  they started from.


def fork_active_source(db, name=None, into_id=None):
    """Give this site its own copy of the SOURCE it is using.

    `name` is what the owner called it -- a name they chose is a name
    they will recognise in the library, which is the whole difference
    between this and the automatic version that produced three entries
    called "(your copy)". `into_id` overwrites an existing custom copy
    instead of making another, which is the case no automatic rule can
    decide because only the owner knows whether the old one still
    matters.

    Returns the new template's id, or None if there was nothing to do.
    """
    from ...services import lifecycle, packages
    active = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    #  "Is this a source", not "is this shipped". A promoted template gets
    #  the same protection without a second mechanism, which is the point
    #  of the lifecycle: shipped stops being a category the code cares
    #  about.
    if not active or not lifecycle.is_source(active):
        return None

    #  Claim the fork before doing any of it. Gunicorn runs several
    #  workers and the editor fires several requests at once, so two of
    #  them can read "the active template is a builtin" in the same
    #  instant and both fork it. That is not theory: this site ended up
    #  with `bakery-your-copy` AND `bakery-your-copy-2`, the second one
    #  missing its footer, and the page somebody had open was still
    #  pointing at a footer section that no longer belonged to the active
    #  template -- so saving the Contacts tool in it answered with a
    #  redirect where the editor expected JSON, and said "Couldn't save --
    #  check your connection".
    #
    #  One UPDATE, one winner: the loser sees rowcount 0 and leaves. The
    #  builtin is put back if the copy then fails, so a failed fork cannot
    #  leave the site with nothing active.
    claimed = db.execute(
        "UPDATE templates SET is_active = 0 WHERE id = ? AND is_active = 1 AND is_builtin = 1",
        (active["id"],),
    ).rowcount
    if not claimed:
        return None

    def _give_it_back():
        db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (active["id"],))
        db.commit()

    #  The NAME is disambiguated too, not just the slug. Forking the same
    #  builtin more than once -- which happens whenever somebody activates
    #  it again and then edits -- left a library holding three entries all
    #  called "Life Coaching (your copy)", identical in the picker and
    #  impossible to tell apart. The slug was unique the whole time, but
    #  nobody reads slugs.
    name = (name or "").strip() or f'{active["name"]} (your copy)'
    slug = slugify(name)
    base, i = slug, 2
    while db.execute("SELECT 1 FROM templates WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{i}"
        name = f'{active["name"]} (your copy {i})'
        i += 1
    source = packages.template_package_dir(current_app.static_folder, active["slug"], True)
    dest = os.path.join(current_app.static_folder, "themes", slug)
    if not os.path.isdir(source):
        _give_it_back()
        return None
    packages.copy_tree_contents(source, dest)
    try:
        new_id = packages.install_theme_package(
            db, slug, current_app.static_folder, pkg_dir_override=dest, is_builtin=False)
    except packages.PackageError:
        _give_it_back()
        return None
    db.execute("UPDATE templates SET name = ?, forked_from = ? WHERE id = ?",
               (name, active["slug"], new_id))
    db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (new_id,))
    #  The look the admin had customised on top of the builtin travels
    #  with the copy — otherwise forking would quietly reset their colours.
    for field in ("color_overrides", "font_overrides", "shape_override",
                  "shadow_override", "zone_style_overrides"):
        db.execute(f"UPDATE templates SET {field} = ? WHERE id = ?", (active[field], new_id))
    #  Zone sections belong to a template, so the header and footer they
    #  can see have to come across too or the site loses both.
    for row in db.execute("SELECT * FROM sections WHERE template_id = ?", (active["id"],)).fetchall():
        db.execute(
            "INSERT INTO sections (template_id, zone, type, title, content, position, layout_width) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id, row["zone"], row["type"], row["title"], row["content"],
             row["position"], row["layout_width"]))
    #  And the pages. Each one records the template it arrived with, and
    #  from this moment that template is the copy, not the built-in it was
    #  taken from -- the copy IS those pages. Leaving them pointing at the
    #  built-in made the Dashboard tell every page on the site it "came
    #  with the bakery template, not in use" at the exact moment all of
    #  them were most in use, because the site had just made the bakery
    #  its own.
    db.execute("UPDATE pages SET source_template = ? WHERE source_template = ?",
               (slug, active["slug"]))
    db.commit()
    return new_id


#  There WAS a before_request here that forked the active builtin on the
#  first content edit -- "the first content change of a site makes it
#  theirs". It is gone, and it is worth saying why, because it looked
#  protective and was not.
#
#  Editing a page writes to pages and sections. It does not write to the
#  template package or its row, so there was nothing about a content edit
#  that needed a copy of the template. What it produced instead was a new
#  template per site, silently, named "(your copy)", "(your copy 2)",
#  "(your copy 3)" -- three identical entries in one library here, each
#  carrying its own duplicate of the template's pictures.
#
#  It was not guarding _retire_foreign_pack_pages either, which was the
#  one plausible defence: that function spares any page whose
#  source_template is NULL, and the fork never touched source_template at
#  all. That gap is closed separately and properly -- a page somebody has
#  written in carries `owner_edited` and is spared on its own account,
#  whatever pack it came from.
#
#  Forking is now what the owner ASKS for when they change a LOOK, and
#  `fork_active_source` is what does it: named by them, recorded against
#  what it was forked from, and guarded on "is this a source" so a
#  promoted template gets the same protection as a shipped one. See
#  services/lifecycle.py.


@bp.before_request
def force_password_change():
    """No admin screen opens while the generated password is still in use.

    A prompt was not enough. That password was printed to the container
    log and written to a file in the data volume, in plain text, and it
    stays valid until somebody replaces it — so anyone who reads either
    one is an admin. Asking nicely leaves that true for as long as the
    owner keeps meaning to get round to it.

    Only enforced while the password is actually a way in: an owner who
    has since turned password sign-in off has already closed the hole.
    """
    from flask import session, redirect, url_for, request as _request, flash
    from ... import bootstrap
    from ...db import get_db as _get_db
    from ..auth import password_login_disabled

    if not session.get("user_id"):
        return None
    if _request.endpoint in ("auth.account", "auth.logout", "static") or _request.path.startswith("/static/"):
        return None
    db = _get_db()
    if not bootstrap.using_generated_password(db, session.get("user_id")) or password_login_disabled(db):
        return None
    flash("Set your own password before going any further — the one you signed in with was "
          "generated by this site and is written in plain text in the container log and in "
          "data/initial-admin-password.txt.", "warning")
    return redirect(url_for("auth.account"))
