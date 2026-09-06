"""Template Packages — the single format for "a starting point for a site."

A package is a directory under PACKAGES_DIR (built-in, shipped with the
app) or under an install's app/static/themes/<slug>/ (admin-imported or
saved from the live site, in the persistent volume). Every package becomes
a `templates` row (see install_theme_package) whether or not it ships a
pages/ directory — a template's LOOK (activate) and its CONTENT (load)
are independent actions available on any installed template, not two
different kinds of package.

This module only reads/writes packages and the `templates` table's theme
fields. It does not know about pages/sections — that's
_apply_pack_content's job in routes/admin/__init__.py, fed by
load_template_package()'s output.
"""
import os
import re
import json
import shutil
import sqlite3
import tempfile
import zipfile

from .tools import export_all_custom_tools, import_tools

#  Where the shipped templates are AUTHORED. Present in the source tree
#  and in the build, absent from the running image: build_template_zips
#  turns each folder here into one archive, and the app installs those.
PACKAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "templates")

# Every template gets a customizable color palette, not just the ones
# whose own package happens to declare one — a package with no "palette"
# key at all (an admin-uploaded theme that skipped it) still has plenty to
# recolor across site-base.css (Menu buttons, Card/Banner accents, the
# File tool's button/link, a body-text hyperlink, ...) via the --primary/
# --primary-dark bridge public.py's _theme_override_css always emits for
# the resolved primary color. `secondary` is a deeper shade of primary
# (cohesion — depth/hover states); `accent` is chosen as its genuine
# complementary contrast (roughly opposite on the color wheel — blue's
# complement is orange) rather than another shade of the same hue, so a
# highlight/accent use actually stands out. Matches the same "#2563eb"
# site-base.css falls back to today when there's no override at all.
DEFAULT_PALETTE = [
    {"slug": "primary", "name": "Primary", "color": "#2563eb"},
    {"slug": "secondary", "name": "Secondary", "color": "#1e3a8a"},
    {"slug": "accent", "name": "Accent", "color": "#f97316"},
]


#  Built templates, one .zip each, produced from PACKAGES_DIR at image
#  build time (see build_template_zips) and installed at first boot.
#  Shipping the zip rather than the loose folder means the templates that
#  come with the app arrive exactly the way somebody else's template
#  arrives — same archive, same extractor, same installer — so the road a
#  stranger's package travels is the one that gets used sixteen times on
#  every boot instead of only when somebody uploads something.
PACKAGE_ZIPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "template-packages")

#  Zip entries carry a modification time, and a build that stamps the
#  clock into them produces a different archive every time from identical
#  sources. Fixed, so the same templates always build the same bytes:
#  that is what lets a boot decide "this is the package I already
#  installed" by hash, and what keeps two hosts byte-identical.
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)


TEMPLATE_MEDIA_URL = re.compile(r"^/static/themes/([A-Za-z0-9_.-]+)/media/([A-Za-z0-9_.-]+)$")


def adopt_template_picture(url, static_folder, upload_folder):
    """A picture the owner CHOSE from a template becomes theirs.

    Every template keeps its own pictures, which is what makes a package
    portable — but a page that points into a template's folder only works
    while that template is installed. Delete the template and the page
    404s: proven, and permanent for an imported or saved template (a
    builtin's folder comes back at the next boot, which merely makes the
    breakage temporary rather than acceptable).

    So the moment somebody picks one for their own content, it is copied
    into the library and the copy is what gets stored. One extra file per
    choice, against a page that no longer depends on a template's
    lifetime. Deliberately NOT done when a template applies its own
    content — that would copy every picture of every template anyone ever
    activated into the uploads folder.

    Returns the URL to store: the new copy's, or the original unchanged
    if it was not a template picture.
    """
    m = TEMPLATE_MEDIA_URL.match((url or "").strip())
    if not m:
        return url
    slug, filename = m.group(1), m.group(2)
    src = os.path.join(static_folder, "themes", slug, "media", filename)
    if not os.path.isfile(src):
        return url
    ext = os.path.splitext(filename)[1].lower()
    import uuid as _uuid
    unique = f"{_uuid.uuid4().hex}{ext}"
    try:
        os.makedirs(upload_folder, exist_ok=True)
        shutil.copyfile(src, os.path.join(upload_folder, unique))
    except OSError:
        return url          # cannot copy: better the template's copy than nothing
    return f"/static/uploads/{unique}"


def copy_tree_contents(src_dir, dst_dir):
    """Copy a directory's files into another, contents only.

    Deliberately not shutil.copytree, even with copy_function: it also
    stamps the source's permissions and modification time onto every
    destination, directories included, and that is both meaningless here
    (these files came out of a temporary extraction moments ago) and
    fatal, because writing metadata onto something owned by another user
    fails outright — which is what reinstalling a template over its own
    earlier copy does, and what a volume that refuses chown does even to
    root.
    """
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        os.makedirs(target, exist_ok=True)
        for fname in files:
            shutil.copyfile(os.path.join(root, fname), os.path.join(target, fname))


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(131072), b""):
            h.update(chunk)
    return h.hexdigest()


def write_install_json(pkg_dir):
    """Freeze a folder's own account of itself, beside it.

    A shipped template gets this written INTO its zip at build time. A
    promoted one has no zip -- it lives in `static/themes/<slug>/` -- so
    the same description is written into the folder, and export picks it
    up from there like any other file. Same inventory, same question
    answered before installing: what is this about to do to my site?
    """
    inventory = package_inventory(pkg_dir)
    with open(os.path.join(pkg_dir, "install.json"), "w", encoding="utf-8") as fh:
        json.dump(inventory, fh, indent=2, ensure_ascii=False, sort_keys=True)
    return inventory


def package_inventory(pkg_dir):
    """What installing this package will actually do, as data.

    A zip is opaque until something opens it, and "what am I about to let
    into my site?" is a fair question to be able to answer before
    answering it. So the archive carries its own account of itself: every
    page and how many sections it holds, every picture with its size and
    checksum, the layout it will apply, whether it brings a theme. The
    installer does not depend on this file — it is a description, not a
    second source of truth, and a package without one still installs.
    """
    manifest = {}
    manifest_path = os.path.join(pkg_dir, "manifest.json")
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

    pages, sections_total = [], 0
    pages_dir = os.path.join(pkg_dir, "pages")
    if os.path.isdir(pages_dir):
        for fname in sorted(os.listdir(pages_dir)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(pages_dir, fname), encoding="utf-8") as f:
                spec = json.load(f)
            count = len(spec.get("sections") or [])
            sections_total += count
            pages.append({"file": fname, "title": spec.get("title"),
                          "slug_suffix": spec.get("slug_suffix"),
                          "page_type": spec.get("page_type") or "standard",
                          "sections": count})

    media = []
    media_dir = os.path.join(pkg_dir, "media")
    if os.path.isdir(media_dir):
        for fname in sorted(os.listdir(media_dir)):
            full = os.path.join(media_dir, fname)
            if os.path.isfile(full):
                media.append({"file": fname, "bytes": os.path.getsize(full),
                              "sha256": _sha256(full)})

    def _count(name, key=None):
        path = os.path.join(pkg_dir, name)
        if not os.path.isfile(path):
            return 0
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if key:
            data = data.get(key) or []
        return len(data)

    return {
        "format": 1,
        "slug": manifest.get("slug"),
        "name": manifest.get("name"),
        "description": manifest.get("description"),
        "installs": {
            "theme_css": os.path.isfile(os.path.join(pkg_dir, "theme.css")),
            "palette": len(manifest.get("palette") or []),
            "fonts": manifest.get("google_fonts_url"),
            "layout": {k: manifest.get(k) for k in
                       ("nav_layout", "page_layout", "footer_layout",
                        "header_menu", "sidebar_widget")},
            "identity": {k: manifest.get(k) for k in
                         ("business_name", "tagline", "footer_blurb", "footer_contact")},
            "pages": pages,
            "zone_sections": _count("zones.json"),
            "blog_posts": _count("blog_posts.json"),
            "tools": _count("tools.json", "tools"),
            "media": media,
        },
        "totals": {
            "pages": len(pages),
            "sections": sections_total,
            "media": len(media),
            "media_bytes": sum(m["bytes"] for m in media),
        },
    }


def write_package_zip(pkg_dir, dest_path):
    """Zip a package directory whole, with its inventory inside it.

    Everything the package holds goes in — manifest, theme, palette,
    pages, pictures, zones, tools — because the thing being built is the
    template, and a template that has to be completed from somewhere else
    at the far end is the problem this replaces.
    """
    inventory = package_inventory(pkg_dir)
    entries = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, pkg_dir).replace(os.sep, "/")
            if rel != "install.json":
                entries.append((rel, full))
    entries.sort()

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp = dest_path + ".building"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("install.json", date_time=ZIP_EPOCH)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True))
        for rel, full in entries:
            info = zipfile.ZipInfo(rel, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as f:
                zf.writestr(info, f.read())
    os.replace(tmp, dest_path)
    return inventory


def list_template_zips(zips_dir=None):
    """The templates this image ships, as (slug, path) pairs."""
    zips_dir = zips_dir or PACKAGE_ZIPS_DIR
    if not os.path.isdir(zips_dir):
        return []
    return [(f[:-4], os.path.join(zips_dir, f))
            for f in sorted(os.listdir(zips_dir)) if f.endswith(".zip")]


INSTALLED_STAMP = ".installed-from"


def _drop_stale_media(zip_path, installed_dir):
    """Remove pictures the installed copy has and the archive does not.

    Extracting a package ADDS files; it never takes any away. So a
    template whose pictures changed format left every old one behind, on
    every install that had ever run the earlier version -- 77 orphaned
    PNGs on one site, referenced by nothing, doubling the Media Library
    and making the image picker show every picture twice.

    Reading a zip's index is cheap (no extraction), so this runs even on
    the boots that skip reinstalling, which is what lets an install
    already carrying the leftovers clean itself up. Only `media/`, and
    only files: nothing else in the folder is the archive's to own, and a
    stamp or a saved copy must survive.
    """
    media_dir = os.path.join(installed_dir, "media")
    if not os.path.isdir(media_dir):
        return 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            keep = {os.path.basename(n) for n in zf.namelist()
                    if n.startswith("media/") and not n.endswith("/")}
    except (OSError, zipfile.BadZipFile):
        return 0
    if not keep:
        return 0
    removed = 0
    for name in os.listdir(media_dir):
        path = os.path.join(media_dir, name)
        if name in keep or not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


def install_template_zip(db, slug, zip_path, static_folder, adopt_manifest_overrides=False):
    """Install one shipped template from its zip, through the same
    extractor an uploaded package goes through.

    Skipped when the same archive is already unpacked in place: this runs
    for every template on every boot, and unpacking ninety megabytes each
    time to arrive back where it started is a slow start for nothing. The
    stamp records the archive, not the date, so a rebuilt image with an
    edited template reinstalls it and an unchanged one does not. A
    template somebody deleted has no row, so it is reinstalled whatever
    the stamp says — that is how a builtin comes back.
    """
    digest = _sha256(zip_path)
    installed_dir = os.path.join(static_folder, "themes", slug)
    stamp = os.path.join(installed_dir, INSTALLED_STAMP)
    row = db.execute("SELECT id FROM templates WHERE slug = ?", (slug,)).fetchone()
    if row and os.path.isfile(stamp):
        try:
            with open(stamp, encoding="utf-8") as f:
                if f.read().strip() == digest:
                    _drop_stale_media(zip_path, installed_dir)
                    return row["id"]
        except OSError:
            pass

    work_dir = tempfile.mkdtemp(prefix="pkgseed-")
    try:
        with open(zip_path, "rb") as f:
            safe_extract_zip(f, work_dir)
        template_id = install_theme_package(
            db, slug, static_folder, pkg_dir_override=work_dir, is_builtin=True,
            adopt_manifest_overrides=adopt_manifest_overrides,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    #  After a real install as well as after a skipped one. Extracting
    #  adds files and removes none, so the reinstall path is the one that
    #  most obviously leaves a previous version's pictures behind -- and
    #  it was the path this cleanup originally missed, which showed up as
    #  four templates still carrying PNGs while the rest came clean.
    _drop_stale_media(zip_path, installed_dir)
    try:
        os.makedirs(installed_dir, exist_ok=True)
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(digest)
    except OSError:
        pass  # a stamp that cannot be written costs a re-extract, nothing more
    return template_id


def build_template_zips(src_dir=None, dest_dir=None):
    """Build one .zip per shipped template. Run at image build time, so a
    template edited in the source tree is packaged as it now stands rather
    than as it stood whenever somebody last remembered to do this."""
    src_dir = src_dir or PACKAGES_DIR
    dest_dir = dest_dir or PACKAGE_ZIPS_DIR
    if not os.path.isdir(src_dir):
        raise PackageError(f"No template sources at {src_dir}")
    os.makedirs(dest_dir, exist_ok=True)
    built = []
    for slug in sorted(os.listdir(src_dir)):
        pkg_dir = os.path.join(src_dir, slug)
        if not os.path.isfile(os.path.join(pkg_dir, "manifest.json")):
            continue
        dest = os.path.join(dest_dir, f"{slug}.zip")
        inventory = write_package_zip(pkg_dir, dest)
        built.append((slug, dest, inventory))
    return built


def install_theme_package(db, slug, static_folder, pkg_dir_override=None, is_builtin=True,
                          adopt_manifest_overrides=True):
    """Idempotent: upsert the `templates` row for a package's theme (CSS +
    palette + fonts only, no page content). Copies theme.css into the live
    /static/themes/<slug>/ location every call, and always re-syncs
    css_path/palette_json/google_fonts_url from the manifest even for an
    existing row — those three are the PACKAGE's own declared properties,
    so an updated manifest (a new banner palette, a font pairing) always
    reaches an already-seeded install, the same way a rebuilt image's CSS
    already did. Never touches is_active/color_overrides/font_overrides/
    shape_override once a row exists — those are the admin's own, layered
    on top (see routes/admin/templates.py's colors/fonts/shape routes).
    pkg_dir_override lets an admin-uploaded package (extracted to a temp
    dir, not PACKAGES_DIR) reuse this same install path — pass
    is_builtin=False there, so it stays deletable. A package with no
    "palette" of its own still gets DEFAULT_PALETTE, so every template's
    Colors panel works, not just the ones that happen to declare colors.
    Returns the template's id.

    Race note: builtin packages are (re-)installed by app/__init__.py's
    seed loop on every boot, across every gunicorn worker — a builtin can
    also be deleted and thus re-seeded from a clean slate now (see
    routes/admin/templates.py's template_delete), where two workers
    racing this function's INSERT is a real possibility, not just a
    theoretical one. Mirrors db.py's _add_column: let the loser's INSERT
    fail on the slug UNIQUE constraint and just look the row up instead
    of raising."""
    #  Always a real directory somebody just unpacked or built — there is
    #  no folder-in-the-image fallback any more, and silently installing
    #  nothing would be worse than saying so.
    pkg_dir = pkg_dir_override
    if not pkg_dir or not os.path.isdir(pkg_dir):
        raise PackageError(f"No package directory to install for '{slug}'.")
    with open(os.path.join(pkg_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    #  An installed template keeps its package whole — pages, pictures,
    #  zones, tools, not just its CSS — in the themes volume, where
    #  template_package_dir looks for every template regardless of where
    #  it came from. Both kinds arrive here from a temporary folder now: a
    #  builtin unpacked from the zip built into the image, an uploaded one
    #  from the admin's own archive. Neither temporary folder survives the
    #  request that made it, so anything not copied out here is simply
    #  lost — which is what used to happen to an imported template's
    #  content, leaving a look with nothing behind it.
    installed_dir = os.path.join(static_folder, "themes", slug)
    if os.path.abspath(pkg_dir) != os.path.abspath(installed_dir):
        os.makedirs(installed_dir, exist_ok=True)
        #  Every name here came through safe_extract_zip, which is what
        #  decides a path is allowed to exist at all.
        for entry in os.listdir(pkg_dir):
            src_entry = os.path.join(pkg_dir, entry)
            dst_entry = os.path.join(installed_dir, entry)
            if os.path.isdir(src_entry):
                copy_tree_contents(src_entry, dst_entry)
            else:
                shutil.copyfile(src_entry, dst_entry)

    css_path = None
    css_src = os.path.join(pkg_dir, "theme.css")
    if os.path.isfile(css_src):
        dest_dir = os.path.join(static_folder, "themes", slug)
        os.makedirs(dest_dir, exist_ok=True)
        css_dest = os.path.join(dest_dir, "theme.css")
        # save_current_site_as_package passes pkg_dir_override=dest_dir —
        # _build_package_dir already wrote theme.css straight into that
        # same persistent-volume path, so css_src and css_dest can be the
        # exact same file (copyfile onto itself raises SameFileError).
        # A plain zip export/admin import always has pkg_dir in a
        # separate temp dir, so this is specific to the save-as-template
        # path, not a general "skip copying" shortcut.
        if os.path.abspath(css_src) != os.path.abspath(css_dest):
            shutil.copyfile(css_src, css_dest)
        css_path = f"themes/{slug}/theme.css"

    #  A template's pictures travel with it, exactly like its CSS. They
    #  are copied to the same served place on every boot and keep their
    #  own names, so the URL a page ends up holding is the same string on
    #  every install of this image — which is what lets two hosts render
    #  a template byte for byte alike. Deliberately NOT the uploads
    #  folder: an upload is deliberately given a fresh unique name so it
    #  cannot collide with another, and the seed loop runs on every boot,
    #  so that path would copy all of them again under new names each
    #  time the app started.
    media_src = os.path.join(pkg_dir, "media")
    if os.path.isdir(media_src):
        media_dest = os.path.join(static_folder, "themes", slug, "media")
        os.makedirs(media_dest, exist_ok=True)
        for fname in os.listdir(media_src):
            one = os.path.join(media_src, fname)
            other = os.path.join(media_dest, fname)
            #  Same SameFileError guard as theme.css above: a template
            #  saved from the live site is already sitting in its
            #  destination.
            if os.path.isfile(one) and os.path.abspath(one) != os.path.abspath(other):
                shutil.copyfile(one, other)

    # Any custom tools this package bundled (see _build_package_dir) —
    # "only import missing tools" (import_tools skips by name) means this
    # is safe to run on every reinstall, not just the first: an admin's
    # own already-installed tool of the same name is never touched or
    # duplicated. A no-op for built-ins, which never ship a tools.json.
    tools_path = os.path.join(pkg_dir, "tools.json")
    if os.path.isfile(tools_path):
        with open(tools_path, encoding="utf-8") as f:
            import_tools(db, json.load(f))

    existing = db.execute("SELECT id FROM templates WHERE slug = ?", (slug,)).fetchone()
    if existing:
        if css_path:
            db.execute("UPDATE templates SET css_path = ? WHERE id = ?", (css_path, existing["id"]))
        db.execute(
            "UPDATE templates SET palette_json = ?, google_fonts_url = ?, nav_layout = ? WHERE id = ?",
            (json.dumps(manifest.get("palette") or DEFAULT_PALETTE), manifest.get("google_fonts_url"),
             manifest.get("nav_layout") or existing["nav_layout"], existing["id"]),
        )
        # font_overrides/shape_override/shadow_override/zone_style_overrides
        # are the admin's own settings, so re-seeding an EXISTING row must
        # not write them.
        #
        # The guard used to be "only write what the manifest carries",
        # reasoning that a built-in's manifest never carries any. That
        # stopped being true — all sixteen now declare shape_override and
        # shadow_override — and the consequence was quiet and annoying:
        # the seed loop runs for every built-in on every boot, so an admin
        # who picked a Corner style or a Depth got the template's own
        # blanket value back at the next restart. Measured before this
        # changed: Lens + Floating went back to pill + lifted on a plain
        # `docker compose restart`.
        #
        # So the condition is now WHO is asking, not what the manifest
        # happens to hold. An explicit import or save is the admin acting,
        # and its bundled settings should land; the boot seed is not, and
        # must leave the row alone. A brand-new row is unaffected either
        # way — it is created from the manifest below.
        if adopt_manifest_overrides and manifest.get("font_overrides"):
            db.execute(
                "UPDATE templates SET font_overrides = ? WHERE id = ?",
                (json.dumps(manifest["font_overrides"]), existing["id"]),
            )
        #  The shipped defaults are recorded on every install, override
        #  or not: they are what the package SAYS about itself, and an
        #  owner's own choice lives in the *_override columns beside them.
        db.execute("UPDATE templates SET shape_default = ?, shadow_default = ?, "
                   "composition_default = ?, ground_default = ?, ink_default = ? WHERE id = ?",
                   (manifest.get("shape_override"), manifest.get("shadow_override"),
                    manifest.get("composition"), manifest.get("ground_color"),
                    manifest.get("ink_color"), existing["id"]))
        #  A ground the owner "chose" that is exactly the shipped one is
        #  the installer's own earlier write, from when the two shared a
        #  column -- not a choice. Clearing it is what lets Reset mean
        #  "the template's own" on an install that predates the split.
        db.execute("UPDATE templates SET ground_color = NULL WHERE id = ? "
                   "AND ground_color IS NOT NULL AND ground_color = ground_default", (existing["id"],))
        db.execute("UPDATE templates SET ink_color = NULL WHERE id = ? "
                   "AND ink_color IS NOT NULL AND ink_color = ink_default", (existing["id"],))
        if adopt_manifest_overrides and manifest.get("shape_override"):
            db.execute("UPDATE templates SET shape_override = ? WHERE id = ?", (manifest["shape_override"], existing["id"]))
        if adopt_manifest_overrides and manifest.get("shadow_override"):
            db.execute("UPDATE templates SET shadow_override = ? WHERE id = ?", (manifest["shadow_override"], existing["id"]))
        if adopt_manifest_overrides and manifest.get("composition"):
            db.execute("UPDATE templates SET composition_override = ? WHERE id = ?",
                       (manifest["composition"], existing["id"]))
        if adopt_manifest_overrides and manifest.get("zone_style_overrides"):
            db.execute(
                "UPDATE templates SET zone_style_overrides = ? WHERE id = ?",
                (json.dumps(manifest["zone_style_overrides"]), existing["id"]),
            )
        return existing["id"]

    palette = manifest.get("palette") or DEFAULT_PALETTE
    try:
        cur = db.execute(
            "INSERT INTO templates "
            "(name, slug, css_path, is_active, is_builtin, palette_json, google_fonts_url, "
            "font_overrides, shape_override, shadow_override, zone_style_overrides, "
            #  What the package SAYS about itself, and the owner's own
            #  choice beside it -- the same pair Corners and Depth have.
            #  Missing here for one release, which meant a template's
            #  composition survived only if the row already existed: a
            #  freshly generated one, which is every generated one, came
            #  out unshaped.
            "shape_default, shadow_default, composition_default, composition_override, "
            #  The ground is what the package SAYS, so it is a default; the
            #  owner's own colour (ground_color) starts empty.
            "ground_default, ink_default) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                manifest["name"], slug, css_path,
                1 if manifest.get("default_active") else 0,
                1 if is_builtin else 0,
                json.dumps(palette),
                manifest.get("google_fonts_url"),
                json.dumps(manifest["font_overrides"]) if manifest.get("font_overrides") else None,
                manifest.get("shape_override"),
                manifest.get("shadow_override"),
                json.dumps(manifest["zone_style_overrides"]) if manifest.get("zone_style_overrides") else None,
                manifest.get("shape_override"),
                manifest.get("shadow_override"),
                manifest.get("composition"),
                manifest.get("composition"),
                manifest.get("ground_color"),
                manifest.get("ink_color"),
            ),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return db.execute("SELECT id FROM templates WHERE slug = ?", (slug,)).fetchone()["id"]


def backfill_ground_defaults(db, static_folder):
    """Gives every template row its shipped ground, from the manifest on
    disk, and un-chooses a "choice" that was only ever the installer's.

    ground_default arrived after the installer had already been writing
    the manifest's ground into ground_color for a while. Reinstalling
    fixes a row -- but a package whose archive has not changed is not
    reinstalled, by design, so a row that predates the split would keep
    an empty default and a full override for ever, and Reset would keep
    throwing the template's own colour away. Cheap enough to run every
    boot: twenty small files. A row without a manifest is left alone.
    """
    rows = db.execute("SELECT id, slug, is_builtin, ground_color, ink_color, ground_default, ink_default "
                      "FROM templates").fetchall()
    for row in rows:
        folder = template_package_dir(static_folder, row["slug"], row["is_builtin"])
        path = os.path.join(folder, "manifest.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            continue
        ground, ink = manifest.get("ground_color"), manifest.get("ink_color")
        db.execute("UPDATE templates SET ground_default = ?, ink_default = ? WHERE id = ?",
                   (ground, ink, row["id"]))
        if ground and row["ground_color"] == ground:
            db.execute("UPDATE templates SET ground_color = NULL WHERE id = ?", (row["id"],))
        if ink and row["ink_color"] == ink:
            db.execute("UPDATE templates SET ink_color = NULL WHERE id = ?", (row["id"],))
    db.commit()


def load_package_dir(pkg_dir):
    """Reassemble any package directory's manifest.json + pages/*.json +
    optional blog_posts.json back into the single dict shape
    _apply_pack_content's page-merge logic consumes. Works for a built-in
    package dir or a freshly extracted uploaded one."""
    with open(os.path.join(pkg_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    pages_dir = os.path.join(pkg_dir, "pages")
    if os.path.isdir(pages_dir):
        pages = []
        for fname in sorted(os.listdir(pages_dir)):
            with open(os.path.join(pages_dir, fname), encoding="utf-8") as f:
                pages.append(json.load(f))
        manifest["pages"] = pages
    blog_path = os.path.join(pkg_dir, "blog_posts.json")
    if os.path.isfile(blog_path):
        with open(blog_path, encoding="utf-8") as f:
            manifest["blog_posts"] = json.load(f)
    zones_path = os.path.join(pkg_dir, "zones.json")
    if os.path.isfile(zones_path):
        with open(zones_path, encoding="utf-8") as f:
            manifest["zone_sections"] = json.load(f)
    return manifest


def template_package_dir(static_folder, slug, is_builtin):
    """Where an INSTALLED template's own package folder lives: the
    persistent static/themes/<slug>/ volume, for every template.

    One place, whoever it came from. Builtins used to be read straight out
    of a source folder in the image while imported ones lived here, so
    every caller had to be told which kind it was holding — and the
    `is_builtin` argument is still taken, and still ignored, only so this
    reads the same at all of its call sites. They arrive as zips now and
    are unpacked into the same directory an uploaded package lands in.
    """
    return os.path.join(static_folder, "themes", slug)


def template_has_content(static_folder, slug, is_builtin):
    """Same idea as has_content(), but works for any installed template
    (built-in or admin-imported/saved), not just a builtin slug — every
    template can optionally carry content now, not just curated demo
    packs, so callers deciding whether to show a "Load Content" action
    need this generalized check."""
    return os.path.isdir(os.path.join(template_package_dir(static_folder, slug, is_builtin), "pages"))


def load_template_package(static_folder, slug, is_builtin):
    """load_package_dir() for an already-installed template's own package
    folder, regardless of whether it's builtin or admin-imported/saved.
    Returns None if the folder's manifest.json is missing (shouldn't
    normally happen for a template that's actually installed)."""
    pkg_dir = template_package_dir(static_folder, slug, is_builtin)
    if not os.path.isfile(os.path.join(pkg_dir, "manifest.json")):
        return None
    return point_media_at_installed_copy(load_package_dir(pkg_dir), slug)


#  A picture belonging to a template is written in that template's own
#  files as "media/<name>" — a reference to something inside the package,
#  which is what makes the package portable: zip it, move it to another
#  install, and the file it names is in the zip. The extension is what
#  makes this safe to search for: a page whose slug is "media" (several
#  templates have one) is never "media/something.png".
MEDIA_REF = re.compile(
    r"(?<![\w/.-])media/([A-Za-z0-9_.-]+\.(?:png|jpe?g|gif|webp|svg|mp4|webm))")


#  What an export has to pull back into the package: a picture the admin
#  uploaded, and a picture that came from a template's own media folder.
#  The second one matters because a page built from a template keeps
#  pointing at the template's copy — miss it and exporting that site
#  produces a package whose pictures only work on an install that already
#  has the original template.
EXPORTABLE_MEDIA = re.compile(
    r"/static/(?:uploads|themes/[A-Za-z0-9_.-]+/media)/([^\s'\"()]+)")


def _static_source_path(static_folder, url):
    """The file on disk behind a /static/... URL this app itself wrote."""
    return os.path.join(static_folder, *url[len("/static/"):].split("/"))


def installed_media_url(slug, fname):
    return f"/static/themes/{slug}/media/{fname}"


def point_media_at_installed_copy(pack, slug):
    """Turn a package's own "media/<name>" references into the URL of the
    copy install_theme_package puts under static/themes/<slug>/media/.

    Every string in the package is walked rather than only the places
    pictures are expected, because a picture can be named in a section's
    content, in a zone section, in a blog post or in a manifest key, and
    a reference this function misses becomes a broken image on a page.
    """
    def walk(value):
        if isinstance(value, str):
            return MEDIA_REF.sub(lambda m: installed_media_url(slug, m.group(1)), value)
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    return walk(pack)


# ---------- Zip import/export ----------
# An admin builds a look (or a full demo site) in the tool, then exports it
# as a .zip to reuse on another install or share with someone else — the
# same package format either way, just a .zip instead of a folder. An
# uploaded archive is untrusted input, which is why the extraction step
# below is this careful about it.

ALLOWED_PACKAGE_EXTENSIONS = {".json", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_PACKAGE_FILES = 500
MAX_PACKAGE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100MB — generous for a CSS+JSON+images bundle, small next to the app's 250MB upload cap


class PackageError(Exception):
    pass


def safe_extract_zip(fileobj, dest_dir):
    """Extract an uploaded zip into dest_dir, refusing anything that looks
    hostile instead of trusting ZipFile.extractall(): a zip-slip path that
    would land outside dest_dir, a suspiciously large decompressed payload
    (zip-bomb), too many entries, or a file type not on the allowlist.
    Raises PackageError with a message safe to show the admin; writes
    nothing to disk until every entry has already passed all checks."""
    try:
        zf = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise PackageError("That doesn't look like a valid .zip file.")

    infos = zf.infolist()
    if len(infos) > MAX_PACKAGE_FILES:
        raise PackageError(f"Too many files in the archive (max {MAX_PACKAGE_FILES}).")

    dest_dir = os.path.realpath(dest_dir)
    total_size = 0
    targets = []  # [(info, real_target_path), ...]
    for info in infos:
        if info.is_dir():
            continue
        total_size += info.file_size
        if total_size > MAX_PACKAGE_UNCOMPRESSED_BYTES:
            raise PackageError("Archive is too large once decompressed.")
        ext = os.path.splitext(info.filename)[1].lower()
        if ext not in ALLOWED_PACKAGE_EXTENSIONS:
            raise PackageError(f"'{info.filename}' isn't a file type this import accepts.")
        target = os.path.realpath(os.path.join(dest_dir, info.filename))
        if target != dest_dir and not target.startswith(dest_dir + os.sep):
            raise PackageError("Archive contains a path that escapes the extraction folder.")
        targets.append((info, target))

    for info, target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _build_package_dir(db, tpl, static_folder, page_ids, work_dir, slug, name=None, capture_layout=False):
    """Shared by export_package_zip() and save_current_site_as_package():
    assembles a package directory (manifest + theme.css + pages/*.json +
    media/) under work_dir/<slug>/ from a live template row (+ optionally
    a set of its pages, bundled as page content). `name` overrides the
    manifest's display name (default: the template's own current name).

    `capture_layout=True` (only save_current_site_as_package uses this —
    a plain zip Export never does) also captures the site's current
    header/sidebar/footer sections (verbatim, into zones.json) and
    site-wide nav_layout setting (into the manifest), so re-activating
    this saved template later restores the exact structure it was saved
    with — the same "full save-point" job Snapshots used to do alone,
    folded into the same package format instead of a second system.

    Returns the built directory's path."""
    pkg_dir = os.path.join(work_dir, slug)
    os.makedirs(pkg_dir, exist_ok=True)

    manifest = {"name": name or tpl["name"], "slug": slug, "has_content": bool(page_ids)}
    if tpl["google_fonts_url"]:
        manifest["google_fonts_url"] = tpl["google_fonts_url"]
    palette = json.loads(tpl["palette_json"]) if tpl["palette_json"] else None
    overrides = json.loads(tpl["color_overrides"]) if tpl["color_overrides"] else {}
    if palette:
        for entry in palette:
            if entry["slug"] in overrides:
                entry["color"] = overrides[entry["slug"]]
        manifest["palette"] = palette
    # Admin customizations layered on top of the theme's own defaults —
    # font_overrides/shape_override/shadow_override/zone_style_overrides —
    # used to be
    # silently dropped on export/save-as-template: only the base palette
    # and the theme's own google_fonts_url were captured, so a custom
    # heading font (or shape, or a recolored header bar) never survived
    # the round trip. Captured verbatim here; install_theme_package writes
    # them straight back onto the installed row the same way.
    if tpl["font_overrides"]:
        manifest["font_overrides"] = json.loads(tpl["font_overrides"])
    if tpl["shape_override"]:
        manifest["shape_override"] = tpl["shape_override"]
    if tpl["shadow_override"]:
        manifest["shadow_override"] = tpl["shadow_override"]
    #  The ground the page is actually painted -- the owner's choice, else
    #  what this template shipped. A saved template is a new template, so
    #  what it carries is its default. Exported without this, a navy site
    #  saved as a template came back on a tint of the primary.
    cols = tpl.keys()
    ground = (tpl["ground_color"] if "ground_color" in cols else None) or \
             (tpl["ground_default"] if "ground_default" in cols else None)
    ink = (tpl["ink_color"] if "ink_color" in cols else None) or \
          (tpl["ink_default"] if "ink_default" in cols else None)
    if ground:
        manifest["ground_color"] = ground
    if ink:
        manifest["ink_color"] = ink
    #  Which composition the template wears -- the layout that gates
    #  composition.css (the banded hero, the white overlay button, the gutters).
    #  Dropped on export, the imported template loaded none of it: the banner
    #  button fell back to the palette's primary (brown, not white) and the
    #  banded look was gone. install_theme_package reads manifest["composition"]
    #  straight back onto the row (composition_default/override).
    _composition = tpl["composition_override"] or tpl["composition_default"]
    if _composition:
        manifest["composition"] = _composition
    if tpl["zone_style_overrides"]:
        manifest["zone_style_overrides"] = json.loads(tpl["zone_style_overrides"])
    if capture_layout:
        nav_row = db.execute("SELECT value FROM settings WHERE key = 'nav_layout'").fetchone()
        if nav_row and nav_row["value"]:
            manifest["nav_layout"] = nav_row["value"]
    with open(os.path.join(pkg_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if tpl["css_path"]:
        css_src = os.path.join(static_folder, tpl["css_path"])
        if os.path.isfile(css_src):
            shutil.copyfile(css_src, os.path.join(pkg_dir, "theme.css"))

    # Bundle every custom (admin-created) content tool currently on this
    # site, not just ones this specific template's own content happens to
    # use — detecting "which tools does this template's content actually
    # reference" would need parsing every section's stored HTML for tool-
    # specific markers (see HTML_SECTION_LABEL_MARKERS), which is fragile;
    # a few extra tool definitions riding along in an export is harmless,
    # a genuinely-used custom tool silently missing from the export is not.
    tools_data = export_all_custom_tools(db)
    if tools_data["tools"]:
        with open(os.path.join(pkg_dir, "tools.json"), "w", encoding="utf-8") as f:
            json.dump(tools_data, f, indent=2, ensure_ascii=False)

    media_files = {}  # {original /static/<...> URL : media/<name>}
    if page_ids:
        pages_dir = os.path.join(pkg_dir, "pages")
        os.makedirs(pages_dir, exist_ok=True)
        for i, page_id in enumerate(page_ids):
            page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
            if not page:
                continue
            sections = db.execute(
                "SELECT * FROM sections WHERE page_id = ? ORDER BY position", (page_id,)
            ).fetchall()
            section_specs = []
            for s in sections:
                content = s["content"] or ""
                for m in EXPORTABLE_MEDIA.finditer(content):
                    media_files[m.group(0)] = f"media/{m.group(1)}"
                #  Carry the section's own styling, not just its words. A
                #  saved template that dropped the picture behind a band,
                #  its corners and its colour would restore as a different
                #  design wearing the same text — which is what happened
                #  before these columns were captured here.
                extras = {}
                #  `caption`, `link_url` and `file_display` are here for
                #  the same reason as the rest: each is set by a real tool
                #  (the Image tool's caption and link, the File tool's
                #  "how should this download look"), and a saved template
                #  that dropped them would come back missing something the
                #  admin had deliberately set. A capability the tools have
                #  but a package cannot carry is a gap of its own.
                #  view_overrides carries the per-view (laptop/tablet/mobile)
                #  hide/align/order/height a section was given; layout_width_px
                #  a custom pixel width; title_level/align/on the heading a
                #  section wears. All are set by real controls, so a package
                #  that dropped them restored a section shaped differently from
                #  the one that was saved -- the same "a tool can do it but the
                #  package cannot carry it" gap the columns above were added to
                #  close. The install side writes whatever columns arrive, so
                #  adding them here is all it takes to round-trip.
                for column in ("bg_color", "border_color", "corner_style", "shadow_style",
                               "bg_image", "bg_overlay", "bg_position", "width", "layout_width",
                               "layout_width_pct", "layout_width_px", "animation", "mask_shape",
                               "media_type", "content_height_px", "view_overrides",
                               "title_level", "title_align", "title_on",
                               "caption", "link_url", "link_new_tab", "file_display", "file_name", "file_icon"):
                    try:
                        value = s[column]
                    except (IndexError, KeyError):
                        continue
                    if value not in (None, ""):
                        extras[column] = value
                #  A background picture is a file the package has to carry,
                #  the same as one referenced in the markup — it just lives
                #  in a column instead of in the HTML.
                for m in EXPORTABLE_MEDIA.finditer(str(extras.get("bg_image") or "")):
                    media_files[m.group(0)] = f"media/{m.group(1)}"
                section_specs.append([s["type"], s["title"] or "", content, extras])
            page_spec = {
                "title": page["title"], "slug_suffix": page["slug"], "page_type": page["page_type"],
                "meta_description": page["meta_description"] or "", "sections": section_specs,
            }
            #  And the page's own backdrop.
            for column in ("bg_color", "bg_image", "bg_attach", "bg_overlay", "bg_surface"):
                try:
                    value = page[column]
                except (IndexError, KeyError):
                    continue
                if value not in (None, ""):
                    page_spec[column] = value
            if capture_layout:
                page_spec["nav_layout_override"] = page["nav_layout_override"]
                page_spec["hide_sidebar"] = bool(page["hide_sidebar"])
                page_spec["hide_sidebar_right"] = bool(page["hide_sidebar_right"])
                page_spec["hide_footer"] = bool(page["hide_footer"])
            with open(os.path.join(pages_dir, f"{i:02d}-{page['slug']}.json"), "w", encoding="utf-8") as f:
                json.dump(page_spec, f, indent=2, ensure_ascii=False)

        if capture_layout:
            zone_rows = db.execute(
                "SELECT * FROM sections WHERE template_id = ? AND zone != 'body' ORDER BY zone, position",
                (tpl["id"],),
            ).fetchall()
            if zone_rows:
                zone_specs = []
                for s in zone_rows:
                    content = s["content"] or ""
                    for m in EXPORTABLE_MEDIA.finditer(content):
                        media_files[m.group(0)] = f"media/{m.group(1)}"
                    zone_specs.append({
                        "zone": s["zone"], "type": s["type"], "title": s["title"] or "",
                        "content": content, "position": s["position"], "layout_width": s["layout_width"],
                    })
                with open(os.path.join(pkg_dir, "zones.json"), "w", encoding="utf-8") as f:
                    json.dump(zone_specs, f, indent=2, ensure_ascii=False)

        if media_files:
            media_dir = os.path.join(pkg_dir, "media")
            os.makedirs(media_dir, exist_ok=True)
            for url, rel in media_files.items():
                src = _static_source_path(static_folder, url)
                if os.path.isfile(src):
                    shutil.copyfile(src, os.path.join(media_dir, os.path.basename(rel)))
            # Section content still points at the URL the live site
            # serves, not the media/ placeholder — rewrite it so the
            # package names its own copy, the way every other package's
            # page JSON does, and stays readable on an install that has
            # never seen this site.
            zones_path = os.path.join(pkg_dir, "zones.json")
            paths = [os.path.join(pages_dir, f) for f in os.listdir(pages_dir)]
            if os.path.isfile(zones_path):
                paths.append(zones_path)
            for path in paths:
                with open(path, encoding="utf-8") as f:
                    spec = json.load(f)
                sections_list = spec["sections"] if isinstance(spec, dict) else spec
                for section in sections_list:
                    key = 2 if isinstance(section, list) else "content"
                    for url, rel in media_files.items():
                        section[key] = section[key].replace(url, rel)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(spec, f, indent=2, ensure_ascii=False)

    return pkg_dir


def export_package_zip(db, template_id, static_folder, page_ids=None):
    """Build a .zip for the given template (+ optionally a set of its
    pages, bundled as page content) and return its path — the inverse of
    install_theme_package()/an uploaded content import. Caller is
    responsible for cleaning up the returned temp file/directory."""
    tpl = db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not tpl:
        raise PackageError("Template not found.")

    work_dir = tempfile.mkdtemp(prefix="pkgexport-")
    pkg_dir = _build_package_dir(db, tpl, static_folder, page_ids, work_dir, tpl["slug"])

    #  Asked for a template rather than for a named set of pages, so what
    #  goes in the zip is the template: the words it ships and the
    #  pictures they refer to, not only the CSS. An export used to be the
    #  look alone, which made "export, move to another install, import"
    #  quietly lossy — the demo site the template is FOR stayed behind.
    #  The manifest and theme.css _build_package_dir just wrote are the
    #  live template row's own, so they win over the package's copies.
    if not page_ids:
        own = template_package_dir(static_folder, tpl["slug"], bool(tpl["is_builtin"]))
        if os.path.isdir(own) and os.path.abspath(own) != os.path.abspath(pkg_dir):
            copied_pages = False
            for entry in ("pages", "media", "zones.json", "blog_posts.json"):
                src_entry = os.path.join(own, entry)
                dst_entry = os.path.join(pkg_dir, entry)
                if os.path.isdir(src_entry):
                    copy_tree_contents(src_entry, dst_entry)
                    copied_pages = copied_pages or entry == "pages"
                elif os.path.isfile(src_entry) and not os.path.exists(dst_entry):
                    shutil.copyfile(src_entry, dst_entry)

            #  The manifest _build_package_dir just wrote describes the
            #  live template row — its colours, its fonts, the admin's
            #  overrides. It says nothing about the things only the
            #  package declares: which way the header sits, what the
            #  business is called, whether there is a menu in the header.
            #  Export without them and the template arrives on the other
            #  install wearing the right colours in the wrong shape, under
            #  somebody else's name. Merge them underneath, so anything
            #  the live row has an opinion about still wins.
            own_manifest = os.path.join(own, "manifest.json")
            built_manifest = os.path.join(pkg_dir, "manifest.json")
            if os.path.isfile(own_manifest):
                with open(own_manifest, encoding="utf-8") as f:
                    declared = json.load(f)
                with open(built_manifest, encoding="utf-8") as f:
                    built = json.load(f)
                merged = {k: v for k, v in declared.items()
                          if k not in ("pages", "blog_posts", "zone_sections")}
                merged.update(built)
                merged["has_content"] = copied_pages or bool(merged.get("has_content"))
                with open(built_manifest, "w", encoding="utf-8") as f:
                    json.dump(merged, f, indent=2, ensure_ascii=False)

    # Zip paths are relative to pkg_dir (not work_dir), so manifest.json
    # sits at the archive root — exactly what safe_extract_zip() lands at
    # <dest_dir>/manifest.json on import, with no extra wrapper folder to
    # unwrap.
    zip_path = os.path.join(work_dir, f"{tpl['slug']}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(pkg_dir):
            for fname in files:
                full = os.path.join(root, fname)
                zf.write(full, os.path.relpath(full, pkg_dir))
    return zip_path


def save_current_site_as_package(db, static_folder, slug, name, page_ids=None):
    """Captures the currently active template's look (CSS + palette),
    header/sidebar/footer sections, and site-wide nav_layout, plus the
    given pages' own content (default: none) as a brand new, independent
    Template Package written straight into the local library
    (app/static/themes/<slug>/ + a `templates` row) — the same place an
    imported .zip lands, so it's immediately activatable/exportable like
    any other entry. This is the app's one "save the whole current setup
    so I can get back to it" mechanism (see template_activate's
    `_apply_default_layout`/zone_sections handling for the restore side) —
    it replaced a separate Snapshots system that did the same job with a
    second, non-portable data model. `slug` must already be confirmed
    unique by the caller (see the same pattern in
    routes/admin/templates.py's package_import). Returns the new
    template's id."""
    tpl = db.execute("SELECT * FROM templates WHERE is_active = 1").fetchone()
    if not tpl:
        raise PackageError("No active template to save.")

    work_dir = tempfile.mkdtemp(prefix="pkgsave-")
    try:
        pkg_dir = _build_package_dir(db, tpl, static_folder, page_ids, work_dir, slug, name=name, capture_layout=True)
        dest_dir = os.path.join(static_folder, "themes", slug)
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        copy_tree_contents(pkg_dir, dest_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return install_theme_package(db, slug, static_folder, pkg_dir_override=dest_dir, is_builtin=False)


def cover_for(static_folder, slug):
    """A picture that shows what a template looks like, or nothing.

    A LIST OF NAMES IS NOT A LIBRARY. The Templates screen was twenty
    rows of text with three icons on each -- so choosing between a
    bakery and a barn meant opening a live preview twenty times, and the
    one thing a person actually decides on, what it LOOKS like, was the
    one thing not on the screen.

    Nothing on this server can take a screenshot: the app ships no
    browser, deliberately. But a template that ships a picture has
    already said what it looks like -- it is the photograph across the
    top of its own front page -- and its palette says the rest. So the
    cover is the template's own banner, which costs nothing to produce
    and is never out of date, because it IS the template's content
    rather than a render of it.

    Returns a URL under /static/themes/<slug>/media/, or "" when the
    template ships no pictures (several do not, and a colour tile is the
    honest answer there rather than a stock image standing in for one).
    """
    folder = os.path.join(static_folder, "themes", slug, "media")
    if not os.path.isdir(folder):
        return ""
    names = sorted(
        n for n in os.listdir(folder)
        if os.path.splitext(n)[1].lower() in (".webp", ".png", ".jpg", ".jpeg"))
    if not names:
        return ""
    #  The banner first, by name, because that is the picture the front
    #  page opens with and so the one somebody is choosing between. The
    #  shipped set is named for exactly this -- <slug>-banner.webp -- and
    #  anything else falls back to whichever comes first, which is at
    #  least stable.
    chosen = next((n for n in names if "-banner." in n), names[0])
    return "/static/themes/%s/media/%s" % (slug, chosen)
