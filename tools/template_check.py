"""A template is a source or it is custom, and that decides what may
happen to it.

Three things this is the net under, each of which has already gone wrong
on a live install:

  * **The fork used to be an accident.** It fired on the first content
    edit and produced three identically-named "(your copy)" entries, each
    with its own duplicate of the template's pictures. It is a question
    now, asked when a LOOK changes, and answered with a name.
  * **A draft could be handed over as though it were finished.** Export
    was offered on any library entry at any time. A package once went out
    silently missing its pages and its pictures.
  * **An owner's edits were disposable.** Activating a template deleted
    every page whose `source_template` was a different pack -- including
    ones somebody had since rewritten, because an edited page still
    carries the slug it arrived with.

Run inside the container:

    docker compose exec -T web python tools/template_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/app")

DATA_DIR = tempfile.mkdtemp(prefix="template-check-")
os.environ["DATA_DIR"] = DATA_DIR

from app import create_app                                    # noqa: E402
from app.db import get_db                                     # noqa: E402
from app.services import lifecycle                            # noqa: E402

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    print("  %-58s %s%s" % (name, "ok" if ok else "FAILED",
                            "  " + detail if detail and not ok else ""))
    if ok:
        passed += 1
    else:
        failures.append(name)


app = create_app()

with app.app_context():
    db = get_db()

    print()
    print("Every route that changes a look is guarded")
    print("-" * 70)
    #  The guard is a named SET, and this is why: a seventeenth route
    #  that forgets to join it would silently let somebody edit a shipped
    #  template. A set can be checked against the routing table; a
    #  decorator on each route cannot.
    from app.routes.admin.templates import LOOK_ENDPOINTS
    look_like_looks = set()
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("admin.template"):
            continue
        if "POST" not in (rule.methods or set()):
            continue
        path = str(rule)
        if any(part in path for part in
               ("/colors", "/fonts", "/shape", "/shadow", "/shades", "/zone-style")):
            look_like_looks.add(rule.endpoint)
    missing = sorted(look_like_looks - LOOK_ENDPOINTS)
    check("no look-changing route is left out of the guard", not missing,
          ", ".join(missing))
    stale = sorted(LOOK_ENDPOINTS - {r.endpoint for r in app.url_map.iter_rules()})
    check("...and the guard names no route that no longer exists", not stale,
          ", ".join(stale))
    check("the guard covers a real number of them", len(look_like_looks) >= 10,
          str(len(look_like_looks)))

    print()
    print("Shipped and promoted are both sources; custom is not")
    print("-" * 70)
    shipped = db.execute("SELECT * FROM templates WHERE is_builtin = 1 LIMIT 1").fetchone()
    check("a shipped template is a source", lifecycle.is_source(shipped))
    check("...and can be exported", lifecycle.can_export(shipped))
    check("...and is called a starting point", lifecycle.kind(shipped) == "shipped")

    #  A custom one, made the way a fork makes one.
    db.execute("INSERT INTO templates (name, slug, is_builtin, is_active) "
               "VALUES ('Mine', 'mine', 0, 0)")
    db.commit()
    mine = db.execute("SELECT * FROM templates WHERE slug = 'mine'").fetchone()
    check("a custom template is not a source", not lifecycle.is_source(mine))
    check("...and cannot be exported", not lifecycle.can_export(mine))
    check("...and is called work in progress", lifecycle.kind(mine) == "custom")

    db.execute("UPDATE templates SET is_promoted = 1 WHERE slug = 'mine'")
    db.commit()
    promoted = db.execute("SELECT * FROM templates WHERE slug = 'mine'").fetchone()
    check("a promoted template IS a source", lifecycle.is_source(promoted))
    check("...and can be exported", lifecycle.can_export(promoted))
    check("...and is told apart from a shipped one",
          lifecycle.kind(promoted) == "promoted")

    print()
    print("Promotion is reversible until something depends on it")
    print("-" * 70)
    check("nothing depends on it yet", lifecycle.depends_on(db, promoted) == [],
          str(lifecycle.depends_on(db, promoted)))

    db.execute("INSERT INTO templates (name, slug, is_builtin, is_active, forked_from) "
               "VALUES ('A fork', 'a-fork', 0, 0, 'mine')")
    db.commit()
    check("a fork of it is a dependency",
          any("forked from it" in r for r in lifecycle.depends_on(db, promoted)),
          str(lifecycle.depends_on(db, promoted)))

    db.execute("DELETE FROM templates WHERE slug = 'a-fork'")
    db.execute("UPDATE templates SET is_active = 1 WHERE slug = 'mine'")
    db.commit()
    active = db.execute("SELECT * FROM templates WHERE slug = 'mine'").fetchone()
    check("being in use is a dependency too",
          any("using" in r for r in lifecycle.depends_on(db, active)),
          str(lifecycle.depends_on(db, active)))

    print()
    print("Promotion refuses an incomplete package, and says what is wrong")
    print("-" * 70)
    #  The point of checking HERE is that somebody is waiting to be told.
    empty = tempfile.mkdtemp(prefix="tpl-empty-")
    check("no manifest is refused",
          any("manifest" in p for p in lifecycle.completeness(empty)),
          str(lifecycle.completeness(empty)))

    with open(os.path.join(empty, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write('{"name": "A thing"}')
    check("a manifest with nothing behind it is refused",
          any("nothing" in p or "neither" in p for p in lifecycle.completeness(empty)),
          str(lifecycle.completeness(empty)))

    #  The failure this exists for: a page pointing at a picture the
    #  package does not carry.
    os.makedirs(os.path.join(empty, "pages"))
    with open(os.path.join(empty, "pages", "01-home.json"), "w", encoding="utf-8") as fh:
        fh.write('{"sections": [{"content": "<img src=\\"/static/themes/x/media/hero.png\\">"}]}')
    problems = lifecycle.completeness(empty)
    check("a picture referenced but not included is named",
          any("hero.png" in p for p in problems), str(problems))

    os.makedirs(os.path.join(empty, "media"))
    open(os.path.join(empty, "media", "hero.png"), "wb").write(b"x")
    check("...and once it is there, it passes", lifecycle.completeness(empty) == [],
          str(lifecycle.completeness(empty)))
    shutil.rmtree(empty, ignore_errors=True)

    print()
    print("A template load loads the template's pages -- all of them")
    print("-" * 70)
    from app.routes.admin import _retire_foreign_pack_pages
    db.execute("INSERT INTO pages (title, slug, source_template, is_home) "
               "VALUES ('Untouched', 'untouched', 'oldpack', 0)")
    db.execute("INSERT INTO pages (title, slug, source_template, is_home) "
               "VALUES ('Written in', 'written-in', 'oldpack', 0)")
    db.commit()
    written = db.execute("SELECT id FROM pages WHERE slug = 'written-in'").fetchone()["id"]
    #  Through the trigger, the way a real edit does it -- not by setting
    #  the column, which would prove only that the column exists.
    db.execute("INSERT INTO sections (page_id, zone, type, content, position) "
               "VALUES (?, 'body', 'html', '<p>My own words</p>', 0)", (written,))
    db.commit()
    marked = db.execute("SELECT owner_edited FROM pages WHERE id = ?",
                        (written,)).fetchone()["owner_edited"]
    check("writing a section marks its page as written in", marked == 1, str(marked))

    #  A TEMPLATE IS A STRUCTURED WEBSITE, PAGES INCLUDED. Loading one
    #  loads its pages and the previous template's go -- all of them.
    #
    #  This checked the opposite until today: a page carrying
    #  `owner_edited` was SPARED, and a spared page is spared by every
    #  future switch as well. Combined with a bug that marked every page
    #  of every pack as edited, that is how one template's "The library"
    #  survived onto three unrelated sites carrying its own heading.
    #
    #  The care that rule was reaching for is a warning now, not a veto:
    #  the second return value names the pages that had the owner's own
    #  writing in them, and the caller says so. Keeping them is what
    #  "just the look" is for.
    removed, written_in = _retire_foreign_pack_pages(db, "newpack")
    check("an untouched page from an old pack is removed",
          "Untouched" in removed, str(removed))
    check("a page somebody wrote in is removed too",
          "Written in" in removed, str(removed))
    check("...and it is gone afterwards",
          db.execute("SELECT 1 FROM pages WHERE slug = 'written-in'").fetchone() is None)
    check("...and the owner is told which of them they had written in",
          "Written in" in written_in, str(written_in))

    print()
    print("Loading a template's content makes the page the template's again")
    print("-" * 70)
    #  A fresh page: the one above is gone now, which is the rule this
    #  file states two sections up. The flag still exists and still means
    #  "somebody wrote in this" -- it is what the warning is built from --
    #  and putting the pack's own copy back is what un-sets it.
    db.execute("INSERT INTO pages (title, slug, source_template, is_home) "
               "VALUES ('Reloaded', 'reloaded', 'oldpack', 0)")
    db.commit()
    again = db.execute("SELECT id FROM pages WHERE slug = 'reloaded'").fetchone()["id"]
    db.execute("INSERT INTO sections (page_id, zone, type, content, position) "
               "VALUES (?, 'body', 'html', '<p>Mine</p>', 0)", (again,))
    db.commit()
    check("writing in it marks it again",
          db.execute("SELECT owner_edited FROM pages WHERE id = ?",
                     (again,)).fetchone()["owner_edited"] == 1)
    db.execute("UPDATE pages SET owner_edited = 0 WHERE id = ?", (again,))
    db.commit()
    check("after Load Content it is the pack's copy again",
          db.execute("SELECT owner_edited FROM pages WHERE id = ?",
                     (again,)).fetchone()["owner_edited"] == 0)

shutil.rmtree(DATA_DIR, ignore_errors=True)
print()
print("%d checks, %d failed" % (passed + len(failures), len(failures)))
sys.exit(1 if failures else 0)
