from flask import Blueprint, request, jsonify, session
from bson import ObjectId

from models.db import get_collections
from utils.helpers import (
    api_error,
    api_success,
    login_required,
)
from utils.time_utils import ist_now, format_ist
from utils.logging_config import setup_logging

logger = setup_logging()
support_bp = Blueprint("support", __name__)
cols = get_collections()
users_col = cols["users"]
support_queries_col = cols["support_queries"]

@support_bp.route("/api/support", methods=["POST"])
@login_required
def support_api():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    priority = (data.get("priority") or "Low").strip().title()

    if not subject or not message:
        return api_error("Subject and message are required.", 400, endpoint="main.support_page")
    if priority not in {"Low", "Medium", "High"}:
        return api_error("Priority must be Low, Medium, or High.", 400, endpoint="main.support_page")

    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.support_page")

    user = users_col.find_one({"_id": user_obj_id})
    if not user:
        return api_error("User not found.", 404, endpoint="main.support_page")

    support_doc = {
        "user_id": user_obj_id,
        "email": user.get("email"),
        "subject": subject,
        "message": message,
        "priority": priority,
        "status": "Open",
        "created_at": ist_now(),
        "resolved_at": None,
        "admin_reply": None,
    }

    result = support_queries_col.insert_one(support_doc)
    return api_success(
        "Support request submitted successfully.",
        endpoint="main.support_page",
        payload={"query_id": str(result.inserted_id)},
    )

@support_bp.route("/api/support/history", methods=["GET"])
@login_required
def support_history_api():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user ID."}), 400

    cursor = (
        support_queries_col.find({"user_id": user_obj_id})
        .sort("created_at", -1)
        .limit(50)
    )

    queries = []
    for query in cursor:
        created_at = query.get("created_at") or query["_id"].generation_time
        resolved_at = query.get("resolved_at")
        queries.append(
            {
                "id": str(query.get("_id")),
                "subject": query.get("subject", ""),
                "priority": query.get("priority", "Low"),
                "status": query.get("status", "Open"),
                "created_at": created_at.isoformat(),
                "created_at_display": format_ist(created_at),
                "resolved_at": resolved_at.isoformat() if resolved_at else None,
                "resolved_at_display": format_ist(resolved_at),
                "admin_reply": query.get("admin_reply"),
            }
        )

    return jsonify({"queries": queries})
