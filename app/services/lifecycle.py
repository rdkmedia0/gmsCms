"""A template is a SOURCE or it is CUSTOM, and that decides what may
happen to it.

  * A **source** never changes. The sixteen shipped ones are sources, and
    so is any custom template the owner has finished with and promoted.
    A source is a starting point, and a starting point that moves is not
    one. It is packaged, and therefore exportable.
  * A **custom** template is work in progress: forked from a source,
    freely editable, private to this install. It has no zip, so there is
    nothing to keep in step with the edits.

Two consequences fall out of that, and both fix something real.

**The fork stops being an accident and becomes a question.** It used to
fire on the first content edit, which produced three identically-named
"(your copy)" entries on one live install, each with its own duplicate of
the template's pictures. Content edits write to the SITE -- pages and
sections -- and never needed a copy. Changing a LOOK is the first moment
anything shipped would actually be altered, so that is where the question
belongs.

**Packaging gets a moment.** `export_package_zip()` used to be offered on
any library entry at any time, so a half-finished custom template could
be handed to somebody else as though it were a thing. It isn't; it is a
draft. Promotion is when the artefact is built -- and it is the right
place for the completeness check, because it is a deliberate act with a
person waiting on it. A package once went out silently missing its pages
and its pictures; promotion is the one moment where "this references four
pictures and three of them exist" can be reported to somebody who can do
something about it, rather than discovered by whoever installs it later.

`is_builtin` stops being the thing the code branches on. "Shipped" is now
one of two reasons a template is a source, which is what stops promoted
templates being a special case bolted on beside them.
"""
import os


def is_source(template):
    """Shipped, or finished and promoted. Either way: immutable."""
    if template is None:
        return False
    try:
        return bool(template["is_builtin"] or template["is_promoted"])
    except (KeyError, IndexError, TypeError):
        #  A row read before the column existed. Tolerated rather than
        #  raised: this is asked on every admin screen, and a migration
        #  that has not run yet must not take the whole admin down.
        return bool(template["is_builtin"])


def kind(template):
    """What to call it on screen."""
    if template is None:
        return "custom"
    if template["is_builtin"]:
        return "shipped"
    try:
        return "promoted" if template["is_promoted"] else "custom"
    except (KeyError, IndexError, TypeError):
        return "custom"


def can_export(template):
    """Only a source has an artefact to export. A custom template is a
    draft, and handing somebody a draft as though it were a template is
    how an incomplete package goes out."""
    return is_source(template)


def depends_on(db, template):
    """What would break if this stopped being a source.

    Promotion is reversible while nothing depends on it and refused once
    something does -- the same shape as "the active template cannot be
    deleted", which is the guard that made an earlier cleanup safe.
    """
    reasons = []
    if template["is_active"]:
        reasons.append("it is the template this site is using")
    forks = db.execute(
        "SELECT COUNT(*) c FROM templates WHERE forked_from = ?",
        (template["slug"],)).fetchone()["c"]
    if forks:
        reasons.append("%d template%s %s forked from it"
                       % (forks, "" if forks == 1 else "s",
                          "was" if forks == 1 else "were"))
    return reasons


class Incomplete(Exception):
    """A template that cannot be promoted, and exactly why."""

    def __init__(self, problems):
        self.problems = problems
        Exception.__init__(self, "; ".join(problems))


def completeness(pkg_dir):
    """What is wrong with this template as a distributable package.

    Read from the FILES, not from the database, because the files are
    what travels. A picture the database knows about and the folder does
    not is precisely the failure this exists to catch -- it is how a
    package went out looking complete and arrived empty.
    """
    import json

    problems = []
    if not pkg_dir or not os.path.isdir(pkg_dir):
        return ["Its files are missing, so there is nothing to package."]

    manifest_path = os.path.join(pkg_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return ["It has no manifest.json, so nothing would know what it is."]
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    except (ValueError, OSError) as e:
        return ["Its manifest.json cannot be read (%s)." % e]
    if not (manifest.get("name") or "").strip():
        problems.append("It has no name in its manifest.")

    pages_dir = os.path.join(pkg_dir, "pages")
    pages = sorted(f for f in os.listdir(pages_dir)
                   if f.endswith(".json")) if os.path.isdir(pages_dir) else []

    #  Every picture a page points at has to be IN the package. A template
    #  whose pictures live in a shared folder is a template that arrives
    #  blank on somebody else's install.
    media_dir = os.path.join(pkg_dir, "media")
    have = set(os.listdir(media_dir)) if os.path.isdir(media_dir) else set()
    wanted = set()
    for name in pages:
        try:
            raw = open(os.path.join(pages_dir, name), encoding="utf-8").read()
        except OSError:
            problems.append("%s cannot be read." % name)
            continue
        for marker in ("/static/themes/", "media/"):
            start = 0
            while True:
                at = raw.find(marker, start)
                if at < 0:
                    break
                end = at
                #  A backslash too: page JSON escapes its quotes, so
                #  stopping only at a quote captured the backslash in
                #  front of it, and made this look for a file whose
                #  name ended in one.
                while end < len(raw) and raw[end] not in '"\' <>)\\':
                    end += 1
                wanted.add(os.path.basename(raw[at:end]))
                start = end
    missing = sorted(w for w in wanted if w and w not in have and "." in w)
    if missing:
        problems.append(
            "%d picture%s referenced but not included: %s"
            % (len(missing), "" if len(missing) == 1 else "s", ", ".join(missing[:5])))

    if not pages and not os.path.isfile(os.path.join(pkg_dir, "theme.css")):
        problems.append("It has neither pages nor a theme.css, so it would do nothing.")
    return problems
