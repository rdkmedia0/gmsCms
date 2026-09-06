import os
import json
import secrets
from flask import Flask, url_for, request, session
import mimetypes
from werkzeug.middleware.proxy_fix import ProxyFix
from flask.sessions import SecureCookieSessionInterface
from flask import has_request_context

from . import bootstrap
from .services import site
from . import db as db_module
from .db import init_db, get_db, DATA_DIR
from .services import packages

SECRET_KEY_PATH = os.path.join(DATA_DIR, ".secret_key")


def _get_or_create_secret_key():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w") as f:
        f.write(key)
    return key


#  Headers a reverse proxy sets about the original request. Believed
#  when a proxy plausibly sent them, and REMOVED otherwise -- not merely
#  ignored, so that nothing further in (Werkzeug, a library, a future
#  handler) can find them and reach a different conclusion.
FORWARDED_HEADERS = (
    "HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST",
    "HTTP_X_FORWARDED_PORT", "HTTP_X_FORWARDED_PREFIX",
)


def _looks_like_a_proxy(address):
    """Could the peer that sent this request be a reverse proxy?

    A proxy in front of this container reaches it over the docker network,
    the loopback interface or the LAN -- all private. A visitor arriving
    directly from the internet does not, and their X-Forwarded-Proto is
    a claim about themselves that nothing should act on.

    This is a heuristic, and it is the right one to default to because it
    is correct in both directions for every ordinary deployment: put a
    proxy in front and it is believed, expose the port and nobody can lie
    to it. TRUST_PROXY overrides it in the two cases it cannot know about
    -- a proxy reaching this from a public address, or a deployment that
    wants nothing trusted at all.
    """
    if not address:
        return False
    try:
        import ipaddress
        peer = ipaddress.ip_address(address.strip().split("%")[0])
    except ValueError:
        return False
    #  "Not reachable from the internet", which is the actual question,
    #  rather than is_private -- a list that turns out to include the
    #  documentation ranges (203.0.113.0/24 and friends) while leaving out
    #  carrier-grade NAT. is_global is the one range definition that means
    #  what this needs it to mean.
    return not peer.is_global


class TrustedProxyFix:
    """ProxyFix, but only for peers that could actually be the proxy.

    ProxyFix on its own trusts whoever it is talking to. That is correct
    with nginx in front and wrong the moment this container is reachable
    directly -- which is now a supported way to run it, so it cannot be
    left as an assumption made in a comment.
    """

    def __init__(self, wsgi_app, mode="auto"):
        self.plain = wsgi_app
        self.fixed = ProxyFix(wsgi_app, x_for=1, x_proto=1, x_host=1)
        self.mode = (mode or "auto").strip().lower()

    def trusts(self, environ):
        if self.mode == "always":
            return True
        if self.mode == "never":
            return False
        return _looks_like_a_proxy(environ.get("REMOTE_ADDR"))

    def __call__(self, environ, start_response):
        if self.trusts(environ):
            return self.fixed(environ, start_response)
        for header in FORWARDED_HEADERS:
            environ.pop(header, None)
        return self.plain(environ, start_response)


class _SchemeAwareSessions(SecureCookieSessionInterface):
    """Marks the session cookie Secure on https requests, and only those.

    `SESSION_COOKIE_SECURE` is one setting for the whole app, so turning
    it on because the site is served over https would also stop the
    cookie being sent to http://localhost:5000 -- locking the owner out
    of local admin to protect a connection they were not using. That is
    why it was left to an environment variable, and why it was then off
    on every install whose owner never read the log line saying to set it.

    Flask asks this method each time it writes the cookie, and by then
    there IS a request to ask, so the question has an honest answer:
    Secure exactly when this request came in over https. ProxyFix has
    already applied X-Forwarded-Proto, so a site behind nginx answers
    correctly. FORCE_SECURE_COOKIES=1 still pins it on regardless.
    """

    def get_cookie_secure(self, app):
        if app.config.get("SESSION_COOKIE_SECURE"):
            return True
        return bool(has_request_context() and request.is_secure)


#  Python works out a static file's Content-Type from the system's mime
#  table, and a slim base image does not have one -- so .webp came back as
#  application/octet-stream, which some browsers decline to render and
#  none of them cache as an image. Registered here rather than relied on,
#  because the alternative is a picture that works on the machine it was
#  developed on.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("font/woff2", ".woff2")


def create_app():
    app = Flask(__name__)
    # Behind a proxy, trust its X-Forwarded-* headers so url_for(_external=True)
    # (used for the Google OAuth redirect_uri) generates https://<real-domain>
    # instead of the container's own http://127.0.0.1:5000 -- and so the
    # session cookie and HSTS know the request arrived over https.
    #
    # But only from a peer that could BE a proxy: this container is also
    # meant to run with nothing in front of it, where those headers are a
    # stranger's assertion about themselves. See TrustedProxyFix.
    app.wsgi_app = TrustedProxyFix(app.wsgi_app, os.environ.get("TRUST_PROXY", "auto"))
    app.config["SECRET_KEY"] = _get_or_create_secret_key()
    app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 250 MB upload limit (video files are large)
    app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
    app.config["THEMES_FOLDER"] = os.path.join(app.static_folder, "themes")
    # Session cookie hardening: Secure means the browser never sends it over
    # plain HTTP — safe (and should stay on) once this is actually served
    # over HTTPS via nginx per docker-compose.yml, but forcing it on
    # unconditionally here would silently break login over bare HTTP
    # (e.g. testing directly against http://localhost:5000 with no proxy
    # in front) since the browser would refuse to send the cookie back at
    # all. FORCE_SECURE_COOKIES=1 opts in once nginx+HTTPS is actually in
    # front of this. SameSite=Lax stops the cookie being attached to a
    # cross-site POST at all (the first line of CSRF defense, before
    # csrf.py's Origin check even runs); HttpOnly is Flask's own default,
    # restated here for clarity.
    #  Secure cookies whenever this site is actually served over https --
    #  decided per REQUEST rather than per install (see below), because
    #  left to an environment variable it stays off on exactly the
    #  deployment that needed it most: the one nobody remembered to
    #  configure. The variable now means "always, even over http", which
    #  is the only case it can still usefully answer.
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FORCE_SECURE_COOKIES") == "1"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.session_interface = _SchemeAwareSessions()

    from .csrf import init_csrf
    init_csrf(app)

    init_db(app)
    #  Anything the owner supplied as environment is taken over into the
    #  database once, here, before seeding — so the admin created below
    #  can be checked against a Google client that arrived the same way.
    bootstrap.adopt_environment(app)
    first_boot = _seed(app)
    #  After _seed, not inside init_db's migrations, because it reads the
    #  installed packages and _seed is what installs them. Run earlier it
    #  would read the PREVIOUS build of a template and quietly do nothing
    #  until the boot after next.
    with app.app_context():
        restored = db_module._restore_opening_hours(get_db())
        get_db().commit()
        if restored:
            app.logger.info("Put opening hours back on %d page(s).", restored)
    #  The translation worker is a thread in a web process, so a restart
    #  kills it and leaves its run flagged active. Clear that here, or the
    #  Languages screen shows a phantom "translating…" and refuses a new run.
    with app.app_context():
        from .services import translation as _translation
        _translation.reset_stuck_run(get_db())
    with app.app_context():
        db = get_db()
        outcome = bootstrap.apply_password_login_policy(db)
        if outcome == "on":
            app.logger.warning("PASSWORD_LOGIN is set: username/password sign-in switched ON.")
        elif outcome == "off":
            app.logger.info("PASSWORD_LOGIN is set: username/password sign-in switched OFF.")
        elif outcome == "refused":
            app.logger.warning(
                "PASSWORD_LOGIN asks to switch username/password sign-in OFF, but Google "
                "sign-in is not usable yet (needs a client id, a secret, and an admin with a "
                "linked Google address). Left ON so nobody is locked out.")
        db.commit()
    bootstrap.tighten_permissions(app)
    bootstrap.check_storage(app)

    #  The Secure flag is one global setting, not a per-request one, so
    #  turning it on because the PUBLIC address is https would stop the
    #  cookie being sent over plain http on localhost — locking the owner
    #  out of local admin to protect a connection they were not using.
    #  So it stays an explicit choice, and the gap is named out loud
    #  rather than left to be discovered.
    with app.app_context():
        base = site.public_base(get_db())
    if base.startswith("https://") and not app.config["SESSION_COOKIE_SECURE"]:
        app.logger.warning(
            "This site's address is %s but session cookies are not marked Secure, so a "
            "downgraded http request could carry one. Set FORCE_SECURE_COOKIES=1 once you "
            "are only reaching it over https.", base)

    #  Sent on every response. None of these replace getting the code
    #  right; they limit what a mistake elsewhere can be turned into.
    CSP = "; ".join((
        "default-src 'self'",
        #  'unsafe-inline' is required by this app's own inline handlers
        #  and style attributes, so this does not stop injected inline
        #  script. It does stop injected script being LOADED from
        #  somewhere else, which is what most real payloads need.
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        #  Product pictures come from Stripe, and page images can be
        #  data: URIs from the editor.
        "img-src 'self' data: https:",
        "media-src 'self' data: https:",
        "font-src 'self'",
        "connect-src 'self'",
        #  Embeds (a video, a booking widget) are a real feature; being
        #  framed BY someone else is not, hence frame-ancestors.
        #  'self' as well as https: -- these are two different jobs in one
        #  directive. `https:` is for an embedded third party (a Cal.com
        #  booking, a Stripe button, a video), which is why it is that
        #  wide. `'self'` is for the editor's own responsive preview,
        #  which frames THIS site: over https the origin happened to
        #  match `https:` and it worked, over plain http it did not, so
        #  the preview came up empty on every install that had not put a
        #  certificate on yet. Naming the site itself says what is meant
        #  and stops depending on the scheme to say it.
        "frame-src 'self' https:",
        #  'self', not 'none': the responsive preview shows the site's own
        #  page in a frame, and a page that refuses every framer refuses
        #  itself -- the preview came up as a broken document. Another
        #  site still cannot frame this one, which is the whole point of
        #  the rule; X-Frame-Options below says the same thing to older
        #  browsers and has to agree, or the stricter of the two wins.
        "frame-ancestors 'self'",
        #  Checkout is a form that redirects to Stripe's own payment page,
        #  and form-action is enforced across the whole redirect chain --
        #  so 'self' alone silently refuses every purchase in a browser
        #  while curl, which ignores CSP, sails through.
        "form-action 'self' https://checkout.stripe.com https://pay.stripe.com",
        "base-uri 'self'",
        "object-src 'none'",
    ))

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("Content-Security-Policy", CSP)
        #  Stops a browser deciding an uploaded .png is really HTML and
        #  running it on this origin.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        #  Belt and braces with frame-ancestors, for older browsers.
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        #  Only ever sent over https, so it cannot strand a site that is
        #  served over plain http. Deliberately without includeSubDomains
        #  or preload: both are promises about names this app does not
        #  control and cannot take back quickly.
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
        #  An SVG is a document, not just a picture: open one directly and
        #  any <script> inside it runs on THIS origin, with this site's
        #  cookies. Uploads are admin-only, so this is not a stranger's
        #  way in, but "admin-only" includes an admin who was handed a
        #  logo by a client. Forcing a download stops the one dangerous
        #  case — being navigated to — while <img src="...svg"> still
        #  renders normally, because browsers ignore this header for
        #  subresources.
        if request.path.startswith("/static/uploads/") and request.path.lower().endswith(".svg"):
            response.headers["Content-Disposition"] = "attachment"
        return response

    #  There WAS an after_request here taking the scheduled backup, on
    #  the grounds that gunicorn runs several workers and a timer thread
    #  in each is more moving parts than a small site needs. That was
    #  true when it was written and is not any more: there is a poller,
    #  it is armed by the first request each worker handles, and it
    #  already runs scheduled sends and scheduled publishes with a claim
    #  that settles which worker acts.
    #
    #  Two consequences of moving, both good. A site nobody visits now
    #  backs itself up -- under the old hook it could not, and that was
    #  written down as a fair trade rather than fixed. And a backup can
    #  be booked for 3am on the first Sunday, which "every week" could
    #  never say.

    @app.after_request
    def _learn_public_address(response):
        """Notices the address this site is actually reached on.

        The alternative is asking the owner to type it, which they should
        not have to: the deployment already knows, every time a request
        arrives. Only an admin's own request teaches it (see
        services/site.remember_detected for why), and only when nothing
        has been configured explicitly.
        """
        try:
            if session.get("user_id"):
                db = get_db()
                if site.remember_detected(db, request.host_url, True):
                    db.commit()
        except Exception:  # noqa: BLE001 - never break a response over this
            pass
        return response

    app.jinja_env.filters["from_json"] = lambda s: json.loads(s) if s else None

    def static_url(filename):
        """url_for('static', ...) plus a ?v=<mtime> cache-buster. Our own
        JS/CSS get redeployed under the exact same filename every time (no
        build hash), and served with no explicit cache headers — so a
        browser (or an intermediate proxy) that already cached e.g.
        inline-editor.js from an earlier session can keep serving that
        stale copy indefinitely after a fix ships, with nothing in the
        response telling it otherwise. The mtime in the query string
        changes whenever the file's content changes, forcing a real
        refetch exactly when needed and never otherwise."""
        path = os.path.join(app.static_folder, filename)
        try:
            v = int(os.path.getmtime(path))
        except OSError:
            v = 0
        return f"{url_for('static', filename=filename)}?v={v}"

    app.jinja_env.globals["static_url"] = static_url

    #  The version, for the admin bar and the Version tool. See version.py.
    from . import version as _version
    app.jinja_env.globals["app_version"] = _version.info()

    from . import icons as _icons
    app.jinja_env.globals["icon_svg"] = _icons.render_icon
    #  A SURFACE THAT PAINTS ITSELF STATES ITS OWN INK, and a section
    #  with a background colour is the commonest surface there is: the
    #  Colour control on any section, and every band the theme generator
    #  lays down. The colour was written inline and the text left to
    #  inherit the PAGE's ink, so a pale band on a dark site -- or a
    #  brand-coloured band on a light one -- swallowed whatever stood on
    #  it. Measured on the shipped bakery and hair-salon templates: a
    #  contact row at 1.30:1 and 1.40:1.
    #
    #  Templates ask for it here rather than each one working it out,
    #  because the ones that forget are exactly the ones that break.
    from .services.palette import readable_on as _readable_on
    app.jinja_env.globals["ink_for"] = _readable_on

    #  Where anything given to an AI tool goes, for partials/ai_notice.html.
    #  A FUNCTION, not a context value: it costs a settings query, and only
    #  the handful of screens that actually send something should pay it.
    def _ai_destination():
        from .assistant import where_content_goes
        from .db import get_db
        try:
            return where_content_goes(get_db())
        except Exception:                                     # noqa: BLE001
            #  A notice that cannot be worked out must not take the page
            #  down with it -- but it must not silently claim "nothing is
            #  sent" either, so the screen shows the general form.
            return {"label": "the AI provider set up for this site",
                    "offsite": True, "ready": True}
    app.jinja_env.globals["ai_destination"] = _ai_destination

    #  The messages this app has for the owner, taken once and written
    #  down. Called by admin/base.html and nowhere else, which is what
    #  makes "record every one of them" true without touching the
    #  hundred-odd places that raise one: `flash` stays exactly as it is,
    #  and this is the single point where a flash is READ.
    def _admin_notes():
        from flask import get_flashed_messages
        from .db import get_db
        taken = get_flashed_messages(with_categories=True)
        if not taken:
            return []
        try:
            db = get_db()
            for category, message in taken:
                db.execute(
                    "INSERT INTO admin_notes (category, message) VALUES (?, ?)",
                    (category or "success", message))
            db.execute("DELETE FROM admin_notes WHERE id <= "
                       "(SELECT MAX(id) - 500 FROM admin_notes)")
            db.commit()
        except Exception:                                     # noqa: BLE001
            #  Never let the record-keeping cost somebody their message.
            pass
        return taken
    app.jinja_env.globals["admin_notes"] = _admin_notes

    from .services.sections import (
        banner_overlay_settings, banner_portrait_of, banner_portrait_size_of,
        banner_portrait_shape_of, banner_button_settings, card_style_settings, card_button_settings,
        TABLE_STYLE_CHOICES, VIDEO_GALLERY_LAYOUTS, MAX_VIDEO_GALLERY_CLIPS,
        ACCORDION_STYLES, FAQ_STYLES, MAX_FAQ_ITEMS,
    )
    app.jinja_env.globals["banner_overlay_settings"] = banner_overlay_settings
    app.jinja_env.globals["banner_portrait_of"] = banner_portrait_of
    app.jinja_env.globals["banner_portrait_size_of"] = banner_portrait_size_of
    app.jinja_env.globals["banner_portrait_shape_of"] = banner_portrait_shape_of
    app.jinja_env.globals["card_style_settings"] = card_style_settings
    app.jinja_env.globals["card_button_settings"] = card_button_settings
    app.jinja_env.globals["banner_button_settings"] = banner_button_settings
    app.jinja_env.globals["table_style_choices"] = TABLE_STYLE_CHOICES
    from .services.sections import (TOOL_TEXT_COLORS as _tool_text_colors,
                                     tool_accent_style as _tool_accent_style,
                                     BUTTON_COLORS as _button_colors)
    app.jinja_env.globals["tool_text_colors"] = _tool_text_colors
    app.jinja_env.globals["tool_accent_style"] = _tool_accent_style
    app.jinja_env.globals["button_colors"] = _button_colors
    from .services.sections import FILE_DISPLAY_CHOICES as _file_displays, FILE_EXTENSIONS as _file_exts
    app.jinja_env.globals["file_displays"] = _file_displays
    #  What the File tool's chooser offers, and the icon a file wears by
    #  its type -- both read by the tool's form in public/page.html.
    app.jinja_env.globals["file_accept"] = ",".join(_file_exts)
    app.jinja_env.globals["icon_for_file"] = _icons.file_type_icon
    app.jinja_env.globals["video_gallery_layouts"] = VIDEO_GALLERY_LAYOUTS
    app.jinja_env.globals["max_video_gallery_clips"] = MAX_VIDEO_GALLERY_CLIPS
    app.jinja_env.globals["accordion_styles"] = ACCORDION_STYLES
    app.jinja_env.globals["faq_styles"] = FAQ_STYLES
    app.jinja_env.globals["max_faq_items"] = MAX_FAQ_ITEMS

    from .routes.auth import bp as auth_bp
    from .routes.admin import bp as admin_bp
    from .routes.public import bp as public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)

    #  Scheduled sends are polled by a thread PER WORKER, armed by the
    #  first request that worker handles.
    #
    #  Not here at import time, which is where it belongs by every other
    #  measure: gunicorn runs --preload, so this function executes in the
    #  master and the workers are forked from it -- and threads do not
    #  survive a fork. A thread started here would sit in the master,
    #  where no request is ever served, and none would exist in either
    #  worker. Both of them running one is harmless: taking a job is an
    #  atomic claim, so only one can win it (see services/scheduling.py).
    @app.before_request
    def _arm_scheduled_sends():           # noqa: ANN202
        from .routes.admin.newsletters import arm_scheduler
        arm_scheduler(app)

    #  The very first boot opens the site with a look on, once there are
    #  routes for its menus to point at. See _open_with_a_look.
    if first_boot:
        with app.app_context():
            _open_with_a_look(app, get_db())

    return app


#  Which look a brand-new site opens with. Deliberately the most
#  general of the sixteen rather than the prettiest: whatever this is,
#  the owner is going to swap it, and a Family Business page makes more
#  sense to swap FROM than a tattoo studio would.
FIRST_TEMPLATE = "business"


def _open_with_a_look(app, db):
    """Activates a template the first time this site is ever created.

    Until now a new install opened on an unstyled page reading "Edit this
    page from the admin dashboard", with sixteen ready-made looks sitting
    in a library nobody had been sent to yet. For a product whose whole
    pitch is those sixteen looks, that is the worst possible first
    screen -- and it is not what the sixteen are for.

    So the site starts as a real one: a look, its pages, its layout, and
    its own name until the owner sets theirs (see _apply_pack_identity,
    which only ever fills in a placeholder).

    Guarded on FIRST BOOT, not on "nothing looks active". The difference
    matters: an existing site upgrading to this version must never have a
    template applied over the top of what somebody has written. This runs
    only in the branch that has just created the home page, which by
    definition is a site with nothing in it.
    """
    from .routes.admin import _apply_pack_content, _apply_default_layout, _apply_pack_identity
    from .routes.admin.templates import refresh_site_menus
    from .services import packages

    row = db.execute("SELECT id, slug, is_builtin FROM templates WHERE slug = ?",
                     (FIRST_TEMPLATE,)).fetchone()
    if row is None:
        row = db.execute(
            "SELECT id, slug, is_builtin FROM templates ORDER BY slug LIMIT 1").fetchone()
    if row is None:
        return  # no templates at all: nothing to open with
    pack = packages.load_template_package(app.static_folder, row["slug"], bool(row["is_builtin"]))
    #  A request context, because building the template's menus asks
    #  url_for where each page lives, and url_for outside a request needs
    #  a SERVER_NAME this app deliberately does not set.
    with app.test_request_context("/"):
        db.execute("UPDATE templates SET is_active = 0")
        db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (row["id"],))
        if pack:
            _apply_pack_identity(db, pack)
            if pack.get("pages"):
                #  force: the only thing that could be overwritten is the
                #  placeholder home page written four lines ago.
                _apply_pack_content(db, pack)
            _apply_default_layout(db, row["id"], pack, force=True)
        refresh_site_menus(db)
        db.commit()
    app.logger.info("First run: opened with the %s template. Change it on the Dashboard.",
                    row["slug"])


def _seed(app):
    with app.app_context():
        db = get_db()

        # The one admin. Its password is generated per install and told to
        # the owner through the container log and a file in the data
        # volume — never a fixed default, which on a public image is not a
        # default but a published password. See bootstrap.py.
        bootstrap.seed_admin(db, app)

        #  Every shipped package becomes a `templates` row, whether or
        #  not it has pages: a template's LOOK and its CONTENT are
        #  independent actions on any installed template.
        #
        #  They arrive as one .zip each and are installed through the same
        #  extractor and installer an uploaded package goes through --
        #  deliberately the same path, so it runs sixteen times on every
        #  boot rather than only when somebody uploads something.
        for slug, zip_path in packages.list_template_zips():
            #  adopt_manifest_overrides=False: this runs on every boot, and
            #  a re-seed must not undo the admin's own Corner/Depth/font
            #  choices by re-applying the manifest's. An import or a save
            #  still adopts them — that is the admin asking for it.
            packages.install_template_zip(db, slug, zip_path, app.static_folder,
                                          adopt_manifest_overrides=False)
        #  Every row's shipped ground, from its manifest -- including the
        #  ones the loop above skipped because their archive is unchanged,
        #  and the ones that were saved or generated here. See
        #  packages.backfill_ground_defaults for why a reinstall is not
        #  enough.
        packages.backfill_ground_defaults(db, app.static_folder)

        # One-time carry-over for installs that had the earlier per-theme
        # nav_layout column set (briefly shipped, now replaced by the
        # global settings.nav_layout above) — preserves whatever the
        # active theme's structure already was instead of silently
        # snapping every site back to "topbar" the moment this ships.
        if not db.execute("SELECT 1 FROM settings WHERE key = 'nav_layout'").fetchone():
            active_layout = db.execute(
                "SELECT nav_layout FROM templates WHERE is_active = 1"
            ).fetchone()
            if active_layout and active_layout["nav_layout"]:
                db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES ('nav_layout', ?)",
                    (active_layout["nav_layout"],),
                )

        # Default home page — guarded by the row check above; a lost race here
        # just means a duplicate home page, which INSERT OR IGNORE can't
        # prevent (no unique constraint on slug), so re-check inside a lock-
        # like pattern isn't worth it for a two-worker boot-time seed.
        page = db.execute("SELECT id FROM pages WHERE slug = ?", ("home",)).fetchone()
        first_boot = page is None
        if not page:
            cur = db.execute(
                "INSERT INTO pages (title, slug, is_home, nav_order) VALUES (?, ?, 1, 0)",
                ("Home", "home"),
            )
            page_id = cur.lastrowid
            db.execute(
                "INSERT INTO sections (page_id, type, title, content, position) VALUES (?, 'header', ?, ?, 0)",
                (page_id, "Welcome to Your Site", "Edit this page from the admin dashboard."),
            )
            db.execute(
                "INSERT INTO sections (page_id, type, title, content, position) VALUES (?, 'text', ?, ?, 1)",
                (page_id, "About", "This is a text section. Click Edit in the admin area to change this content."),
            )

        db.commit()
        #  Not here: applying a look builds the site's menus, and a menu
        #  asks url_for where each page lives -- and at this point in
        #  create_app the blueprints have not been registered, so there is
        #  no public.home to ask about. Recorded and done at the end of
        #  create_app instead.
        return first_boot
