# gmsCms — a self-hosted website builder

A simple, single-site content management system you run yourself. You build
your site **on the page** — click any heading to type, and drag tools
(text, image, gallery, columns, table, menu, banner, card, a blog, forms…)
from a toolbar straight onto the page. Styling is a click, not code: a
colour palette, fonts, and corner and shadow styles that restyle the whole
site at once. There's no separate editor and nothing to learn.

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

Three ways to run it — none needs a reverse proxy.

**1. Standalone (this container serves 443).** Get a certificate and point
`.env` at it:

```
WEB_PORT=443
TLS_CERT_FILE=/etc/letsencrypt/live/yoursite.example/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/live/yoursite.example/privkey.pem
```

Uncomment the cert mount in `docker-compose.yml`
(`- /etc/letsencrypt:/etc/letsencrypt:ro`). Certs must be readable by
uid 1000, and a renewed cert is picked up on restart.

**2. A platform terminates TLS for you.** Leave `WEB_PORT=5000`, let the
platform route to it — nothing to configure.

**3. Behind your own proxy.** Set `WEB_PORT=127.0.0.1:5000` and proxy to
it. With nginx, forward `X-Forwarded-Proto $scheme` (required — it's how
the app knows it's on HTTPS) and set `client_max_body_size 250M`. Caddy:

```
yoursite.example {
    reverse_proxy 127.0.0.1:5000
}
```

Serve it at a **domain root**, not a sub-path. If your proxy reaches the
container from a public address, set `TRUST_PROXY=always`.

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
docker compose pull && docker compose up -d      # published image
git pull && docker compose up -d --build         # from source
```

Data lives in the mounted folders, not the image; migrations run at boot.
Take a backup first. The version + commit shows at the top of every
signed-in screen.

---

## If something goes wrong

- **Locked out / lost password** — sign-ins are rate-limited 15 min; wait.
  To reset:
  ```bash
  docker compose run --rm web python -c "from app import create_app; from app.db import get_db; from werkzeug.security import generate_password_hash; app=create_app(); ctx=app.app_context(); ctx.push(); db=get_db(); db.execute('UPDATE users SET password_hash = ?', (generate_password_hash('a-new-password'),)); db.commit(); print('done')"
  ```
- **"database is locked"** — `data/` is on a network filesystem (NFS/SMB);
  move it to local disk.
- **Email not arriving** — check Settings → Email; Gmail needs an App
  Password.
- **Email links use the wrong address** — set the site's web address in
  Settings.
- **Is it running?** — `curl http://127.0.0.1:5000/healthz` (checks the DB
  too), `docker compose ps`, `docker compose logs -f web`.

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

Copyright (C) 2026 the gmsCms authors.
