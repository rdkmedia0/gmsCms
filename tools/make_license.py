"""Make a supporter's key -- the thing that removes the "Built with gmsCms"
line under a site's footer. One-off and permanent; one per site.

    python tools/make_license.py            # one key
    python tools/make_license.py 3          # three keys (three sites)
    python tools/make_license.py --check GMS-1A2B3C4D-...   # is this one ours?

Run by the person who RECEIVED the support, never by the app: the app
only checks keys (services/support.py). The signing key lives in
services/support_key.py, loaded here by path -- it is standard library
only, so this runs on a machine with no Flask installed and without
importing the app (which would open a database). Run from anywhere.
"""
import os
import sys
import importlib.util

_KEY_MODULE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "services", "support_key.py")
_spec = importlib.util.spec_from_file_location("support_key", _KEY_MODULE)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv and argv[0] == "--check":
        ok = support.parse_key(argv[1] if len(argv) > 1 else "")
        print("Genuine." if ok else "Not a genuine key.")
        return 0 if ok else 1
    count = int(argv[0]) if argv else 1
    if count < 1 or count > 100:
        print("Between 1 and 100 keys at a time.")
        return 1
    for _ in range(count):
        print(support.make_key())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
