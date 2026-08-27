"""
The Legal pages screen: a few plain questions, then real pages.

Thin by design — everything about what the documents say, and why they say
it, lives in services/legal.py and the templates it renders.
"""
from flask import request, flash, redirect, url_for, render_template

from . import bp
from ..auth import login_required
from ...db import get_db
from ...services import legal, subscribers


@bp.route("/legal")
@login_required
def legal_pages():
    db = get_db()
    return render_template(
        "admin/legal.html",
        settings=legal.settings_for(db),
        #  Built from the number already on file, because the one thing a
        #  person cannot be expected to know is that wa.me wants the
        #  international number and nothing else. See legal.whatsapp_link.
        whatsapp=legal.whatsapp_link(legal.settings_for(db).get("phone")),
        site_name=((db.execute(
            "SELECT value FROM settings WHERE key = 'site_title'").fetchone() or {"value": ""})["value"] or "").strip(),
        documents=legal.DOCUMENTS,
        countries=legal.COUNTRIES,
        sells=legal.what_is_sold(db),
        existing=legal.existing_pages(db),
        missing=legal.missing_details(db),
    )


@bp.route("/legal/save", methods=["POST"])
@login_required
def legal_save():
    db = get_db()
    legal.save_settings(db, request.form)
    db.commit()
    flash("Your details are saved. Now choose which pages to write.", "success")
    return redirect(url_for("admin.legal_pages"))


@bp.route("/legal/write", methods=["POST"])
@login_required
def legal_write():
    """Writes the chosen documents as ordinary pages.

    Re-running is the normal case, not an edge case: details change, and
    what the site sells changes — adding downloads to a shop that only
    sold sessions means the refunds page is now wrong. Only the section
    this tool wrote is replaced, so anything the owner added to the page
    survives a refresh.
    """
    db = get_db()
    missing = legal.missing_details(db)
    if missing:
        flash("Fill in " + ", ".join(missing) + " first — the pages would name nobody otherwise.",
              "error")
        return redirect(url_for("admin.legal_pages"))
    #  One page or several. Defaulting to one, because four extra entries
    #  in the navigation of a five-page site is a real cost, and most
    #  sites put this on a single page anyway.
    combined = request.form.get("layout", "combined") == "combined"
    chosen = request.form.getlist("documents")
    if not chosen:
        flash("Tick at least one page to write.", "error")
        return redirect(url_for("admin.legal_pages"))
    written, updated = legal.write_pages(db, chosen, combined=combined)
    db.commit()
    parts = []
    if written:
        parts.append("Created " + ", ".join(written))
    if updated:
        parts.append("Refreshed " + ", ".join(updated))
    flash(". ".join(parts) + ". Read them through and change anything that isn't how you work — "
          "they're ordinary pages now.", "success")
    return redirect(url_for("admin.legal_pages"))


@bp.route("/subscribers")
@login_required
def subscriber_list():
    db = get_db()
    return render_template(
        "admin/subscribers.html",
        people=subscribers.listing(db, include_gone=True),
        counts=subscribers.counts(db),
        #  Read once for the whole list rather than a query per row: the
        #  question "has this address bought anything" is asked of every
        #  line on a screen that can run to thousands.
        orders=subscribers.orders_by_email(db),
    )


@bp.route("/subscribers/<int:subscriber_id>/customer", methods=["POST"])
@login_required
def subscriber_customer(subscriber_id):
    """The owner's own answer to "is this person a customer".

    It sits beside what the orders say rather than instead of them: a
    shop sale, a telephone order, or somebody who signed up with one
    address and bought with another are all real customers this site has
    no record of. Taking the flag off somebody who HAS bought something
    leaves them a customer, because they are one -- the flag adds, it
    does not veto.
    """
    db = get_db()
    flag = request.form.get("flag") == "1"
    email = subscribers.set_customer_flag(db, subscriber_id, flag)
    db.commit()
    if email:
        flash(f"{email} is flagged as a customer." if flag
              else f"Removed the customer flag from {email}.", "success")
    return redirect(url_for("admin.subscriber_list"))


@bp.route("/subscribers/<int:subscriber_id>/erase", methods=["POST"])
@login_required
def subscriber_erase(subscriber_id):
    """Removes somebody from the list completely.

    Not the same act as unsubscribing them, and both are needed. An
    unsubscribe stops the mail and keeps the row, which is what evidences
    that it stopped. An erasure takes the person out of the site
    altogether -- their address, and with it the record of what they
    agreed to -- which is what somebody asking to be forgotten is asking
    for, and what an owner tidying up a test address wants too.
    """
    db = get_db()
    email = subscribers.erase(db, subscriber_id)
    db.commit()
    flash(f"Erased {email}." if email else "That address is not on the list.",
          "success" if email else "error")
    return redirect(url_for("admin.subscriber_list"))


@bp.route("/subscribers/export")
@login_required
def subscriber_export():
    from flask import Response
    csv_text = subscribers.export_csv(get_db())
    return Response(csv_text, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=subscribers.csv"})
