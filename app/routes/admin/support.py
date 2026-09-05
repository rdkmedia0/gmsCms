"""The Support screen: where to say thanks, and the supporter's key that
removes the credit line under the site's footer. The logic is in
services/support.py; this only asks and answers."""
from flask import request, flash, redirect, url_for, render_template

from . import bp
from ..auth import login_required
from ...services import support
from ... import version


@bp.route("/support")
@login_required
def support_screen():
    return render_template("admin/support.html",
                           paypal_url=support.PAYPAL_URL,
                           support_email=support.SUPPORT_EMAIL,
                           wallets=support.crypto_wallets(),
                           license=support.state(),
                           app_version=version.info())


@bp.route("/support/key", methods=["POST"])
@login_required
def support_key():
    """Apply or remove a supporter's key. Back to the same screen either
    way -- the answer belongs where the question was asked."""
    action = request.form.get("action", "apply")
    if action == "remove":
        if support.remove():
            flash("The key is removed. The line under your footer is back.", "success")
        else:
            flash("There was no key to remove.", "success")
    else:
        try:
            support.install_key(request.form.get("key", ""))
        except ValueError as e:
            flash(str(e), "error")
        else:
            flash("Thank you. The line under your footer is gone.", "success")
    return redirect(url_for("admin.support_screen"))


@bp.route("/support/claim", methods=["POST"])
@login_required
def support_claim():
    """Claim a key with a crypto transaction id: verify it on-chain against
    the project's addresses, and if it is a confirmed payment to us, issue
    the key on the spot. The on-chain calls can take a few seconds; the
    poller lives in the service, not here."""
    ok, message = support.claim_with_txid(request.form.get("txid", ""))
    flash(message, "success" if ok else "error")
    return redirect(url_for("admin.support_screen"))
