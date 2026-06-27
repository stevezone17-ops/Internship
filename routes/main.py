from flask import Blueprint, render_template, session, redirect, url_for, flash
from bson import ObjectId
from models.db import get_collections
from services.accounts import ACCOUNT_RULES, get_account_for_user
from utils.helpers import login_required, get_session_user_id, format_ist

main_bp = Blueprint("main", __name__)
cols = get_collections()
accounts_col = cols["accounts"]
users_col = cols["users"]
support_queries_col = cols["support_queries"]

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

def account_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not get_session_account_id():
            return redirect(url_for("main.create_page"))
        return view_func(*args, **kwargs)
    return wrapper

@main_bp.route("/")
def home_page():
    return render_template("index.html")

@main_bp.route("/create")
@login_required
def create_page():
    return render_template("create_account.html", account_types=ACCOUNT_RULES)

@main_bp.route("/dashboard")
@login_required
@account_required
def dashboard_page():
    account_id = get_session_account_id()
    return render_template("dashboard.html", account_id=account_id)

@main_bp.route("/transact")
@login_required
@account_required
def transact_page():
    return render_template("transact.html")

@main_bp.route("/transfer")
@login_required
@account_required
def transfer_page():
    return render_template("transfer.html", account_id=get_session_account_id())

@main_bp.route("/transactions")
@login_required
@account_required
def transactions_page():
    return render_template("transactions.html", account_id=get_session_account_id())

@main_bp.route("/profile")
@login_required
@account_required
def profile_page():
    return render_template("profile.html", account_id=get_session_account_id())

@main_bp.route("/change-pin")
@login_required
@account_required
def change_pin_page():
    user_id = session.get("user_id")
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return redirect(url_for("auth.login_page"))

    user = users_col.find_one({"_id": user_obj_id})
    if not user:
        return redirect(url_for("auth.login_page"))

    return render_template(
        "change_pin.html",
        account_id=get_session_account_id(),
        account_email=user.get("email", ""),
    )

@main_bp.route("/support")
@login_required
def support_page():
    return render_template("support.html")

@main_bp.route("/security")
@login_required
def security_page():
    return render_template("security.html")

@main_bp.route("/set-pin")
@login_required
def set_pin_page():
    return render_template("set_pin.html")

@main_bp.route("/setup-pin", methods=["GET", "POST"])
@login_required
def setup_pin_page():
    from flask import request
    from werkzeug.security import generate_password_hash
    from utils.time_utils import ist_now

    if request.method == "GET":
        return render_template("setup_pin.html")

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_page"))

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        flash("Invalid user ID.", "danger")
        return redirect(url_for("main.setup_pin_page"))

    pin = (request.form.get("pin") or "").strip()
    confirm_pin = (request.form.get("confirm_pin") or "").strip()

    if not pin or not confirm_pin:
        flash("Please check your input.", "warning")
        return redirect(url_for("main.setup_pin_page"))
    if pin != confirm_pin:
        flash("PIN entries do not match.", "danger")
        return redirect(url_for("main.setup_pin_page"))
    if not pin.isdigit() or len(pin) != 4:
        flash("PIN must be exactly 4 digits.", "warning")
        return redirect(url_for("main.setup_pin_page"))

    hashed_pin = generate_password_hash(pin)
    users_col.update_one(
        {"_id": user_obj_id},
        {"$set": {"transaction_pin": hashed_pin, "pin": hashed_pin, "pin_updated_at": ist_now()}},
    )
    flash("Transaction PIN updated successfully.", "success")
    return redirect(url_for("main.dashboard_page"))

@main_bp.route("/beneficiaries")
@login_required
def beneficiaries_page():
    return render_template("beneficiaries.html")

@main_bp.route("/support/<query_id>")
@login_required
def support_details_page(query_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_page"))

    try:
        query_obj_id = ObjectId(query_id)
        user_obj_id = ObjectId(user_id)
    except Exception:
        return render_template("support_details.html", query=None, error="Invalid query ID.")

    query = support_queries_col.find_one({"_id": query_obj_id, "user_id": user_obj_id})
    if not query:
        return render_template("support_details.html", query=None, error="Support query not found.")

    created_at = query.get("created_at") or query_obj_id.generation_time
    resolved_at = query.get("resolved_at")
    details = {
        "id": str(query.get("_id")),
        "subject": query.get("subject", ""),
        "message": query.get("message", ""),
        "priority": query.get("priority", "Low"),
        "status": query.get("status", "Open"),
        "created_at_display": format_ist(created_at),
        "resolved_at_display": format_ist(resolved_at),
        "admin_reply": query.get("admin_reply"),
    }
    return render_template("support_details.html", query=details, error=None)
