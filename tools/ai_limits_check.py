"""What the AI can and cannot do, said before somebody meets it.

Two limits, both of them Ollama being what it is rather than this app
failing -- and an owner who is not told cannot tell those apart. "The
Generate button does nothing" reads as a bug every time.

  * **Ollama has no image API at all**, whatever model is loaded. So the
    Generate buttons are not offered while it is the provider, and the
    reason is said in words rather than left as an absence.
  * **A small self-hosted model asked something it cannot map to a tool
    very often returns NOTHING** -- no words, no tool call. That used to
    be relayed as an empty reply, so the panel showed nothing at all:
    you asked, and the screen did not change, which reads as the
    assistant ignoring you. It is answered in words now.

Run inside the container:

    docker compose exec -T web python tools/ai_limits_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="ai-limits-check-")
os.environ["DATA_DIR"] = DATA_DIR

#  Isolated from the host's own AI configuration, for the same reason
#  DATA_DIR is isolated from its database. get_ai_settings falls back to
#  OPEN_WEBUI_* / OLLAMA_* / GEMINI_* environment variables -- a
#  deliberate path for an install configured that way before these
#  screens existed -- so on a machine that HAS them set, "delete every
#  setting" does not mean "no provider", and this file would be checking
#  the deployment rather than the code.
for _leftover in [k for k in os.environ
                  if k.startswith(("OPEN_WEBUI_", "OLLAMA_", "GEMINI_"))]:
    del os.environ[_leftover]

from app import create_app, ai_image, assistant                # noqa: E402
from app.db import get_db                                      # noqa: E402

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


def provider(db, name, **extra):
    """Set the provider and its fields the way the app really stores them.

    A key goes in ENCRYPTED, under its own `_enc` name -- writing the
    plaintext one writes somewhere nothing ever reads, which is how the
    first version of this file "proved" Gemini could not make pictures.
    """
    from app import crypto
    values = {"ai_provider": name}
    for key, value in extra.items():
        if key.endswith("_api_key"):
            values[key + "_enc"] = crypto.encrypt(value) if value else ""
        else:
            values[key] = value
    for key, value in values.items():
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()


#  A REQUEST context, not just an app one: run_turn renders the
#  assistant's system prompt from a template, and an admin context
#  processor reads the session while doing it.
with app.test_request_context("/"):
    db = get_db()

    print()
    print("Pictures: offered when they work, explained when they do not")
    print("-" * 70)
    provider(db, "ollama", ollama_url="http://localhost:11434")
    check("Ollama cannot make pictures", not ai_image.is_configured(db))
    reason = ai_image.unavailable_reason(db)
    check("...and is not merely 'not configured'",
          "Ollama" in reason and "cannot make pictures" in reason, reason[:80])
    check("...and says what to do instead", "Open WebUI" in reason, reason[:80])
    check("...naming the thing that would then do the work",
          "ComfyUI" in reason or "backend" in reason, reason)

    provider(db, "openwebui", openwebui_url="https://ai.example.test",
             openwebui_api_key="k")
    check("Open WebUI can", ai_image.is_configured(db))
    provider(db, "openwebui", openwebui_api_key="")
    check("...but not without its key", not ai_image.is_configured(db))
    check("...and says which half is missing",
          "key" in ai_image.unavailable_reason(db), ai_image.unavailable_reason(db))

    provider(db, "gemini", gemini_api_key="k")
    check("Gemini can", ai_image.is_configured(db))

    for key in ("ai_provider", "gemini_api_key_enc", "openwebui_url",
                "openwebui_api_key_enc", "ollama_url"):
        db.execute("DELETE FROM settings WHERE key = ?", (key,))
    db.commit()
    check("with no AI at all, it says so",
          "No AI is set up" in ai_image.unavailable_reason(db),
          ai_image.unavailable_reason(db))

    print()
    print("Silence is not relayed as an answer")
    print("-" * 70)
    provider(db, "ollama", ollama_url="http://localhost:11434")

    #  A model that returns no words and no tool call. This is the exact
    #  shape a small local model produces when it cannot map a request to
    #  a tool, and it used to reach the panel as "".
    assistant._call_provider = lambda db_, messages, tools: {
        "content": None, "tool_calls": []}
    answer = assistant.run_turn(db, [{"role": "user", "content": "make it nicer"}])
    said = (answer or {}).get("reply") or ""
    check("an empty completion is answered in words", bool(said.strip()), repr(said))
    check("...and names the likely cause rather than apologising",
          "self-hosted" in said or "unsure" in said, said)
    check("...and says what would actually help",
          "larger model" in said or "plainer" in said, said)

    #  On a hosted provider the same silence gets different words,
    #  because "try a larger model" is useless advice there.
    provider(db, "gemini", gemini_api_key="k")
    hosted = assistant._nothing_came_back(db)
    check("a hosted provider is told something else",
          "self-hosted" not in hosted, hosted)
    check("...and is still a real sentence", bool(hosted.strip()))

    print()
    print("Both limits are on the screen where the provider is chosen")
    print("-" * 70)
    card = open("/app/app/templates/partials/ai_settings_card.html",
                encoding="utf-8").read()
    check("the picture limit is stated", "Ollama cannot make pictures" in card)
    check("...with the way round it", "Open WebUI" in card)
    check("the instruction-following limit is stated",
          "follows instructions less reliably" in card)
    check("...and says the app no longer shows an empty answer",
          "empty answer" in card)

    print()
    print("A product can have a picture made for it")
    print("-" * 70)
    routes = open("/app/app/routes/admin/settings.py", encoding="utf-8").read()
    screen = open("/app/app/templates/admin/commerce_fulfilment.html",
                  encoding="utf-8").read()
    check("a new product can be given a description to generate from",
          "_generated_product_image_url" in routes and 'name="image_prompt"' in screen)
    #  The description box lives in one shared chooser (the image_controls
    #  macro), so it is written once and RENDERED on both forms rather than
    #  copied. "Edit can generate too" is therefore that the chooser is
    #  placed on both -- the add form and each product's editor -- not that
    #  the input's markup appears twice in the source.
    check("...and so can one being edited",
          screen.count("{{ image_controls(") == 2,
          str(screen.count("{{ image_controls(")))
    check("both forms go through one function",
          routes.count("= _picture_for_product()") == 2,
          str(routes.count("= _picture_for_product()")))
    #  Not a comment that says so, but the order the code actually reads its
    #  sources in: _picture_for_product looks at the attached file before it
    #  looks at the description box, and returns on the file, so a prompt
    #  left over from last time can never beat a file just attached.
    picker = routes[routes.index("def _picture_for_product"):
                    routes.index("def _library_image_url")]
    check("an uploaded file wins over a description",
          picker.index('request.files.get("image")') < picker.index("image_prompt"),
          "a prompt left in the box from last time is not a deliberate act")
    #  A Generate control that cannot generate is a control that lies.
    check("the control is offered only when it would work",
          "image_gen_ready" in screen and "image_gen_ready=" in routes)
    check("...and the reason is shown when it is not",
          "image_gen_reason" in screen)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
