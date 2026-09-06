# gmsCms — setup & usage guide

Everything after `docker compose up -d`: how to configure it, what every
admin screen does, the content tools and how to use them, and how the
project is laid out. For install and HTTPS, see the [README](../README.md).

- [1. First steps](#1-first-steps)
- [2. Configuring it](#2-configuring-it)
- [3. The admin, screen by screen](#3-the-admin-screen-by-screen)
- [4. Editing your site](#4-editing-your-site)
- [5. The tools](#5-the-tools)
- [6. Selling things](#6-selling-things)
- [7. How the project is structured](#7-how-the-project-is-structured)

---

## 1. First steps

1. **Sign in.** Go to `http://your-server:5000/admin` as `admin`. If you
   didn't set `ADMIN_PASSWORD`, the first-run password is in
   `data/initial-admin-password.txt` (and the container log). You're made
   to set your own password before anything else opens; that deletes the
   file.
2. **Walk through setup.** A bar at the top offers a short walk-through —
   the site's name, its look, who's behind it, its web address, and email.
   Every step is skippable and you can re-run it from the Dashboard. The
   **name** you set is yours permanently; trying on another template later
   changes the look and pages, never your identity.
3. **Look around.** The site already has a real template on it, so you have
   something to edit rather than a blank page.

**Two ways to work:**

- **The admin** (`/admin`) — Dashboard, Design, Commerce, Email,
  Connections, Support, Account. Settings and management.
- **The live page in edit mode** — click **View Site**, and while signed in
  you edit the actual pages: click text to change it, drag tools onto the
  page. An **Editing / Viewing** toggle in the top bar hides the edit chrome
  for a clean preview.

---

## 2. Configuring it

Everything is configured in the admin screens. `.env` only seeds the very
first boot (values are read once, copied into the database with secrets
encrypted, then ignored) — so after first run, use the screens.

### Email (SMTP)

Needed for contact-form messages, newsletters, order emails and the
double-opt-in confirmation. **Dashboard → ✉️ Email → Sending email** (or
`SMTP_*` in `.env`):

| Field | What to put |
|---|---|
| SMTP host / port | Blank defaults to `smtp.gmail.com:587` |
| Username | Your email login |
| Password | **Gmail needs an [App Password](https://support.google.com/accounts/answer/185833), not your normal password** — turn on 2-Step Verification, then generate one |
| From address | What recipients see it came from |
| Contact-to address | Where the contact form delivers |

The banner at the top of the screen tells you whether mail can send yet and
what's still missing. To check it end to end, open a newsletter or a System
email and use its **Preview** — that opens the real rendered mail.

### Connections — Stripe, Cal.com, AI

**Dashboard → 🔌 Connections.** One page, three cards. After saving a key, use
its **Test connection** button — it makes a real call and reads back something
from your own account, so a pass proves the key reaches the right place, not
just that it's well-formed. Keys are encrypted when saved and never shown back
— only whether one is set.

- **💳 Stripe** — paste your **secret key** to take payments; the
  **Commerce** tab then appears. Use the **"Create webhook in Stripe"**
  helper so Stripe can confirm payments back to your site (until that
  works, a buyer can pay and no order appears). A `sk_test_…` key is
  test-mode (Stripe's test cards, nothing charged); `sk_live_…` is live.
- **📅 Cal.com** — an API key, to sell **sessions** that a buyer books
  against one of your Cal.com meetings.
- **✨ AI** — pick a provider (**Google Gemini**, or a local **Ollama** /
  **Open WebUI**), fill its URL/key, and **Load Models** to choose the
  model from a live list. This powers the AI assistant, the ✨ Generate
  image buttons, and whole-look generation. (Image generation needs Gemini
  with billing enabled, or Open WebUI with an image backend — Ollama has no
  image API of its own.)

### Signing in with Google

**Account → Google Sign-In**: paste a Google OAuth Client ID and Secret.
Once set, admins can sign in with Google (link a Google address to an admin
under **Account → Admins**). Setting all three of
`ADMIN_GOOGLE_EMAIL` + `GOOGLE_CLIENT_ID`/`SECRET` in `.env` switches
password sign-in **off** on first boot.

### Other configuration

- **Site name & tagline, favicon, the site's web address** — Dashboard.
  The web address is learned from your first sign-in; set it explicitly
  only if you set up on one domain and serve on another.
- **Layout** — site-wide nav / sidebar / footer defaults and default
  section width (Dashboard).
- **Maintenance mode** — a holding page for visitors while you work; you
  keep seeing the real site (Dashboard).
- **Encryption key** — `data/.encryption_key` decrypts your saved API keys.
  Once live, consider moving it into `ENCRYPTION_KEY` and deleting the file,
  so a copied volume doesn't carry both halves. It is **unrecoverable** —
  keep a copy off the database backup.

---

## 3. The admin, screen by screen

The **Dashboard** (`/admin`) is a row of buttons. The top bar — on every
signed-in screen — carries **Dashboard, Account, Media Library, Help,
Support, Log out**, and the version number at its right end. Anything with
more than one screen groups them behind **tabs** along the top, and a tab is
a link (bookmark it, open it in a new window, use Back).

Secrets you enter anywhere (SMTP password, Stripe/Cal.com keys, Google
secret) are **encrypted when saved and never shown back** — a screen tells
you only whether one is set. Destructive actions (delete, restore, remove
admin) always ask first.

### 🎨 Design — five tabs

- **Pages** — every page: add, rename, reorder, set public/private, delete.
  Adding a page offers a **layout** to start from (Landing, Blog, FAQ,
  Catalogue, Process…) — a starting point that drops the right tools on an
  ordinary page, never a locked "page type". Each page has its own **Layout**
  card (hide the sidebar/footer, override nav for this page only) and an
  **SEO** card (a `meta_description`; blank auto-summarises the page).
- **Templates** — the look library. **Activate** one to apply its design (and
  optionally its example pages); **Load content** re-loads a template's own
  pages; **Save current site as a new template** captures what's on screen as
  a reusable look; export/delete. Changing a look asks before replacing your
  work; editing a page never forks anything.
- **Layout** — site-wide defaults: the nav style, whether sidebars/footer
  show, and one-click sidebar starting structures (App shell, Documentation,
  Publisher…).
- **Theme Generator** — describe your business and AI designs a whole
  coordinated look (colours, fonts, shape) and, if you want, writes the
  pages. It builds a *template* you preview and keep or throw away — nothing
  is applied to your live site until you activate it. Needs an AI connection.
- **Languages** — tick the languages visitors can switch between, then have
  AI translate the whole site; a progress table tracks it, and re-running
  only fills what's new. Your business name is never translated.

### 📰 Blog

A blog is a named set of posts (not "the blog page" — a site can have
several, shown by the Blog tool wherever you drop it). Write, edit, publish
or schedule posts; a post has a permanent address that never changes when
pages move. A published post can also be **sent as a newsletter**.

### 🖼️ Media

The Media Library: every uploaded picture and file in one place, used by the
picture-picker on every tool and screen. Upload, search, delete (a delete is
checked so you can't remove something still in use).

### 🔌 Connections

One page, three cards — this is where external services plug in. Adding a
**Stripe** secret key makes the Commerce tab appear; each card's key is
tested against the real account when you save.

- **💳 Stripe** — secret key + the **"Create webhook"** helper (until the
  webhook works, a buyer can pay and no order appears). `sk_test_…` is
  test-mode, `sk_live_…` is live.
- **📅 Cal.com** — an API key, to sell sessions booked against your meetings.
- **✨ AI** — provider (Gemini / Ollama / Open WebUI), URL/key, and **Load
  Models** to pick from a live list. Powers the assistant, ✨ Generate image,
  and the Theme Generator. (Image generation needs Gemini with billing, or
  Open WebUI with an image backend — Ollama has no image API.)

### ✉️ Email — four tabs

- **Newsletters** — write one (an ordered set of **blocks** — heading, text,
  picture, button, divider — the canvas you write into *is* the email), then
  send now or put it on a **schedule**. Below the editor, one table lists
  every newsletter written, waiting or sent. A ✨ **Write with AI** button
  drafts one for you (it never sends — you press Send). "To" chooses the
  audience (everyone confirmed, or customers only).
- **Email list** — everyone who signed up through an Email sign-up block, and
  the consent record for each (it's double opt-in — only confirmed addresses
  are ever written to). A **Customer** badge is computed live from paid
  orders. Export to a spreadsheet; erase a person (removes their consent
  record — different from unsubscribing them).
- **System emails** — the wording of the four messages the site sends itself
  (order received, a sale, a sign-up, a confirmation). The whole body is
  yours; **placeholders** (`{{items}}`, `{{total}}`, `{{link}}`, `{{access}}`…)
  drop in the facts. A live preview fills them in as you type. The sender line
  and (on list mail) the unsubscribe link are added for you and aren't
  editable.
- **Sending email** — the one SMTP account everything sends through (see §2).
  A banner tells you if it can't send yet and what's missing.

### 🛍️ Commerce — four tabs

Appears once Stripe is connected.

- **Products** — what you sell. Add one, pick a **Type** (take payment /
  sessions to book / a file to download / something to post), fill the fields
  that appear, set a picture. Each is **Available** (in the shop) or not, and
  can be **Archived** (retired in Stripe) — both ticks, with bulk actions.
  A price is immutable in Stripe, so "change the price" makes a new one and
  retires the old.
- **Orders** — every sale as a filterable table (by buyer, product, kind,
  date, status), with **CSV export**. Orders are a cache of Stripe (the
  source of truth); a keep-from date tidies old settled ones and anything can
  be re-pulled. Buyers reach purchases through an emailed link (no accounts)
  that stays valid while they still have something to use.
- **Bookings** — your diary of sessions booked against your Cal.com meetings.
- **Store settings** — your shop's **currency** (one per shop) and
  **Delivery**: weight-band prices per carrier and region (editable Swiss
  Post presets), each physical product carrying a weight, priced at checkout
  from the basket.

### ⚖️ Legal pages

Generates Terms / Refunds / Privacy / Impressum as ordinary editable pages
from your own details (name, address, country, VAT, cancellation window). It
writes what's relevant to what you actually sell, onto one **Terms &
Conditions** page by default (or a page each, needed for a German/Austrian
Impressum). A starting point, not legal advice.

### 🕒 Schedules

Named recurring times ("First Monday", "Monthly") defined once, then picked
wherever an action needs one — sending a newsletter, publishing a post,
running a backup. A second tab, **Scheduled items**, is the queue: everything
waiting, going out, done or failed. A failure is written down and left for
you (never auto-retried — nothing can tell "the mail server blinked" from
"twenty already got it").

### 💾 Backups

A copy of everything — pages, orders, customers, bookings, pictures, paid
files. **Back up now** (optionally including pictures, and — off by default —
the encryption key, only for moving machines), **automatic backups** on a
named schedule keeping the last N, and **restore** from an uploaded `.zip`
(which snapshots the current state first, so a restore is itself undoable).
Copy the important ones off the server — they live on the same volume.

### 📈 Visitors

Anonymous analytics: visits over time, top countries, top pages, for a chosen
window. No visitor or IP is stored — only per-day/country/page totals; your
own signed-in views aren't counted; country is resolved from a bundled
offline database, so nothing leaves the server.

### 📋 Activity

A log of everything the site has told you — what a template changed, what was
removed, what was sent — newest first (the flash messages that used to
vanish). Read-only.

### ♥ Support

Optional appreciation for a free tool (PayPal, or crypto with QR codes), and
the one switch for the small "Built with gmsCms" footer credit. Nothing here
is required and nothing unlocks anything.

### Account (top bar)

Who can sign in and how — everyone listed has full access. **Change Password**
(this *is* the reset flow — there's no email-a-link), **Sign-In Method**
(turn username/password off once Google works, guarded so you can't lock
yourself out), **Admins** (add/remove; the last admin and your own account
can't be removed), and **Google Sign-In** (OAuth Client ID + Secret, and the
exact redirect URI to paste into Google Cloud).

---

## 4. Editing your site

You build pages **on the live page** while signed in — there's no separate
editor.

- **Sections** are empty frames. **+ Add Section** adds a blank one. A
  frame's toolbar has **Divide** to split it into 1–6 side-by-side **cells**
  (columns); a cell can be split again into rows.
- **Content comes from tools.** Open the **🧰 Tools** panel (docked on the
  right edge in edit mode) and drag a tool into a frame or a cell — it fills
  just that cell. See [the tools](#5-the-tools).
- **Click any text to edit it** in place. The formatting toolbar has
  bold/italic/underline, lists, headings, links, alignment, fonts, colours,
  and insert image / insert icon (a big emoji picker).
- **Reorder** frames and cells by dragging the ⠿ handle.
- **Width & height** — each section sets its own width (Auto / Full /
  Custom %) from its toolbar, or drag its bottom edge to set a height (a
  ⟲ button resets it).
- **Sidebars** — up to two vertical rails (left/right) beside the
  header/body/footer. Same tool system; a sidebar holds one section (its
  Divide stacks rows). Dashboard → **Sidebar layouts** gives one-click
  starting structures (App shell, Documentation, Publisher, Workspace…).

**The three docked panels** (right edge, edit mode):

- **🧰 Tools** — the tools you drag onto the page.
- **🎨 Colors** — the active template's colour palette: pick a preset or
  fine-tune each colour. This restyles the whole site at once.
- **💬 AI Assistant** — a chat that can look at your real page content and
  **propose** edits (nothing is applied until you click **Apply**), and can
  take an attached image as guidance.

**Styling** is a click, never markup: the Colors panel and font/shape/shadow
controls reshape the whole site; select one section and use **Selection →
Corner** to shape just that one.

---

## 5. The tools

Drag any of these from the **🧰 Tools** panel onto a page frame or cell.

| Tool | What it is / does |
|---|---|
| **Text** | Rich text (WYSIWYG) — headings, lists, links, colours, fonts, icons. |
| **Image** | A picture with size, an optional caption, a cut-out shape (circle/diamond/hexagon/star), a link, animation, and an AI **✨ Generate** button. |
| **Media Player** | A YouTube link, or an uploaded video / audio file. |
| **File / Download** | A file a visitor downloads (or, for a shop, a paid download — see Commerce). |
| **Columns** | Splits a frame into side-by-side cells you fill with other tools. |
| **Table** | A data table with its own controls for rows/columns, header row, and look (bordered / striped / coloured header / plain). |
| **Menu** | A navigation menu of pages and custom links — plain / buttons / dropdown-with-submenus, several button and submenu styles, dividers and per-item icons. In a sidebar it goes vertical automatically. |
| **Breadcrumb** | A "you are here" trail; size and style options. |
| **Banner** | A background image with an overlay headline and text, an optional shape mask, and an AI **✨ Generate** button. |
| **Card** | A coloured/shaped block you write text over, with an optional custom colour or AI-generated image. |
| **Divider** | A styled horizontal rule (line style, width, spacing, colour). |
| **Image Accordion** | Five picture panels shown as hover-to-expand Panels, a Carousel, or a Masonry grid, with an optional click-to-enlarge popup. |
| **Video Gallery** | A grid of YouTube clips (a link + optional caption each), set in its own form. |
| **HTML / Embed** | Raw embed code — **only** for real third-party widgets (a Cal.com calendar, a Stripe button). Not for styling or layout; those have proper tools. |
| **FAQ** | Questions and answers written as one document, shown read-through or folded into rows. A separate **FAQ Reader** can mirror a chosen set elsewhere. |
| **Search** | A search box that filters whatever on the page is searchable (e.g. FAQ answers). |
| **Blog** | Shows a blog's posts. Choosing "Blog" when adding a page starts one for you. |
| **Contact form** | A form visitors write to you with (emailed to your contact-to address; rate-limited and spam-trapped). |
| **Contact info** | Your address / phone / email / socials, laid out. |
| **Language switcher** | Links between translated versions of the site. |

**Content blocks** (ready-made, filled in via a form — never by editing
markup): **Pricing** tiers, **Testimonial**, **Stats**, **Logos**,
**Skills / tags**, **Team**, **Timeline**, **Call-to-action**, and a
**Newsletter sign-up** (double opt-in).

**Shop tools** (once Stripe is connected): **Shop** (your product
catalogue), **Buy button** (one product), and **Basket** (a floating
cart). See [Selling things](#6-selling-things).

---

## 6. Selling things

Connect Stripe (§2) and the **Commerce** tab opens: **Products, Orders,
Bookings, Store settings**. Full walk-through with screenshots is in the
[README](../README.md#selling-things). In short:

- **Products** — add one, pick a **Type** (take payment / sessions to book
  / a file to download / something to post), and set a picture. Each is
  **Available** (shown in the shop) or not, and can be **Archived**; both
  are ticks, with bulk actions.
- **Delivery** (Store settings) — weight-band pricing per carrier and
  region (Swiss Post presets included).
- **Orders** — a filterable table with CSV export; buyers reach purchases
  through an emailed link that stays valid while they still have something
  to use.

---

## 7. How the project is structured

For developers. The app is a Flask + SQLite CMS; the tree is split by domain
so no single file becomes a monolith again.

```
app/
  routes/
    admin/            # the admin Blueprint (a package, not one file)
      __init__.py     #   shared state: settings getters, layout, tools
      dashboard.py    #   Dashboard + Design tabs + theme generator
      pages.py        #   page / blog-post CRUD, per-page layout
      sections.py     #   sections, columns, banners, cards, the Tools panel
      templates.py    #   template colours / activate / delete, packages
      settings.py     #   site/email/AI/commerce settings, admins
      assistant_routes.py  # AI assistant chat / apply
    auth.py           # login / logout / Google OAuth / account
    public.py         # the public site (pages, blog, cart, checkout, webhook)
  services/           # business logic (routes -> services -> data/db, one way)
    sections.py       # section classification, columns, cards, tools
    packages.py       # template packages (zip install / export)
    commerce.py       # orders, entitlements, access tokens, Stripe reconcile
    cart.py, downloads.py, integrations.py, shipping.py   # the shop
    blocks.py         # the declared content blocks (pricing, stats, …)
    scheduling.py, newsletter.py, subscribers.py, email_layouts.py  # email
    legal.py, seo.py, maintenance.py, site.py, palette.py, menu.py
  data/templates/<slug>/   # the 20 built-in template packages (authored form)
  templates/          # Jinja: admin/, partials/, public/, prompts/*.j2
  static/             # css/, js/ (js/admin/ for admin panels), fonts/
  db.py, crypto.py, mailer.py, ai_image.py, bootstrap.py, csrf.py
tools/                # checkers (parity, fresh_install, …), dev-only
```

Principles (see [CLAUDE.md](../CLAUDE.md) for the full reasoning):

- **Thin routes, logic in `services/`.** Services take `db` + plain args,
  never Flask request objects, so they're reusable and testable.
- **One-way imports:** `routes → services → data/db`. A service never
  imports a route.
- **Templates are structure only** — no business logic in `<script>`, no
  hand-rolled CSS in `<style>`; JS lives in `static/js/`, CSS in
  `static/css/`.
- **Features are tools, not page types** — a new capability is a tool an
  admin drops on any page, not a special kind of page.
- **Stripe is the source of truth** for products and payments; the local DB
  holds fulfilment state Stripe doesn't have (sessions used, downloads
  left).
- **Checkers** in `tools/` are the safety net under each feature; run the
  relevant one after a change (`docker compose exec web python tools/<x>_check.py`).
