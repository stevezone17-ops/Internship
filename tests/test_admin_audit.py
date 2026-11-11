import os
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections

cols = get_collections()
users_col = cols["users"]
accounts_col = cols["accounts"]
support_queries_col = cols["support_queries"]
notifications_col = cols["notifications"]
transactions_col = cols["transactions"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    support_queries_col.delete_many({})
    notifications_col.delete_many({})
    transactions_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    support_queries_col.delete_many({})
    notifications_col.delete_many({})
    transactions_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user(email="regular@example.com", role="user"):
    u_res = users_col.insert_one({
        "name": "Test User",
        "email": email,
        "password_hash": generate_password_hash("Password123!"),
        "role": role,
    })
    return str(u_res.inserted_id)


def login_session(client, user_id, email="regular@example.com", is_admin=False):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_email"] = email
        sess["is_admin"] = is_admin


def test_admin_unauthenticated_api_access(client):
    res = client.get("/api/admin/overview")
    assert res.status_code == 401
    assert "Please login" in res.get_json()["error"]


def test_admin_unauthenticated_page_access(client):
    res = client.get("/admin")
    assert res.status_code == 302
    assert "/login" in res.location


def test_admin_forbidden_regular_user_api(client):
    u_id = setup_user(role="user")
    login_session(client, u_id, is_admin=False)

    res = client.get("/api/admin/overview")
    assert res.status_code == 403
    assert "Forbidden" in res.get_json()["error"]


def test_admin_forbidden_regular_user_page(client):
    u_id = setup_user(role="user")
    login_session(client, u_id, is_admin=False)

    res = client.get("/admin")
    assert res.status_code == 302
    assert "/dashboard" in res.location


def test_admin_authorized_overview(client):
    admin_id = setup_user(email="admin@bank.com", role="admin")
    login_session(client, admin_id, email="admin@bank.com", is_admin=True)

    res = client.get("/api/admin/overview")
    assert res.status_code == 200
    data = res.get_json()
    assert "totals" in data
    assert "users" in data["totals"]
    assert "accounts" in data["totals"]
    assert "transactions" in data["totals"]


def test_admin_support_reply_and_notification(client):
    # Setup customer user and ticket
    cust_id = setup_user(email="cust@example.com", role="user")
    acct_id = accounts_col.insert_one({
        "user_id": ObjectId(cust_id),
        "email": "cust@example.com",
        "name": "Customer",
        "balance": 2000.0,
    }).inserted_id
    ticket_id = support_queries_col.insert_one({
        "user_id": ObjectId(cust_id),
        "email": "cust@example.com",
        "subject": "Payment issue",
        "message": "Double charged",
        "priority": "High",
        "status": "Open",
    }).inserted_id

    # Admin replies
    admin_id = setup_user(email="admin@bank.com", role="admin")
    login_session(client, admin_id, email="admin@bank.com", is_admin=True)

    res = client.post(
        f"/api/admin/support/{ticket_id}/reply",
        json={"reply": "Refund processed."},
    )
    assert res.status_code == 200

    # Verify ticket state
    ticket = support_queries_col.find_one({"_id": ticket_id})
    assert ticket["status"] == "Resolved"
    assert ticket["admin_reply"] == "Refund processed."
    assert ticket.get("resolved_at") is not None

    # Verify notification created for customer account
    notif = notifications_col.find_one({"account_id": acct_id, "metadata.type": "support"})
    assert notif is not None
    assert "Payment issue" in notif["message"]
