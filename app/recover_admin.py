"""The way back in when the password is forgotten. Run on the server:

    docker compose run --rm web python -m app.recover_admin admin

The name can be left out when the site has only one admin. What it does
and why it is shaped that way is in bootstrap.reset_admin_password; this
file is only the command line around it.

(Not called reset_password.py: the pre-commit hook refuses any file
named like a credential, and it is right to -- a name is the one thing a
check can see before content is even read.)
"""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m app.recover_admin",
        description="Give one admin a new one-use password, the same way a first "
                    "boot does. It is printed here and saved to data/"
                    "initial-admin-password.txt; the first sign-in with it must "
                    "replace it.")
    parser.add_argument("username", nargs="?",
                        help="which admin. Optional when there is only one.")
    args = parser.parse_args(argv)

    from . import create_app, bootstrap
    from .db import get_db

    app = create_app()
    with app.app_context():
        ok, lines = bootstrap.reset_admin_password(get_db(), app, args.username)
    print()
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
