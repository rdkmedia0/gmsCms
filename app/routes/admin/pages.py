import datetime
import os
import re
import json
import uuid
from flask import request, flash, redirect, url_for, jsonify, render_template, current_app
from werkzeug.utils import secure_filename

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import packages
from ...services.sections import (
    _list_media, PAGE_TYPES, PAGE_LAYOUTS, starter_page_sections,
)
from ...services.menu import _regenerate_menu_html
from ...services import blog as blog_service
from . import RESERVED_SLUGS, slugify, wants_json, _redirect_next, NAV_LAYOUTS

# ---------- Pages ----------

@bp.route("/pages/new", methods=["GET", "POST"])
@login_required
def page_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            if wants_json():
                return jsonify({"error": "Please enter a page name."}), 400
            flash("Please enter a page name.", "error")
            return redirect(url_for("admin.page_new"))
        db = get_db()
        slug = slugify(title)
        base_slug = slug
        i = 2
        # Pages render at the bare /<slug> URL now (human-readable URLs) —
        # a page slug matching one of the app's own top-level path
        # segments would never actually be reachable there (Flask's
        # blueprint routes always win), so route around the collision the
        # same way an already-taken slug is handled: append -2, -3, ...
        while (
            db.execute("SELECT id FROM pages WHERE slug = ?", (slug,)).fetchone()
            or slug in RESERVED_SLUGS
        ):
            slug = f"{base_slug}-{i}"
            i += 1
        #  Two separate questions that used to be one. "What kind of page
        #  is this" has almost no answers left (see PAGE_TYPES), while
        #  "what should it start with" has several — and the second is
        #  only ever about the first few minutes of the page's life.
        layout = request.form.get("page_layout", "standard")
        if layout not in dict((k, v) for k, v, _ in PAGE_LAYOUTS):
            layout = "standard"
        #  Choosing the Newsletter starting point makes a newsletter --
        #  one question instead of a starting point and a tick box that
        #  meant the same thing. "Newsletter" here buys the send controls
        #  on the page and a line on the Newsletters screen, and nothing
        #  else: it is on the site or not, in the menu or not, exactly
        #  like any other page, and it can be turned off again from the
        #  page's own settings.
        page_type = "newsletter" if layout == "newsletter" else "standard"
        cur = db.execute(
            "INSERT INTO pages (title, slug, nav_order, page_type) "
            "VALUES (?, ?, (SELECT COALESCE(MAX(nav_order),0)+1 FROM pages), ?)",
            (title, slug, page_type),
        )
        #  Some types arrive with something in them — see
        #  starter_page_sections for which, and why.
        for position, (section_type, section_title, content) in enumerate(
            starter_page_sections(db, layout, title)
        ):
            db.execute(
                "INSERT INTO sections (page_id, type, title, content, position) "
                "VALUES (?, ?, ?, ?, ?)",
                (cur.lastrowid, section_type, section_title, content, position),
            )
        db.commit()
        page_url = url_for("public.page", slug=slug)
        if wants_json():
            return jsonify({"ok": True, "id": cur.lastrowid, "title": title, "slug": slug, "url": page_url})
        flash(f'Page "{title}" created!', "success")
        return redirect(page_url)
    return render_template("admin/page_new.html", page_types=PAGE_TYPES,
                           page_layouts=PAGE_LAYOUTS)


@bp.route("/pages/<int:page_id>/edit")
@login_required
def page_edit(page_id):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if not page:
        flash("Page not found.", "error")
        return redirect(url_for("admin.dashboard"))
    sections = db.execute(
        "SELECT * FROM sections WHERE page_id = ? ORDER BY position", (page_id,)
    ).fetchall()
    blog_posts = []
    if page["page_type"] == "blog":
        blog_posts = db.execute(
            "SELECT * FROM blog_posts WHERE page_id = ? ORDER BY position DESC, id DESC", (page_id,)
        ).fetchall()
    return render_template(
        "admin/page_edit.html",
        page=page,
        sections=sections,
        blog_posts=blog_posts,
        nav_layouts=NAV_LAYOUTS,
        #  The backdrop picker chooses from the Image Library, same as
        #  every other picture field in the app.
        media_images=[{"url": m["url"], "name": m["filename"]}
                      for m in _list_media(image_only=True)],
    )


@bp.route("/pages/<int:page_id>/bg-color", methods=["POST"])
@login_required
def page_bg_color(page_id):
    bg = request.form.get("bg_color", "").strip()
    if bg and not re.match(r"^#[0-9a-fA-F]{6}$", bg):
        flash("Please choose a valid color.", "error")
        return redirect(url_for("admin.page_edit", page_id=page_id))
    db = get_db()
    fields = {"bg_color": bg or None}
    #  Only touch what the submitted form actually carried: the colour and
    #  the picture are two forms on the same card, and saving one should
    #  not quietly clear the other.
    if "bg_image" in request.form:
        #  Same as a section's: a picture chosen from a template becomes
        #  this site's own copy, so the page keeps it if that template is
        #  ever removed (see packages.adopt_template_picture).
        chosen = (request.form.get("bg_image") or "").strip()
        if chosen:
            chosen = packages.adopt_template_picture(
                chosen, current_app.static_folder, current_app.config["UPLOAD_FOLDER"])
        fields["bg_image"] = chosen or None
        attach = (request.form.get("bg_attach") or "").strip()
        fields["bg_attach"] = attach if attach in ("scroll", "fixed") else "fixed"
        overlay = (request.form.get("bg_overlay") or "").strip()
        fields["bg_overlay"] = overlay if overlay in ("none", "light", "medium", "dark", "tint") else "none"
        surface = (request.form.get("bg_surface") or "").strip()
        fields["bg_surface"] = surface if surface in ("plain", "panels", "veil") else "plain"
    assignments = ", ".join(f"{key} = ?" for key in fields)
    db.execute(f"UPDATE pages SET {assignments} WHERE id = ?", (*fields.values(), page_id))
    db.commit()
    flash("Page background updated.", "success")
    return redirect(url_for("admin.page_edit", page_id=page_id))


@bp.route("/pages/<int:page_id>/seo", methods=["POST"])
@login_required
def page_seo(page_id):
    description = (request.form.get("meta_description") or "").strip()[:300]
    db = get_db()
    db.execute("UPDATE pages SET meta_description = ? WHERE id = ?", (description or None, page_id))
    db.commit()
    flash("SEO description saved.", "success")
    return redirect(url_for("admin.page_edit", page_id=page_id))


@bp.route("/pages/<int:page_id>/layout", methods=["POST"])
@login_required
def page_layout(page_id):
    """Per-page overrides on top of the layout cascade (template default
    -> site-wide -> here, see routes/admin/templates.py's activate route
    and __init__.py's get_nav_layout): this page can swap its own header
    arrangement, or hide a sidebar/footer zone the active template
    otherwise renders on every page. The zone's actual section content
    stays shared per-template — this only toggles whether THIS page
    shows it (see db.py's _migrate for the column comments)."""
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if not page:
        flash("Page not found.", "error")
        return redirect(url_for("admin.dashboard"))
    nav_override = request.form.get("nav_layout_override", "").strip()
    if nav_override not in NAV_LAYOUTS:
        nav_override = ""
    db.execute(
        "UPDATE pages SET nav_layout_override = ?, hide_sidebar = ?, hide_sidebar_right = ?, hide_footer = ? WHERE id = ?",
        (
            nav_override or None,
            1 if request.form.get("hide_sidebar") == "1" else 0,
            1 if request.form.get("hide_sidebar_right") == "1" else 0,
            1 if request.form.get("hide_footer") == "1" else 0,
            page_id,
        ),
    )
    db.commit()
    flash("Page layout updated.", "success")
    return redirect(url_for("admin.page_edit", page_id=page_id))


# ---------- Blog posts ----------
#
#  Keyed by blog, not by page. A post belongs to a set of writing, and
#  which page happens to show that set is a display decision made
#  elsewhere — one that can change, or be made twice, without any of this
#  needing to know.


def _post_return_url(default):
    """Where saving a post should land.

    A post is usually written from the page its blog is shown on, so that
    is where saving belongs — being left in the admin area afterwards
    loses your place in the work you were actually doing. Only same-site
    paths are honoured, so this cannot be used to bounce somebody
    somewhere else.
    """
    target = (request.form.get("next") or request.args.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def _published_date(form, existing=""):
    """Turns "publish this" plus an optional date into a stored date.

    Publishing used to mean typing a date, which asks somebody to know
    that a date is what makes a post public. Ticking the box is the
    decision; the date is a detail, and today's is the obvious default.
    """
    if not form.get("publish"):
        return ""
    typed = (form.get("published_at") or "").strip()
    return typed or existing or datetime.date.today().isoformat()


@bp.route("/blogs/new", methods=["POST"])
@login_required
def blog_new():
    """Makes a blog. The Dashboard could list them and open them, and
    could not make one -- the only way to get a blog was to drop a Blog
    tool on a page and let it make one for you, which is a fine shortcut
    and a poor only route."""
    db = get_db()
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Give the blog a name.", "error")
        return redirect(url_for("admin.dashboard"))
    blog_service.create_blog(db, name)
    db.commit()
    flash('Blog "%s" created.' % name, "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/blogs/<int:blog_id>/rename", methods=["POST"])
@login_required
def blog_rename(blog_id):
    """A new name, the same address. Post URLs are built from the slug, so
    renaming deliberately leaves it alone -- see create_blog."""
    db = get_db()
    if not blog_service.get_blog(db, blog_id):
        flash("That blog no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    blog_service.rename_blog(db, blog_id, request.form.get("name"))
    db.commit()
    return redirect(url_for("admin.dashboard"))


@bp.route("/blogs/<int:blog_id>/delete", methods=["POST"])
@login_required
def blog_delete(blog_id):
    """Removes a blog and everything in it, having said how much that is."""
    db = get_db()
    row = blog_service.get_blog(db, blog_id)
    if not row:
        flash("That blog no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    posts = blog_service.delete_blog(db, blog_id)
    db.commit()
    flash('Deleted "%s" and %d post%s.' % (row["name"], posts, "" if posts == 1 else "s"),
          "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/blogs/<int:blog_id>")
@login_required
def blog_manage(blog_id):
    db = get_db()
    blog = blog_service.get_blog(db, blog_id)
    if not blog:
        flash("That blog no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    posts = blog_service.posts_for(db, blog_id, published_only=False)
    return render_template("admin/blog_manage.html", blog=blog, posts=posts)


@bp.route("/blogs/<int:blog_id>/posts/new", methods=["GET", "POST"])
@login_required
def blog_post_new(blog_id):
    db = get_db()
    blog = blog_service.get_blog(db, blog_id)
    if not blog:
        flash("That blog no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Please enter a post title.", "error")
            return redirect(url_for("admin.blog_post_new", blog_id=blog_id))
        #  One creator, in the service: a post arrives three ways now and
        #  the unique-address rule has to be the same for all of them.
        post_id = blog_service.create_post(
            db, blog_id, title,
            content=request.form.get("content", "").strip(),
            excerpt=request.form.get("excerpt", "").strip(),
            published_at=_published_date(request.form))
        db.commit()
        flash("Post created.", "success")
        return redirect(_post_return_url(
            url_for("admin.blog_post_edit", blog_id=blog_id, post_id=post_id)))
    return render_template("admin/blog_post_edit.html", blog=blog, post=None,
                           next_url=_post_return_url(""))


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>", methods=["GET", "POST"])
@login_required
def blog_post_edit(blog_id, post_id):
    db = get_db()
    blog = blog_service.get_blog(db, blog_id)
    post = db.execute(
        "SELECT * FROM blog_posts WHERE id = ? AND blog_id = ?", (post_id, blog_id)
    ).fetchone()
    if not blog or not post:
        flash("Post not found.", "error")
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        title = request.form.get("title", "").strip() or post["title"]
        #  Which blog it belongs to is a control on the tool now, so a
        #  post written in the wrong one is a dropdown rather than a
        #  rewrite. The address follows the blog, and blog_service.move
        #  is what keeps it free there.
        wanted = request.form.get("blog_id", type=int)
        if wanted and wanted != blog_id and blog_service.move(db, post_id, wanted):
            blog_id = wanted
            blog = blog_service.get_blog(db, blog_id)
        db.execute(
            #  The post's picture comes from the writing toolbar now (the
            #  Image button sets it and shows it where it will appear), so
            #  it is saved with everything else rather than through a
            #  second form of its own.
            "UPDATE blog_posts SET title = ?, excerpt = ?, content = ?, published_at = ?, "
            "featured_image = ? WHERE id = ?",
            (
                title,
                request.form.get("excerpt", "").strip(),
                request.form.get("content", "").strip(),
                _published_date(request.form, post["published_at"]),
                (request.form.get("featured_image") or "").strip() or None,
                post_id,
            ),
        )
        db.commit()
        flash("Post updated.", "success")
        return redirect(_post_return_url(
            url_for("admin.blog_post_edit", blog_id=blog_id, post_id=post_id)))
    #  What the Send panel on this screen needs to know. Worked out here
    #  rather than in the template, and kept to the few facts that decide
    #  whether sending is possible at all -- the same three the newsletter
    #  bar on a page asks: something to send with, a postal address on
    #  file, and somebody to send to.
    from ...services import legal as legal_service, newsletter as newsletter_service
    from ...services import subscribers as subscriber_service
    from . import get_email_settings, get_site_settings
    from ... import mailer as mailer_module
    _line, has_address = newsletter_service.sender_line(
        legal_service.settings_for(db), (get_site_settings(db) or {}).get("site_title"))
    counts = subscriber_service.counts(db)
    email_ready = mailer_module.is_configured(get_email_settings(db))
    #  The same tool the Blogs screen carries, so this screen needs what
    #  that tool reads: the post with its blog on it, every blog to move
    #  it to, and the schedules it can be published on.
    from ...services import scheduling as scheduling_service
    waiting = {row["target_id"]: row
               for row in scheduling_service.recent(db, limit=200)
               if row["kind"] == "publish" and not row["claimed_at"]}
    return render_template(
        "admin/blog_post_edit.html", blog=blog,
        post=blog_service.post_with_blog(db, post_id),
        blogs=blog_service.list_blogs(db),
        post_scheduled=waiting.get(post_id),
        schedule_choices=[
            {"name": t["name"], "says": scheduling_service.describe_template(t),
             "dates": [{"utc": d.strftime("%Y-%m-%d %H:%M:%S")}
                       for d in scheduling_service.upcoming(
                           t, scheduling_service.utcnow(), 8)]}
            for t in scheduling_service.templates(db)],
        next_url=_post_return_url(""),
        audiences=subscriber_service.AUDIENCES,
        audience_counts={key: subscriber_service.audience_count(db, key)
                         for key, _label in subscriber_service.AUDIENCES},
        counts=counts,
        last_send=newsletter_service.last_send(db, "post", post_id),
        newsletter_ready={"email_ready": email_ready, "has_address": has_address,
                          "can_send": bool(email_ready and has_address and counts["active"])},
    )


@bp.route("/blogs/<int:blog_id>/posts/draft", methods=["POST"])
@login_required
def blog_post_draft(blog_id):
    """Starts a post and goes straight to it, on the site itself.

    Writing a post is writing, and everything else in this app is written
    on the page it appears on. So this makes an empty draft and hands the
    admin its own page in editing mode, rather than a form in the admin
    area — the post is typed where it will be read.
    """
    db = get_db()
    if not blog_service.get_blog(db, blog_id):
        flash("That blog no longer exists.", "error")
        return redirect(url_for("admin.dashboard"))
    #  No published date: a new post is a draft until its author says
    #  otherwise, so nothing half-written is ever public for a moment.
    slug = blog_service.unique_slug(db, blog_id, "New post")
    blog_service.create_post(db, blog_id, "New post", published_at="")
    db.commit()
    blog = blog_service.get_blog(db, blog_id)
    return redirect(url_for("public.blog_post", slug=blog["slug"], post_slug=slug))


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/publish", methods=["POST"])
@login_required
def blog_post_publish(blog_id, post_id):
    """Publishes a post, or puts it back to a draft.

    One button where the blog is shown, because deciding a post is ready
    is not the same job as writing it and should not need the writing form
    opened to do it. Publishing keeps whatever date the post already had,
    so re-publishing something does not silently re-date it.
    """
    db = get_db()
    post = db.execute(
        "SELECT * FROM blog_posts WHERE id = ? AND blog_id = ?", (post_id, blog_id)
    ).fetchone()
    if not post:
        flash("Post not found.", "error")
        return redirect(url_for("admin.dashboard"))
    published = "" if post["published_at"] else (
        post["published_at"] or datetime.date.today().isoformat())
    db.execute("UPDATE blog_posts SET published_at = ? WHERE id = ?", (published, post_id))
    db.commit()
    flash("Post published." if published else "Post put back to a draft.", "success")
    return redirect(_post_return_url(url_for("admin.blog_manage", blog_id=blog_id)))


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/update", methods=["POST"])
@login_required
def blog_post_update(blog_id, post_id):
    """Saves one field of a post, edited in place on its own page.

    Patch-shaped like section_update, and for the same reason: the page
    sends whichever field just changed, not the whole post, so two people
    (or two tabs) editing different parts do not overwrite each other.
    """
    db = get_db()
    post = db.execute(
        "SELECT * FROM blog_posts WHERE id = ? AND blog_id = ?", (post_id, blog_id)
    ).fetchone()
    if not post:
        return (jsonify({"error": "Post not found."}), 404) if wants_json() else redirect(
            url_for("admin.dashboard"))
    fields, values = [], []
    for name in ("title", "excerpt", "content", "published_at"):
        if name in request.form:
            fields.append(f"{name} = ?")
            values.append(request.form.get(name, "").strip())
    if fields:
        values.append(post_id)
        db.execute(f"UPDATE blog_posts SET {', '.join(fields)} WHERE id = ?", values)
        db.commit()
    if wants_json():
        return jsonify({"ok": True})
    return redirect(url_for("public.blog_post",
                            slug=blog_service.get_blog(db, blog_id)["slug"],
                            post_slug=post["slug"]))


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def blog_post_delete(blog_id, post_id):
    db = get_db()
    db.execute("DELETE FROM blog_posts WHERE id = ? AND blog_id = ?", (post_id, blog_id))
    db.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("admin.blog_manage", blog_id=blog_id))


@bp.route("/blogs/<int:blog_id>/posts/<int:post_id>/image-upload", methods=["POST"])
@login_required
def blog_post_image_upload(blog_id, post_id):
    db = get_db()
    post = db.execute(
        "SELECT * FROM blog_posts WHERE id = ? AND blog_id = ?", (post_id, blog_id)
    ).fetchone()
    if not post:
        flash("Post not found.", "error")
        return redirect(url_for("admin.dashboard"))
    file = request.files.get("image")
    if not file or file.filename == "":
        flash("Please choose an image file.", "error")
        return redirect(url_for("admin.blog_post_edit", blog_id=blog_id, post_id=post_id))
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        flash("Please upload a PNG, JPG, GIF, WEBP, or SVG image.", "error")
        return redirect(url_for("admin.blog_post_edit", blog_id=blog_id, post_id=post_id))
    unique_name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name))
    db.execute(
        "UPDATE blog_posts SET featured_image = ? WHERE id = ?",
        (f"/static/uploads/{unique_name}", post_id),
    )
    db.commit()
    flash("Image updated.", "success")
    return redirect(url_for("admin.blog_post_edit", blog_id=blog_id, post_id=post_id))

@bp.route("/pages/<int:page_id>/settings", methods=["POST"])
@login_required
def page_settings(page_id):
    """The two questions that are about the page rather than its look.

    Whether visitors can read it, and whether it carries the newsletter
    controls. Both are ordinary settings on an ordinary page, which is the
    point: an issue that goes only to the list, an issue anybody can read,
    or a page that stops being a newsletter -- none of that should mean
    making a different KIND of page and moving the writing across.
    """
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if not page:
        flash("Page not found.", "error")
        return redirect(url_for("admin.dashboard"))
    #  A home page nobody can reach is a site nobody can reach.
    public = 1 if (request.form.get("is_public") == "1" or page["is_home"]) else 0
    page_type = "newsletter" if request.form.get("is_newsletter") == "1" else "standard"
    db.execute("UPDATE pages SET is_public = ?, page_type = ? WHERE id = ?",
               (public, page_type, page_id))
    db.commit()
    if page["is_home"] and request.form.get("is_public") != "1":
        flash("The home page has to stay on the site — everything else can be private.", "warning")
    else:
        flash("Saved.", "success")
    where = (request.form.get("next") or "").strip()
    if where.startswith("/") and not where.startswith("//"):
        return redirect(where)
    return redirect(url_for("admin.page_edit", page_id=page_id))


@bp.route("/pages/<int:page_id>/set-home", methods=["POST"])
@login_required
def page_set_home(page_id):
    db = get_db()
    db.execute("UPDATE pages SET is_home = 0")
    db.execute("UPDATE pages SET is_home = 1 WHERE id = ?", (page_id,))
    db.commit()
    flash("Home page updated.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/pages/<int:page_id>/rename", methods=["POST"])
@login_required
def page_rename(page_id):
    """Renames a page's display title only — the slug/URL is left alone so
    existing links/bookmarks to it keep working. (Changing the URL too
    would need its own explicit, more careful flow — this is just the
    label people see.)"""
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if not page:
        if wants_json():
            return jsonify({"error": "Page not found."}), 404
        flash("Page not found.", "error")
        return redirect(url_for("admin.dashboard"))
    title = (request.form.get("title") or "").strip()
    if not title:
        if wants_json():
            return jsonify({"error": "Please enter a page name."}), 400
        flash("Please enter a page name.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE pages SET title = ? WHERE id = ?", (title, page_id))
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "title": title})
    flash("Page renamed.", "success")
    return _redirect_next("admin.dashboard")


@bp.route("/pages/<int:page_id>/delete", methods=["POST"])
@login_required
def page_delete(page_id):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if page and page["is_home"]:
        if wants_json():
            return jsonify({"error": "You can't delete the home page. Set another page as home first."}), 400
        flash("You can't delete the home page. Set another page as home first.", "error")
        return redirect(url_for("admin.dashboard"))
    db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
    # A Menu tool's link list is baked HTML (data-menu-items + rendered
    # <a> tags), not re-resolved against the pages table on every render —
    # see _regenerate_menu_html's docstring. Without this, a deleted page
    # stays as a dead link in any Menu that included it until an admin
    # happens to re-open and re-save that menu's own config form.
    for menu_section in db.execute(
        "SELECT id, content FROM sections WHERE type = 'html' AND content LIKE '%cms-menu%'"
    ).fetchall():
        db.execute(
            "UPDATE sections SET content = ? WHERE id = ?",
            (_regenerate_menu_html(db, menu_section["content"]), menu_section["id"]),
        )
    db.commit()
    if wants_json():
        return jsonify({"ok": True, "home_url": url_for("public.home")})
    flash("Page deleted.", "success")
    # if we just deleted the page the admin was standing on, "next" is now a 404 — go home instead
    next_url = request.form.get("next")
    if next_url and page and next_url.rstrip("/").endswith(page["slug"]):
        return redirect(url_for("public.home"))
    return _redirect_next("admin.dashboard")


@bp.route("/content/reset-all", methods=["POST"])
@login_required
def content_reset_all():
    """A theme (colors/fonts/header-footer chrome, keyed by template_id) and
    page content (sections, keyed by page_id) are independent by design —
    sections.page_id and sections.template_id are two separate FKs on the
    same table (see db.py's sections_new migration), and switching or
    deleting a template only ever cascades its own template_id-scoped
    rows. So swapping the active theme never touches what "Insert Layout"
    put into a page's body earlier — that's intentional (a page's content
    is the admin's own, not the theme's, once it's been placed), but it
    means there's no way to blank every page back to empty short of
    deleting each section by hand. This does that in one action: every
    page keeps existing (title, slug, nav position, page type all
    untouched) but loses every section, exactly like a freshly created
    page — ready for a fresh "Insert Layout" from whichever theme, or to
    build by hand. Header/footer chrome and blog posts are untouched."""
    db = get_db()
    db.execute("DELETE FROM sections WHERE page_id IS NOT NULL")
    db.commit()
    flash("All page content cleared. Every page is now empty — use \"Insert Layout\" on a theme, or add sections by hand.", "success")
    return redirect(url_for("admin.dashboard"))




