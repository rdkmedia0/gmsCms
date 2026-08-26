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
}


#  The brand marks are real paths, not emoji, because no emoji means
#  "Instagram" and a footer full of approximations reads as a mistake.
#  They ride in the same picker under keys of their own — render_icon
#  knows a "brand:" key draws an SVG and everything else is the character
#  itself.
BRAND_LABELS = {
    "facebook": "Facebook", "instagram": "Instagram", "x": "X",
    "youtube": "YouTube", "linkedin": "LinkedIn", "tiktok": "TikTok",
    "pinterest": "Pinterest",
}
EMOJI_GROUPS.insert(1, ("Social", [("brand:" + k, BRAND_LABELS[k]) for k in SOCIAL_ICON_PATHS]))

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
        path = SOCIAL_ICON_PATHS.get(icon_key[6:])
        if path:
            return ('<span class="cms-icon cms-icon-drawn"><svg viewBox="0 0 24 24" '
                    'width="16" height="16" fill="currentColor" aria-hidden="true">'
                    '<path d="%s"/></svg></span>' % path)
        return ""
    kind = "cms-icon-glyph" if icon_key in TEXT_GLYPH_ICONS else "cms-icon-emoji"
    return f'<span class="cms-icon {kind}">{html_escape(icon_key)}</span>'
