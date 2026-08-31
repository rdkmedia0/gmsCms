"""Are the email layouts things an inbox can actually render?

Every rule here exists because a client breaks it: a stylesheet is
stripped, a class means nothing, flex and grid are not implemented, and
padding on an inline element is ignored by Outlook. The old newsletter
was checked by sending it and looking -- which is how five tools came to
arrive empty without anyone noticing.

    python tools/email_layout_check.py
"""
import io
import os
import re
import sys

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _here)

from app import create_app                                         # noqa: E402
from app.services import email_layouts, newsletter                 # noqa: E402

passed = failed = 0


NL = chr(10)


def _source(rel):
    """One of the files this checks the CONTENT of, read as text."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return io.open(os.path.join(here, rel), encoding="utf-8").read()


#  The editor's markup lives in a PARTIAL now: it is the top of the
#  Newsletters page as well as its own screen, and two copies of it is
#  how the two screens come to offer different controls. Both are read,
#  so an assertion about "the editor" is about wherever it is written.
ISSUE_EDIT = (_source("app/templates/partials/newsletter_editor.html")
              + _source("app/templates/admin/newsletter_issue_edit.html"))
EDITOR_JS = _source("app/static/js/admin/newsletter-editor.js")
#  The serialiser is shared with the system-messages canvas now: both
#  are "the thing being written into is the thing that gets sent", and
#  a second copy is where the two would come to disagree.
SERIALISER_JS = _source("app/static/js/admin/rich-serialiser.js")
WORDING_JS = _source("app/static/js/admin/wording-editor.js")
BLOCKS_TPL = _source("app/templates/emails/blocks.html")
NEWSLETTERS_SCREEN = _source("app/templates/admin/newsletters.html")


def check(what, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print("  %-56s %s%s" % (what, "ok" if ok else "FAILED", "   " + detail if detail and not ok else ""))


FILLED = {
    "heading": "Spring news <&>",
    "body": "First paragraph.\n\nSecond one, with a line\nbreak in it.",
    "image": "https://example.com/a.png",
    "button_label": "Read it",
    "button_url": "https://example.com/x",
    "left_heading": "One", "left_body": "Left words.",
    "right_heading": "Two", "right_body": "Right words.",
}

app = create_app()
look = newsletter.look_from({"primary": {"base": "#b5541e", "lightest": "#fcf8f6"}},
                            {"heading": "Georgia, serif", "body": "Georgia, serif"})

with app.test_request_context("/"):
    print("Every layout renders")
    print("-" * 68)
    bodies = {}
    for key, name, blurb in email_layouts.choices():
        #  Its own starting arrangement, filled in -- a layout IS its
        #  blocks now, so rendering it any other way would check
        #  something nobody ever sends.
        blocks = email_layouts.starting_blocks(key)
        for block in blocks:
            if block["type"] == "image":
                block["src"] = "https://example.test/p.png"
            elif block["type"] == "button":
                block["label"] = "Read it"
                block["url"] = "https://example.test/"
        html = email_layouts.render(blocks, look)
        bodies[key] = html
        check("%s renders something" % name, len(html.strip()) > 80)

    print()
    print("What an inbox can cope with")
    print("-" * 68)
    for key, html in bodies.items():
        check("%s: laid out with tables" % key, "<table" in html)
        check("%s: no stylesheet to strip" % key,
              "<style" not in html.lower() and "<link" not in html.lower())
        check("%s: no class to resolve" % key, 'class="' not in html)
        check("%s: no flex or grid" % key,
              "display:flex" not in html.replace(" ", "") and "display:grid" not in html.replace(" ", ""))
        check("%s: every visible box carries its own style" % key,
              html.count("style=") >= html.count("<p") )
        check("%s: no script" % key, "<script" not in html.lower())

    print()
    print("The site's look reaches the message")
    print("-" * 68)
    story = bodies["story"]
    check("the template's colour is on the button", look["accent"] in story, look["accent"])
    check("the template's font stack is on the words", "Georgia, serif" in story)
    check("a button is a table, not a padded link",
          re.search(r"<table[^>]*>\s*<tr>\s*<td[^>]*bgcolor", story, re.S) is not None)
    check("a picture cannot burst the card", "max-width:536px" in story)
    #  The wrapper inlines width:100% onto every table, which would make a
    #  button as wide as the card.
    wrapped_story = newsletter.to_email_html(
        [{"type": "html", "title": "", "content": story}], "S", "u", "s", look=look)
    btn = re.search(r"<table[^>]*>\s*<tr>\s*<td[^>]*bgcolor[^>]*>", wrapped_story, re.S)
    check("a button stays the width of its label",
          bool(btn) and "width:auto" in btn.group(0), (btn.group(0)[:90] if btn else "none"))

    print()
    print("What the owner typed is safe")
    print("-" * 68)
    #  A fixture of its own: reading these off whatever words a layout
    #  happens to ship made the check depend on the sample text, so
    #  rewording a template broke it.
    typed = email_layouts.render([{
        "type": "text",
        "text": "<&> first line" + NL + "second line" + NL + NL + "a new paragraph",
    }], look)
    check("angle brackets are escaped, not rendered", "&lt;&amp;&gt;" in typed, typed[:70])
    check("a blank line makes a new paragraph", typed.count("<p ") >= 2, typed[:90])
    check("a single newline stays a line break", "<br>" in typed, typed[:90])

    print()
    print("Choosing a shape happens in the editor, not before it")
    print("-" * 68)
    #  There WAS a picker on the Newsletters screen: four specimens to
    #  choose between before writing a word. It is gone. The editor's
    #  Template dropdown already makes that choice and makes it better,
    #  at full size with the blocks in front of you -- and a choice
    #  offered twice is one somebody makes twice, the earlier time with
    #  less information.
    #
    #  Checked because the dead-code rule applies to code written today:
    #  `sample()` and the `specimen` render mode existed only for that
    #  picker, and this repository carried a removed importer's leavings
    #  for months.
    check("the picker is gone from the Newsletters screen",
          "cms-layout-choice" not in NEWSLETTERS_SCREEN)
    check("...and so is the code that fed it",
          not hasattr(email_layouts, "sample"))
    check("...and the render mode written for it",
          "specimen" not in open(
              "/app/app/templates/emails/blocks.html", encoding="utf-8").read())
    #  ...and there is no button to start one either: the creation tool
    #  IS the top of the page now, so the page always has a newsletter in
    #  it rather than a button that makes one.
    check("the creation tool is the page, not a button that opens one",
          "partials/newsletter_editor.html" in NEWSLETTERS_SCREEN
          and "Write a newsletter</button>" not in NEWSLETTERS_SCREEN)
    check("the shape is chosen in the editor",
          "layout-select" in ISSUE_EDIT and "layoutStarts" in EDITOR_JS)


    print()
    print("The vocabulary a body may use, and only that")
    print("-" * 68)
    #  Everything the toolbar can produce, written down as text. The
    #  editor's serialiser is the exact inverse of this; if it drifts, a
    #  newsletter stops reading back the way it was written.
    vocab_look = {"body_font": "Georgia, serif", "heading_font": "Palatino, serif",
                  "accent": "#a3352a"}
    src = ("## A heading" + NL
           + "Words with **bold** and *italic* and [a link](https://x.test)." + NL
           + "A second line of the same paragraph." + NL + NL
           + "- first bullet" + NL
           + "- second bullet" + NL + NL
           + "### A smaller heading" + NL
           + "[not a link](javascript:alert(1)) stays as it was typed." + NL
           + "<script>alert(1)</script>")
    out = email_layouts.rich(src, vocab_look)
    joined = "".join(out)
    check("## makes a heading", out[0].startswith("<h2 "), out[0][:40])
    check("### makes a smaller heading", any(b.startswith("<h3 ") for b in out))
    check("** makes bold", "<strong>bold</strong>" in joined)
    check("* makes italic", "<em>italic</em>" in joined)
    check("- makes one list, not one per line", joined.count("<ul") == 1
          and joined.count("<li") == 2)
    check("a link is a link", '<a href="https://x.test"' in joined)
    check("a script-scheme link stays plain text",
          "javascript:alert(1)) stays" in joined and 'href="javascript' not in joined)
    check("typed markup is escaped, never rendered",
          "&lt;script&gt;" in joined and "<script>" not in joined)

    #  The email carries its style on the tag, because most clients strip
    #  a stylesheet -- and it carries the SITE's, not a default.
    check("every block carries an inline style",
          all(' style="' in b for b in out))
    check("the body font reaches a paragraph", "Georgia, serif" in joined)
    check("the heading font reaches a heading", "Palatino, serif" in joined)
    check("the site's colour reaches a link", "#a3352a" in joined)

    #  One dictionary, read by the email and by the editor. If these
    #  stopped agreeing, a heading made by the toolbar would look one way
    #  on screen and another in the inbox.
    st = email_layouts.block_styles(vocab_look)
    check("the editor is given the same styles the email writes",
          all(st[k] in joined for k in ("p", "h2", "h3", "ul", "li", "a")))
    check("the screen hands those styles to the editor",
          "cms-email-block-styles" in ISSUE_EDIT and "block_styles" in ISSUE_EDIT)
    #  Per block, not one set for the whole email: a block can carry its
    #  own font and colour now, so the editor reads the styles off the
    #  block it is editing rather than off the page.
    check("the editor reads them rather than repeating them",
          "data-styles" in BLOCKS_TPL and "stylesFor" in EDITOR_JS
          and "dataset.styles" in EDITOR_JS)

    print()
    print("The editor is the email, with tools")
    print("-" * 68)
    check("the shared toolbar is used, not a second one",
          "wysiwyg_toolbar" in ISSUE_EDIT and "wysiwyg-commands.js" in ISSUE_EDIT)
    check("what an email cannot honour is not offered",
          "include_layout=false" in ISSUE_EDIT)
    check("the toolbar acts on the slot being written in",
          "lastBody" in EDITOR_JS)
    check("a block the toolbar makes is styled like the sent one",
          "function restyle" in EDITOR_JS and "restyle(el)" in EDITOR_JS)
    check("the serialiser reads headings back",
          '"## "' in SERIALISER_JS and '"### "' in SERIALISER_JS)
    check("the serialiser reads emphasis and links back",
          '"**"' in SERIALISER_JS.replace(chr(39), chr(34))
          or '**" + inner' in SERIALISER_JS)
    #  One serialiser, two canvases. Both of them are the same idea --
    #  what is written into is what is sent -- and the inverse of rich()
    #  existing twice is the place they would come to disagree about
    #  what a heading is.
    check("...and it is the one BOTH canvases use",
          "window.cmsRichText" in EDITOR_JS and "window.cmsRichText" in WORDING_JS)
    check("...so neither keeps a copy of its own",
          "function textFromBlocks" not in EDITOR_JS
          and "function inline" not in WORDING_JS)

    print()
    print("A picture sits where the alignment says")
    print("-" * 68)
    #  It was `margin:0 auto` -- centred and nothing else. The cell
    #  around it did carry `text-align:left`, which a display:block image
    #  does not listen to, so the control was set, stored, shown in the
    #  panel as "Left" and ignored. Every half-width picture was centred
    #  whatever anybody chose, and nothing on screen said why.
    where = {}
    for how in ("left", "center", "right"):
        html = email_layouts.render(
            [{"type": "image", "src": "/p.png", "alt": "", "url": "", "scale": 50,
              "style": {"align": how}}], look)
        bit = html[html.index("<img"):]
        bit = bit[:bit.index(">")]
        where[how] = bit[bit.index("margin:"):].split(";")[0]
    check("left is against the left edge", where["left"] == "margin:0 auto 0 0",
          where["left"])
    check("centred is centred", where["center"] == "margin:0 auto", where["center"])
    check("right is against the right edge", where["right"] == "margin:0 0 0 auto",
          where["right"])
    #  A picture with nothing said follows the same default every other
    #  block does. One convention per control: the same control on two
    #  blocks has to mean the same thing.
    plain = email_layouts.render(
        [{"type": "image", "src": "/p.png", "alt": "", "url": "", "scale": 50,
          "style": {}}], look)
    check("...and saying nothing is the same as saying left",
          "margin:0 auto 0 0" in plain, plain[plain.index("<img"):][:200])


    print()
    print("The screen can build itself, and refuse for a reason")
    print("-" * 68)
    for key, name, blurb in email_layouts.choices():
        blocks = email_layouts.starting_blocks(key)
        check("%s: lays out real blocks" % key, len(blocks) > 0)
        check("%s: every block is one this app can render" % key,
              all(b["type"] in email_layouts.BLOCK_TYPES for b in blocks))
    check("every kind of block has a name and a hint",
          all(v.get("name") and v.get("hint") for v in email_layouts.BLOCK_TYPES.values()))
    check("the Insert menu offers every kind, once",
          sorted(email_layouts.BLOCK_ORDER) == sorted(email_layouts.BLOCK_TYPES))

    #  What stops a send is a block that would arrive BROKEN, named so the
    #  refusal says what to do rather than that something is wrong.
    empty = email_layouts.missing([])
    check("an empty newsletter says so", empty == ["There are no words in it yet"], str(empty))
    half = email_layouts.missing([
        {"type": "heading", "text": "Hello"},
        {"type": "button", "label": "Book now", "url": ""},
        {"type": "image", "src": ""},
    ])
    check("a button with nowhere to go is named",
          any("no web address" in g for g in half), str(half))
    check("an empty picture slot is named",
          any("no picture" in g for g in half), str(half))
    check("a newsletter with words and nothing broken is ready",
          email_layouts.missing([{"type": "heading", "text": "Hello"}]) == [])

    #  Every style a block may carry has to survive being written down and
    #  read back, or a control that appears to work quietly does nothing.
    styled = email_layouts.normalise([{
        "type": "text", "text": "Hi",
        "style": {"bg": "#fff3cd", "color": "#402000", "align": "center",
                  "font": "Georgia, 'Times New Roman', serif",
                  "shadow": "3px 3px red"},
    }])
    check("a block keeps the styles an inbox honours",
          styled[0]["style"] == {"bg": "#fff3cd", "color": "#402000",
                                 "align": "center",
                                 "font": "Georgia, 'Times New Roman', serif"},
          str(styled[0]["style"]))
    check("...and drops anything else", "shadow" not in styled[0]["style"])
    check("a colour that is not a colour is refused",
          email_layouts.normalise([{"type": "text", "style": {"bg": "red; x:y"}}])[0]["style"] == {})
    check("a font nobody has is refused",
          email_layouts.normalise([{"type": "text",
                                    "style": {"font": "Comic Sans MS"}}])[0]["style"] == {})
    check("a block type this app cannot render is dropped",
          email_layouts.normalise([{"type": "carousel"}]) == [])

    #  Somebody's draft, written before blocks existed.
    old = email_layouts.from_named_slots(
        {"heading": "Autumn", "body": "Words.", "button_label": "Go",
         "button_url": "https://example.test/"})
    check("a newsletter written the old way still opens",
          [b["type"] for b in old] == ["heading", "text", "button"],
          str([b["type"] for b in old]))
    check("...with what was written still in it",
          old[0]["text"] == "Autumn" and old[2]["url"] == "https://example.test/")

    print()
    print("The wrapper does not undo the layout")
    print("-" * 68)
    wrapped = newsletter.to_email_html(
        [{"type": "html", "title": "", "content": bodies["story"]}],
        "S", "u", "s", look=look)
    #  Proof the rule can fail: the same test against markup that really
    #  does carry two style attributes must come back False. A regex with
    #  a mistyped escape matches nothing and passes everything, which is
    #  how this file shipped a check that could never fail.
    check("...and this rule can actually fail",
          bool(re.search(r"<[a-z]+ [^>]*style=[^>]*style=",
                         '<a style="a" href="#" style="b">x</a>', re.I)))
    check("no element ends up with two style attributes",
          not re.search(r"<[a-z]+\b[^>]*style=[^>]*style=", wrapped, re.I))
    #  The label sat on the accent and was recoloured to the accent.
    label = re.search(r"<a[^>]*>Read it</a>", wrapped, re.I)
    check("a button label keeps its own colour",
          bool(label) and "#ffffff" in label.group(0), label.group(0)[:80] if label else "no button")

    print()
    print("It composes with the wrapper that must not change")
    print("-" * 68)
    full = newsletter.to_email_html(
        [{"type": "html", "title": "", "content": bodies["letter"]}],
        "TLC Coaching", "https://example.com/u", "Sender line here", look=look)
    check("the unsubscribe link survives", "https://example.com/u" in full)
    check("the sender line survives", "Sender line here" in full)
    check("the card stays light", "background:#ffffff" in full)

print()
print("Nothing carries an invisible character")
print("-" * 68)
#  A mistyped escape put a literal backspace (chr 8) where a regex word
#  boundary belonged. The pattern then matched nothing -- silently, since
#  a rule written as `not re.search(...)` passes when it matches nothing.
#  It is invisible in an editor, in grep and in inspect.getsource. So it
#  is looked for by code from now on, across everything shipped.
import os as _os
WHITESPACE = (chr(9), chr(10), chr(13))
#  Not a control character, and every bit as invisible: a U+00A0 that
#  got into a regex or an identifier reads as a space in every editor
#  and matches nothing. Allowed in TEMPLATES, where it is a real
#  typographic choice, and never in code.
NBSP = chr(0xA0)
_nbsp = []
_bad = []
for _root, _dirs, _files in _os.walk(_os.path.join(_here, "app")):
    _dirs[:] = [d for d in _dirs if d not in ("__pycache__", "fonts", "themes", "uploads")]
    for _f in _files:
        if not _f.endswith((".py", ".html", ".css", ".js", ".j2")):
            continue
        _p = _os.path.join(_root, _f)
        try:
            _s = open(_p, encoding="utf-8").read()
        except Exception:
            continue
        #  C0 (below 32) AND C1 (127-159). The first sweep only looked
        #  below 32 and missed a real one: an em dash in site-base.css
        #  had become U+0081 + "4", almost certainly a cp1252 round-trip,
        #  and it shipped into a message shown to the admin. A C1 control
        #  is every bit as invisible as a C0 one and rather more likely,
        #  because it is what a mangled encoding actually produces.
        _hit = next((c for c in _s
                     if (ord(c) < 32 or 127 <= ord(c) <= 159) and c not in WHITESPACE), None)
        if _hit is not None:
            _bad.append("%s (U+%04X)" % (_os.path.relpath(_p, _here), ord(_hit)))
        #  In CODE only: a template may legitimately want one between two
        #  words that must not be split across a line.
        if _f.endswith((".py", ".css", ".js")) and NBSP in _s:
            _nbsp.append(_os.path.relpath(_p, _here))
check("no control characters anywhere in app/", not _bad, ", ".join(_bad[:3]))
check("no invisible non-breaking spaces in code", not _nbsp, ", ".join(_nbsp[:3]))

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
