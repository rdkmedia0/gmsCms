#!/bin/sh
set -e

# Starts as root only long enough to hand the mounted volumes to the
# unprivileged user, then drops and never comes back.
#
# The chown is what makes this work on an existing install: the database,
# uploads and themes were created by an earlier version of this image
# running as root, and a non-root process can read them but not write —
# which shows up as "attempt to write a readonly database" the first time
# anyone saves anything. Fixing it here means an upgrade is still just
# `docker compose up`, with nothing for the owner to do by hand.
# Serving TLS itself, when there is no proxy to do it. Both files have to
# be there: half a pair is a misconfiguration, and starting on plain HTTP
# because a path was mistyped is the kind of quiet downgrade nobody
# notices until it matters, so say so and stop.
if [ -n "$TLS_CERT_FILE" ] || [ -n "$TLS_KEY_FILE" ]; then
    if [ -z "$TLS_CERT_FILE" ] || [ -z "$TLS_KEY_FILE" ]; then
        echo "TLS_CERT_FILE and TLS_KEY_FILE must be set together." >&2
        exit 1
    fi
    for f in "$TLS_CERT_FILE" "$TLS_KEY_FILE"; do
        if [ ! -r "$f" ]; then
            echo "Cannot read $f — is it mounted into the container?" >&2
            exit 1
        fi
    done
    echo "Serving HTTPS with $TLS_CERT_FILE"
    set -- "$@" --certfile "$TLS_CERT_FILE" --keyfile "$TLS_KEY_FILE"
fi

if [ "$(id -u)" = "0" ]; then
    for d in /app/data /app/app/static/uploads /app/app/static/themes; do
        [ -d "$d" ] && chown -R cms:cms "$d" 2>/dev/null || true
    done
    # A certificate this process can read as root and the app cannot
    # read as cms is the same outage as no certificate at all, arriving
    # one second later with a worse error. Ask now, while there is
    # still somebody to tell.
    if [ -n "$TLS_CERT_FILE" ]; then
        for f in "$TLS_CERT_FILE" "$TLS_KEY_FILE"; do
            if ! setpriv --reuid=cms --regid=cms --init-groups test -r "$f"; then
                echo "$f cannot be read by the app's own user (uid 1000)." >&2
                echo "Give it group cms, or chmod it so uid 1000 can read it." >&2
                exit 1
            fi
        done
    fi
    # setpriv rather than su: no intermediate shell, so signals from
    # Docker reach gunicorn directly and a stop is a clean stop.
    exec setpriv --reuid=cms --regid=cms --init-groups "$@"
fi

exec "$@"
