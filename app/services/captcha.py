"""
A human check for the contact form.

Deliberately not reCAPTCHA, hCaptcha or Turnstile. This app self-hosts
every font specifically so that a visitor's IP address does not reach a
third party on every page load; putting Google's CAPTCHA on the contact
page would be a far larger version of exactly that — every visitor
profiled, on a page whose whole purpose is that a stranger can talk to
the site owner. It would also be one more service that can be down.

So the check is local, stateless, and readable. Three layers, because no
single one is much good on its own:

  a hidden field a person never sees and a naive bot fills in;
  a minimum time between the form being issued and sent back;
  and a question in words, which needs no images, no JavaScript, and
  works with a screen reader.

Stateless via a signature rather than a stored answer: the token carries
when it was issued plus an HMAC over the issue time and the answer, so
verifying means recomputing the same HMAC with whatever was typed. No
table, nothing to clean up, and nothing to guess — a forged token needs
the site's secret key.

This will not stop a determined attacker who reads the page and does the
sum. It is not meant to: the rate limit on the route is what bounds the
damage. This stops the automated traffic that fills in every form on the
internet, which is the actual problem a small site has.
"""
import base64
import hmac
import hashlib
import random
import time

from flask import current_app

#  Spelled out, so the question cannot be answered by pattern-matching
#  digits out of the page, and so it reads naturally aloud.
WORDS = ("zero", "one", "two", "three", "four", "five", "six",
         "seven", "eight", "nine", "ten", "eleven", "twelve")

HONEYPOT_FIELD = "website"
MIN_SECONDS = 3
MAX_SECONDS = 3600


def _sign(issued_at, answer):
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode()
    payload = f"{issued_at}:{str(answer).strip().lower()}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:32]


def challenge():
    """(question, token) — a fresh sum, and proof of what it should be."""
    left = random.randint(1, 9)
    right = random.randint(1, 9)
    answer = left + right
    issued_at = int(time.time())
    question = f"What is {WORDS[left]} plus {WORDS[right]}?"
    token = base64.urlsafe_b64encode(
        f"{issued_at}.{_sign(issued_at, answer)}".encode()
    ).decode()
    return question, token


def _accepts(answer):
    """Digits or the word — someone typing "seven" is not a robot."""
    answer = (answer or "").strip().lower()
    if answer.isdigit():
        return [answer]
    if answer in WORDS:
        return [str(WORDS.index(answer))]
    return [answer]


def verify(token, answer, honeypot=""):
    """(ok, reason). `reason` is for the log, never for the visitor.

    A wrong sum tells the sender to try again. Everything else — a filled
    honeypot, a form returned in under three seconds, a forged or
    replayed token — is a bot, and the caller is expected to accept it
    silently rather than explain what gave it away.
    """
    if (honeypot or "").strip():
        return False, "honeypot filled"
    try:
        decoded = base64.urlsafe_b64decode((token or "").encode()).decode()
        issued_at_raw, signature = decoded.split(".", 1)
        issued_at = int(issued_at_raw)
    except (ValueError, TypeError, UnicodeDecodeError):
        return False, "malformed token"

    age = time.time() - issued_at
    if age < MIN_SECONDS:
        return False, "submitted too fast to have been read"
    if age > MAX_SECONDS:
        return False, "form expired"

    for candidate in _accepts(answer):
        if hmac.compare_digest(signature, _sign(issued_at, candidate)):
            return True, ""
    return False, "wrong answer"
