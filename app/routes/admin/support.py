"""The Support screen: where to show appreciation, and the one switch for
the small credit line under the footer. Logic is in services/support.py;
this only asks and answers."""
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
                           github_url=support.GITHUB_CONTACT_URL,
                           wallets=support.crypto_wallets(),
                           notice_hidden=support.notice_hidden(),
                           app_version=version.info())


@bp.route("/support/line", methods=["POST"])
@login_required
def support_line():
    """Show or hide the footer credit line. No payment, no key -- the
    owner's choice, taken and reversed here."""
    hide = request.form.get("action") == "hide"
    support.set_notice_hidden(hide)
    if hide:
        flash("The gmsCms line is hidden from your footer. You can bring it back here any time.", "success")
    else:
        flash("The gmsCms line is showing under your footer again. Thank you!", "success")
    return redirect(url_for("admin.support_screen"))
