"""The two public forms that send email are bounded.

`services/captcha.py` has always ended by saying, correctly, that a sum
"will not stop a determined attacker who reads the page and does the sum.
It is not meant to: the rate limit on the route is what bounds the
damage." **That rate limit did not exist.** The only limiter in the app
guarded the password on a purchases page. A module that documents a
defence it does not have is worse than one documenting none, because it
is the reason nobody goes looking -- the same shape as the check that
could never fail.

The two forms are not equally dangerous, and the checks below say so:

  * the contact form mails the OWNER; a flood is a nuisance.
  * the sign-up form mails **whatever address was typed into it**, so a
    flood is a confirmation message sent to a stranger who did not ask,
    at an address the attacker chose. Double opt-in bounds the harm at
    one message each; the limit bounds how many strangers get one.

Run inside the container:

    docker compose exec -T web python tools/abuse_check.py
"""
import base64
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="abuse-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app import mailer                                        # noqa: E402
from app.services import captcha, ratelimit                   # noqa: E402

SENT = []
mailer.is_configured = lambda settings: True
mailer.send_html = lambda settings, to, subject, html, text, from_name=None, headers=None: \
    SENT.append(to)

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

with app.app_context():
    db = get_db()

    print()
    print("A limit exists, and it is tighter where the risk is somebody else's")
    print("-" * 70)
    check("both forms that send email are limited",
          set(ratelimit.LIMITS) == {"contact", "signup"}, str(set(ratelimit.LIMITS)))
    contact_n, _ = ratelimit.LIMITS["contact"]
    signup_n, _ = ratelimit.LIMITS["signup"]
    #  The sign-up form mails a stranger. It gets less rope.
    check("sign-up is tighter than contact", signup_n < contact_n,
          "%d vs %d" % (signup_n, contact_n))

    ip = "203.0.113.7"
    check("nothing is limited to begin with", not ratelimit.too_many(db, "signup", ip))
    for _ in range(signup_n):
        ratelimit.record(db, "signup", ip)
    db.commit()
    check("it stops after its allowance", ratelimit.too_many(db, "signup", ip))
    check("...and only for that address",
          not ratelimit.too_many(db, "signup", "198.51.100.4"))
    check("...and only for that form",
          not ratelimit.too_many(db, "contact", ip))

    #  A proxy that strips the header must not lock out every visitor at
    #  once: a contact form nobody can use is worse than one that can be
    #  spammed.
    check("with no address to count, it fails OPEN",
          not ratelimit.too_many(db, "signup", ""))
    ratelimit.record(db, "signup", "")
    check("...and records nothing", db.execute(
        "SELECT COUNT(*) c FROM login_attempts WHERE ip = ''").fetchone()["c"] == 0)

    print()
    print("...and it says so without accusing anybody")
    print("-" * 70)
    for kind in ratelimit.LIMITS:
        words = ratelimit.wait_message(kind)
        check("%s: there are words for it" % kind, bool(words and words.strip()))
        check("%s: they do not say 'rate limit'" % kind,
              "rate limit" not in words.lower() and "blocked" not in words.lower(),
              words)

    print()
    print("The sign-up form sets the same trap the contact form does")
    print("-" * 70)
    from app.services import blocks
    markup = blocks.build_newsletter({"heading": "H", "text": "T"})
    check("it has a honeypot", 'name="website"' in markup, markup[:120])
    check("...and it is the SAME field the contact form uses",
          captcha.HONEYPOT_FIELD == "website",
          "a bot that learned one trap would not know the other")
    check("...hidden by a rule that covers both",
          "cms-newsletter-hp" in markup)
    css = open("/app/app/static/css/site-base.css", encoding="utf-8").read()
    check("...and that rule really does hide it",
          ".cms-contact-hp, .cms-newsletter-hp {" in css,
          "two rules that can drift is how one form leaks a visible field")
    check("it is not type=hidden, which a bot can tell apart",
          'name="website" tabindex' in markup.replace('type="text" id="cms-sub-website" ', ''),
          markup[markup.find("cms-newsletter-hp"):][:200])

    print()
    print("Both routes actually use it")
    print("-" * 70)
    #  A statement about the code: a limiter nothing calls is the exact
    #  fault this file exists because of.
    public = open("/app/app/routes/public.py", encoding="utf-8").read()
    check("the contact form asks before doing the work",
          'ratelimit.too_many(db, "contact"' in public)
    check("the sign-up form asks too",
          'ratelimit.too_many(db, "signup"' in public)
    check("both count on the way IN, not on success",
          public.count("ratelimit.record(db,") == 2,
          "counting only successes means the way past is to fail")
    check("the sign-up form checks the honeypot",
          "captcha.HONEYPOT_FIELD" in public
          and public.count("captcha.HONEYPOT_FIELD") >= 2)

    print()
    print("The human check is varied, and only the right answer passes")
    print("-" * 70)
    #  A FIXED question is a question you write a parser for once. The
    #  weakness of the old sum was that it was always a sum -- so what is
    #  asserted here is that the KIND rotates, and that whichever kind
    #  comes up, the right answer passes and a wrong one does not.
    kinds = set()
    for _ in range(60):
        kinds.add(" ".join(captcha.challenge()[0].split()[:2]))
    check("the question is not always the same shape", len(kinds) >= 2,
          "a single fixed question is a single parser away from beaten")

    def _token(answer, age=5):
        #  Backdated past MIN_SECONDS so timing is not what passes/fails it.
        issued = int(time.time()) - age
        sig = captcha._sign(issued, answer)
        return base64.urlsafe_b64encode(("%d.%s" % (issued, sig)).encode()).decode()

    for gen in captcha._QUESTIONS:
        q, ans = gen()
        tok = _token(ans)
        ok, _r = captcha.verify(tok, ans)
        bad, _r = captcha.verify(tok, ans + "x")
        kind = gen.__name__[3:]  # drop the "_q_" prefix
        check("%s: the right answer passes" % kind, ok, q)
        check("%s: a wrong answer does not" % kind, not bad)

    #  A word answer that happens to be a number word ("one") must still
    #  match -- the raw word is signed, not its digit.
    check("a number-word answer ('one') still matches",
          captcha.verify(_token("one"), "one")[0])
    #  ...and a sum signing the digit still accepts the word.
    check("a sum accepts the word or the digit",
          captcha.verify(_token("7"), "seven")[0] and captcha.verify(_token("7"), "7")[0])
    check("answered instantly, it is refused",
          not captcha.verify(_token("7", age=0), "7")[0])
    check("honeypot filled, it is refused",
          not captcha.verify(_token("7"), "7", honeypot="x")[0])

    print()
    print("A WhatsApp link is built, or refused — never silently wrong")
    print("-" * 70)
    #  wa.me takes the international number and NOTHING else. A number
    #  with a plus, a space or a leading trunk zero in it produces a link
    #  that opens WhatsApp to nobody at all, with no error and nothing to
    #  see -- which is why this is done for the owner rather than left as
    #  "paste a link into a Button", something they can already do.
    from app.services.legal import whatsapp_link
    for given, want, why in (
        ("+41 79 123 45 67", "https://wa.me/41791234567", "spaces and a plus"),
        ("+1 (555) 010-9999", "https://wa.me/15550109999", "brackets and dashes"),
        ("0041 79 123 45 67", "https://wa.me/41791234567", "00 instead of +"),
        #  Refused rather than guessed. A local number needs a country
        #  code, and guessing one produces a link that reaches somebody
        #  -- just not the right somebody, which is the worst outcome
        #  available here.
        ("079 123 45 67", "", "local, so there is no country code to use"),
        ("+41 79", "", "too short to be a real number"),
        ("not a number", "", "not a number at all"),
        ("", "", "nothing to work from"),
    ):
        check("%s: %s" % (why, whatsapp_link(given) or "refused"),
              whatsapp_link(given) == want, repr(whatsapp_link(given)))

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
