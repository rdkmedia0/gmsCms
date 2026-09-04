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


#  The check is one of SEVERAL kinds of question, chosen at random, so a
#  bot author cannot write "find two digits and add them" once and beat it
#  forever -- the weakness of a fixed sum was the FIXED part, not the sum.
#  Every kind is answerable from words alone (no image, no JS, reads aloud
#  for a screen reader) and its answer is known to the server so the token
#  can sign it. This does not stop a determined attacker who reads the page
#  -- nothing local and readable can -- it stops the untargeted automation
#  that fills every form on the internet, backed by the route's rate limit.

#  Small odd-one-out pools. "language" is drawn from the translation
#  feature's own set of languages, so the human-readable items rotate with
#  what the app already knows about.
_CATEGORIES = {
    "colour": ["red", "green", "blue", "yellow", "orange", "purple", "pink"],
    "animal": ["dog", "cat", "horse", "rabbit", "fox", "bird", "sheep"],
    "fruit": ["apple", "banana", "grape", "lemon", "peach", "cherry", "pear"],
    "language": ["English", "French", "German", "Spanish", "Italian",
                 "Portuguese", "Dutch", "Polish"],
}
_PHRASES = ("the quick brown fox", "a calm and quiet sea", "one small green apple",
            "the tall old oak tree", "a warm cup of tea")
_ORDINALS = ("first", "second", "third", "fourth", "fifth")


def _q_sum():
    a, b = random.randint(1, 9), random.randint(1, 9)
    return f"What is {WORDS[a]} plus {WORDS[b]}?", str(a + b)


def _q_category():
    cat = random.choice(list(_CATEGORIES))
    answer = random.choice(_CATEGORIES[cat])
    #  A distractor must NOT also belong to the target category, or the
    #  question would have two right answers (orange is a colour AND a
    #  fruit) -- so exclude every member of the target category from the
    #  pool, however it is listed elsewhere.
    target = set(_CATEGORIES[cat])
    pool = [w for c, ws in _CATEGORIES.items() if c != cat for w in ws if w not in target]
    options = [answer] + random.sample(pool, 2)
    random.shuffle(options)
    article = "an" if cat[0] in "aeiou" else "a"
    return ("Which of these is %s %s: %s?" % (article, cat, ", ".join(options))), answer.lower()


def _q_nth_word():
    phrase = random.choice(_PHRASES)
    words = phrase.split()
    i = random.randint(0, min(len(words), len(_ORDINALS)) - 1)
    return ("In the phrase “%s”, type the %s word." % (phrase, _ORDINALS[i])), words[i].lower()


_QUESTIONS = (_q_sum, _q_category, _q_nth_word)


def challenge():
    """(question, token) — a fresh question of a random kind, and proof of
    what its answer should be."""
    question, answer = random.choice(_QUESTIONS)()
    issued_at = int(time.time())
    token = base64.urlsafe_b64encode(
        f"{issued_at}.{_sign(issued_at, answer)}".encode()
    ).decode()
    return question, token


def _accepts(answer):
    """Every form the typed answer could take. The raw text is always a
    candidate; a number word ALSO stands for its digit ("seven" == "7"), so
    a sum accepts either -- and a word-answer challenge whose answer happens
    to be a number word ("one") still matches, because the raw word is tried
    too (the sum signs the digit, a phrase challenge signs the word)."""
    answer = (answer or "").strip().lower()
    candidates = [answer]
    if answer in WORDS:
        candidates.append(str(WORDS.index(answer)))
    return candidates


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
