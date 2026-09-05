"""Make a supporter's key -- the thing that removes the "Built with gmsCms"
line under a site's footer until the day it names.

    python tools/make_license.py 2027-09-05      # until that day
    python tools/make_license.py --months 12     # a year from today
    python tools/make_license.py --check GMS-20270905-...   # what a key says

Run by the person who RECEIVED the support, never by the app: the app
only checks keys (services/support.py). The signing key lives in
services/support_key.py, loaded here by path -- it is standard library
only, so this runs on a machine with no Flask installed and without
importing the app (which would open a database). Run from anywhere.
"""
import os
import sys
import datetime
import importlib.util

_KEY_MODULE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "services", "support_key.py")
_spec = importlib.util.spec_from_file_location("support_key", _KEY_MODULE)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


def _months_from_today(n):
    today = datetime.date.today()
    month = today.month - 1 + n
    year = today.year + month // 12
    month = month % 12 + 1
    day = min(today.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return datetime.date(year, month, day)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--check":
        until = support.parse_key(argv[1] if len(argv) > 1 else "")
        if until is None:
            print("Not a genuine key.")
            return 1
        left = (until - datetime.date.today()).days
        print(f"Genuine. Runs until {until.isoformat()} ({left} days {'left' if left >= 0 else 'ago'}).")
        return 0
    if argv[0] == "--months":
        until = _months_from_today(int(argv[1]))
    else:
        until = datetime.date.fromisoformat(argv[0])
    if until < datetime.date.today():
        print("That day has already passed.")
        return 1
    print(support.make_key(until))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
