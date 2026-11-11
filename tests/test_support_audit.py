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


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    support_queries_col.delete_many({})
    notifications_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    support_queries_col.delete_many({})
    notifications_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user(email="supporter@example.com", name="Support User"):
    u_res = users_col.insert_one({
        "name": name,
        "email": email,
        "password_hash": generate_password_hash("Password123!"),
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


def login_session(client, user_id, account_id, email="supporter@example.com", name="Support User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["account_id"] = account_id
        sess["user_email"] = email
        sess["user_name"] = name


def test_support_create_valid(client):
    u_id, a_id = setup_user()
    login_session(client, u_id, a_id)

    res = client.post(
        "/api/support",
        json={"subject": "Card Issue", "message": "My card was declined.", "priority": "High"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "query_id" in data

    ticket = support_queries_col.find_one({"_id": ObjectId(data["query_id"])})
    assert ticket is not None
    assert ticket["subject"] == "Card Issue"
    assert ticket["priority"] == "High"
    assert ticket["status"] == "Open"
    assert ticket["user_id"] == ObjectId(u_id)


def test_support_create_validation_errors(client):
    u_id, a_id = setup_user()
    login_session(client, u_id, a_id)

    # Missing message
    res_no_msg = client.post("/api/support", json={"subject": "Inquiry"})
    assert res_no_msg.status_code == 400

    # Invalid priority
    res_bad_pri = client.post(
        "/api/support",
        json={"subject": "Inquiry", "message": "Test details", "priority": "SuperUrgent"},
    )
    assert res_bad_pri.status_code == 400
    assert "Priority must be Low, Medium, or High" in res_bad_pri.get_json()["error"]


def test_support_history_and_details_idor(client):
    u1_id, a1_id = setup_user(email="u1@example.com", name="User One")
    u2_id, a2_id = setup_user(email="u2@example.com", name="User Two")

    # User 1 creates ticket
    login_session(client, u1_id, a1_id, email="u1@example.com")
    res1 = client.post("/api/support", json={"subject": "U1 Secret Ticket", "message": "Private info"})
    q1_id = res1.get_json()["query_id"]

    # User 2 logs in and checks history
    login_session(client, u2_id, a2_id, email="u2@example.com")
    hist_res = client.get("/api/support/history")
    assert hist_res.status_code == 200
    queries = hist_res.get_json()["queries"]
    assert len(queries) == 0  # Cannot see User 1's ticket

    # User 2 tries to view User 1's ticket details page (IDOR attack)
    detail_res = client.get(f"/support/{q1_id}")
    assert detail_res.status_code == 200
    assert b"Support query not found" in detail_res.data


def test_notifications_tracking_and_idor(client):
    from services.notifications import add_notification

    u1_id, a1_id = setup_user(email="u1@example.com")
    u2_id, a2_id = setup_user(email="u2@example.com")

    # Add notification for User 1
    add_notification(notifications_col, ObjectId(a1_id), "Deposit received ₹500")
    add_notification(notifications_col, ObjectId(a1_id), "Security alert: password changed")

    # Add notification for User 2
    add_notification(notifications_col, ObjectId(a2_id), "User 2 welcome notification")

    login_session(client, u1_id, a1_id, email="u1@example.com")

    # Check unread count for User 1
    res_count = client.get("/api/notifications/unread-count")
    assert res_count.status_code == 200
    assert res_count.get_json()["count"] == 2

    # Get notifications list
    res_list = client.get("/api/notifications")
    assert res_list.status_code == 200
    notifs = res_list.get_json()["notifications"]
    assert len(notifs) == 2
    n1_id = notifs[0]["id"]

    # Mark single notification read
    res_read = client.post(f"/api/notifications/{n1_id}/mark-read")
    assert res_read.status_code == 200

    # Unread count should now be 1
    res_count2 = client.get("/api/notifications/unread-count")
    assert res_count2.get_json()["count"] == 1

    # User 2 logs in and tries to mark User 1's notification as read (IDOR attack)
    login_session(client, u2_id, a2_id, email="u2@example.com")
    res_idor = client.post(f"/api/notifications/{n1_id}/mark-read")
    assert res_idor.status_code == 404

    # User 1 marks all read
    login_session(client, u1_id, a1_id, email="u1@example.com")
    res_all = client.post("/api/notifications/mark-all-read")
    assert res_all.status_code == 200
    assert res_all.get_json()["count"] == 1
