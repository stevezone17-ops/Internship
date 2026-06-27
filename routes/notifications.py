from flask import Blueprint, request, jsonify, session
from bson import ObjectId

from models.db import get_collections
from services.notifications import (
    get_notifications,
    get_unread_count,
    mark_notification_read,
    mark_all_read,
)
from utils.helpers import login_required, get_display_name
from utils.logging_config import setup_logging

logger = setup_logging()
notifications_bp = Blueprint("notifications", __name__)
cols = get_collections()
notifications_col = cols["notifications"]
accounts_col = cols["accounts"]
users_col = cols["users"]

def get_session_account_id():
    from services.accounts import get_account_for_user
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

@notifications_bp.route("/api/notifications", methods=["GET"])
@login_required
def notifications():
    account_id = get_session_account_id()
    if not account_id:
        return jsonify({"notifications": []})
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400

    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 5))
    except ValueError:
        return jsonify({"error": "Invalid pagination values."}), 400

    total = notifications_col.count_documents({"account_id": account_obj_id})
    notifications_list = get_notifications(
        notifications_col, account_obj_id, page=page, limit=limit
    )
    total_pages = max(1, (total + limit - 1) // limit)
    return jsonify(
        {
            "notifications": notifications_list,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    )

@notifications_bp.route("/api/notifications/<notification_id>/mark-read", methods=["POST"])
@login_required
def mark_notification_read_api(notification_id):
    account_id = get_session_account_id()
    if not account_id:
        return jsonify({"error": "Not logged in"}), 401
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400
    ok = mark_notification_read(notifications_col, notification_id, account_obj_id)
    if ok:
        return jsonify({"message": "Notification marked as read."})
    return jsonify({"error": "Notification not found."}), 404

@notifications_bp.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read_api():
    account_id = get_session_account_id()
    if not account_id:
        return jsonify({"error": "Not logged in"}), 401
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400
    count = mark_all_read(notifications_col, account_obj_id)
    return jsonify({"message": f"Marked {count} notification(s) as read.", "count": count})

@notifications_bp.route("/api/notifications/unread-count", methods=["GET"])
@login_required
def unread_count_api():
    account_id = get_session_account_id()
    if not account_id:
        return jsonify({"count": 0})
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"count": 0})
    count = get_unread_count(notifications_col, account_obj_id)
    return jsonify({"count": count})

@notifications_bp.route("/api/notifications/migrate", methods=["POST"])
@login_required
def migrate_notifications():
    """Replace MongoDB ObjectIds in old notification messages with real user names."""
    import re

    account_id = get_session_account_id()
    if not account_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400

    oid_pattern = re.compile(r"[0-9a-f]{24}")

    cursor = notifications_col.find({"account_id": account_obj_id})
    fixed_count = 0

    for notification in cursor:
        msg = notification.get("message", "")
        match = oid_pattern.search(msg)
        if not match:
            continue

        raw_id = match.group(0)
        display_name = None

        try:
            target_account = accounts_col.find_one({"_id": ObjectId(raw_id)})
            if target_account:
                target_user = users_col.find_one({"_id": target_account.get("user_id")})
                display_name = get_display_name(target_user)
            else:
                target_user = users_col.find_one({"_id": ObjectId(raw_id)})
                display_name = get_display_name(target_user)
        except Exception:
            display_name = None

        if display_name and display_name != "Unknown User":
            new_msg = msg.replace(raw_id, display_name)
            notifications_col.update_one(
                {"_id": notification["_id"]},
                {"$set": {"message": new_msg}},
            )
            fixed_count += 1

    return jsonify({"message": f"Migrated {fixed_count} notification(s).", "fixed": fixed_count})
