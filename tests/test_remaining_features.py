import os

import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections

cols = get_collections()
accounts_col = cols["accounts"]
support_queries_col = cols["support_queries"]
users_col = cols["users"]


@pytest.fixture(autouse=True)
def clear_collections():
    for col in (accounts_col, support_queries_col, users_col):
        col.delete_many({})
    yield
    for col in (accounts_col, support_queries_col, users_col):
        col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def create_user(email="user@example.com", password="secret123", role="user"):
    doc = {
        "name": "Test User",
        "email": email,
        "password_hash": generate_password_hash(password),
        "verified": True,
        "created_at": None,
        "role": role,
    }
    result = users_col.insert_one(doc)
    return users_col.find_one({"_id": result.inserted_id})


def create_account(user, balance=5000.0):
    account = {
        "name": user["name"],
        "email": user["email"],
        "user_id": user["_id"],
        "balance": balance,
        "account_type": "savings",
        "min_balance": 1000.0,
        "created_at": None,
    }
    result = accounts_col.insert_one(account)
    return accounts_col.find_one({"_id": result.inserted_id})


def login_as(client, user, account=None):
    with client.session_transaction() as sess:
        sess["user_id"] = str(user["_id"])
        sess["user_name"] = user["name"]
        sess["user_email"] = user["email"]
        sess["account_id"] = str(account["_id"]) if account else None
        sess["is_admin"] = user.get("role") == "admin"


def test_signup_returns_specific_pin_validation_error(client):
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "test-csrf-token"

    response = client.post(
        "/api/signup",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "StrongPass1!",
            "pin": "abc",
            "confirm_password": "StrongPass1!",
            "_csrf_token": "test-csrf-token",
        },
        headers={"X-CSRFToken": "test-csrf-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Transaction PIN must be 4 to 6 digits."


def test_pin_lock_after_failed_attempts(client):
    user = create_user()
    account = create_account(user)
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"transaction_pin": generate_password_hash("1234"), "pin": generate_password_hash("1234")}},
    )
    login_as(client, user, account)

    for _ in range(5):
        response = client.post(
            "/api/transfer",
            json={"receiver_email": "receiver@example.com", "amount": 10, "pin": "0000"},
        )
        assert response.status_code == 400

    locked = users_col.find_one({"_id": user["_id"]})
    assert locked.get("pin_lock_until") is not None

    response = client.post(
        "/api/transfer",
        json={"receiver_email": "receiver@example.com", "amount": 10, "pin": "0000"},
    )
    assert response.status_code == 429


def test_admin_support_reply_updates_ticket(client):
    admin = create_user(email="admin@example.com", role="admin")
    login_as(client, admin)
    query_id = support_queries_col.insert_one(
        {
            "user_id": ObjectId(),
            "email": "customer@example.com",
            "subject": "Help needed",
            "message": "Issue",
            "priority": "High",
            "status": "Open",
            "created_at": None,
            "resolved_at": None,
            "admin_reply": None,
        }
    ).inserted_id

    response = client.post(
        f"/api/admin/support/{query_id}/reply",
        json={"reply": "We have resolved this."},
    )
    assert response.status_code == 200

    updated = support_queries_col.find_one({"_id": query_id})
    assert updated["status"] == "Resolved"
    assert updated["admin_reply"] == "We have resolved this."


def test_created_at_backfill_script_marks_missing_documents(tmp_path, monkeypatch):
    user = create_user(email="legacy@example.com")
    accounts_col.insert_one(
        {
            "name": "Legacy",
            "email": "legacy@example.com",
            "user_id": user["_id"],
            "balance": 1000.0,
            "account_type": "savings",
            "min_balance": 1000.0,
        }
    )

    from scripts.backfill_created_at import main

    main()

    refreshed_user = users_col.find_one({"_id": user["_id"]})
    refreshed_account = accounts_col.find_one({"email": "legacy@example.com"})
    assert refreshed_user.get("created_at") is not None
    assert refreshed_account.get("created_at") is not None