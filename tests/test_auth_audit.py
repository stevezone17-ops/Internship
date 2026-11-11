import os
from datetime import timedelta
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections
from utils.time_utils import ist_now
from utils.helpers import verify_transaction_pin

cols = get_collections()
users_col = cols["users"]
accounts_col = cols["accounts"]
transactions_col = cols["transactions"]
notifications_col = cols["notifications"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})
    notifications_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})
    notifications_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_signup_valid(client):
    res = client.post(
        "/api/signup",
        json={
            "name": "Audit User",
            "email": "audit@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    assert res.status_code == 200
    user = users_col.find_one({"email": "audit@example.com"})
    assert user is not None
    assert user["name"] == "Audit User"
    assert check_password_hash(user["password_hash"], "Password123!")
    assert check_password_hash(user["transaction_pin"], "1234")
    assert check_password_hash(user["pin"], "1234")


def test_signup_duplicate_email(client):
    client.post(
        "/api/signup",
        json={
            "name": "First User",
            "email": "dup@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    res = client.post(
        "/api/signup",
        json={
            "name": "Second User",
            "email": "dup@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "5678",
        },
    )
    assert res.status_code == 400
    assert "already exists" in res.get_json()["error"]


def test_signup_invalid_email_format(client):
    invalid_emails = ["notanemail", "missingat.com", "@missinguser.com", "spaces in@email.com"]
    for email in invalid_emails:
        res = client.post(
            "/api/signup",
            json={
                "name": "Bad Email",
                "email": email,
                "password": "Password123!",
                "confirm_password": "Password123!",
                "pin": "1234",
            },
        )
        assert res.status_code == 400
        assert "valid email" in res.get_json()["error"]


def test_signup_missing_fields(client):
    res = client.post("/api/signup", json={"email": "missing@example.com"})
    assert res.status_code == 400


def test_signup_short_password(client):
    res = client.post(
        "/api/signup",
        json={
            "name": "Short Pass",
            "email": "short@example.com",
            "password": "short",
            "confirm_password": "short",
            "pin": "1234",
        },
    )
    assert res.status_code == 400
    assert "at least 8 characters" in res.get_json()["error"]


def test_signup_password_mismatch(client):
    res = client.post(
        "/api/signup",
        json={
            "name": "Mismatch User",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPass!",
            "pin": "1234",
        },
    )
    assert res.status_code == 400
    assert "do not match" in res.get_json()["error"]


def test_signup_pin_length_variations(client):
    # 4 digits
    res4 = client.post(
        "/api/signup",
        json={"name": "P4", "email": "p4@example.com", "password": "Password123!", "confirm_password": "Password123!", "pin": "1234"},
    )
    assert res4.status_code == 200

    # 5 digits
    res5 = client.post(
        "/api/signup",
        json={"name": "P5", "email": "p5@example.com", "password": "Password123!", "confirm_password": "Password123!", "pin": "12345"},
    )
    assert res5.status_code == 200

    # 6 digits
    res6 = client.post(
        "/api/signup",
        json={"name": "P6", "email": "p6@example.com", "password": "Password123!", "confirm_password": "Password123!", "pin": "123456"},
    )
    assert res6.status_code == 200

    # 3 digits (invalid)
    res3 = client.post(
        "/api/signup",
        json={"name": "P3", "email": "p3@example.com", "password": "Password123!", "confirm_password": "Password123!", "pin": "123"},
    )
    assert res3.status_code == 400

    # 7 digits (invalid)
    res7 = client.post(
        "/api/signup",
        json={"name": "P7", "email": "p7@example.com", "password": "Password123!", "confirm_password": "Password123!", "pin": "1234567"},
    )
    assert res7.status_code == 400


def test_login_valid(client):
    client.post(
        "/api/signup",
        json={
            "name": "Login User",
            "email": "login@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    res = client.post("/api/login", json={"email": "login@example.com", "password": "Password123!"})
    assert res.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("user_email") == "login@example.com"
        assert sess.get("user_id") is not None


def test_login_invalid_password(client):
    client.post(
        "/api/signup",
        json={
            "name": "Login User",
            "email": "login@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    res = client.post("/api/login", json={"email": "login@example.com", "password": "WrongPassword"})
    assert res.status_code == 401
    user = users_col.find_one({"email": "login@example.com"})
    assert user.get("failed_attempts") == 1


def test_login_account_lockout(client):
    client.post(
        "/api/signup",
        json={
            "name": "Lockout User",
            "email": "lockout@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    # 5 failed attempts
    for _ in range(5):
        res = client.post("/api/login", json={"email": "lockout@example.com", "password": "WrongPassword"})
        assert res.status_code == 401

    user = users_col.find_one({"email": "lockout@example.com"})
    assert user.get("lock_until") is not None

    # 6th attempt should be blocked with 429
    res = client.post("/api/login", json={"email": "lockout@example.com", "password": "WrongPassword"})
    assert res.status_code == 429


def test_password_forgot_and_reset(client):
    client.post(
        "/api/signup",
        json={
            "name": "Reset User",
            "email": "reset@example.com",
            "password": "OldPassword1!",
            "confirm_password": "OldPassword1!",
            "pin": "1234",
        },
    )
    # Generate token
    res = client.post("/api/password/forgot", json={"email": "reset@example.com"})
    assert res.status_code == 200
    user = users_col.find_one({"email": "reset@example.com"})
    token = user.get("reset_token")
    assert token is not None

    # Execute reset with token
    res_reset = client.post("/api/password/reset", json={"token": token, "password": "NewPassword123!"})
    assert res_reset.status_code == 200

    # Verify login with new password
    login_res = client.post("/api/login", json={"email": "reset@example.com", "password": "NewPassword123!"})
    assert login_res.status_code == 200


def test_account_creation_savings_and_current_rules(client):
    signup_res = client.post(
        "/api/signup",
        json={
            "name": "Account Opener",
            "email": "opener@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    user_id = signup_res.get_json()["user_id"]

    # Log in session
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Account Opener"
        sess["user_email"] = "opener@example.com"

    # Try savings with initial deposit under 1000
    res_fail_savings = client.post(
        "/api/create_account",
        json={"name": "Account Opener", "email": "opener@example.com", "account_type": "savings", "initial_deposit": 500},
    )
    assert res_fail_savings.status_code == 400

    # Success savings with 1500
    res_ok_savings = client.post(
        "/api/create_account",
        json={"name": "Account Opener", "email": "opener@example.com", "account_type": "savings", "initial_deposit": 1500},
    )
    assert res_ok_savings.status_code == 200
    account = accounts_col.find_one({"user_id": ObjectId(user_id)})
    assert account is not None
    assert account["balance"] == 1500.0
    assert account["min_balance"] == 1000.0

    # Attempt to open second account must fail
    res_second = client.post(
        "/api/create_account",
        json={"name": "Account Opener", "email": "opener@example.com", "account_type": "current", "initial_deposit": 6000},
    )
    assert res_second.status_code == 400
    assert "already has an account" in res_second.get_json()["error"]


def test_pin_update_5_and_6_digit_propagates_to_transaction_pin(client):
    signup_res = client.post(
        "/api/signup",
        json={
            "name": "PIN Updater",
            "email": "pinupdate@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "pin": "1234",
        },
    )
    user_id = signup_res.get_json()["user_id"]

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "PIN Updater"
        sess["user_email"] = "pinupdate@example.com"

    # Update profile with a 6-digit PIN
    res_prof = client.post(
        "/api/profile/update",
        json={"pin": "654321"},
    )
    assert res_prof.status_code == 200

    # Verify user in database
    user = users_col.find_one({"_id": ObjectId(user_id)})
    assert check_password_hash(user["transaction_pin"], "654321")
    assert check_password_hash(user["pin"], "654321")

    # Verify with transaction pin checker
    ok, err, code = verify_transaction_pin(users_col, user, "654321")
    assert ok is True
    assert err is None
