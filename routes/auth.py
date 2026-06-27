import time
from datetime import timedelta
from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template
from werkzeug.security import generate_password_hash
from bson import ObjectId

from models.db import get_collections
from services.accounts import (
    authenticate_user,
    create_reset_token,
    mark_user_verified,
    reset_password,
    get_account_for_user,
)
from utils.helpers import (
    api_error,
    api_success,
    make_aware,
    get_session_user_id,
    is_admin_user,
    verify_user_password,
)
from utils.time_utils import ist_now
from utils.logging_config import setup_logging

logger = setup_logging()
auth_bp = Blueprint("auth", __name__)
cols = get_collections()
users_col = cols["users"]
login_activity_col = cols["login_activity"]
accounts_col = cols["accounts"]

LOGIN_WINDOW_SECONDS = 600
LOGIN_LOCK_SECONDS = 300


def _update_failed_login(user_id, last_failed_at, attempts):
    now = ist_now()
    last_failed_at = make_aware(last_failed_at)
    if not last_failed_at or (now - last_failed_at).total_seconds() > LOGIN_WINDOW_SECONDS:
        attempts = 1
    else:
        attempts += 1

    updates = {"failed_attempts": attempts, "last_failed_at": now}
    if attempts >= 5:
        updates["lock_until"] = now + timedelta(seconds=LOGIN_LOCK_SECONDS)
    users_col.update_one({"_id": user_id}, {"$set": updates})
    return updates.get("lock_until")

@auth_bp.route("/signup")
def signup_page():
    return render_template("signup.html")

@auth_bp.route("/login")
def login_page():
    return render_template("login.html")

@auth_bp.route("/forgot")
def forgot_page():
    return render_template("forgot_password.html")

@auth_bp.route("/reset/<token>")
def reset_page(token):
    return render_template("reset_password.html", token=token)

@auth_bp.route("/verify/<token>")
def verify_page(token):
    user, error = mark_user_verified(users_col, token)
    if error:
        return render_template("verify.html", success=False, message=error)
    return render_template("verify.html", success=True, message="Email verified. You can login now.")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.home_page"))

@auth_bp.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True)
    name = ((data or {}).get("name") or request.form.get("name") or "").strip()
    email = ((data or {}).get("email") or request.form.get("email") or "").strip().lower()
    password = ((data or {}).get("password") or request.form.get("password") or "").strip()
    pin = ((data or {}).get("pin") or request.form.get("pin") or "").strip()

    if not name or not email or not password:
        return api_error("Please check your input.", 400, endpoint="auth.signup_page", category="warning")
    if not pin or not pin.isdigit() or len(pin) < 4 or len(pin) > 6:
        return api_error("Please check your input.", 400, endpoint="auth.signup_page", category="warning")

    existing = users_col.find_one({"email": email})
    if existing:
        return api_error("An account with that email already exists.", 400, endpoint="auth.signup_page")

    hashed_pin = generate_password_hash(pin)
    hashed_password = generate_password_hash(password)
    result = users_col.insert_one(
        {
            "name": name,
            "email": email,
            "password_hash": hashed_password,
            "pin": hashed_pin,
            "transaction_pin": hashed_pin,
            "pin_updated_at": ist_now(),
            "created_at": ist_now(),
        }
    )

    logger.info("User signup: %s", email)
    if request.is_json:
        return jsonify({"message": "Signup successful.", "user_id": str(result.inserted_id)})
    flash("Registration successful. Please sign in to continue.", "success")
    return redirect(url_for("auth.login_page"))

@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    email = ((data or {}).get("email") or request.form.get("email") or "").strip().lower()
    password = ((data or {}).get("password") or request.form.get("password") or "").strip()

    if not email or not password:
        return api_error("Please check your input.", 400, endpoint="auth.login_page", category="warning")

    user = users_col.find_one({"email": email})
    lock_until = make_aware(user.get("lock_until")) if user else None
    if user and lock_until and lock_until > ist_now():
        return api_error("Too many login attempts. Try again later.", 429, endpoint="auth.login_page")

    if not user or not verify_user_password(user, password):
        if user:
            _update_failed_login(user["_id"], user.get("last_failed_at"), user.get("failed_attempts", 0))
        return api_error("Invalid email or password.", 401, endpoint="auth.login_page")

    session.clear()
    session["user_id"] = str(user["_id"])
    session["user_name"] = user.get("name") or user.get("email")
    session["user_email"] = user.get("email")
    session["is_admin"] = is_admin_user(user)
    session["login_at"] = time.time()
    session["last_activity"] = time.time()
    session.permanent = True

    account = get_account_for_user(accounts_col, session["user_id"])
    if account:
        session["account_id"] = str(account["_id"])

    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_attempts": 0}, "$unset": {"last_failed_at": "", "lock_until": ""}},
    )

    try:
        login_activity_col.insert_one({
            "user_id": user["_id"],
            "account_id": account["_id"] if account else None,
            "ip": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
            "created_at": ist_now(),
        })
    except Exception:
        logger.warning("Failed to record login activity for %s", email)

    logger.info("User login: %s", email)
    if request.is_json:
        return jsonify({"message": "Login successful.", "account_id": session.get("account_id")})
    flash("Login successful.", "success")
    return redirect(url_for("main.dashboard_page"))

@auth_bp.route("/api/password/forgot", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return api_error("Please check your input.", 400, endpoint="auth.forgot_page", category="warning")

    user, token = create_reset_token(users_col, email)
    if user and token:
        reset_link = url_for("auth.reset_page", token=token, _external=True)
        logger.info("Password reset link for %s: %s", email, reset_link)
        return jsonify({"message": "Reset link generated.", "reset_link": reset_link})

    return api_success("If the email exists, a reset link was generated.", endpoint="auth.forgot_page")

@auth_bp.route("/api/password/reset", methods=["POST"])
def reset_password_api():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    new_password = (data.get("password") or "").strip()

    if not token or not new_password:
        return api_error("Please check your input.", 400, endpoint="auth.reset_page")

    user, error = reset_password(users_col, token, new_password)
    if error:
        return api_error(error, 400, endpoint="auth.reset_page")

    logger.info("Password reset for %s", user.get("email"))
    return api_success("Password updated.", endpoint="auth.login_page")
