"""
CSRF defense via Origin/Referer validation, applied to every state-changing
request app-wide — deliberately not a per-form hidden-token scheme.

This app has no central form-rendering helper (every <form> across ~15
templates is a raw, independently hand-written tag, plus several JS
fetch() calls), so a token-based scheme would mean threading a hidden
field through every single one of them — easy to miss one, and a missed
one either breaks silently (rejected with no token) or, worse, is quietly
left unprotected. Origin/Referer checking protects every route uniformly
from one place, with no template or JS changes required and no risk of a
forgotten form: a genuine cross-site request (from an attacker's page, or
curl/script with a forged/absent browser context) never carries a
same-origin Origin/Referer, so it's rejected regardless of which route it
targets — a browser cannot forge either header to lie about where a
request actually originated. This is the same mechanism OWASP lists as an
acceptable primary CSRF defense (see "Verifying Origin with Standard
Headers") for exactly this kind of app.
"""
from flask import request, abort

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

#  Endpoints that carry their own cryptographic proof of origin and so
#  cannot use the check below. A payment provider is not a browser: it
#  sends no Origin or Referer, and would be rejected by every rule in this
#  file. It signs its payload instead, and the route MUST verify that
#  signature before reading a single field — see
#  services/commerce.verify_stripe_signature.
#
#  This list is deliberately explicit and deliberately short. Adding a name
#  here removes a route's CSRF protection, so nothing belongs here unless
#  it replaces that protection with something at least as strong.
SIGNATURE_VERIFIED_ENDPOINTS = {
    "public.stripe_webhook",
}

#  Endpoints whose entire credential is an unguessable token in the URL,
#  and whose POST does exactly what their GET already does.
#
#  One member, and it earns it: a one-click unsubscribe. A mail program
#  that finds List-Unsubscribe-Post in a message offers its own
#  unsubscribe button and, when pressed, POSTs to the link -- from the
#  mail client, with no Origin and no Referer, which every rule in this
#  file rejects. There is nothing here for CSRF to protect. The link
#  already works as a GET, so anything that could forge the POST could
#  simply follow the link; what actually guards the row is that the token
#  is 128 random bits, which is why it is random rather than made from
#  the address. And the worst a forgery achieves is unsubscribing
#  somebody who can subscribe again -- against which the alternative is
#  the mail client's OTHER button, marked spam.
TOKEN_IS_THE_CREDENTIAL_ENDPOINTS = {
    "public.unsubscribe",
}


def _request_origin_host():
    """The host a browser says this request actually came from, from
    whichever of Origin/Referer is present — Origin is preferred (sent by
    fetch/XHR and modern form submissions), Referer is the fallback for
    older browsers. Neither can be set by JavaScript on a genuine
    cross-site request; both are only ever missing if the request wasn't
    made by a browser navigating/submitting from a real page at all."""
    origin = request.headers.get("Origin")
    if origin:
        # "null" is a real value some browsers send for sandboxed/file:// contexts.
        if origin == "null":
            return None
        from urllib.parse import urlparse
        return urlparse(origin).netloc
    referer = request.headers.get("Referer")
    if referer:
        from urllib.parse import urlparse
        return urlparse(referer).netloc
    return None


def init_csrf(app):
    @app.before_request
    def _check_origin():
        if request.method in SAFE_METHODS:
            return
        if request.endpoint in SIGNATURE_VERIFIED_ENDPOINTS:
            return  # proves itself by signature instead — see above
        if request.endpoint in TOKEN_IS_THE_CREDENTIAL_ENDPOINTS:
            return  # the URL is the credential, and its GET does the same
        origin_host = _request_origin_host()
        # request.host already reflects the real external host (ProxyFix
        # trusts X-Forwarded-Host — see create_app), so this compares
        # against what the browser/user actually sees as the site's
        # address, not the container's internal one.
        if not origin_host or origin_host != request.host:
            abort(403)
