"""Remember what was read from a theme folder until that folder changes.

An admin's page lists every installed template and every picture it
brought, which came to several hundred file reads and stats per render.
On a folder mounted from Windows or macOS each one costs milliseconds, so
one page took over two seconds -- and every style change renders a page.

One stat per folder decides whether the remembered answer still holds.
Kept per process: a gunicorn worker that has not seen a change notices it
on its next look, from the same stat.
"""
import os

_DIRS = {}


def listing(folder):
    """[(name, mtime), ...] for the files in `folder`, sorted by name; []
    when there is no such folder. A folder's own mtime moves when a file
    is added, removed or renamed, which is every change that matters here."""
    try:
        stamp = os.stat(folder).st_mtime_ns
    except OSError:
        _DIRS.pop(folder, None)
        return []
    hit = _DIRS.get(folder)
    if hit and hit[0] == stamp:
        return hit[1]
    files = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_file():
                    files.append((entry.name, entry.stat().st_mtime))
    except OSError:
        return []
    files.sort()
    _DIRS[folder] = (stamp, files)
    return files


def stamp(*paths):
    """A signature that changes when any of these files or folders does."""
    out = []
    for path in paths:
        try:
            st = os.stat(path)
            out.append((st.st_mtime_ns, st.st_size, st.st_ino))
        except OSError:
            out.append(None)
    return tuple(out)
