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

READS = (".txt", ".md", ".markdown", ".text", ".docx")


class DocumentError(Exception):
    """Said to the owner, in their terms."""


def _plain_text(raw):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError("That file is not text this app can read.")


def _docx_text(raw):
    """The paragraphs of a .docx, in order.

    Tags out and paragraph breaks kept, because the breaks are most of
    what a CV's structure IS -- a list of roles with dates reads as a
    list only while the line endings survive. Done on the XML with a
    regex rather than a parser: the shapes being matched are two fixed
    tags, an XML parser brings entity-expansion questions of its own,
    and everything here is already bounded by MAX_TEXT_BYTES.
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
    #  A paragraph end and a line break become newlines; a tab becomes a
    #  tab. Every other tag goes.
    xml = re.sub(r"</w:p>", chr(10), xml)
    xml = re.sub(r"<w:br[^>]*/?>", chr(10), xml)
    xml = re.sub(r"<w:tab[^>]*/?>", chr(9), xml)
    text = re.sub(r"<[^>]+>", "", xml)
    #  html.unescape rather than a handful of replacements: Word writes
    #  numeric references for anything typographic -- an em dash arrives
    #  as &#8212; -- and five hand-written pairs turned "2021 to now --
    #  Independent practice" into "2021 to now &#8212; Independent
    #  practice" on a real document. There is one right list of these
    #  and it is in the standard library.
    text = html.unescape(text)
    #  Word writes a paragraph per line and plenty of empty ones.
    lines = [line.strip() for line in text.split(chr(10))]
    out = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return chr(10).join(out).strip()


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
    if any(name.endswith(ext) for ext in READS):
        return _plain_text(raw).strip()
    #  NAME WHAT IS ACCEPTED, and refuse everything else. Calling out
    #  one format that is not read implies the rest are -- and the list
    #  of things somebody might try is endless (.pages, .odt, .rtf, a
    #  photograph of a page). One list; anything not on it is refused.
    raise DocumentError(
        "That file type is not accepted. This reads Word documents "
        "(.docx) and plain text (.txt, .md). Paste anything else in as text.")
