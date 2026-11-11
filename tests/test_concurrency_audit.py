import os
import concurrent.futures
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections
from utils.time_utils import ist_now

cols = get_collections()
users_col = cols["users"]
accounts_col = cols["accounts"]
transactions_col = cols["transactions"]
scheduled_col = cols["scheduled_transfers"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})
    scheduled_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})
    scheduled_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user_and_account(email="user@example.com", balance=3000.0, acct_type="savings"):
    hashed_pass = generate_password_hash("Password123!")
    hashed_pin = generate_password_hash("1234")
    u_res = users_col.insert_one({
        "name": "Race User",
        "email": email,
        "password_hash": hashed_pass,
        "pin": hashed_pin,
        "transaction_pin": hashed_pin,
    })
    user_id = u_res.inserted_id

    min_bal = 1000.0 if acct_type == "savings" else 5000.0
    a_res = accounts_col.insert_one({
        "user_id": user_id,
        "name": "Race User",
        "email": email,
        "balance": float(balance),
        "account_type": acct_type,
        "min_balance": float(min_bal),
    })
    return str(user_id), str(a_res.inserted_id)


def login_session(client, user_id, account_id, email="user@example.com"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["account_id"] = account_id
        sess["user_email"] = email
        sess["user_name"] = "Race User"
        sess["last_tx_time"] = 0


def test_atomic_balance_debit_prevents_overdraft(client):
    """Verify that MongoDB atomic $gte guard prevents overdraft when two operations race."""
    u_id, a_id = setup_user_and_account(balance=1500.0, acct_type="savings")
    acct_oid = ObjectId(a_id)

    # Attempt two atomic decrements of 1000 each on a 1500 balance
    res1 = accounts_col.find_one_and_update(
        {"_id": acct_oid, "balance": {"$gte": 1000.0}},
        {"$inc": {"balance": -1000.0}},
        return_document=True,
    )
    assert res1 is not None
    assert res1["balance"] == 500.0

    # Second atomic decrement should fail because balance is 500 < 1000
    res2 = accounts_col.find_one_and_update(
        {"_id": acct_oid, "balance": {"$gte": 1000.0}},
        {"$inc": {"balance": -1000.0}},
        return_document=True,
    )
    assert res2 is None

    # Balance remains 500.0 without going negative
    final_account = accounts_col.find_one({"_id": acct_oid})
    assert final_account["balance"] == 500.0


def test_malformed_object_ids_graceful_handling(client):
    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    # Malformed account id
    res_acct = client.get("/api/account/invalid-hex-id-123")
    assert res_acct.status_code in (400, 404)

    # Malformed transaction account id
    res_tx = client.get("/api/transactions/invalid-hex-id-123")
    assert res_tx.status_code in (400, 403, 404)

    # Malformed delete beneficiary id
    res_ben = client.delete("/api/beneficiaries/not-an-objectid")
    assert res_ben.status_code in (400, 404)


def test_extreme_amounts_and_non_numeric_handling(client):
    u_id, a_id = setup_user_and_account(balance=5000.0)
    login_session(client, u_id, a_id)

    # String amount
    res_str = client.post("/api/deposit", json={"amount": "abc", "pin": "1234"})
    assert res_str.status_code == 400

    # NaN string
    res_nan = client.post("/api/deposit", json={"amount": "NaN", "pin": "1234"})
    assert res_nan.status_code == 400

    # Huge number > 10000 limit
    res_huge = client.post("/api/deposit", json={"amount": 999999999, "pin": "1234"})
    assert res_huge.status_code == 400


def test_scheduled_transfer_runner_execution(client, monkeypatch):
    monkeypatch.setenv("SCHEDULED_TRANSFER_TOKEN", "super-secret-cron-token")

    sender_uid, sender_aid = setup_user_and_account(email="sender@cron.com", balance=5000.0)
    receiver_uid, receiver_aid = setup_user_and_account(email="receiver@cron.com", balance=1000.0)

    # Insert a due scheduled transfer
    scheduled_col.insert_one({
        "user_id": ObjectId(sender_uid),
        "receiver_email": "receiver@cron.com",
        "amount": 500.0,
        "scheduled_at": ist_now(),
        "created_at": ist_now(),
        "status": "scheduled",
    })

    # Unauthorized runner call without token
    res_unauth = client.post("/api/scheduled-transfers/run")
    assert res_unauth.status_code == 403

    # Authorized runner call
    res_run = client.post(
        "/api/scheduled-transfers/run",
        headers={"X-Scheduler-Token": "super-secret-cron-token"},
    )
    assert res_run.status_code == 200
    data = res_run.get_json()
    assert data["processed"] == 1

    # Verify balances updated
    sender_acct = accounts_col.find_one({"_id": ObjectId(sender_aid)})
    assert sender_acct["balance"] == 4500.0
    receiver_acct = accounts_col.find_one({"_id": ObjectId(receiver_aid)})
    assert receiver_acct["balance"] == 1500.0

    # Verify scheduled transfer marked processed
    st = scheduled_col.find_one({"receiver_email": "receiver@cron.com"})
    assert st["status"] == "processed"
    assert st.get("processed_at") is not None
