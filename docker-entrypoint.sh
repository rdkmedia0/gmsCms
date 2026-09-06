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
#
# Only when what is being started IS the web server. `docker compose run
# web python -m app.recover_admin` comes through here too, and handing
# python a --certfile it never asked for turned the one command an owner
# runs when locked out into a traceback -- on exactly the installs that
# had done everything right.
serving=0
case "${1##*/}" in gunicorn) serving=1 ;; esac
if [ "$serving" = 1 ] && { [ -n "$TLS_CERT_FILE" ] || [ -n "$TLS_KEY_FILE" ]; }; then
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
    # Docker copies /etc/resolv.conf in from the host WITH ITS MODE. A
    # host that keeps its own at 0640 hands this container a resolver
    # config that root can read and the app's unprivileged user cannot --
    # and glibc does not report that. Given an unreadable resolv.conf it
    # falls back to 127.0.0.1:53, which is nothing here, so every name
    # lookup fails with "Temporary failure in name resolution" and
    # payments, bookings and email all stop working at once.
    #
    # Almost no image hits this, because almost no image gives up root.
    # This one does, so it has to make the file readable to the user it is
    # about to become. The mode of the CONTAINER's copy is changed; the
    # host's own file is untouched, and no DNS server is imposed -- it
    # keeps whatever resolver the host gave it.
    if [ -f /etc/resolv.conf ] && ! setpriv --reuid=cms --regid=cms --init-groups test -r /etc/resolv.conf; then
        chmod o+r /etc/resolv.conf 2>/dev/null             && echo "Made /etc/resolv.conf readable by the app's user (it arrived unreadable)."             || echo "WARNING: /etc/resolv.conf is not readable by uid 1000 and could not be changed. No name will resolve." >&2
    fi

    # A certificate this process can read as root and the app cannot
    # read as cms is the same outage as no certificate at all, arriving
    # one second later with a worse error. Ask now, while there is
    # still somebody to tell.
    if [ "$serving" = 1 ] && [ -n "$TLS_CERT_FILE" ]; then
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
