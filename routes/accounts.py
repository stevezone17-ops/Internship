from flask import Blueprint, request, jsonify, session, redirect, url_for, flash
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
import time

from models.db import get_collections
from services.accounts import (
    ACCOUNT_RULES,
    create_account_for_user,
    ensure_account_owner,
    get_account_by_id,
    get_account_for_user,
)
from services.notifications import add_notification
from utils.helpers import (
    api_error,
    api_success,
    get_session_user_id,
    get_session_account_id,
    login_required,
    verify_transaction_pin,
    verify_user_password,
)
from utils.time_utils import ist_now, format_ist
from utils.logging_config import setup_logging

logger = setup_logging()
accounts_bp = Blueprint("accounts", __name__)
cols = get_collections()
accounts_col = cols["accounts"]
users_col = cols["users"]
notifications_col = cols["notifications"]
login_activity_col = cols["login_activity"]
transactions_col = cols["transactions"]

# Temporary in-memory cache for quick lookups in this process only.
account_cache = {}
ACCOUNT_CACHE_MAX = 500
# Temporary list cache of recent transactions by account id.
recent_transactions = {}

def account_to_dict(account):
    created_at = account.get("created_at") or account.get("_id").generation_time
    acct_type = account.get("account_type")
    acct_label = ACCOUNT_RULES.get(acct_type, {}).get("label") if acct_type else None
    return {
        "id": str(account["_id"]),
        "name": account["name"],
        "email": account["email"],
        "balance": float(account.get("balance", 0.0)),
        "account_type": acct_type,
        "account_type_label": acct_label,
        "min_balance": float(account.get("min_balance", 0.0)),
        "created_at": created_at.isoformat() if created_at else None,
        "created_at_display": format_ist(created_at) if created_at else None,
    }


@accounts_bp.route("/api/profile", methods=["GET"])
@login_required
def profile_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.profile_page")

    user = users_col.find_one({"_id": user_obj_id})
    if not user:
        return api_error("User not found.", 404, endpoint="main.profile_page")

    account = get_account_for_user(accounts_col, user_id)
    account_data = account_to_dict(account) if account else {}

    return jsonify({
        "name": user.get("name"),
        "email": user.get("email"),
        "account_type": account_data.get("account_type"),
        "account_type_label": account_data.get("account_type_label"),
        "balance": account_data.get("balance", 0.0),
        "member_since": account_data.get("created_at_display"),
        "created_at": account_data.get("created_at"),
    })

@accounts_bp.route("/api/profile/update", methods=["POST"])
@login_required
def profile_update_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.profile_page")

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    pin = (data.get("pin") or "").strip()

    updates = {}
    if name:
        updates["name"] = name
    if email:
        existing = users_col.find_one({"email": email, "_id": {"$ne": user_obj_id}})
        if existing:
            return api_error("That email is already in use.", 400, endpoint="main.profile_page")
        updates["email"] = email
    if pin:
        if not pin.isdigit() or len(pin) < 4 or len(pin) > 6:
            return api_error("PIN must be 4 to 6 digits.", 400, endpoint="main.profile_page")
        hashed_pin = generate_password_hash(pin)
        updates["pin"] = hashed_pin
        if len(pin) == 4:
            updates["transaction_pin"] = hashed_pin
            updates["pin_updated_at"] = ist_now()
    if not updates:
        return api_error("No updates provided.", 400, endpoint="main.profile_page")

    result = users_col.update_one({"_id": user_obj_id}, {"$set": updates})
    if result.matched_count == 0:
        return api_error("User not found.", 404, endpoint="main.profile_page")

    user = users_col.find_one({"_id": user_obj_id})
    if user:
        session["user_name"] = user.get("name") or user.get("email")
        session["user_email"] = user.get("email")
    return api_success(
        "Profile updated.",
        endpoint="main.profile_page",
        payload={"name": user.get("name"), "email": user.get("email")},
    )

@accounts_bp.route("/api/create_account", methods=["POST"])
@login_required
def create_account():
    from utils.validators import parse_amount
    from services.transactions import record_transaction

    data = request.get_json(silent=True)
    name = ((data or {}).get("name") or request.form.get("name") or "").strip()
    email = ((data or {}).get("email") or request.form.get("email") or "").strip().lower()
    initial_deposit = parse_amount((data or {}).get("initial_deposit") or request.form.get("initial_deposit"))
    account_type = ((data or {}).get("account_type") or request.form.get("account_type") or "").strip().lower()

    if not name or not email:
        return api_error("Please check your input.", 400, endpoint="main.create_page", category="warning")
    if initial_deposit is None or initial_deposit < 0:
        return api_error("Please check your input.", 400, endpoint="main.create_page", category="warning")

    user_id = get_session_user_id()
    account_doc, error = create_account_for_user(
        accounts_col, user_id, name, email, account_type, float(initial_deposit)
    )
    if error:
        return api_error(error, 400, endpoint="main.create_page")

    account_id = account_doc["_id"]
    account_cache[str(account_id)] = account_doc
    if len(account_cache) > ACCOUNT_CACHE_MAX:
        oldest_key = next(iter(account_cache))
        account_cache.pop(oldest_key, None)

    if initial_deposit > 0:
        tx_doc, tx_tuple, warnings = record_transaction(
            transactions_col, account_id, "deposit", float(initial_deposit)
        )
        recent_transactions.setdefault(str(account_id), []).append(tx_tuple)
        
        add_notification(
            notifications_col,
            account_id,
            f"Deposit of ₹{float(initial_deposit):,.2f} received.",
            metadata={"type": "deposit"},
        )
        for warning in warnings:
            add_notification(notifications_col, account_id, warning, level="warning")

    session["account_id"] = str(account_id)
    logger.info("Account created: %s", session["account_id"])

    if request.is_json:
        return jsonify({"account_id": str(account_id), "balance": float(initial_deposit)})
    flash("Account created successfully.", "success")
    return redirect(url_for("main.dashboard_page"))

@accounts_bp.route("/api/account/<account_id>", methods=["GET"])
@login_required
def get_account(account_id):
    account = get_account_by_id(accounts_col, account_id)
    if not account:
        return jsonify({"error": "Account not found."}), 404
    if not ensure_account_owner(account, get_session_user_id()):
        return jsonify({"error": "Unauthorized account access."}), 403
    
    if not account.get("created_at"):
        try:
            accounts_col.update_one({"_id": account["_id"]}, {"$set": {"created_at": ist_now()}})
            account = get_account_by_id(accounts_col, account_id)
        except Exception as exc:
            logger.warning("Failed to set created_at for account %s: %s", account_id, exc)
    return jsonify(account_to_dict(account))

@accounts_bp.route("/api/account/<account_id>", methods=["DELETE"])
@login_required
def delete_account(account_id):
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        return jsonify({"error": "Invalid account ID."}), 400

    account = accounts_col.find_one({"_id": account_obj_id})
    if not account:
        return jsonify({"error": "Account not found."}), 404
    if not ensure_account_owner(account, get_session_user_id()):
        return jsonify({"error": "Unauthorized account access."}), 403

    accounts_col.delete_one({"_id": account_obj_id})
    transactions_col.delete_many({"account_id": account_obj_id})
    notifications_col.delete_many({"account_id": account_obj_id})
    cols["login_activity"].delete_many({"account_id": account_obj_id})
    cols["scheduled_transfers"].delete_many({"user_id": account.get("user_id")})
    account_cache.pop(str(account_obj_id), None)
    recent_transactions.pop(str(account_obj_id), None)

    if session.get("account_id") == str(account_obj_id):
        session.pop("account_id", None)

    return jsonify({"message": "Account deleted."})

@accounts_bp.route("/api/set-pin", methods=["POST"])
@login_required
def set_pin_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.set_pin_page")

    data = request.get_json(silent=True) or {}
    pin = (data.get("pin") or "").strip()
    if not pin.isdigit() or len(pin) != 4:
        return api_error("PIN must be exactly 4 digits.", 400, endpoint="main.set_pin_page")

    hashed_pin = generate_password_hash(pin)
    result = users_col.update_one(
        {"_id": user_obj_id},
        {"$set": {"pin": hashed_pin, "transaction_pin": hashed_pin, "pin_updated_at": ist_now()}},
    )
    if result.matched_count == 0:
        return api_error("User not found.", 404, endpoint="main.set_pin_page")

    return api_success("Transaction PIN updated successfully.", endpoint="main.dashboard_page")

@accounts_bp.route("/api/update-pin", methods=["POST"])
@login_required
def update_pin_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.profile_page")

    data = request.get_json(silent=True) or {}
    current_pin = (data.get("current_pin") or "").strip()
    new_pin = (data.get("new_pin") or "").strip()
    confirm_pin = (data.get("confirm_pin") or "").strip()

    if not current_pin or not new_pin or not confirm_pin:
        return api_error("Please check your input.", 400, endpoint="main.profile_page", category="warning")
    if new_pin != confirm_pin:
        return api_error("New PIN entries do not match.", 400, endpoint="main.profile_page")
    if not new_pin.isdigit() or len(new_pin) != 4:
        return api_error("PIN must be exactly 4 digits.", 400, endpoint="main.profile_page")
    if current_pin == new_pin:
        return api_error("New PIN must be different from current PIN.", 400, endpoint="main.profile_page")

    last_change = session.get("pin_change_ts", 0)
    now_ts = time.time()
    if now_ts - last_change < 60:
        return api_error("Please wait before updating your PIN again.", 429, endpoint="main.profile_page", category="warning")

    user = users_col.find_one({"_id": user_obj_id})
    if not user:
        return api_error("User not found.", 404, endpoint="main.profile_page")
    stored_pin = user.get("transaction_pin") or user.get("pin")
    if not stored_pin:
        return api_error("PIN not set. Use Set PIN first.", 400, endpoint="main.set_pin_page")
    if not check_password_hash(stored_pin, current_pin):
        return api_error("The transaction PIN entered is incorrect.", 400, endpoint="main.profile_page")

    hashed_pin = generate_password_hash(new_pin)
    users_col.update_one(
        {"_id": user_obj_id},
        {"$set": {"pin": hashed_pin, "transaction_pin": hashed_pin, "pin_updated_at": ist_now()}},
    )
    session["pin_change_ts"] = now_ts

    return api_success("Transaction PIN updated successfully.", endpoint="main.profile_page")

@accounts_bp.route("/api/change-pin", methods=["POST"])
@login_required
def change_pin_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.change_pin_page")

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    new_pin = (data.get("new_pin") or "").strip()

    if not email or not password or not new_pin:
        return api_error("Please check your input.", 400, endpoint="main.change_pin_page", category="warning")
    if not new_pin.isdigit() or len(new_pin) != 4:
        return api_error("PIN must be exactly 4 digits.", 400, endpoint="main.change_pin_page")

    user = users_col.find_one({"_id": user_obj_id})
    if not user:
        return api_error("User not found.", 404, endpoint="main.change_pin_page")

    session_email = (user.get("email") or session.get("user_email") or "").strip().lower()
    if email != session_email:
        return api_error("Email does not match the signed-in account.", 400, endpoint="main.change_pin_page")

    if not verify_user_password(user, password):
        return api_error("The account password entered is incorrect.", 400, endpoint="main.change_pin_page")

    hashed_pin = generate_password_hash(new_pin)
    result = users_col.update_one(
        {"_id": user_obj_id},
        {
            "$set": {
                "transaction_pin": hashed_pin,
                "pin": hashed_pin,
                "pin_updated_at": ist_now(),
            }
        },
    )
    if result.matched_count == 0:
        return api_error("User not found.", 404, endpoint="main.change_pin_page")

    account_id = get_session_account_id()
    if account_id:
        try:
            account_obj_id = ObjectId(account_id)
        except Exception:
            account_obj_id = None
        if account_obj_id:
            add_notification(
                notifications_col,
                account_obj_id,
                "Transaction PIN changed successfully.",
                metadata={"type": "security"},
            )

    return api_success("Transaction PIN updated successfully.", endpoint="main.change_pin_page")

@accounts_bp.route('/api/change-password', methods=['POST'])
@login_required
def change_password_api():
    user_id = session.get('user_id')
    if not user_id:
        return api_error('Please login to continue.', 401, endpoint='auth.login_page')
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error('Invalid user ID.', 400, endpoint='main.security_page')

    data = request.get_json(silent=True) or {}
    current = (data.get('current') or request.form.get('current') or '').strip()
    new = (data.get('new') or request.form.get('new') or '').strip()
    confirm = (data.get('confirm') or request.form.get('confirm') or '').strip()

    if not current or not new or not confirm:
        return api_error('All fields are required.', 400, endpoint='main.security_page', category='warning')
    if new != confirm:
        return api_error('New passwords do not match.', 400, endpoint='main.security_page')
    if len(new) < 8:
        return api_error('New password must be at least 8 characters long.', 400, endpoint='main.security_page')

    user = users_col.find_one({'_id': user_obj_id})
    if not user:
        return api_error('User not found.', 404, endpoint='main.security_page')

    if not verify_user_password(user, current):
        return api_error('Current password is incorrect.', 400, endpoint='main.security_page')

    hashed = generate_password_hash(new)
    users_col.update_one({'_id': user_obj_id}, {'$set': {'password_hash': hashed}, '$unset': {'password': ''}})

    try:
        account = get_account_for_user(accounts_col, user_id)
        if account:
            add_notification(notifications_col, account['_id'], 'Account password changed successfully.', metadata={'type': 'security'})
    except Exception as exc:
        logger.warning("Failed to send password change notification: %s", exc)

    session.clear()
    if request.is_json:
        return jsonify({'message': 'Password changed. Please login again.'})
    flash('Password changed successfully. Please login again.', 'success')
    return redirect(url_for('auth.login_page'))

@accounts_bp.route("/api/login-activity", methods=["GET"])
@login_required
def login_activity_api():
    user_id = session.get("user_id")
    if not user_id:
        return api_error("Please login to continue.", 401, endpoint="auth.login_page")
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return api_error("Invalid user ID.", 400, endpoint="main.profile_page")

    cursor = login_activity_col.find({"user_id": user_obj_id}).sort("created_at", -1).limit(10)
    results = []
    for item in cursor:
        created_at = item.get("created_at") or item.get("_id").generation_time
        results.append(
            {
                "id": str(item.get("_id")),
                "ip": item.get("ip"),
                "user_agent": item.get("user_agent"),
                "created_at": created_at.isoformat() if created_at else None,
                "created_at_display": format_ist(created_at),
            }
        )
    return jsonify({"logins": results})
