"""Where two tools use the same word, they must mean the same thing.

The Breadcrumb and the Menu both offer a "pill badge". The Menu's was
first built as a button style -- a filled pill on every item -- which is
a row of buttons with a rounder corner and not a badge at all. A badge
marks ONE thing: the page you are on.

An editor stops being learnable when a word means two things in it, and
nothing in a stylesheet stops the two drifting apart again, so the rule
is asserted here rather than trusted.

    python tools/design_conventions_check.py
"""
import os
import re
import sys

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _here)

passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print("  %-58s %s%s" % (what, "ok" if ok else "FAILED", "   " + detail if detail and not ok else ""))


css = open(os.path.join(_here, "app", "static", "css", "site-base.css"), encoding="utf-8").read()


def declarations(selector, first_only=True):
    """The property:value pairs a selector sets, order-independent.

    A selector may appear more than once -- the menu badge states its
    look in one rule and undoes the usual current-page marking in
    another -- so the comparison takes the first block, which is the one
    carrying the shared look.
    """
    found = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not found:
        return None
    return sorted(part.strip() for part in found.group(1).split(";") if part.strip())


print("A pill badge means the same in the Breadcrumb and the Menu")
print("-" * 70)
crumb = declarations(".cms-breadcrumb-style-pill .cms-breadcrumb-current")
menu = declarations(".cms-menu-badge a.cms-menu-current")
check("the breadcrumb declares one", crumb is not None)
check("the menu declares one", menu is not None)
check("they are the same declarations", crumb == menu, "%s vs %s" % (crumb, menu))
check("and take their colour from the palette, not the button colour",
      bool(crumb) and any("accent" in d for d in crumb) and not any("menu-btn" in d for d in crumb))

print()
print("A badge is not a button")
print("-" * 70)
from app import create_app                                          # noqa: E402
from app.db import get_db                                           # noqa: E402
from app.services.menu import _build_menu_links_html, MENU_BUTTON_STYLES   # noqa: E402

app = create_app()
with app.test_request_context("/"):
    db = get_db()
    items = [{"key": "c1", "type": "custom", "label": "Home", "url": "/", "icon": "", "parent": None},
             {"key": "c2", "type": "custom", "label": "About", "url": "/about", "icon": "", "parent": None}]
    badge = _build_menu_links_html(db, items, style="pill", highlight_current=True)
    buttons = _build_menu_links_html(db, items, style="buttons", highlight_current=True)
    check("a badge menu carries no button class", "cms-menu-buttons" not in badge)
    check("its links are plain links", "cms-menu-btn" not in badge)
    check("it says which page you are on", "data-highlight-current" in badge)
    check("a button menu still draws buttons", "cms-menu-btn" in buttons)
    check("pill is not offered as a button style too",
          "pill" not in MENU_BUTTON_STYLES, str(MENU_BUTTON_STYLES))

print()
print("One fact gets one mark")
print("-" * 70)
#  The usual current-page treatment is bold plus an underline. With a
#  badge that is three marks for one fact, and the Breadcrumb's badge
#  carries neither.
_undo = re.findall(r"\.cms-menu-badge a\.cms-menu-current\s*\{([^}]*)\}", css)
_all = " ".join(_undo)
check("the badge drops the underline", "text-decoration: none" in _all)
check("and the bold", "font-weight: inherit" in _all)

print()
print("Nobody is asked to type HTML")
print("-" * 70)
#  CLAUDE.md: never a raw HTML textarea as the way to accomplish ordinary
#  styling or layout. The page editor had one removed once already; the
#  blog post editor still had one, showing <p> tags to somebody writing a
#  post.
_admin = os.path.join(_here, "app", "templates", "admin")
_raw = []
for _name in sorted(os.listdir(_admin)):
    if not _name.endswith(".html"):
        continue
    _t = open(os.path.join(_admin, _name), encoding="utf-8").read()
    for _m in re.finditer(r"<textarea[^>]*>", _t):
        _tag = _m.group(0)
        #  A field holding a post's or a page's writing must be upgraded.
        if 'name="content"' in _tag and "data-richtext" not in _tag:
            _raw.append(_name)
check("no admin form takes a post's writing as raw HTML", not _raw, ", ".join(_raw))
check("the blog editor loads the rich-text script",
      "js/admin/rich-text.js" in open(os.path.join(_admin, "blog_post_edit.html"), encoding="utf-8").read())

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
