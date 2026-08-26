# Self-hosted Google Fonts

Every font this app can select (the 7 non-empty `FONT_PAIRINGS` presets in
`app/routes/admin/__init__.py`, plus all `GOOGLE_FONT_CHOICES` individually
pickable fonts) is bundled here as real `.woff2` files with local
`@font-face` CSS — nothing in this app fetches `fonts.googleapis.com` or
`fonts.gstatic.com` at runtime. This is a closed, fixed set: there is no
free-form "type any font name" input anywhere in the app, so every
possible font choice is already covered by what's in this directory.

- `<pairing-key>.css` (e.g. `cormorant-jost.css`) — one per `FONT_PAIRINGS`
  entry, referenced by `google_fonts_url` in that preset and in whichever
  built-in template manifests use it (`app/data/templates/*/manifest.json`).
- `choices.css` — every `GOOGLE_FONT_CHOICES` family at its default weight,
  used both by the Fonts panel's style-revealing dropdown preview and by
  any individually-picked heading/body/footer font (see
  `_google_fonts_stylesheet_url` — a browser only fetches the specific
  weight/style actually used on the page, so one shared bundle file costs
  nothing extra over a per-pick one).
- `licenses/` — the actual OFL.txt/LICENSE.txt for every bundled family,
  fetched from Google's own `google/fonts` repo. Nearly all Google Fonts
  are SIL Open Font License 1.1 (a handful, e.g. Roboto, are Apache 2.0)
  — both explicitly permit self-hosting and bundling/redistributing the
  font files with software (including selling that software), provided
  each copy carries the original copyright notice and license text (see
  the file in `licenses/` for each family) — the one thing neither
  license permits is selling a font *by itself*, which doesn't apply here.

Regenerating this bundle (e.g. adding a new `GOOGLE_FONT_CHOICES` entry or
`FONT_PAIRINGS` preset) means re-running the same fetch-parse-download
process against `https://fonts.googleapis.com/css2?family=...&display=swap`
with a real browser User-Agent (Google serves WOFF2-only `@font-face`
blocks for a modern UA, TTF+many `unicode-range` splits otherwise), then
rewriting each `src: url(...)` from `fonts.gstatic.com` to a local path.

## Filenames

Each `.woff2` is named `<family>-<NN>.woff2` — the family, then a number
per family within its folder. They arrived under the hashed names Google's
CDN serves them as, up to 132 characters of base64 identifying a build of
a font on their side, which is nothing this repository needs to know and
is not free: 132 characters plus a folder plus wherever somebody clones to
exceeds Windows' 260-character path limit, and `git clone` fails partway
through the checkout with "Filename too long", leaving a repository that
looks cloned and is not. **When adding a font, rename its files the same
way** and point the stylesheet at the new names — the stylesheet is the
only thing in this app that names a font file at all.
