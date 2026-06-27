from bson import ObjectId

from utils.time_utils import format_ist, ist_now


def add_notification(notifications_col, account_id, message, level="info", metadata=None):
    """Insert a notification document with read/unread tracking."""
    notifications_col.insert_one(
        {
            "account_id": account_id,
            "message": message,
            "level": level,
            "read": False,
            "metadata": metadata or {},
            "created_at": ist_now(),
        }
    )


def get_notifications(notifications_col, account_id, page=1, limit=10):
    """Return paginated notifications for an account, newest first."""
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    skip = (page - 1) * limit
    cursor = (
        notifications_col.find({"account_id": account_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    results = []
    for n in cursor:
        created_at = n.get("created_at")
        results.append(
            {
                "id": str(n["_id"]),
                "message": n.get("message"),
                "level": n.get("level", "info"),
                "read": bool(n.get("read", False)),
                "metadata": n.get("metadata", {}),
                "created_at": created_at.isoformat() if created_at else None,
                "created_at_display": format_ist(created_at),
            }
        )
    return results


def get_unread_count(notifications_col, account_id):
    """Return the number of unread notifications for an account."""
    return notifications_col.count_documents({"account_id": account_id, "read": False})


def mark_notification_read(notifications_col, notification_id, account_id):
    """Mark a single notification as read. Returns True on success."""
    try:
        obj_id = ObjectId(notification_id)
    except Exception:
        return False
    result = notifications_col.update_one(
        {"_id": obj_id, "account_id": account_id},
        {"$set": {"read": True}},
    )
    return result.modified_count > 0


def mark_all_read(notifications_col, account_id):
    """Mark all notifications for the account as read."""
    result = notifications_col.update_many(
        {"account_id": account_id, "read": False},
        {"$set": {"read": True}},
    )
    return result.modified_count
