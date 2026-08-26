"""Menu-building logic — used by body-section Menu tools, template header/
sidebar/footer zone routes, and demo/package content application. Pure
functions apart from url_for/db reads — no request/session coupling."""
import re
import json
from html import escape as html_escape, unescape as html_unescape

import sqlite3

from flask import url_for

from .. import icons


# ---------- Menu tool (build a links block from selected pages, on the spot) ----------
# No standing "named menu" object to manage — the admin just picks whichever
# pages they want, wherever they're adding a Menu, and that becomes a plain
# links block (a normal 'html' section/chunk) they can reorder/edit like any
# other content afterward. Any number of these can exist independently.

MENU_STYLES = ("plain", "buttons", "dropdown")
MENU_SIZES = ("small", "medium", "large")
MENU_BUTTON_STYLES = ("solid", "outline", "soft", "floating", "tabs", "fade")
MENU_SUBMENU_STYLES = ("card", "minimal", "dark", "bordered", "pill")
MENU_DIRECTIONS = ("horizontal", "vertical")


def _page_href(p):
    return url_for("public.home") if p["is_home"] else url_for("public.page", slug=p["slug"])


MENU_ITEM_TYPES = ("page", "custom", "divider")
MENU_FONTS = {
    "": None,
    "arial": "Arial, sans-serif",
    "georgia": "Georgia, serif",
    "times": "'Times New Roman', serif",
    "courier": "'Courier New', monospace",
    "verdana": "Verdana, sans-serif",
    "trebuchet": "'Trebuchet MS', sans-serif",
}


def _parse_menu_form(form, default_direction="horizontal"):
    """Reads the Menu tool's shape: a single JSON `menu_items` field built
    client-side, plus style/size/bg/align/highlight/font options. One
    JS-owned JSON blob (rather than scattered page_ids[]/parent_<id>
    fields) means an unrelated field change can never silently wipe out
    nesting on save — see git history for the bug that fixed.

    Each item is normalized to: {key, type, id?, url?, label?, icon?, parent}
      - key: stable string identity for this item, used for drag-reorder and
        parent references — independent of page id so custom links/dividers
        (which have no page id) can be nested/reordered too.
      - type: 'page' (id = a real page), 'custom' (arbitrary url + label),
        or 'divider' (a plain visual separator — no href, not nestable, and
        not a valid nest target).
      - parent: another item's key, or None — only meaningful for the
        Dropdown style, ignored otherwise. A divider can't have a parent and
        can't itself be a parent (checked at render time, not here, since
        the target might not exist yet in this same submission).
    Old items saved before this schema existed are just {"id", "parent"} —
    those still parse fine (type defaults to 'page', key defaults to
    "p<id>"), so older menus don't lose their pages on next edit.

    direction: 'horizontal' (flows left-to-right, the traditional topbar
    look) or 'vertical' (stacks top-to-bottom, for a sidebar rail). The
    admin can always pick explicitly via the Direction field
    (`menu_direction` in the form); when they haven't touched it yet,
    `default_direction` supplies a smart default based on context (e.g.
    the zone the Menu was dropped into) — see call sites.
    """
    try:
        raw_items = json.loads(form.get("menu_items", "[]"))
    except (ValueError, TypeError):
        raw_items = []
    items = []
    seen_keys = set()
    if isinstance(raw_items, list):
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            item_type = it.get("type")
            if item_type not in MENU_ITEM_TYPES:
                item_type = "page" if isinstance(it.get("id"), int) else None
            if item_type is None:
                continue
            key = it.get("key")
            if item_type == "page":
                pid = it.get("id")
                if not isinstance(pid, int):
                    continue
                key = key if isinstance(key, str) and key else f"p{pid}"
            elif not isinstance(key, str) or not key:
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            parent = it.get("parent")
            entry = {
                "key": key,
                "type": item_type,
                "parent": parent if isinstance(parent, str) else None,
            }
            if item_type == "page":
                entry["id"] = pid
            elif item_type == "custom":
                entry["url"] = (it.get("url") or "").strip()
                entry["label"] = (it.get("label") or "").strip() or "Link"
                if not entry["url"]:
                    continue
            if item_type != "divider":
                icon = (it.get("icon") or "").strip()
                # Icons are chosen from a fixed <select> (menu_icon_options in
                # page.html), not typed — a couple of them are multi-codepoint
                # emoji (e.g. ℹ️, 🛠️ use a variation selector), so this just
                # bounds size against a tampered request rather than actually
                # constraining to "one visible glyph".
                entry["icon"] = icon[:8] if icon else ""
            items.append(entry)
    style = form.get("menu_style", "plain")
    size = form.get("menu_size", "medium")
    align = form.get("menu_align", "left")
    link_style = form.get("menu_link_style", "normal")
    font_key = form.get("menu_font", "")
    font_key = font_key if font_key in MENU_FONTS else ""
    highlight_current = bool(form.get("menu_highlight_current"))
    bg_color = form.get("menu_bg_color", "").strip() if form.get("menu_bg_color_on") else ""
    text_color = form.get("menu_text_color", "").strip() if form.get("menu_text_color_on") else ""
    button_style = form.get("menu_button_style", "solid")
    button_style = button_style if button_style in MENU_BUTTON_STYLES else "solid"
    submenu_style = form.get("menu_submenu_style", "card")
    submenu_style = submenu_style if submenu_style in MENU_SUBMENU_STYLES else "card"
    direction = form.get("menu_direction", "")
    direction = direction if direction in MENU_DIRECTIONS else default_direction
    return items, style, size, bg_color, align, highlight_current, text_color, link_style, font_key, button_style, submenu_style, direction


MENU_ALIGNS = ("left", "center", "right")


MENU_LINK_STYLES = ("normal", "bold", "uppercase")


def _contrast_text_color(hex_color):
    """Cheap WCAG-ish luminance check so an auto-picked button text color
    (white or near-black) stays readable against whatever custom button
    color the admin chose — no separate "button text color" control needed."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1f2430" if luminance > 0.6 else "#ffffff"


def _build_menu_links_html(db, items, style="plain", size="medium", bg_color="",
                            align="left", highlight_current=False, text_color="", link_style="normal",
                            font_key="", button_style="solid", submenu_style="card", direction="horizontal"):
    """
    items: normalized list from _parse_menu_form — each {key, type, id?,
    url?, label?, icon?, parent}. type='page' resolves id against real
    pages (dropped if the page no longer exists); type='custom' is an
    arbitrary url+label; type='divider' renders a plain separator with no
    link at all.
    style: 'plain' (a plain list of links), 'buttons' (each link styled as
    a button), or 'dropdown' (top-level items with a submenu — an item
    whose parent is another item's key nests under it; a dropdown item
    with no children just renders as a normal top-level link). Dividers
    are never nested and never a nest target, in any style.
    size: 'small'/'medium'/'large' — mirrors the Breadcrumb tool's own size option.
    bg_color: optional '#rrggbb', shown behind the links.
    align: 'left'/'center'/'right'.
    highlight_current: if set, embeds a marker the public site.js reads to
    bold whichever link matches the page currently being viewed — this has
    to happen client-side (or at request time) since the same saved HTML
    is shown on every page of the site.
    text_color: optional '#rrggbb'. For 'plain'/'dropdown' styles this is
    the link text color. For 'buttons' it's redundant as a *text* color
    (the button's own background already dictates readable text via
    _contrast_text_color), so it's repurposed as the button color instead —
    one color picker, meaning depends on style, rather than a second control.
    link_style: 'normal'/'bold'/'uppercase'.
    font: an explicit font-family CSS value, or None for the theme default.
    button_style: only meaningful when style == 'buttons' — 'solid' (filled,
    the original/default look), 'outline' (border only, transparent fill),
    'soft' (a light tint of the color, colored text), 'floating' (solid pill
    with a shadow, lifts off the page), 'tabs' (flat, no fill, bottom border
    only — active/hover state reads as an underline), 'fade' (gradient fill
    from the color into a lighter shade of itself).
    submenu_style: only meaningful when style == 'dropdown' — how the
    flyout panel of a submenu looks: 'card' (the original/default —
    white card, border, shadow), 'minimal' (no border/shadow, just a plain
    background), 'dark' (dark background, light text, regardless of the
    page's own theme), 'bordered' (thicker border, square corners, no
    shadow), 'pill' (each item is its own rounded pill button with gaps,
    instead of a flush list).

    The link list is always wrapped in a .cms-menu-links element and a
    .cms-menu-toggle (hamburger) button is always emitted — both no-ops on
    desktop (the CSS only activates them under the mobile breakpoint) so
    every existing/older saved menu gets the collapse behavior for free
    without needing a re-save.
    """
    style = style if style in MENU_STYLES else "plain"
    size = size if size in MENU_SIZES else "medium"
    align = align if align in MENU_ALIGNS else "left"
    link_style = link_style if link_style in MENU_LINK_STYLES else "normal"
    button_style = button_style if button_style in MENU_BUTTON_STYLES else "solid"
    submenu_style = submenu_style if submenu_style in MENU_SUBMENU_STYLES else "card"
    direction = direction if direction in MENU_DIRECTIONS else "horizontal"
    bg_color = (bg_color or "").strip()
    text_color = (text_color or "").strip()
    text_color_valid = bool(text_color and re.match(r"^#[0-9a-fA-F]{6}$", text_color))
    style_parts = []
    if bg_color and re.match(r"^#[0-9a-fA-F]{6}$", bg_color):
        style_parts.append(f"background-color:{bg_color}")
    if text_color_valid and style != "buttons":
        style_parts.append(f"color:{text_color}")
    if text_color_valid and style == "buttons":
        style_parts.append(f"--menu-btn-color:{text_color}")
        style_parts.append(f"--menu-btn-text:{_contrast_text_color(text_color)}")
    font_key = font_key if font_key in MENU_FONTS else ""
    font_css = MENU_FONTS.get(font_key)
    if font_css:
        style_parts.append(f"font-family:{font_css}")
    style_attr = f' style="{"; ".join(style_parts)}"' if style_parts else ""
    font_attr = f' data-menu-font="{font_key}"' if font_key else ""

    page_ids = [it["id"] for it in items if it["type"] == "page"]
    pages_by_id = {p["id"]: p for p in db.execute("SELECT * FROM pages WHERE id IN ({})".format(
        ",".join("?" * len(page_ids))
    ), page_ids)} if page_ids else {}
    resolved = [it for it in items if it["type"] != "page" or it["id"] in pages_by_id]
    by_key = {it["key"]: it for it in resolved}

    def _href_label(it):
        if it["type"] == "page":
            p = pages_by_id[it["id"]]
            return _page_href(p), p["title"]
        return it["url"], it["label"]

    def _icon_span(it):
        return icons.render_icon(it.get("icon"))

    items_json = html_escape(json.dumps(resolved))
    highlight_attr = ' data-highlight-current="1"' if highlight_current else ""
    align_class = f" cms-menu-align-{align}"
    link_style_class = f" cms-menu-style-{link_style}" if link_style != "normal" else ""
    direction_class = f" cms-menu-direction-{direction}" if direction == "vertical" else ""
    direction_attr = f' data-menu-direction="{direction}"'
    toggle_btn = '<button type="button" class="cms-menu-toggle" aria-label="Menu" aria-expanded="false">☰</button>'

    if style == "dropdown":
        children_of = {}
        top_level = []
        for it in resolved:
            parent_key = it["parent"]
            parent = by_key.get(parent_key)
            if it["type"] != "divider" and parent and parent["type"] != "divider" and parent_key != it["key"]:
                children_of.setdefault(parent_key, []).append(it)
            else:
                top_level.append(it)
        parts = []
        for it in top_level:
            if it["type"] == "divider":
                parts.append('<li class="cms-menu-divider" data-menu-key="' + html_escape(it["key"]) + '" aria-hidden="true"></li>')
                continue
            href, label = _href_label(it)
            kids = children_of.get(it["key"], [])
            link_html = f'<a href="{html_escape(href)}" data-menu-key="{html_escape(it["key"])}">{_icon_span(it)}{html_escape(label)}</a>'
            if kids:
                sub_items = "".join(
                    f'<li><a href="{html_escape(_href_label(k)[0])}" data-menu-key="{html_escape(k["key"])}">{_icon_span(k)}{html_escape(_href_label(k)[1])}</a></li>'
                    for k in kids
                )
                parts.append(f'<li class="cms-menu-has-submenu" data-menu-key="{html_escape(it["key"])}">{link_html}<ul class="cms-submenu">{sub_items}</ul></li>')
            else:
                parts.append(f'<li data-menu-key="{html_escape(it["key"])}">{link_html}</li>')
        submenu_style_class = f" cms-menu-submenustyle-{submenu_style}"
        submenu_style_attr = f' data-menu-submenu-style="{submenu_style}"'
        return (
            f'<nav class="cms-menu cms-menu-dropdown cms-menu-{size}{align_class}{link_style_class}{submenu_style_class}{direction_class}" data-menu-items="{items_json}" '
            f'data-menu-style="dropdown" data-menu-size="{size}" data-menu-align="{align}"{highlight_attr}{font_attr}{submenu_style_attr}{direction_attr}{style_attr}>'
            + toggle_btn + '<div class="cms-menu-links"><ul>' + "".join(parts) + "</ul></div></nav>"
        )

    link_class = ' class="cms-menu-btn"' if style == "buttons" else ""
    parts = []
    for it in resolved:
        if it["type"] == "divider":
            parts.append(f'<span class="cms-menu-divider" data-menu-key="{html_escape(it["key"])}" aria-hidden="true"></span>')
            continue
        href, label = _href_label(it)
        parts.append(f'<a href="{html_escape(href)}" data-menu-key="{html_escape(it["key"])}"{link_class}>{_icon_span(it)}{html_escape(label)}</a>')
    button_style_class = f" cms-menu-btnstyle-{button_style}" if style == "buttons" else ""
    menu_class = f"cms-menu cms-menu-{size}{align_class}{link_style_class}{direction_class}" + (" cms-menu-buttons" + button_style_class if style == "buttons" else "")
    button_style_attr = f' data-menu-button-style="{button_style}"' if style == "buttons" else ""
    return (
        f'<nav class="{menu_class}" data-menu-items="{items_json}" data-menu-style="{style}" '
        f'data-menu-size="{size}" data-menu-align="{align}"{highlight_attr}{font_attr}{button_style_attr}{direction_attr}{style_attr}>'
        + toggle_btn + '<div class="cms-menu-links">' + "\n".join(parts) + "</div></nav>"
    )


def _menu_updated_html(db, form, default_direction="horizontal"):
    items, style, size, bg_color, align, highlight_current, text_color, link_style, font, button_style, submenu_style, direction = _parse_menu_form(form, default_direction)
    return _build_menu_links_html(db, items, style, size, bg_color, align, highlight_current, text_color, link_style, font, button_style, submenu_style, direction)


def _parse_menu_meta(html_content):
    """Pulls the items/style/size/align/highlight/bg-color the Menu tool
    baked into its own markup (data-menu-items carries the full ordered
    [{"id","parent"}, ...] list as JSON) back out, so the in-place config
    form's chip list can rebuild exactly what was last saved instead of
    always starting blank. Older menus saved before data-menu-items existed
    only have data-page-ids (flat, no nesting) — fall back to that so they
    don't silently lose their chosen pages."""
    html_content = html_content or ""
    items_match = re.search(r'data-menu-items="([^"]*)"', html_content)
    items = []
    if items_match:
        try:
            items = json.loads(html_unescape(items_match.group(1)))
        except (ValueError, TypeError):
            items = []
    if not items:
        ids_match = re.search(r'data-page-ids="([^"]*)"', html_content)
        raw_ids = ids_match.group(1) if ids_match else ""
        items = [{"id": int(x), "parent": None} for x in raw_ids.split(",") if x.strip().isdigit()]
    # Normalize once here (not in the template or the JS) so every caller —
    # Jinja filtering by type, the JS builder, the drag/nest logic — can
    # assume every item has type/key, regardless of which schema era it
    # was saved under. A page item's key is deterministic ("p<id>") so
    # toggling that same page off/on later reuses the same key.
    normalized = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("type") in ("page", "custom", "divider") and it.get("key"):
            normalized.append(it)
            continue
        pid = it.get("id")
        if not isinstance(pid, int):
            continue
        normalized.append({"key": f"p{pid}", "type": "page", "id": pid, "icon": it.get("icon", ""), "parent": it.get("parent")})
    items = normalized
    style_match = re.search(r'data-menu-style="([^"]*)"', html_content)
    size_match = re.search(r'data-menu-size="([^"]*)"', html_content)
    align_match = re.search(r'data-menu-align="([^"]*)"', html_content)
    font_match = re.search(r'data-menu-font="([^"]*)"', html_content)
    button_style_match = re.search(r'data-menu-button-style="([^"]*)"', html_content)
    submenu_style_match = re.search(r'data-menu-submenu-style="([^"]*)"', html_content)
    direction_match = re.search(r'data-menu-direction="([^"]*)"', html_content)
    bg_color_match = re.search(r'background-color:\s*(#[0-9a-fA-F]{6})', html_content)
    # Plain/dropdown styles store the chosen color as a plain `color:`; the
    # buttons style repurposes the same picker as the button color, stored
    # as the --menu-btn-color custom property instead (see
    # _build_menu_links_html) — check both so the config bar shows
    # whichever one this particular menu actually used.
    text_color_match = re.search(r'(?<!background-)color:\s*(#[0-9a-fA-F]{6})', html_content)
    btn_color_match = re.search(r'--menu-btn-color:\s*(#[0-9a-fA-F]{6})', html_content)
    link_style = "bold" if "cms-menu-style-bold" in html_content else (
        "uppercase" if "cms-menu-style-uppercase" in html_content else "normal"
    )
    style = style_match.group(1) if style_match else "plain"
    size = size_match.group(1) if size_match else "medium"
    align = align_match.group(1) if align_match else "left"
    font = font_match.group(1) if font_match else ""
    button_style = button_style_match.group(1) if button_style_match else "solid"
    submenu_style = submenu_style_match.group(1) if submenu_style_match else "card"
    highlight_current = 'data-highlight-current="1"' in html_content
    bg_color = bg_color_match.group(1) if bg_color_match else ""
    text_color = (btn_color_match.group(1) if btn_color_match else None) or (text_color_match.group(1) if text_color_match else "")
    direction = direction_match.group(1) if direction_match else "horizontal"
    return items, style, size, align, highlight_current, bg_color, text_color, link_style, font, button_style, submenu_style, direction


def _regenerate_menu_html(db, content):
    """Re-resolves a saved Menu tool's HTML against the pages table right
    now, dropping any item whose page no longer exists (_build_menu_links_
    html already does this — see its own docstring — the only thing
    missing was ever calling it again after the initial save). Used by
    page_delete so a menu that included the deleted page updates
    immediately instead of keeping a dead link until someone happens to
    re-open and re-save that menu's own config form."""
    (items, style, size, align, highlight_current, bg_color,
     text_color, link_style, font, button_style, submenu_style, direction) = _parse_menu_meta(content)
    return _build_menu_links_html(
        db, items, style=style, size=size, bg_color=bg_color, align=align,
        highlight_current=highlight_current, text_color=text_color, link_style=link_style,
        font_key=font, button_style=button_style, submenu_style=submenu_style, direction=direction,
    )


def refresh_site_menus(db):
    """Re-points every Menu tool at the pages that exist right now.

    A menu stores which pages it lists, by id, and turns that into HTML
    once. That is fine while pages come and go one at a time — deleting a
    page already regenerates the menus that named it. Changing template is
    the case it was never told about: activating one retires the previous
    template's pages and creates its own, so a menu can be left pointing
    at half a dozen addresses that stopped existing a moment ago. That is
    where "/services" on a coffee shop came from.

    Two things happen here, and the second is why regenerating alone was
    not enough. Rebuilding drops items whose page has gone — but a
    template's pages are often newly created, with new ids, so a menu
    whose items all pointed at the old ones would rebuild to nothing at
    all. A menu that loses every page that way is re-listed from the
    site's current pages instead, which is what it would have been seeded
    with, keeping its own styling.

    Returns how many menus were changed, so a caller can say so.
    """
    changed = 0
    try:
        rows = db.execute(
            "SELECT id, content FROM sections WHERE content LIKE '%cms-menu%'"
        ).fetchall()
    except sqlite3.Error:
        return 0

    pages = db.execute(
        "SELECT id FROM pages WHERE page_type != 'newsletter' ORDER BY nav_order, title"
    ).fetchall()

    for row in rows:
        content = row["content"] or ""
        (items, style, size, align, highlight_current, bg_color, text_color,
         link_style, font, button_style, submenu_style, direction) = _parse_menu_meta(content)

        live = {p["id"] for p in db.execute("SELECT id FROM pages").fetchall()}
        kept = [it for it in items if it["type"] != "page" or it["id"] in live]
        lost_a_page = any(it["type"] == "page" and it["id"] not in live for it in items)

        if lost_a_page and pages:
            #  A page this menu named has been retired, which only happens
            #  when the site has just become a different site. Pruning
            #  alone would leave the navigation listing whichever pages
            #  happened to survive — three of a template's eight, in the
            #  case that prompted this — so the page items are re-listed
            #  from what exists now.
            #
            #  Anything that is NOT a page is kept exactly where it was:
            #  a custom link to somewhere off the site, or a divider, is a
            #  deliberate act that a template change has no opinion about.
            listed = {it["id"] for it in kept if it["type"] == "page"}
            fresh = [{"key": f"p{p['id']}", "type": "page", "id": p["id"],
                      "url": "", "label": "", "icon": "", "parent": ""}
                     for p in pages if p["id"] not in listed]
            kept = [it for it in kept if it["type"] == "page"] + fresh +                    [it for it in kept if it["type"] != "page"]

        rebuilt = _build_menu_links_html(
            db, kept, style=style, size=size, bg_color=bg_color, align=align,
            highlight_current=highlight_current, text_color=text_color,
            link_style=link_style, font_key=font, button_style=button_style,
            submenu_style=submenu_style, direction=direction,
        )
        if rebuilt != content:
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (rebuilt, row["id"]))
            changed += 1
    return changed
