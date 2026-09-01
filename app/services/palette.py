"""Color-palette helpers shared by the Theme Generator, template colors
routes, and package export (see app/services/packages.py).

Pure functions with no Flask coupling. color_scheme_choices() is the one
exception and takes `db` as an argument rather than reaching for it,
because what an admin can pick from now includes the palette of every
installed template, and that is a question only the database can answer.
"""

import json
import re


def _match_palette_roles(palette):
    """Guess which palette slug plays which brand-color role, by name."""
    def find(*keywords):
        for c in palette:
            s = c["slug"].lower()
            if any(k in s for k in keywords):
                return c["slug"]
        return None

    roles = {
        "primary": find("primary", "brand", "main"),
        "secondary": find("secondary"),
        "accent": find("accent", "highlight"),
    }
    if not roles["primary"] and palette:
        roles["primary"] = palette[0]["slug"]
    if not roles["secondary"] and len(palette) > 1:
        roles["secondary"] = palette[1]["slug"]
    return {k: v for k, v in roles.items() if v}


def _darken_hex(hex_color, amount=0.15):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) not in (6,):
        return hex_color
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return f"#{hex_color}"
    r, g, b = (max(0, int(c * (1 - amount))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten_hex(hex_color, amount=0.15):
    """Same idea as _darken_hex, mixed toward white instead of black."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) not in (6,):
        return hex_color
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return f"#{hex_color}"
    r, g, b = (min(255, int(c + (255 - c) * amount)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# The tonal ramp exposed per role color.
#
# Eleven steps, numbered the way design systems number them (50 lightest,
# 950 darkest, 500 the color itself). Five steps was not enough to build
# anything real with: a card needs a background a shade off white, a
# border two steps darker, body text near the bottom of the scale and a
# hover state one step from the base — that is four distinct values from
# ONE role before any of the others are touched.
#
# Built in HSL rather than by mixing toward white and black in RGB. Mixing
# toward white washes the hue out and mixing toward black muddies it, so a
# blue's light end drifts grey and its dark end drifts navy-brown. Holding
# hue fixed and moving lightness keeps every step recognisably the same
# color. Saturation is eased off at both ends because a fully saturated
# near-white glows and a fully saturated near-black looks like ink
# spillage — the same easing every mature palette applies by eye.
RAMP_STEPS = (
    (50, 0.97), (100, 0.94), (200, 0.86), (300, 0.76), (400, 0.64),
    (500, None),  # the color as chosen
    (600, 0.42), (700, 0.34), (800, 0.26), (900, 0.18), (950, 0.11),
)

#  Kept because site-base.css and the built-in themes already read these
#  names in a lot of places. They are aliases onto the numbered scale now,
#  not a second system.
LEGACY_ALIASES = {
    "lightest": 50,
    "light": 200,
    "dark": 600,
    "darker": 800,
    "darkest": 950,
}


def _hex_to_hsl(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    high, low = max(r, g, b), min(r, g, b)
    lightness = (high + low) / 2
    if high == low:
        return 0.0, 0.0, lightness
    delta = high - low
    saturation = delta / (2 - high - low) if lightness > 0.5 else delta / (high + low)
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation, lightness


def _hsl_to_hex(hue, saturation, lightness):
    c = (1 - abs(2 * lightness - 1)) * saturation
    x = c * (1 - abs(((hue / 60) % 2) - 1))
    m = lightness - c / 2
    sector = int(hue // 60) % 6
    rgb = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[sector]
    r, g, b = (max(0, min(255, round((v + m) * 255))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def ramp(hex_color, spread=1.0, sat_ease=0.35, curve=1.0, light_spread=None,
         dark_curve=None):
    """{step: hex} for all eleven steps, with 500 being the chosen color.

    `spread` is how far the scale reaches from the chosen color: below 1
    the shades cluster near it for a quiet, tonal look, above 1 they reach
    further for a punchier one. It scales the DISTANCE to each end rather
    than setting the ends, so the steps stay in order at any value, which
    is what lets this be an admin-facing control (see SHADE_SPREADS in
    services/design.py) without letting anyone produce dark text on a
    darker fill. `sat_ease` is the other half of the same control — how
    much colour drains out toward the ends.

    `curve` is the half that actually shows, and it bends the LIGHT half
    only unless `dark_curve` says otherwise — the two halves do different
    jobs. The light half is fills, and bending it is free. The dark half
    is text, and flattening it drags the darkest steps back toward the
    base until they collide after 8-bit rounding and the words lose their
    contrast; measured, a single curve of 3.4 put six of the shipped
    ramps out of order and dropped the worst pair to 3.7:1. So a setting
    that wants pale fills keeps its darks exactly where they were. It bends how fast the scale
    descends from its light end into the colour, WITHOUT moving either
    end: below 1 the steps dive into colour immediately, so a fill at 100
    is already a real tint; above 1 they hug the light end and stay pale.
    Because the endpoints do not move, neither does the contrast between
    the fill a page paints from and the text it puts on top — which is
    what makes this one safe to hand to an admin where compressing the
    scale was not.

    The light and dark halves are interpolated FROM the chosen color
    rather than aimed at fixed lightness targets. Fixed targets look right
    for a mid-tone and fall apart at the ends: a deep rust at 40% lightness
    sat below its own 600, so the scale ran light, dark, then lighter
    again. Interpolating outward from wherever the color actually sits
    keeps every step in order whatever is chosen, which is the one thing a
    scale has to do.
    """
    hsl = _hex_to_hsl(hex_color)
    normalized = hex_color if hex_color.startswith("#") else f"#{hex_color}"
    if not hsl:
        return {500: normalized}
    hue, saturation, lightness = hsl
    #  Headroom at both ends so a very light or very dark brand color
    #  still has somewhere to go.
    lightest = max(lightness + (1 - lightness) * 0.96, min(0.97, lightness + 0.04))
    darkest = min(lightness * 0.22, max(0.06, lightness - 0.04))
    #  Reach further or less far from the chosen colour. Clamped short of
    #  pure white and pure black so a bold setting still leaves the ends
    #  distinguishable from the page and from ink.
    #  The two ends move independently. The light end is the expensive
    #  one — pulling it toward the colour is what makes a fill carry real
    #  colour instead of a whisper, and it is also what spends contrast
    #  against the dark text the page puts on it. The dark end is nearly
    #  free, so it can deepen to buy some of that back.
    light = spread if light_spread is None else light_spread
    lightest = max(lightness, min(0.985, lightness + (lightest - lightness) * light))
    darkest = min(lightness, max(0.03, lightness - (lightness - darkest) * spread))

    light_steps = [50, 100, 200, 300, 400]
    dark_steps = [600, 700, 800, 900, 950]
    out = {500: normalized}
    #  50 lands ON the light end rather than one interpolation short of
    #  it: the top of the scale is what page backgrounds and subtle fills
    #  are drawn from, and a 50 that is merely pale is no use for either.
    near_base = lightness + (lightest - lightness) * 0.15
    for i, step in enumerate(light_steps):
        t = (i / (len(light_steps) - 1)) ** curve
        out[step] = _shade(hue, saturation, lightest + (near_base - lightest) * t, step, sat_ease)
    for i, step in enumerate(dark_steps):
        t = ((i + 1) / len(dark_steps)) ** (curve if dark_curve is None else dark_curve)
        out[step] = _shade(hue, saturation, lightness + (darkest - lightness) * t, step, sat_ease)
    return {step: out[step] for step, _ in RAMP_STEPS}


def neutral_ramp(hex_color, sat_ease=0.35):
    """The greys of a palette, borrowed from its primary's hue.

    A three-colour palette still needs neutrals — page grounds, hairlines,
    quiet body text — and a template that hardcodes them ends up with a
    fixed cream that stays put however the brand colour changes. Deriving
    them from the primary instead means a warm brand gets warm greys and a
    cool one gets cool greys, and both move together.

    The hue is the primary's; almost none of its saturation survives. Just
    enough for the ground to feel related to the brand rather than
    identical to it — past roughly a tenth it stops reading as a neutral
    and starts competing with the palette it is meant to sit behind. The
    lightness runs the full range rather than being interpolated outward
    from the brand colour, because a neutral scale is not ABOUT the
    primary: it needs its own near-white and its own near-black wherever
    the brand happens to sit.
    """
    hsl = _hex_to_hsl(hex_color)
    if not hsl:
        hue, saturation = 0.0, 0.0
    else:
        hue, saturation, _ = hsl
    tint = min(saturation, 0.10)
    #  Even steps from near-white to near-ink, the same eleven names the
    #  role ramps use so a rule can swap one for the other.
    lightness_by_step = {
        50: 0.985, 100: 0.955, 200: 0.90, 300: 0.82, 400: 0.68, 500: 0.52,
        600: 0.42, 700: 0.33, 800: 0.24, 900: 0.15, 950: 0.08,
    }
    return {step: _shade(hue, tint, light, step, sat_ease)
            for step, light in lightness_by_step.items()}


def _shade(hue, saturation, lightness, step, sat_ease=0.35):
    """One step, with saturation eased off toward the ends — a fully
    saturated near-white glows and a fully saturated near-black reads as
    ink rather than as the color."""
    distance = abs(step - 500) / 450
    eased = saturation * (1 - sat_ease * distance * distance)
    return _hsl_to_hex(hue, max(0.0, min(1.0, eased)), max(0.0, min(1.0, lightness)))


def color_scheme_choices(db):
    """Every colour scheme an admin can pick from: {key: {...}}.

    The eight built-in schemes PLUS the palette of every installed
    template. A template's colours were only ever reachable by activating
    that whole template — its look, its layout and its content — so
    borrowing the palette of one for another was not something the app let
    you ask for, even though a palette is exactly the sort of thing you
    want to try somewhere else. Sixteen of the sixteen built-in templates
    had a scheme the picker did not offer.

    Generated rather than written down, so a template saved from the live
    site or imported from a zip brings its colours into the picker without
    anyone maintaining a list. Keyed "tpl:<slug>" to keep them apart from
    the built-in keys, and de-duplicated on the colours themselves — a
    template whose palette IS one of the built-in schemes does not appear
    twice under two names.
    """
    from .design import COLOR_PRESETS

    out = {k: dict(v, source="built-in") for k, v in COLOR_PRESETS.items()}
    seen = {
        tuple(sorted((v["primary"].lower(), v["secondary"].lower(), v["accent"].lower())))
        for v in COLOR_PRESETS.values()
    }
    rows = db.execute(
        "SELECT slug, name, palette_json FROM templates "
        "WHERE palette_json IS NOT NULL ORDER BY name"
    ).fetchall()
    for row in rows:
        try:
            palette = json.loads(row["palette_json"])
        except (ValueError, TypeError):
            continue
        roles = {}
        for entry in palette:
            slug = (entry.get("slug") or "").lower()
            if slug in ("primary", "secondary", "accent") and entry.get("color"):
                roles[slug] = entry["color"]
        if len(roles) < 3:
            continue
        key = tuple(sorted(c.lower() for c in roles.values()))
        if key in seen:
            continue
        seen.add(key)
        out["tpl:" + row["slug"]] = dict(roles, name=row["name"], source="template")
    return out


def tint_shade_ramp(hex_color, spread=1.0, sat_ease=0.35, curve=1.0, light_spread=None,
                    dark_curve=None):
    """{suffix: hex} for every CSS variable a role color should publish —
    the numbered scale plus the older names, which are now aliases onto
    it rather than a separate set of amounts."""
    steps = ramp(hex_color, spread, sat_ease, curve, light_spread, dark_curve)
    out = {str(step): value for step, value in steps.items() if step != 500}
    for name, step in LEGACY_ALIASES.items():
        if step in steps:
            out[name] = steps[step]
    return out


def _relative_luminance(hex_color):
    hex_color = (hex_color or "").lstrip("#")
    if len(hex_color) != 6:
        return 1.0
    channels = []
    for i in (0, 2, 4):
        value = int(hex_color[i:i + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(a, b):
    la, lb = _relative_luminance(a), _relative_luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def readable_on(hex_color):
    """Black or white, whichever can actually be read on this colour.

    Buttons and filled bands were hardcoded to white text, which is right
    for a deep navy and wrong for a sage green: one built-in came out at
    3.6:1, below the 4.5:1 a person with ordinary eyesight needs at body
    size. Choosing per colour means a palette can be as light as it likes
    without the text on it becoming a decision anybody has to remember to
    check.
    """
    try:
        dark = contrast_ratio(hex_color, "#111111")
        light = contrast_ratio(hex_color, "#ffffff")
    except (ValueError, TypeError):
        return "#ffffff"
    return "#111111" if dark > light else "#ffffff"


def role_ramps(template):
    """A template's three role colours, resolved and expanded.

    {"primary": {"base": "#...", "lightest": "#...", ...}, ...}. Any
    override the owner has set wins over the palette the template shipped
    with, which is what makes this the honest answer to "what colour is
    this site". Read by the Colors panel's depth preview, and by the
    newsletter, which sends in these colours rather than in a hardcoded
    blue."""
    if not template or not template["palette_json"]:
        return {}
    try:
        palette = json.loads(template["palette_json"])
    except (ValueError, TypeError):
        return {}
    if not palette:
        return {}
    overrides = json.loads(template["color_overrides"]) if template["color_overrides"] else {}
    roles = _match_palette_roles(palette)
    ramps = {}
    for role_name in ("primary", "secondary", "accent"):
        role_slug = roles.get(role_name)
        if not role_slug:
            continue
        color = overrides.get(role_slug) or next((c["color"] for c in palette if c["slug"] == role_slug), None)
        if color and re.match(r"^#[0-9a-fA-F]{6}$", color):
            ramps[role_name] = {"base": color, **tint_shade_ramp(color)}
    return ramps


# ---------------------------------------------------------------------
#  The colours a page needs that are NOT roles.
#
#  A palette gives three decisions: primary, secondary, accent. A page
#  needs four more things, and every one of them was left to chance:
#  what colour the paper is, what colour the ink is, what a hairline
#  looks like, and what may safely be written ON the accent.
#
#  Left to chance means #ffffff and #000000, which is not a neutral
#  choice -- it is the absence of one, and it is most of what makes a
#  generated page look generated. A ground with 3% of the brand in it
#  and an ink that is the brand darkened to near-black cost nothing and
#  read immediately as chosen.
#
#  The two accent variants are not taste at all, they are arithmetic:
#  measured, #ff4000 on white is 3.51:1, which fails AA for anything
#  under 24px -- so an accent used as a text colour has to be darkened
#  until it passes, and white on that same accent fails just as badly,
#  so a band painted in it takes dark ink instead. A generator that
#  picks a bright accent and then writes white on it has produced an
#  inaccessible page from a correct palette.


def _rgb(colour):
    colour = (colour or "").strip().lstrip("#")
    if len(colour) != 6:
        return None
    try:
        return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def _relative_luminance(rgb):
    def channel(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one, two):
    """The WCAG ratio between two colours, or 1.0 if either is unreadable."""
    a, b = _rgb(one), _rgb(two)
    if not a or not b:
        return 1.0
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _mix(one, two, amount):
    a, b = _rgb(one), _rgb(two)
    if not a or not b:
        return one
    return _hex(tuple(x + (y - x) * amount for x, y in zip(a, b)))


def page_colours(palette, ground=""):
    """Ground, ink, tint, hairline, card and the two accent variants.

    ONE path, whatever colour the ground is -- pale, dark, or the mid
    grey-blue a photograph of a workshop actually has. There were two
    branches, one for light pages and one for dark, and a mid ground fit
    neither, so it was thrown away and a light page derived instead.
    That is the tool overruling the example somebody uploaded: they
    chose that picture, and if they had wanted a white site they would
    have chosen a white one.

    So the direction is MEASURED rather than assumed. Ink is whichever
    of near-black or near-white actually reads on this ground; a band is
    a step away from the ground in whichever direction has room; and the
    accent is walked until it passes 4.5:1 against it. Every one of
    those is arithmetic, which is why the tool can be trusted with a
    colour nobody planned for.
    """
    roles = {r.get("slug"): r.get("color") for r in (palette or [])
             if isinstance(r, dict) and r.get("color")}
    primary = roles.get("primary") or "#333333"
    accent = roles.get("accent") or roles.get("secondary") or primary
    if not _rgb(primary):
        return {}

    #  The picture's own ground, or one mixed from the brand when there
    #  is no picture at all.
    if not (ground and _rgb(ground)):
        ground = _mix("#ffffff", primary, 0.03)
    #  Is this a dark page? MEASURED, not thresholded.
    #
    #  A luminance cut-off gets mid grounds wrong in both directions: a
    #  sage #989880 sits at 0.30 and so counted as "dark", which sent the
    #  ink light and the accent walking towards white -- on a ground
    #  where dark text actually reads better by two and a half times.
    #  The question is not how bright the ground is, it is which ink
    #  wins on it, and that is one comparison.
    dark_page = contrast("#ffffff", ground) > contrast("#111111", ground)

    #  Ink: the direction that reads, tinted towards the brand so it is
    #  a chosen colour rather than plain black or plain white.
    ink = _mix("#f4f4f4", primary, 0.06) if dark_page else _mix(primary, "#000000", 0.55)
    if contrast(ink, ground) < 7.0:
        ink = "#f2f2f2" if dark_page else "#241f1f"
    #  ...and if the ground is mid enough that neither passes, take
    #  whichever passes better and say so by measuring, not by hoping.
    if contrast(ink, ground) < 4.5:
        ink = max(("#ffffff", "#111111"), key=lambda c: contrast(c, ground))

    #  A band steps AWAY from the ground -- lighter on a dark page,
    #  darker on a light one -- because the direction is what makes it
    #  read as a band at all.
    towards = "#ffffff" if dark_page else "#000000"
    tint = _mix(ground, towards, 0.13 if dark_page else 0.05)
    line = _mix(ground, towards, 0.22 if dark_page else 0.12)
    card = _mix(ground, "#ffffff" if dark_page else "#ffffff",
                0.05 if dark_page else 1.0)

    accent_ink = max((ink, "#ffffff", "#111111"), key=lambda c: contrast(c, accent))
    #  The accent as TEXT, walked towards white or black until it passes
    #  on THIS ground.
    accent_text = accent
    for step in range(1, 15):
        if contrast(accent_text, ground) >= 4.5:
            break
        accent_text = _mix(accent, towards_text(ground), step * 0.06)
    return {
        "--site-ground": ground,
        "--site-ink": ink,
        "--site-tint": tint,
        "--site-line": line,
        "--site-card-bg": card,
        "--site-accent-ink": accent_ink,
        "--site-accent-text": accent_text,
    }


def towards_text(ground):
    """Which way an accent has to move to read on this ground.

    The same measurement the page itself uses: towards whichever of
    white or black carries better here.
    """
    return ("#ffffff" if contrast("#ffffff", ground) > contrast("#111111", ground)
            else "#000000")


def _unused_light_page(palette, ground=""):
    """The old light-only path, kept for one release as a reference.

    It is not called: `page_colours` has one path now, which measures
    the ground rather than assuming which way round the page is. Two
    branches is exactly what made a mid-tone ground fit neither.
    """
    """Ground, ink, tint, hairline and the two safe accent variants.

    Returned as a plain dict of CSS custom properties, so the caller
    emits them beside the role colours and nothing has to know how they
    were worked out.
    """
    roles = {r.get("slug"): r.get("color") for r in (palette or [])
             if isinstance(r, dict) and r.get("color")}
    primary = roles.get("primary") or "#333333"
    accent = roles.get("accent") or roles.get("secondary") or primary
    if not _rgb(primary):
        return {}

    #  The picture's own pale ground when it gave us one -- Hacker
    #  News's cream is the whole first impression of that page and
    #  cannot be derived from a brand colour.
    ground = ground if (ground and _rgb(ground)) else _mix("#ffffff", primary, 0.03)
    ink = _mix(primary, "#000000", 0.55)
    #  ...unless the brand is already so dark that darkening it further
    #  makes an ink nobody could tell from black.
    if contrast(ink, ground) < 7.0:
        ink = "#241f1f"
    tint = _mix(ground, roles.get("secondary") or accent, 0.08)
    line = _mix(ground, ink, 0.12)

    #  What may be written ON the accent: whichever of the two reads
    #  better, rather than white because white is usual.
    accent_ink = ink if contrast(ink, accent) >= contrast("#ffffff", accent) else "#ffffff"
    #  ...and the accent as TEXT, darkened until it passes on the ground.
    accent_text = accent
    for step in range(1, 13):
        if contrast(accent_text, ground) >= 4.5:
            break
        accent_text = _mix(accent, "#000000", step * 0.06)
    return {
        "--site-ground": ground,
        "--site-ink": ink,
        "--site-tint": tint,
        "--site-line": line,
        #  A card on a light page is white; the ground is the warm one.
        "--site-card-bg": "#ffffff",
        "--site-accent-ink": accent_ink,
        "--site-accent-text": accent_text,
    }
