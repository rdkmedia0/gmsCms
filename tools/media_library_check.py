"""Every tool that takes a picture can take one you already have.

A photograph that is already on this site had to be found on the machine
it came from and uploaded a second time, because nearly every chooser in
the editor offered an upload and nothing else. Measured before the fix:
ONE chooser out of nine offered the Media Library. The Library filled up
with duplicates of itself, and the one place that did offer it made the
other eight look broken rather than different.

So this asks two questions, and neither can be answered by reading:

  * does every media chooser offer the Library as well as an upload, and
    does each one say what it will accept?
  * is a library URL treated as a URL and not as a path? It arrives from
    a client, and a client can send anything -- so it is checked against
    what is actually IN the library, and the value used is the library's
    own rather than the string that was sent.

Run inside the container:

    docker compose exec -T web python tools/media_library_check.py
"""
import io
import re
import sys

sys.path.insert(0, "/app")

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


PAGE = io.open("/app/app/templates/public/page.html", encoding="utf-8").read()
EDITOR = io.open("/app/app/static/js/inline-editor.js", encoding="utf-8").read()
ROUTES = io.open("/app/app/routes/admin/sections.py", encoding="utf-8").read()
SERVICE = io.open("/app/app/services/sections.py", encoding="utf-8").read()

print()
print("Every chooser offers the Library, not only an upload")
print("-" * 70)

#  Every file input in the live editor that is choosing MEDIA. The
#  package/toolkit/archive uploads on admin screens are not media and are
#  not what this is about.
lines = PAGE.split(chr(10))
choosers = []
for i, line in enumerate(lines):
    if 'type="file"' not in line:
        continue
    cls = re.search(r'class="([a-z-]+)"', line)
    if not cls:
        continue
    name = cls.group(1)
    near = chr(10).join(lines[max(0, i - 6):i + 3])
    choosers.append((name, "data-library-pick" in near or "image-pick" in near))

check("there are media choosers to check", len(choosers) >= 8, str(len(choosers)))
without = [name for name, has in choosers if not has]
check("every one of them offers the Library",
      not without, ", ".join(without))

#  ...and says what it will take, because "Choose" on a video slot that
#  then offers photographs is worse than no button.
kinds = re.findall(r'data-library-kinds="([a-z,]+)"', PAGE)
check("each says what it accepts", len(kinds) == PAGE.count("data-library-pick"),
      "%d kinds for %d buttons" % (len(kinds), PAGE.count("data-library-pick")))
check("...including the ones that are not pictures",
      any("video" in k for k in kinds) and any("file" in k for k in kinds),
      ", ".join(sorted(set(kinds))))
bare = re.findall(r'data-library-pick(?![^>]*title=)[^>]*>', PAGE)
check("every one carries a sentence", not bare, str(len(bare)))

print()
print("A pick lands the way an upload does")
print("-" * 70)
#  The failure this prevents: a Choose button with its own copy of what
#  happens afterwards, which is how the two come to differ -- one
#  reloading, one not; one showing a toast, one silent.
check("there is one binding for every Choose button",
      EDITOR.count('bindEach("[data-library-pick]"') == 1)
check("...and it hands the pick to the upload's own sender",
      "input.cmsSend(body)" in EDITOR or "input.cmsSend(" in EDITOR)
senders = EDITOR.count(".cmsSend = async")
check("every chooser has such a sender", senders >= 5, str(senders))
#  Counting reloads across the whole file measured nothing -- the editor
#  reloads in a dozen unrelated places. What matters is that the Choose
#  binding does not apply anything ITSELF: it posts through the upload's
#  sender and stops. A second apply here is how a picked picture and an
#  uploaded one come to behave differently.
_start = EDITOR.index('bindEach("[data-library-pick]"')
_binding = EDITOR[_start:EDITOR.index("bindEach(", _start + 20)]
check("...and the binding applies nothing itself",
      "location.reload" not in _binding and "fetch(" not in _binding.split("libraryList")[-1],
      _binding[-160:])

print()
print("A library URL is a URL, not a path")
print("-" * 70)
#  It arrives from a client and a client can send anything. Both upload
#  helpers check it against what is actually in the library and use the
#  library's own value -- never the string that was sent.
check("the shared upload helper checks the library",
      "library_url" in ROUTES and "_list_media()" in ROUTES)
check("...and the card/banner helper does too",
      "library_url" in SERVICE and "_list_media(image_only=True)" in SERVICE)

from app import create_app                                            # noqa: E402
from app.services.sections import _save_card_image_file, _list_media  # noqa: E402

app = create_app()
with app.test_request_context():
    real = [i["url"] for i in _list_media(image_only=True)]

if not real:
    check("there is a picture to test with", False, "the library is empty")
else:
    with app.test_request_context(method="POST", data={"library_url": real[0]}):
        url, error = _save_card_image_file()
    check("a real pick is accepted", url == real[0] and not error, str(error))

    for bad in ("/static/uploads/../../etc/passwd",
                "/etc/passwd",
                "https://example.test/evil.png",
                "/static/uploads/does-not-exist.png"):
        with app.test_request_context(method="POST", data={"library_url": bad}):
            url, error = _save_card_image_file()
        check("refused: %s" % bad[:34], url is None and bool(error), str(url))

    #  An upload with no file and no pick still says which it wanted --
    #  the refusal it always had.
    with app.test_request_context(method="POST"):
        url, error = _save_card_image_file()
    check("nothing at all is still refused, with a reason",
          url is None and bool(error) and "choose" in error[0].lower(), str(error))

print()
print("  %d ok, %d failed" % (passed, len(failures)))
for name in failures:
    print("    - " + name)
sys.exit(1 if failures else 0)
