"""Blogs: a named set of posts, and the tool that shows one.

A blog used to be a kind of page. That made "this site has a blog" and
"this page is the blog" the same statement, so a site could have exactly
one, it lived at exactly one address, and nothing else could show its
posts. Making it a tool separates the two: a blog is a named thing posts
belong to, and a Blog tool is one place a set of them is shown. A site can
have several blogs, a page can show more than one, and the same blog can
appear on two pages without its posts being duplicated.

Posts therefore belong to a blog, never to a page (see `blog_posts.blog_id`).
The blog's own slug is what a post's address is built from, so a post keeps
its URL no matter which page happens to display it -- or if none does.

Follows the rule in CLAUDE.md: services take `db` and plain arguments, and
the tool's display settings live in its own markup rather than in a column
on some other table.
"""
import re

from bs4 import BeautifulSoup
from markupsafe import escape as html_escape

#  How the cards look. Kept here rather than on the page, because it is a
#  property of this showing of the posts -- two Blog tools on the same
#  blog may reasonably look different.
BLOG_STYLES = (
    ("cards", "Cards"),
    ("list", "Simple list"),
    ("grid", "Tight grid"),
)
BLOG_STYLE_ATTR = "data-blog-style"


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "blog"


# ---------------------------------------------------------------- blogs


def list_blogs(db):
    return db.execute("SELECT * FROM blogs ORDER BY name").fetchall()


def get_blog(db, blog_id):
    return db.execute("SELECT * FROM blogs WHERE id = ?", (blog_id,)).fetchone()


def get_blog_by_slug(db, slug):
    return db.execute("SELECT * FROM blogs WHERE slug = ?", (slug,)).fetchone()


def create_blog(db, name, slug=None):
    """A new blog, with an address of its own that no other blog has.

    The slug is what post URLs are built from, so it has to be unique and
    it has to be stable -- renaming a blog later leaves it alone rather
    than breaking every link to every post in it.
    """
    name = (name or "").strip() or "Blog"
    base = slugify(slug or name)
    candidate, n = base, 2
    while db.execute("SELECT 1 FROM blogs WHERE slug = ?", (candidate,)).fetchone():
        candidate = f"{base}-{n}"
        n += 1
    cur = db.execute("INSERT INTO blogs (name, slug) VALUES (?, ?)", (name, candidate))
    return cur.lastrowid


def delete_blog(db, blog_id):
    """Removes a blog and the posts in it. Returns how many posts went.

    A blog is a set of posts, so there is no such thing as deleting the
    set and keeping the members -- a post with no blog has no address,
    because its URL is built from the blog's slug. The count is returned
    so the asking can say what it is about to destroy rather than "are you
    sure".

    Any Blog tool pointing at it is left alone deliberately. It will find
    nothing and say so, which is honest and recoverable; hunting through
    every page's markup to rewrite blocks is not something a delete should
    do quietly.
    """
    posts = db.execute(
        "SELECT COUNT(*) AS n FROM blog_posts WHERE blog_id = ?", (blog_id,)
    ).fetchone()["n"]
    db.execute("DELETE FROM blog_posts WHERE blog_id = ?", (blog_id,))
    db.execute("DELETE FROM blogs WHERE id = ?", (blog_id,))
    return posts


def rename_blog(db, blog_id, name):
    """Renames a blog without touching its slug — see create_blog."""
    db.execute("UPDATE blogs SET name = ? WHERE id = ?", ((name or "").strip() or "Blog", blog_id))


def unique_slug(db, blog_id, title):
    """An address for a post that no other post in this blog has."""
    base = slugify(title) or "post"
    slug, i = base, 2
    while db.execute("SELECT 1 FROM blog_posts WHERE blog_id = ? AND slug = ?",
                     (blog_id, slug)).fetchone():
        slug = "%s-%d" % (base, i)
        i += 1
    return slug


def create_post(db, blog_id, title, content="", excerpt="", published_at=None):
    """Writes one post and returns its id.

    Here rather than in a route because there are three ways a post
    arrives now -- typed into the editor, saved as a draft, and a
    newsletter keeping a copy of itself when it goes out -- and the
    unique-address rule has to be the same for all of them. Two of them
    were already separate copies of the same six lines.
    """
    return db.execute(
        "INSERT INTO blog_posts (blog_id, title, slug, excerpt, content, published_at, "
        "position) VALUES (?, ?, ?, ?, ?, ?, "
        "(SELECT COALESCE(MAX(position), 0) + 1 FROM blog_posts WHERE blog_id = ?))",
        (blog_id, title, unique_slug(db, blog_id, title), excerpt or "", content or "",
         published_at, blog_id)).lastrowid


def publish(db, post_id, when=None):
    """Makes a post public. True if there was one to publish.

    Keeps whatever date the post already had, so re-publishing something
    does not silently re-date it -- the same rule the Publish button on
    the list follows. A post with no date at all gets today's.
    """
    import datetime
    row = db.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return False
    stamp = row["published_at"] or (
        when or datetime.datetime.utcnow()).strftime("%Y-%m-%d")
    db.execute("UPDATE blog_posts SET published_at = ? WHERE id = ?", (stamp, post_id))
    return True


def move(db, post_id, blog_id):
    """Puts a post in a different blog, with an address that is free there.

    A post's address is built from its blog's, so moving it changes where
    it lives -- and the slug it arrived with may already be taken in the
    blog it is going to. Checked rather than assumed: two posts in one
    blog sharing an address means one of them is unreachable.
    """
    row = db.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,)).fetchone()
    if not row or row["blog_id"] == blog_id or not get_blog(db, blog_id):
        return False
    clash = db.execute("SELECT 1 FROM blog_posts WHERE blog_id = ? AND slug = ?",
                       (blog_id, row["slug"])).fetchone()
    slug = unique_slug(db, blog_id, row["title"]) if clash else row["slug"]
    db.execute("UPDATE blog_posts SET blog_id = ?, slug = ? WHERE id = ?",
               (blog_id, slug, post_id))
    return True


def posts_for(db, blog_id, published_only=True, limit=0):
    """A blog's posts, newest first.

    `published_only` is what a visitor sees: a post with no published date
    is a draft, and drafts are visible while editing so they can be worked
    on in place, but never to anybody else.
    """
    sql = "SELECT * FROM blog_posts WHERE blog_id = ?"
    if published_only:
        sql += " AND published_at != '' AND published_at IS NOT NULL"
    sql += " ORDER BY position DESC, id DESC"
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"
    return db.execute(sql, (blog_id,)).fetchall()


# ----------------------------------------------------------- the tool


def post_with_blog(db, post_id):
    """One post, carrying its blog's name and address.

    A post's web address is built from its blog's slug, so almost nothing
    can do anything useful with a post row on its own -- and every caller
    fetching the blog separately is a join waiting to be forgotten.
    """
    return db.execute(
        "SELECT p.*, b.name AS blog_name, b.slug AS blog_slug "
        "FROM blog_posts p JOIN blogs b ON b.id = p.blog_id WHERE p.id = ?",
        (post_id,)).fetchone()


def everything(db, waiting=None):
    """Every post on this site, newest first, with what state it is in.

    One table across every blog. It was one list per blog, which reads as
    several small screens and hides the only question anybody asks of
    that page: what have I written, and what is still a draft.

    `waiting` is the scheduled-publish jobs keyed by post id; a post can
    be a draft that is going to publish itself, which is neither of the
    other two states and is exactly the one somebody would otherwise
    publish by hand a second time.
    """
    waiting = waiting or {}
    rows = db.execute(
        "SELECT p.*, b.name AS blog_name, b.slug AS blog_slug "
        "FROM blog_posts p JOIN blogs b ON b.id = p.blog_id "
        "ORDER BY COALESCE(NULLIF(p.published_at, ''), '9999') DESC, p.id DESC").fetchall()
    out = []
    for row in rows:
        job = waiting.get(row["id"])
        out.append({
            "row": row,
            "job": job,
            "state": ("published" if row["published_at"]
                      else "waiting" if job else "draft"),
        })
    return out


def post_html(content):
    """A post's writing as HTML.

    Old posts were typed as plain text with blank lines between
    paragraphs; newer ones come from the editor already as HTML. Lived in
    routes/public.py, which was fine while a post was only ever shown on
    a page -- it is needed by the newsletter now, and a route is not
    somewhere another route can reach into. Same rule as everything else
    here: shared logic is a service.
    """
    if not content:
        return ""
    if "<" in content:
        return content
    from html import escape
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return "\n".join("<p>%s</p>" % escape(p) for p in paragraphs)


def build_blog(blog_id, style="cards", count=0):
    """The tool's stored markup: which blog, shown how, how many.

    A marker rather than the posts themselves — the same reasoning as the
    Shop tool. Posts change, and a copy frozen into a section would go on
    advertising last month's writing. What is stored is the question; the
    answer is worked out when the page is rendered.
    """
    style = style if style in dict(BLOG_STYLES) else "cards"
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        count = 0
    blog_attr = f' data-blog-id="{int(blog_id)}"' if blog_id else ' data-blog-id=""'
    return (f'<div class="cms-blog"{blog_attr} {BLOG_STYLE_ATTR}="{style}" '
            f'data-blog-count="{count}"></div>')


def blog_settings(content):
    """Which blog this tool shows, and how — read back off its markup."""
    soup = BeautifulSoup(content or "", "html.parser")
    box = soup.find(class_="cms-blog")
    if box is None:
        return {"blog_id": None, "style": "cards", "count": 0}
    raw_id = box.get("data-blog-id") or ""
    style = box.get(BLOG_STYLE_ATTR) or "cards"
    try:
        count = max(0, int(box.get("data-blog-count") or 0))
    except ValueError:
        count = 0
    return {
        "blog_id": int(raw_id) if raw_id.isdigit() else None,
        "style": style if style in dict(BLOG_STYLES) else "cards",
        "count": count,
    }


def apply_blog_form(db, form):
    """One submit: pick a blog (or start one), a style, and how many."""
    chosen = (form.get("blog_id") or "").strip()
    #  Starting a blog lives where one is first wanted, rather than on a
    #  settings screen somebody has to know to visit. It is its own button
    #  with its own field name — sharing blog_id with the select above
    #  meant only the select was ever read.
    if (form.get("blog_op") or "") == "new":
        blog_id = create_blog(db, form.get("blog_new_name", ""))
    else:
        blog_id = int(chosen) if chosen.isdigit() else None
    if blog_id and (form.get("blog_name") or "").strip():
        rename_blog(db, blog_id, form.get("blog_name"))
    return build_blog(blog_id, form.get("blog_style"), form.get("blog_count") or 0)


def render_blog(db, content, editing=False, post_url=None, edit_url=None):
    """The cards a visitor sees, built when the page is rendered.

    `post_url` is passed in rather than imported, so this stays a service:
    it needs a URL builder but must not reach into Flask's routing itself.
    """
    settings = blog_settings(content)
    if not settings["blog_id"]:
        return ('<p class="cms-blog-empty">No blog chosen yet — pick one in this '
                'tool, or start a new one.</p>')
    blog = get_blog(db, settings["blog_id"])
    if not blog:
        return ('<p class="cms-blog-empty">That blog no longer exists — choose '
                'another in this tool.</p>')
    posts = posts_for(db, blog["id"], published_only=not editing, limit=settings["count"])
    if not posts:
        return ('<p class="cms-blog-empty">No posts yet'
                + (" — add one from this tool." if editing else ".")
                + "</p>")
    cards = []
    for post in posts:
        #  While editing, a card is the way into the post — the posts are
        #  already listed here, so listing them a second time in the
        #  toolbar was the same information twice. A visitor's card still
        #  points at the post itself.
        if editing and edit_url:
            href, extra = edit_url(post["id"]), ' data-cms-edit-link title="Open this post to edit it"'
        else:
            href, extra = (post_url(blog["slug"], post["slug"]) if post_url else "#"), ""
        image = ""
        if post["featured_image"]:
            image = ('<div class="cms-blog-card-image" style="background-image:url(\''
                     + html_escape(post["featured_image"]) + '\')"></div>')
        date = (f'<span class="cms-blog-date">{html_escape(post["published_at"])}</span>'
                if post["published_at"] else
                '<span class="cms-blog-date cms-blog-draft">Draft</span>')
        excerpt = f"<p>{html_escape(post['excerpt'])}</p>" if post["excerpt"] else ""
        cards.append(
            f'<a class="cms-blog-card" href="{html_escape(href)}"{extra}>{image}'
            f'<div class="cms-blog-card-body"><h3>{html_escape(post["title"])}</h3>'
            f"{date}{excerpt}</div></a>"
        )
    return (f'<div class="cms-blog-grid cms-blog-{settings["style"]}">'
            + "".join(cards) + "</div>")
