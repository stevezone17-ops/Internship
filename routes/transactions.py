import io
import time
from datetime import timedelta
import pandas as pd
from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template, send_file
from bson import ObjectId
from werkzeug.security import check_password_hash, generate_password_hash

from models.db import get_collections
from services.accounts import (
    ACCOUNT_RULES,
    ensure_account_owner,
    get_account_by_id,
    get_account_for_user,
)
from services.notifications import add_notification
from services.transactions import record_transaction
from services.fake_email_service import (
    build_deposit_email,
    build_transfer_email,
    build_transfer_received_email,
    build_withdraw_email,
    send_deposit_email,
    send_fake_email,
)
from utils.helpers import (
    api_error,
    api_success,
    get_display_name,
    get_session_user_id,
    make_aware,
    format_currency,
    verify_transaction_pin,
)
from utils.time_utils import ist_now, format_ist
from utils.validators import parse_amount, parse_date
from utils.logging_config import setup_logging

logger = setup_logging()
transactions_bp = Blueprint("transactions", __name__)
cols = get_collections()
accounts_col = cols["accounts"]
transactions_col = cols["transactions"]
users_col = cols["users"]
notifications_col = cols["notifications"]
scheduled_transfers_col = cols["scheduled_transfers"]

# Temporary in-memory cache for recent transactions by account id.
recent_transactions = {}


def insert_transaction(account_id, tx_type, amount, metadata=None):
    tx_doc, tx_tuple, warnings = record_transaction(
        transactions_col, account_id, tx_type, amount, metadata
    )
    cache_key = str(account_id)
    recent_transactions.setdefault(cache_key, []).append(tx_tuple)
    return tx_doc, warnings

def get_session_account_id():
    account_id = session.get("account_id")
    if account_id:
        return account_id

    user_id = session.get("user_id")
    if not user_id:
        return None

    account = get_account_for_user(accounts_col, user_id)
    if account:
        session["account_id"] = str(account["_id"])
        return session["account_id"]
    return None

@transactions_bp.route("/api/deposit", methods=["POST"])
def deposit():
    data = request.get_json(silent=True) or request.form
    account_id = get_session_account_id()
    if not account_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")
    amount = parse_amount(data.get("amount"))
    entered_pin = (data.get("pin") or "").strip()

    if amount is None or amount <= 0:
        return api_error("Please check your input.", 400, endpoint="main.transact_page", category="warning")

    user = users_col.find_one({"_id": ObjectId(get_session_user_id())})
    if not user:
        return api_error("User not found.", 404, endpoint="auth.login_page")

    ok, err, status = verify_transaction_pin(users_col, user, entered_pin)
    if not ok:
        if status == 403:
             if request.is_json:
                return jsonify({"error": err, "require_pin_setup": True, "setup_url": "/setup-pin"}), 403
             flash("Transaction PIN not set. Please set your PIN first.", "warning")
             return redirect(url_for("main.setup_pin_page"))
        return api_error(err, status, endpoint="main.transact_page")

    account = get_account_by_id(accounts_col, account_id)
    if not account:
        return api_error("Account not found.", 404, endpoint="main.transact_page")

    if not ensure_account_owner(account, get_session_user_id()):
        return api_error("Please login to continue.", 403, endpoint="auth.login_page")

    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return api_error("Invalid account ID.", 400, endpoint="main.transact_page")

    new_balance = float(account.get("balance", 0.0)) + float(amount)
    accounts_col.update_one({"_id": account_obj_id}, {"$set": {"balance": new_balance}})

    tx_doc, warnings = insert_transaction(account_obj_id, "deposit", float(amount))
    add_notification(
        notifications_col,
        account_obj_id,
        f"Deposit of ₹{float(amount):,.2f} received.",
        metadata={"type": "deposit"},
    )
    for warning in warnings:
        add_notification(notifications_col, account_obj_id, warning, level="warning")

    email_to = user.get("email") if user else ""
    if email_to:
        subject, email_message, template_name, context = build_deposit_email(
            get_display_name(user), float(amount), new_balance
        )
        email_html = render_template(template_name, **context)
        try:
            send_deposit_email(email_to, subject, email_message)
            add_notification(
                notifications_col,
                account_obj_id,
                f"Email notification sent: {subject}.",
                metadata={
                    "type": "deposit",
                    "email_subject": subject,
                    "email_to": email_to,
                    "email_preview_html": email_html,
                },
            )
        except Exception as exc:
            logger.warning("Email failed: %s", exc)

    logger.info("Deposit %s to %s", amount, account_id)
    if request.is_json:
        return jsonify(
            {
                "message": "Amount deposited successfully.",
                "balance": new_balance,
                "transaction_id": tx_doc["transaction_id"],
                "warnings": warnings,
            }
        )
    flash("Amount deposited successfully.", "success")
    return redirect(url_for("main.dashboard_page"))

@transactions_bp.route("/api/withdraw", methods=["POST"])
def withdraw():
    data = request.get_json(silent=True) or request.form
    account_id = get_session_account_id()
    if not account_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")
    amount = parse_amount(data.get("amount"))
    entered_pin = (data.get("pin") or "").strip()

    if amount is None or amount <= 0:
        return api_error("Please check your input.", 400, endpoint="main.transact_page", category="warning")
    if amount > 10000:
        return api_error("Please check your input.", 400, endpoint="main.transact_page", category="warning")

    user = users_col.find_one({"_id": ObjectId(get_session_user_id())})
    if not user:
        return api_error("User not found.", 404, endpoint="auth.login_page")

    ok, err, status = verify_transaction_pin(users_col, user, entered_pin)
    if not ok:
        if status == 403:
             if request.is_json:
                return jsonify({"error": err, "require_pin_setup": True, "setup_url": "/setup-pin"}), 403
             flash("Transaction PIN not set. Please set your PIN first.", "warning")
             return redirect(url_for("main.setup_pin_page"))
        return api_error(err, status, endpoint="main.transact_page")

    last_tx = session.get("last_tx_time", 0)
    now = time.time()
    if now - last_tx < 5:
        return api_error("Please wait before trying again.", 429, endpoint="main.transact_page", category="warning")
    session["last_tx_time"] = now

    account = get_account_by_id(accounts_col, account_id)
    if not account:
        return api_error("Account not found.", 404, endpoint="main.transact_page")

    if not ensure_account_owner(account, get_session_user_id()):
        return api_error("Please login to continue.", 403, endpoint="auth.login_page")

    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return api_error("Invalid account ID.", 400, endpoint="main.transact_page")

    current_balance = float(account.get("balance", 0.0))
    min_balance = float(account.get("min_balance", 0.0))
    if amount > current_balance:
        return api_error("Insufficient balance available.", 400, endpoint="main.transact_page")
    if current_balance - amount < min_balance:
        if account.get("account_type") == "current":
            return api_error("Current accounts must maintain a minimum balance of ₹5,000.", 400, endpoint="main.transact_page")
        return api_error(f"Minimum balance of ₹{min_balance:.0f} must be maintained.", 400, endpoint="main.transact_page")

    new_balance = current_balance - float(amount)
    accounts_col.update_one({"_id": account_obj_id}, {"$set": {"balance": new_balance}})

    tx_doc, warnings = insert_transaction(account_obj_id, "withdraw", float(amount))
    add_notification(
        notifications_col,
        account_obj_id,
        f"Withdrawal of ₹{float(amount):,.2f} processed.",
        metadata={"type": "withdraw"},
    )
    if new_balance < min_balance * 1.2:
        add_notification(
            notifications_col,
            account_obj_id,
            "Low balance alert: balance is close to minimum threshold.",
            level="warning",
        )
    for warning in warnings:
        add_notification(notifications_col, account_obj_id, warning, level="warning")

    logger.info("Withdraw %s from %s", amount, account_id)
    if request.is_json:
        return jsonify(
            {
                "message": "Amount withdrawn successfully.",
                "balance": new_balance,
                "transaction_id": tx_doc["transaction_id"],
                "warnings": warnings,
            }
        )
    flash("Amount withdrawn successfully.", "success")
    return redirect(url_for("main.dashboard_page"))

@transactions_bp.route("/api/transfer", methods=["POST"])
def transfer():
    data = request.get_json(silent=True) or request.form
    sender_account_id = get_session_account_id()
    if not sender_account_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")
    receiver_email = (data.get("receiver_email") or "").strip().lower()
    amount = parse_amount(data.get("amount"))
    entered_pin = (data.get("pin") or "").strip()

    if amount is None or amount <= 0:
        return api_error("Please check your input.", 400, endpoint="main.transfer_page", category="warning")
    if amount > 10000:
        return api_error("Please check your input.", 400, endpoint="main.transfer_page", category="warning")
    if not receiver_email:
        return api_error("Please check your input.", 400, endpoint="main.transfer_page", category="warning")

    user = users_col.find_one({"_id": ObjectId(get_session_user_id())})
    if not user:
        return api_error("User not found.", 404, endpoint="auth.login_page")

    ok, err, status = verify_transaction_pin(users_col, user, entered_pin)
    if not ok:
        if status == 403:
             if request.is_json:
                return jsonify({"error": err, "require_pin_setup": True, "setup_url": "/setup-pin"}), 403
             flash("Transaction PIN not set. Please set your PIN first.", "warning")
             return redirect(url_for("main.setup_pin_page"))
        return api_error(err, status, endpoint="main.transfer_page")

    last_tx = session.get("last_tx_time", 0)
    now = time.time()
    if now - last_tx < 5:
        return api_error("Please wait before trying again.", 429, endpoint="main.transfer_page", category="warning")
    session["last_tx_time"] = now

    receiver_account = accounts_col.find_one({"email": receiver_email})
    if not receiver_account:
        return api_error("The recipient account could not be found.", 404, endpoint="main.transfer_page")
    
    receiver_user = users_col.find_one({"_id": receiver_account.get("user_id")})
    receiver_account_id = str(receiver_account["_id"])
    if sender_account_id == receiver_account_id:
        return api_error("You cannot transfer funds to your own account.", 400, endpoint="main.transfer_page")

    sender_account = get_account_by_id(accounts_col, sender_account_id)
    if not sender_account:
        return api_error("Account not found.", 404, endpoint="main.transfer_page")
    if not ensure_account_owner(sender_account, get_session_user_id()):
        return api_error("Please login to continue.", 403, endpoint="auth.login_page")
    
    sender_user = users_col.find_one({"_id": ObjectId(get_session_user_id())})
    sender_name = get_display_name(sender_user)
    receiver_name = get_display_name(receiver_user)

    sender_balance = float(sender_account.get("balance", 0.0))
    sender_min_balance = float(sender_account.get("min_balance", 0.0))
    if amount > sender_balance:
        return api_error("Insufficient balance available.", 400, endpoint="main.transfer_page")
    if sender_balance - amount < sender_min_balance:
        if sender_account.get("account_type") == "current":
            return api_error("Current accounts must maintain a minimum balance of ₹5,000.", 400, endpoint="main.transfer_page")
        return api_error(f"Minimum balance of ₹{sender_min_balance:.0f} must be maintained.", 400, endpoint="main.transfer_page")

    sender_new_balance = sender_balance - float(amount)
    receiver_new_balance = float(receiver_account.get("balance", 0.0)) + float(amount)

    accounts_col.update_one({"_id": sender_account["_id"]}, {"$set": {"balance": sender_new_balance}})
    accounts_col.update_one({"_id": receiver_account["_id"]}, {"$set": {"balance": receiver_new_balance}})

    tx_doc, warnings = insert_transaction(
        sender_account["_id"],
        "transfer",
        float(amount),
        metadata={"to_account_id": str(receiver_account["_id"])},
    )
    insert_transaction(
        receiver_account["_id"],
        "transfer",
        float(amount),
        metadata={"from_account_id": str(sender_account["_id"])},
    )

    add_notification(notifications_col, sender_account["_id"], f"Transfer of ₹{float(amount):,.2f} sent to {receiver_name}.", metadata={"type": "transfer"})
    add_notification(notifications_col, receiver_account["_id"], f"Transfer of ₹{float(amount):,.2f} received from {sender_name}.", metadata={"type": "transfer"})
    
    if sender_new_balance < sender_min_balance * 1.2:
        add_notification(notifications_col, sender_account["_id"], "Low balance alert: balance is close to minimum threshold.", level="warning")
    for warning in warnings:
        add_notification(notifications_col, sender_account["_id"], warning, level="warning")

    # Email notifications (simplified)
    # ... (similar logic as in app.py)

    logger.info("Transfer %s from %s to %s", amount, sender_account_id, receiver_account_id)
    if request.is_json:
        return jsonify({"message": "Money transferred successfully.", "balance": sender_new_balance, "transaction_id": tx_doc["transaction_id"], "warnings": warnings})
    flash("Money transferred successfully.", "success")
    return redirect(url_for("main.dashboard_page"))

@transactions_bp.route("/api/transactions/<account_id>/export/csv", methods=["GET"])
def export_csv(account_id):
    account = get_account_by_id(accounts_col, account_id)
    if not account or not ensure_account_owner(account, get_session_user_id()):
        return jsonify({"error": "Unauthorized account access."}), 403

    # Support same filters as /api/transactions
    filters = {"account_id": ObjectId(account_id)}
    tx_type = (request.args.get("type") or "").strip().lower()
    min_amount = parse_amount(request.args.get("min_amount"))
    max_amount = parse_amount(request.args.get("max_amount"))
    start_date = parse_date(request.args.get("start_date"))
    end_date = parse_date(request.args.get("end_date"))
    q = (request.args.get("q") or "").strip()

    if tx_type:
        filters["type"] = tx_type
    if min_amount is not None or max_amount is not None:
        filters["amount"] = {}
        if min_amount is not None:
            filters["amount"]["$gte"] = float(min_amount)
        if max_amount is not None:
            filters["amount"]["$lte"] = float(max_amount)
    if start_date or end_date:
        filters["timestamp"] = {}
        if start_date:
            filters["timestamp"]["$gte"] = start_date
        if end_date:
            filters["timestamp"]["$lte"] = end_date
    if q:
        filters["$or"] = [
            {"transaction_id": {"$regex": q, "$options": "i"}},
            {"metadata": {"$regex": q, "$options": "i"}},
        ]

    sort_by = (request.args.get("sort_by") or "timestamp").strip()
    sort_order = (request.args.get("order") or "desc").strip().lower()
    sort_dir = -1 if sort_order == "desc" else 1
    sort_field = sort_by if sort_by in {"timestamp", "amount", "type"} else "timestamp"

    cursor = transactions_col.find(filters).sort(sort_field, sort_dir)
    account_doc = get_account_by_id(accounts_col, account_id)
    running_balance = float(account_doc.get("balance", 0.0)) if account_doc else 0.0

    rows = []
    # We iterate newest-first; keep running_balance as the CURRENT account balance
    for tx in cursor:
        amount = float(tx.get("amount", 0.0))
        tx_type = tx.get("type") or "-"
        metadata = tx.get("metadata", {})
        # determine whether this transaction was a credit (incoming) or debit (outgoing)
        direction = "debit"
        if tx_type == "deposit":
            direction = "credit"
        elif tx_type == "transfer":
            # if this account is the sender -> debit; if receiver -> credit
            if metadata.get("from_account_id") == str(account_id):
                direction = "debit"
            elif metadata.get("to_account_id") == str(account_id):
                direction = "credit"

        # balance_after is the balance at the time of this (newer) transaction
        balance_after = running_balance
        # when iterating newest-first, to move backwards in time:
        # - if this tx was a credit (incoming), previous balance = current - amount
        # - if this tx was a debit (outgoing), previous balance = current + amount
        if direction == "credit":
            running_balance = running_balance - amount
        else:
            running_balance = running_balance + amount

        rows.append(
            {
                "Date": format_ist(tx.get("timestamp") or tx["_id"].generation_time),
                "Type": tx_type,
                "Amount": format_currency(amount),
                "Status": "Completed",
                "Balance After": format_currency(balance_after),
            }
        )

    df = pd.DataFrame(rows)

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    export_date = ist_now().strftime("%Y_%m_%d")
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"statement_{export_date}.csv",
    )


@transactions_bp.route("/api/transactions/<account_id>/export/pdf", methods=["GET"])
def export_pdf(account_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    account = get_account_by_id(accounts_col, account_id)
    if not account or not ensure_account_owner(account, get_session_user_id()):
        return jsonify({"error": "Unauthorized account access."}), 403

    # Apply same filtering and sorting as transactions API
    filters = {"account_id": ObjectId(account_id)}
    tx_type = (request.args.get("type") or "").strip().lower()
    min_amount = parse_amount(request.args.get("min_amount"))
    max_amount = parse_amount(request.args.get("max_amount"))
    start_date = parse_date(request.args.get("start_date"))
    end_date = parse_date(request.args.get("end_date"))
    q = (request.args.get("q") or "").strip()

    if tx_type:
        filters["type"] = tx_type
    if min_amount is not None or max_amount is not None:
        filters["amount"] = {}
        if min_amount is not None:
            filters["amount"]["$gte"] = float(min_amount)
        if max_amount is not None:
            filters["amount"]["$lte"] = float(max_amount)
    if start_date or end_date:
        filters["timestamp"] = {}
        if start_date:
            filters["timestamp"]["$gte"] = start_date
        if end_date:
            filters["timestamp"]["$lte"] = end_date
    if q:
        filters["$or"] = [
            {"transaction_id": {"$regex": q, "$options": "i"}},
            {"metadata": {"$regex": q, "$options": "i"}},
        ]

    sort_by = (request.args.get("sort_by") or "timestamp").strip()
    sort_order = (request.args.get("order") or "desc").strip().lower()
    sort_dir = -1 if sort_order == "desc" else 1
    sort_field = sort_by if sort_by in {"timestamp", "amount", "type"} else "timestamp"

    cursor = transactions_col.find(filters).sort(sort_field, sort_dir)
    account_doc = get_account_by_id(accounts_col, account_id)
    account_name = account_doc.get("name") if account_doc else "Customer"
    account_email = account_doc.get("email") if account_doc else ""
    account_balance = float(account_doc.get("balance", 0.0)) if account_doc else 0.0
    export_label = format_ist(ist_now())
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, 770, "Simple Banking")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 754, "Account Statement")
    pdf.drawString(40, 740, f"Customer: {account_name}")
    if account_email:
        pdf.drawString(40, 726, f"Email: {account_email}")
    pdf.drawString(40, 712, f"Account ID: {account_id}")
    pdf.drawString(40, 698, f"Exported: {export_label}")

    totals = {"deposit": 0.0, "withdraw": 0.0, "transfer": 0.0}
    tx_list = list(cursor)
    running_balance = account_balance
    rows = []

    for tx in tx_list:
        amount = float(tx.get("amount", 0.0))
        tx_type = tx.get("type") or "-"
        metadata = tx.get("metadata", {})
        direction = "debit"
        if tx_type == "deposit":
            direction = "credit"
            totals["deposit"] += amount
        elif tx_type == "withdraw":
            totals["withdraw"] += amount
        elif tx_type == "transfer":
            totals["transfer"] += amount
            if metadata.get("from_account_id") == str(account_id):
                direction = "debit"
            elif metadata.get("to_account_id") == str(account_id):
                direction = "credit"

        balance_after = running_balance
        if direction == "credit":
            running_balance = running_balance - amount
        else:
            running_balance = running_balance + amount

        rows.append(
            {
                "date": format_ist(tx.get("timestamp") or tx["_id"].generation_time),
                "type": tx_type.title(),
                "amount": format_currency(amount),
                "status": "Completed",
                "balance": format_currency(balance_after),
            }
        )

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, 674, "Summary")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, 660, f"Total Deposits: {format_currency(totals['deposit'])}")
    pdf.drawString(240, 660, f"Total Withdrawals: {format_currency(totals['withdraw'])}")
    pdf.drawString(40, 646, f"Total Transfers: {format_currency(totals['transfer'])}")
    pdf.drawString(240, 646, f"Current Balance: {format_currency(account_balance)}")

    y = 620
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Date")
    pdf.drawString(190, y, "Type")
    pdf.drawString(260, y, "Amount")
    pdf.drawString(340, y, "Status")
    pdf.drawString(420, y, "Balance")
    y -= 16

    pdf.setFont("Helvetica", 9)
    for row in rows:
        if y < 60:
            pdf.showPage()
            y = 760
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(40, y, "Account Statement")
            y -= 20
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(40, y, "Date")
            pdf.drawString(190, y, "Type")
            pdf.drawString(260, y, "Amount")
            pdf.drawString(340, y, "Status")
            pdf.drawString(420, y, "Balance")
            y -= 16
            pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y, row["date"])
        pdf.drawString(190, y, row["type"])
        pdf.drawRightString(320, y, row["amount"])
        pdf.drawString(340, y, row["status"])
        pdf.drawRightString(520, y, row["balance"])
        y -= 14

    pdf.save()
    buffer.seek(0)

    export_date = ist_now().strftime("%Y_%m_%d")
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"statement_{export_date}.pdf",
    )


@transactions_bp.route("/api/transactions/<account_id>", methods=["GET"])
def get_transactions(account_id):
    account = get_account_by_id(accounts_col, account_id)
    if not account:
        return jsonify({"error": "Account not found."}), 404
    if not ensure_account_owner(account, get_session_user_id()):
        return jsonify({"error": "Unauthorized account access."}), 403

    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400

    filters = {"account_id": account_obj_id}
    tx_type = (request.args.get("type") or "").strip().lower()
    min_amount = parse_amount(request.args.get("min_amount"))
    max_amount = parse_amount(request.args.get("max_amount"))
    start_date = parse_date(request.args.get("start_date"))
    end_date = parse_date(request.args.get("end_date"))
    q = (request.args.get("q") or "").strip()
    sort_by = (request.args.get("sort_by") or "timestamp").strip()
    sort_order = (request.args.get("order") or "desc").strip().lower()

    if tx_type:
        filters["type"] = tx_type
    if min_amount is not None or max_amount is not None:
        filters["amount"] = {}
        if min_amount is not None:
            filters["amount"]["$gte"] = float(min_amount)
        if max_amount is not None:
            filters["amount"]["$lte"] = float(max_amount)
    if start_date or end_date:
        filters["timestamp"] = {}
        if start_date:
            filters["timestamp"]["$gte"] = start_date
        if end_date:
            filters["timestamp"]["$lte"] = end_date

    if q:
        filters["$or"] = [
            {"transaction_id": {"$regex": q, "$options": "i"}},
            {"metadata": {"$regex": q, "$options": "i"}},
        ]

    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return jsonify({"error": "Invalid pagination values."}), 400

    if page < 1: page = 1
    if limit < 1: limit = 10

    skip = (page - 1) * limit
    total = transactions_col.count_documents(filters)
    sort_dir = -1 if sort_order == "desc" else 1
    sort_field = sort_by if sort_by in {"timestamp", "amount", "type"} else "timestamp"
    cursor = transactions_col.find(filters).sort(sort_field, sort_dir).skip(skip).limit(limit)
    
    transactions = []
    for tx in cursor:
        timestamp = tx.get("timestamp") or tx["_id"].generation_time
        transactions.append({
            "_id": str(tx.get("_id")),
            "transaction_id": tx.get("transaction_id"),
            "type": tx.get("type"),
            "amount": float(tx.get("amount", 0.0)),
            "timestamp": timestamp.isoformat(),
            "formatted_time": format_ist(timestamp),
            "metadata": tx.get("metadata", {}),
        })

    total_pages = max(1, (total + limit - 1) // limit)

    # Compute Summary for filtered results (excluding pagination)
    summary_cursor = transactions_col.find(filters)
    total_deposits = 0.0
    total_withdrawals = 0.0
    for tx in summary_cursor:
        amt = float(tx.get("amount", 0.0))
        txtype = tx.get("type")
        if txtype == "deposit":
            total_deposits += amt
        elif txtype == "withdraw":
            total_withdrawals += amt
        elif txtype == "transfer":
            if tx.get("metadata", {}).get("from_account_id") == str(account_id):
                total_withdrawals += amt
            elif tx.get("metadata", {}).get("to_account_id") == str(account_id):
                total_deposits += amt

    return jsonify({
        "transactions": transactions,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "summary": {
            "total_transactions": total,
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "current_balance": float(account.get("balance", 0.0)),
        }
    })
