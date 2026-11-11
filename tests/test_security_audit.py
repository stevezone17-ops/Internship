import os
import time
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections

cols = get_collections()
users_col = cols["users"]
accounts_col = cols["accounts"]
login_activity_col = cols["login_activity"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    login_activity_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    login_activity_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user(email="security@example.com", name="Sec User", pin="1234", password="OldPassword1!"):
    hashed_pass = generate_password_hash(password)
    hashed_pin = generate_password_hash(pin)
    u_res = users_col.insert_one({
        "name": name,
        "email": email,
        "password_hash": hashed_pass,
        "pin": hashed_pin,
        "transaction_pin": hashed_pin,
    })
    user_id = u_res.inserted_id
    a_res = accounts_col.insert_one({
        "user_id": user_id,
        "name": name,
        "email": email,
        "balance": 5000.0,
        "account_type": "savings",
        "min_balance": 1000.0,
    })
    return str(user_id), str(a_res.inserted_id)


def login_session(client, user_id, account_id, email="security@example.com", name="Sec User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["account_id"] = account_id
        sess["user_email"] = email
        sess["user_name"] = name
        sess["last_activity"] = time.time()
        sess["_csrf_token"] = "valid-csrf-token-12345"


def test_csrf_production_enforcement(client, monkeypatch):
    # Simulate production environment on Render
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("RENDER", "true")

    u_id, a_id = setup_user()
    with client.session_transaction() as sess:
        sess["user_id"] = u_id
        sess["account_id"] = a_id
        sess["_csrf_token"] = "valid-csrf-token-12345"

    # Request without CSRF token must fail with 403 Forbidden even if app.config['TESTING'] is True
    res_no_token = client.post("/api/deposit", json={"amount": 100, "pin": "1234"})
    assert res_no_token.status_code == 403
    assert "Invalid CSRF token" in res_no_token.get_json()["error"]

    # Request with wrong token must also fail with 403
    res_bad_token = client.post(
        "/api/deposit",
        json={"amount": 100, "pin": "1234"},
        headers={"X-CSRFToken": "wrong-token"},
    )
    assert res_bad_token.status_code == 403

    # Request with valid matching token must succeed
    res_good_token = client.post(
        "/api/deposit",
        json={"amount": 100, "pin": "1234"},
        headers={"X-CSRFToken": "valid-csrf-token-12345"},
    )
    assert res_good_token.status_code == 200


def test_password_change_flow(client):
    u_id, a_id = setup_user()
    login_session(client, u_id, a_id)

    # Change password
    res = client.post(
        "/api/change-password",
        json={"current": "OldPassword1!", "new": "NewSecurePass123!", "confirm": "NewSecurePass123!"},
    )
    assert res.status_code == 200
    assert "Password changed" in res.get_json()["message"]

    # Old password fails login
    res_old = client.post("/api/login", json={"email": "security@example.com", "password": "OldPassword1!"})
    assert res_old.status_code == 401

    # New password succeeds login
    res_new = client.post("/api/login", json={"email": "security@example.com", "password": "NewSecurePass123!"})
    assert res_new.status_code == 200


def test_password_change_validation_errors(client):
    u_id, a_id = setup_user()
    login_session(client, u_id, a_id)

    # Wrong current password
    res_wrong = client.post(
        "/api/change-password",
        json={"current": "WrongOldPass", "new": "NewSecurePass123!", "confirm": "NewSecurePass123!"},
    )
    assert res_wrong.status_code == 400
    assert "incorrect" in res_wrong.get_json()["error"]

    # Password mismatch
    res_mismatch = client.post(
        "/api/change-password",
        json={"current": "OldPassword1!", "new": "NewSecurePass123!", "confirm": "DifferentPass123!"},
    )
    assert res_mismatch.status_code == 400
    assert "do not match" in res_mismatch.get_json()["error"]

    # Too short (<8 chars)
    res_short = client.post(
        "/api/change-password",
        json={"current": "OldPassword1!", "new": "short", "confirm": "short"},
    )
    assert res_short.status_code == 400
    assert "at least 8" in res_short.get_json()["error"]


def test_pin_update_rate_limiting(client):
    u_id, a_id = setup_user()
    login_session(client, u_id, a_id)

    # First PIN update with current PIN
    res1 = client.post(
        "/api/update-pin",
        json={"current_pin": "1234", "new_pin": "5678", "confirm_pin": "5678"},
    )
    assert res1.status_code == 200

    # Immediate second update should be rate limited to 60s
    res2 = client.post(
        "/api/update-pin",
        json={"current_pin": "5678", "new_pin": "9999", "confirm_pin": "9999"},
    )
    assert res2.status_code == 429
    assert "wait" in res2.get_json()["error"]


def test_inactivity_timeout_expiration(client):
    u_id, a_id = setup_user()
    with client.session_transaction() as sess:
        sess["user_id"] = u_id
        sess["account_id"] = a_id
        sess["user_email"] = "security@example.com"
        # Simulate last activity 700 seconds ago (limit is 600s)
        sess["last_activity"] = time.time() - 700

    # API call should return 401 expired
    res = client.get("/api/profile")
    assert res.status_code == 401
    assert "expired" in res.get_json()["error"].lower()


def test_login_activity_audit(client):
    u_id, a_id = setup_user(email="auditlogin@example.com")

    # Login to create login_activity record
    res = client.post(
        "/api/login",
        json={"email": "auditlogin@example.com", "password": "OldPassword1!"},
        headers={"User-Agent": "TestBrowser/1.0"},
    )
    assert res.status_code == 200

    # Fetch login activity
    res_act = client.get("/api/login-activity")
    assert res_act.status_code == 200
    activities = res_act.get_json()["logins"]
    assert len(activities) >= 1
    assert activities[0]["user_agent"] == "TestBrowser/1.0"
