# gmsCms — a self-hosted website builder

A simple, single-site content management system you run yourself. You build
your site **on the page** — click any heading to type, and drag tools
(text, image, gallery, columns, table, menu, banner, card, a blog, forms…)
from a toolbar straight onto the page. Styling is a click, not code: a
colour palette, fonts, and corner and shadow styles that restyle the whole
site at once. There's no separate editor — what you see is the site.

Helpers do the heavy lifting when you want them: **generate an image** from
a few words, **draft or rewrite copy** with the built-in AI assistant, or
**generate a whole coordinated look**. And if you'd rather start from
something finished, **20 ready-made designs** ship with it — edit over one,
or save your own site as a reusable template.

It also covers what a site usually needs a plugin for: a blog, a newsletter
(double opt-in), contact forms, a shop with Stripe, bookings with Cal.com,
SEO, a maintenance page, legal pages built from your own details, and
scheduled backups.

---

## What you need

- A **server you control** — a VPS (Hetzner, DigitalOcean, Linode, a box
  at home) with **Docker** and the Compose plugin. 1 GB RAM is enough.
- A **domain** pointed at it.

Classic shared/PHP hosting won't run this — you need somewhere a container
can run.

---

## Install

You run a **pre-built image** — no source to compile, no toolchain. All you
need is Docker and the compose file:

```bash
mkdir mysite && cd mysite
curl -O https://raw.githubusercontent.com/rdkmedia0/gmsCms/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/rdkmedia0/gmsCms/main/.env.example   # optional — see Settings
docker compose pull
docker compose up -d
```

### First sign-in

If you didn't set `ADMIN_PASSWORD` in `.env`, one was generated:

```bash
cat data/initial-admin-password.txt
```

Sign in at `http://your-server:5000/admin` as `admin`. It makes you set
your own password first, then deletes that file. A short setup walk-through
(name, look, contact, address, email) runs at the top of the screen — every
step is skippable.

> **New here?** The [guide](#guide) further down walks through configuring
> email and integrations, every admin screen, all the content tools, and how
> the project is laid out.

---

## What it does

- **Build on the page** — click text to change it; drag tools (Text, Image,
  Media, Columns, Table, Menu, Banner, Card, Divider, FAQ, Search, Embed…)
  onto any page or column. No code, no separate editor.
- **Style with a click** — a colour palette, font pairings, and corner and
  shadow styles that reshape the whole site at once, or one section on its
  own.
- **AI helpers** — generate a product or banner image from a description,
  ask the built-in assistant to draft or reword content, or generate a
  whole coordinated look (colours, fonts, shape) from a brief or a picture.
  Connect a provider (Gemini, or a local Ollama / Open WebUI) under
  **Dashboard → 🔌 Connections → AI**; without one, these simply aren't
  offered.
- **Start from a template, or your own** — try on any of the 20 built-in
  looks (your name and details always stay yours), or save your current
  site as a reusable template.
- **Blog, newsletter, contact forms** — the newsletter is double opt-in
  with an unsubscribe link; forms email you.
- **Shop with Stripe** — see below.
- **Bookings** — sell sessions that a buyer books against a Cal.com meeting.
- **SEO, maintenance mode, legal pages, backups** — all from the admin.

### Selling things

Add your Stripe secret key — **Dashboard → 🔌 Connections → Stripe**, or
`STRIPE_SECRET_KEY` in `.env` — and the **Commerce** tab opens (Products,
Orders, Bookings, Store settings). You never touch the Stripe dashboard.

**Products.** Add one, choose a **Type** (take payment / sessions to book /
a file to download / something to post), fill the fields that appear, and
set a picture (upload, Media Library, or AI). Each product is **Available**
(shown in the shop) or not, and can be **Archived** (retired in Stripe) —
both are ticks, and you can archive/restore in bulk. Nothing is deleted.

![Products screen](docs/screenshots/products.png)

**Delivery** is by weight, region and carrier. Under **Commerce → Store
settings → Delivery** you set up services with weight-band prices (editable
Swiss Post presets included) for a region (Switzerland, Europe, UK, USA,
North America, Worldwide), and each physical product carries a weight.
Checkout prices it from the basket weight.

![Delivery services](docs/screenshots/delivery.png)

**Orders** are a filterable table you can **export to CSV**. Buyers get a
link by email (no accounts) that stays valid while they still have a
session or download to use. Orders are a cache of Stripe; a keep-from date
tidies settled old ones and anything can be re-pulled.

![Orders ledger](docs/screenshots/orders.png)

---

## HTTPS

Your site needs to be reached at `https://yoursite.example` (the padlock),
which takes a certificate. Pick the situation that matches yours.

**A. Your hosting already gives you HTTPS** (a platform with a load
balancer in front, e.g. Railway, Fly, Coolify). Nothing to do — leave
`WEB_PORT=5000` and let the platform route to it.

**B. A plain server — the easy way.** Put **Caddy** in front: a small web
server that fetches the certificate itself, renews it, and passes visitors
through to gmsCms. In `.env` set `WEB_PORT=127.0.0.1:5000` (so only Caddy
can reach the app), [install Caddy](https://caddyserver.com/docs/install),
and put this in `/etc/caddy/Caddyfile`:

```
yoursite.example {
    reverse_proxy 127.0.0.1:5000
}
```

Then `sudo systemctl reload caddy`. Done — certificates are automatic from
here on. (Using nginx instead? Pass `X-Forwarded-Proto $scheme` and set
`client_max_body_size 250M`.)

**C. A plain server — no extra software.** The container serves HTTPS
itself from a certificate you provide. Get one from Let's Encrypt while the
container is stopped (it needs port 80 for a minute):

```bash
docker compose down && sudo certbot certonly --standalone -d yoursite.example && docker compose up -d
```

Point `.env` at it:

```
WEB_PORT=443
TLS_CERT_FILE=/etc/letsencrypt/live/yoursite.example/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/live/yoursite.example/privkey.pem
```

and in `docker-compose.yml` uncomment the line
`- /etc/letsencrypt:/etc/letsencrypt:ro`. The app runs as user **1000** and
must be able to read both files — it refuses to start and names the file if
it can't. Certificates expire every 90 days: repeat the `certbot` line above
to renew, then `docker compose restart`.

Whichever you choose, serve it at the **domain root**
(`https://yoursite.example`), not a sub-path. In B, if your proxy is on a
different machine and reaches this one over a public address, add
`TRUST_PROXY=always` to `.env`.

---

## Settings

Everything is set from the admin screens. `.env` is only for the very first
boot: every value is read once, copied into the database (secrets
encrypted), then ignored — editing `.env` later does nothing.

`.env.example` lists them all. The ones that matter:

| | |
|---|---|
| `ADMIN_PASSWORD` | set your own instead of a generated one |
| `SMTP_*` | send email (contact forms, newsletters, receipts) |
| `STRIPE_SECRET_KEY` | take payments |
| `ENCRYPTION_KEY` | decrypts saved keys — see Backups |
| `ADMIN_GOOGLE_EMAIL` + `GOOGLE_CLIENT_ID`/`SECRET` | sign in with Google |

---

## Backups

Everything lives in three folders next to `docker-compose.yml`:

| | |
|---|---|
| `data/` | database, keys, backups |
| `uploads/` | uploaded pictures and files |
| `themes/` | installed/saved templates |

Take backups from **Dashboard → Backups** (into `data/backups/`) and copy
them **off the server**. Don't copy `data/cms.db` while running (WAL mode —
it's missing recent writes); the app's backup takes a consistent copy.

`data/.encryption_key` decrypts your saved API keys and is
**unrecoverable** — keep a copy somewhere other than the DB backup.

---

## Upgrading

```bash
docker compose pull && docker compose up -d
```

Data lives in the mounted folders, not the image; migrations run at boot.
Take a backup first. The version + commit shows at the top of every
signed-in screen.

---

## If something goes wrong

- **Locked out / lost password** — sign-ins are rate-limited 15 min; wait.
  Forgotten entirely? Another admin can remove and re-add your account
  under **Account → Admins**. If there's no other admin, run this on the
  server:
  ```bash
  docker compose run --rm web python -m app.recover_admin admin
  ```
  It works exactly like day one: a new one-use password is printed and
  saved to `data/initial-admin-password.txt`, you're made to set your own
  on first sign-in, and the file is deleted. It also turns password
  sign-in back on if you'd switched to Google-only, and signs everyone out
  at the next `docker compose restart`. Nothing is typed on the command
  line, and nobody else's password changes.
- **"database is locked"** — `data/` is on a network filesystem (NFS/SMB);
  move it to local disk.
- **Email not arriving** — check Settings → Email; Gmail needs an App
  Password.
- **Email links use the wrong address** — set the site's web address in
  Settings.
- **Is it running?** — `curl http://127.0.0.1:5000/healthz` (checks the DB
  too), `docker compose ps`, `docker compose logs -f web`.

---

## Guide

Everything after `docker compose up -d`: how to configure it, what every
admin screen does, the content tools and how to use them, and how the
code is laid out.

- [1. First steps](#1-first-steps)
- [2. Configuring it](#2-configuring-it)
- [3. The admin, screen by screen](#3-the-admin-screen-by-screen)
- [4. Editing your site](#4-editing-your-site)
- [5. The tools](#5-the-tools)
- [6. How the project is structured](#6-how-the-project-is-structured)

---

### 1. First steps

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

### 2. Configuring it

Everything is configured in the admin screens. `.env` only seeds the very
first boot (values are read once, copied into the database with secrets
encrypted, then ignored) — so after first run, use the screens.

#### Email (SMTP)

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

#### Connections — Stripe, Cal.com, AI

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

#### Signing in with Google

**Account → Google Sign-In**: paste a Google OAuth Client ID and Secret.
Once set, admins can sign in with Google (link a Google address to an admin
under **Account → Admins**). Setting all three of
`ADMIN_GOOGLE_EMAIL` + `GOOGLE_CLIENT_ID`/`SECRET` in `.env` switches
password sign-in **off** on first boot.

#### Other configuration

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

### 3. The admin, screen by screen

The **Dashboard** (`/admin`) is a row of buttons. The top bar — on every
signed-in screen — carries **Dashboard, Account, Media Library, Help,
Support, Log out**, and the version number at its right end. Anything with
more than one screen groups them behind **tabs** along the top, and a tab is
a link (bookmark it, open it in a new window, use Back).

Secrets you enter anywhere (SMTP password, Stripe/Cal.com keys, Google
secret) are **encrypted when saved and never shown back** — a screen tells
you only whether one is set. Destructive actions (delete, restore, remove
admin) always ask first.

#### 🎨 Design — five tabs

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

#### 📰 Blog

A blog is a named set of posts (not "the blog page" — a site can have
several, shown by the Blog tool wherever you drop it). Write, edit, publish
or schedule posts; a post has a permanent address that never changes when
pages move. A published post can also be **sent as a newsletter**.

#### 🖼️ Media

The Media Library: every uploaded picture and file in one place, used by the
picture-picker on every tool and screen. Upload, search, delete (a delete is
checked so you can't remove something still in use).

#### 🔌 Connections

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

#### ✉️ Email — four tabs

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
- **Sending email** — the one SMTP account everything sends through (see *Configuring it* above).
  A banner tells you if it can't send yet and what's missing.

#### 🛍️ Commerce — four tabs

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
  from the basket — and how far ahead a buyer can book a session (they
  page through the calendar a month at a time, up to that limit).

#### ⚖️ Legal pages

Generates Terms / Refunds / Privacy / Impressum as ordinary editable pages
from your own details (name, address, country, VAT, cancellation window). It
writes what's relevant to what you actually sell, onto one **Terms &
Conditions** page by default (or a page each, needed for a German/Austrian
Impressum). A starting point, not legal advice.

#### 🕒 Schedules

Named recurring times ("First Monday", "Monthly") defined once, then picked
wherever an action needs one — sending a newsletter, publishing a post,
running a backup. A second tab, **Scheduled items**, is the queue: everything
waiting, going out, done or failed. A failure is written down and left for
you (never auto-retried — nothing can tell "the mail server blinked" from
"twenty already got it").

#### 💾 Backups

A copy of everything — pages, orders, customers, bookings, pictures, paid
files. **Back up now** (optionally including pictures, and — off by default —
the encryption key, only for moving machines), **automatic backups** on a
named schedule keeping the last N, and **restore** from an uploaded `.zip`
(which snapshots the current state first, so a restore is itself undoable).
Copy the important ones off the server — they live on the same volume.

#### 📈 Visitors

Anonymous analytics: visits over time, top countries, top pages, for a chosen
window. No visitor or IP is stored — only per-day/country/page totals; your
own signed-in views aren't counted; country is resolved from a bundled
offline database, so nothing leaves the server.

#### 📋 Activity

A log of everything the site has told you — what a template changed, what was
removed, what was sent — newest first (the flash messages that used to
vanish). Read-only.

#### ♥ Support

Optional appreciation for a free tool (PayPal, or crypto with QR codes), and
the one switch for the small "Built with gmsCms" footer credit. Nothing here
is required and nothing unlocks anything.

#### Account (top bar)

Who can sign in and how — everyone listed has full access. **Change Password**
(this *is* the reset flow — there's no email-a-link), **Sign-In Method**
(turn username/password off once Google works, guarded so you can't lock
yourself out), **Admins** (add/remove; the last admin and your own account
can't be removed), and **Google Sign-In** (OAuth Client ID + Secret, and the
exact redirect URI to paste into Google Cloud).

**If a password is forgotten**, there are three ways back in, most
convenient first: sign in with Google if you linked it; have another admin
remove and re-add your account; or, with server access, run
`docker compose run --rm web python -m app.recover_admin <username>` —
it issues a new one-use password exactly like the first boot did (see *If something
goes wrong* above). Before going live, set up at least one
of the first two.

---

### 4. Editing your site

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
- **🎨 Colors** — the active template's colour palette (pick a preset or
  fine-tune each colour), the page **Background** colour (any colour —
  the text and everything else are re-coloured to stay readable on it),
  corners, composition and depth. Each restyles the whole site at once.
- **💬 AI Assistant** — a chat that can look at your real page content and
  **propose** edits (nothing is applied until you click **Apply**), and can
  take an attached image as guidance.

**Styling** is a click, never markup: the Colors panel and font/shape/shadow
controls reshape the whole site; select one section and use **Selection →
Corner** to shape just that one.

---

### 5. The tools

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
cart). See [Selling things](#selling-things).

---

### 6. How the project is structured

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

Principles:

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

---

## Support the project — buy me a coffee ☕

gmsCms is free and always will be. If it saved you the cost of a hosted
site and you'd like to say thanks, a coffee is welcome — a gift, never
required, and it unlocks nothing.

<p align="center">
  <a href="https://www.paypal.com/paypalme/rdkmedia0"><img src="https://img.shields.io/badge/PayPal-Buy%20me%20a%20coffee-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Donate with PayPal"></a>
  &nbsp;
  <a href="https://github.com/rdkmedia0/gmsCms"><img src="https://img.shields.io/github/stars/rdkmedia0/gmsCms?style=for-the-badge&logo=github&logoColor=white&label=Star&color=444" alt="Star on GitHub"></a>
</p>

<table align="center">
  <tr>
    <td align="center" width="280">
      <img src="docs/qr-btc.png" width="180" alt="Bitcoin address QR code"><br>
      <b>Bitcoin</b><br>
      <code>bc1qkxc695rp49sjjuj2egwhp3k8w4we0359z0vmux</code>
    </td>
    <td align="center" width="280">
      <img src="docs/qr-eth.png" width="180" alt="Ethereum / EVM address QR code"><br>
      <b>Ethereum / EVM</b><br>
      <code>0xa2e66631f91673d549ae295773ca7fe7c60e7b76</code>
    </td>
  </tr>
</table>

<p align="center"><sub>Scan with a wallet app. ETH on Ethereum or Base, or POL on Polygon — the network's own coin only, not tokens.<br>The admin's <b>♥ Support</b> screen shows the same, plus a switch for the small footer credit. A star, an issue or a PR is just as welcome.</sub></p>

---

## License

Free software under the **GNU Affero General Public License v3.0**
(AGPL-3.0) — see [LICENSE](LICENSE). Run a modified version as a network
service and you must offer your users the source of your changes.

Copyright (C) 2026 [rdkmedia0](https://github.com/rdkmedia0).
