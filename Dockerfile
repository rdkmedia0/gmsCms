#  Stage one exists to turn the templates into the form the app installs.
#  Each folder under app/data/templates is AUTHORED as loose files —
#  readable, diffable, reviewable in a pull request — and is built here
#  into one .zip per template, carrying its pages, its pictures, its theme
#  and an install.json saying exactly what importing it will do.
#
#  Built on every image build, because the templates are still being
#  edited: an archive generated from whatever the source folders currently
#  say cannot drift from them the way a checked-in one silently would.
#
#  The sources are then deleted here, before the runtime image copies the
#  tree across, and that ordering is the entire reason for a second stage:
#  delete them in a later layer of a single-stage build and the earlier
#  layer still holds them, so the image carries all 86MB of sources plus
#  the zips built from them.
FROM python:3.12-slim AS packager

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -c "from app.services.packages import build_template_zips;         print('built %d template packages' % len(build_template_zips()))"     && rm -rf app/data/templates     && find /app -name __pycache__ -type d -prune -exec rm -rf {} +


FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The user the app runs as, created BEFORE the COPY below, because
# that COPY hands it the files directly with --chown.
RUN useradd --create-home --uid 1000 cms

# --chown on the COPY, not a chown afterwards. `chown -R` rewrites the
# metadata of every file it touches, and to a layer a changed file is a
# new file -- so the recursive chown wrote a second, complete copy of
# everything COPY had just written. 126MB of image, to set an owner.
COPY --from=packager --chown=cms:cms /app /app

# Everything that must outlive the container. Three things live here and
# all three are unrecoverable if they are lost:
#
#   cms.db            every page, order, entitlement and booking
#   .encryption_key   the key the stored API keys are encrypted WITH.
#                     Losing it does not lose the keys visibly — they
#                     simply stop decrypting, and the app reports every
#                     provider as "not connected" with no other symptom.
#   .secret_key       signs sessions; losing it just logs everyone out
#
# DATA_DIR is set here, not only in docker-compose, so that `docker run`
# with no environment still puts them somewhere that survives. The VOLUME
# lines mean even a run with no -v gets an anonymous volume rather than
# writing into the container's own layer, where a rebuild destroys it.
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data /app/app/static/uploads /app/app/static/themes
VOLUME ["/app/data", "/app/app/static/uploads", "/app/app/static/themes"]

#  Run as somebody rather than as root. Nothing here is known to be
#  exploitable, but the value of this is entirely about the day something
#  is: a bug in an upload handler or a dependency is the difference
#  between "an app bug" and "an app bug with root on the container". The
#  data directory is chowned so the app can still write its database,
#  uploads and backups.
RUN chown cms:cms /app/data /app/app/static/uploads /app/app/static/themes
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
#  Deliberately NOT `USER cms`: the entrypoint needs root for exactly as
#  long as it takes to hand the mounted volumes over, then drops for good.
#  A volume created by an older root-run image is otherwise readable but
#  not writable, which surfaces as a broken save rather than a clear error.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

EXPOSE 5000

#  Asked from inside the container, so it needs no curl and no open port
#  on the host. /healthz touches the database, which is what makes this
#  worth having: a container whose data volume failed to mount is running
#  perfectly and serving nothing, and a check on the port alone calls
#  that healthy.
#
#  start-period covers the first boot, which installs sixteen template
#  packages before it serves anything. Three failures in a row (90s) is
#  slow enough not to trip over one gunicorn worker being busy with an AI
#  render, and quick enough to matter.
#  Asks over https when the app is serving its own certificate, and does
#  not verify it: this is a check on the loopback interface, where the
#  name on the certificate is never the name being asked for.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os,ssl,sys,urllib.request; tls=bool(os.environ.get('TLS_CERT_FILE')); url=('https' if tls else 'http')+'://127.0.0.1:5000/healthz'; ctx=ssl._create_unverified_context() if tls else None; sys.exit(0 if urllib.request.urlopen(url, timeout=4, context=ctx).status == 200 else 1)"

# --timeout 2000 (~33min) comfortably covers AI video generation
# (app/ai_video.py), which can spend several minutes waiting for a
# sleeping GPU backend to wake up (see DISPATCH_WAKE_TIMEOUT_S) on top of
# however long the actual render takes (POLL_TIMEOUT_S) — the slowest
# thing this app does by a wide margin.
#
# THREADS, not just workers, and that is about running with nothing in
# front. Two sync workers can hold two connections; a proxy hides this
# because it accepts the request itself and only speaks to gunicorn once
# it has the whole thing. Directly exposed, two clients that open a
# socket and dawdle are the entire server — and with a 2000s timeout they
# hold it for half an hour. 2 workers x 8 threads is 16 concurrent
# connections for a site whose real concurrency is one owner and a
# handful of readers, and it turns "the site is down" into "the site is
# briefly slower".
#
# --access-logfile - puts request lines on stdout with everything else,
# so `docker compose logs` (or a host's log viewer) shows what the site
# actually served. Without it gunicorn logs errors only, and a live site
# that is quietly 404ing looks identical to one nobody is visiting.
#
# No --forwarded-allow-ips: the app decides for itself which peers may
# talk about X-Forwarded-* (see TrustedProxyFix), and gunicorn rewriting
# the scheme first would undo that decision.
# --preload builds the app ONCE in the master and forks workers from it.
# Without it every worker independently runs the migration and installs
# all sixteen template packages, at the same moment, against the same
# file — which on a first boot, where there is real work to do, is two
# processes racing over an empty database. There was never a reason for
# the second one to do it.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--preload", \
     "--workers", "2", "--worker-class", "gthread", "--threads", "8", \
     "--timeout", "2000", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", "run:app"]
