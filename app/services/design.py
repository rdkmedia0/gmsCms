"""The fixed sets of design choices an admin picks from: colour schemes,
font pairings, the individual font list, corner styles and depth.

They live here rather than in the admin Blueprint because they are data,
not routing — a route should read them, never own them. They were the
largest tenant of a 1,200-line route package, which is the exact shape
CLAUDE.md warns about ("a big config dict does not belong as a Python
literal inside a route file"), and every one of them is read from more
than one place: the public site bridges shape and depth into CSS
variables, the seeder reads the palettes, and the admin panels render
all five.

Kept as Python literals rather than as JSON under app/data/ because each
carries its reasoning in its own comments, which a data file cannot hold,
and because SHAPE_PRESETS pairs every radius with the content inset that
shape needs — a relationship, not a value. app/data/ stays the home for
CONTENT (a template package, a demo site's pages); this is a vocabulary
the code itself speaks.
"""

# Each preset's secondary is analogous to (or a shade of) its primary, for
# cohesion; its accent is chosen as a genuine complementary or
# split-complementary contrast — the color roughly opposite the primary on
# the color wheel — so CTAs/highlights actually pop against the brand
# color instead of blending into it. Forest/Summer/Sunset/Berry/Slate
# already had that contrast; Ocean and Classic Blue were purely
# monochromatic (every color the same hue, just lighter/darker) and got a
# real complementary accent (coral for teal, amber for blue) instead.
# Monochrome is deliberately hue-free — that's the point of it.
COLOR_PRESETS = {
    "forest": {"name": "Forest", "primary": "#2F5233", "secondary": "#8AA624", "accent": "#C9A227"},
    "summer": {"name": "Summer", "primary": "#FF6F3C", "secondary": "#FFD23F", "accent": "#0FA3B1"},
    "ocean": {"name": "Ocean", "primary": "#005F73", "secondary": "#0A9396", "accent": "#E76F51"},
    "sunset": {"name": "Sunset", "primary": "#D7263D", "secondary": "#F46036", "accent": "#F6AE2D"},
    "berry": {"name": "Berry", "primary": "#7B2D8B", "secondary": "#C81D77", "accent": "#F25F5C"},
    "slate": {"name": "Slate", "primary": "#2B2D42", "secondary": "#8D99AE", "accent": "#EF233C"},
    "classic-blue": {"name": "Classic Blue", "primary": "#2563EB", "secondary": "#1D4ED8", "accent": "#F59E0B"},
    "mono": {"name": "Monochrome", "primary": "#1F2430", "secondary": "#6B7280", "accent": "#111111"},
}

# Curated heading+body pairings — the same "quick-start preset on top of a
# free-form field" relationship COLOR_PRESETS has with the raw color
# pickers, so choosing a font pairing never requires knowing real Google
# Fonts family names. `google_fonts_url` is the stylesheet link the
# pairing needs — self-hosted (app/static/fonts/<key>.css, downloaded
# once rather than fetched from fonts.googleapis.com at request time; see
# app/static/fonts/licenses/ for each family's OFL/Apache license text,
# required for redistributing the font files themselves) so a page never
# pings Google's servers just to render its own text. "" (System Sans)
# deliberately means "no webfont at all", not "fall back to the theme's
# own" — picking a pairing always fully replaces the theme's font
# declaration, the same way a color override fully replaces that one role
# rather than blending with the default.
FONT_PAIRINGS = {
    "cormorant-jost": {
        "name": "Cormorant + Jost", "heading": "\"Cormorant Garamond\", Georgia, serif",
        "body": "\"Jost\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/cormorant-jost.css",
    },
    "fraunces-nunito": {
        "name": "Fraunces + Nunito Sans", "heading": "\"Fraunces\", Georgia, serif",
        "body": "\"Nunito Sans\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/fraunces-nunito.css",
    },
    "dmserif-worksans": {
        "name": "DM Serif + Work Sans", "heading": "\"DM Serif Display\", Georgia, serif",
        "body": "\"Work Sans\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/dmserif-worksans.css",
    },
    "grotesk-inter": {
        "name": "Space Grotesk + Inter", "heading": "\"Space Grotesk\", -apple-system, \"Segoe UI\", sans-serif",
        "body": "\"Inter\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/grotesk-inter.css",
    },
    "bebas-archivo": {
        "name": "Bebas Neue + Archivo", "heading": "\"Bebas Neue\", \"Arial Narrow\", sans-serif",
        "body": "\"Archivo\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/bebas-archivo.css",
    },
    "marcellus-karla": {
        "name": "Marcellus + Karla", "heading": "\"Marcellus\", Georgia, serif",
        "body": "\"Karla\", -apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/marcellus-karla.css",
    },
    "playfair-system": {
        "name": "Playfair Display + System", "heading": "\"Playfair Display\", Georgia, serif",
        "body": "-apple-system, \"Segoe UI\", sans-serif",
        "google_fonts_url": "/static/fonts/playfair-system.css",
    },
    "system-only": {
        "name": "System Sans (no webfont)", "heading": "-apple-system, \"Segoe UI\", sans-serif",
        "body": "-apple-system, \"Segoe UI\", sans-serif", "google_fonts_url": "",
    },
}

# A curated ~50-name slice of Google Fonts' most-used families (spanning
# sans/serif/slab/display/script so there's real variety, not 50 near-
# identical grotesques), for the Fonts panel's "pick a font individually"
# dropdowns — the pairings above stay the fast/no-thought quick-start;
# this is the "I know roughly what I want" path. (family, generic
# fallback) — the fallback is what actually goes in the CSS font-family
# value after the family name, so a slow/failed webfont load still lands
# on a same-shape system font instead of the browser's serif default.
GOOGLE_FONT_CHOICES = (
    ("Roboto", "sans-serif"), ("Open Sans", "sans-serif"), ("Lato", "sans-serif"),
    ("Montserrat", "sans-serif"), ("Oswald", "sans-serif"), ("Raleway", "sans-serif"),
    ("Poppins", "sans-serif"), ("Merriweather", "serif"), ("Nunito", "sans-serif"),
    ("Playfair Display", "serif"), ("Ubuntu", "sans-serif"), ("PT Sans", "sans-serif"),
    ("Noto Sans", "sans-serif"), ("Roboto Slab", "serif"), ("Mukta", "sans-serif"),
    ("Rubik", "sans-serif"), ("Inter", "sans-serif"), ("Work Sans", "sans-serif"),
    ("Karla", "sans-serif"), ("Quicksand", "sans-serif"), ("Fira Sans", "sans-serif"),
    ("Source Sans Pro", "sans-serif"), ("Barlow", "sans-serif"), ("Inconsolata", "monospace"),
    ("Cormorant Garamond", "serif"), ("DM Sans", "sans-serif"), ("Josefin Sans", "sans-serif"),
    ("Libre Baskerville", "serif"), ("Crimson Text", "serif"), ("EB Garamond", "serif"),
    ("Bitter", "serif"), ("Archivo", "sans-serif"), ("Space Grotesk", "sans-serif"),
    ("Manrope", "sans-serif"), ("Outfit", "sans-serif"), ("Plus Jakarta Sans", "sans-serif"),
    ("Lexend", "sans-serif"), ("Sora", "sans-serif"), ("IBM Plex Sans", "sans-serif"),
    ("Zilla Slab", "serif"), ("Cabin", "sans-serif"), ("Dosis", "sans-serif"),
    ("Vollkorn", "serif"), ("Alegreya", "serif"), ("Domine", "serif"),
    ("Spectral", "serif"), ("Bebas Neue", "sans-serif"), ("Anton", "sans-serif"),
    ("Abril Fatface", "serif"), ("Caveat", "cursive"), ("Pacifico", "cursive"),
)


def _google_fonts_stylesheet_url(family_names):
    """The <link> href for however many family names are given — used both
    for a single applied choice (1-2 names) and for preloading every
    GOOGLE_FONT_CHOICES name at once so the Fonts panel's dropdown can
    render each <option> in its own actual font. Self-hosted, not a live
    fonts.googleapis.com request: app/static/fonts/choices.css already
    bundles every GOOGLE_FONT_CHOICES family's @font-face rules (see
    scripts used to build it — app/static/fonts/licenses/ carries each
    family's OFL/Apache license text), so any individual pick is already
    covered by that one file regardless of which names are passed here —
    a browser only ever fetches the specific weight/style a page actually
    uses, so referencing the shared bundle instead of a per-pick file
    costs nothing extra."""
    if not family_names:
        return ""
    return "/static/fonts/choices.css"

# Corner-radius language, bridged into --site-radius, which the generic
# card/banner/panel classes read as var(--site-radius, <theme's own
# value>) -- so a preset can only move a template away from its own
# default, never break one that has not opted in. "Organic" is a full
# border-radius shorthand because an asymmetric shape needs one.
#
# Four of these curve far enough to reach into their own box, so they
# carry the padding their shape needs and public.py emits it as a rule
# over the boxes whose content reaches their edges. The numbers are
# geometry: a corner is an ellipse of radii (rx, ry), and content inset
# by (px, py) clears it while ((rx-px)/rx)^2 + ((ry-py)/ry)^2 <= 1,
# solved for a card at least as tall as it is wide, with a margin so a
# theme adding a border does not push it back into the curve.
#
# Three properties to keep when changing them: the padding is lopsided
# (a tall box curves at top and bottom, so paying sideways only narrows
# the text); the deepest presets take their vertical radius as a share of
# HEIGHT, so they want a squarer box past ~2.5:1; and the absolute caps
# exist for wide boxes, where a percentage of the width is a percentage
# of the long side. Decorative surfaces are left alone -- nothing inside
# a banner or a button can spill.
#  The side figure is set by the corner, not by eye. A block 950 wide and
#  560 tall with a 999px radius gets 280px corners (half the short side),
#  so content sitting 88px below the top edge needs
#  280 - sqrt(280^2 - (280-88)^2) = 76px of side clearance before it is
#  inside the shape at all. It had 36px, which is why a first list item
#  and a first blog card sat on the curve. 104px clears it with room.
#  A phone makes every box tall and narrow, and an ellipse that tall
#  cannot hold a paragraph: measured on a real page, a 190x471 newsletter
#  block had its words 3.05 times outside its own curve. Padding cannot
#  fix it -- adding vertical padding makes the box taller, which makes the
#  ellipse taller, which pushes the words further out. Tried: +92px of
#  padding moved 3.05 to 2.49.
#
#  So the strongly-curved shapes state a small-screen radius as well.
#  Below the breakpoint they become firmly rounded corners rather than
#  ellipses -- the same judgement the video and textarea caps already
#  make, and for the same reason: at that size the shape stops the thing
#  working. `radius_small` is absent on the gentle shapes, which need no
#  such thing.
SHAPE_SMALL_SCREEN_MAX = 700

SHAPE_PRESETS = {
    "sharp": {"name": "Sharp", "radius": "0px", "radius_safe": "0px"},
    "soft": {"name": "Soft", "radius": "10px", "radius_safe": "10px"},
    "rounded": {"name": "Rounded", "radius": "22px", "radius_safe": "22px"},
    "pill": {
        "name": "Pill",
        "radius": "999px",
        "radius_small": "26px",
        "content_padding": "min(24%, 88px) min(22%, 104px)",
        #  For a box much WIDER than it is tall. Percentage padding
        #  resolves against WIDTH on every side, so the figure above
        #  turned a 420x80 row into 420x352; the vertical half is a
        #  length here and only the horizontal stays a percentage,
        #  because horizontally it is measuring the right thing.
        "row_padding": "16px min(13%, 56px)",
        #  The shape as a plain LENGTH, for the things that
        #  cannot wear the real one -- a video, whose controls
        #  live on the edge that curves away, and a textarea,
        #  which is the one field tall enough for a pill to
        #  become a stadium. clamp() cannot do this: a lens is
        #  `50% / 30%`, so the declaration is invalid after
        #  substitution and becomes unset rather than falling
        #  back.
        "radius_safe": "28px",
    },
    "lens": {
        "name": "Lens",
        "radius": "50% / 30%",
        "radius_small": "22px",
        "content_padding": "min(30%, 96px) min(22%, 104px)",
        "row_padding": "16px min(12%, 50px)",
        "radius_safe": "24px",
    },
    "cut-corner": {"name": "Cut Corner", "radius": "0 32px 0 32px", "radius_safe": "20px"},
    "organic": {
        "name": "Organic",
        "radius": "60% 40% 55% 45% / 45% 55% 40% 60%",
        "radius_small": "22px",
        "content_padding": "min(34%, 104px) min(14%, 52px)",
        "row_padding": "18px min(11%, 46px)",
        "radius_safe": "24px",
    },
    "organic-alt": {
        "name": "Organic (Alt)",
        "radius": "30% 70% 70% 30% / 30% 30% 70% 70%",
        "radius_small": "22px",
        "content_padding": "min(34%, 104px) min(14%, 52px)",
        "row_padding": "18px min(11%, 46px)",
        "radius_safe": "24px",
    },
}

# Elevation, bridged into --site-shadow the same way SHAPE_PRESETS is
# bridged into --site-radius: every generic class reads
# var(--site-shadow, <its own original value>), so picking one can only
# move a template away from its own default, never break one that hasn't
# opted in.
#
# Tinted from the palette rather than black on purpose. Every other color
# in this app flows from the palette, and a black drop shadow is both the
# usual amateur tell AND invisible on a dark theme — a primary-tinted one
# stays visible on either, because the tint is a real hue rather than an
# absence of light. Kept to four steps: offset/blur/spread as separate
# controls would be four ways for a novice to get one effect wrong.
SHADOW_PRESETS = {
    "none": {"name": "Flat", "shadow": "none"},
    "subtle": {
        "name": "Subtle",
        "shadow": "0 1px 3px color-mix(in srgb, var(--primary, #1f2937) 18%, transparent)",
    },
    "raised": {
        "name": "Raised",
        "shadow": "0 4px 14px color-mix(in srgb, var(--primary, #1f2937) 22%, transparent)",
    },
    "floating": {
        "name": "Floating",
        "shadow": "0 14px 34px color-mix(in srgb, var(--primary, #1f2937) 28%, transparent)",
    },
}

#  How much COLOUR the eleven shades of each palette colour carry as they
#  move away from the colour itself. The page paints fills from the light
#  end and text from the dark end, so this is the one control that decides
#  how much tonal depth a three-colour site has.
#
#  Named rather than numeric, and site-wide rather than per colour, for
#  the same reason Corners and Depth are: an admin can picture "Subtle"
#  and cannot picture "0.62".
#
#  Two rules bound any change to these numbers, both measured over all 72
#  shipped colours (see BOW.md, "Shade spreads"):
#
#    * `spread` must not go below 0.85, and `dark_curve` must stay at 1.0
#      for the lighter settings. Both compress the gap between the light
#      fill and the dark text on it, which is the contrast AA is measured
#      on -- 0.80 dropped the worst pair to 4.7:1 and put two ramps out of
#      order.
#    * `sat_ease` and `curve` are free to vary. They bend the path between
#      two fixed endpoints without moving the endpoints, so no setting can
#      change that contrast. This is where the visible difference lives.
SHADE_SPREADS = {
    "subtle": {"name": "Subtle", "spread": 1.0, "sat_ease": 0.80,
               "curve": 3.0, "dark_curve": 1.0},
    "balanced": {"name": "Balanced", "spread": 1.0, "sat_ease": 0.35,
                 "curve": 1.0},
    "bold": {"name": "Bold", "spread": 1.20, "sat_ease": 0.02,
             "curve": 0.30, "light_spread": 0.62, "dark_curve": 0.72},
}


#  ---------------------------------------------------------------------
#  COMPOSITION: what a page is SHAPED like.
#
#  Corners and Depth say what an EDGE looks like. This says what the page
#  looks like from across the room -- how tall the hero stands, how much
#  air a band gets, how big the headings are against the text, how far
#  apart the lines sit, how wide a column of reading gets.
#
#  Every one of these numbers was a constant in site-base.css, which is
#  why two templates with different palettes still read as one design
#  wearing two colours. They are tokens now (see the Composition block in
#  site-base.css) and this is the set of answers.
#
#  A preset is a whole opinion, not a slider: the values inside one are
#  chosen against each other. A big type scale wants more air and a
#  narrower measure or it reads as shouting; a quiet scale wants a longer
#  line or it reads as a form.
COMPOSITION_PRESETS = {
    "classic": {
        "name": "Classic",
        "blurb": "Even, familiar, unfussy — the proportions this app has always had.",
        "vars": {},
    },
    "editorial": {
        "name": "Editorial",
        "blurb": "Big quiet headlines, a narrow column, plenty of air. Reads like "
                 "something written rather than something sold.",
        "vars": {
            "--site-h1-size": "clamp(2.75rem, 6vw, 5rem)",
            "--site-h2-size": "clamp(2rem, 3.4vw, 3rem)",
            "--site-h3-size": "22px",
            "--site-h1-line": "1.1", "--site-h2-line": "1.15", "--site-h3-line": "1.3",
            "--site-heading-weight": "500", "--site-heading-track": "-0.03em",
            "--site-hero-min": "80vh",
            "--site-hero-align": "left",
            "--site-hero-block": "min(58ch, 92%)",
            "--site-hero-text": "20ch",
            "--site-hero-margin": "0",
            "--site-hero-justify": "flex-start",
            "--site-block-pad": "0", "--site-band-pad-mobile": "72px",
            "--site-hero-place": "end", "--site-hero-pad": "0 0 96px",
            "--site-card-pad": "36px", "--site-card-align": "left",
            "--site-band-pad": "80px", "--site-band-pad-tight": "88px",
            "--site-lead": "1.7", "--site-lead-size": "21px",
            "--site-content-max": "1180px", "--site-measure": "66ch", "--site-scrim": "0.5",
            "--site-btn-pad": "16px 34px", "--site-btn-weight": "600",
            "--site-btn-track": "0.02em",
            "--site-eyebrow-track": "0.16em",
        },
    },
    "bold": {
        "name": "Bold",
        "blurb": "Enormous headlines over a tall picture, and a button you cannot "
                 "miss. For a place with one thing to say.",
        "vars": {
            "--site-h1-size": "clamp(3rem, 7.5vw, 6rem)",
            "--site-h2-size": "clamp(2.25rem, 4vw, 3.5rem)",
            "--site-h3-size": "24px",
            "--site-h1-line": "1.08", "--site-h2-line": "1.1", "--site-h3-line": "1.25",
            "--site-heading-weight": "700", "--site-heading-track": "-0.035em",
            "--site-hero-min": "78vh",
            "--site-hero-align": "left",
            "--site-hero-block": "min(56ch, 92%)",
            "--site-hero-text": "20ch",
            "--site-hero-margin": "0",
            "--site-hero-justify": "flex-start",
            "--site-block-pad": "0", "--site-band-pad-mobile": "64px",
            "--site-hero-place": "end", "--site-hero-pad": "0 0 88px",
            "--site-card-pad": "32px", "--site-card-align": "left",
            "--site-band-pad": "88px", "--site-band-pad-tight": "80px",
            "--site-lead": "1.6", "--site-lead-size": "20px",
            "--site-content-max": "1240px", "--site-measure": "62ch", "--site-scrim": "0.62",
            "--site-btn-pad": "18px 38px", "--site-btn-weight": "600",
            "--site-btn-track": "0.08em", "--site-btn-case": "uppercase",
            "--site-eyebrow-track": "0.14em",
        },
    },
    "quiet": {
        "name": "Quiet",
        "blurb": "Small headings, long lines, a lot of white. For somebody whose work "
                 "should be the loudest thing on the page.",
        "vars": {
            "--site-h1-size": "clamp(2.5rem, 4.5vw, 3.75rem)",
            "--site-h2-size": "clamp(1.75rem, 2.6vw, 2.25rem)",
            "--site-h3-size": "20px",
            "--site-h1-line": "1.08", "--site-h2-line": "1.2", "--site-h3-line": "1.35",
            "--site-heading-weight": "500", "--site-heading-track": "-0.015em",
            "--site-hero-min": "68vh",
            "--site-hero-align": "center",
            "--site-hero-block": "min(60ch, 88%)",
            "--site-hero-text": "24ch",
            "--site-hero-margin": "auto",
            "--site-hero-justify": "center",
            "--site-block-pad": "0", "--site-band-pad-mobile": "56px",
            "--site-hero-place": "center", "--site-hero-pad": "0",
            "--site-card-pad": "28px", "--site-card-align": "center",
            "--site-band-pad": "80px", "--site-band-pad-tight": "64px",
            "--site-lead": "1.8", "--site-lead-size": "19px",
            "--site-content-max": "1040px", "--site-measure": "60ch", "--site-scrim": "0.45",
            "--site-btn-pad": "14px 28px", "--site-btn-weight": "500",
            "--site-btn-track": "0.01em",
            "--site-eyebrow-track": "0.1em",
        },
    },
    "warm": {
        "name": "Warm",
        "blurb": "Friendly proportions, a softer scale, and room to breathe. For a "
                 "place people come back to.",
        "vars": {
            "--site-h1-size": "clamp(2.5rem, 5vw, 4rem)",
            "--site-h2-size": "clamp(1.9rem, 3vw, 2.5rem)",
            "--site-h3-size": "21px",
            "--site-h1-line": "1.1", "--site-h2-line": "1.2", "--site-h3-line": "1.3",
            "--site-heading-weight": "600", "--site-heading-track": "-0.01em",
            "--site-hero-min": "72vh",
            "--site-hero-align": "center",
            "--site-hero-block": "min(58ch, 90%)",
            "--site-hero-text": "22ch",
            "--site-hero-margin": "auto",
            "--site-hero-justify": "center",
            "--site-block-pad": "0", "--site-band-pad-mobile": "60px",
            "--site-hero-place": "center", "--site-hero-pad": "0",
            "--site-card-pad": "32px", "--site-card-align": "center",
            "--site-band-pad": "84px", "--site-band-pad-tight": "72px",
            "--site-lead": "1.7", "--site-lead-size": "19px",
            "--site-content-max": "1120px", "--site-measure": "64ch", "--site-scrim": "0.55",
            "--site-btn-pad": "16px 32px", "--site-btn-weight": "600",
            "--site-btn-track": "0.02em",
            "--site-eyebrow-track": "0.12em",
        },
    },
    "compact": {
        "name": "Compact",
        "blurb": "Tight bands and a firm scale, so more of the page is visible at "
                 "once. For a site with a lot to list.",
        "vars": {
            "--site-h1-size": "clamp(2.25rem, 3.6vw, 3rem)",
            "--site-h2-size": "clamp(1.6rem, 2.4vw, 2rem)",
            "--site-h3-size": "20px",
            "--site-h1-line": "1.1", "--site-h2-line": "1.2", "--site-h3-line": "1.3",
            "--site-heading-weight": "700", "--site-heading-track": "-0.01em",
            "--site-hero-min": "58vh",
            "--site-hero-align": "left",
            "--site-hero-block": "min(62ch, 92%)",
            "--site-hero-text": "24ch",
            "--site-hero-margin": "0",
            "--site-hero-justify": "flex-start",
            "--site-block-pad": "0", "--site-band-pad-mobile": "44px",
            "--site-hero-place": "end", "--site-hero-pad": "0 0 64px",
            "--site-card-pad": "24px", "--site-card-align": "left",
            "--site-band-pad": "64px", "--site-band-pad-tight": "48px",
            "--site-lead": "1.6", "--site-lead-size": "18px",
            "--site-content-max": "1160px", "--site-measure": "68ch", "--site-scrim": "0.5",
            "--site-btn-pad": "13px 24px", "--site-btn-weight": "600",
            "--site-btn-track": "0.02em",
            "--site-eyebrow-track": "0.12em",
        },
    },
}
