"""Words out of a file somebody uploaded, and nothing else.

WHAT THIS IS FOR. The theme generator can take content the owner
already has and lay a site out from it -- but a CV is almost never
typed, it is a file. Asking somebody to open their CV, select all and
paste is three seconds of work and one more reason not to bother.

WHAT IT DELIBERATELY IS NOT. It reads plain text and .docx, and it adds
no dependency to do it: a .docx is a zip holding XML, which the standard
Anything else is refused by name. The list of things somebody
might try is endless and naming one of them teaches nothing; naming
what IS read is the whole of the rule. (A PDF needs a real parser in
the image, which is a decision for whoever runs this app rather than a
thing to slip in -- but that is a reason for the code to know, not a
sentence for the screen.)

A .docx is an ARCHIVE, so it gets the treatment every archive gets in
this codebase (see packages.safe_extract_zip and CLAUDE.md's "Security
is not optional"): nothing is written to disk, one named member is read
and no other, and the size is capped BEFORE decompressing rather than
discovered afterwards -- a few hundred kilobytes of zip can be gigabytes
of XML, and "the request body was small" is not a bound on that.
"""
import html
import io
import re
import zipfile

#  What a document may weigh, before and after.
#
#  Both, because either alone is a hole: a small upload can decompress
#  to gigabytes, and a large upload that happens to decompress to little
#  is still a large upload. Generous enough for any real document -- a
#  200-page thesis is well under a megabyte of text.
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024

#  The one member of a .docx that holds the writing. Headers, footers,
#  footnotes, comments and tracked changes live in other parts and are
#  NOT read: a CV's header is a page number, and a comment is somebody's
#  private note about the document rather than part of it.
DOCX_BODY = "word/document.xml"

READS = (".txt", ".md", ".markdown", ".text", ".docx", ".pdf")


class DocumentError(Exception):
    """Said to the owner, in their terms."""


def _plain_text(raw):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError("That file is not text this app can read.")


#  A bullet drawn in a symbol font (Wingdings, Symbol) arrives as its
#  code point, not as text -- often the replacement char once decoded --
#  and several bullets can land on one line with no break between them.
#  Turned into real "- " line starts so a list reads as a list.
_SYMBOL_BULLETS = "•�▪●‣⁃∙"


def _clean_runs(text):
    """Symbol bullets to line-started dashes, and the tidy-up every path
    shares. Applied once, at the end, so box text and body text agree."""
    text = html.unescape(text)
    text = re.sub(r"[" + _SYMBOL_BULLETS + r"]\s*", chr(10) + "- ", text)
    #  A phone number and an email that share a line get their own lines.
    #  A contact block reads one item per line, and a document that put a
    #  phone and an email in the same paragraph -- some do, inconsistently
    #  -- otherwise arrives with them run together. Only after a digit, so
    #  ordinary prose ("email me at a@b.com") is left alone.
    text = re.sub(r"(\d)[ \t]+([^\s@]+@[^\s@]+\.[A-Za-z]{2,})",
                  r"\1" + chr(10) + r"\2", text)
    lines = [ln.strip() for ln in text.split(chr(10))]
    out = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return chr(10).join(out).strip()


def _plain_from_box(inner):
    """The text of one text box: paragraph breaks kept, tags gone."""
    inner = re.sub(r"</w:p>", chr(10), inner)
    inner = re.sub(r"<w:br[^>]*/?>", chr(10), inner)
    inner = re.sub(r"<w:tab[^>]*/?>", " ", inner)
    return re.sub(r"<[^>]+>", "", inner).strip()


def _docx_textboxes(xml):
    """Every floating text box in a .docx, as (top, left, text) in points.

    A CV built from a template is often not a run of paragraphs at all --
    it is dozens of positioned text boxes, one per section, and Word
    stores them in no particular order. Read straight down the XML the
    headings land AFTER their own content and the page is scrambled: that
    is the "basic data" a designed CV came back as.

    Each box carries where it sits. Word writes boxes two ways -- VML
    (`v:shape` with a `style` in points) and DrawingML (`wp:anchor` with
    `posOffset` in EMU) -- and often BOTH for one box, so they are read
    together and de-duplicated by text and rough position. Their
    coordinates are what `_order_columns` needs to put the reading order
    back.
    """
    boxes, seen = [], set()

    def add(top, left, inner):
        txt = _plain_from_box(inner)
        if not txt:
            return
        key = (None if top is None else round(top / 6.0),
               None if left is None else round(left / 6.0), txt[:24])
        if key in seen:
            return
        seen.add(key)
        boxes.append((top if top is not None else 1e9,
                      left if left is not None else 0.0, txt))

    #  VML: position is in the shape's style, in points.
    for m in re.finditer(
            r'<v:shape\b[^>]*\bstyle="([^"]*)"[^>]*>(.*?)</v:shape>', xml, re.S):
        style, body = m.group(1), m.group(2)
        tb = re.search(r"<v:textbox\b[^>]*>(.*?)</v:textbox>", body, re.S)
        if not tb:
            continue

        def pt(key, s=style):
            mm = re.search(key + r":\s*(-?[\d.]+)pt", s)
            return float(mm.group(1)) if mm else None
        top = pt("top")
        if top is None:
            top = pt("margin-top")
        left = pt("margin-left")
        if left is None:
            left = pt("left")
        add(top, left, tb.group(1))

    #  DrawingML: position is in EMU (12700 per point) on the anchor.
    for m in re.finditer(r"<wp:anchor\b(.*?)</wp:anchor>", xml, re.S):
        block = m.group(1)
        tb = re.search(r"<w:txbxContent>(.*?)</w:txbxContent>", block, re.S)
        if not tb:
            continue
        offs = re.findall(r"<wp:posOffset>(-?\d+)</wp:posOffset>", block)
        top = int(offs[1]) / 12700.0 if len(offs) > 1 else None
        left = int(offs[0]) / 12700.0 if offs else None
        add(top, left, tb.group(1))
    return boxes


def _order_columns(boxes):
    """Positioned boxes read back in human order: columns left to right,
    top to bottom within each -- so a heading returns above its section
    and a sidebar reads as a column, not one row at a time."""
    if not boxes:
        return ""
    lefts = sorted({round(b[1]) for b in boxes})
    cols = []
    for x in lefts:
        if cols and x - cols[-1][-1] <= 60:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols]

    def col_of(x):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))
    ordered = sorted(boxes, key=lambda b: (col_of(b[1]), b[0]))
    return chr(10).join(b[2] for b in ordered)


def _docx_bands(boxes):
    """A box-built page split into vertical BANDS, each a list of columns.

    A designed document is not one grid: it is usually two columns for
    most of its height and then a row that is three (a CV's references),
    or a full-width strip across the top. So the page is read as a stack
    of bands, and each band has its OWN column count -- which is what lets
    the finished page reflect the format it was given rather than forcing
    one column count on all of it.

    Columns are found by LEFT EDGE (a masonry has no clean whitespace gap
    to cut on, but every box's left edge still votes for its column). A
    band boundary is where a column that does not run the full height
    STARTS -- the moment a third column appears is the moment the layout
    changed. Everything below that is one wide band, so a three-column
    references row comes back as one three-column band, not fragments.

    Returns a list of bands, each a list of columns (left to right), each
    column a list of (top, left, text) boxes -- or None when the document
    is a single column (then the ordinary one-column path renders it).
    """
    boxes = [b for b in boxes if b[0] < 1e8]
    if len(boxes) < 6:
        return None
    lefts = sorted(b[1] for b in boxes)
    groups = []
    for x in lefts:
        if groups and x - groups[-1][-1] <= 70:
            groups[-1].append(x)
        else:
            groups.append([x])
    centers = [sum(g) / len(g) for g in groups]
    if len(centers) < 2:
        return None

    def col_of(x):
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))
    tops = [b[0] for b in boxes]
    height = (max(tops) - min(tops)) or 1.0
    extent = {}
    for b in boxes:
        c = col_of(b[1])
        lo, hi = extent.get(c, (b[0], b[0]))
        extent[c] = (min(lo, b[0]), max(hi, b[0]))
    #  A column that runs most of the height is a MAIN column; one that
    #  lives in a small vertical range is LOCAL to a band, and where it
    #  begins is a band boundary.
    local = [c for c in extent if (extent[c][1] - extent[c][0]) < 0.5 * height]
    bounds = sorted({min(tops)} | {extent[c][0] for c in local})
    bounds.append(max(tops) + 1)

    def band_of(top):
        for i in range(len(bounds) - 1):
            if bounds[i] <= top < bounds[i + 1]:
                return i
        return 0
    grouped = {}
    for b in boxes:
        grouped.setdefault(band_of(b[0]), []).append(b)
    bands = []
    for bi in sorted(grouped):
        here = grouped[bi]
        cols = []
        for c in sorted(set(col_of(b[1]) for b in here)):
            cols.append(sorted((b for b in here if col_of(b[1]) == c),
                               key=lambda b: b[0]))
        bands.append(cols)
    return bands


def _fragments_to_lines(frags):
    """Word-level fragments (a browser gives text run by run) grouped back
    into lines: same top is one line, joined left to right. Adjacent runs
    with no gap between them are joined WITHOUT a space -- docx-preview
    sometimes splits a word ("s" + "tevenson"), and a gap of real width is
    what tells a break from a split."""
    frags = sorted(frags, key=lambda f: (f["top"], f["left"]))
    lines, cur, cur_top = [], [], None
    for f in frags:
        if cur and abs(f["top"] - cur_top) <= 6:
            cur.append(f)
        else:
            if cur:
                lines.append(_join_run(cur))
            cur, cur_top = [f], f["top"]
    if cur:
        lines.append(_join_run(cur))
    return lines


def _join_run(frags):
    frags = sorted(frags, key=lambda f: f["left"])
    out = frags[0]["text"]
    prev = frags[0]
    for f in frags[1:]:
        gap = f["left"] - (prev["left"] + prev.get("width", 0))
        t = f["text"] or ""
        head = t[:1]
        if gap < 4 and head and (head.islower() or head.isdigit()):
            #  A genuine mid-word split -- docx-preview breaks a word and
            #  the tail is lower-case or a digit ("s"+"tevenson",
            #  "B"+"est", "60"+"neil"). Join with no space.
            out += t
        elif head in ",.;:)]%":
            #  Punctuation hugs the word before it, whatever the gap.
            out += t
        else:
            #  Two real words -- an upper-case start, or a measured gap.
            #  A space, even when the runs happen to touch ("IT"+"EXPERT",
            #  "Work"+"Experience"), which read wrong fused together.
            out += " " + t
        prev = f
    return out


def layout_from_boxes(boxes):
    """The document's LAYOUT as bands of columns, from box positions a
    BROWSER resolved (see the theme generator's docx render). The .docx's
    own coordinates are anchored to the text flow and cannot be compared;
    a browser lays the document out and reports where each run actually
    sits, which is what makes the reading order correct. Those runs are
    grouped into lines, then the same left-edge column clustering and
    band detection the file path uses (_docx_bands) turns them into a
    two-column body, a three-column references row, and so on.
    """
    frags = [{"top": float(b.get("top", 0)), "left": float(b.get("left", 0)),
              "width": float(b.get("width", 0)), "text": str(b.get("text", "")).strip()}
             for b in (boxes or []) if str(b.get("text", "")).strip()]
    if len(frags) < 6:
        return None
    #  Band/column structure from the fragments' positions (as tuples the
    #  shared _docx_bands understands), then each band's each column has
    #  its own fragments grouped back into lines.
    tuples = [(f["top"], f["left"], i) for i, f in enumerate(frags)]
    bands = _docx_bands(tuples)
    if not bands:
        return None
    out, multi = [], False
    for band in bands:
        cols = []
        for col in band:
            col_frags = [frags[i] for (_t, _l, i) in col]
            cols.append(_clean_runs(chr(10).join(_fragments_to_lines(col_frags))))
        cols = [c for c in cols if c.strip()]
        if not cols:
            continue
        out.append({"columns": cols})
        if len(cols) >= 2:
            multi = True
    return {"bands": out} if (multi and out) else None


def columns_from(filename, raw):
    """A .docx's LAYOUT as bands of columns, or None when it has none.

    The document's own layout, so the page can reflect it (see the
    generator's column path and _docx_bands). Only a box-built document
    has columns to find; a plain run of paragraphs, a single-column
    design, and every non-.docx return None and take the ordinary
    one-column path. General: the column count is whatever the document
    uses per band -- two down the body, three across the references row --
    not a fixed number.
    """
    if not (filename or "").lower().endswith(".docx"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read(DOCX_BODY).decode("utf-8", "replace")
    except Exception:
        return None
    bands = _docx_bands(_docx_textboxes(xml))
    if not bands:
        return None
    out, multi = [], False
    for band in bands:
        cols = [_clean_runs(chr(10).join(b[2] for b in col)) for col in band]
        cols = [c for c in cols if c.strip()]
        if not cols:
            continue
        out.append({"columns": cols})
        if len(cols) >= 2:
            multi = True
    #  Worth a column layout only if some band is actually more than one
    #  column; otherwise it is a single-column document after all.
    return {"bands": out} if (multi and out) else None


def _docx_text(raw):
    """The words of a .docx, in reading order.

    Two shapes, because a CV is written as one of two very different
    things. Most are a run of PARAGRAPHS (the branch below), where the
    line breaks are most of what the structure is. A designed template is
    instead dozens of floating TEXT BOXES; those are read by
    _docx_textboxes and put back in order by _order_columns. Whichever
    holds more of the writing wins, so a plain CV is untouched and a
    boxed one stops arriving scrambled.

    Done on the XML with regexes rather than a parser: the shapes matched
    are a few fixed tags, an XML parser brings entity-expansion questions
    of its own, and everything here is bounded by MAX_TEXT_BYTES.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError):
        raise DocumentError("That .docx could not be opened. If it came from "
                            "another program, try saving it as Word or plain "
                            "text first.")
    with archive:
        try:
            entry = archive.getinfo(DOCX_BODY)
        except KeyError:
            raise DocumentError("That .docx has no document body in it, which "
                                "usually means it is a template or was not "
                                "finished saving.")
        #  DECLARED size first: refusing before decompressing is the
        #  whole point. A zip's header can lie, so the read below is
        #  bounded as well -- one check is a policy, two is a bound.
        if entry.file_size > MAX_TEXT_BYTES:
            raise DocumentError("That document is too big to read. Paste the "
                                "part you want instead.")
        with archive.open(entry) as member:
            xml = member.read(MAX_TEXT_BYTES + 1)
    if len(xml) > MAX_TEXT_BYTES:
        raise DocumentError("That document is too big to read. Paste the part "
                            "you want instead.")
    xml = xml.decode("utf-8", "replace")

    #  The text boxes, read and ordered by where they sit on the page.
    boxes = _docx_textboxes(xml)
    box_text = _order_columns(boxes)

    #  The BODY paragraphs -- everything that is not inside a text box.
    #  The text boxes' own content is read above, so it is removed here,
    #  by its INNERMOST wrappers (`v:textbox`, `w:txbxContent`) rather
    #  than by `w:pict`/`w:drawing`: a template's boxes are not always
    #  wrapped in those, and when they are not, leaving the box text in
    #  the body made the body look bigger than the ordered boxes -- so
    #  the scrambled document-order body won the test below by a hair,
    #  and every fix above did nothing. Removing the boxes' own numbers
    #  (their position offsets) here is also what stops
    #  "41967154311015Master's degree".
    body_xml = re.sub(r"<v:textbox\b.*?</v:textbox>", " ", xml, flags=re.S)
    body_xml = re.sub(r"<w:txbxContent>.*?</w:txbxContent>", " ", body_xml, flags=re.S)
    body_xml = re.sub(r"<w:drawing>.*?</w:drawing>", " ", body_xml, flags=re.S)
    body_xml = re.sub(r"<w:pict>.*?</w:pict>", " ", body_xml, flags=re.S)
    #  A table cell ends with a tab and a row with a newline, so a
    #  table reads as its rows rather than every cell run into one line
    #  -- a CV laid out as a two-column table (dates | roles) keeps that
    #  shape. The rest are paragraph, line and tab breaks; every other
    #  tag goes.
    body_xml = re.sub(r"</w:tc>", chr(9), body_xml)
    body_xml = re.sub(r"</w:tr>", chr(10), body_xml)
    body_xml = re.sub(r"</w:p>", chr(10), body_xml)
    body_xml = re.sub(r"<w:br[^>]*/?>", chr(10), body_xml)
    body_xml = re.sub(r"<w:tab[^>]*/?>", chr(9), body_xml)
    body_text = re.sub(r"<[^>]+>", "", body_xml)

    #  Whichever holds more of the writing is the document; the other is
    #  its decoration. A boxed template's body is nearly empty, a plain
    #  CV has no boxes -- so this leaves a normal document exactly as it
    #  was and only re-orders the ones that are actually built from boxes.
    #  html.unescape (inside _clean_runs) rather than hand-written pairs:
    #  Word writes numeric references for anything typographic -- an em
    #  dash arrives as &#8212; -- and the one right list of these is in
    #  the standard library.
    if len(box_text) > len(body_text.strip()):
        text = box_text
        if body_text.strip():
            text = text + chr(10) + chr(10) + body_text
    else:
        text = body_text
    return _clean_runs(text)


def _split_columns(page_text):
    """A two-column page read as two columns, not one scrambled line.

    A designed CV puts a sidebar (contact, skills, languages) beside the
    main column (profile, experience, education). Layout-mode extraction
    keeps them where they sit, so the two columns land on the SAME line
    separated by a wide run of spaces -- "SKILLS            Senior
    Landscape Architect" -- and a heading on one side is glued to a
    sentence on the other. Read straight, that is the "basic data"
    failure: the section titles are buried mid-line where nothing finds
    them.

    The gutter is the column where the right side consistently begins,
    after a wide gap, on enough lines to be a real column and not one
    stray tab. Found by the median of those right-edge starts. When one
    exists, the page is cut there and read left column first, then
    right -- so every heading returns to the start of its own line.
    Single-column pages have no such gutter and pass through untouched.
    """
    lines = page_text.split(chr(10))
    starts = []
    for ln in lines:
        m = re.search(r"\S\s{4,}(\S)", ln)
        if m:
            starts.append(m.start(1))
    if len(starts) < 3:
        return page_text
    starts.sort()
    gutter = starts[len(starts) // 2]
    if gutter < 12:
        return page_text
    #  The gutter has to be a real, repeated column -- half the gaps
    #  landing within a few characters of it -- or a document with one
    #  wide indent would be torn into columns that are not there.
    near = [x for x in starts if abs(x - gutter) <= 8]
    if len(near) < 3 or len(near) * 2 < len(starts):
        return page_text
    substantial = [ln for ln in lines if len(ln.strip()) > 1]
    if not substantial:
        return page_text
    #  A SIDEBAR IS A COLUMN, NOT A MARGIN. The tell that separates a real
    #  two-column layout from a single column with dates set hard right
    #  ("Lead Designer            2017-2021") is how much lives to the
    #  right of the gutter: a sidebar is many lines of contact, skills and
    #  languages; a right-aligned date is three short fragments clinging
    #  to the edge. Split only when the right side is a substantial column
    #  AND enough rows genuinely straddle the gutter -- otherwise a very
    #  common single-column CV gets torn away from its own dates.
    right_lines = [ln for ln in lines if len(ln[gutter:].strip()) >= 2]
    straddle = sum(1 for ln in lines
                   if ln[:gutter].strip() and ln[gutter:].strip())
    if len(right_lines) < max(6, int(0.30 * len(substantial))):
        return page_text
    if straddle * 3 < len(substantial):
        return page_text

    #  Cut each line at ITS OWN gap, not at a fixed column. Layout mode
    #  sets each line's text where it actually sits, so the right column
    #  begins a character or two either side of the gutter from line to
    #  line -- and a fixed cut sliced "PROFILE" into "PROF" + "ILE". The
    #  split point is the whitespace run nearest the gutter, so a word is
    #  never broken; a line with no such gap belongs wholly to the side
    #  its text starts on.
    left, right = [], []
    for ln in lines:
        if not ln.strip():
            continue
        gaps = [(m.start(), m.end()) for m in re.finditer(r"\s{3,}", ln)
                if m.start() > 0 and m.end() < len(ln)]
        pick = None
        for gs, ge in gaps:
            if pick is None or abs(ge - gutter) < abs(pick[1] - gutter):
                pick = (gs, ge)
        if pick and abs(pick[1] - gutter) <= 20:
            l_side, r_side = ln[:pick[0]], ln[pick[1]:]
            if l_side.strip():
                left.append(l_side.strip())
            if r_side.strip():
                right.append(r_side.strip())
        else:
            #  One column on this line: whichever side its text starts on.
            indent = len(ln) - len(ln.lstrip())
            (left if indent < gutter - 6 else right).append(ln.strip())
    joined = (chr(10).join(left).strip() + chr(10) + chr(10)
              + chr(10).join(right).strip())
    return joined.strip()


def _pdf_text(raw):
    """The text layer of a PDF, page by page.

    pypdf is pure Python -- no system libraries -- and reads the text a
    PDF already carries. It does NOT read a SCANNED pdf, which is images
    of pages with no text in them; there is nothing to extract, and the
    honest answer is to say so rather than return an empty site. OCR is
    a much heavier dependency and a separate decision.

    Bounded like the rest: refused if the extracted text would exceed
    MAX_TEXT_BYTES, checked as it is built rather than after.
    """
    try:
        import pypdf
    except ImportError:
        raise DocumentError(
            "This build cannot read PDFs. Save the document as Word or "
            "plain text, or paste it in.")
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
    except Exception:
        raise DocumentError("That PDF could not be opened. If it is "
                            "protected, save an unprotected copy first.")
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise DocumentError("That PDF is password-protected. Save an "
                                "unlocked copy and try again.")
    #  LAYOUT MODE. pypdf's default extraction reads glyphs in draw
    #  order and often loses the line breaks, so a real CV comes back as
    #  one run of merged text that has no headings to split on -- which
    #  is how a whole document became a single page of "basic data".
    #  Layout mode places the text by where it sits on the page, keeping
    #  the lines and the columns, which is what the section detection
    #  needs. It is newer, so if it is unavailable or returns nothing
    #  useful, the plain mode is the fallback -- something beats nothing.
    def _read(page):
        best = ""
        for kw in ({"extraction_mode": "layout"}, {}):
            try:
                t = page.extract_text(**kw) or ""
            except (TypeError, Exception):
                t = ""
            if len(t.strip()) > len(best.strip()):
                best = t
        #  Un-interleave a two-column layout while the horizontal
        #  spacing that reveals it is still there -- layout mode keeps
        #  it, plain mode does not, so this has to happen per page,
        #  here, before the pages are joined.
        return _split_columns(best)

    parts, size = [], 0
    for page in reader.pages:
        page_text = _read(page)
        parts.append(page_text)
        size += len(page_text)
        if size > MAX_TEXT_BYTES:
            raise DocumentError("That PDF is too big to read. Paste the "
                                "part you want instead.")
    text = chr(10).join(parts).strip()
    if not text:
        raise DocumentError(
            "That PDF has no text in it to read -- it looks like a scan or "
            "images of pages. Paste the text in, or use a Word or text copy.")
    #  Now that the columns are separated, the wide runs of spaces have
    #  done their job. What is left inside a line -- a right-aligned date
    #  held out to the margin -- is just gap, and it reads as a gap to
    #  everything downstream: "Lead Designer            2020" should be
    #  "Lead Designer 2020". Squeezed per line, so line breaks (the
    #  structure the section detector needs) are untouched.
    text = chr(10).join(re.sub(r"[ \t]{2,}", " ", ln).strip()
                        for ln in text.split(chr(10)))
    return text.strip()


def text_from(filename, raw):
    """(name, bytes) -> the writing in it.

    Raises DocumentError with something the owner can act on. Never
    returns markup, never touches the filesystem, and never guesses a
    format from the bytes: the extension is what the owner told us, and
    a file that is not one of them is refused by name rather than
    sniffed into something it is not.
    """
    name = (filename or "").strip().lower()
    if not raw:
        return ""
    if len(raw) > MAX_FILE_BYTES:
        raise DocumentError("That file is too big. Paste the part you want "
                            "instead, or save it as plain text.")
    if name.endswith(".docx"):
        return _docx_text(raw)
    if name.endswith(".pdf"):
        return _pdf_text(raw)
    if any(name.endswith(ext) for ext in READS):
        return _plain_text(raw).strip()
    #  NAME WHAT IS ACCEPTED, and refuse everything else. Calling out
    #  one format that is not read implies the rest are -- and the list
    #  of things somebody might try is endless (.pages, .odt, .rtf, a
    #  photograph of a page). One list; anything not on it is refused.
    raise DocumentError(
        "That file type is not accepted. This reads Word (.docx), PDF, "
        "and plain text (.txt, .md). Paste anything else in as text.")
