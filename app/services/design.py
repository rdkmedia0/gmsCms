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

# Corner-radius language — bridged into --site-radius, which the generic
# card/banner/panel classes in site-base.css read via
# var(--site-radius, <theme's own original value>), so picking a preset
# here can only ever move a template AWAY from its own default, never
# break a template that hasn't opted in (see shape_override being NULL by
# default). "Organic" is a full border-radius shorthand rather than a
# single length because that's what an asymmetric "worn pebble" shape
# actually requires — still just one preset choice from the admin's side.
#
# Four of these curve far enough to reach into their own box. A radius of
# 999px turns a tall card into a stadium, but its content is still laid
# out in the rectangle, so on a phone the button at the foot of a pricing
# tier sat outside the curve. The shape is not the problem — it is the
# whole character of those presets — the padding is: content has to be
# inset far enough to clear the corner it is sitting in.
#
# So those four carry the padding their own shape needs, and
# _color_override_css in routes/public.py emits it as a rule over the
# boxes whose content reaches their edges. The numbers are geometry, not
# taste. A corner is an ellipse of radii (rx, ry) centred that far in
# from the corner, and content inset by (px, py) clears it while
# ((rx-px)/rx)^2 + ((ry-py)/ry)^2 <= 1. Solving that for a card at least
# as tall as it is wide — which is what all of these are, a card in a
# column — gives the pairs below, with a margin over the minimum, since
# the binding corner is a full-width button sitting flush with the bottom
# of the padding box and one that only just clears the curve stops
# clearing it the moment a theme adds a border.
#
# They are deliberately lopsided. On a tall box the curve is at the top
# and the bottom, so that is where the room should come from; paying for
# it sideways instead just narrows the text for no gain (it cost a
# pricing tier 40px of line length before this was split). The Lens and
# the Organics curve more deeply again, and their vertical radius is a
# share of the HEIGHT, so they hold to roughly two and a half times
# taller than wide and want a squarer box past that.
#
# The absolute caps are for the other extreme: a wide box, where a
# percentage of the width is a percentage of the LONG side and would pad
# a 1100px box by 264px for a corner only 150px across.
#
# Decorative surfaces — a banner, a picture, a button — are left alone:
# nothing inside them can spill.
SHAPE_PRESETS = {
    "sharp": {"name": "Sharp", "radius": "0px"},
    "soft": {"name": "Soft", "radius": "10px"},
    "rounded": {"name": "Rounded", "radius": "22px"},
    "pill": {
        "name": "Pill",
        "radius": "999px",
        "content_padding": "min(24%, 88px) min(9%, 36px)",
    },
    "lens": {
        "name": "Lens",
        "radius": "50% / 30%",
        "content_padding": "min(30%, 96px) min(9%, 36px)",
    },
    "cut-corner": {"name": "Cut Corner", "radius": "0 32px 0 32px"},
    "organic": {
        "name": "Organic",
        "radius": "60% 40% 55% 45% / 45% 55% 40% 60%",
        "content_padding": "min(34%, 104px) min(14%, 52px)",
    },
    "organic-alt": {
        "name": "Organic (Alt)",
        "radius": "30% 70% 70% 30% / 30% 30% 70% 70%",
        "content_padding": "min(34%, 104px) min(14%, 52px)",
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
#  how much tonal depth a three-colour site has — the answer to "give me
#  more than three flat colours" without asking anyone to choose nine.
#
#  Named rather than numeric, and site-wide rather than per colour, for
#  the same reason Corners and Depth are: an admin can picture "Subtle"
#  and cannot picture "0.62".
#
#  The variation is carried almost entirely by `sat_ease` — how fast
#  colour drains out toward the ends — and barely at all by `spread`, the
#  distance the scale reaches. That split is not a preference, it is what
#  the numbers allow: the page sets text from the dark end on fills from
#  the light end, so compressing the scale compresses that pair's
#  contrast. Measured over all 72 shipped colours, a spread of 0.80 put
#  two ramps out of order and dropped the worst pair to 4.7:1, under the
#  4.5:1 AA needs once rounding is counted; 0.85 was the floor. Saturation
#  has no such limit — across the whole range every ramp stays in order
#  and no pair falls below 6.8:1, while the colour left in a light fill
#  more than doubles. So the control varies what is free to vary.
#  `curve` is what carries the difference. Saturation alone was almost
#  invisible on a real page: it only bites at the far ends of the scale,
#  and the far light end is nearly white, where a doubling of saturation
#  is a couple of values of chroma nobody can see. `curve` bends how fast
#  the scale descends from its light end INTO the colour, which is where
#  the fills a page actually paints with live — steps 100 and 200. Below
#  1 they dive into colour immediately; above 1 they hug the light end and
#  stay pale.
#
#  It is safe for the same reason the saturation was and the compression
#  was not: bending the path between two fixed endpoints never moves the
#  endpoints, so the contrast between the light fill and the dark text is
#  identical at every setting.
#
#  Where each number came from, since none of them is a taste call:
#
#    Subtle's curve stops at 3.0. Past 3.2 the light steps crowd so close
#    to the light end that two of them land on the same value once
#    rounded to 8 bits, and a scale with a flat spot in it is a broken
#    scale. Its dark_curve stays at 1.0 deliberately — bending BOTH
#    halves is what put six ramps out of order and dropped the worst pair
#    to 3.7:1 at an earlier attempt, because the dark half is the text.
#
#    Bold pulls its light end 38% of the way back toward the colour
#    (light_spread 0.62), which is what actually puts colour in a fill,
#    and deepens the dark end to buy back the contrast that costs. It
#    lands at 7.4:1 — the same neighbourhood as Balanced's 7.3:1.
#
#  Measured across all 72 shipped colours, average chroma of the fill at
#  step 100: 3, 23, 92. Thirty times the colour between the ends of the
#  control, with every ramp in order and no pair below 7.3:1.
SHADE_SPREADS = {
    "subtle": {"name": "Subtle", "spread": 1.0, "sat_ease": 0.80,
               "curve": 3.0, "dark_curve": 1.0},
    "balanced": {"name": "Balanced", "spread": 1.0, "sat_ease": 0.35,
                 "curve": 1.0},
    "bold": {"name": "Bold", "spread": 1.20, "sat_ease": 0.02,
             "curve": 0.30, "light_spread": 0.62, "dark_curve": 0.72},
}
