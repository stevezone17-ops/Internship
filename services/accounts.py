from werkzeug.security import check_password_hash, generate_password_hash
from utils.time_utils import ist_now

ACCOUNT_RULES = {
    "savings": {"min_balance": 1000.0, "label": "Savings"},
    "current": {"min_balance": 5000.0, "label": "Current"},
}


def authenticate_user(users_col, email, password):
    user = users_col.find_one({"email": email})
    if not user:
        return None
    if not check_password_hash(user.get("password_hash", ""), password):
        return None
    return user


def mark_user_verified(users_col, token):
    user = users_col.find_one({"verification_token": token})
    if not user:
        return None, "Invalid verification token."

    expires = user.get("verification_expires")
    if expires and ist_now() > expires:
        return None, "Verification token expired."

    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"verified": True},
            "$unset": {"verification_token": "", "verification_expires": ""},
        },
    )
    return user, None


def create_reset_token(users_col, email):
    user = users_col.find_one({"email": email})
    if not user:
        return None, None

    reset_token = str(uuid.uuid4())
    reset_expires = ist_now() + timedelta(minutes=10)
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"reset_token": reset_token, "reset_expires": reset_expires}},
    )
    return user, reset_token


def reset_password(users_col, token, new_password):
    user = users_col.find_one({"reset_token": token})
    if not user:
        return None, "Invalid reset token."

    expires = user.get("reset_expires")
    if expires and ist_now() > expires:
        return None, "Reset token expired."

    users_col.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password_hash": generate_password_hash(new_password)},
            "$unset": {"reset_token": "", "reset_expires": ""},
        },
    )
    return user, None


def create_account_for_user(accounts_col, user_id, name, email, account_type, initial_deposit):
    if account_type not in ACCOUNT_RULES:
        return None, "Invalid account type."

    existing = accounts_col.find_one({"user_id": ObjectId(user_id)})
    if existing:
        return None, "This user already has an account."

    min_balance = ACCOUNT_RULES[account_type]["min_balance"]
    if initial_deposit < min_balance:
        return None, f"Minimum balance for {ACCOUNT_RULES[account_type]['label']} is ₹{min_balance:.0f}."

    account_doc = {
        "name": name,
        "email": email,
        "user_id": ObjectId(user_id),
        "balance": float(initial_deposit),
        "account_type": account_type,
        "min_balance": float(min_balance),
        "created_at": ist_now(),
    }
    result = accounts_col.insert_one(account_doc)
    account_doc["_id"] = result.inserted_id
    return account_doc, None


def get_account_by_id(accounts_col, account_id):
    try:
        account = accounts_col.find_one({"_id": ObjectId(account_id)})
    except Exception:
        return None
    return account


def get_account_for_user(accounts_col, user_id):
    return accounts_col.find_one({"user_id": ObjectId(user_id)})


def ensure_account_owner(account, user_id):
    return account and str(account.get("user_id")) == str(user_id)
