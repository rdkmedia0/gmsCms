"""Search-engine essentials: a sitemap, a robots file, and the tags a
crawler and a social preview read out of a page's <head>.

Kept out of the templates (which stay structure-only) and out of the
routes (which stay thin): this builds the values, the route serves them,
the head renders them. Absolute URLs throughout, because a sitemap entry
and an og:url mean nothing relative -- they are built from the site's own
public address (services/site.py), the one authority for where this site
lives.

Only PUBLIC things appear: a page marked not-public (is_public = 0) 404s
for a visitor and is left out of the sitemap; a blog post that has not
been published is left out too. Nothing here invents a page a crawler
could not otherwise reach.
"""
import json
import re


#  Sections that are navigation, a form, a file list or contact details --
#  not prose. Their text ("Home About Contact", "Name Email Message", a
#  download's file path, "Available on request Zurich") is noise in a
#  description, so a summary skips them and reads the real content instead.
_STRUCTURAL_MARKERS = ("cms-menu", "cms-breadcrumb", "cms-contact",
                       "cms-wordmark", "cms-lang-switcher", "cms-basket",
                       "cms-search", "cms-newsletter-signup", "cms-file-tool")


def summarize_html(html, limit=160):
    """A plain-text description from HTML content: the first ~limit
    characters of real text, cut at a word boundary, with an ellipsis when
    it was trimmed. No markup, whitespace collapsed."""
    from bs4 import BeautifulSoup
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    #  A bare URL or a file path that slipped through as visible text is not
    #  a description -- drop it before trimming.
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"/\S*\.\w{2,5}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" .,;:—-") + "…"


def _is_structural(content):
    return any(m in (content or "") for m in _STRUCTURAL_MARKERS)


def page_summary(db, page_id, limit=160):
    """A description built FROM a page's own content -- so a page can
    describe itself and nobody has to write a meta description by hand. The
    prose sections in order, up to `limit`, with menus/forms/search skipped
    as noise. Empty when a page has no readable text (a gallery, say),
    which the caller falls back from."""
    rows = db.execute(
        "SELECT content FROM sections WHERE page_id = ? ORDER BY position",
        (page_id,)).fetchall()
    html = " ".join(r["content"] for r in rows
                    if r["content"] and not _is_structural(r["content"]))
    return summarize_html(html, limit)


def _abs(base, path_or_url):
    """An absolute URL from a stored path, or a full URL left as it is."""
    if not path_or_url:
        return None
    if path_or_url.startswith(("http://", "https://", "//")):
        return path_or_url
    return base.rstrip("/") + "/" + str(path_or_url).lstrip("/")


def _xml_escape(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def sitemap_entries(db, base):
    """(loc, lastmod-or-None) for every URL a crawler should see: the home
    page, every PUBLIC page, and every PUBLISHED blog post."""
    base = base.rstrip("/")
    entries = []
    pages = db.execute(
        "SELECT slug, is_home FROM pages WHERE COALESCE(is_public, 1) = 1 "
        "ORDER BY nav_order, title").fetchall()
    for p in pages:
        loc = base + "/" if p["is_home"] else base + "/" + p["slug"]
        entries.append((loc, None))
    posts = db.execute(
        "SELECT bp.slug AS pslug, bp.published_at, b.slug AS bslug "
        "FROM blog_posts bp JOIN blogs b ON b.id = bp.blog_id "
        "WHERE bp.published_at IS NOT NULL AND bp.published_at != ''").fetchall()
    for p in posts:
        #  A post lives at /blog/<blog-slug>/<post-slug> (see public.blog_post);
        #  the blog's own slug keeps the address stable however pages move.
        entries.append((base + "/blog/" + p["bslug"] + "/" + p["pslug"],
                        (p["published_at"] or "")[:10] or None))
    return entries


def sitemap_xml(entries):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in entries:
        lines.append("  <url><loc>%s</loc>%s</url>" % (
            _xml_escape(loc),
            ("<lastmod>%s</lastmod>" % _xml_escape(lastmod)) if lastmod else ""))
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_txt(base):
    """Allow everything a visitor can see, keep crawlers out of the admin
    and the token-scoped buyer pages, and point them at the sitemap."""
    return ("User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Disallow: /my/\n"
            "Sitemap: %s/sitemap.xml\n" % base.rstrip("/"))


def head_meta(db, page, post, site_settings, base, path):
    """The <head> SEO block for a page (or a blog post shown through it):
    a canonical URL, Open Graph + Twitter tags for a rich share preview,
    and JSON-LD (a WebSite always; an Article for a post)."""
    ss = site_settings or {}
    site_title = ss.get("site_title") or "Website"
    base = base.rstrip("/")
    canonical = base + (path if path and path != "/" else "/")
    is_post = bool(post)
    #  Description fallback chain: what the owner wrote, else a summary the
    #  page builds from its OWN content (so nobody has to write one), else
    #  the site tagline, else nothing.
    if is_post:
        title = post["title"]
        desc = ((post["excerpt"] or "").strip()
                or summarize_html(post["content"])
                or ss.get("site_tagline") or "")
        image = _abs(base, post["featured_image"])
        og_type = "article"
    else:
        title = site_title if page["is_home"] else page["title"]
        desc = ((page["meta_description"] or "").strip()
                or page_summary(db, page["id"])
                or ss.get("site_tagline") or "")
        image = None
        og_type = "website"

    ld = [{"@context": "https://schema.org", "@type": "WebSite",
           "name": site_title, "url": base + "/"}]
    if is_post:
        article = {"@context": "https://schema.org", "@type": "Article",
                   "headline": title, "mainEntityOfPage": canonical,
                   "publisher": {"@type": "Organization", "name": site_title}}
        if post["published_at"]:
            article["datePublished"] = post["published_at"]
        if image:
            article["image"] = image
        ld.append(article)

    return {
        "canonical": canonical,
        "title": title,
        "description": (desc or "")[:300],
        "og_type": og_type,
        "og_image": image,
        "og_site_name": site_title,
        "twitter_card": "summary_large_image" if image else "summary",
        #  Rendered raw inside a <script type="application/ld+json"> block, so
        #  a "</script>" in an admin-authored title must not break out of it.
        #  Escaping < > & as \uXXXX keeps the JSON valid and inert as HTML --
        #  the browser decodes them back to the characters when it parses the
        #  JSON, and never sees a tag.
        "json_ld": (json.dumps(ld, ensure_ascii=False)
                    .replace("<", "\\u003c").replace(">", "\\u003e")
                    .replace("&", "\\u0026")),
    }
