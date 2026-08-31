"""The words an owner writes reach the messages that go out on their own.

Four messages send themselves — an order lands, somebody signs up,
somebody confirms — so nobody is watching when they are wrong. The
failure this is the net under is quiet in both directions: a greeting
that never arrives, and a FACT that an owner managed to delete.

Walked with the mail captured rather than sent, on a throwaway site:

  * does what the owner wrote actually reach the message?
  * do the facts survive, whatever the owner wrote?
  * is a placeholder this app cannot fill left visible rather than
    becoming a blank?
  * does the preview show the same words the real thing sends?

Run inside the container:

    docker compose exec -T web python tools/site_emails_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="site-emails-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import mailer                                        # noqa: E402
from app.services import site_emails, subscribers             # noqa: E402

NL = chr(10)

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = lambda settings, to, subject, html, text, from_name=None, headers=None: \
    SENT.append({"to": to, "subject": subject, "html": html, "text": text})

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


app = create_app()

with app.test_request_context("/"):
    db = get_db()

    print()
    print("Every message this site sends on its own is here")
    print("-" * 70)
    check("four of them, in a fixed order",
          sorted(site_emails.ORDER) == sorted(site_emails.MESSAGES),
          str(site_emails.ORDER))
    for key in site_emails.ORDER:
        spec = site_emails.MESSAGES[key]
        check("%s: says when it goes and ships real words" % key,
              bool(spec["name"] and spec["when"] and spec["body_default"]))
        #  A placeholder offered on a message that cannot fill it is a
        #  promise this app does not keep -- it would arrive as braces.
        check("%s: every placeholder it offers can be filled" % key,
              all(p["name"] in site_emails.SAMPLE for p in spec["placeholders"]),
              str([p["name"] for p in spec["placeholders"]
                   if p["name"] not in site_emails.SAMPLE]))
        check("%s: every placeholder says what it means" % key,
              all(p["name"] and p["means"] for p in spec["placeholders"]))

    print()
    print("The whole message is the owner's")
    print("-" * 70)
    site_emails.save(db, "order", "Hello from {{site}}. You paid {{total}}.")
    db.commit()
    got = site_emails.wrap(db, "order", None,
                           {"site": "Flour & Salt", "total": "24.00 CHF"})
    check("their words are what is sent", got == "Hello from Flour & Salt. You paid 24.00 CHF.", got)

    #  The whole point of opening this up: an owner can now correct a
    #  sentence that used to be ours and used to be wrong.
    site_emails.save(db, "order", "")
    db.commit()
    check("an owner who empties it sends nothing",
          site_emails.wrap(db, "order", None, site_emails.SAMPLE) == "",
          repr(site_emails.wrap(db, "order", None, site_emails.SAMPLE)))

    print()
    print("The default wording is a real message, not a skeleton")
    print("-" * 70)
    site_emails.reset(db, "order")
    db.commit()
    shipped = site_emails.wrap(db, "order", None, site_emails.SAMPLE)
    check("it says what was bought", "Coaching pack" in shipped, shipped)
    check("...what it cost", "42.00 CHF" in shipped, shipped)
    check("...how it was paid for", "Card (Stripe)" in shipped, shipped)
    check("...and the way back in", site_emails.SAMPLE["link"] in shipped, shipped)
    #  The fault that opened this up: the old fixed body told a returning
    #  buyer their LIFETIME entitlements in an email about one order.
    check("it does not talk about other orders",
          "sessions to book" not in shipped and "downloads left" not in shipped,
          shipped)
    check("no placeholder survives into a real message", "{{" not in shipped, shipped)

    for key in ("sale", "confirm", "subscribed"):
        site_emails.reset(db, key)
    db.commit()
    sale = site_emails.wrap(db, "sale", None, site_emails.SAMPLE)
    #  It leads with a HEADING now -- the shipped wording has structure,
    #  because an owner should be able to leave the default alone and
    #  have it look like something a business sent.
    check("the sale notice leads with what happened",
          sale.startswith("## A customer made an order"), sale[:60])
    check("...and the shipped wording has a heading and its facts labelled",
          all(b.split(chr(10))[0].startswith("## ")
              for b in (site_emails.MESSAGES[k]["body_default"]
                        for k in site_emails.ORDER)))
    check("...and names the buyer", site_emails.SAMPLE["buyer"] in sale, sale)
    conf = site_emails.wrap(db, "confirm", None, site_emails.SAMPLE)
    check("the confirmation asks them to opt in",
          "opt in" in conf and site_emails.SAMPLE["link"] in conf, conf[:80])
    check("...and says what to do if it was not them",
          "delete and ignore" in conf, conf[:120])

    print()
    print("A placeholder this app cannot fill is visible, not blank")
    print("-" * 70)
    #  A blank is a mistake nobody notices until a customer asks; the
    #  literal braces are one somebody can see and fix.
    odd = site_emails.fill("Hello {{site}}, about {{discount}}", {"site": "Flour"})
    check("the known one is filled", "Hello Flour" in odd, odd)
    check("the unknown one stays visible", "{{discount}}" in odd, odd)

    #  An EMPTY value is a different case and takes its line with it: an
    #  order with nothing to post must not send a message ending in
    #  "Buyer: " with nothing after it.
    gap = site_emails.fill("Before" + NL + "{{action}}" + NL + "After", {"action": ""})
    check("an empty value takes its own line away", gap == "Before" + NL + "After", repr(gap))
    stranded = site_emails.fill("Buyer: {{buyer}}", {"buyer": ""})
    check("...but a label with it keeps its line", stranded == "Buyer:", repr(stranded))

    print()
    print("What the law adds cannot be written out")
    print("-" * 70)
    #  The one carve-out. Everything else is the owner's; this is not,
    #  and no wording may remove it.
    site_emails.save(db, "subscribed", "Thanks, that is all.")
    db.commit()
    out = site_emails.wrap(db, "subscribed", None, {"link": "https://your.site/u/abc"})
    check("the unsubscribe link is added below any wording",
          "https://your.site/u/abc" in out, out)
    #  ...and only once, for an owner who put it in their own sentence.
    site_emails.save(db, "subscribed", "Leave any time: {{link}}")
    db.commit()
    once = site_emails.wrap(db, "subscribed", None, {"link": "https://your.site/u/abc"})
    check("...and not twice when they wrote it themselves",
          once.count("https://your.site/u/abc") == 1, once)
    #  A confirmation is not a list message: there is nothing to leave.
    site_emails.save(db, "confirm", "Confirm here: {{link}}")
    db.commit()
    conf2 = site_emails.wrap(db, "confirm", None, {"link": "https://your.site/c/abc"})
    check("a confirmation carries no unsubscribe",
          "Unsubscribe" not in conf2, conf2)

    print()
    print("An owner's earlier words are adopted, never dropped")
    print("-" * 70)
    #  Installs configured before the body existed have an intro and an
    #  outro. An upgrade that silently deletes what somebody wrote is the
    #  worst kind of upgrade.
    site_emails.reset(db, "sale")
    for part, value in (("intro", "Morning!"), ("outro", "-- the shop")):
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   ("email_sale_" + part, value))
    db.commit()
    adopted = site_emails.body(db, "sale")
    check("the old greeting is still there", adopted.startswith("Morning!"), adopted[:40])
    check("...the sign-off too", adopted.rstrip().endswith("-- the shop"), adopted[-40:])
    check("...wrapped around the shipped default",
          "A customer made an order" in adopted, adopted[:120])
    #  Saving once replaces the pair, and a reset must clear both or it
    #  falls through to an intro somebody believed they had cleared.
    site_emails.reset(db, "sale")
    db.commit()
    check("resetting clears the legacy pair too",
          site_emails.body(db, "sale") == site_emails.MESSAGES["sale"]["body_default"],
          site_emails.body(db, "sale")[:60])

    print()
    print("The preview shows what would really be sent")
    print("-" * 70)
    site_emails.save(db, "subscribed", "Lovely to have you, {{site}}.")
    db.commit()
    shown = site_emails.preview(db, "subscribed")
    live = site_emails.wrap(db, "subscribed", None, site_emails.SAMPLE)
    check("the preview is the same words, filled the same way", shown == live, shown)
    check("...against believable data, not the placeholders repeated back",
          "{{" not in shown, shown)

    print()
    print("It refuses what it cannot send, and can be put back")
    print("-" * 70)
    ok_, error = site_emails.save(db, "not-a-message", "a")
    check("a message this site does not send is refused", not ok_ and error, str(error))
    site_emails.reset(db, "order")
    db.commit()
    check("resetting restores the standard wording",
          site_emails.body(db, "order") == site_emails.MESSAGES["order"]["body_default"])
    #  Deleting is a choice, and different from never having touched it.
    site_emails.save(db, "order", "")
    db.commit()
    check("an owner who deletes it gets nothing, not the default",
          site_emails.body(db, "order") == "", repr(site_emails.body(db, "order")))

    print()
    print("What the editor shows is what the inbox gets")
    print("-" * 70)
    #  The screen said one thing and the inbox another. The editor's
    #  preview runs the body through email_layouts.rich -- headings,
    #  bold, links -- and the SENT email did not, so a message written
    #  with any of them arrived with the markers still in it. Found by
    #  looking at a real preview, which is why that exists.
    from app.services import newsletter as _nl                 # noqa: E402
    site_emails.save(db, "order", "## A heading" + NL + "and **bold** words.")
    db.commit()
    body = site_emails.wrap(db, "order", None, site_emails.SAMPLE)
    sent = _nl.to_transactional_html(body, "Site", "Sender line", None)
    check("a heading arrives as a heading", "<h2" in sent, sent[:120])
    check("...and bold arrives as bold", "<strong>bold</strong>" in sent)
    check("...and no marker survives into the inbox",
          "##" not in sent and "**" not in sent, sent[:160])
    site_emails.reset(db, "order")
    db.commit()

    print()
    print("The live senders go through it")
    print("-" * 70)
    #  A statement about the code: every one of the four had its own
    #  hardcoded body and now wraps it, and a fifth added later that
    #  forgot to would be invisible from here otherwise.
    public = open("/app/app/routes/public.py", encoding="utf-8").read()
    for key in site_emails.ORDER:
        check("%s is wrapped where it is sent" % key,
              'site_emails.wrap(' in public and '"%s"' % key in public)
    check("the screen exists and is reachable",
          "site_emails" in open("/app/app/templates/partials/email_tabs.html",
                                encoding="utf-8").read())

    #  The screen shows the MESSAGE, not a description of it. It was two
    #  textareas and a collapsed preview, which asked somebody to hold
    #  three things at once: what they were typing, where it would land,
    #  and what it would look like there.
    screen = open("/app/app/templates/admin/site_emails.html",
                  encoding="utf-8").read()
    check("each message is shown in the card it arrives in",
          "cms-issue-canvas" in screen)
    check("...the owner's parts written into directly",
          'contenteditable="true"' in screen and "data-wording" in screen)
    check("...and the code's parts greyed and inert",
          "cms-wording-fixed" in screen)
    css = open("/app/app/static/css/admin.css", encoding="utf-8").read()
    check("greyed really means it cannot be clicked",
          ".cms-wording-fixed { opacity" in css and "pointer-events: none" in css)
    #  Grey carries it for somebody who notices grey. A person who does
    #  not should not have to hover to find out which half is theirs.
    check("...and it is said in words, not only in grey",
          "cms-wording-note" in screen
          and "cannot be changed" in screen)
    #  A sentence with a placeholder in the middle of it cannot be
    #  judged until the placeholder says 42.00 CHF. That was answered
    #  with a second pane beside the first; it is a VIEW of the same
    #  canvas now, so the width goes on the message rather than on a
    #  second copy of it that is wanted occasionally.
    check("the same words can be seen filled in",
          "data-preview" in screen and "data-preview-toggle" in screen)
    #  One editor with a dropdown, not four copies of one screen.
    check("one editor, chosen from a dropdown",
          "data-message-pick" in screen and "data-message-panel" in screen)
    check("...carrying the app's one rich-text toolbar",
          "wysiwyg_toolbar(" in screen)
    #  The preview showed invented values for things this install knows.
    route = open("/app/app/routes/admin/newsletters.py", encoding="utf-8").read()
    check("the preview reads this install rather than inventing it",
          "def _wording_values(" in route and "site_title" in route)
    check("...and says which values are real",
          "sample_note" in route and "sample_note" in screen)
    check("the sender line is shown so nobody writes it twice",
          "cms-issue-canvas-foot" in screen)

    print()
    print("What is written into looks like what is sent")
    print("-" * 70)
    #  The canvas held the STORED text in a div: `## Thank you for your
    #  order` with its markers still in it, every blank line collapsed by
    #  HTML, and the whole message on screen as one run-on paragraph
    #  bearing no relation to what arrives. It holds the message rendered
    #  now -- the same rule the newsletter canvas follows.
    from app.services import email_layouts as el                      # noqa: E402
    #  Whatever look the site has; what is being asked here is about the
    #  SHAPE of what the canvas holds, not its colours.
    written = el.rich(site_emails.body(db, "order"), {})
    joined = "".join(written)
    check("the canvas is rendered, not raw", "<h2" in joined, joined[:120])
    check("...so no marker is left on screen",
          "## " not in joined and "**" not in joined, joined[:160])
    check("...and the paragraphs are separate blocks",
          joined.count("<p") >= 3, str(joined.count("<p")))
    #  The placeholders stay VISIBLE here: this is the writing view, and
    #  Preview is what fills them. A canvas that filled them in would be
    #  a canvas somebody edits the sample data in.
    check("the placeholders are still there to be seen",
          "{{total}}" in joined and "{{items}}" in joined)

    screen = open("/app/app/templates/admin/site_emails.html", encoding="utf-8").read()
    #  Asked of the CANVAS, not the file. The hidden store still holds
    #  the stored text and must: that is what a save writes back, and
    #  what the server renders the real message from.
    canvas = screen[screen.index('data-wording="body"'):]
    canvas = canvas[:canvas.index("</div>")]
    check("the canvas renders that, not the stored text",
          "written[key]" in canvas and "wording[key]" not in canvas, canvas[-90:])
    check("...and the stored text is still what gets saved",
          'name="body"' in screen and "{{ wording[key] }}" in screen)
    check("...and loads the serialiser that reads it back",
          "rich-serialiser.js" in screen)

    #  The buttons are glyphs, and the same glyphs the rest of the admin
    #  uses: an eye SHOWS, a pencil WRITES. The JS used to overwrite the
    #  icon with the word "Preview", so a toolbar of icons had one text
    #  button in the middle of it -- from JavaScript, invisibly.
    wording_js = open("/app/app/static/js/admin/wording-editor.js",
                      encoding="utf-8").read()
    #  Asked of what is ASSIGNED to the button, not of the file -- the
    #  comment above it names the word it used to write, which is the
    #  sort of thing a substring check reads as the bug itself.
    said = [l for l in wording_js.split(chr(10))
            if "previewBtn.innerHTML" in l or "previewBtn.textContent" in l]
    check("the preview control stays an icon",
          len(said) == 1 and "innerHTML" in said[0]
          and "&#128065;" in said[0] and "&#9998;" in said[0],
          " / ".join(x.strip() for x in said))
    check("...and still says what it does in words",
          wording_js.count("previewBtn.title") >= 1)

    #  Pressing Preview must not move the buttons. The note saying where
    #  the figures came from was a sentence of running text IN the
    #  ribbon, revealed on toggle -- so using the control reflowed the
    #  toolbar and everything after it moved. A control that changes
    #  place when you use it is one you have to find again.
    #
    #  Asked structurally: the note is inside the message panel, with
    #  the values it is about, and not inside the toolbar at all.
    ribbon = screen[screen.index("data-wording-toolbar"):]
    ribbon = ribbon[:ribbon.index('<div class="cms-wording-chips">')]
    check("the note is not in the row of controls",
          "data-preview-source" not in ribbon)
    panel = screen[screen.index('data-message-panel="{{ key }}"'):]
    check("...it stands with the message it is about",
          "data-preview-source" in panel)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()

print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
