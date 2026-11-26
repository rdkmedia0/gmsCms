"""One style across every copy of a tool, on every page.

Banners, cards, blogs and the list-shaped tools are used again and again,
and keeping them looking alike meant repeating each change on each one.
Each now has "Apply style to all pages", ticked unless the owner unticks
it: a style change made to a ticked tool is made to every other ticked
tool of the same kind. Only what was CHANGED travels, so tools that look
different today stay different until that setting is touched.

Unticking marks the tool's own markup (data-style-own) and it is left
alone. Ticking it again takes on the style of the others.

Only style travels -- never words, pictures, links or which blog is shown.
"""
import json

from bs4 import BeautifulSoup

from . import blocks
from .sections import _clear_text_overrides, _parse_style, _style_str

OWN = "data-style-own"

#  The parts of a banner's own style attribute that are style. Its picture
#  and the picture's focal point belong to that picture.
BANNER_PROPS = ("align-items", "justify-content", "background-size", "min-height",
                "background-color", "--cms-banner-ink")
CARD_PROPS = ("background-color", "color")
BLOG_ATTRS = ("data-blog-style", "data-blog-image")

KIND_CLASS = {"banner": "cms-banner", "card": "cms-card-shape", "blog": "cms-blog"}


def block_choices(key):
    """The drop-down settings of a declared block: its style."""
    spec = blocks.BLOCKS.get(key)
    return [f["name"] for f in spec["fields"] if f.get("kind") == "select"] if spec else []


def class_of(kind):
    return KIND_CLASS.get(kind) or "cms-block-" + kind.split(":", 1)[1]


def kinds_in(html):
    """Every shareable kind of tool this markup could hold."""
    found = [kind for kind, name in KIND_CLASS.items() if name in (html or "")]
    found += ["block:" + key for key in blocks.BLOCKS
              if block_choices(key) and "cms-block-%s" % key in (html or "")]
    return found


def _root(html, kind):
    soup = BeautifulSoup(html or "", "html.parser")
    return soup, soup.find(class_=class_of(kind))


def is_own(html, kind=None):
    for each in ([kind] if kind else kinds_in(html)):
        _, root = _root(html, each)
        if root is not None:
            return root.get(OWN) == "1"
    return False


def mark(html, kind, own):
    """`html` with the tool marked as keeping its own style, or not."""
    soup, root = _root(html, kind)
    if root is None or (root.get(OWN) == "1") == own:
        return html
    if own:
        root[OWN] = "1"
    else:
        del root[OWN]
    return str(soup)


def style_of(html, kind):
    """The tool's style as {setting: value}; None means "not set"."""
    soup, root = _root(html, kind)
    if root is None:
        return {}
    classes = root.get("class") or []
    if kind == "banner":
        props = _parse_style(root.get("style"))
        style = {"box:" + name: props.get(name) for name in BANNER_PROPS}
        style["mask"] = next((c for c in classes if c.startswith("cms-mask-")), None)
        style["fixed"] = "cms-banner-fixed" if "cms-banner-fixed" in classes else None
        overlay = root.find(class_="cms-banner-overlay")
        words = _parse_style(overlay.get("style")) if overlay is not None else {}
        #  The text box's whole style attribute is style, whatever is in it.
        style.update({"text:" + name: value for name, value in words.items()})
        return style
    if kind == "card":
        props = _parse_style(root.get("style"))
        style = {"box:" + name: props.get(name) for name in CARD_PROPS}
        style["shape"] = next((c for c in classes
                               if c.startswith("cms-card-") and c != "cms-card-shape"), None)
        return style
    if kind == "blog":
        return {name: root.get(name) for name in BLOG_ATTRS}
    key = kind.split(":", 1)[1]
    _, values = blocks.parse_block(html)
    return {name: (values or {}).get(name) for name in block_choices(key)}


def differences(before, after):
    return {name: after.get(name) for name in set(before) | set(after)
            if before.get(name) != after.get(name)}


def _set_props(el, wanted):
    props = _parse_style(el.get("style"))
    for name, value in wanted.items():
        if value is None:
            props.pop(name, None)
        else:
            props[name] = value
    if _style_str(props):
        el["style"] = _style_str(props)
    elif el.has_attr("style"):
        del el["style"]


def _swap_class(el, belongs, new):
    classes = [c for c in (el.get("class") or []) if not belongs(c)]
    el["class"] = classes + ([new] if new else [])


def apply(html, kind, changes):
    """`html` with these settings changed; unchanged markup comes back as is."""
    current = style_of(html, kind)
    changes = {k: v for k, v in changes.items() if current.get(k) != v}
    if not changes:
        return html
    soup, root = _root(html, kind)
    if root is None:
        return html
    if kind.startswith("block:"):
        _, values = blocks.parse_block(html)
        values.update({k: v for k, v in changes.items() if v is not None})
        return mark(blocks.build(kind.split(":", 1)[1], values), kind, root.get(OWN) == "1")
    if kind == "blog":
        for name, value in changes.items():
            if value is not None:
                root[name] = value
        return str(soup)
    box = {k[4:]: v for k, v in changes.items() if k.startswith("box:")}
    if box:
        _set_props(root, box)
    if "mask" in changes:
        _swap_class(root, lambda c: c.startswith("cms-mask-"), changes["mask"])
    if "fixed" in changes:
        _swap_class(root, lambda c: c == "cms-banner-fixed", changes["fixed"])
    if "shape" in changes:
        _swap_class(root, lambda c: c.startswith("cms-card-") and c != "cms-card-shape",
                    changes["shape"])
    words = {k[5:]: v for k, v in changes.items() if k.startswith("text:")}
    overlay = root.find(class_="cms-banner-overlay")
    if words and overlay is not None:
        _set_props(overlay, words)
        _clear_text_overrides(overlay, [
            css for css, source in (("color", "color"), ("font-size", "--cms-banner-size"),
                                    ("font-family", "font-family"), ("text-align", "text-align"))
            if source in words])
    return str(soup)


#  ---------------------------------------------------------------- the site

def _rows(db):
    """Sections that are on the site: every page's, and the active
    template's header, footer and sidebars."""
    return db.execute(
        "SELECT id, content FROM sections WHERE page_id IS NOT NULL OR template_id = "
        "(SELECT id FROM templates WHERE is_active = 1) ORDER BY id").fetchall()


def _walk(node, change):
    """Applies `change` to every piece of tool markup in a Columns tree."""
    if isinstance(node, list):
        return [_walk(item, change) for item in node]
    if isinstance(node, dict):
        out = {key: _walk(value, change) for key, value in node.items()}
        if isinstance(out.get("content"), str):
            out["content"] = change(out["content"])
        return out
    return node


def _each_markup(content, change):
    if content and content.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(content)
        except ValueError:
            return change(content)
        new = _walk(data, change)
        return content if new == data else json.dumps(new)
    return change(content)


def peer_style(db, kind):
    """The style the ticked tools of this kind are wearing: the first one's,
    in the order they were made. None when there is no such tool."""
    found = []

    def look(html):
        if not found and class_of(kind) in (html or ""):
            _, root = _root(html, kind)
            if root is not None and root.get(OWN) != "1":
                found.append(style_of(html, kind))
        return html

    for row in _rows(db):
        _each_markup(row["content"] or "", look)
        if found:
            return found[0]
    return None


def take_on(html, kind, style):
    """`html` wearing exactly this style (anything it has that the style
    does not is taken off)."""
    wanted = dict.fromkeys(style_of(html, kind))
    wanted.update(style)
    return apply(html, kind, wanted)


def propagate(db, kind, changes):
    """Makes these changes to every ticked tool of this kind. Returns how
    many sections changed. The caller commits."""
    def change(html):
        if class_of(kind) not in (html or "") or is_own(html, kind):
            return html
        return apply(html, kind, changes)

    count = 0
    for row in _rows(db):
        new = _each_markup(row["content"] or "", change)
        if new != (row["content"] or ""):
            db.execute("UPDATE sections SET content = ? WHERE id = ?", (new, row["id"]))
            count += 1
    return count


def adopt(db, content):
    """A newly placed tool starts in the style the others are wearing."""
    for kind in kinds_in(content):
        style = peer_style(db, kind)
        if style:
            #  Only what the others have set: a new tool keeps its own
            #  starting values for anything they leave alone.
            content = apply(content, kind, {k: v for k, v in style.items() if v is not None})
    return content


def save(where, kind, content, form, untouched=None, **write):
    """Writes a tool after a toolbar change, and shares its style.

    `where` still holds the markup as it was. `untouched` is what saving
    that toolbar with nothing changed would produce: a toolbar sends every
    setting, and writing its defaults down is not the owner changing them,
    so only the difference from `untouched` is shared. Returns
    (content, sync): sync is True when other things on screen are now out
    of date.
    """
    db = where.db
    before = where.read()
    was_own = is_own(before, kind)
    if "apply_all_present" in form:
        share = form.get("apply_all") == "1"
    else:
        share = not was_own
    rejoining = share and was_own
    if rejoining:
        style = peer_style(db, kind)
        if style:
            content = take_on(content, kind, style)
    content = mark(content, kind, not share)
    changes = differences(style_of(untouched or before, kind), style_of(content, kind))
    where.write(content, **write)
    others = 0
    if share and not was_own and changes:
        #  The tool just written already has these, so this passes over it.
        others = propagate(db, kind, changes)
        db.commit()
    return content, bool(rejoining or others)
