from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template
from bson import ObjectId
from functools import wraps
import os

from models.db import get_collections
from services.notifications import add_notification
from utils.helpers import (
    api_error,
    api_success,
    is_admin_user,
)
from utils.time_utils import ist_now, format_ist
from utils.logging_config import setup_logging

logger = setup_logging()
admin_bp = Blueprint("admin", __name__)
cols = get_collections()
accounts_col = cols["accounts"]
users_col = cols["users"]
transactions_col = cols["transactions"]
support_queries_col = cols["support_queries"]
notifications_col = cols["notifications"]


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("auth.login_page"))
        user = None
        try:
            user = users_col.find_one({"_id": ObjectId(user_id)})
        except Exception as exc:
            logger.warning("Failed to fetch user for admin check: %s", exc)
        if not is_admin_user(user):
            flash("You do not have access to the admin dashboard.", "danger")
            return redirect(url_for("main.dashboard_page"))
        session["is_admin"] = True
        return view_func(*args, **kwargs)
    return wrapper

@admin_bp.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")

@admin_bp.route("/test-db")
@admin_required
def test_db():
    if os.environ.get("FLASK_ENV") != "testing":
        return jsonify({"status": "error", "message": "Only available in testing environment."}), 403
    sample = {"message": "db_check", "created_at": ist_now()}
    result = notifications_col.insert_one(sample)
    inserted = notifications_col.find_one({"_id": result.inserted_id})
    if not inserted:
        return jsonify({"status": "error", "message": "Insert failed."}), 500
    return jsonify({"status": "ok", "id": str(result.inserted_id)})

@admin_bp.route("/api/admin/overview", methods=["GET"])
@admin_required
def admin_overview_api():
    totals = {
        "users": users_col.count_documents({}),
        "accounts": accounts_col.count_documents({}),
        "transactions": transactions_col.count_documents({}),
        "support_open": support_queries_col.count_documents({"status": "Open"}),
        "support_resolved": support_queries_col.count_documents({"status": "Resolved"}),
    }
    return jsonify({"totals": totals})

@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_users_api():
    cursor = users_col.find({}).sort("created_at", -1).limit(25)
    users = []
    for user in cursor:
        created_at = user.get("created_at") or user.get("_id").generation_time
        users.append({
            "id": str(user.get("_id")),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role", "user"),
            "verified": bool(user.get("verified")),
            "created_at_display": format_ist(created_at),
        })
    return jsonify({"users": users})

@admin_bp.route("/api/admin/transactions", methods=["GET"])
@admin_required
def admin_transactions_api():
    cursor = transactions_col.find({}).sort("timestamp", -1).limit(25)
    items = []
    for tx in cursor:
        timestamp = tx.get("timestamp") or tx.get("_id").generation_time
        items.append({
            "id": str(tx.get("_id")),
            "transaction_id": tx.get("transaction_id"),
            "type": tx.get("type"),
            "amount": float(tx.get("amount", 0.0)),
            "created_at_display": format_ist(timestamp),
        })
    return jsonify({"transactions": items})

@admin_bp.route("/api/admin/support", methods=["GET"])
@admin_required
def admin_support_api():
    cursor = support_queries_col.find({}).sort("created_at", -1).limit(25)
    items = []
    for query in cursor:
        created_at = query.get("created_at") or query.get("_id").generation_time
        items.append({
            "id": str(query.get("_id")),
            "subject": query.get("subject", ""),
            "email": query.get("email", ""),
            "priority": query.get("priority", "Low"),
            "status": query.get("status", "Open"),
            "created_at_display": format_ist(created_at),
            "admin_reply": query.get("admin_reply"),
        })
    return jsonify({"support": items})

@admin_bp.route("/api/admin/support/<query_id>/reply", methods=["POST"])
@admin_required
def admin_support_reply_api(query_id):
    data = request.get_json(silent=True) or {}
    reply = (data.get("reply") or request.form.get("reply") or "").strip()
    if not reply:
        return api_error("Reply cannot be empty.", 400, endpoint="admin.admin_page")
    try:
        query_obj_id = ObjectId(query_id)
    except Exception:
        return api_error("Invalid support query ID.", 400, endpoint="admin.admin_page")

    query = support_queries_col.find_one({"_id": query_obj_id})
    if not query:
        return api_error("Support query not found.", 404, endpoint="admin.admin_page")

    support_queries_col.update_one(
        {"_id": query_obj_id},
        {
            "$set": {
                "admin_reply": reply,
                "status": "Resolved",
                "resolved_at": ist_now(),
            }
        },
    )

    try:
        user_id = query.get("user_id")
        if user_id:
            account = accounts_col.find_one({"user_id": user_id})
            if account:
                add_notification(
                    notifications_col,
                    account["_id"],
                    f"Support response added for: {query.get('subject', '')}",
                    metadata={"type": "support", "support_query_id": str(query_obj_id)},
                )
    except Exception:
        pass

    return api_success("Reply posted.", endpoint="admin.admin_page")
