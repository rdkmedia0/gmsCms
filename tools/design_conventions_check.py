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
print("The rich-text toolbar exists once")
print("-" * 70)
#  It was defined in public/page.html and reimplemented, smaller, for the
#  blog editor. One markup source and one dispatch now, so a button added
#  in one place appears in both.
_tpl = os.path.join(_here, "app", "templates")
_defs = []
for _root, _dirs, _files in os.walk(_tpl):
    for _f in _files:
        if not _f.endswith(".html"):
            continue
        _t = open(os.path.join(_root, _f), encoding="utf-8").read()
        if "macro wysiwyg_toolbar" in _t:
            _defs.append(os.path.relpath(os.path.join(_root, _f), _tpl))
check("the toolbar markup is declared in one place", len(_defs) == 1, ", ".join(_defs))
check("and it is the shared partial",
      _defs == [os.path.join("partials", "wysiwyg_toolbar.html")], str(_defs))

_js = os.path.join(_here, "app", "static", "js")
check("the command dispatch has its own module",
      os.path.isfile(os.path.join(_js, "wysiwyg-commands.js")))
_inline = open(os.path.join(_js, "inline-editor.js"), encoding="utf-8").read()
_rich = open(os.path.join(_js, "admin", "rich-text.js"), encoding="utf-8").read()
check("the live editor uses it", "cmsWysiwyg.bindToolbar" in _inline)
check("the admin field uses it too", "cmsWysiwyg.bindToolbar" in _rich)
check("and neither runs execCommand for the toolbar itself",
      "execCommand" not in _rich, "rich-text.js still dispatches its own")

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
print("Every screen that sends something to an AI says so")
print("-" * 70)
#  NAMED, so it can be CHECKED. A screen that hands somebody's words or
#  pictures to a provider has to say where they go -- and the surfaces
#  are few and known, so a list here catches the fifth one rather than
#  hoping whoever writes it remembers.
#
#  One partial, not a paragraph pasted four times: pasted, it would
#  differ on the fifth screen, and a notice that is wrong somewhere is
#  worse than none because it teaches people to skip it.
SENDS_TO_AI = (
    "admin/theme_generator.html",       # a brief, a paste, a picture
    "partials/assistant_panel.html",    # every question asked of it
    "partials/newsletter_editor.html",  # write a first draft with AI
)
for _name in SENDS_TO_AI:
    _text = open(os.path.join(_tpl, _name.replace('/', os.sep)), encoding="utf-8").read()
    check("%s carries the AI notice" % _name,
          "partials/ai_notice.html" in _text)

_notice = open(os.path.join(_tpl, "partials", "ai_notice.html"),
                  encoding="utf-8").read()
#  It has to name WHICH provider and WHERE: three of the four are
#  self-hosted, and telling somebody their own server is a third party
#  trains them to ignore the warning that matters.
check("the notice names the provider rather than saying 'a third party'",
      "ai_destination()" in _notice and "ai.label" in _notice)
check("...and says nothing at all when no AI is configured",
      "ai.ready" in _notice)

print()
print("A form that takes a file says so")
print("-" * 70)
#  Without enctype the browser posts a file input's NAME and no bytes,
#  so `request.files` is empty and the server sees nothing at all. It
#  cost a full run to find, because the failure is silent and looks
#  exactly like the owner having uploaded nothing.
#
#  Checked by walking every admin template rather than by naming them:
#  the next form to take a file is the one that will forget.
for _root, _dirs, _files in os.walk(_tpl):
    for _f in _files:
        if not _f.endswith(".html"):
            continue
        _path = os.path.join(_root, _f)
        _t = open(_path, encoding="utf-8").read()
        #  A file input with a NAME is one the browser will post; a
        #  nameless one is read in JavaScript and sent some other way,
        #  which is how every picture control in the editor works and
        #  how the reference picture works. Only the first kind needs
        #  the form to be multipart, and flagging the second would be a
        #  check that cries wolf on six controls that are correct.
        posted = (re.search(r'type="file"[^>]*\sname=', _t)
                  or re.search(r'name="[^"]+"[^>]*type="file"', _t))
        if not posted:
            continue
        _rel = os.path.relpath(_path, _tpl)
        #  The form tag that encloses it -- these templates carry one
        #  form each around any file input they have.
        check("%s posts as multipart" % _rel,
              "enctype=" in _t and "multipart/form-data" in _t,
              "has a file input and no enctype")

print()
print("A portrait is an option on the Banner, not a tool of its own")
print("-" * 70)
#  The shape every profile page has settled on: a round photograph of a
#  person overlapping the bottom edge of a wide one. It belongs to the
#  Banner because that is what it is -- the same band with a face on it.
#  A tool of its own would mean a second thing to place, a second thing
#  to style, and a rule about which of the two owns the space they share.
sys.path.insert(0, _here)
from app.services import sections as _sec                     # noqa: E402
_start = ('<div class="cms-banner"><div class="cms-banner-overlay">'
          "<h2>Hello</h2></div></div>")
_left = _sec._update_banner_portrait(_start, "left")
check("a portrait can be put on a banner",
      _sec.banner_portrait_of(_left) == "left")
_shot = _sec._set_banner_portrait_image(_left, "/static/uploads/me.png")
check("...and given a picture", "/static/uploads/me.png" in _shot)
_moved = _sec._update_banner_portrait(_shot, "right")
check("...moved without losing it",
      _sec.banner_portrait_of(_moved) == "right" and "me.png" in _moved)
_gone = _sec._update_banner_portrait(_moved, "none")
check("...and removed without losing the words",
      _sec.banner_portrait_of(_gone) == "none" and "<h2>Hello</h2>" in _gone)
#  Three positions, and it works with no background picture at all --
#  somebody with a headshot and no cover photograph should not have to
#  find one.
check("left, centre and right are all offered",
      set(_sec.BANNER_PORTRAITS) == {"none", "left", "center", "right"},
      str(_sec.BANNER_PORTRAITS))
check("...and a banner with no picture can still carry one",
      _sec.banner_portrait_of(
          _sec._update_banner_portrait('<div class="cms-banner"></div>',
                                       "center")) == "center")

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
