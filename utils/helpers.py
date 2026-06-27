import time
import os
from datetime import timedelta
from functools import wraps
from flask import flash, jsonify, redirect, request, session, url_for
from bson import ObjectId
import pytz
from utils.time_utils import IST, ist_now, format_ist

def make_aware(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        return pytz.utc.localize(dt).astimezone(IST)
    return dt

def format_currency(amount):
    return f"₹{amount:,.2f}"

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please login first."}), 401
            return redirect(url_for("auth.login_page"))
        return view_func(*args, **kwargs)
    return wrapper

def api_error(message, status_code=400, endpoint=None, category="danger"):
    if request.is_json:
        return jsonify({"error": message}), status_code
    flash(message, category)
    if endpoint:
        if endpoint.startswith("/"):
            return redirect(endpoint)
        try:
            return redirect(url_for(endpoint))
        except Exception:
            pass
    if request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("main.home_page"))

def api_success(message, endpoint=None, payload=None, category="success"):
    payload = payload or {}
    if request.is_json:
        body = {"message": message}
        body.update(payload)
        return jsonify(body)
    flash(message, category)
    if endpoint:
        if endpoint.startswith("/"):
            return redirect(endpoint)
        try:
            return redirect(url_for(endpoint))
        except Exception:
            pass
    if request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("main.home_page"))

def get_session_user_id():
    return session.get("user_id")

def get_display_name(user):
    if not user:
        return "Unknown User"
    return (
        user.get("full_name")
        or user.get("name")
        or user.get("email")
        or "Unknown User"
    )

def verify_user_password(user, password):
    from werkzeug.security import check_password_hash
    if not user or not password:
        return False
    password_hash = user.get("password_hash")
    if not password_hash:
        return False
    try:
        return check_password_hash(password_hash, password)
    except Exception:
        return False

def is_admin_user(user):
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    return bool(admin_email and (user.get("email") or "").strip().lower() == admin_email)

PIN_WINDOW_SECONDS = 600
PIN_LOCK_SECONDS = 300

def _update_failed_pin(users_col, user_id, last_failed_at, attempts):
    now = ist_now()
    last_failed_at = make_aware(last_failed_at)
    if not last_failed_at or (now - last_failed_at).total_seconds() > PIN_WINDOW_SECONDS:
        attempts = 1
    else:
        attempts += 1

    updates = {"failed_pin_attempts": attempts, "last_pin_failed_at": now}
    if attempts >= 5:
        updates["pin_lock_until"] = now + timedelta(seconds=PIN_LOCK_SECONDS)
    users_col.update_one({"_id": user_id}, {"$set": updates})
    return updates.get("pin_lock_until")

def _is_pin_locked(user):
    if not user:
        return False
    locked_until = make_aware(user.get("pin_lock_until"))
    return bool(locked_until and locked_until > ist_now())

def verify_transaction_pin(users_col, user, entered_pin):
    from werkzeug.security import check_password_hash
    if _is_pin_locked(user):
        return False, "Too many transaction PIN attempts. Try again later.", 429

    stored_pin = user.get("transaction_pin") or user.get("pin")
    if not stored_pin:
        return False, "PIN not set", 403

    if not entered_pin:
        return False, "Please check your input.", 400

    if not check_password_hash(stored_pin, entered_pin):
        _update_failed_pin(
            users_col,
            user["_id"],
            user.get("last_pin_failed_at"),
            user.get("failed_pin_attempts", 0),
        )
        return False, "The transaction PIN entered is incorrect.", 400

    # Success - reset attempts
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_pin_attempts": 0}, "$unset": {"last_pin_failed_at": "", "pin_lock_until": ""}},
    )
    return True, None, None
