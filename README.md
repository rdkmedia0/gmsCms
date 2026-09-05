# A self-hosted website, with the templates built in

A small CMS you run yourself. It ships sixteen complete looks — a bakery,
a garage, a clinic, a shop, a CV — each one a real design with its own
pages, and you edit your site **on the site**: open a page, click a
heading, type. There is no separate editor to learn.

It also does the parts a website usually needs something else for: a
blog, a newsletter with double opt-in, contact forms, a shop with Stripe,
bookings with Cal.com, legal pages written from your own details, and
scheduled backups.

---

## What you need

- **A server you control** — a VPS (IONOS, Hetzner, DigitalOcean, Linode,
  a machine at home) with Docker on it. 1 GB of RAM is enough.
- **Docker** and the Compose plugin.
- **A domain name** pointed at that server.

**Classic shared web hosting will not run this.** If your plan is the one
with a control panel and PHP, there is nowhere for a container to run.
You need a VPS, or a host that takes a Docker image.

---

## Install

```bash
git clone git@github.com:rdkmedia0/gmsCms.git mysite
cd mysite
git config core.hooksPath .githooks   # refuses commits carrying credentials
cp .env.example .env      # optional — see "Settings" below
docker compose pull
docker compose up -d
```

That pulls a ready-built image rather than compiling one — see below for
the one-time login it needs. To build from this source instead (while
developing, or to run a change you have not pushed), use
`docker compose up -d --build`, which ignores the registry entirely. It
takes a few minutes and about 2 GB of disk, most of it packing the sixteen
templates.

### Run the published image

Every push to `main` builds an image for **amd64 and arm64** and publishes
it to this repository's own registry. The package is private, like the
repository, so a host has to identify itself once:

1. Make a token at **github.com → Settings → Developer settings → Personal
   access tokens → Tokens (classic)** with the single scope
   **`read:packages`**.
2. On the host:

```bash
echo YOUR_TOKEN | docker login ghcr.io -u rdkmedia0 --password-stdin
```

That is stored in `~/.docker/config.json` and does not need repeating.
From then on:

```bash
docker compose pull && docker compose up -d
```

is the whole upgrade — no `git pull`, no build, and about 30 seconds of
downtime. `latest` follows `main`; every build is also tagged with its
commit, so `ghcr.io/rdkmedia0/gmscms:sha-<full-sha>` pins an exact one and
is the thing to roll back to.

If you would rather not hold a token on the host, clone the repository and
build from source with `--build` as above — the image is a convenience,
not a requirement.

That is the whole install. The first boot creates the database, installs
the sixteen templates, turns one of them on and creates your admin
account — so there is a real site to look at immediately, rather than an
empty page and a list of things to configure.

### Signing in the first time

If you left `ADMIN_PASSWORD` blank, one was generated for you. It is in
two places:

```bash
docker compose logs web | grep -A4 "FIRST RUN"
```

```bash
cat data/initial-admin-password.txt
```

Sign in at `http://your-server:5000/admin` as `admin`. **The first thing
it does is make you set your own password** — nothing else opens until
you have. Doing that deletes `data/initial-admin-password.txt` for you.

If you would rather choose the password up front, put it in `.env` as
`ADMIN_PASSWORD=` before the first `docker compose up`, and none of the
above applies.

### Then walk through the setup

Once you are in, the bar at the top offers a six-step walk-through: what
the site is called, how it looks, who is behind it, where it lives,
sending email, and what you have not set up yet. It takes a couple of
minutes, every step can be skipped, and you can re-run it later from the
Dashboard.

The name you give it in step one is yours permanently — trying on another
template afterwards changes the look and the pages, never your identity.

---

## HTTPS

There are three ways to run this and **none of them requires a reverse
proxy**. Pick the one that matches where it is hosted.

### 1. On its own — this container is the whole web server

Give it a certificate and let it listen on 443. Nothing else is involved.

```bash
sudo certbot certonly --standalone -d yoursite.example
```

Then in `.env`:

```
WEB_PORT=443
TLS_CERT_FILE=/etc/letsencrypt/live/yoursite.example/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/live/yoursite.example/privkey.pem
```

and mount the certificates in, by uncommenting the line already in
`docker-compose.yml`:

```yaml
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

Both variables must be set and both files must be readable by uid 1000 —
it refuses to start on half a pair rather than quietly falling back to
plain HTTP.

Two things to know about renewal. `certbot renew` wants port 80, so give
it a hook that stands this container aside for the minute it takes:

```
# /etc/letsencrypt/renewal-hooks/pre/stop-site
#!/bin/sh
cd /path/to/mysite && docker compose stop web
```

```
# /etc/letsencrypt/renewal-hooks/post/start-site
#!/bin/sh
cd /path/to/mysite && docker compose start web
```

(A DNS challenge avoids the downtime entirely if your registrar supports
one.) And a renewed certificate is only picked up on restart, which the
post-hook above already does.

**Nothing listens on port 80 in this shape**, which is deliberate — it
leaves the port free for certbot — but it means a visitor who types
`yoursite.example` into an older browser, and gets sent to `http://`,
sees a connection refused rather than your site. Most current browsers
try HTTPS first and are unaffected. If you want the redirect, that is the
one job a two-line proxy is genuinely good at (shape 3), or a `redir` line
in a Caddyfile.

### 2. On a platform that terminates TLS for you

A PaaS, a load balancer, a cloud front end. Leave `WEB_PORT` at 5000, let
the platform route to it, and there is nothing to configure: the app reads
`X-Forwarded-Proto` and behaves as though it served the HTTPS itself.

### 3. Behind a proxy you run

If you already have nginx, Caddy or Traefik, use it. Set
`WEB_PORT=127.0.0.1:5000` so the port is reachable only from that machine.

**Caddy**, which gets a certificate on its own:

```
yoursite.example {
    reverse_proxy 127.0.0.1:5000
}
```

**nginx**, with certbot for the certificate:

```nginx
server {
    listen 443 ssl;
    server_name yoursite.example;

    ssl_certificate     /etc/letsencrypt/live/yoursite.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yoursite.example/privkey.pem;

    # 250 MB, matching the app's own upload limit — video files are large.
    client_max_body_size 250M;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;   # required
        proxy_read_timeout 2000s;   # AI video generation is slow
    }
}
```

`X-Forwarded-Proto` is not optional in this shape. It is how the app knows
it is being served over HTTPS, and that decides three things: the session
cookie gets its `Secure` flag, an HSTS header is sent, and the links it
emails out are built with `https://`.

### Who is allowed to say what the request was

Those `X-Forwarded-*` headers are believed **only from a private or
loopback peer** — a proxy on this machine, this docker network, or the
LAN. From anyone else they are stripped, so a container exposed directly
to the internet cannot be told by a visitor that their request was
something it was not. Shapes 2 and 3 work; shape 1 cannot be lied to.

If your proxy or load balancer reaches this container from a *public*
address, set `TRUST_PROXY=always`. To trust nothing at all, `never`.

Serve it at a **domain root**, not a sub-path like `/blog`.

---

## Settings

Everything is configurable from the admin screens. `.env` exists only so
you can fill things in on a server you have not opened a browser on yet —
**every value is read once, on the first boot**, copied into the site's
own database (secrets encrypted), and ignored from then on. Editing `.env`
later does nothing; use the admin screens.

`.env.example` has the full annotated list. The ones that matter most:

| | |
|---|---|
| `ADMIN_PASSWORD` | choose your own instead of being given one |
| `ADMIN_GOOGLE_EMAIL` + `GOOGLE_CLIENT_ID`/`SECRET` | sign in with Google — setting all three switches password sign-in off |
| `SMTP_*` | sending email: contact forms, newsletters, order receipts |
| `STRIPE_SECRET_KEY` | taking payments |
| `ENCRYPTION_KEY` | see below — worth doing once you are live |

---

## Backing up

Three directories hold everything, and all three sit next to
`docker-compose.yml`:

| | |
|---|---|
| `data/` | the database, the encryption key, the session key, backups |
| `uploads/` | every picture and file you have uploaded |
| `themes/` | installed and saved templates |

The app takes its own scheduled backups (Dashboard → Backups) into
`data/backups/` as `.zip` archives, and restores one from the same screen.
Copy them off the server: a backup on the same disk is not a backup.

**Do not copy `data/cms.db` while the site is running.** The database runs
in WAL mode, so that file on its own is missing recent writes. Use the
app's own backup, which takes a consistent copy.

**`data/.encryption_key` is unrecoverable.** It decrypts your saved API
keys. Lose it and nothing looks broken — the site simply reports every
integration as "not connected" and you re-enter each key. Keep a copy
somewhere other than the backup holding the database (backups exclude the
key by default for exactly this reason). Once you are live, consider
moving it out of `data/` altogether: put its contents in `ENCRYPTION_KEY`
and delete the file, so anyone who copies the volume has only one half.

---

## Upgrading

Running the published image:

```bash
docker compose pull && docker compose up -d
```

Building from source instead:

```bash
git pull && docker compose up -d --build
```

Your data lives in the mounted directories, not in the image. Migrations
run at boot. Take a backup first anyway.

**Which version is running?** The bar at the top of every signed-in
screen ends with it — `v0.9.0 (53e3520)`, the number from the `VERSION`
file and, for a published image, the commit it was built from. Compare
it with the latest commit on `main` to know whether a pull is due.

---

## The line under the footer

gmsCms is free. Every site it builds shows one small line under its
footer — *"Built with gmsCms, which is free to use. Site owners can
remove this line by supporting the project."* — and that is the one
thing it asks for. **Admin → ♥ Support** has the link to say thanks and
a box for the supporter's key that removes the line for the period the
support covers. The key is checked on your own server (`data/
license.json`, beside the database, so it survives an upgrade); nothing
is sent anywhere. When the key runs out the line comes back by itself.
The same screen removes a key again.

---

## Is it running?

```bash
curl http://127.0.0.1:5000/healthz
```

```bash
docker compose ps
```

```bash
docker compose logs -f web
```

`/healthz` touches the database, so it answers `unhealthy` (503) if the
data volume did not mount — the failure that otherwise looks like a
perfectly healthy container serving a broken site. Docker asks it every
30 seconds, and `restart: unless-stopped` acts on the answer.

---

## If something goes wrong

**Locked out.** Failed sign-ins are rate-limited per IP for 15 minutes;
wait it out. If the password is genuinely lost, set a new one directly:

```bash
docker compose run --rm web python -c "from app import create_app; from app.db import get_db; from werkzeug.security import generate_password_hash; app=create_app(); ctx=app.app_context(); ctx.push(); db=get_db(); db.execute('UPDATE users SET password_hash = ?', (generate_password_hash('a-new-password'),)); db.commit(); print('done')"
```

**"database is locked".** Should not happen — WAL plus a 30-second wait
covers normal contention. If it does, `data/` is probably on a network
filesystem (NFS, SMB), where WAL cannot work. Move it to local disk.

**Email is not arriving.** Settings → Email, then the send log under
Newsletters. Gmail needs an App Password, not your account password.

**Links in emails point at the wrong address.** Settings → the site's web
address. The site learns it from the first admin request, so if you set it
up on one address and serve it on another, set it explicitly.

---

## What this is not

- **Not multi-tenant.** One install is one website, by design.
- **Not clustered.** SQLite on one machine. It will comfortably serve a
  small business site; it is not built to run behind a load balancer with
  several containers sharing one database.
- **Not a certificate authority.** It will serve a certificate you
  give it, but it does not obtain or renew one — that is certbot's
  job, or your proxy's, or your platform's.
- **Admin is a trusted role.** Anyone with an admin login can enter raw
  HTML through the Embed tool. Do not hand out admin accounts you would
  not hand the server to.
