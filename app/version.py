"""What version of gmsCms this is, said in ONE place.

There was no version anywhere: an owner looking at their admin could not
tell whether the image they had pulled was the one with a fix in it, and
"is prod behind?" was answered by counting commits. Two facts, two
sources, because they are known at different times:

  * the NUMBER is the `VERSION` file at the repository root, bumped by
    hand when something is worth calling a release;
  * the BUILD is the commit the image was made from, passed in by the
    publish workflow as `APP_BUILD` (see .github/workflows/publish.yml
    and the Dockerfile). A local `docker compose up --build` has none,
    and says so by leaving it out rather than inventing one.

Read once and cached: neither changes while the process runs.
"""
import os

NAME = "gmsCms"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(_ROOT, "VERSION")

_cache = {}


def number():
    if "number" not in _cache:
        try:
            with open(VERSION_FILE, encoding="utf-8") as f:
                v = f.read().strip()
        except OSError:
            v = ""
        _cache["number"] = v or "0.0.0"
    return _cache["number"]


def build():
    """The short commit the image was built from, or '' for a local build."""
    b = (os.environ.get("APP_BUILD") or "").strip()
    return b[:7] if b and b != "dev" else ""


def label():
    b = build()
    return f"v{number()}" + (f" ({b})" if b else "")


def info():
    """What a template needs: {name, number, build, label}."""
    return {"name": NAME, "number": number(), "build": build(), "label": label()}
