"""Are the email layouts things an inbox can actually render?

Every rule here exists because a client breaks it: a stylesheet is
stripped, a class means nothing, flex and grid are not implemented, and
padding on an inline element is ignored by Outlook. The old newsletter
was checked by sending it and looking -- which is how five tools came to
arrive empty without anyone noticing.

    python tools/email_layout_check.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                                         # noqa: E402
from app.services import email_layouts, newsletter                 # noqa: E402

passed = failed = 0


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
        html = email_layouts.render(key, FILLED, look)
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
    letter = bodies["letter"]
    check("angle brackets are escaped, not rendered", "&lt;&amp;&gt;" in letter, letter[:70])
    check("a blank line makes a new paragraph", letter.count("<p ") >= 2)
    check("a single newline stays a line break", "<br>" in letter)

    print()
    print("The screen can build itself, and refuse for a reason")
    print("-" * 68)
    for key, name, blurb in email_layouts.choices():
        fields = email_layouts.fields_for(key)
        check("%s: every field has a label" % key, all(f["label"] for f in fields))
        check("%s: every field has a hint or needs none" % key,
              all("hint" in f for f in fields))
    check("an empty announcement says what is missing",
          email_layouts.missing("announcement", {}) == ["Heading", "Button", "Button goes to"],
          str(email_layouts.missing("announcement", {})))
    check("a filled one is ready to send", email_layouts.missing("announcement", FILLED) == [])

    print()
    print("The wrapper does not undo the layout")
    print("-" * 68)
    wrapped = newsletter.to_email_html(
        [{"type": "html", "title": "", "content": bodies["story"]}],
        "S", "u", "s", look=look)
    check("no element ends up with two style attributes",
          not re.search(r"<[a-z]+[^>]*style=[^>]*style=", wrapped, re.I))
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
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
