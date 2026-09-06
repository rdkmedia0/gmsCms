"""A newsletter written by the AI is a draft, and only ever a draft.

This is the one place in this app where a plausible-sounding mistake goes
out to real people, over somebody else's name, and cannot be taken back.
So the thing being checked is mostly what it CANNOT do:

  * it never sends anything -- it creates a newsletter and opens it;
  * it composes only from blocks the editor already has, so a model that
    invents one produces a shorter newsletter and never a broken one;
  * it refuses in the owner's terms when there is no provider, no brief,
    or nothing usable came back.

The provider is stubbed, so this runs anywhere and costs nothing. What is
being checked is this app's handling of an answer, not the answer.

    docker compose exec -T web python tools/newsletter_ai_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="newsletter-ai-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import assistant, mailer                             # noqa: E402
from app.services import email_layouts, newsletter, newsletter_ai   # noqa: E402

SENT = []
mailer.send_html = lambda *a, **k: SENT.append(a)

passed = 0
failures = []


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


REPLY = ('{"subject": "Autumn hours", "opening": "Hello,",'
         ' "blocks": [{"type": "heading", "text": "We open later"},'
         ' {"type": "text", "text": "From October we open at **ten**."},'
         ' {"type": "button", "label": "See the hours", "url": ""}],'
         ' "sign_off": "Thanks for reading."}')


def stub(reply, configured=True):
    assistant.is_configured = lambda db: configured
    assistant._call_provider = lambda db, msgs, tools: {"content": reply}


app = create_app()

with app.test_request_context("/"):
    db = get_db()

    print()
    print("It writes a draft from a sentence")
    print("-" * 70)
    stub(REPLY)
    subject, blocks = newsletter_ai.draft(db, "we open later in autumn", "Flour & Salt")
    check("the subject comes back", subject == "Autumn hours", subject)
    kinds = [b["type"] for b in blocks]
    #  The middle, between the opening and the sign-off it is wrapped in.
    check("...and the middle of the letter",
          kinds[1:-1] == ["heading", "text", "button"], str(kinds))
    check("it opens with the owner's own words, as a roled block",
          blocks[0]["role"] == "intro" and blocks[0]["text"] == "Hello,",
          str(blocks[0]))
    check("...and closes with one", blocks[-1]["role"] == "exit", str(blocks[-1]))
    #  Which means a generated newsletter is an ordinary one afterwards,
    #  and nothing downstream has to ask where it came from.
    check("...so it is an ordinary newsletter afterwards",
          email_layouts.has_own_wrapper(blocks))
    check("a button arrives with nowhere to go, for the owner to fill",
          blocks[-2]["url"] == "", str(blocks[-2]))

    print()
    print("It composes only from blocks the editor has")
    print("-" * 70)
    #  A model that invents a block type, or returns raw HTML, must
    #  produce a SHORTER newsletter -- never a broken one. Same rule this
    #  project applies to demo content: if an owner could not have made
    #  it from the Tool menu, neither can generated content.
    stub('{"subject": "x", "opening": "Hi", "blocks": ['
         '{"type": "columns", "text": "two up"},'
         '{"type": "html", "text": "<script>alert(1)</script>"},'
         '{"type": "text", "text": "This one is fine."}], "sign_off": "Bye"}')
    _s, blocks = newsletter_ai.draft(db, "anything", "Site")
    kinds = [b["type"] for b in blocks]
    check("an invented block type is dropped",
          "columns" not in kinds and "html" not in kinds, str(kinds))
    check("...and what was usable survives",
          any(b.get("text") == "This one is fine." for b in blocks), str(kinds))

    print()
    print("It refuses in the owner's terms")
    print("-" * 70)
    for label, reply, brief, configured, expect in (
            ("no brief", REPLY, "  ", True, "what the newsletter is about"),
            ("no provider", REPLY, "something", False, "No AI provider"),
            ("nothing came back", "", "something", True, "didn't have an answer"),
            ("not JSON at all", "Sure! Here you go.", "something", True,
             "didn't have an answer"),
            ("no usable blocks", '{"subject": "x", "blocks": []}', "something",
             True, "anything usable"),
    ):
        stub(reply, configured)
        try:
            newsletter_ai.draft(db, brief, "Site")
            check("%s: it refuses" % label, False, "it did not refuse")
        except newsletter_ai.Refused as why:
            check("%s: it says why, in words" % label,
                  expect.lower() in str(why).lower(), str(why))

    #  A reply wrapped in ``` is punctuation, not a refusal: small models
    #  do it constantly even when told not to.
    stub("```json" + chr(10) + REPLY + chr(10) + "```")
    subject, blocks = newsletter_ai.draft(db, "anything", "Site")
    check("a fenced reply is read anyway", subject == "Autumn hours", subject)
    stub("Here is your newsletter: " + REPLY)
    subject, _b = newsletter_ai.draft(db, "anything", "Site")
    check("...and so is one with a sentence in front of it",
          subject == "Autumn hours", subject)

    print()
    print("It cannot send anything")
    print("-" * 70)
    check("nothing was mailed by any of that", not SENT, str(len(SENT)))
    #  A statement about the code: the route creates and redirects. If a
    #  send ever appears in it, this is where that shows up.
    route = open("/app/app/routes/admin/newsletters.py", encoding="utf-8").read()
    start = route.index("def newsletter_issue_write(")
    body = route[start:route.index("@bp.route", start + 10)]
    check("...and the route that offers it only creates and opens one",
          "deliver(" not in body and "send_html" not in body
          and "_send_it(" not in body)
    check("...ending at the editor, for a person to read",
          "newsletter_issue_edit" in body)

    print()
    print("The prompt is content, not code")
    print("-" * 70)
    #  The rule: a prompt sent to a provider is content and lives in a
    #  template, not in a Python string.
    check("it lives in a template",
          os.path.exists("/app/app/templates/prompts/newsletter_brief.j2"))
    prompt = open("/app/app/templates/prompts/newsletter_brief.j2",
                  encoding="utf-8").read()
    check("...and tells the model what it may not invent",
          "unsubscribe" in prompt.lower() and "placeholder" in prompt.lower())

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
if failures:
    print("failed:", ", ".join(failures))
sys.exit(1 if failures else 0)
