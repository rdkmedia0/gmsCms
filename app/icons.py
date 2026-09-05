"""
Menu/text icons: a curated emoji set — covers the common functional cases
(home, phone, email, location...) plus a broad general-purpose emoji
collection (smileys, people, animals, food, activities, travel, objects,
symbols) similar to a phone's SMS/messaging emoji keyboard — without
needing any bundled art, upload handling, or per-style color treatment the
way the earlier SVG-icon-set design did. Chosen via a visual grid, never
typed — see icon_picker.html and its JS wiring in inline-editor.js.

An earlier design used bundled SVG icon sets, which is why these
functions once carried source/style parameters and why a set of Bootstrap
SVGs sat under static/icons/. Both are gone: nothing read the parameters,
nothing referenced the files, and carrying a removed feature's shape
around is exactly the drift CLAUDE.md exists to prevent.
"""
import os
from html import escape as html_escape

# Grouped for readability/maintenance only — icon_choices_for() flattens
# this into one continuous list (the picker grid has no category headers,
# just a bigger scrollable grid), so item order here is the order shown.
EMOJI_GROUPS = [
    ("Common", [
        ("🏠", "Home"), ("ℹ️", "About"), ("🛠️", "Services"), ("📰", "Blog / News"),
        ("📞", "Phone"), ("✉️", "Email"), ("📍", "Location"), ("🛒", "Shop"),
        ("📅", "Calendar"), ("🔍", "Search"), ("💬", "Chat"), ("👤", "Account"),
        ("🔗", "Link"), ("📷", "Photo"), ("🎬", "Video"), ("📄", "Page"),
    ]),
    ("Smileys & Emotion", [
        ("😀", "Grinning"), ("😃", "Grinning big eyes"), ("😄", "Grinning smiling eyes"),
        ("😁", "Beaming"), ("😆", "Laughing"), ("😅", "Sweat smile"), ("🤣", "Rolling on floor"),
        ("😂", "Joy"), ("🙂", "Slight smile"), ("🙃", "Upside down"), ("😉", "Wink"),
        ("😊", "Smiling eyes"), ("😇", "Halo"), ("🥰", "Hearts"), ("😍", "Heart eyes"),
        ("🤩", "Star struck"), ("😘", "Kiss"), ("😋", "Yum"), ("😛", "Tongue out"),
        ("😜", "Winky tongue"), ("🤪", "Zany"), ("😝", "Squint tongue"), ("🤑", "Money mouth"),
        ("🤗", "Hugging"), ("🤭", "Hand over mouth"), ("🤫", "Shushing"), ("🤔", "Thinking"),
        ("😐", "Neutral"), ("😑", "Expressionless"), ("😶", "No mouth"), ("😏", "Smirk"),
        ("😒", "Unamused"), ("🙄", "Eye roll"), ("😬", "Grimace"), ("🤥", "Lying"),
        ("😌", "Relieved"), ("😔", "Pensive"), ("😪", "Sleepy"), ("🤤", "Drooling"),
        ("😴", "Sleeping"), ("😷", "Mask"), ("🤒", "Thermometer"), ("🤕", "Bandage"),
        ("🤢", "Nauseated"), ("🤮", "Vomiting"), ("🥵", "Hot"), ("🥶", "Cold"),
        ("😵", "Dizzy"), ("🤯", "Mind blown"), ("🥳", "Party"), ("😎", "Sunglasses"),
        ("🤓", "Nerd"), ("🧐", "Monocle"), ("😕", "Confused"), ("😟", "Worried"),
        ("🙁", "Frown"), ("😮", "Open mouth"), ("😯", "Hushed"), ("😲", "Astonished"),
        ("😳", "Flushed"), ("🥺", "Pleading"), ("😦", "Frowning open mouth"), ("😧", "Anguished"),
        ("😨", "Fearful"), ("😰", "Anxious sweat"), ("😥", "Sad relieved"), ("😢", "Crying"),
        ("😭", "Sobbing"), ("😱", "Screaming"), ("😖", "Confounded"), ("😣", "Persevering"),
        ("😞", "Disappointed"), ("😓", "Downcast sweat"), ("😩", "Weary"), ("😫", "Tired"),
        ("🥱", "Yawning"), ("😤", "Triumph"), ("😡", "Pouting"), ("😠", "Angry"),
        ("🤬", "Cursing"), ("👿", "Angry devil"), ("💀", "Skull"), ("👻", "Ghost"),
        ("👽", "Alien"), ("🤖", "Robot"), ("💩", "Poop"), ("🤡", "Clown"),
    ]),
    ("People & Body", [
        ("👋", "Wave"), ("🤚", "Raised hand"), ("✋", "Hand"), ("🖖", "Vulcan"),
        ("👌", "OK"), ("🤏", "Pinch"), ("✌️", "Peace"), ("🤞", "Crossed fingers"),
        ("🤟", "Love you"), ("🤘", "Rock on"), ("👍", "Thumbs up"), ("👎", "Thumbs down"),
        ("👊", "Fist bump"), ("✊", "Raised fist"), ("👏", "Clap"), ("🙌", "Raise hands"),
        ("🙏", "Pray"), ("🤝", "Handshake"), ("💪", "Muscle"), ("🦾", "Mechanical arm"),
        ("🖐️", "Hand splayed"), ("👆", "Point up"), ("👇", "Point down"), ("👈", "Point left"),
        ("👉", "Point right"), ("☝️", "Index up"), ("✍️", "Writing"), ("💅", "Nail polish"),
        ("👂", "Ear"), ("👃", "Nose"), ("🧠", "Brain"), ("👀", "Eyes"), ("👁️", "Eye"),
        ("👶", "Baby"), ("🧒", "Child"), ("👦", "Boy"), ("👧", "Girl"), ("🧑", "Person"),
        ("👨", "Man"), ("👩", "Woman"), ("🧓", "Older person"), ("👴", "Old man"),
        ("👵", "Old woman"), ("👮", "Officer"), ("🕵️", "Detective"), ("👷", "Worker"),
        ("💂", "Guard"), ("🥷", "Ninja"), ("👩‍⚕️", "Health worker"), ("👨‍🍳", "Chef"),
        ("👩‍🎓", "Graduate"), ("👨‍🏫", "Teacher"), ("👩‍💻", "Coder"), ("👨‍🎨", "Artist"),
        ("🦸", "Superhero"), ("🧙", "Mage"), ("🧑‍🚀", "Astronaut"), ("🧑‍🚒", "Firefighter"),
    ]),
    ("Animals & Nature", [
        ("🐶", "Dog"), ("🐱", "Cat"), ("🐭", "Mouse"), ("🐹", "Hamster"), ("🐰", "Rabbit"),
        ("🦊", "Fox"), ("🐻", "Bear"), ("🐼", "Panda"), ("🐨", "Koala"), ("🐯", "Tiger"),
        ("🦁", "Lion"), ("🐮", "Cow"), ("🐷", "Pig"), ("🐸", "Frog"), ("🐵", "Monkey"),
        ("🐔", "Chicken"), ("🐧", "Penguin"), ("🐦", "Bird"), ("🦉", "Owl"), ("🦄", "Unicorn"),
        ("🐝", "Bee"), ("🦋", "Butterfly"), ("🐢", "Turtle"), ("🐍", "Snake"), ("🐳", "Whale"),
        ("🐬", "Dolphin"), ("🐠", "Fish"), ("🐙", "Octopus"), ("🦀", "Crab"), ("🐴", "Horse"),
        ("🦓", "Zebra"), ("🦒", "Giraffe"), ("🐘", "Elephant"), ("🦍", "Gorilla"), ("🐺", "Wolf"),
        ("🐗", "Boar"), ("🐴", "Horse face"), ("🌵", "Cactus"), ("🌲", "Tree"), ("🌳", "Deciduous tree"),
        ("🌴", "Palm tree"), ("🌱", "Seedling"), ("🌿", "Herb"), ("🍀", "Clover"), ("🎍", "Bamboo"),
        ("🎋", "Tanabata tree"), ("🍃", "Leaves"), ("🍂", "Fallen leaf"), ("🌼", "Blossom"),
        ("🌸", "Cherry blossom"), ("🌺", "Hibiscus"), ("🌻", "Sunflower"), ("🌹", "Rose"),
        ("🌷", "Tulip"), ("💐", "Bouquet"), ("🍄", "Mushroom"), ("🌍", "Globe"), ("☀️", "Sun"),
        ("🌙", "Moon"), ("⭐", "Star"), ("🌟", "Glowing star"), ("⚡", "Lightning"),
        ("🔥", "Fire"), ("🌈", "Rainbow"), ("☁️", "Cloud"), ("❄️", "Snowflake"), ("💧", "Droplet"),
        ("🌊", "Wave"),
    ]),
    ("Food & Drink", [
        ("🍏", "Green apple"), ("🍎", "Red apple"), ("🍌", "Banana"), ("🍉", "Watermelon"),
        ("🍇", "Grapes"), ("🍓", "Strawberry"), ("🍒", "Cherries"), ("🍑", "Peach"),
        ("🍍", "Pineapple"), ("🥭", "Mango"), ("🥝", "Kiwi"), ("🍅", "Tomato"), ("🥑", "Avocado"),
        ("🥦", "Broccoli"), ("🥕", "Carrot"), ("🌽", "Corn"), ("🥔", "Potato"), ("🍞", "Bread"),
        ("🥐", "Croissant"), ("🧀", "Cheese"), ("🍗", "Chicken leg"), ("🥩", "Steak"),
        ("🍔", "Burger"), ("🍟", "Fries"), ("🍕", "Pizza"), ("🌭", "Hot dog"), ("🥪", "Sandwich"),
        ("🌮", "Taco"), ("🌯", "Burrito"), ("🍜", "Ramen"), ("🍝", "Pasta"), ("🍣", "Sushi"),
        ("🍱", "Bento"), ("🍦", "Soft serve"), ("🍩", "Donut"), ("🍪", "Cookie"), ("🎂", "Cake"),
        ("🍰", "Shortcake"), ("🧁", "Cupcake"), ("🍫", "Chocolate"), ("🍬", "Candy"), ("🍭", "Lollipop"),
        ("☕", "Coffee"), ("🍵", "Tea"), ("🧃", "Juice box"), ("🥤", "Soda"), ("🍺", "Beer"),
        ("🍷", "Wine"), ("🍹", "Cocktail"), ("🍾", "Champagne"), ("🍽️", "Fork & knife"),
    ]),
    ("Activities & Sports", [
        ("⚽", "Soccer"), ("🏀", "Basketball"), ("🏈", "Football"), ("⚾", "Baseball"),
        ("🎾", "Tennis"), ("🏐", "Volleyball"), ("🏉", "Rugby"), ("🎱", "8 ball"),
        ("🏓", "Ping pong"), ("🏸", "Badminton"), ("🥊", "Boxing"), ("🥋", "Martial arts"),
        ("⛳", "Golf"), ("🏹", "Archery"), ("🎣", "Fishing"), ("🥏", "Frisbee"), ("🛹", "Skateboard"),
        ("⛸️", "Ice skate"), ("🎿", "Skiing"), ("🏂", "Snowboard"), ("🏋️", "Weightlifting"),
        ("🤸", "Cartwheel"), ("🧗", "Climbing"), ("🚴", "Cycling"), ("🏊", "Swimming"),
        ("🏆", "Trophy"), ("🥇", "Gold medal"), ("🥈", "Silver medal"), ("🥉", "Bronze medal"),
        ("🎖️", "Medal"), ("🎮", "Game controller"), ("🕹️", "Joystick"), ("🎲", "Dice"),
        ("🧩", "Puzzle"), ("🎯", "Dart"), ("🎳", "Bowling"), ("🎨", "Palette"), ("🎭", "Masks"),
        ("🎤", "Microphone"), ("🎧", "Headphones"), ("🎸", "Guitar"), ("🎹", "Piano"),
        ("🥁", "Drum"), ("🎺", "Trumpet"), ("🎻", "Violin"), ("🎬", "Clapper"), ("🎪", "Circus"),
        ("🎉", "Party"), ("🎊", "Confetti"), ("🎈", "Balloon"), ("🎁", "Gift"), ("🏅", "Sports medal"),
    ]),
    ("Travel & Places", [
        ("🚗", "Car"), ("🚕", "Taxi"), ("🚙", "SUV"), ("🚌", "Bus"), ("🚎", "Trolleybus"),
        ("🏎️", "Race car"), ("🚓", "Police car"), ("🚑", "Ambulance"), ("🚒", "Fire truck"),
        ("🚚", "Delivery truck"), ("🚲", "Bicycle"), ("🛵", "Scooter"), ("🏍️", "Motorcycle"),
        ("🚂", "Train"), ("🚆", "Train (electric)"), ("🚇", "Metro"), ("🚊", "Tram"),
        ("✈️", "Airplane"), ("🛫", "Departure"), ("🛬", "Arrival"), ("🚀", "Rocket"),
        ("🛸", "UFO"), ("🚁", "Helicopter"), ("⛵", "Sailboat"), ("🚤", "Speedboat"),
        ("🛳️", "Ship"), ("⚓", "Anchor"), ("🚦", "Traffic light"), ("🚧", "Construction"),
        ("🗺️", "Map"), ("🗽", "Statue of Liberty"), ("🗼", "Tower"), ("🏰", "Castle"),
        ("🏯", "Japanese castle"), ("🏟️", "Stadium"), ("🎡", "Ferris wheel"), ("🎢", "Roller coaster"),
        ("⛱️", "Beach umbrella"), ("🏖️", "Beach"), ("🏝️", "Island"), ("🏔️", "Mountain"),
        ("🗻", "Mount Fuji"), ("🌋", "Volcano"), ("🏕️", "Camping"), ("🏡", "House garden"),
        ("🏢", "Office"), ("🏥", "Hospital"), ("🏫", "School"), ("🏛️", "Bank / museum"),
        ("⛪", "Church"), ("🕌", "Mosque"), ("🛕", "Temple"), ("🌆", "Cityscape"), ("🌃", "Night city"),
    ]),
    ("Objects & Tech", [
        ("💡", "Idea"), ("🔦", "Flashlight"), ("🕯️", "Candle"), ("📱", "Mobile phone"),
        ("💻", "Laptop"), ("🖥️", "Desktop"), ("⌨️", "Keyboard"), ("🖱️", "Mouse"),
        ("🖨️", "Printer"), ("📷", "Camera"), ("📹", "Video camera"), ("📺", "TV"),
        ("📻", "Radio"), ("🎙️", "Studio mic"), ("⏰", "Alarm clock"), ("⏱️", "Stopwatch"),
        ("⌚", "Watch"), ("📡", "Satellite dish"), ("🔋", "Battery"), ("🔌", "Plug"),
        ("💾", "Floppy disk"), ("💿", "CD"), ("📀", "DVD"), ("🧮", "Abacus"), ("📚", "Books"),
        ("📖", "Open book"), ("📝", "Memo"), ("📎", "Paperclip"), ("📌", "Pin"), ("📍", "Round pin"),
        ("✂️", "Scissors"), ("🖊️", "Pen"), ("🖋️", "Fountain pen"), ("✏️", "Pencil"),
        ("🔒", "Locked"), ("🔓", "Unlocked"), ("🔑", "Key"), ("🗝️", "Old key"), ("🔨", "Hammer"),
        ("🛠️", "Tools"), ("⚙️", "Gear"), ("🧰", "Toolbox"), ("🧲", "Magnet"), ("⚗️", "Alembic"),
        ("🔬", "Microscope"), ("🔭", "Telescope"), ("📦", "Package"), ("📮", "Postbox"),
        ("✉️", "Envelope"), ("📧", "Email"), ("📨", "Incoming mail"), ("📤", "Outbox"),
        ("💰", "Money bag"), ("💵", "Dollar bill"), ("💳", "Credit card"), ("🧾", "Receipt"),
        ("🛒", "Shopping cart"), ("🎒", "Backpack"), ("👓", "Glasses"), ("🕶️", "Sunglasses"),
    ]),
    ("Symbols", [
        ("❤️", "Heart"), ("🧡", "Orange heart"), ("💛", "Yellow heart"), ("💚", "Green heart"),
        ("💙", "Blue heart"), ("💜", "Purple heart"), ("🖤", "Black heart"), ("🤍", "White heart"),
        ("🤎", "Brown heart"), ("💔", "Broken heart"), ("💕", "Two hearts"), ("💞", "Revolving hearts"),
        ("💓", "Beating heart"), ("💗", "Growing heart"), ("💖", "Sparkling heart"), ("💘", "Cupid heart"),
        #  The legal marks: a footer that carries a copyright line needs
        #  the character for it, and typing © is exactly the sort of thing
        #  a picker exists to save somebody doing.
        ("©", "Copyright"), ("®", "Registered"), ("™", "Trademark"),
        ("💝", "Heart gift"), ("✅", "Check mark"), ("☑️", "Checkbox"), ("✔️", "Tick"),
        ("❌", "Cross mark"), ("❎", "Cross box"), ("➕", "Plus"), ("➖", "Minus"), ("➗", "Divide"),
        ("✖️", "Multiply"), ("♾️", "Infinity"), ("‼️", "Double exclamation"), ("❗", "Exclamation"),
        ("❓", "Question"), ("💯", "100"), ("🔔", "Bell"), ("🔕", "Bell off"), ("📢", "Loudspeaker"),
        ("📣", "Megaphone"), ("🔊", "Loud volume"), ("🔇", "Muted"), ("🚫", "No entry"),
        ("⛔", "No entry sign"), ("⚠️", "Warning"), ("🚸", "Children crossing"), ("♻️", "Recycle"),
        ("✳️", "Sparkle asterisk"), ("✴️", "8 point star"), ("💠", "Diamond dot"), ("🔰", "Beginner"),
        ("🔱", "Trident"), ("⭐", "Star"), ("🌟", "Glow star"), ("💫", "Dizzy star"), ("🔴", "Red circle"),
        ("🟠", "Orange circle"), ("🟡", "Yellow circle"), ("🟢", "Green circle"), ("🔵", "Blue circle"),
        ("🟣", "Purple circle"), ("⚫", "Black circle"), ("⚪", "White circle"), ("🔺", "Red triangle"),
    ]),
]

#  business rather than a column on the page that used to be the blog.

MEDIA_TYPES = ("youtube", "video", "audio")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".ogv", ".mov")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac")
FILE_DISPLAYS = ("card", "button", "text-link", "icon")


BLOCK_TAGS = {"div", "section", "article", "figure", "ul", "ol"}
INTERACTIVE_TAGS = {"table", "iframe", "script", "form"}

# Class-name fragments that signal real interactive/dynamic behavior (a JS
# widget, not just decorative markup) — this is content a "plugin"-style
# html section is actually meant for, since there's no static/local
# equivalent tool that can reproduce it.
INTERACTIVE_CLASS_HINTS = (
    "counter", "typing", "swiper", "splide", "slider", "carousel",
    "accordion", "tabs-", "-tab", "countdown", "marquee", "lightbox",
)


def _has_interactive_content(node):
    if node.find(list(INTERACTIVE_TAGS)):
        return True
    for el in node.find_all(class_=True):
        classes = " ".join(el.get("class") or [])
        if any(hint in classes for hint in INTERACTIVE_CLASS_HINTS):
            return True
    return False


def _significant_children(node):
    return [c for c in node.contents if getattr(c, "name", None)]


def _descend_single_wrappers(nodes):
    """Follow a chain of single-child wrapper elements (a chunk can nest a
    pattern in 2-3 layers of purely-layout divs) down to the level where the
    real content actually branches, so classification below looks at the
    meaningful siblings instead of always seeing "one wrapper div"."""
    level = nodes
    while len(level) == 1 and level[0].name in BLOCK_TAGS:
        children = _significant_children(level[0])
        if not children:
            break
        level = children
    return level


def _is_image_ish(node):
    if node.name in ("img", "figure"):
        return True
    if node.name == "a" and node.find("img") and not node.get_text(strip=True):
        return True
    return False


def _classify_layout_chunk(html_chunk, _depth=0):
    """
    Translate one raw HTML chunk (from the AI Theme Generator or a package's
    page content) into native CMS sections (text/image/columns/banner/card)
    instead of dumping it as an opaque 'html' blob — so it's editable
    through the normal section tools (image size/shape pickers, WYSIWYG
    toolbar, column editing) like any section the admin created by hand.

    A chunk can nest arbitrarily deeply (a heading, then a sub-heading, then
    a row of columns, all wrapped in one outer group) — a single top-level
    shape check can't classify that as a whole, so when nothing simple
    matches, this recurses into each top-level piece and classifies them
    independently, effectively flattening one chunk into several ordered
    native sections. Only content that's genuinely atomic and interactive
    (real JS widgets: sliders, counters, forms, embeds — see
    INTERACTIVE_CLASS_HINTS) falls back to 'html', since there's no local
    tool equivalent for those.

    Returns a LIST of dicts of the fields to insert into `sections`.
    """
    soup = BeautifulSoup(html_chunk or "", "html.parser")
    top_level = _significant_children(soup)
    if not top_level:
        return []

    # A whole chunk that translated straight to a Banner or Card — tag it
    # with that tool's own type immediately, before the generic text/columns
    # rules below get a chance to reclassify it as something else (a Banner
    # with little text and no <img> would otherwise match the Text rule).
    if len(top_level) == 1 and "cms-banner" in (top_level[0].get("class") or []):
        return [{"type": "banner", "title": "", "content": html_chunk}]
    if len(top_level) == 1 and "cms-card-shape" in (top_level[0].get("class") or []):
        return [{"type": "card", "title": "", "content": html_chunk}]

    has_interactive = _has_interactive_content(soup)

    # A chunk can be wrapped in 1-3 layers of purely-layout <div>s — follow
    # those down to where the real content branches.
    level = _descend_single_wrappers(top_level)
    imgs = soup.find_all("img")
    text_len = len(soup.get_text(strip=True))

    # A chunk that's essentially just one image (optionally linked).
    if not has_interactive and len(imgs) == 1 and text_len < 20:
        img = imgs[0]
        link = img.find_parent("a")
        return [{
            "type": "image",
            "title": img.get("alt", "") or "",
            "content": img.get("src", "") or "",
            "link_url": link.get("href", "") if link else "",
        }]

    # A row of nothing but images (a logo strip / simple gallery, any
    # count >= 2, however deeply it was wrapped) — one Columns section,
    # one image per column. Columns cells already hold raw HTML (same as
    # a hand-built Columns section can), so this doesn't need to be
    # interactive-content-free the way the plain Text rule below does.
    if len(level) >= 2 and all(_is_image_ish(c) for c in level):
        return [{
            "type": "columns",
            "title": "",
            "content": json.dumps({"columns": [str(c).strip() for c in level]}),
        }]

    # 2-6 similarly-structured sibling blocks (a WordPress "columns"/"group"
    # pattern) — map onto the native Columns section instead of leaving it
    # as opaque raw HTML. Checked before the Text fallback below, since a
    # columns/group wrapper with 0-1 images in it would otherwise also
    # match that broader rule. Not gated on has_interactive for the same
    # reason as the image row above — any widget nested inside one cell
    # just becomes part of that cell's raw HTML, same as manual editing.
    if 2 <= len(level) <= 6 and all((c.name or "") in BLOCK_TAGS for c in level):
        return [{
            "type": "columns",
            "title": "",
            "content": json.dumps({"columns": [str(c).strip() for c in level]}),
        }]

    # Only text-ish tags, no complex/interactive markup — a plain Text
    # section, not raw HTML. This also covers the very common "one image
    # plus a heading/paragraph" pattern (e.g. a WP media-and-text block):
    # up to one <img> is fine here too, since the WYSIWYG toolbar already
    # supports inline images directly (its Insert Image button), so an
    # embedded <img> doesn't need the dedicated Image section type — that's
    # only for a chunk that's *essentially just* the image (caught above).
    # Excludes "cover" blocks (background image/color + overlay via
    # absolutely-positioned children, tagged .cms-banner and already
    # returned above) — those aren't plain text and the WYSIWYG editor's
    # contenteditable could mangle their nested markup on save, so they
    # stay raw HTML, editable only via "Edit raw HTML".
    if not has_interactive and len(imgs) <= 1 and all(
        (c.name or "") not in INTERACTIVE_TAGS for c in top_level
    ):
        return [{"type": "text", "title": "", "content": str(soup).strip()}]

    # Nothing simple matched as a whole (e.g. a heading + sub-heading
    # followed by a columns block, all in one wrapper) — split into its
    # meaningful pieces (post single-wrapper-descend, so a chunk that's one
    # outer <div> around several real children still splits on those
    # children instead of immediately bailing out) and classify each
    # independently, rather than giving up and keeping the whole thing as
    # one raw HTML blob. Bounded depth so a pathological chunk can't
    # recurse forever.
    if len(level) > 1 and _depth < 6:
        results = []
        for child in level:
            piece = str(child).strip()
            if piece:
                results.extend(_classify_layout_chunk(piece, _depth + 1))
        if results:
            return results

    return [{"type": "html", "title": "", "content": html_chunk}]



BREADCRUMB_SIZES = ("small", "medium", "large")
BREADCRUMB_STYLES = ("plain", "uppercase", "pill")
BANNER_SHAPES = ("none", "rounded", "circle", "square", "diamond", "hexagon", "star")
CONTACT_FIELDS = ("phone", "email", "website", "facebook", "instagram", "x")


def _breadcrumb_starter_html(size, style):
    size = size if size in BREADCRUMB_SIZES else "medium"
    style = style if style in BREADCRUMB_STYLES else "plain"
    return f'<nav class="cms-breadcrumb cms-breadcrumb-{size} cms-breadcrumb-style-{style}">%%CMS_BREADCRUMB%%</nav>'


DIVIDER_STYLES = ("solid", "dashed", "dotted", "double")
DIVIDER_WIDTHS = ("narrow", "medium", "full")
DIVIDER_SPACINGS = ("small", "medium", "large")


def _divider_starter_html(style, width, spacing, color):
    """A plain <hr> with a marker class + style/width/spacing classes, and
    an optional inline color — same in-place-reconfigure shape as
    Breadcrumb/Banner (placed with defaults, then adjusted via its own
    config form, never through the raw HTML editor)."""
    style = style if style in DIVIDER_STYLES else "solid"
    width = width if width in DIVIDER_WIDTHS else "medium"
    spacing = spacing if spacing in DIVIDER_SPACINGS else "medium"
    color = (color or "").strip()
    color_attr = f' style="border-color:{color}"' if color and re.match(r"^#[0-9a-fA-F]{6}$", color) else ""
    return (
        f'<hr class="cms-content-divider cms-divider-{style} cms-divider-{width} '
        f'cms-divider-spacing-{spacing}"{color_attr}>'
    )


BANNER_ATTACHMENTS = ("scroll", "fixed")


# Real brand marks (single-path monochrome, 0 0 24 24 viewBox) instead of
# the letter/initials placeholders ("f", "IG", "X") this used to fall back
# to — those read as an unfinished/broken icon font, not an actual icon.
# Sourced from Simple Icons (simpleicons.org), CC0-licensed — safe to
# embed and ship, unlike pulling a random dafont icon font whose license
# usually only covers personal use, not redistribution in a product.
SOCIAL_ICON_PATHS = {
    "facebook": "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z",
    "instagram": "M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077",
    "x": "M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z",
    "youtube": "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z",
    "linkedin": "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
    "tiktok": "M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z",
    "pinterest": "M12.017 0C5.396 0 .029 5.367.029 11.987c0 5.079 3.158 9.417 7.618 11.162-.105-.949-.199-2.403.041-3.439.219-.937 1.406-5.957 1.406-5.957s-.359-.72-.359-1.781c0-1.663.967-2.911 2.168-2.911 1.024 0 1.518.769 1.518 1.688 0 1.029-.653 2.567-.992 3.992-.285 1.193.6 2.165 1.775 2.165 2.128 0 3.768-2.245 3.768-5.487 0-2.861-2.063-4.869-5.008-4.869-3.41 0-5.409 2.562-5.409 5.199 0 1.033.394 2.143.889 2.741.099.12.112.225.085.345-.09.375-.293 1.199-.334 1.363-.053.225-.172.271-.401.165-1.495-.69-2.433-2.878-2.433-4.646 0-3.776 2.748-7.252 7.92-7.252 4.158 0 7.392 2.967 7.392 6.923 0 4.135-2.607 7.462-6.233 7.462-1.214 0-2.354-.629-2.758-1.379l-.749 2.848c-.269 1.045-1.004 2.352-1.498 3.146 1.123.345 2.306.535 3.55.535 6.607 0 11.985-5.365 11.985-11.987C23.97 5.39 18.592.026 11.985.026L12.017 0z",
    "github": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.014 2.898-.014 3.293 0 .322.216.694.825.576C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    "imdb": "M22.3781 0H1.6218C.7411.0583.0587.7437.0018 1.5953l-.001 20.783c.0585.8761.7125 1.543 1.5559 1.6191A.337.337 0 0 0 1.6016 24h20.7971a.4579.4579 0 0 0 .0437-.002c.8727-.0768 1.5568-.8271 1.5568-1.7085V1.7098c0-.8914-.696-1.6416-1.584-1.7078A.3294.3294 0 0 0 22.3781 0zm0 .496a1.2144 1.2144 0 0 1 1.1252 1.2139v20.5797c0 .6377-.4875 1.1602-1.1045 1.2145H1.6016c-.5967-.0543-1.0645-.5297-1.1053-1.1258V1.6284C.5371 1.0185 1.0184.5364 1.6217.496h20.7564zM4.7954 8.2603v7.3636H2.8899V8.2603h1.9055zm6.5367 0v7.3636H9.6707v-4.9704l-.6711 4.9704H7.813l-.6986-4.8618-.0066 4.8618h-1.668V8.2603h2.468c.0748.4476.1492.9694.2307 1.5734l.2712 1.8713.4407-3.4447h2.4817zm2.9772 1.3289c.0742.0404.122.108.1417.2034.0279.0953.0345.3118.0345.6442v2.8548c0 .4881-.0345.7867-.0955.8954-.0609.1152-.2304.1695-.5018.1695V9.5211c.204 0 .3457.0205.4211.0681zm-.0211 6.0347c.4543 0 .8006-.0265 1.0245-.0742.2304-.0477.4204-.1357.5694-.2648.1556-.1218.2642-.298.3251-.5219.0611-.2238.1021-.6648.1021-1.3224v-2.5832c0-.6986-.0271-1.1668-.0742-1.4039-.041-.237-.1431-.4543-.3126-.6437-.1695-.1973-.4198-.3324-.7456-.421-.3191-.0808-.8542-.1285-1.7694-.1285h-1.4244v7.3636h2.3051zm5.14-1.7827c0 .3523-.0199.5762-.0544.6708-.033.0947-.1894.1424-.3046.1424-.1086 0-.19-.0477-.2238-.1351-.041-.0887-.0609-.2986-.0609-.6238v-1.9469c0-.3324.0199-.5423.0543-.6237.0338-.0808.1086-.122.2171-.122.1153 0 .2709.0412.3114.1425.041.0947.0609.2986.0609.6032v1.8926zm-2.4747-5.5809v7.3636h1.7157l.1152-.4675c.1556.1894.3251.3324.5152.4271.1828.0881.4608.1357.678.1357.3047 0 .5629-.0748.7802-.237.2165-.1562.3589-.3462.4198-.5628.0543-.2173.0887-.543.0887-.9841v-2.0675c0-.4409-.0139-.7324-.0344-.8681-.0199-.1357-.0742-.2781-.1695-.4204-.1021-.1425-.2437-.251-.4272-.3325-.1834-.0742-.3999-.1152-.6576-.1152-.2172 0-.4952.0477-.6846.1285-.1835.0887-.353.2238-.5086.4007V8.2603h-1.8309z",
}


#  Each brand's own colour, from Simple Icons (the same source as the
#  marks). A brand mark is recognised BY its colour as much as its shape
#  -- LinkedIn blue, YouTube red -- so a chromatic brand is drawn in its
#  own colour rather than the site's, which is the convention everywhere
#  these appear and reads on a light card or a dark band alike.
#
#  The MONOCHROME brands -- X, TikTok, GitHub -- are deliberately absent.
#  Their own guidelines are "black OR white, whichever the background
#  needs", so a fixed near-black disappears on a dark ground. Left out,
#  they fall through to currentColor in render_icon, which is dark on a
#  light surface and light on a dark one -- exactly the black/white rule
#  those brands ask for, and the fix for a dark mark on a dark band.
BRAND_COLORS = {
    "facebook": "#0866FF", "instagram": "#E4405F",
    "youtube": "#FF0000", "linkedin": "#0A66C2",
    "pinterest": "#BD081C", "imdb": "#F5C518",
}


#  The brand marks are real paths, not emoji, because no emoji means
#  "Instagram" and a footer full of approximations reads as a mistake.
#  They ride in the same picker under keys of their own — render_icon
#  knows a "brand:" key draws an SVG and everything else is the character
#  itself.
BRAND_LABELS = {
    "facebook": "Facebook", "instagram": "Instagram", "x": "X",
    "youtube": "YouTube", "linkedin": "LinkedIn", "tiktok": "TikTok",
    "pinterest": "Pinterest", "github": "GitHub", "imdb": "IMDb",
}


#  Plain UI icons drawn ALWAYS in currentColor -- so they take the colour of
#  the text around them, which follows the site's theme, and recolour with
#  it. This is the theme-fitting, "font-coloured" alternative to an emoji,
#  whose OS-painted colours no palette can touch. Each is (viewBox, path) --
#  the viewBox is kept because these come from different icon sets and are
#  not all 24x24. See render_icon.
UI_ICON_PATHS = {
    "certificate": ("0 0 384 512", "M173.8 5.5c11-7.3 25.4-7.3 36.4 0L228 17.2c6 3.9 13 5.8 20.1 5.4l21.3-1.3c13.2-.8 25.6 6.4 31.5 18.2l9.6 19.1c3.2 6.4 8.4 11.5 14.7 14.7L344.5 83c11.8 5.9 19 18.3 18.2 31.5l-1.3 21.3c-.4 7.1 1.5 14.2 5.4 20.1l11.8 17.8c7.3 11 7.3 25.4 0 36.4L366.8 228c-3.9 6-5.8 13-5.4 20.1l1.3 21.3c.8 13.2-6.4 25.6-18.2 31.5l-19.1 9.6c-6.4 3.2-11.5 8.4-14.7 14.7L301 344.5c-5.9 11.8-18.3 19-31.5 18.2l-21.3-1.3c-7.1-.4-14.2 1.5-20.1 5.4l-17.8 11.8c-11 7.3-25.4 7.3-36.4 0L156 366.8c-6-3.9-13-5.8-20.1-5.4l-21.3 1.3c-13.2 .8-25.6-6.4-31.5-18.2l-9.6-19.1c-3.2-6.4-8.4-11.5-14.7-14.7L39.5 301c-11.8-5.9-19-18.3-18.2-31.5l1.3-21.3c.4-7.1-1.5-14.2-5.4-20.1L5.5 210.2c-7.3-11-7.3-25.4 0-36.4L17.2 156c3.9-6 5.8-13 5.4-20.1l-1.3-21.3c-.8-13.2 6.4-25.6 18.2-31.5l19.1-9.6C65 70.2 70.2 65 73.4 58.6L83 39.5c5.9-11.8 18.3-19 31.5-18.2l21.3 1.3c7.1 .4 14.2-1.5 20.1-5.4L173.8 5.5zM272 192a80 80 0 1 0 -160 0 80 80 0 1 0 160 0zM1.3 441.8L44.4 339.3c.2 .1 .3 .2 .4 .4l9.6 19.1c11.7 23.2 36 37.3 62 35.8l21.3-1.3c.2 0 .5 0 .7 .2l17.8 11.8c5.1 3.3 10.5 5.9 16.1 7.7l-37.6 89.3c-2.3 5.5-7.4 9.2-13.3 9.7s-11.6-2.2-14.8-7.2L74.4 455.5l-56.1 8.3c-5.7 .8-11.4-1.5-15-6s-4.3-10.7-2.1-16zm248 60.4L211.7 413c5.6-1.8 11-4.3 16.1-7.7l17.8-11.8c.2-.1 .4-.2 .7-.2l21.3 1.3c26 1.5 50.3-12.6 62-35.8l9.6-19.1c.1-.2 .2-.3 .4-.4l43.2 102.5c2.2 5.3 1.4 11.4-2.1 16s-9.3 6.9-15 6l-56.1-8.3-32.2 49.2c-3.2 5-8.9 7.7-14.8 7.2s-11-4.3-13.3-9.7z"),
    "phone": ("0 0 512 512", "M164.9 24.6c-7.7-18.6-28-28.5-47.4-23.2l-88 24C12.1 30.2 0 46 0 64C0 311.4 200.6 512 448 512c18 0 33.8-12.1 38.6-29.5l24-88c5.3-19.4-4.6-39.7-23.2-47.4l-96-40c-16.3-6.8-35.2-2.1-46.3 11.6L304.7 368C234.3 334.7 177.3 277.7 144 207.3L193.3 167c13.7-11.2 18.4-30 11.6-46.3l-40-96z"),
    "email": ("0 0 512 512", "M48 64C21.5 64 0 85.5 0 112c0 15.1 7.1 29.3 19.2 38.4L236.8 313.6c11.4 8.5 27 8.5 38.4 0L492.8 150.4c12.1-9.1 19.2-23.3 19.2-38.4c0-26.5-21.5-48-48-48L48 64zM0 176L0 384c0 35.3 28.7 64 64 64l384 0c35.3 0 64-28.7 64-64l0-208L294.4 339.2c-22.8 17.1-54 17.1-76.8 0L0 176z"),
    "address": ("0 0 384 512", "M215.7 499.2C267 435 384 279.4 384 192C384 86 298 0 192 0S0 86 0 192c0 87.4 117 243 168.3 307.2c12.3 15.3 35.1 15.3 47.4 0zM192 128a64 64 0 1 1 0 128 64 64 0 1 1 0-128z"),
    "web": ("0 0 512 512", "M352 256c0 22.2-1.2 43.6-3.3 64l-185.3 0c-2.2-20.4-3.3-41.8-3.3-64s1.2-43.6 3.3-64l185.3 0c2.2 20.4 3.3 41.8 3.3 64zm28.8-64l123.1 0c5.3 20.5 8.1 41.9 8.1 64s-2.8 43.5-8.1 64l-123.1 0c2.1-20.6 3.2-42 3.2-64s-1.1-43.4-3.2-64zm112.6-32l-116.7 0c-10-63.9-29.8-117.4-55.3-151.6c78.3 20.7 142 77.5 171.9 151.6zm-149.1 0l-176.6 0c6.1-36.4 15.5-68.6 27-94.7c10.5-23.6 22.2-40.7 33.5-51.5C239.4 3.2 248.7 0 256 0s16.6 3.2 27.8 13.8c11.3 10.8 23 27.9 33.5 51.5c11.6 26 20.9 58.2 27 94.7zm-209 0L18.6 160C48.6 85.9 112.2 29.1 190.6 8.4C165.1 42.6 145.3 96.1 135.3 160zM8.1 192l123.1 0c-2.1 20.6-3.2 42-3.2 64s1.1 43.4 3.2 64L8.1 320C2.8 299.5 0 278.1 0 256s2.8-43.5 8.1-64zM194.7 446.6c-11.6-26-20.9-58.2-27-94.6l176.6 0c-6.1 36.4-15.5 68.6-27 94.6c-10.5 23.6-22.2 40.7-33.5 51.5C272.6 508.8 263.3 512 256 512s-16.6-3.2-27.8-13.8c-11.3-10.8-23-27.9-33.5-51.5zM135.3 352c10 63.9 29.8 117.4 55.3 151.6C112.2 482.9 48.6 426.1 18.6 352l116.7 0zm358.1 0c-30 74.1-93.6 130.9-171.9 151.6c25.5-34.2 45.2-87.7 55.3-151.6l116.7 0z"),
    "birthday": ("0 0 448 512", "M86.4 5.5L61.8 47.6C58 54.1 56 61.6 56 69.2L56 72c0 22.1 17.9 40 40 40s40-17.9 40-40l0-2.8c0-7.6-2-15-5.8-21.6L105.6 5.5C103.6 2.1 100 0 96 0s-7.6 2.1-9.6 5.5zm128 0L189.8 47.6c-3.8 6.5-5.8 14-5.8 21.6l0 2.8c0 22.1 17.9 40 40 40s40-17.9 40-40l0-2.8c0-7.6-2-15-5.8-21.6L233.6 5.5C231.6 2.1 228 0 224 0s-7.6 2.1-9.6 5.5zM317.8 47.6c-3.8 6.5-5.8 14-5.8 21.6l0 2.8c0 22.1 17.9 40 40 40s40-17.9 40-40l0-2.8c0-7.6-2-15-5.8-21.6L361.6 5.5C359.6 2.1 356 0 352 0s-7.6 2.1-9.6 5.5L317.8 47.6zM128 176c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 48c-35.3 0-64 28.7-64 64l0 71c8.3 5.2 18.1 9 28.8 9c13.5 0 27.2-6.1 38.4-13.4c5.4-3.5 9.9-7.1 13-9.7c1.5-1.3 2.7-2.4 3.5-3.1c.4-.4 .7-.6 .8-.8l.1-.1c3.1-3.2 7.4-4.9 11.9-4.8s8.6 2.1 11.6 5.4l.1 .1c.1 .1 .4 .4 .7 .7c.7 .7 1.7 1.7 3.1 3c2.8 2.6 6.8 6.1 11.8 9.5c10.2 7.1 23 13.1 36.3 13.1s26.1-6 36.3-13.1c5-3.5 9-6.9 11.8-9.5c1.4-1.3 2.4-2.3 3.1-3c.3-.3 .6-.6 .7-.7l.1-.1c3-3.5 7.4-5.4 12-5.4s9 2 12 5.4l.1 .1c.1 .1 .4 .4 .7 .7c.7 .7 1.7 1.7 3.1 3c2.8 2.6 6.8 6.1 11.8 9.5c10.2 7.1 23 13.1 36.3 13.1s26.1-6 36.3-13.1c5-3.5 9-6.9 11.8-9.5c1.4-1.3 2.4-2.3 3.1-3c.3-.3 .6-.6 .7-.7l.1-.1c2.9-3.4 7.1-5.3 11.6-5.4s8.7 1.6 11.9 4.8l.1 .1c.2 .2 .4 .4 .8 .8c.8 .7 1.9 1.8 3.5 3.1c3.1 2.6 7.5 6.2 13 9.7c11.2 7.3 24.9 13.4 38.4 13.4c10.7 0 20.5-3.9 28.8-9l0-71c0-35.3-28.7-64-64-64l0-48c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 48-64 0 0-48c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 48-64 0 0-48zM448 394.6c-8.5 3.3-18.2 5.4-28.8 5.4c-22.5 0-42.4-9.9-55.8-18.6c-4.1-2.7-7.8-5.4-10.9-7.8c-2.8 2.4-6.1 5-9.8 7.5C329.8 390 310.6 400 288 400s-41.8-10-54.6-18.9c-3.5-2.4-6.7-4.9-9.4-7.2c-2.7 2.3-5.9 4.7-9.4 7.2C201.8 390 182.6 400 160 400s-41.8-10-54.6-18.9c-3.7-2.6-7-5.2-9.8-7.5c-3.1 2.4-6.8 5.1-10.9 7.8C71.2 390.1 51.3 400 28.8 400c-10.6 0-20.3-2.2-28.8-5.4L0 480c0 17.7 14.3 32 32 32l384 0c17.7 0 32-14.3 32-32l0-85.4z"),
    #  A plain document, for the File tool's download (an SVG in the theme's
    #  own colour, not the OS-painted 📄 emoji it replaced).
    "document": ("0 0 384 512", "M0 64C0 28.7 28.7 0 64 0L224 0l0 128c0 17.7 14.3 32 32 32l128 0 0 288c0 35.3-28.7 64-64 64L64 512c-35.3 0-64-28.7-64-64L0 64zm384 64l-128 0L256 0 384 128zM112 256c-8.8 0-16 7.2-16 16s7.2 16 16 16l160 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-160 0zm0 64c-8.8 0-16 7.2-16 16s7.2 16 16 16l160 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-160 0zm0 64c-8.8 0-16 7.2-16 16s7.2 16 16 16l160 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-160 0z"),
    #  A CV / résumé: a card with a portrait and lines, which reads as a
    #  person's document rather than a generic file.
    "resume": ("0 0 576 512", "M0 96C0 60.7 28.7 32 64 32l448 0c35.3 0 64 28.7 64 64l0 320c0 35.3-28.7 64-64 64L64 480c-35.3 0-64-28.7-64-64L0 96zM88 384l144 0c13.3 0 24-10.7 24-24c0-30.9-25.1-56-56-56l-56 0c-30.9 0-56 25.1-56 56c0 13.3 10.7 24 24 24zM160 288a56 56 0 1 0 0-112 56 56 0 1 0 0 112zm176-64c0 8.8 7.2 16 16 16l128 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-128 0c-8.8 0-16 7.2-16 16zm0 64c0 8.8 7.2 16 16 16l128 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-128 0c-8.8 0-16 7.2-16 16zm0 64c0 8.8 7.2 16 16 16l128 0c8.8 0 16-7.2 16-16s-7.2-16-16-16l-128 0c-8.8 0-16 7.2-16 16z"),
}
UI_ICON_LABELS = {
    "certificate": "Certificate / award", "phone": "Phone", "email": "Email",
    "address": "Address / location", "web": "Website", "birthday": "Birthday",
    "document": "Document / file", "resume": "CV / résumé",
}

#  File-TYPE icons, for the File tool and the Media Library: a page outline
#  carrying the type in letters, so a PDF, a spreadsheet and a zip can be
#  told apart at a glance -- which a grid of identical 📄 could not. Drawn,
#  not emoji, for the same reason as the rest of this file: currentColor,
#  so they follow the theme. Keyed "ui:file-<type>"; `file_type_icon`
#  picks one from a filename, and a File tool line with no icon of its own
#  wears that.
FILE_TYPE_ICONS = {
    "file-pdf": ("PDF", "PDF file"),
    "file-word": ("DOC", "Word document"),
    "file-sheet": ("XLS", "Spreadsheet"),
    "file-csv": ("CSV", "CSV data"),
    "file-slides": ("PPT", "Presentation"),
    "file-archive": ("ZIP", "Zip archive"),
    "file-text": ("TXT", "Plain text"),
}
_FILE_TYPE_BY_EXT = {
    ".pdf": "file-pdf", ".doc": "file-word", ".docx": "file-word",
    ".xls": "file-sheet", ".xlsx": "file-sheet", ".csv": "file-csv",
    ".ppt": "file-slides", ".pptx": "file-slides", ".zip": "file-archive",
    ".txt": "file-text",
}
#  A page with a folded corner, drawn as an outline so the letters read
#  inside it. 384x512, the same box the document icon uses.
_FILE_PAGE_OUTLINE = ("M64 16h176l112 112v336a32 32 0 0 1-32 32H64"
                      "a32 32 0 0 1-32-32V48a32 32 0 0 1 32-32z M240 16v112h112")


def file_type_icon(filename):
    """The icon key for a file, from its extension -- "ui:file-pdf" for a
    .pdf -- or the plain document for anything this does not know."""
    ext = os.path.splitext(filename or "")[1].lower()
    return "ui:" + _FILE_TYPE_BY_EXT.get(ext, "document")


def _file_type_svg(key):
    label = FILE_TYPE_ICONS[key][0]
    return ('<span class="cms-icon cms-icon-drawn"><svg viewBox="0 0 384 512" '
            'width="16" height="16" aria-hidden="true">'
            '<path d="%s" fill="none" stroke="currentColor" stroke-width="28" stroke-linejoin="round"/>'
            '<text x="192" y="418" text-anchor="middle" fill="currentColor" '
            'font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="128">%s</text>'
            '</svg></span>' % (_FILE_PAGE_OUTLINE, label))


EMOJI_GROUPS.insert(1, ("Social", [("brand:" + k, BRAND_LABELS[k]) for k in SOCIAL_ICON_PATHS]))
EMOJI_GROUPS.insert(2, ("Icons (follow theme)",
                        [("ui:" + k, UI_ICON_LABELS[k]) for k in UI_ICON_PATHS]
                        + [("ui:" + k, v[1]) for k, v in FILE_TYPE_ICONS.items()]))

EMOJI_CHOICES = [item for _group, items in EMOJI_GROUPS for item in items]


def icon_choices_for():
    """[(emoji, label), ...] — one flat curated set, in the order shown."""
    return EMOJI_CHOICES


#  Characters that are TEXT rather than pictures. An emoji is drawn to
#  fill its line — about 1.37em wide at any size — while © and its
#  relatives are ordinary typography and come out around 0.71em, so at one
#  font-size the same setting produces three different-looking marks. The
#  class lets the CSS even them up; measured rather than guessed (see
#  BOW.md, 2026-08-25).
TEXT_GLYPH_ICONS = {"©", "®", "™"}


def render_icon(icon_key):
    """Inline HTML for one icon. `icon_key` is the emoji itself, a
    "brand:<name>" key for a drawn mark, or a text character — this wraps
    it so the CSS can size all three to the same square."""
    if not icon_key:
        return ""
    if icon_key.startswith("brand:"):
        name = icon_key[6:]
        path = SOCIAL_ICON_PATHS.get(name)
        if path:
            #  Drawn in the brand's own colour, which is how a brand mark
            #  is meant to read; currentColor is the fallback for a mark
            #  whose colour we do not carry.
            fill = BRAND_COLORS.get(name, "currentColor")
            return ('<span class="cms-icon cms-icon-drawn"><svg viewBox="0 0 24 24" '
                    'width="16" height="16" fill="%s" aria-hidden="true">'
                    '<path d="%s"/></svg></span>' % (fill, path))
        return ""
    if icon_key.startswith("ui:"):
        if icon_key[3:] in FILE_TYPE_ICONS:
            return _file_type_svg(icon_key[3:])
        #  A plain icon, ALWAYS currentColor -- it takes the colour of the
        #  text it sits in, so it follows the site's theme and recolours with
        #  it (the answer to "make these icons fit the theme").
        entry = UI_ICON_PATHS.get(icon_key[3:])
        if entry:
            viewbox, path = entry
            return ('<span class="cms-icon cms-icon-drawn"><svg viewBox="%s" '
                    'width="16" height="16" fill="currentColor" aria-hidden="true">'
                    '<path d="%s"/></svg></span>' % (viewbox, path))
        return ""
    kind = "cms-icon-glyph" if icon_key in TEXT_GLYPH_ICONS else "cms-icon-emoji"
    return f'<span class="cms-icon {kind}">{html_escape(icon_key)}</span>'
