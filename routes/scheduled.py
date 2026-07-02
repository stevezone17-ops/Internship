from flask import Blueprint, request, jsonify, session
from bson import ObjectId
import os

from models.db import get_collections
from services.accounts import get_account_for_user
from services.transactions import record_transaction
from utils.helpers import (
    api_error,
    api_success,
    login_required,
    verify_transaction_pin,
)
from utils.time_utils import ist_now, format_ist
from utils.validators import parse_amount, parse_date
from utils.logging_config import setup_logging

logger = setup_logging()
scheduled_bp = Blueprint("scheduled", __name__)
cols = get_collections()
scheduled_transfers_col = cols["scheduled_transfers"]
accounts_col = cols["accounts"]
transactions_col = cols["transactions"]

def insert_transaction(account_id, tx_type, amount, metadata=None):
    tx_doc, tx_tuple, warnings = record_transaction(
        transactions_col, account_id, tx_type, amount, metadata
    )
    return tx_doc, warnings

@scheduled_bp.route("/api/scheduled-transfers", methods=["GET", "POST"])
@login_required
def scheduled_transfers_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    if request.method == "GET":
        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            return api_error("Invalid user ID.", 400, endpoint="main.transfer_page")
        cursor = scheduled_transfers_col.find({"user_id": user_obj_id}).sort("scheduled_at", -1)
        items = []
        for s in cursor:
            scheduled_at = s.get("scheduled_at")
            items.append({
                "id": str(s.get("_id")),
                "receiver_email": s.get("receiver_email"),
                "amount": float(s.get("amount", 0.0)),
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "scheduled_at_display": format_ist(scheduled_at) if scheduled_at else None,
                "status": s.get("status", "scheduled"),
            })
        return jsonify({"scheduled": items})

    # POST - create scheduled transfer
    data = request.get_json(silent=True) or {}
    receiver_email = (data.get("receiver_email") or request.form.get("receiver_email") or "").strip().lower()
    amount = parse_amount(data.get("amount") or request.form.get("amount"))
    scheduled_at_raw = (data.get("scheduled_at") or request.form.get("scheduled_at") or "").strip()
    entered_pin = (data.get("pin") or "").strip()

    if not receiver_email or amount is None or amount <= 0:
        return api_error("Please check your input.", 400, endpoint="main.transfer_page")

    users_col = cols["users"]
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        return api_error("User not found.", 404, endpoint="auth.login_page")

    ok, err, status = verify_transaction_pin(users_col, user, entered_pin)
    if not ok:
        return api_error(err, status, endpoint="main.transfer_page")

    try:
        scheduled_at = None
        if scheduled_at_raw:
            scheduled_at = parse_date(scheduled_at_raw)
            if not scheduled_at:
                return api_error("Invalid scheduled date.", 400, endpoint="main.transfer_page")
    except Exception:
        scheduled_at = None

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.transfer_page")

    doc = {
        "user_id": user_obj_id,
        "receiver_email": receiver_email,
        "amount": float(amount),
        "scheduled_at": scheduled_at or ist_now(),
        "created_at": ist_now(),
        "status": "scheduled",
    }
    result = scheduled_transfers_col.insert_one(doc)
    return api_success("Transfer scheduled.", payload={"id": str(result.inserted_id)}, endpoint="main.transfer_page")

@scheduled_bp.route("/api/scheduled-transfers/<transfer_id>", methods=["DELETE"])
@login_required
def scheduled_transfer_delete(transfer_id):
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")
    try:
        user_obj_id = ObjectId(user_id)
        t_obj = ObjectId(transfer_id)
    except Exception:
        return api_error("Invalid id.", 400, endpoint="main.transfer_page")
    res = scheduled_transfers_col.delete_one({"_id": t_obj, "user_id": user_obj_id})
    if res.deleted_count:
        return api_success("Scheduled transfer cancelled.", endpoint="main.transfer_page")
    return api_error("Unable to cancel scheduled transfer.", 400, endpoint="main.transfer_page")

@scheduled_bp.route("/api/scheduled-transfers/run", methods=["POST"])
def scheduled_transfers_run():
    # This endpoint processes due scheduled transfers. In production run via cron.
    scheduler_token = os.environ.get("SCHEDULED_TRANSFER_TOKEN", "").strip()
    if not scheduler_token:
        logger.warning("SCHEDULED_TRANSFER_TOKEN not set — rejecting request.")
        return jsonify({"error": "Scheduler not configured."}), 503

    provided_token = (request.headers.get("X-Scheduler-Token") or "").strip()
    if provided_token != scheduler_token:
        return jsonify({"error": "Forbidden."}), 403

    now = ist_now()
    due = list(scheduled_transfers_col.find({"scheduled_at": {"$lte": now}, "status": "scheduled"}))
    processed = 0
    for s in due:
        try:
            sender_user_id = s.get("user_id")
            receiver_email = s.get("receiver_email")
            amount = float(s.get("amount", 0))
            # load sender account
            account = get_account_for_user(accounts_col, str(sender_user_id))
            if not account:
                scheduled_transfers_col.update_one({"_id": s.get("_id")}, {"$set": {"status": "failed", "error": "no account"}})
                continue
            receiver_account = accounts_col.find_one({"email": receiver_email})
            if not receiver_account:
                scheduled_transfers_col.update_one({"_id": s.get("_id")}, {"$set": {"status": "failed", "error": "recipient not found"}})
                continue
            # check balance
            sender_balance = float(account.get("balance", 0.0))
            sender_min_balance = float(account.get("min_balance", 0.0))
            if amount > sender_balance or sender_balance - amount < sender_min_balance:
                scheduled_transfers_col.update_one({"_id": s.get("_id")}, {"$set": {"status": "failed", "error": "insufficient funds"}})
                continue
            # perform transfer
            accounts_col.update_one({"_id": account["_id"]}, {"$inc": {"balance": -float(amount)}})
            accounts_col.update_one({"_id": receiver_account["_id"]}, {"$inc": {"balance": float(amount)}})
            insert_transaction(account["_id"], "transfer", float(amount), metadata={"to_account_id": str(receiver_account["_id"])})
            insert_transaction(receiver_account["_id"], "transfer", float(amount), metadata={"from_account_id": str(account["_id"])})
            scheduled_transfers_col.update_one({"_id": s.get("_id")}, {"$set": {"status": "processed", "processed_at": ist_now()}})
            processed += 1
        except Exception as exc:
            logger.exception("Scheduled transfer processing failed: %s", exc)
            try:
                scheduled_transfers_col.update_one({"_id": s.get("_id")}, {"$set": {"status": "failed", "error": str(exc)}})
            except Exception:
                pass
    return jsonify({"processed": processed, "total": len(due)})
