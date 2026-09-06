"""Could an owner have built this by hand?

For every template this app ships, and every page and zone in it: what
section types does it use, what markup does it contain, and is there a
TOOL that produces each of them?

The rule this enforces is one of this project's oldest: demo and
generated content "must compose only from the Tool menu's actual
primitives -- if a real admin couldn't reproduce a piece of content by
picking tools from the panel, neither can generated content." The
HTML/Embed tool is reserved for real third-party embed code and is
never the answer for styling or layout.

The answer has to be yes with no AI involved except picture generation,
because a template is a starting point somebody then edits by hand. A
gap here is not a template that needs fixing -- it is a TOOL that is
missing, and the fix is to build the tool.

Run:  docker compose exec -T web python tools/by_hand_check.py
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, "/app")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app import create_app                                      # noqa: E402
from app.services import blocks                                 # noqa: E402
from app.services.sections import PAGE_TYPES                    # noqa: E402

app = create_app()

#  Every section type a tool can make. Anything else on a page is
#  something an owner could not have chosen.
TOOL_TYPES = {
    "text", "image", "banner", "card", "columns", "html", "file", "media",
    "header", "blank",
}

#  What tool made this? ASKED OF THE APP, not decided here.
#
#  `_section_display_label` is what the editor puts on a section's own
#  panel -- it reads the markup and names the tool. A hand-kept list of
#  tool classes here would be a second copy of that answer, and it would
#  be wrong the first time a tool changed. Anything it calls "Embed" is
#  markup with no tool behind it.
from app.routes.public import _section_display_label               # noqa: E402

#  ...and an Embed is legitimate for exactly one thing: real
#  third-party code that needs a script or an iframe to work.
EMBED_IS_FINE = re.compile(r"<(script|iframe)[ >/]", re.I)


def sections_of(pkg_dir):
    """Every section in a package: (where, type, content, extras)."""
    out = []
    pages = os.path.join(pkg_dir, "pages")
    if os.path.isdir(pages):
        for name in sorted(os.listdir(pages)):
            if not name.endswith(".json"):
                continue
            spec = json.load(io.open(os.path.join(pages, name), encoding="utf-8"))
            for s in spec.get("sections") or []:
                s = list(s) + [{}]
                out.append((name, s[0], s[2] or "", s[3]))
    zones = os.path.join(pkg_dir, "zones.json")
    if os.path.isfile(zones):
        for s in json.load(io.open(zones, encoding="utf-8")) or []:
            if isinstance(s, dict):
                out.append(("zones.json", s.get("type", "?"), s.get("content") or "", {}))
            else:
                s = list(s) + [{}]
                out.append(("zones.json", s[0], s[2] or "", s[3]))
    return out


def main():
    with app.app_context():
        roots = []
        for base in ("/app/app/static/themes", "/app/app/data/templates"):
            if not os.path.isdir(base):
                continue
            for slug in sorted(os.listdir(base)):
                d = os.path.join(base, slug)
                if os.path.isdir(d) and os.path.isfile(os.path.join(d, "manifest.json")):
                    roots.append((slug, d))

        gaps, embeds, total = {}, [], 0
        print("Templates audited")
        print("-" * 70)
        for slug, d in roots:
            found = sections_of(d)
            total += len(found)
            odd_types = sorted({t for _f, t, _c, _e in found if t not in TOOL_TYPES})
            raw = []
            for where, kind, content, _extra in found:
                if kind != "html":
                    continue
                label = _section_display_label(kind, content, "Embed")
                if label == "Embed" and not EMBED_IS_FINE.search(content or ""):
                    raw.append((where, " ".join((content or "").split())[:70]))
            if odd_types:
                gaps.setdefault("section type with no tool", set()).update(
                    "%s: %s" % (slug, t) for t in odd_types)
            embeds += [(slug, w, c) for w, c in raw]
            flag = ""
            if odd_types or raw:
                flag = "  <-- " + ", ".join(filter(None, [
                    "types: " + ",".join(odd_types) if odd_types else "",
                    "%d hand-written" % len(raw) if raw else "",
                ]))
            print("  %-24s %3d sections%s" % (slug, len(found), flag))

        print()
        print("  %d templates, %d sections" % (len(roots), total))
        print()
        print("Could an owner build this by hand?")
        print("-" * 70)
        if not gaps and not embeds:
            print("  Yes - every section on every page is a tool an owner can pick.")
            return 0
        for what, where in sorted(gaps.items()):
            print("  %s:" % what)
            for line in sorted(where)[:30]:
                print("     " + line)
        if embeds:
            print("  markup with no tool behind it (the app calls it Embed,")
            print("  and it needs no script or iframe to work):")
            for slug, where, snippet in embeds[:30]:
                print("     %-22s %-18s %s" % (slug, where, snippet))
        print()
        print("  Each of these is a MISSING TOOL, not a broken template.")
        return 1


def self_test():
    """This check has to be able to FAIL, or it is decoration.

    Three pieces of markup, run through the app's own recogniser: a
    hand-rolled two-column grid and a hand-made badge are things an
    owner could not produce from the tool panel, and a Cal.com script
    is exactly what the Embed tool is for.
    """
    with app.app_context():
        bad = ['<div style="display:grid;grid-template-columns:2fr 1fr">two</div>',
               '<span class="badge">New</span>']
        fine = '<script src="https://cal.com/embed.js"></script>'
        for markup in bad:
            label = _section_display_label("html", markup, "Embed")
            assert label == "Embed" and not EMBED_IS_FINE.search(markup), markup
        assert EMBED_IS_FINE.search(fine), fine
    print("  self-test: hand-written markup is caught, a real embed is not")


if __name__ == "__main__":
    self_test()
    sys.exit(main())
