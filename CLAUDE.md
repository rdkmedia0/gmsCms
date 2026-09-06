# Architecture principles for this project

This is a self-hosted Flask CMS. It used to have a single 5,251-line
`app/routes/admin.py` mixing routing, business logic, hardcoded content
data, AI prompt text, and ad-hoc markup/styling, plus dead code from a
removed WordPress-import feature that went unnoticed for a long time. That
was fully cleaned up and de-monolithed (see "Refactor history" at the
bottom for what changed and how it was verified). **Do not let it regrow
that way.** Every rule below exists to prevent a repeat of that specific
failure mode — read this file before making structural changes.

## Where things live

```
app/
  routes/
    admin/            # the admin Blueprint — package, not a single file
      __init__.py     # `bp` + cross-cutting shared state: settings getters,
                       # sidebar/footer layout application, the demo/package
                       # content merge engine, undo snapshots, _list_tools
      dashboard.py     # the Dashboard (now a row of buttons), the screens
                       # its six sections became — Blog, and Design's
                       # Pages/Templates/Layout tabs — plus help and the
                       # theme generator. All five share _screen_context()
                       # rather than growing four near-copies of one query
                       # set; the markup lives in partials/dash/*.html.
      pages.py         # page/blog-post CRUD, undo route, per-page layout
      sections.py      # every section/column/banner/card/image-library
                       # route, plus the Tools-panel routes
      templates.py     # template colors/activate/delete, nav-layout,
                       # sidebar/footer layout presets, package import/export
      demo.py          # demo pack load/clear
      settings.py      # site/favicon/layout/email/AI/Google settings, admins
      assistant_routes.py  # AI assistant chat/apply
    auth.py            # login/logout/Google OAuth/account
    public.py          # the public-facing site (pages, blog posts)
  services/            # reusable business logic — see "No monolith files"
    packages.py        # Template Package install/export/import (zip)
    sections.py        # section-content classification, columns, banner/
                       # card styling, starter-HTML builders, image-library
                       # listing — the biggest one, matches the biggest
                       # feature area
    scheduling.py      # doing something later: the claim IS the lock,
                       # because two workers wake up together. A schedule
                       # is a TIME THIS SITE ACTS AT, not a property of
                       # any one feature -- a newsletter sends on one, a
                       # post publishes on one, a backup runs on one --
                       # and they are made in exactly ONE place, the
                       # Schedules screen (routes/admin/schedules.py).
                       # They were defined on two screens and picked on
                       # a third that could not make one.
    email_layouts.py   # what a NEWSLETTER is made of: the BLOCKS, and
                       # the arrangements of them each template starts
                       # from. An email is not a page —
                       # see "Newsletters" below.
    menu.py            # the Menu-tool builder, shared by body sections,
                       # template zones, and demo/package content
    palette.py         # color-palette role matching + tint_shade_ramp()
                       # (the 6-step lightest..darkest expansion per role
                       # color, bridged into --{role}-{step} CSS vars)
    tools.py           # custom-tool toolkit export/import (a tool can be
                       # imported from a shared file or a Template Package,
                       # or deleted, but not created from scratch anymore
                       # — see "Content tools" below for why)
  data/
    templates/<slug>/  # built-in Template Packages shipped with the app —
                       # see "Template Packages" below
  templates/
    admin/, partials/, public/   # Jinja templates — structure + data-*
                                  # only, no embedded logic (see below)
    prompts/*.j2        # AI prompt content (see "AI prompts" below)
  static/
    js/admin/           # extracted admin-panel JS — one file per template,
                         # plus shared helpers: modal.js (the cmsModal()
                         # confirm/prompt dialog), elapsed-timer.js (the
                         # "Generating... Ns" counter pattern),
                         # image-picker.js (window.cmsImagePicker -- the
                         # Media Library chooser, pulled out of
                         # inline-editor.js so an ADMIN screen can ask
                         # for a picture without a second one being
                         # written)
    js/inline-editor.js # the live-page WYSIWYG editor (contenteditable,
                         # drag-drop, uses window.cmsModal from modal.js)
    css/                # site-base.css (shared structure) + one theme.css
                         # per built-in look (now sourced from
                         # data/templates/<slug>/theme.css at seed time)
    fonts/              # every selectable Google Font, self-hosted as real
                         # .woff2 files + local @font-face CSS (one file per
                         # FONT_PAIRINGS preset, plus one shared choices.css
                         # for individually-picked fonts) with each family's
                         # OFL/Apache license text in fonts/licenses/ — see
                         # "Fonts are fully self-hosted" below
  assistant.py, ai_image.py, ai_video.py, mailer.py, crypto.py, icons.py, db.py, csrf.py
                                          # (the AI Theme Generator lives in
                                          # services/ now — see below)
```

## The admin is buttons, then tabs

The Dashboard was six long sections on one screen — blogs, settings,
pages, the theme generator, templates, layout — and it read as a wall.
It is a row of buttons now, and anything with more than one screen groups
them behind tabs along the top: **Design** (Pages / Templates / Layout /
Theme Generator), **Commerce** (Products / Orders / Bookings), **Email**
(Newsletters / Email list / Sending email).

Three rules for adding a screen:

- **A tab list lives in ONE partial** and is included by each of its
  screens — `partials/design_tabs.html`, `partials/commerce_tabs.html`,
  `partials/email_tabs.html`. They were pasted into each template once
  and that is exactly how a fourth screen ends up missing one.
- **Tabs are links** (see `partials/tabs.html`), so a tab can be
  bookmarked, opened in a new window and found again by the back button.
- **A section's markup is a partial**, not a block inside a bigger
  template. `partials/dash/*.html` are the Dashboard's old sections,
  unchanged, rendered from their own routes.

## No monolith files

Never let routing, business logic, and content data pile up in one file.
When adding a route:

- The route function itself should be thin: parse the request, call one
  service function, format the response. If a route body is doing real
  work (looping over rows, building HTML, branching on business rules),
  that work belongs in `app/services/<domain>.py`, not inline in the route.
- Services take `db` and plain arguments — never `request`/`session`/
  `flash`/`redirect`. That's what keeps them callable from more than one
  route, from `_seed()`, and from a script, without dragging Flask
  request-context along.
- Import direction is one-way: `routes -> services -> data/db`. A service
  never imports from `routes`. If you find yourself doing that, the logic
  is in the wrong layer.
- A hardcoded content blob (business copy, a big config dict, a whole
  demo site's worth of pages) does not belong as a Python literal inside a
  route file. It belongs in `app/data/` as its own file(s) — see "Template
  Packages" below for the pattern this project uses for themes and demo
  content.
- If a route file (or a service file) starts creeping past ~500-800 lines
  again, that's the signal to split it by domain the same way
  `app/routes/admin/` already is — one file per feature area, sharing
  state through the package's `__init__.py`, not by re-merging everything
  back into one file.

## A tool's controls are the app's; a tool's content is the site's

The single boundary that decides how anything in the editor is styled,
and which side of it a change belongs on. See BOW.md (2026-08-25) for how
each of these was found and measured.

- **Controls** — a tool's panel, its selects, steppers, hints, labels and
  buttons, the toolbars, the admin screens, the dock — are this app
  talking. They are styled centrally (`inline-editor.css`, `admin.css`,
  `cms-sidepanel.css`) and look identical on every install: the editor's
  own typeface (`--cms-ui-font`), its own accent (`--cms-ui-accent`), its
  own text colour (`--cms-ui-text`) and its own corners
  (`--cms-ui-radius-control` 4px for anything you click or type into,
  `--cms-ui-radius-surface` 8px for a plate something sits on, 999px for a
  pill). **Take the token; never type a radius.**
  An action is an icon with a tooltip, and the same glyph means the same
  act everywhere: a pencil edits, a **red ×** removes, a tick is a state
  and not a button. When the label is a glyph the `title` is the only text
  there is, so every one carries a sentence — see `.icon-btn` /
  `.icon-state` in `admin.css`.
  **Never `var(--primary)`, never an inherited site face or colour, in a
  control.** A chrome surface — anything that paints a background of its
  own — states what colour text on it is; it never lets the site's colour
  reach it by inheritance. Six of them did, invisibly, because every
  label inside them happened to pin its own; that is how the Numbers
  panel became unreadable, one unpinned element later.
  A control whose colour comes from the active template is a control
  whose legibility is decided by somebody's brand — the self-help
  palette gave the admin's own buttons 3.58:1, and an owner can override
  a palette to anything.
- **Content** — what the tool renders onto the page — belongs to the
  site and keeps following the palette, the fonts and the three-tier
  Corners/Depth. A theme styling `.cms-stat-value` or `.cms-card-shape`
  is correct and must not be "fixed".
- The test is **"could a visitor ever see it?"** If not, it is the app's.
  A form a *visitor* fills in (newsletter sign-up, contact form) is
  content even though it is made of form controls, and still wears the
  site's clothes.
- A control does not stop being a control when it stands somewhere else.
  The Rows stepper on a Columns cell sits in a bare `.cms-inline-form`
  rather than in a tool panel; it is still chrome. Every form carrying
  that class is this app asking the admin a question.
- **Editor markup does not ship to visitors.** `data-save-url`,
  `data-field`, `data-section-id` and `data-set-tool-url` are gated on
  `editing` (see the `edit_field` macro in `public/page.html`). The
  attributes the PAGE renders with — `data-layout-width`,
  `data-corner-style`, `data-shadow-style` — stay in both views.
- **One convention per control, everywhere.** A tool's name always takes
  its own line at the top of its panel. It used to sit left or on top
  depending on whether the controls happened to fit beside it, so the
  same tool changed shape when its column was resized.

Tools cannot carry CSS at all — `content_tools` has no stylesheet column,
only markup and identity — so this is enforced by the schema rather than
by discipline. Keep it that way: a tool that needs a new look needs a
rule in the central stylesheet, not a style of its own.

## Is it a defect, or is it the site's look?

The chrome-vs-content boundary above says WHO owns a style. This says
whether a thing that looks wrong is yours to fix at all. Two questions,
and a fix in shared CSS needs BOTH answers to be no:

  1. **Could an owner change it with a control?** If a select, a checkbox
     or a panel already governs it, the current value is somebody's
     answer. Overriding it in CSS overrules a person.
  2. **Did anyone choose this outcome?** A template picking pill corners
     chose that. A breadcrumb receiving 88px of padding because a
     percentage resolved against the box's WIDTH chose nothing -- no
     hand set that number and no control can unset it.

Worked through, from a real review of a live site:

  * **A video's controls clipped by a 999px radius** -- no control, and
    nobody chose an unusable player. Fix it. The shape rules already say
    "a banner, a picture, a button: nothing inside them can spill", and a
    video is the case that breaks the exemption: its controls live on the
    edge that curves away. Same for a caption, and for a textarea, which
    is the one field tall enough for a pill to become a stadium.
  * **A menu aligned left inside a symmetric shape** -- `menu_align`
     (left/centre/right) is a control on the Menu tool. That is a choice,
     and centring it in CSS overrode it. If a TEMPLATE should ship
     centred, set it in that template's page data, where the owner can
     still change it afterwards.

The two mistakes this prevents are opposite and equally common: styling
around a defect in the machinery instead of fixing it, and "fixing" a
site's own look out from under the person whose site it is.

Two more traps in the same family, both found by measuring rather than
reading, and both cases where a WRONG declaration produces silence:

  * **A percentage pads against WIDTH on every side**, top and bottom
    included. Right for a box roughly as tall as it is wide, absurd for
    a row: a 420x80 file card given `min(24%, 88px)` vertically became
    420x352. A short-wide surface takes `--site-radius-pad-row`, whose
    vertical half is a LENGTH and whose horizontal half stays a
    percentage, because horizontally it is measuring the right thing.
  * **`clamp()` cannot cap a lens or a blob**, and the failure is worse
    than not capping. A lens is `50% / 30%`, so `clamp(0px,
    var(--site-radius), 28px)` is invalid after substitution -- and an
    invalid value arriving through `var()` does not fall back to the
    previous declaration, it is "invalid at computed-value time", which
    means UNSET. Measured: it computed to `0px`. So on exactly the sites
    that needed the cap, the rule did nothing at all. Anything that
    cannot wear the real shape takes `--site-radius-safe`, which is
    always a plain length.

  Both variables are declared by every entry in `SHAPE_PRESETS`, emitted
  with the theme CSS, and mirrored in the `[data-corner-style]` block for
  a section's own override. `tools/shape_check.py` measures all eight
  shapes in a real browser, and proves the old values really did fail.

Two more, about a box that has been emptied rather than styled. Both
were found on the same element, the floating basket, and both were made
twice:

  * **`display: none` on a box that CONTAINS a `position: fixed` child
    hides the child too.** Fixed positioning escapes the flow, not the
    display tree. So emptying a section that a floating thing came from
    takes the floating thing with it, and what was meant to remove a
    placeholder removes the feature. `display: contents` removes the box
    and keeps the child, which is the whole distinction.
  * **Emptying the section is not emptying the block inside it.** They
    are two boxes. `.cms-section` going to `contents` left
    `.block-html` -- which pads 8px 14px around a link that now
    contributes no size -- as a 30x18 pill wearing the site's card
    background, border and 999px radius, under the menu, containing
    nothing.

    And the rule that fixed the second one was written under
    `.cms-editing`, because that is where it was noticed. **A fix scoped
    to the surface it was found on is not a fix**: the visitor is most
    of the people who will ever see the page, and they kept the pill for
    a week. Ask which surfaces render the thing, not which one the
    report came from.

A related trap, found the same day: **you cannot select on a CSS
variable's value.** `[data-corner-style]` is empty unless an ADMIN has
overridden the shape -- a template that simply IS curved sets
`--site-radius` in its own CSS -- so a rule keyed off that attribute
silently matches nothing on most sites. A rule that has to respond to the
shape must be unconditional, or read the variable with `clamp()`/`min()`.

## Templates: HTML, CSS, and JS stay separate

A Jinja template (`app/templates/**/*.html`) should contain **structure and
`data-*` attributes only** — no embedded business logic in a `<script>`
block, no hand-rolled CSS in a `<style>` block, beyond values that are
*genuinely* per-request runtime data (a computed color, an uploaded image
URL) that cannot be a static class or file. There are currently zero
inline `<script>` blocks anywhere in `app/templates/` — keep it that way.

- Real JS logic lives in `app/static/js/` (or `app/static/js/admin/` for
  admin-only panels), as its own file, reading whatever it needs off
  `data-*` attributes or a `<script type="application/json">` data block —
  never generated ad hoc per-template via Jinja. If a page needs data that
  isn't just a URL/id/flag (e.g. the Image Library's list of images), put
  it in a `<script type="application/json" id="...">` block and
  `JSON.parse()` it, rather than interpolating it into the JS file itself.
- Real CSS lives in `app/static/css/` (or a package's own `theme.css`) as
  real classes — never a `<style>` block hand-built in a route or a
  one-off inline `style="..."` for a value that's actually a fixed
  constant (if the value never changes, it's a CSS class, not an inline
  style).
- The only Jinja values allowed to flow into JS/CSS at all are the ones
  that are genuinely dynamic per page load (a URL from `url_for`, an id, a
  boolean flag) — pass those as `data-*` attributes and read them from the
  static JS file, don't generate the logic itself in the template.
- Before adding a new inline `<script>`/`<style>` block to a template,
  check whether the same interaction already exists elsewhere. Two
  templates independently re-implementing the same confirm-and-submit flow
  is exactly the kind of drift this rule exists to prevent — it already
  happened once between `dashboard.html` and `partials/template_panel.html`
  (native `confirm()` + full form-submits vs. `window.cmsModal()` +
  `fetch()`, silently diverged over time). Also check for the "elapsed
  seconds" counter pattern (`window.cmsElapsedTimer` in
  `static/js/admin/elapsed-timer.js`) before hand-rolling another
  `setInterval` for a slow async action.
- The shared confirm/prompt modal (`window.cmsModal`, from
  `static/js/admin/modal.js`) needs its backdrop markup on the page —
  `{% include "partials/cms_modal.html" %}` — before it'll work. Both
  `admin/base.html` and `public/page.html` already include it; if you add
  a third page shell that needs confirm dialogs, include it there too.

## Fonts are fully self-hosted — never add a live Google Fonts link

Every font this app can select — the 7 non-empty `FONT_PAIRINGS` presets
and all `GOOGLE_FONT_CHOICES` (`routes/admin/__init__.py`) — is bundled as
real `.woff2` files with local `@font-face` CSS under `app/static/fonts/`
(see its own README.md). Nothing in this app fetches `fonts.googleapis.com`
or `fonts.gstatic.com` at runtime, by design: this was a deliberate fix
(2026-08-22, see BOW.md) after checking Google Fonts' actual license terms
(OFL 1.1 / Apache 2.0 both explicitly permit self-hosting and bundling
font files with software) and confirming a live CDN link had two real
costs — silent fallback-font degradation if the visitor can't reach
Google, and every visitor's IP going to Google on every page load (a
GDPR-relevant third-party exposure some EU courts have specifically
flagged for unconsented live Google Fonts loading).

There is no free-form "type any font name" input anywhere in the app —
every font choice is a closed, fixed set — which is exactly what makes
bundling all of it upfront tractable. **When adding a new font choice**
(a new `GOOGLE_FONT_CHOICES` entry or `FONT_PAIRINGS` preset), it must be
downloaded and added to `app/static/fonts/` the same way (fetch the CSS2
API URL with a real browser User-Agent so Google serves clean WOFF2-only
`@font-face` blocks, download each referenced file, **rename it
`<family>-<NN>.woff2`** — Google's own filenames are up to 132 characters
of base64 naming a build on their CDN, long enough that a `git clone` into
a nested folder fails on Windows' 260-character path limit and leaves a
repository that looks cloned and is not — rewrite `src: url(...)` to the
local path, fetch the family's OFL/Apache license text from
`google/fonts` on GitHub into `fonts/licenses/`) — never just add a
`https://fonts.googleapis.com/...` URL and call it done, even temporarily.
Template Packages don't need to bundle font files themselves: every
deployment of this codebase already ships the complete fixed font set as
part of the repo/Docker image, so a package's `google_fonts_url` (always
one of the local paths above) resolves correctly regardless of which
install exports or imports it.

## What the AI cannot do, said before somebody meets it

Two limits belong to the PROVIDER, not to this app -- and an owner who
is not told cannot tell those apart. "The Generate button does nothing"
reads as a bug every time.

- **Ollama has no image-generation API at all**, whatever model is
  loaded. So `ai_image.IMAGE_GEN_PROVIDERS` excludes it, the Generate
  controls are not offered while it is the provider, and
  `ai_image.unavailable_reason()` says WHY in the owner's terms with the
  way round it (put Open WebUI in front of it: that passes image
  requests to a backend that can, and still uses Ollama for chat). Never
  "not configured" -- that is true of a missing key and of a provider
  that structurally cannot, and those need different actions.
- **A small self-hosted model asked something it cannot map to a tool
  very often returns NOTHING** -- no words and no tool call. That used
  to be relayed as an empty reply, so the panel showed nothing at all:
  you asked, and the screen did not change, which reads as the assistant
  ignoring you. `assistant._nothing_came_back()` answers in words, and
  says something DIFFERENT depending on the provider, because "try a
  larger model" is useless advice to somebody on Gemini.

The rule behind both: **an absence is not an explanation.** A control
that is missing, or a reply that is empty, has to come with the reason,
and the reason has to name something the owner can act on.
`tools/ai_limits_check.py`, and it isolates itself from `OPEN_WEBUI_*` /
`OLLAMA_*` / `GEMINI_*` in the environment -- `get_ai_settings` falls
back to those for installs configured before these screens existed, so a
machine that has them set would otherwise have the checker testing the
deployment rather than the code.

## AI prompts live in template files, not Python strings

A prompt sent to an AI provider (a system prompt, an instruction block) is
content, not code. Long/static prompts go in `app/templates/prompts/*.j2`,
rendered with `render_template()` like any other template — even a prompt
with no variables (`assistant_system_prompt.j2` has none;
`theme_generator_brief.j2` takes `brief`/`schema`). Short (a few lines),
tightly-coupled-to-a-JSON-schema strings (like a single tool's
`description` field in `assistant.py`'s `TOOLS` list) are fine to stay
inline. If the assistant's own feature-set description drifts from
reality after a feature changes (it did once, for a removed importer),
fix `assistant_system_prompt.j2` in the same change.

## Template Packages: this app is a template manager, not a CMS with a demo-data side feature

The product framing: **a template manager (browse/install/activate/save/
export full-site looks) built on top of a general-purpose CMS**. A
"Template Package" is authored as a directory under `app/data/templates/<slug>/`
(built into a shipped `.zip` — see "Shipped templates travel as one .zip each" below)
(built-in, shipped with the app — 20 exist today, each a complete look +
content pack: `bakery`, `business`, `clinic`, `coaching`, `coffee-shop`,
`community`, `cv`, `fitness`, `garage`, `hair-salon`, `personal`,
`restaurant`, `self-help`, `shop`, `trades`, `venue`, plus four made BY
the Theme Generator and promoted into the set — `ash-barn`,
`half-turn`, `harbour-physio`, `lumen-rooms`. Those four earn their
place by SHAPE rather than by category, which is the second axis the
original sixteen do not vary on: they are the only built-ins that open
on a Catalogue (prices first, `ash-barn`, `lumen-rooms`) or a Process
(the steps of working together, `half-turn`, `harbour-physio`) rather
than a Landing. They also overlap the existing set by trade -- a venue,
a garage, a clinic and a portfolio are all already there -- so when
adding to the set, ask which of the two axes a candidate is new on. The set is chosen
against how the large builders categorise demand, not by taste: trades,
appointment-led services, food, retail and portfolio all have one, and
each differs in nav/shape/shadow/palette/fonts AND in page structure —
six templates built from the same four sections demonstrate one layout
six times, which is what the earlier set did) or `app/static/themes/<slug>/` (admin-imported or saved from
the live site, in the Docker-mounted persistent volume). Earlier
revisions shipped 6 additional content-free "theme-only" packages
(Simple Clean, Modern SaaS, Editorial Serif, Corporate Navy, Dark Studio,
Warm Community) that a content pack pointed at by name via a manifest
`theme_name` key. That indirection is gone: each of the 6 packages above
now ships its own `theme.css`/`palette`/`google_fonts_url` directly, so
there's nothing left for a bare theme-only package to do that the paired
content pack doesn't already do better. Don't reintroduce a "theme-only,
no content" package — every built-in should be a real, complete look:

```
<slug>/
  manifest.json     # name, slug, palette/nav/layout metadata
  theme.css         # optional
  palette.json      # optional, or inlined in manifest.json's "palette" key
  pages/
    NN-<slug>.json  # optional — omit entirely for a template with no content;
                     # NN prefix keeps page order stable across files
  blog_posts.json    # optional
  media/             # optional — the template's OWN pictures, named
                     # <slug>-<what it is>.png so a file copied into any
                     # shared place still says whose it is. A template's
                     # pictures belong to the template: never a shared
                     # app-wide folder, which is what made an exported
                     # package silently incomplete.
```

**Shipped templates travel as one .zip each.** The folders above are
where a template is AUTHORED — loose files, diffable, reviewable. The
image build runs `services.packages.build_template_zips()`, which turns
each folder into `app/data/template-packages/<slug>.zip` and deletes the
sources (a `packager` stage in the Dockerfile, so the sources are gone
before the runtime image copies the tree — delete them in a later layer
and the earlier one still carries all 86MB). Zips are deterministic:
fixed entry timestamps, sorted entries, so identical sources always build
identical bytes. Each carries an `install.json` written by
`package_inventory()` — every page and its section count, every picture
with size and checksum, the layout and identity keys it will apply —
so what a package will do can be read before letting it do it.

**Every package becomes a `templates` row**, whether or not it ships
`pages/` — see `app/__init__.py`'s seed loop, which calls
`services.packages.install_template_zip()` for every shipped zip on every
boot. That deliberately uses the SAME extractor (`safe_extract_zip`) and
the same installer an admin's uploaded package goes through: the import
path used to run only when somebody uploaded something, which is exactly
how it came to discard a package's pages and pictures unnoticed. It now
runs sixteen times per boot, so a break in it is a failed start rather
than a surprise months later. **Installing also REMOVES pictures the
archive no longer ships** (`_drop_stale_media`): extracting adds files and
never takes any away, so a template whose pictures changed format left
every old one behind — 77 orphaned PNGs on one install, referenced by
nothing, doubling the Media Library. Reading a zip's index is cheap, so
it runs on the boots that skip reinstalling too, which is what lets an
install already carrying leftovers clean itself. It touches `media/`
only, and a missing or unreadable archive removes nothing: not being able
to read what a folder should contain must never mean deleting what is in
it. Reinstalling is skipped when the archive
already unpacked in place matches by hash (`.installed-from`), so a boot
costs milliseconds — but a template with no `templates` row is always
reinstalled, which is how a deleted builtin comes back. Every installed
package, builtin or uploaded, lives at `static/themes/<slug>/`;
`template_package_dir()` has one answer now, not one per kind. A template's LOOK and its CONTENT are two
independent, always-available actions on any installed template, not two
different kinds of package and not one combined action gated on whether a
package happens to have `pages/`:

- **Activate** (`routes/admin/templates.py`'s `template_activate`) flips
  `is_active` and applies everything the package ships: its default
  layout, if its manifest declares one (`nav_layout`/`page_layout`/
  `footer_layout` keys — optional on any template) via
  `_apply_default_layout()` (`routes/admin/__init__.py`), AND its page
  content, if it has any, via `_apply_pack_content()` — activating a look
  loads what comes with it, one step, all-or-nothing. Either part is
  skipped (and the admin told to confirm) if it would replace an existing
  sidebar/footer section or page content, unless already confirmed
  (`force=1`; see `_default_layout_conflicts()`/`pack_content_conflicts()`
  and `template-panel.js`'s snapshot-first confirm flow).
- **Load Content** (`template_load_content` route) re-merges ALL of a
  package's `pages/*.json` into the site's own matching pages via
  `_apply_pack_content()` — all-or-nothing, no per-page picker (a
  template has its base data; you load all of it or none). Since Activate
  already loads it once, this exists mainly to reload it again later
  (e.g. resetting a page back to the template's own copy after editing
  it). A single action scoped to whichever template is currently
  **active** — not a picker listed per library entry
  (`dashboard_template_maps()` computes just one `active_content` value,
  not a map of every content-bearing template) — since only one template
  is ever "the one you're looking at" at a time.
- **Save current site as a new template**
  (`services.packages.save_current_site_as_package()`) captures the
  active template's look plus every live page's content, writing
  straight into `app/static/themes/<new-slug>/` + a new `templates` row —
  the same place an imported `.zip` lands, immediately
  activatable/loadable like any other entry. It arrives as WORK IN
  PROGRESS -- see the lifecycle below -- so it is not exportable until
  it is promoted.
- **A template is a SOURCE or it is CUSTOM** (`services/lifecycle.py`),
  and that one distinction decides what may happen to it. A **source**
  never changes: the sixteen shipped ones are sources, and so is any
  custom template the owner has finished and PROMOTED. It is packaged,
  and therefore exportable. A **custom** template is work in progress:
  freely editable, private to this install, with no artefact behind it
  and so nothing to export. `is_builtin` is no longer what the code
  branches on -- "shipped" is one of two reasons a template is a source,
  which is what stops promoted ones being a special case beside them.
- **Editing content never forks. Changing a LOOK asks.** There WAS a
  `before_request` that copied the active builtin on the first content
  edit, and it produced three identically-named "(your copy)" entries on
  one install, each with its own duplicate of the pictures. Editing a
  page writes to `pages` and `sections` -- the SITE's data -- so nothing
  about it needed a copy. Changing a template's colours, fonts, shape or
  shadow is the first moment anything shipped would actually be altered,
  so that is where the question belongs: `LOOK_ENDPOINTS` in
  `routes/admin/templates.py` and the `before_request` beside it answer
  `needs_fork`, the panel asks for a NAME (a name they chose is one they
  will recognise), and `fork_as` / `fork_into` carry the answer back.
  Overwrite-or-another is asked rather than decided, because only the
  owner knows whether the old copy still matters. **The endpoint set is
  named rather than decorated so it can be CHECKED** -- `template_check.py`
  fails if a route whose path changes a look is not in it.
- **Promotion is when the artefact is built, and the only place the
  completeness check belongs.** A custom template has no zip, so there is
  nothing to keep in step with the edits; promoting it writes the folder
  and its `install.json` inventory and freezes it. The check runs there
  because promotion is a deliberate act with a person waiting on it --
  the one moment "this references four pictures and three of them exist"
  can be REFUSED rather than discovered by whoever installs it later.
  Promotion is reversible while nothing depends on it (`lifecycle.depends_on`)
  and refused once something does, the same shape as "the active template
  cannot be deleted". A shipped template can never be demoted: its
  package is in the image and comes back on the next boot.
- **A template is a structured website, pages included.** Loading one
  loads its pages, and the previous template's pages go -- ALL of them.
  Keeping what is there is what "just the look" is for, and that is the
  only exception.

  This spared any page carrying `pages.owner_edited`, on the reasoning
  that a page somebody has written in is the site's now. Two things were
  wrong with it. The flag is set by a trigger on `sections`, so an older
  bug that cleared it BEFORE writing a pack's own sections marked every
  page of every pack as edited -- and a spared page is spared by every
  future switch too. That is how one template's "The library" survived
  onto a wedding barn, a bicycle workshop and a pottery studio, carrying
  its own heading, with nothing on screen explaining why. The second is
  that it made "load the template" mean different things depending on
  history nobody can see.

  The flag still exists and still means "somebody wrote in this page".
  It is a WARNING now, not a veto: `_retire_foreign_pack_pages` returns
  which of the removed pages had the owner's own writing in them, and
  the caller says so. The undo is the one this app already has -- the
  confirm dialog's "save the current setup as a new template first" --
  which is an act the owner chooses, rather than preservation by a flag
  they cannot see. Load Content clears the flag: putting the pack's own
  copy back is exactly the act that un-edits a page.
- **Delete** works on any template, including builtins — a deleted
  builtin's `templates` row (and its copied `static/themes/<slug>/`
  asset) just comes back the next time the app restarts, since the seed
  loop reinstalls every builtin package unconditionally. Only the
  currently-active template can't be deleted.
- **Every template gets a customizable color palette**, even a
  content-only package whose manifest never declared one —
  `install_theme_package()` falls back to `packages.DEFAULT_PALETTE`
  (primary/secondary/accent, chosen as a genuine complementary scheme —
  see its own docstring) so the Colors panel works universally, not just
  on templates that happen to ship their own colors. `--primary`/
  `--primary-dark` (`public.py`'s `_color_override_css()`, always
  bridging the resolved primary color, override or not) reach every
  colorable object in `site-base.css` that isn't a real theme's own
  markup — Menu buttons, Card/Banner accents, the File tool's
  button/hover/text-link, and a body-text hyperlink (`.cms-wysiwyg-body
  a`) — so customizing colors has a visible, site-wide effect even on a
  template with no imported theme CSS of its own. `COLOR_PRESETS`
  (`routes/admin/__init__.py`) are built the same way: each one's accent
  is chosen as that primary's actual complementary contrast, not just
  another shade of the same hue — when adding a new preset or touching
  `DEFAULT_PALETTE`, keep that relationship (secondary = analogous/deeper
  shade for cohesion, accent = genuine complementary contrast), and when
  wiring a new section type's CSS, check whether it has a color that
  should route through `--primary`/`--primary-dark` instead of a
  hardcoded hex, the same way the File tool and body links now do.
- **Layout has a 3-tier cascade**: a template's own default (above) →
  site-wide override (`settings.nav_layout`, unchanged) → per-page
  override (`pages.nav_layout_override`/`hide_sidebar`/
  `hide_sidebar_right`/`hide_footer` — set from the page's own "Layout"
  card in `admin/page_edit.html`, resolved in `public.py`'s
  `_render_page`/`blog_post`). A page's own hide flags never fork that
  zone's content — the sidebar/footer's sections stay one shared,
  template-wide thing; a page just opts out of showing them.

There is no "active demo pack" concept — no `demo_active_pack` setting,
no `demo.py`, no undo-by-clearing. There is also no separate Snapshots
system any more (the old `page_snapshots` table/routes are gone) —
"Save current site as a new template" (see above) IS the one
undo/get-back-to-this mechanism: it's a real, portable template the
moment it's saved, reusable by Activating it again later. The shared
`cmsModal()` (`static/js/admin/modal.js`) offers "save the current setup
as a new template first" as a checkbox on every layout/content-
destructive confirm, wired through `template-panel.js`'s
`maybeSaveTemplate()`, which posts to `template_save_current` with no
name so it auto-names the save `"<active template> - <timestamp>"` —
the admin can rename it (or export it) from the Dashboard afterward.

**This is not two separate systems** — don't reintroduce a hardcoded
`BUILTIN_THEMES` list or a `DEMO_PACKS` dict in Python, and don't gate a
feature on "does this package have `pages/`" as if that made it a
different kind of thing. If it's a starting point for a site — a color
scheme, a full demo site, anything in between — it's a package under
`app/data/templates/` (or an admin's own saved one under
`app/static/themes/`), loaded through `app/services/packages.py`. When
adding a new built-in look or demo site, add a package folder (see any
existing one for the exact shape). When adding logic that operates on
packages, add it to `app/services/packages.py`, not back into a route
file.

**The AI Theme Generator makes one of these** (`services/theme_generator.py`,
reached from `routes/admin/dashboard.py`). It used to append three or four
sections to whichever page you picked, which made generating an edit to a
live site whose undo was "delete the sections it added, one at a time".
It writes a package now and installs it through the same installer an
uploaded `.zip` goes through, **without activating it** — so what comes
back is a template to look at, keep, use, export or throw away, and six
things come free: preview, one all-or-nothing apply, undo by re-activating
what was active, export, media owned by the template, and
`package_inventory()`.

What that means for anything added to it:

- **It picks values; it never writes rules.** A look is a palette, fonts,
  a shape and a shadow — every one of them a value the existing controls
  already carry. No `theme.css` travels with a generated package and no
  rule hides in the markup. Emitting *tokens* the stylesheet already
  consumes would be acceptable one day; emitting CSS never is.
- **Everything it emits is built from real tools**, so an owner can go on
  editing it by hand. A class the generator invented is a look nobody can
  edit with the controls they have, and nothing on screen says so —
  `theme_generator_check.py` fails on any class no tool produces.
- **It carries no identity.** A package may carry a business name; this
  one must not invent one, and a generator is the likeliest thing here to
  overwrite the site's own by accident.
- **A brand kit is resolved once per run** — tone, voice, reading level,
  language, palette, fonts, shape, depth, and one image direction — and
  read by every call. Independent calls are exactly why generated sites
  read as several different companies.
- **Looking is free.** "Show me the plan" asks the provider nothing and
  says what the run would make and what it would cost. The checker counts
  provider calls during a plan and goes red if looking ever starts
  costing something.
- **Three modes, three intentions**: keep my words (no AI at all),
  rewrite them (same facts, different voice — an answer of the wrong
  shape keeps the original, because a rewrite that drops a phone number
  is a mistake the owner may never find), or write new pages.
- **A picture gives style and only style** (`services/look_from_picture.py`):
  colours, typefaces, corners, depth, and three or four words for how it
  feels. Nothing it returns could carry somebody's prose, which is the
  boundary this has always had.

  It was a LINK, fetched and parsed for its CSS, and that went for two
  reasons an install's owner cares about more than we do. A small site's
  server reaching out to third-party pages, repeatedly, from one address,
  is what a scraper looks like — and being taken for one costs THEM their
  reachability. And it was refused by exactly the sites people most want
  to point at: a bot check answers with a challenge page, a challenge
  page HAS colours, so the reader "succeeded" and returned the wrong ones.
  Measured over twelve real sites it also missed anything that renders
  itself in JavaScript, GitHub included.

  **The colours are arithmetic and the style is not**, so they are read in
  two different places. Colours come from the pixels, in the BROWSER
  (`theme-generator.js`), which needs no provider at all — an install with
  no AI still gets a palette out of a screenshot. Every rule in that
  sampler is a measurement: NEAREST rather than smooth, because a
  smoothing downscale averages neighbours and invents colours that are in
  no part of the picture (it turned Hacker News orange into three tints of
  peach); weighted by saturation squared, because a brand colour is a
  decision and a photograph's average is not; and the three have to differ
  from each other, or a gradient returns three shades of one and the
  palette has no secondary and no accent.
- **What is SENT is a small copy, and only when something can look at it.**
  The file itself is never uploaded — the input has no `name`. Measured
  against a real vision model, the full 1280x800 screenshot came back HTTP
  400, and 87 KB at 1024px came back **empty**: no error, no words, a
  blank reply indistinguishable from a model with nothing to say. 64 KB
  answered. So the browser shrinks it to 800px/~40 KB before sending, and
  `MAX_BYTES` refuses anything a model would choke on rather than
  discovering it in silence.
- **Whether the model can see is asked, not guessed.** Both self-hosted
  providers publish it per model, and a no NAMES the models on the same
  server that can — this install had a coder model selected with four
  vision models sitting beside it. Two traps, both real: Open WebUI's
  `info.meta.capabilities.vision` is `true` on **every** model (it is the
  UI's own toggle block, defaulted on) so it says nothing and must not be
  read — the honest field is the backend's capability list; and a model
  that does not SAY is tried rather than refused, because refusing on a
  model's behalf is the failure this replaced.

Runs are synchronous. They should become claimed jobs (the discipline is
in `services/scheduling.py`) when a run grows past what a request should
hold; at three pages it is three requests and does not need to be.

## The site's identity is the site's, never the template's

One install is one website. However many templates get tried on, the name,
the tagline, the business details, the postal address and the contact are
the site's own: captured once, managed from the admin screens, and read by
everything that needs them. **A template brings a look and some pages. It
does not bring an identity, and activating one must not overwrite these.**

Two things worth knowing before touching this:

- These details live in two places -- `site_title`/`site_tagline`, and
  the fifteen `legal_*` settings written from the Legal pages screen.
  Write into what is there; do not open a third home. **The legal name
  falls back to the site's** (`legal.settings_for`) rather than standing
  empty beside it, and the Legal screen says so and points out a
  disagreement instead of merging one: a trading name and a legal entity
  genuinely can differ ("Flour & Salt" on the door, "Flour & Salt GmbH"
  on the paperwork), so differing must be something the owner typed, not
  something that happened to them. This install had a tab reading one
  business and a Terms page naming another, which is how it was found.
- A package MAY carry an identity (`business_name`, `tagline`,
  `footer_blurb`, `footer_contact` in its manifest -- the builtins all do,
  with invented names for invented businesses). On apply it is a
  **fallback only**: used when the site has none of its own, never an
  overwrite. `_apply_pack_identity()` (`routes/admin/__init__.py`) is the
  one place that happens, and only because a fresh install has no name of
  its own: it writes the manifest's `business_name` ONLY while the current
  name is still a placeholder or another builtin's demo name.
- **A package never carries a connection or a key.** Not an API key, not
  SMTP, not Stripe or Cal.com settings. This holds by construction today
  -- the only setting `_build_package_dir()` reads is `nav_layout`, and
  commerce is not captured at all -- and it must keep holding: keys live
  encrypted in settings (`crypto.py`) and have no business in a file that
  travels. Content and the site's name are a different matter and are fine
  to carry.
- **The risk in a shared package is misattribution, not disclosure.** It
  is tempting to treat an embedded Cal.com widget or Stripe button as a
  secret escaping. It is not: that markup is served to every visitor of
  the site it came from, so a copy reveals nothing, and it is of no use to
  anybody unless they actually want to book or buy -- from the original
  owner. The real failure is the other way round, and it lands on the
  person who INSTALLED the package: their site now carries a Pay Now
  button wired to somebody else's Stripe account, or a booking that fills
  somebody else's calendar, looking for all the world like part of the
  template. Money and appointments go to the wrong party, silently.
  The same is true of the owner's business details. An Impressum is public
  by law; the problem is not that the address escaped, it is that the
  importer's terms page would now name the wrong legal entity and the
  wrong VAT number.
  So the rule is about pointing, not hiding: **content that names a
  specific real-world party -- a payment account, a calendar, a legal
  entity -- must not silently keep pointing at that party on somebody
  else's site.** Which makes it an INSTALL-time concern, not an
  export-time one: nothing needs stripping on the way out. Treat such a
  reference the way a Blog tool's id is already treated -- the installer
  fills it from the receiving site's own integration, or leaves the block
  visibly unconfigured, exactly as a package ships `data-blog-id=""`
  because it cannot know what the receiving install will call things. That is a heuristic standing in for an answer nobody has
  given yet. If a flow ever records that the owner stated their identity
  (see BOW.md's setup wizard), this path stops applying to them entirely
  rather than getting a smarter guess.

## Features are tools, never page types

A page type describes the page **as a whole** — a blog's list of posts, a
newsletter's ability to be sent as email. That list is closed
(`PAGE_TYPES` in `services/sections.py`) and should stay closed. Every
other capability is a **tool** an admin drops onto an ordinary page.

This was learned the expensive way, twice. "FAQ" was briefly a page type,
with the page enforcing what could go on it and injecting a search box
and a contents list of its own. It was the wrong shape in three separate
ways: the questions could not live anywhere else, a site could not have
two sets of them, and every later feature would have had to ask which
kind of page it was standing on before knowing what it could do.
Replacing it with tools removed all three limits at once and deleted code
rather than adding it.

**Blog** went the same way for the same reasons (`services/blog.py`). A
blog was a page, which made "this site has a blog" and "this page is the
blog" one statement — one blog per site, at one address, and nothing else
able to show its posts. A blog is now a named set of posts with a slug of
its own, and the Blog tool is one place a set is shown: several blogs per
site, several on a page, or the same blog on two pages without its posts
being copied. A post's address is built from the blog's slug, so it never
changes when pages are rearranged — and existing sites carried across
with their URLs intact, because the migrated blog keeps the old page's
slug. Note what this cost: `blog_posts.page_id` was NOT NULL, so the
table had to be rebuilt. **A column pointing at the wrong owner is the
tell that a feature has been modelled as a page.**

**Contact** went too. `PAGE_TYPES` still lists `standard` and
`newsletter`, but newsletter no longer earns its place as a TYPE and the
way it lost that is the clearest statement of the rule this project has.
It was defended here on the grounds that it changed what the page IS to
the rest of the app: kept out of navigation, listed in the public
archive, sendable to a list. Two of those three turned out not to be
about newsletters at all — a page is in a menu because somebody ticked
it, and whether a page is readable is a question EVERY page has, now
answered by `pages.is_public`. The third, sendability, is an action an
admin performs, not a way the page is treated. So what is left is a
marker about what the owner sees on that page while editing it.
**The test still stands**: if the answer to "what does this type do" is a
thing that appears on the page, it is a tool; if it is how the page is
treated by everything else, it is a type. What this taught is the
follow-up question — **ask it about each behaviour separately**. Three
behaviours were bundled under one type and only one of them was ever
about the type at all.

What replaced the types for page creation is `PAGE_LAYOUTS` — a starting
point, not a kind. Choosing "Blog" makes an ordinary page with a Blog
tool already on it, pointed at a blog; choosing "FAQ" makes one with a
Text, a Search and an FAQ Content tool. Every one of them is a standard
page afterwards, and nothing later has to ask what it was created as.
Template Packages follow the same rule: their pages are all `standard`
and carry tools, and a package's Blog tool ships with an empty
`data-blog-id` that the installer fills in, since a package cannot know
what id a blog will get on somebody else's install.

So, when adding a capability:

- **Ask what the admin drops on a page**, not what kind of page it is. If
  the answer is "a page that does X", the feature is a tool called X.
- **Splitting one tool in two is normal** when it does two jobs. FAQ
  Content writes questions; FAQ Reader shows a chosen set of them from
  wherever they were written, with its own display options. One toolbar
  for each, and neither one carrying controls that belong to the other.
- **A tool that produces content other tools consume gives its output a
  name and a stable id.** Every FAQ question carries a permanent
  `data-faq-id`, and a set of them carries `data-faq-name`, so a page can
  hold several sets and a Reader elsewhere can tell them apart. The page
  title alone cannot do this — two sets on one page both answer to it.
- **A page-wide behaviour is a tool too.** Search is a control an admin
  drops where they want it, filtering whatever on that page has said it
  is searchable. It is not something an "FAQ page" does automatically,
  which is what it was first built as.
- **Do not enforce rules by page type** ("this page may not use Embed").
  Enforce them in the tool that has the requirement: an FAQ answer takes
  a small written vocabulary (`faq_markdown` — bold, italic, a link, a
  list, escaped first and converted second) because the tool has to read
  the answer back to edit it. That constraint travels with the tool onto
  any page, which is the point.

## Security is not optional

This app accepts uploads (images, files, `.zip` template package archives)
and renders admin-authored HTML. Treat every input-handling change as
security-relevant, not just the ones that look risky:

- **Uploaded archives**: never call `ZipFile.extractall()` on an untrusted
  file — use `services.packages.safe_extract_zip()`, which resolves every
  entry's real destination path and rejects the whole upload if it would
  land outside the target directory (zip-slip), caps total uncompressed
  size and entry count (zip-bomb protection) independent of the request
  body size limit, and only extracts files whose type is on an explicit
  allowlist. Route any new archive-accepting feature through this
  function rather than writing a second one.
- **File uploads**: keep using `secure_filename()` plus a generated unique
  name (the existing pattern at every upload call site in this codebase) —
  never trust or reuse a client-supplied filename directly on disk.
- **Path handling**: when a user-influenced value builds a filesystem path
  (an upload filename, a package slug), verify the resolved path stays
  inside the intended directory before touching disk — the existing
  `os.path.commonpath(...)` check in the image-library delete route
  (`routes/admin/sections.py`) is the pattern to follow.
- **Raw HTML**: any admin-authored raw HTML (the "HTML/Embed" tool,
  imported package content) is rendered `| safe` by design — this is an
  admin-only, trusted-operator feature, not a public input path. Don't add
  a new path that lets an unauthenticated visitor's input reach a `| safe`
  render.
- **CSP is enforced by the browser, and only by the browser.** The
  Content-Security-Policy in `app/__init__.py` is not advisory: `form-action`
  applies to a form submission's WHOLE redirect chain, so `'self'` alone
  silently refused every checkout — the POST is same-origin, the 303 to
  Stripe is not. It answered 303 to `curl` and did nothing in a browser,
  which is why every command-line check passed while nobody could pay. Two
  rules follow: name any third-party host a form must be able to reach
  (`checkout.stripe.com`, `pay.stripe.com` are there now), and verify
  anything that leaves this origin in a real browser, because no
  server-side test can see a CSP refusal. `tools/prod_check.py` asserts
  the directive admits Stripe and has not been widened to `*` while doing
  it.
- **A public form that sends email is rate limited, and the two are not
  equally dangerous** (`services/ratelimit.py`). `captcha.py` has always
  said a sum "will not stop a determined attacker... the rate limit on
  the route is what bounds the damage" -- and that limit did not exist,
  which is worse than documenting none, because it is the reason nobody
  went looking. The contact form mails the OWNER; a flood is a nuisance.
  The sign-up form mails **whatever address was typed into it**, so a
  flood is a confirmation message to a stranger who did not ask, at an
  address the attacker chose -- so it gets a tighter allowance, plus the
  same honeypot, using the SAME field name as the contact form's (one
  trap, not two that can disagree). Counted on the way IN, because
  counting only successes means the way past is to make each attempt
  fail; and with no client address to count against it fails OPEN, since
  a contact form nobody can use is worse than one that can be spammed.
- **Auth/CSRF**: every state-changing admin route stays behind
  `@login_required` and the existing CSRF middleware (`app/csrf.py`,
  Origin/Referer-based, not a hidden-token scheme — see its own docstring
  for why) — don't add a new route that bypasses either.
- **A commit is checked before it is made, not after.** `.githooks/pre-commit`
  refuses any commit carrying a file named like a credential, or content
  shaped like a live key (`sk_live_`, `whsec_`, `ghp_`, a PEM header). It
  exists because a `git add -A` swept up a password file somebody had put
  in the working directory to be READ, committed it, and pushed it to a
  remote -- and the repository had to be destroyed and rebuilt. Care is
  what failed there, so the replacement is not more care. **Enable it in
  every clone: `git config core.hooksPath .githooks`** (git does not
  enable hooks on clone, by design). `.gitignore` also matches credential
  files by PATTERN rather than by name, because the next one will be
  called something else.
- **Secrets**: never log, commit, or echo `.secret_key`, `.encryption_key`,
  API keys, or OAuth client secrets. `data/`, `.secret_key`, and
  `.encryption_key` are gitignored on purpose — keep it that way. Don't
  commit Claude Code's own runtime state either (`.claude/scheduled_tasks.lock`
  is gitignored for the same reason: it's per-session, not project source).
- When in doubt, treat the change as if it were public-facing: validate
  size, type, and destination before trusting any uploaded or imported
  content.

## Content tools: use the right tool for the job

Demo/seed/generated content must compose only from the Tool menu's actual
primitives (Text, Image, Banner, Card, Columns, Menu, Table, ...) — if a
real admin couldn't reproduce a piece of content by picking tools from the
panel, neither can generated content. Never invent a one-off CSS class or
bespoke markup structure to make something look right; if the visual
result needs a genuinely new capability, that's a product discussion, not
a private code path.

Within that, the **HTML/Embed tool is reserved for real third-party embed
code** — a Cal.com booking widget, a Stripe button, anything that
genuinely needs actual `<script>`/iframe markup to function. It is never
the answer for styling text, laying out simple content, or working around
something a proper tool doesn't do yet — every one of those has (or
should have) a dedicated tool, and reaching for Embed instead hides the
gap rather than surfacing it. This applies equally to the AI assistant's
own content edits (see `assistant_system_prompt.j2`) and to any
generated/seeded content.

**There is no "create a new custom tool" feature any more** (removed
2026-08-22, see BOW.md) — it used to be a form (and an AI Assistant
function, `create_content_tool`) for saving a `(section_type, raw HTML)`
pair as a new tool-panel chip. On inspection it added no real capability
beyond the existing tools: using it well required hand-typing HTML, which
is exactly the Embed-wrapped shortcut the rule above exists to prevent —
and since the AI Assistant only ever proposes content, not code, it could
structurally never build a *genuinely* new tool (a real dedicated editing
form) either, only ever another Embed-shaped one. `content_tools` rows
can still arrive via the Toolkit import/export system
(`services/tools.py`) or a Template Package's bundled `tools.json`, and
can still be deleted — just not authored from scratch in this app.

This extends to **every admin/editing surface, not just generated
content**: design for a total novice ("think as if grandma wants to
build a website") — plain quick-select controls (dropdowns, checkboxes,
labeled buttons), a `title` tooltip on every control in addition to
adjacent `<p class="hint">` text, never a raw HTML textarea as the way to
accomplish ordinary styling or layout. **There is ONE rich-text toolbar**
— its markup in `partials/wysiwyg_toolbar.html`, its behaviour in
`static/js/wysiwyg-commands.js` — used by the live editor and by any
admin form that needs one (`textarea[data-richtext]`, upgraded by
`admin/rich-text.js`). The blog editor briefly had a second, smaller
one; `tools/design_conventions_check.py` now refuses that. A caller
passes only what genuinely differs: which editable a control acts on,
what to do afterwards, and how to ask for a URL.
`admin/page_edit.html` used to
render every section's `content` in a raw `<textarea>` — including plain
Text/Card/Banner sections whose `content` is real HTML — as a legacy
fallback UI; it was removed once the live inline editor
(`public/page.html` + `inline-editor.js`, reached via "View Site") fully
superseded it with real WYSIWYG editing for every section type. If you're
tempted to add a raw-HTML input for something a real admin would want to
do with plain content, stop — that's a product discussion (a new
dedicated tool), not a quick escape hatch.

## What was added after the refactor (same rules apply)

Each of these follows the structure above — thin routes, logic in
`app/services/`, content in templates, no inline script:

- **Commerce**: `services/integrations.py` (provider registry: Stripe,
  Cal.com), `services/commerce.py` (customers, orders, entitlements, the
  booking↔credit link), `services/cart.py`, `services/downloads.py`
  (paid files, stored OUTSIDE any served directory — see its docstring).
  Products are created and repriced from this app; a Stripe price is
  immutable, so "change the price" means new price + retire old + move
  the fulfilment rule.
  **A subscription keeps delivering.** Fulfilment had no concept of
  recurring delivery: only `checkout.session.completed` and the refund
  events were handled, so a monthly price granting 10 sessions granted
  them ONCE, at the first payment, and never again -- silently, with the
  customer running out in month two. `invoice.paid` is handled now, and
  **the first payment is skipped**, because Stripe sends BOTH a checkout
  session and an invoice with `billing_reason: subscription_create` for
  the same money and granting both hands every new subscriber double.
  `commerce.FIRST_PAYMENT` / `RENEWAL_REASONS` name that distinction so
  it cannot be got wrong by accident. A failed renewal grants nothing so
  there is nothing to revoke, but it is recorded as a failed order,
  because an expired card is otherwise completely silent. **Adding a
  handler is only half of it**: `WEBHOOK_EVENTS` decides what Stripe is
  ASKED to send, and an endpoint keeps the list it was created with
  forever -- so `webhook_missing_events` compares the two and the
  Integrations screen names anything missing, or a new event works on
  new installs and does nothing on every existing one.
  **One shop is one currency** (`integrations.base_currency`): one
  setting, the default every new product is created with. It was a
  per-product dropdown with CHF first in the list, which is exactly how
  a shop came to price in three currencies -- and the consequence was not
  untidiness, it was that `cart.lines()` took the FIRST line's currency
  and added every later amount into one subtotal, so 10 CHF and 10 EUR
  read "20.00 CHF": a number that is not a price in either. A basket now
  refuses to mix and says which one it took out. An EXISTING product
  keeps the currency it was created with, because a Stripe price is
  immutable and a new one in a different currency would orphan the
  fulfilment rule keyed to the old -- so the screen states each price's
  currency rather than offering to change it, and names any that
  disagree with the base. Conversion and regional detection are separate
  features and deliberately not here.
- **One list of tool controls**: a tool's config forms live once, in
  `tool_config_forms` (`public/page.html`), called by the section chain
  and by `render_cell` alike -- a section passes no `col_index` and gets
  the URLs it always had, since Flask drops a None and picks the rule
  that does not need one. `tools/parity_check.py` puts every tool on a
  page twice, once as a section and once as a cell, and compares the two
  panels with the ids, URLs and storage field names taken out: **30
  tools, 0 differences**. Run it after touching anything a tool renders;
  it is what found the last three places where the same tool behaved
  differently depending on which container it was standing in.
- **Declared content blocks**: `services/blocks.py`. Eight tools
  (pricing, testimonial, stats, logos, team, timeline, CTA, newsletter
  sign-up) share ONE config form, ONE parser and ONE pair of routes. A
  ninth tool is a dictionary entry, not six files. Content lives once, in
  the markup, read back via `data-field` attributes.
- **Section backgrounds**: any section can carry a picture with an
  overlay (`bg_image`/`bg_overlay`/`bg_position`). The overlay is not
  optional — text over an unmodified photograph is legible about half the
  time — and it is a class, so everything inside a dimmed band flips
  colour with it.
- **An email is not a page** (2026-08-27). A newsletter WAS a page,
  written with the tools every other page uses, and most of them do not
  survive the trip: measured, Blog/Shop/Buy button/Contact form/FAQ
  Reader arrive EMPTY (each is a marker resolved against live data an
  inbox does not have), Search arrives as a magnifying glass, and Columns
  as the literal text `{}`. So a newsletter is an ordered list of
  **blocks** -- `email_layouts.BLOCK_TYPES` (heading, text, picture,
  button, divider), rendered by ONE template,
  `templates/emails/blocks.html`, which is both the email that is sent
  and the canvas that is written into (`edit` is the only difference,
  and with it false not one extra attribute is emitted). Table
  structure, every style inline. What the wrapper owns does not move and
  must not become editable: the ground, the light card, the sender line
  and the unsubscribe link.
- **The shape is chosen IN the editor, and nowhere else.** There was a
  picker on the Newsletters screen -- four specimens to choose between
  before writing a word -- and it is gone. The Template dropdown already
  makes that choice and makes it better: at full size, with the blocks
  in front of you, changing as you choose. A choice offered twice is one
  somebody makes twice, and the earlier time is the one made with less
  information. What that dropdown must get right: it asks before
  replacing work, and **asks only when there IS work** -- "does any
  block contain words" is the obvious test and it is wrong, because a
  template lays out "A heading" and "What you want to say", so a new
  newsletter answered yes and every change asked to replace nothing.
  The question is whether the blocks still MATCH what that layout laid
  out. `tools/newsletter_layout_check.py`.
- **A newsletter LAYOUT is a starting arrangement, not a kind** -- the
  same shape `PAGE_LAYOUTS` takes for pages, and here for the same
  reason. Layouts were a fixed set of named slots, so a letter could
  never carry a picture and a story could never carry two, and every
  newsletter had exactly the parts its layout declared whether it wanted
  them or not. `starting_blocks(key)` seeds the blocks; every one can be
  added, removed, reordered or restyled afterwards, and nothing later
  asks which layout a newsletter was made from. Adding a layout is a
  dictionary entry -- never a template, and never a tool. Adding a kind
  of BLOCK is a considered addition to `BLOCK_TYPES`, because everything
  in it has to survive an inbox.
- **A block's style is admitted on two tests, not one**: an inbox has to
  honour it AND the stored form has to be able to write it down.
  Background, text colour, alignment and a font family pass -- they are
  inline attributes on a table cell, which is the one thing every client
  renders. `@font-face` fails (Gmail strips it), so `EMAIL_FONTS` is
  real installed families only. This corrects an earlier, too-strong
  reading that fonts and colours "mean nothing in an inbox": the real
  reason those controls lied was that a flat text field could not record
  them, which a block can. **A control that is discarded on save is a
  control that lies** -- that rule stands, and the second test is what
  it actually means.
- **Newsletters**: `services/newsletter.py`. A newsletter IS a page,
  sent as email by translating its sections to inline-styled HTML. One
  message per person, refused without a postal address. `page_type=
  'newsletter'` is a **marker about what the owner sees** -- Subject,
  Preview and Send on the page itself while editing, plus a line on the
  Newsletters screen -- and can be turned on or off on any page from its
  own settings. Nothing about the SITE branches on it: whether a page is
  in a menu is whether somebody ticked it, and whether visitors can read
  it is `pages.is_public`, a question every page has (a private page 404s
  for a visitor, still opens for its owner, is left out of `_nav_pages`
  and the `/newsletters` archive, and its email carries no "read it
  online" link). A send is aimed with `newsletter.sections_for()`:
  everything, the latest (`sections.updated_at`, stamped to the
  millisecond by a trigger so it means last CHANGED, not last added), or
  one section by number. The preview takes the same aim, because a
  preview of something else is not a preview. `tools/newsletter_check.py`
  walks the lot with the mail captured instead of sent. **A blog post can
  be sent too, and is the common path**: a post already has a title, a
  date, a permanent address and an online copy, so it is an issue
  without inventing one. Both go through `_send_it()` in
  `routes/admin/newsletters.py` -- extract the guards first, then add the
  caller, or the two drift. `newsletter_sends` records `target_kind` +
  `target_id` with **no foreign key on purpose**: the record that you
  emailed forty people outlives the page or post being deleted, which is
  what it is for. Sending a draft publishes it first (an email whose
  "read it online" link 404s is worse than either). **The email takes the
  active template's colour** (`newsletter.look_from()` over
  `palette.role_ramps()`) for links, rules and the ground behind the
  card -- but stays a LIGHT card and sends only the fallback half of the
  theme's font stack, because Gmail strips `@font-face` and several
  clients invert dark grounds. A greeting and a sign-off wrap every send
  (`newsletter_intro`/`newsletter_outro`, plain text, `{{title}}` and
  `{{link}}`); the sender line and unsubscribe link are appended by the
  code and are deliberately not editable.
- **Who a send reaches** (`services/subscribers.py`): `AUDIENCES` is
  everyone or customers-only. **A customer is computed, never stored** --
  any subscriber whose address has a `paid` order (`is_customer_sql()`),
  so the number cannot go stale and a refund takes it back;
  `subscribers.is_customer` is only the owner's own flag for a sale this
  site never saw (shop, telephone, a different address at checkout), and
  it ADDS to the orders rather than overriding them. **A customer is not
  a subscriber**: every audience intersects with the confirmed list, so
  somebody who bought and never confirmed is never written to. Sends
  record their audience, and a private page (`is_public = 0`) is how
  content reaches the list without appearing on the site -- which is not
  the same as secret, since an email can be forwarded.
- **The email list is double opt-in, and the record is the point**
  (`services/subscribers.py`). Signing up sends ONE mail with a link;
  nothing else is ever sent to an address that has not followed it
  (`listing(confirmed_only=True)` is what a send reads). Three rules that
  are easy to break by accident: **the form must say a confirmation mail
  is coming** before it is used -- a fixed line in `build_newsletter`,
  deliberately not an editable field, because an owner rewording it into
  "you're subscribed" would make the site lie about its own mechanism;
  **every message after confirmation carries an unsubscribe link** that
  needs no login, in the body and in `List-Unsubscribe`/
  `List-Unsubscribe-Post` headers (which is why `public.unsubscribe`
  answers POST and is the one member of `csrf.TOKEN_IS_THE_CREDENTIAL_ENDPOINTS`);
  and **each step is written down** -- consent wording as shown at the
  time, signup IP and page, when the invitation was sent, when and from
  where it was answered -- because "we had consent" is a claim you have
  to evidence a year later. Erasing somebody (admin) is a different act
  from unsubscribing them and takes that evidence with it, by design.
  `tools/signup_check.py` walks the whole path with the mail captured
  instead of sent; run it after touching any of this.
- **A newsletter body takes a small written vocabulary**, not HTML and
  not a plain box: `## `/`### `, `**bold**`, `*italic*`,
  `[words](address)`, `- ` bullets (`email_layouts.rich`, escaped first
  and converted second -- the same shape `faq_markdown` takes, for the
  same reasons). The editing canvas IS the email, and there is ONE
  toolbar above it in four groups: the template (a dropdown -- changing
  it lays the blocks out again, and asks first), what can be added, the
  shared writing tools (`include_layout=false`, because alignment, font
  and colour act on a BLOCK here, and two controls that look alike but
  differ would be worse than either), and the selected block's own
  style.
  **A layout somebody likes can be saved to the Template list**
  (`email_layouts.save_layout`, an `email_layouts` table). A layout is a
  starting arrangement and not a kind, so a saved one is the same thing
  with its blocks written down instead of typed out, in the same
  dropdown. It keeps what is on the CANVAS rather than what was last
  saved, asks for a name (a name somebody chose is one they will
  recognise six weeks later), and replaces rather than duplicates when
  the same name is used again. It can be REMOVED, and only if it is one
  of yours -- a shipped layout is in the code and would be back on the
  next boot, so both the button and the route refuse.

  **The screen is ordered like an envelope**: the ribbon, To and Subject,
  the message, then what to do with it. It used to put the actions third,
  which meant Send -- the button you press last -- sat above everything
  you do first, live, over a message that was still empty. Everything
  before the canvas is what the message needs; everything after it is
  what happens to the message. Schedule and its time are drawn as ONE
  control, and Delete is in that row rather than alone in a card below.

  **A block's link is a block control**, in the ribbon beside its
  alignment and colour -- not a card under the message holding one field.
  Its explanation is the field's own tooltip: a sentence of running text
  in a row of controls is most of what makes a toolbar read as a section.

  Three things travel together and must stay in step: `rich()`,
  `newsletter-editor.js`'s serialiser (its exact inverse), and
  `block_styles()`, which both the sent email and the editor read so a
  heading made by the toolbar looks like the heading that arrives. In the
  editor, writing a style attribute is safe while typing; REPLACING a
  node moves the caret and may only happen on blur or before saving.
  **Structure is saved and re-rendered by the server, never rebuilt in
  JavaScript** -- adding, removing, moving or restyling a block submits
  the form, so the canvas always comes from `blocks.html`, the same
  template that renders what is sent. Two renderers would drift, and a
  preview that has drifted is worse than none. Every structural action
  reads the canvas into the block list BEFORE it splices, because that
  re-read matches DOM to blocks by index.
  The screen is laid out the way a mail composer is -- ribbon, then the
  actions, then To and Subject, then the message -- because that is a
  shape people already know; "who gets it" used to be a card at the
  BOTTOM beside Send, so deciding who a newsletter was for happened
  after writing it. It is ONE form and the buttons differ by
  `formaction`, which is what lets Send, Schedule, Save and Preview all
  read the same audience control without a second copy of it.
- **A scheduled send has to survive two workers** (`services/scheduling.py`).
  This app runs two gunicorn workers against one SQLite file, so whatever
  wakes up looking for due sends is running twice and the failure it
  invites is mailing everybody twice. **The claim is the lock**: taking a
  job is one UPDATE carrying the state it expects (`claimed_at IS NULL`),
  so exactly one worker can match and `rowcount` says which. Nothing to
  leak if a process dies mid-send -- a claimed, unfinished row is visible
  AS one. **A failure is never retried automatically**: it is written
  down with its reason and left for a person, because an automatic retry
  cannot tell "SMTP was briefly down" from "twenty of them already got
  it". The poller thread is armed by the first request each worker
  handles, NOT at import time: `--preload` means `create_app()` runs in
  the master and threads do not survive a fork, so one started there
  would sit where no request is ever served. A scheduled send runs inside
  a request context built from the site's own public address, because
  `url_for` cannot make a link without a host and there is no request to
  borrow one from -- and reading that address first is also the check
  that there IS one, without which the job is refused rather than sent
  with an unsubscribe link to nowhere. `tools/schedule_check.py` walks
  the lot with the mail captured, including racing two claims.
  `tools/newsletter_editor_check.py` drives the real thing in a browser
  and compares what is sent against what was on screen -- run it after
  touching any of the three.
- **Backups**: `services/backup.py`. SQLite `VACUUM INTO`, never a file
  copy; restore pushes back through SQLite's backup API rather than
  swapping a file under a running app. The encryption key is excluded by
  default so a leaked archive cannot spend money.
- **The messages that send themselves are the owner's**
  (`services/site_emails.py`): an order landing, a sale, a sign-up, a
  confirmation. **The whole body is written by the owner**, and the facts
  arrive as placeholders -- `{{items}}`, `{{invoice}}`, `{{total}}`,
  `{{method}}`, `{{link}}`, `{{access}}` -- offered per message and
  listed on one screen (Email -> Message wording).

  This reverses an earlier rule, and the reason is worth keeping. It was
  a greeting and a sign-off wrapped around a body the CODE rendered, on
  the grounds that **the facts are not a field**: an owner writing over
  them removes something the reader needs. That was half right, and the
  wrong half cost more. The fixed middle told a returning buyer how many
  sessions they had IN TOTAL, summed across every order they had ever
  placed, in an email about the one they had just paid for -- and no
  owner could correct it, because the sentence was ours. **A fixed body
  that says the wrong thing is worse than an editable one that says
  nothing**, because the first cannot be fixed by the person being
  blamed for it. The facts did not become optional; they became
  addressable.

  **Two things are still not a field**, and neither is a matter of taste.
  The unsubscribe link is appended below any wording on a list message --
  in `wrap()`, not in the route that happens to know the URL, so a fifth
  list message cannot ship without it, and only when it is not already
  there. The sender line is added to BOTH halves of the mail. And a
  placeholder this app cannot fill is left visible as `{{whatever}}`
  rather than becoming a blank, because a visible mistake gets fixed and
  a gap does not; an EMPTY one takes its whole line with it, so a message
  never ends in "Buyer: " with nothing after it.

  Everything a message can say about an order is worked out **once, per
  order**, in `commerce.order_values` -- the buyer's copy and the
  seller's differ in their words, never in their facts. Two sets built
  separately is how one of them comes to quote a different total.

  **The screen IS the message** (`admin/site_emails.html` +
  `admin/wording-editor.js`), in the newsletter editor's own canvas:
  written on the left, and the same words with the placeholders filled in
  on the right, updating as they are typed. A sentence with `{{total}}`
  in the middle of it cannot be judged until it says 42.00 CHF, and the
  old collapsed preview asked somebody to imagine that. What the code
  appends is greyed and inert below, and said in words as well -- grey
  carries it only for somebody who notices grey.

  An owner's earlier wording is adopted, never dropped: installs carrying
  `email_<m>_intro`/`_outro` compose them around the shipped default, and
  a reset clears the pair too. Adding a fifth message means adding it to
  `MESSAGES` and wrapping it where it is sent; `site_emails_check.py`
  fails if a sender forgets.
- **The invoice belongs to both parties.** Stripe raises a real, numbered
  invoice for every payment -- this app has always asked for one
  (`invoice_creation[enabled]`, because a receipt is not a document
  anybody can put through their books) and then never looked at the
  answer, so the tax document existed and was unreachable from either
  side. Orders keep `invoice_ref`; `commerce.invoice_links()` resolves
  the PDF, and a redirect route serves it to the buyer (token-scoped,
  like a download) and to the seller. Both need it and for the same
  reason: one files a purchase, the other a sale.
  **Resolved, never stored at the time**: `invoice_pdf` and
  `hosted_invoice_url` are null until Stripe finalises the invoice, which
  is normally AFTER the webhook that recorded the order -- so the one
  moment a URL could be baked in is the moment it is guaranteed to be
  missing. A null means "ask again", never "there is none". A renewal is
  the exception and needs no second call: a paid invoice is a finalised
  one, and the event carries both links.
  A text `{{invoice}}` is always available and is the fallback for orders
  placed before any of this was captured.
- **Legal pages**: `services/legal.py` + `templates/legal/*.j2`, written
  from the owner's own details and what the site actually sells. They go
  on **one page called Terms & Conditions** (`/terms-and-conditions`) by default, each document a marked section
  under its own heading and anchor — four extra entries in the menu of a
  five-page site is a real cost. "A page for each" remains, for the case
  that needs it: an Impressum is expected under its own clearly labelled
  link in Germany and Austria. Either way each document keeps its own
  `data-legal-doc` marker, so a refresh rewrites that section and nothing
  around it, and switching to one page removes the old separate pages only
  when they hold nothing but generated text.
- **Bootstrap**: `app/bootstrap.py` — first-run setup from environment
  for a Docker install with no shell. Read once, adopted into the
  database, encrypted; the admin screens are authoritative thereafter.
  **A first boot also opens the site with a template on**
  (`_open_with_a_look`, `FIRST_TEMPLATE` in `app/__init__.py`): a
  template manager whose new install shows an unstyled placeholder page
  is advertising the wrong thing. Guarded on FIRST BOOT -- the branch
  that has just created the home page -- never on "nothing looks
  active", so an upgrade can never apply a template over somebody's
  site; and it runs after the blueprints are registered, because
  applying a look builds menus and a menu asks `url_for` where a page
  lives. The example business name that comes with it is flagged on
  every admin screen until the owner replaces it
  (`site_still_has_a_borrowed_name`). `tools/fresh_install_check.py`
  boots against an empty DATA_DIR twice and checks the lot.
- **Site address**: `services/site.py` is the single authority for any
  URL that leaves the app. Never `url_for(_external=True)` for those.
- **An FAQ is a document, not a form**: FAQ Content holds one document
  (`data-faq-md`). **The rule is `Q.`** — it marks where a question
  starts, and the answer is simply what follows until the next one. That
  one marker is enough: an answer can be several paragraphs or a list with
  no further concept, anything before the first `Q.` is an introduction,
  and nothing has to be inferred about where a question ends. `A.` was
  tried alongside it and dropped as noise — still READ, since pasted FAQs
  use it, but never required or written. `normalise_faq_source` also reads
  `#` headings, numbered questions and plain question-then-answer blocks,
  so an existing FAQ usually pastes in untouched; those are tolerance, not
  the rule. It is written in a WYSIWYG (`faq-editor.js`) whose serialiser
  is the exact inverse of `faq_editor_html`, so the document stays the
  stored form and the checker, mirroring and views never learn the editor
  exists. It
  is written and pasted whole, because a real FAQ runs to dozens of
  questions and arrives already written; a row-at-a-time form was fine for
  three and unusable for forty. How it is SHOWN is a separate choice
  (`FAQ_VIEWS`): read straight through, or folded into rows that open. The
  same text serves every view, and both render the same
  `cms-faq-item`/`cms-faq-q` markup so Search and the Reader behave
  identically either way. A question's id is the slug of its own words —
  derived, not stored, since there is nowhere to hide a generated id in
  text somebody edits by hand. The trade: rewording a question changes its
  id and a Reader falls back to the next question, which is the right way
  round, because a reworded question is usually a different question.
  Each set takes an optional `data-faq-name`, so one page can hold several.
  An FAQ Reader elsewhere can mirror them
  (`build_faq_mirror`/`resolve_faq_mirror`) — it stores which questions it
  shows, never their words, and they are resolved at render time. So a
  wording change on the FAQ page reaches every page repeating it, a
  deleted question drops out rather than dangling, and mirrored text is
  deliberately not editable in place. A mirror is never a source, and a
  block cannot point at itself.

## Running it for real

`README.md` is the operator's document -- install, reverse proxy, backups,
recovery. It is written for somebody who has never seen this code, and it
is the thing to update when a deployment fact changes. What follows is the
part that constrains the CODE.

- **Two workers, one SQLite file.** `db.get_db()` opens WAL with a 30s
  busy timeout and `synchronous = NORMAL`. Under the default rollback
  journal a writer blocks every reader, so an admin saving a page could
  500 a visitor reading one -- and the odds rise with traffic, which is
  the worst possible shape for a fault. Consequences to respect: never
  copy `cms.db` as a file (the -wal file holds recent writes; backups go
  through `VACUUM INTO` and SQLite's backup API for exactly this reason),
  and WAL needs a local filesystem, so a `DATA_DIR` on NFS/SMB falls back
  and the app must not assert on the pragma's return value.
- **A first boot is two processes, and it is the boot that does work.**
  Setting WAL takes an exclusive lock; a fresh install has both gunicorn
  workers running the migration and installing sixteen packages at the
  same moment, so one of them asked for that lock, was refused, and took
  the container down -- `database is locked`, on the pragma, at boot.
  Invisible on any database already converted, because the pragma is then
  a no-op that never asks. Two rules came out of it: **`busy_timeout` is
  set before anything that can be refused** (it was set after the pragma
  that needed it), and the switch is asked about before it is made, since
  READING the mode takes no lock. gunicorn also runs `--preload` now, so
  `create_app()` happens once in the master rather than once per worker --
  there was never a reason for the second one to migrate and seed.
- **Never order by a timestamp to mean "most recent".** This was got
  wrong three times: whole seconds tied, milliseconds tied, and the
  tie-break -- the row id -- silently means "added last", which is a
  different question and usually the wrong answer. WAL made writes fast
  enough that three of them land in one millisecond, and "send the latest
  section" started picking the wrong one. `sections.changed_seq` is a
  counter the triggers bump with `MAX + 1`, so the order is total; read it
  through `newsletter._changed_key`, and include the column in any SELECT
  feeding it. A clock cannot fix this at any resolution -- there is always
  a faster machine.
- **A migration may not touch the data it is migrating.** The backfill for
  that column ran with the old timestamp trigger still installed, so each
  row it wrote fired the trigger, rewrote that row's `updated_at` to
  "now", and moved it ahead of the ordering the next row was about to be
  ranked against -- every row came out first, and every section's real
  timestamp was destroyed. **Drop triggers before backfilling the column
  they stamp**, and prefer a backfill that repairs a bad run (this one
  re-ranks whenever the numbering is not a total order, not only when it
  is missing) over one that only fills blanks.
- **The session cookie's `Secure` flag is decided per request**, by
  `_SchemeAwareSessions` in `app/__init__.py`, from whether THIS request
  arrived over https (ProxyFix having applied `X-Forwarded-Proto`). It was
  an environment variable, which meant it was off on every install whose
  owner never read the log line telling them to set it. `FORCE_SECURE_
  COOKIES=1` still pins it on. HSTS is sent on https requests only, and
  deliberately without `includeSubDomains`/`preload` -- promises about
  names this app does not control.
- **`/healthz` touches the database** (`routes/public.py`) because a
  process that is running and a site that works are different claims: the
  interesting failure is a data volume that did not mount, which a check
  on the port alone calls healthy. It answers to anyone who can reach the
  port, so it says `ok` and nothing else -- no version, no counts.
- **A reverse proxy is not a dependency.** Three shapes are supported and
  the code has to be correct in all of them: this container serving its
  own certificate (`TLS_CERT_FILE`/`TLS_KEY_FILE`, added to gunicorn's
  arguments by the entrypoint), a platform terminating TLS in front of
  it, and a proxy somebody runs. So `X-Forwarded-*` is believed only from
  a peer that could BE a proxy -- `TrustedProxyFix` in `app/__init__.py`,
  which applies `ProxyFix` for a non-global peer and STRIPS the headers
  from anyone else, since a directly-exposed container must not be
  tellable by a visitor that their request was something it was not.
  `TRUST_PROXY=always|never` overrides. Note the range predicate is
  `not is_global`, not `is_private`: Python calls the documentation
  ranges private and leaves carrier-grade NAT out of them.
- **The proxy was also load-bearing for slow clients.** Two sync workers
  can hold two connections, which is invisible behind nginx (it buffers
  the request and only then speaks to gunicorn) and is two lazy sockets
  from a dead site without one -- for `--timeout 2000` each. gunicorn
  runs `gthread` with 8 threads per worker for that reason; keep any
  worker-model change compatible with it (per-request SQLite connections
  via `g` are thread-safe, module-level mutable state would not be).
- **The image is published, and the compose file names it.** Every push to
  `main` builds `ghcr.io/rdkmedia0/gmscms` for amd64 AND arm64
  (`.github/workflows/publish.yml`) -- a small site's VPS is as likely to
  be one as the other. `docker-compose.yml` carries `image:` and `build:`
  together on purpose: `compose pull && up -d` runs the published image,
  `up -d --build` compiles the working tree, and neither needs the file
  edited. If you change the Dockerfile or anything the build copies, the
  published image is what a host gets -- so a change verified only against
  a local build is a change verified in the wrong place.
- **Running a checker.** `tools/` is in `.dockerignore` on purpose --
  development material, not product -- so the published image ships none
  of them and `docker compose exec web python tools/x_check.py` fails on
  a clean clone with "No such file or directory". Copy them in first:

  ```
  docker compose exec -T web sh -c 'rm -rf /app/tools && mkdir -p /app/tools'
  docker cp ./tools/. <container>:/app/tools
  ```

  The `rm -rf` goes inside `sh -c`: on Windows, Git Bash rewrites a bare
  `/app/tools` argument into a Windows path, so the delete silently
  misses and the next `docker cp` nests into `/app/tools/tools` -- and
  the checkers keep running, against the old copy. The browser-driven
  ones (`shape`, `basket`, `newsletter_editor`, `newsletters_screen`,
  `admin_density`, `image_picker`, `newsletter_layout`) run on the HOST
  instead, against a URL, because they need a real browser.
- **The other checkers**, each the net under one feature:
  `parity_check.py` (every tool's panel, section vs cell),
  `newsletter_check.py` and `signup_check.py` (the mail paths, with the
  mail captured), `fresh_install_check.py` (two boots against an empty
  DATA_DIR), `email_layout_check.py` (that an inbox can render a layout —
  tables, no stylesheet, no classes, no flex — and that nothing in `app/`
  carries a control character, after an invisible one cost a day),
  `stale_media_check.py` (that installing removes what a template no
  longer ships, and refuses to when it cannot read the archive),
  `currency_check.py` (that one shop is one currency and a basket cannot
  add two of them together),
  `basket_check.py` (that a floating basket leaves no box behind it for a
  VISITOR as well as while editing, and that it does not vanish instead
  -- measured in a browser, because the markup is identical either way),
  `site_emails_check.py` (that an owner's words reach the four messages
  that send themselves, and that no field can delete a fact),
  `shape_check.py` (that every shape survives a video, a textarea and a
  short wide box, measured in a browser because no server-side check can
  see a dropped declaration),
  `template_check.py` (that no look-changing route escapes the fork
  guard, that only a source can be exported, and that a page somebody
  wrote in survives a template change),
  `abuse_check.py` (that both public forms that send email are bounded,
  and that the limiter is actually called),
  `ai_limits_check.py` (that a provider which cannot make pictures says
  so with the way round it, and that a model returning nothing is
  answered in words),
  `subscription_check.py` (that a renewal delivers every month, that the
  first payment delivers once and not twice, and that a failed one is
  visible -- driven through the real webhook route, because "the file
  contains invoice.paid" passes just as happily when the branch is
  wrong),
  `schedule_check.py` (that a send put on the clock goes exactly once
  even when two workers claim it together, and refuses for the same
  reasons a live send refuses), and
  `design_conventions_check.py` (that a word means one thing across
  tools, and that no admin form asks for raw HTML),
  `newsletters_screen_check.py` (that writing one comes before the list,
  that Yours/going out/gone out are one table, and that a blog is not a
  section of that screen),
  `admin_density_check.py` (that no admin screen is set larger than what
  it holds -- measured across fourteen of them, and reporting a 404
  rather than measuring the error page's own type scale), and
  `newsletter_ai_check.py` (that a newsletter written by the AI is a
  draft and only ever a draft: it cannot send, it composes only from
  blocks the editor has, and it refuses in the owner's terms).
- **A security header written about third parties still has to be read
  as a statement about this site's own features.** `frame-ancestors` and
  `X-Frame-Options` said "nobody may frame this", and the editor's
  responsive preview frames THIS site -- so it showed an empty document
  at every width, silently, because a blocked frame is a console line and
  never an error the server sees. They are `'self'`/`SAMEORIGIN` now,
  which still refuses every other origin. `frame-src` is the other half
  and the subtler one: it said `https:` (wide, for an embedded Cal.com or
  Stripe), which the site's own origin happens to match over https and
  never matches over http -- so the preview would have stayed broken on
  every install without a certificate. It names `'self'` explicitly
  rather than depending on the scheme to say it by accident.
- **`tools/prod_check.py`** is the net under all of the above: it proves
  the pragmas are live by holding a write open and reading through it,
  proves the ordering cannot tie by racing three writes, asks for the
  cookie over both schemes, spoofs `X-Forwarded-Proto` from a LAN peer
  and from a public address to prove only one of them is believed, and
  changes a password to prove the generated one's plaintext file is
  removed with it.

## Deferred follow-ups (identified, not built — don't build unprompted)

These came up while designing the Template Package system as the same
pattern applied further. Worth revisiting if asked, but each is its own
scoped feature, not part of "finish the refactor":

- **Standalone color palettes**: every template now has a customizable
  palette (real or `packages.DEFAULT_PALETTE`), but `COLOR_PRESETS` and a
  package's `palette.json` — already just `[{slug,name,color}]` — could
  still become their own shareable unit (a "Palette Library") independent
  of a full template package, importable/exportable/reusable across
  templates on its own.
- **Blocks/patterns**: `BLOCK_LIBRARY` (starter content for tools) is
  conceptually a Template Package scoped to one section instead of a
  whole site — an admin could save a section they built as a reusable
  pattern.
- ~~**AI Theme Generator ↔ Template Packages**~~ — **done**. The
  generator writes a Template Package and installs it without activating
  it; `theme_layouts.py` is gone. See "The AI Theme Generator makes one of
  these" above. What is still deferred from that work: runs as claimed
  jobs, which only matters once a run outgrows a request.

## Refactor history

The de-monolithing happened as a sequence of small, independently-verified
commits (dead-code removal → Template Package system + zip import/export
→ AI prompts to templates → service-layer extraction → blueprint package
split → front-end script extraction). Each phase was verified against the
actual running app (Docker rebuild + live clicks/fetches through the admin
UI and public site, not just "it imports without error") before moving to
the next.

**The de-monolithing itself landed as a single squashed commit**, so for
that work `git log` is NOT the design record — the reasoning that would
have been in those commit messages lives in this file and in BOW.md, which
is why both are as long as they are. Keep it that way: a decision
explained only in a commit message is a decision this project cannot read
back. Everything since HAS been written as design-note commits (the log is
now hundreds of them) — carry that on, and keep the durable "why" here as
well, because a commit is found by whoever already knows to look for it.

A later pass unified Activate/Load Content/Save-as-template/per-page
layout overrides into the single system described above (retiring
`demo.py` and the `demo_active_pack` tracking it depended on), gave every
template a customizable palette, made every template deletable, retired
the separate Snapshots feature in favor of "Save as a new template"
serving both jobs, and removed `admin/page_edit.html`'s legacy raw-HTML
section editor — see the "Template Packages" and "Content tools"
sections above for the resulting shape, not a separate commit-by-commit
account here.
