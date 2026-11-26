"""A colour an owner picks for one item, kept LINKED to the palette.

Colour controls used to store the hex they showed. A banner or card then
kept those exact colours whatever palette was applied afterwards -- and a
colour input cannot be empty, so changing only the text size also saved
the picker's default white. A choice is now a role ("primary"), stored as
a CSS variable, so it follows every palette change. "" means automatic:
nothing is stored and the theme decides. A custom hex is still allowed,
and "keep" means a stored value these controls cannot name.
"""
import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

#  role -> (the colour, what reads on it)
ROLES = {
    "primary": ("var(--primary)", "var(--primary-on, #fff)"),
    "secondary": ("var(--secondary)", "var(--secondary-on, #111)"),
    "accent": ("var(--accent)", "var(--accent-on, #fff)"),
    "light": ("var(--site-tint, #f5f5f5)", "var(--site-ink, #111)"),
    "dark": ("var(--primary-900, #1c1c1c)", "#fff"),
}
LABELS = (("", "Auto"), ("primary", "Primary"), ("secondary", "Secondary"),
          ("accent", "Accent"), ("light", "Light"), ("dark", "Dark"))


def css_colour(choice, custom=""):
    """The CSS to store for a choice, or "" for automatic / unusable."""
    if choice in ROLES:
        return ROLES[choice][0]
    custom = (custom or "").strip()
    if choice == "custom" and HEX_RE.match(custom):
        return custom.lower()
    return ""


def ink_on(choice, custom=""):
    """The text colour that reads on a chosen background, or ""."""
    if choice in ROLES:
        return ROLES[choice][1]
    if css_colour(choice, custom):
        from .palette import readable_on
        return readable_on(custom.strip())
    return ""


def with_opacity(colour, percent):
    percent = max(0, min(100, 45 if percent is None else percent))
    return "color-mix(in srgb, %s %d%%, transparent)" % (colour, percent)


def read(value):
    """(choice, hex, opacity or None) from a stored CSS value."""
    value = (value or "").strip()
    opacity = None
    mix = re.match(r"color-mix\(in srgb,\s*(.+?)\s+(\d+)%,\s*transparent\)$", value)
    if mix:
        value, opacity = mix.group(1), int(mix.group(2))
    rgba = re.match(r"rgba?\((\d+),(\d+),(\d+)(?:,([\d.]+))?\)$", value.replace(" ", ""))
    if rgba:
        value = "#%02x%02x%02x" % tuple(int(rgba.group(i)) for i in (1, 2, 3))
        if rgba.group(4) is not None:
            opacity = round(float(rgba.group(4)) * 100)
    for role, (colour, _) in ROLES.items():
        if value == colour:
            return role, "", opacity
    if HEX_RE.match(value):
        return "custom", value.lower(), opacity
    return "", "", opacity
