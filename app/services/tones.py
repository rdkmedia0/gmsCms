"""A colour, expanded into a tonal scale, in a perceptual space.

WHY THIS EXISTS. The palette used to be built by mixing towards black
or white and then MEASURING whether the result could be read -- walking
a colour in 6% steps until it passed, per role, per surface. That is an
audit standing in for an algorithm, and it fails in the ordinary way an
audit fails: it only checks what somebody remembered to check. Sixty-five
pieces of text on the shipped templates were below AA, every one of them
produced by a rule that looked reasonable on its own.

A tonal scale answers it once instead. sRGB is not perceptually even --
mixing 50% towards white does not move a yellow and a blue by the same
amount -- so the scale is built in OKLab, where LIGHTNESS is a real
quantity you can space evenly. Pick a step by its lightness and the
contrast follows from the step you picked, for every hue, without
measuring anything afterwards.

The shape is the one Radix and Material both settled on: a fixed set of
lightness targets, chroma shaped so the pale end stays a tint rather
than turning grey, and named roles that are STEPS rather than colours.
This module holds the arithmetic; services/palette.py assigns the roles.

No dependencies -- the conversions are short and exact, and adding a
colour library to a self-hosted CMS to move six numbers is not a trade
worth making.
"""
import math

#  The scale, as lightness targets in OKLab's L (0..1).
#
#  Twelve steps, densest at the ends, because that is where a page
#  actually works: a ground and a hairline live within a few percent of
#  each other, and so do body text and a heading. The middle is where a
#  brand colour sits and it needs the fewest stops.
LIGHT_STEPS = (0.995, 0.980, 0.960, 0.935, 0.905, 0.870,
               0.820, 0.745, 0.640, 0.560, 0.450, 0.280)

#  The dark scale is NOT the light one inverted. Inverting puts step 1 at
#  L 0.005 -- five colours in a row that are all effectively black, and a
#  hairline indistinguishable from the ground it is meant to separate. A
#  dark interface lives in a narrower, higher band than its mirror image,
#  which is what both Radix and Material found and why they publish two
#  sets of targets rather than one and a flip.
DARK_STEPS = (0.155, 0.190, 0.230, 0.270, 0.310, 0.355,
              0.415, 0.485, 0.580, 0.660, 0.770, 0.935)

#  Chroma as a fraction of the source colour's own, per step. A tint
#  that keeps full chroma reads as a different colour rather than a
#  paler one; a mid step that loses it reads as grey.
CHROMA_SHAPE = (0.10, 0.16, 0.24, 0.34, 0.46, 0.58,
                0.74, 0.90, 1.00, 0.98, 0.88, 0.62)


def _srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c):
    c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return max(0, min(255, int(round(c * 255))))


def _hex_to_rgb(value):
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def to_oklch(value):
    """#rrggbb -> (L, C, H). H in degrees; None for an unreadable value."""
    rgb = _hex_to_rgb(value)
    if not rgb:
        return None
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    ok_l = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    ok_a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    ok_b = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    chroma = math.hypot(ok_a, ok_b)
    hue = math.degrees(math.atan2(ok_b, ok_a)) % 360
    return (ok_l, chroma, hue)


def from_oklch(ok_l, chroma, hue):
    """(L, C, H) -> #rrggbb, with chroma reduced until it fits in sRGB.

    Out-of-gamut is normal at high chroma and the honest fix is to keep
    the lightness -- which is what the contrast depends on -- and give
    up saturation, rather than let a channel clip and move the lightness
    somewhere nobody asked for.
    """
    for step in range(21):
        c = chroma * (1 - step * 0.05)
        rad = math.radians(hue)
        ok_a, ok_b = c * math.cos(rad), c * math.sin(rad)
        l_ = (ok_l + 0.3963377774 * ok_a + 0.2158037573 * ok_b) ** 3
        m_ = (ok_l - 0.1055613458 * ok_a - 0.0638541728 * ok_b) ** 3
        s_ = (ok_l - 0.0894841775 * ok_a - 1.2914855480 * ok_b) ** 3
        r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
        g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
        b = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
        if all(-0.001 <= v <= 1.001 for v in (r, g, b)):
            return _rgb_to_hex(tuple(_linear_to_srgb(v) for v in (r, g, b)))
    return _rgb_to_hex(tuple(_linear_to_srgb(max(0.0, min(1.0, ok_l))) for _ in range(3)))


def scale(value, dark=False):
    """A colour -> its twelve steps, step 1 nearest the page's ground.

    `dark` flips the lightness targets, so step 1 is the darkest and the
    roles below mean the same thing either way round. That is the whole
    reason the scale is indexed rather than named by lightness: a rule
    that asks for "the hairline step" must not have to know which way up
    the page is.
    """
    hcl = to_oklch(value)
    if not hcl:
        return []
    _, chroma, hue = hcl
    out = []
    for i, target in enumerate(LIGHT_STEPS):
        ok_l = DARK_STEPS[i] if dark else target
        out.append(from_oklch(ok_l, chroma * CHROMA_SHAPE[i], hue))
    return out


def relative_luminance(value):
    rgb = _hex_to_rgb(value)
    if not rgb:
        return 0.0
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def step_that_reads(value, on, need=4.5, dark=False):
    """The palest step of `value` that still reads on `on`.

    One pass over a scale that is already ordered by lightness, rather
    than a search that mixes a new colour each time it fails. The answer
    is a step INDEX, so the same call gives the same role on every hue
    and the page cannot end up with one colour chosen more carefully
    than another.

    Walks FROM the ground end outwards and takes the first step that
    passes, so the answer is the quietest colour that still reads. The
    direction matters: walking from the far end returns the darkest step
    every time, which made the 4.5:1 role and the 7:1 role the same
    colour and left the page with no quiet text at all.

    The far end is the floor, so this cannot fail to return something.
    """
    steps = scale(value, dark=dark)
    if not steps:
        return ""
    for hex_value in steps:
        if contrast(hex_value, on) >= need:
            return hex_value
    return steps[-1]


def nudge(value, amount):
    """Move a colour along LIGHTNESS by `amount`, keeping its hue.

    What a band and a hairline are: the ground, stepped. Doing it in
    OKLab rather than by mixing towards white means the step is the same
    SIZE on every hue -- mixing 5% towards white moves a pale yellow
    almost not at all and a deep blue a long way, which is why bands
    used to read as obvious on some templates and invisible on others.
    """
    hcl = to_oklch(value)
    if not hcl:
        return value
    ok_l, chroma, hue = hcl
    return from_oklch(max(0.0, min(1.0, ok_l + amount)), chroma, hue)


def is_dark(value):
    """Which way up a page sitting on this colour is.

    Measured -- whichever of near-white or near-black reads better on it
    -- rather than thresholded, because a mid ground has no obvious side
    and picking one by a cutoff is how a grey-blue photograph turned
    into a navy page.
    """
    return contrast("#ffffff", value) > contrast("#111111", value)


def step_at_contrast(base, target, towards=""):
    """The step of `base`'s own scale that sits `target`:1 away from it.

    A band and a hairline are not text and have no reading threshold --
    what they have is a JOB: a band must be visibly a different surface
    without becoming a second page, a hairline must be findable. Both are
    contrast ratios, and asking for a ratio works at either end of the
    range where asking for a lightness delta does not: +0.045 in OKLab L
    is a clear step away from a cream page and is still pure black when
    the page is pure black.

    `towards` is which SIDE of the ground to step -- normally the ink.
    Without it a mid ground steps whichever way its scale happens to
    run: a grey-blue page took a near-white hairline, which is invisible
    against the white cards sitting on it. Stepping towards the text is
    the rule that cannot collide with a card, because a card is on the
    other side by definition.

    Nearest match rather than first-over, so a target lands where it was
    aimed instead of overshooting to whatever step happened to clear it.
    """
    here = relative_luminance(base)
    candidates = [c for c in scale(base, dark=False) + scale(base, dark=True) if c]
    if towards:
        want_darker = relative_luminance(towards) < here
        side = [c for c in candidates
                if (relative_luminance(c) < here) == want_darker]
        candidates = side or candidates
    if not candidates:
        return base
    return min(candidates, key=lambda hex_value: abs(contrast(hex_value, base) - target))
