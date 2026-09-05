"""Locale-based, user-selectable translation.

The shape, and why it is this shape:

- **Translated ONCE, on the owner's command, then stored.** When a site is
  finished the owner clicks "Translate", the configured AI provider renders
  every public page's text into each enabled language, and the results are
  kept. A visitor is served the STORED copy for their language -- no AI call
  on a page view, so no per-visitor cost, no first-view stall, and nothing a
  visitor reads ever leaves this server. This mirrors the self-hosted-fonts
  decision: the privacy-preserving option is the default because a small
  site's owner cannot audit a third party on their visitors' behalf.

- **Content-addressed cache.** A translation is keyed by (language, sha256 of
  the source text), so an identical string anywhere on the site is translated
  once, and EDITING a string changes its hash -- a silent cache miss that
  falls back to the original until the next Translate run refreshes it. No
  per-section bookkeeping, and no stale translation is ever shown as if it
  were current.

- **The language set is CLOSED**, like the fonts and the colour presets. A
  fixed list of common languages the owner ticks; the source is the site's
  own language. A free-form "any language" box would be a provider bill and a
  quality lottery nobody chose.

- **Locale decides the DEFAULT, the visitor decides the rest.** The first
  visit picks a language from the browser's own `Accept-Language` (never IP or
  region -- a locale is a stated preference, an IP is a guess about where a
  body is), among the languages actually enabled; a Language switcher lets the
  visitor override it, remembered in a cookie. No account, no profile.

Import direction stays one-way: this is a service, called by routes and by the
render. It reaches the AI the same way the theme generator does -- lazily,
through `assistant._call_provider` -- and never imports from `routes`.
"""

import re
import json
import time
import hashlib
import threading

# ---------------------------------------------------------------------------
# The closed set of offerable languages. (code, English name, native name,
# right-to-left?). The source language is the site's own and is not in here as
# a "target"; it is whatever `site_language` says (default English).
# Chosen as the widely-served set the large builders default to, spanning the
# scripts that actually need distinct handling (RTL, CJK) so the render and the
# switcher are exercised, not just five flavours of Latin script.
# ---------------------------------------------------------------------------
LANGUAGES = [
    ("es", "Spanish", "Español", False),
    ("fr", "French", "Français", False),
    ("de", "German", "Deutsch", False),
    ("it", "Italian", "Italiano", False),
    ("pt", "Portuguese", "Português", False),
    ("nl", "Dutch", "Nederlands", False),
    ("pl", "Polish", "Polski", False),
    ("ru", "Russian", "Русский", False),
    ("ar", "Arabic", "العربية", True),
    ("zh", "Chinese (Simplified)", "简体中文", False),
    ("ja", "Japanese", "日本語", False),
    ("hi", "Hindi", "हिन्दी", False),
]
_BY_CODE = {code: (code, en, native, rtl) for (code, en, native, rtl) in LANGUAGES}

#  A representative flag per language, drawn as inline SVG rather than an emoji
#  -- flag EMOJI render as bare letters ("GB") on Windows and some Linux, so
#  they cannot be relied on. A language is not a country, so this is a
#  convenience, not a claim. viewBox is 0 0 3 2; the render sizes it.
_FLAG_BODY = {
    #  Tricolours and simple bars.
    "fr": '<rect width="1" height="2" fill="#0055A4"/><rect x="1" width="1" height="2" fill="#fff"/><rect x="2" width="1" height="2" fill="#EF4135"/>',
    "it": '<rect width="1" height="2" fill="#008C45"/><rect x="1" width="1" height="2" fill="#fff"/><rect x="2" width="1" height="2" fill="#CD212A"/>',
    "de": '<rect width="3" height=".667" fill="#000"/><rect y=".667" width="3" height=".666" fill="#DD0000"/><rect y="1.333" width="3" height=".667" fill="#FFCE00"/>',
    "nl": '<rect width="3" height=".667" fill="#AE1C28"/><rect y=".667" width="3" height=".666" fill="#fff"/><rect y="1.333" width="3" height=".667" fill="#21468B"/>',
    "ru": '<rect width="3" height=".667" fill="#fff"/><rect y=".667" width="3" height=".666" fill="#0039A6"/><rect y="1.333" width="3" height=".667" fill="#D52B1E"/>',
    "es": '<rect width="3" height="2" fill="#AA151B"/><rect y=".5" width="3" height="1" fill="#F1BF00"/>',
    "pl": '<rect width="3" height="1" fill="#fff"/><rect y="1" width="3" height="1" fill="#DC143C"/>',
    "pt": '<rect width="3" height="2" fill="#DA291C"/><rect width="1.2" height="2" fill="#046A38"/><circle cx="1.2" cy="1" r=".33" fill="#FFE900" stroke="#DA291C" stroke-width=".06"/>',
    "ja": '<rect width="3" height="2" fill="#fff"/><circle cx="1.5" cy="1" r=".6" fill="#BC002D"/>',
    "zh": '<rect width="3" height="2" fill="#EE1C25"/><path fill="#FFDE00" d="M.55 .3l.16.5.53 0-.43.31.16.5-.42-.31-.43.31.16-.5-.43-.31.53 0z"/>',
    "ar": '<rect width="3" height="2" fill="#165D31"/><rect x=".45" y=".8" width="2.1" height=".28" rx=".05" fill="#fff"/>',
    "hi": '<rect width="3" height=".667" fill="#FF9933"/><rect y=".667" width="3" height=".666" fill="#fff"/><rect y="1.333" width="3" height=".667" fill="#138808"/><circle cx="1.5" cy="1" r=".22" fill="none" stroke="#000080" stroke-width=".05"/>',
    #  A simplified Union Jack for English.
    "en": ('<rect width="3" height="2" fill="#012169"/>'
           '<path d="M0 0L3 2M3 0L0 2" stroke="#fff" stroke-width=".4"/>'
           '<path d="M0 0L3 2M3 0L0 2" stroke="#C8102E" stroke-width=".24"/>'
           '<path d="M1.5 0V2M0 1H3" stroke="#fff" stroke-width=".6"/>'
           '<path d="M1.5 0V2M0 1H3" stroke="#C8102E" stroke-width=".36"/>'),
}
_FLAG_FALLBACK = '<rect width="3" height="2" fill="#e5e7eb"/><path d="M1.5.5a.5.5 0 100 1 .5.5 0 000-1" fill="#94a3b8"/>'


def language_flag_svg(code):
    """A small inline SVG flag for a language, or a neutral globe-ish fallback.
    Our own markup -- rendered `| safe`."""
    body = _FLAG_BODY.get(code, _FLAG_FALLBACK)
    return ('<svg class="cms-ls-flag" viewBox="0 0 3 2" preserveAspectRatio="xMidYMid slice" '
            'aria-hidden="true" focusable="false">%s</svg>' % body)


DEFAULT_SOURCE = "en"
SOURCE_NAMES = {"en": ("English", "English")}
_ENABLED_KEY = "translation_langs"
_SOURCE_KEY = "site_language"

#  The ONLY section type whose `content` is not prose HTML but a structured
#  blob (JSON of cells) -- handled by iter_source_strings' own recursion, so
#  it must not be sent to the translator as if it were text.
_STRUCTURED_TYPE = "columns"
#  A marker class means "this is a dynamic tool": its stored content is a
#  placeholder resolved at render from live data (a menu's links, a blog's
#  posts), so translating the placeholder does nothing and its real labels
#  are translated on their own path. Everything else is prose and IS
#  translated, whatever its type -- so a new tool or design needs no change
#  here to be covered.
_MARKER_RE = re.compile(
    r'cms-(menu|breadcrumb|wordmark|version|file-tool|blog|search|contact-form|faq-reader|'
    r'lang-switcher|video-gallery|image-accordion|shop|buy-button|basket)\b')
_HAS_LETTERS = re.compile(r'[^\W\d_]', re.UNICODE)


# --- language helpers ------------------------------------------------------

def language_name(code, native=False):
    if code in SOURCE_NAMES:
        return SOURCE_NAMES[code][1 if native else 0]
    row = _BY_CODE.get(code)
    if not row:
        return code
    return row[2] if native else row[1]


def is_rtl(code):
    row = _BY_CODE.get(code)
    return bool(row and row[3])


def source_language(db):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_SOURCE_KEY,)).fetchone()
    return (row["value"] if row and row["value"] else DEFAULT_SOURCE)


def enabled_languages(db):
    """The target languages the owner has switched on, in the fixed order."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_ENABLED_KEY,)).fetchone()
    try:
        chosen = set(json.loads(row["value"])) if row and row["value"] else set()
    except (ValueError, TypeError):
        chosen = set()
    return [code for (code, _e, _n, _r) in LANGUAGES if code in chosen]


def set_enabled_languages(db, codes):
    keep = [code for (code, _e, _n, _r) in LANGUAGES if code in set(codes or [])]
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_ENABLED_KEY, json.dumps(keep)))
    db.commit()
    return keep


def available_languages(db):
    """Every offerable language with its enabled flag, for the settings UI."""
    on = set(enabled_languages(db))
    return [{"code": c, "name": e, "native": n, "rtl": r, "enabled": c in on}
            for (c, e, n, r) in LANGUAGES]


# --- the cache -------------------------------------------------------------

def _hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def cached(db, text, lang):
    """The stored translation of `text` into `lang`, or None."""
    if not text:
        return None
    row = db.execute(
        "SELECT translated FROM translations WHERE lang = ? AND source_hash = ?",
        (lang, _hash(text))).fetchone()
    return row["translated"] if row else None


def _store(db, text, lang, translated):
    db.execute(
        "INSERT INTO translations (lang, source_hash, source_text, translated) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(lang, source_hash) DO UPDATE SET translated = excluded.translated, "
        "source_text = excluded.source_text",
        (lang, _hash(text), text, translated))


def needs_translation(text):
    """Worth sending to a translator: has real words -- not just markup,
    numbers, symbols, or URLs. A URL/email is never prose (translating a
    link's visible text breaks it), so content whose only words are URLs is
    left alone."""
    if not text or not text.strip():
        return False
    stripped = re.sub(r"<[^>]+>", " ", text)
    if not _HAS_LETTERS.search(stripped):
        return False
    words = [w for w in stripped.split() if _HAS_LETTERS.search(w)]
    return any(not _is_urlish(w) for w in words)


def section_translatable(section_type, content):
    #  Prose in ANY section is translated, EXCEPT the Columns wrapper (its
    #  cells are handled by the recursion in iter_source_strings) and the
    #  dynamic marker tools (their content is a live-resolved placeholder).
    #  A denylist, not an allowlist, so a new tool or design is covered
    #  without a change here.
    return (section_type != _STRUCTURED_TYPE
            and needs_translation(content)
            and not _MARKER_RE.search(content or ""))


def _columns_cells(content):
    """The cells of a Columns section, or [] for anything else. A Columns
    section keeps its cells as JSON in `content` -- {"columns": [cell, ...]}
    -- so its prose does not live in the section row the way a Text or Card
    does; without reaching in here, everything a site puts in columns (which
    is most of it) is never translated."""
    try:
        data = json.loads(content) if content else None
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    cells = data.get("columns")
    return cells if isinstance(cells, list) else []


def _cell_source_strings(cell):
    """Every translatable string a Columns cell contributes. A cell is either
    a single tool ({type, content}) or a STACK of them ({type:"rows", rows:
    [...]}) -- the CV's Experience/Education entries are stacks, so without
    recursing into `rows` most of a two-column page is never collected."""
    if not isinstance(cell, dict):
        return
    if cell.get("type") == "rows":
        for sub in cell.get("rows") or []:
            for s in _cell_source_strings(sub):
                yield s
        return
    if section_translatable(cell.get("type"), cell.get("content")):
        yield cell["content"]


def _localize_cell(db, cell, lang):
    """A Columns cell with its stored translations swapped in (cache only).
    Recurses into a `rows` stack the same way the collector does. Returns
    (new_cell, changed)."""
    if not isinstance(cell, dict):
        return cell, False
    if cell.get("type") == "rows":
        new_rows, changed = [], False
        for sub in cell.get("rows") or []:
            ns, ch = _localize_cell(db, sub, lang)
            new_rows.append(ns)
            changed = changed or ch
        if not changed:
            return cell, False
        out = dict(cell)
        out["rows"] = new_rows
        return out, True
    if section_translatable(cell.get("type"), cell.get("content")):
        hit = cached(db, cell.get("content"), lang)
        if hit is not None:
            out = dict(cell)
            out["content"] = hit
            return out, True
    return cell, False


def iter_source_strings(section_type, content):
    """Every translatable source string a section contributes -- its own
    prose, or, for a Columns section, the prose inside each cell (stacked
    tools included). One place so the collector and the render agree on
    exactly what gets translated."""
    if section_type == "columns":
        for cell in _columns_cells(content):
            for s in _cell_source_strings(cell):
                yield s
        return
    if section_translatable(section_type, content):
        yield content


def localized_content(db, section_type, content, lang):
    """`content` with its prose swapped for the STORED translation into
    `lang` (cache only -- the render never calls a provider). A Columns
    section is rewritten cell by cell, stacked tools included. A miss keeps
    the original, so a half-translated site degrades to source, not blanks."""
    if section_type == "columns":
        cells = _columns_cells(content)
        if not cells:
            return content
        new_cells, changed = [], False
        for cell in cells:
            nc, ch = _localize_cell(db, cell, lang)
            new_cells.append(nc)
            changed = changed or ch
        if not changed:
            return content
        data = json.loads(content)
        data["columns"] = new_cells
        return json.dumps(data)
    if section_translatable(section_type, content):
        hit = cached(db, content, lang)
        if hit is not None:
            return hit
    return content


# --- talking to the provider ----------------------------------------------

class TranslationError(Exception):
    pass


#  The last thing the PROVIDER said, per thread.
#
#  A string's translation is several calls deep -- whole, then batched,
#  then one segment at a time -- and each layer swallows the layer below's
#  failure to try the next way. That is right for the RESULT (the worst
#  case is untranslated words, never a broken layout) and wrong for the
#  REASON: by the time _translate_via_ai gives up, the provider's "API key
#  not valid" or "model not found" has been thrown away three times and
#  what reaches the screen is "returned nothing for any part", which is
#  true and useless. So every provider failure is noted here as it
#  happens, and the outermost error carries the innermost message. Thread-
#  local because the background run and a request can translate at once.
_last = threading.local()


def _note_failure(msg):
    _last.error = (msg or "").strip() or None


def last_provider_error():
    return getattr(_last, "error", None)


#  A self-hosted model handed several KB of markup at once returns NOTHING
#  -- no error, an empty reply after a long pause (measured: fine to ~800
#  chars, empty by ~3000, on the model this install had). We still TRY the
#  whole string first, whatever its size, so anything the model can handle
#  comes back byte-for-byte unchanged; only a LARGE string that actually
#  fails is then split at element boundaries and retried piece by piece.
#  This is the size below which a failure is just a failure -- too small to
#  be worth splitting.
_CHUNK_LIMIT = 1500


def _translate_call(db, text, lang):
    """One provider call for a fragment small enough to come back whole.
    Returns the translated string or raises TranslationError."""
    from .. import assistant
    target = language_name(lang)
    prompt = (
        "Translate the following HTML fragment into %s.\n"
        "Rules:\n"
        "- Translate ONLY the human-readable text.\n"
        "- Keep every HTML tag, attribute, URL, class and data-* value EXACTLY as-is.\n"
        "- Do not add, remove or reorder any markup.\n"
        "- Return ONLY the translated fragment, with no explanation and no code fence.\n\n"
        "%s" % (target, text))
    try:
        result = assistant._call_provider(
            db, [{"role": "user", "content": prompt}], [],
            want_json=False, timeout=getattr(assistant, "GENERATE_TIMEOUT", 240))
    except Exception as e:  # ProviderError and anything the wire throws
        _note_failure(str(e))
        raise TranslationError(str(e))
    out = (result.get("content") if result else "") or ""
    out = re.sub(r"^```(?:html)?", "", out.strip()).strip()
    out = re.sub(r"```$", "", out).strip()
    if not out:
        _note_failure("The AI provider returned nothing.")
        raise TranslationError("The AI provider returned nothing.")
    return out


_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][\w-]*)")


def _tags_preserved(src, out):
    """Did the translation keep exactly the tags the source had? Compared as a
    multiset of tag names -- a model that dropped a <p> or an <li> (taking its
    text with it, the 'a whole section became one word' bug) fails this, and
    we fall back to translating text nodes instead of trusting the mangled
    whole."""
    return sorted(_TAG_RE.findall(src or "")) == sorted(_TAG_RE.findall(out or ""))


#  Every URL/email in a fragment -- in the text AND in href/src attributes --
#  so the whole-string fast path can be rejected if the model altered one.
_URL_FIND = re.compile(
    r"https?://[^\s\"'<>]+|mailto:[^\s\"'<>]+|\b[\w.-]+\.[a-z]{2,}(?:/[^\s\"'<>]*)?",
    re.IGNORECASE)


def _urls_preserved(src, out):
    """Every URL the source had still appears verbatim in the output. The
    fast path hands the model whole markup and asks it to keep URLs as-is;
    when it doesn't (a translated link, a mangled domain), this catches it
    and the per-node path -- which never sends a URL at all -- takes over."""
    src_urls = set(_URL_FIND.findall(src or ""))
    if not src_urls:
        return True
    out_urls = set(_URL_FIND.findall(out or ""))
    return src_urls <= out_urls


_NUM_LINE_RE = re.compile(r"^\s*(\d+)\s*[.)\]:-]\s*(.*)$")

#  A bare URL, email or domain/path is not prose -- translating it changes
#  the visible link text ("…/contact" -> "…/contacto") and breaks it. A URL
#  sitting inside a sentence (which has spaces) is left to the sentence.
_URLISH_RE = re.compile(
    r"^(?:https?://|mailto:|www\.)"           # a scheme or www.
    r"|^\S+@\S+\.\S+$"                          # an email
    r"|^[\w.-]+\.[a-z]{2,}(?:/\S*)?$",         # domain.tld, optionally /path
    re.IGNORECASE)


def _is_urlish(s):
    s = (s or "").strip()
    return bool(s) and " " not in s and "\t" not in s and bool(_URLISH_RE.search(s))


def _translate_batch(db, segments, lang):
    """Translate several short text segments in ONE call, as a numbered list.
    The model never sees a tag -- these are plain strings pulled out of the
    markup -- so it cannot drop or mangle structure, and one call does the
    work of many (a slow self-hosted model's cost is per-call). Returns a list
    the same length as `segments`; None for any line the reply did not return,
    so the caller can retry just those. Raises only if the call itself fails."""
    from .. import assistant
    target = language_name(lang)
    numbered = "\n".join("%d. %s" % (i + 1, re.sub(r"\s+", " ", s).strip())
                         for i, s in enumerate(segments))
    prompt = (
        "Translate each numbered line below into %s.\n"
        "Rules:\n"
        "- Reply with the SAME numbers, one translation per line, in the same order.\n"
        "- Translate the visible text only; never drop, merge, split or renumber a line.\n"
        "- Reply with ONLY the numbered list, no preamble and no code fence.\n\n"
        "%s" % (target, numbered))
    try:
        result = assistant._call_provider(
            db, [{"role": "user", "content": prompt}], [],
            want_json=False, timeout=getattr(assistant, "GENERATE_TIMEOUT", 240))
    except Exception as e:  # ProviderError and anything the wire throws
        _note_failure(str(e))
        raise TranslationError(str(e))
    out = (result.get("content") if result else "") or ""
    if not out.strip():
        _note_failure("The AI provider returned nothing.")
        raise TranslationError("The AI provider returned nothing.")
    by_num = {}
    for line in out.splitlines():
        m = _NUM_LINE_RE.match(line)
        if m:
            by_num[int(m.group(1))] = m.group(2).strip()
    return [by_num.get(i + 1) or None for i in range(len(segments))]


def _translate_texts(db, segments, lang):
    """Translate a list of short text segments in as FEW provider calls as
    possible: grouped into batches under the size the model answers reliably,
    each batch one call. A batch whose reply does not line up (wrong count, a
    missing number) has just its missing items retried one at a time, so the
    fast path is used when it works and nothing is silently dropped when it
    does not. Returns a list the same length as `segments`; None where a
    segment could not be got (the caller keeps its source)."""
    out = [None] * len(segments)
    i, n = 0, len(segments)
    while i < n:
        idx = [i]
        size = len(segments[i])
        i += 1
        while i < n and len(idx) < 25 and size + len(segments[i]) <= _CHUNK_LIMIT:
            idx.append(i)
            size += len(segments[i])
            i += 1
        segs = [segments[j] for j in idx]
        try:
            res = _translate_batch(db, segs, lang)
        except TranslationError:
            res = [None] * len(segs)
        for j, tr in zip(idx, res):
            if tr:
                out[j] = tr
            else:
                try:  # the batch missed this one -- get it on its own
                    out[j] = _translate_call(db, segments[j], lang)
                except TranslationError:
                    out[j] = None
    return out


def _translate_via_ai(db, text, lang):
    """Cached-miss translation of one string, with its HTML preserved EXACTLY.

    Small content is tried whole first: if the model returns it with every tag
    still present, that is used unchanged (byte-clean). Everything else is
    translated by pulling the visible TEXT out of the markup, translating it in
    a few batched calls, and writing it back into the untouched tags. The model
    never sees a tag that way, so it cannot drop, reorder or invent one; the
    work is a handful of calls, not one per word; and any segment that fails
    keeps its source, so the worst case is some untranslated words, never
    missing text or a broken layout. Only an all-empty result raises -- and
    it raises with the PROVIDER's last words, not this function's."""
    text = text or ""
    _note_failure(None)
    if len(text) <= _CHUNK_LIMIT:
        try:
            whole = _translate_call(db, text, lang)
            if _tags_preserved(text, whole) and _urls_preserved(text, whole):
                return whole
        except TranslationError:
            pass  # fall through to the batched text path, which may still get it
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(text, "html.parser")
    nodes, segs = [], []
    for node in list(soup.find_all(string=True)):
        s = str(node)
        if not s.strip() or not _HAS_LETTERS.search(s):
            continue  # whitespace or markup-only, nothing to translate
        if _is_urlish(s):
            continue  # a bare URL/email/domain -- translating it breaks it
        if node.parent is not None and node.parent.name in ("script", "style", "code"):
            continue
        nodes.append(node)
        segs.append(s.strip())
    if not nodes:
        raise TranslationError("Nothing translatable in the fragment.")
    results = _translate_texts(db, segs, lang)
    any_ok = False
    for node, tr in zip(nodes, results):
        if not tr:
            continue  # keep this node's source text
        s = str(node)
        lead = s[:len(s) - len(s.lstrip())]
        trail = s[len(s.rstrip()):]
        node.replace_with(NavigableString(lead + tr + trail))
        any_ok = True
    if not any_ok:
        raise TranslationError(last_provider_error()
                               or "The AI provider returned nothing for any part.")
    return str(soup)


def translate_string(db, text, lang, use_ai=True):
    """Cached translation of one string, translating and storing it on a miss.
    On any provider failure returns None (the render falls back to source)."""
    if not needs_translation(text):
        return text
    hit = cached(db, text, lang)
    if hit is not None:
        return hit
    if not use_ai:
        return None
    try:
        out = _translate_via_ai(db, text, lang)
    except TranslationError:
        return None
    _store(db, text, lang, out)
    db.commit()
    return out


# --- collecting what a site needs translated -------------------------------

def _site_strings(db):
    """Every distinct source string on the public site worth translating:
    public pages' titles and their sections' content, PLUS the active
    template's shared zone sections (footer/sidebar) -- those hang off the
    template by zone, not off a page, so a page-only scan never saw the
    footer and it stayed in the source language."""
    seen, strings = set(), []

    def add(text):
        if needs_translation(text) and text not in seen:
            seen.add(text)
            strings.append(text)

    def add_sections(rows):
        for s in rows:
            for text in iter_source_strings(s["type"], s["content"]):
                add(text)

    pages = db.execute(
        "SELECT id, title FROM pages WHERE is_public = 1").fetchall()
    for p in pages:
        add(p["title"])
        add_sections(db.execute(
            "SELECT type, content FROM sections WHERE page_id = ?", (p["id"],)).fetchall())

    #  The header/footer/sidebars — scoped by template_id + zone, page_id NULL.
    tpl = (db.execute("SELECT id FROM templates WHERE is_active = 1").fetchone()
           or db.execute("SELECT id FROM templates LIMIT 1").fetchone())
    if tpl:
        add_sections(db.execute(
            "SELECT type, content FROM sections "
            "WHERE template_id = ? AND zone IN ('header','footer','sidebar','sidebar_right')",
            (tpl["id"],)).fetchall())
    return strings


def translation_status(db):
    """How much of the site is translated into each enabled language: total
    strings, how many are cached, and whether the language is complete. Reads
    only -- costs no provider call, so the Translate screen can always show it."""
    langs = enabled_languages(db)
    total = len(_site_strings(db))
    out = []
    for lang in langs:
        done = 0
        for text in _site_strings(db):
            if cached(db, text, lang) is not None:
                done += 1
        out.append({"code": lang, "name": language_name(lang),
                    "native": language_name(lang, native=True),
                    "done": done, "total": total,
                    "complete": total > 0 and done == total})
    return {"total": total, "languages": out}


def translate_site(db, langs=None, progress=None, should_stop=None):
    """Translate every public string into each enabled (or given) language,
    skipping anything already cached. Returns per-language counts. A provider
    failure on one string is recorded and the run continues -- a half-done
    language is visible as half-done, better than an all-or-nothing failure
    that leaves the owner nothing. `should_stop()` is checked between strings
    so a Cancel takes effect promptly (a slow call cannot be cut mid-flight);
    a cancelled run returns what it finished, marked."""
    langs = [c for c in (langs or enabled_languages(db))
             if c in _BY_CODE]
    strings = _site_strings(db)
    summary = {"total": len(strings), "languages": {}}
    for lang in langs:
        made, failed, skipped, last_error = 0, 0, 0, None

        def counts():
            return {"made": made, "failed": failed, "skipped": skipped,
                    "last_error": last_error}

        for text in strings:
            if should_stop and should_stop():
                summary["languages"][lang] = counts()
                summary["cancelled"] = True
                return summary
            if cached(db, text, lang) is not None:
                skipped += 1
                continue
            try:
                out = _translate_via_ai(db, text, lang)
            except TranslationError as e:
                #  Counted AND remembered: a run that fails thirteen times
                #  with the reason dropped each time reads as "Paused at
                #  0 / 13" and nothing else -- see the Languages screen.
                failed += 1
                last_error = str(e)[:300] or last_error
            else:
                _store(db, text, lang, out)
                db.commit()
                made += 1
            if progress:
                #  On a failure too: a run that only reports successes
                #  never heartbeats while everything is failing.
                progress(lang, made, failed, skipped, len(strings), last_error)
        summary["languages"][lang] = counts()
    return summary


def clear_translations(db, lang=None):
    """Drop stored translations -- one language, or all. Used when the owner
    turns a language off, and by a full re-translate."""
    if lang:
        db.execute("DELETE FROM translations WHERE lang = ?", (lang,))
    else:
        db.execute("DELETE FROM translations")
    db.commit()


# --- the background run --------------------------------------------------
#  A whole-site translate is minutes of slow provider calls -- too long to
#  hold a request open, and driving it from the browser meant a refresh
#  killed it and the progress was a guess. So it runs in a SERVER thread and
#  its state lives in one settings row; the screen just POLLS. Progress is
#  read from the CACHE (translation_status), which is the true count, not
#  from anything the run reports about itself. "active" is this row AND a
#  recent heartbeat, so a worker that died mid-run doesn't look busy forever.
_RUN_KEY = "translation_run"
RUN_STALE_SECONDS = 600


def run_state(db):
    """The background run's state: {active, started, heartbeat, langs, error}.
    `active` is downgraded to False if the heartbeat has gone quiet, so a
    crashed run frees the next one instead of blocking it."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_RUN_KEY,)).fetchone()
    try:
        st = json.loads(row["value"]) if row and row["value"] else {}
    except (ValueError, TypeError):
        st = {}
    if st.get("active") and (time.time() - float(st.get("heartbeat") or 0)) > RUN_STALE_SECONDS:
        st = dict(st, active=False)
    return st


def _write_run_state(db, st):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_RUN_KEY, json.dumps(st)))
    db.commit()


def claim_translation_run(db, langs):
    """Start a run if none is going (a stale one counts as none). Returns True
    when the caller should spawn the worker, False if one is already running."""
    if run_state(db).get("active"):
        return False
    now = time.time()
    _write_run_state(db, {"active": True, "started": now, "heartbeat": now,
                          "langs": list(langs), "error": None, "languages": {}})
    return True


def run_heartbeat(db):
    st = run_state(db)
    if st.get("active"):
        st["heartbeat"] = time.time()
        _write_run_state(db, st)


def note_progress(db, lang, made, failed, skipped, total, last_error=None):
    """What translate_site reports after every string, written into the run
    state: the counts for that language and the LAST reason a string failed.
    The counts the screen shows still come from the cache (the true number);
    this is where the reason lives, because the cache cannot say why a
    string is not in it. Also the heartbeat."""
    st = run_state(db)
    if not st.get("active"):
        return
    st["heartbeat"] = time.time()
    langs = st.setdefault("languages", {})
    langs[lang] = {"made": made, "failed": failed, "skipped": skipped,
                   "total": total, "last_error": last_error}
    _write_run_state(db, st)


def request_cancel(db):
    """Ask a running translation to stop. It takes effect after the current
    item (a slow model call cannot be interrupted mid-flight), so the worker
    checks this between strings and exits cleanly. Returns True if there was a
    run to cancel."""
    st = run_state(db)
    if not st.get("active"):
        return False
    st["cancel"] = True
    _write_run_state(db, st)
    return True


def cancel_requested(db):
    return bool(run_state(db).get("cancel"))


def finish_run(db, error=None):
    st = run_state(db)
    st["active"] = False
    st["error"] = error
    st["heartbeat"] = time.time()
    _write_run_state(db, st)


def reset_stuck_run(db):
    """Called at boot. The worker is a thread in a web process and never
    survives a restart, so ANY run still flagged active belongs to a thread
    that no longer exists -- clear it, or the screen shows a phantom
    'translating…' until the stale window elapses and no new run can start.
    Reads the raw row (not run_state) so a recent heartbeat can't keep a dead
    run looking alive."""
    row = db.execute("SELECT value FROM settings WHERE key = ?", (_RUN_KEY,)).fetchone()
    try:
        st = json.loads(row["value"]) if row and row["value"] else {}
    except (ValueError, TypeError):
        st = {}
    if st.get("active"):
        st["active"] = False
        st["error"] = "Interrupted by a server restart — press Translate to continue."
        _write_run_state(db, st)


# --- which language a visitor gets -----------------------------------------

_COOKIE = "cms_lang"


def _parse_accept_language(header):
    """Ordered list of language codes (primary subtag) from an Accept-Language
    header, best first."""
    out = []
    for part in (header or "").split(","):
        part = part.strip()
        if not part:
            continue
        code = part.split(";")[0].strip().lower()
        primary = code.split("-")[0]
        if primary and primary not in out:
            out.append(primary)
    return out


def active_language(db, request):
    """The language to render for this request. An explicit ?lang wins and is
    what the switcher sets; else the visitor's saved choice (cookie); else the
    best match from the browser's Accept-Language among the enabled set; else
    the source language. Only ever returns the source or an ENABLED target."""
    src = source_language(db)
    enabled = enabled_languages(db)
    if not enabled:
        return src
    allowed = set(enabled) | {src}
    q = (request.args.get("lang") or "").lower()
    if q in allowed:
        return q
    if q == src:
        return src
    ck = (request.cookies.get(_COOKIE) or "").lower()
    if ck in allowed:
        return ck
    for code in _parse_accept_language(request.headers.get("Accept-Language")):
        if code in allowed:
            return code
    return src


def cookie_name():
    return _COOKIE
