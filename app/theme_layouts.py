"""Hand-built starter layouts for the AI Theme Generator (see theme_generator.py).

Each layout is a small, fixed set of sections built entirely from the CMS's
own tools (Banner, Text, Card via Columns) — never raw/opaque HTML. The
generator fills them with AI-written copy (or leaves them blank, per the
admin's choice) and hands the resulting HTML chunks to admin.py's existing
_insert_layout_chunks, which classifies each chunk into a real section the
same way a hand-built page would be — so everything it produces is editable
afterward exactly like anything the admin built by hand.
"""

LAYOUTS = {
    "landing": {
        "label": "Landing",
        "description": "Hero banner, short intro, three feature highlights, and a closing call-to-action.",
    },
    "about": {
        "label": "About / Story",
        "description": "Hero banner, a longer story/about section, and a closing call-to-action.",
    },
    "simple": {
        "label": "Simple",
        "description": "Just a hero banner and one text section — the smallest useful starting point.",
    },
}
