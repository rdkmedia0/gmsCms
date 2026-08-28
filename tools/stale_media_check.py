"""Does an installed template stop carrying pictures it no longer ships?

Extracting a package adds files and never removes any, so a template
whose pictures changed format left the old ones behind on every install
that had run the earlier version. They are referenced by nothing and they
make the image picker show every picture twice.

    docker compose exec -T web python tools/stale_media_check.py
"""
import os
import shutil
import sys
import tempfile
import zipfile

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _here)

from app.services.packages import _drop_stale_media   # noqa: E402

passed = failed = 0


def check(what, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print("  %-56s %s%s" % (what, "ok" if ok else "FAILED", "   " + detail if detail and not ok else ""))


zips = os.path.join(_here, "app", "data", "template-packages")
sources = os.path.join(_here, "app", "data", "templates")
work = tempfile.mkdtemp(prefix="stale-")
try:
    #  Build one zip from an authored template, the way the image does.
    #
    #  The authored folders only exist where a template is WRITTEN: the
    #  packager stage turns them into zips and deletes them, so they are
    #  gone from the runtime image this runs in. A shipped zip is the same
    #  bytes that folder built, so unpacking one gives the same starting
    #  point -- and it means this checker runs in the same place as the
    #  other fifteen rather than only on a machine with the sources.
    base = os.path.join(work, "src")
    if os.path.isdir(sources) and os.listdir(sources):
        slug = sorted(os.listdir(sources))[0]
        shutil.copytree(os.path.join(sources, slug), base)
    else:
        slug = sorted(f for f in os.listdir(zips) if f.endswith(".zip"))[0][:-4]
        with zipfile.ZipFile(os.path.join(zips, slug + ".zip")) as zf:
            zf.extractall(base)
    check("there is a template to work from",
          os.path.isdir(os.path.join(base, "media")), slug)

    zip_path = os.path.join(work, slug + ".zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _dirs, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                zf.write(full, os.path.relpath(full, base).replace(os.sep, "/"))
    with zipfile.ZipFile(zip_path) as zf:
        shipped = sorted({os.path.basename(n) for n in zf.namelist()
                          if n.startswith("media/") and not n.endswith("/")})
    check("the test archive ships pictures", len(shipped) > 0, str(len(shipped)))

    #  An install of it, plus one picture from an older version.
    installed = os.path.join(work, "installed")
    media = os.path.join(installed, "media")
    os.makedirs(media)
    for name in shipped:
        open(os.path.join(media, name), "wb").write(b"x")
    stale = os.path.join(media, "left-over-from-an-older-version.png")
    open(stale, "wb").write(b"x")
    keeper = os.path.join(installed, ".installed-from")
    open(keeper, "w").write("digest")

    removed = _drop_stale_media(zip_path, installed)
    check("the picture no longer shipped is removed", not os.path.exists(stale))
    check("exactly one was removed", removed == 1, str(removed))
    check("every shipped picture is still there",
          all(os.path.exists(os.path.join(media, n)) for n in shipped))
    check("nothing outside media/ is touched", os.path.exists(keeper))

    #  Running again must be a no-op, not a second round of deleting.
    check("a second run removes nothing", _drop_stale_media(zip_path, installed) == 0)

    #  An unreadable or missing archive must never delete anything.
    before = sorted(os.listdir(media))
    _drop_stale_media(os.path.join(work, "not-here.zip"), installed)
    check("a missing archive leaves the folder alone", sorted(os.listdir(media)) == before)
    bad = os.path.join(work, "bad.zip")
    open(bad, "wb").write(b"not a zip")
    _drop_stale_media(bad, installed)
    check("an unreadable archive leaves the folder alone",
          sorted(os.listdir(media)) == before)
finally:
    shutil.rmtree(work, ignore_errors=True)

#  Both paths, because the first version of this only cleaned the boot
#  that SKIPPED reinstalling, and the templates that actually reinstalled
#  kept their old pictures.
import inspect                                                     # noqa: E402
from app.services import packages                                  # noqa: E402
_src = inspect.getsource(packages.install_template_zip)
check("the skipped-reinstall path cleans up",
      _src.count("_drop_stale_media") >= 1)
check("the real-install path cleans up too",
      _src.count("_drop_stale_media") >= 2, "%d call(s)" % _src.count("_drop_stale_media"))

print()
print("%d checks, %d failed" % (passed + failed, failed))
sys.exit(1 if failed else 0)
