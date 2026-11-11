import os
import time
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections

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


def setup_user_and_account(email="banker@example.com", name="Bank User", balance=5000.0, acct_type="savings", pin="1234"):
    hashed_pass = generate_password_hash("Password123!")
    hashed_pin = generate_password_hash(pin)
    u_res = users_col.insert_one({
        "name": name,
        "email": email,
        "password_hash": hashed_pass,
        "pin": hashed_pin,
        "transaction_pin": hashed_pin,
    })
    user_id = u_res.inserted_id

    min_bal = 1000.0 if acct_type == "savings" else 5000.0
    a_res = accounts_col.insert_one({
        "user_id": user_id,
        "name": name,
        "email": email,
        "balance": float(balance),
        "account_type": acct_type,
        "min_balance": float(min_bal),
    })
    account_id = a_res.inserted_id
    return str(user_id), str(account_id)


def login_session(client, user_id, account_id, email="banker@example.com", name="Bank User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["account_id"] = account_id
        sess["user_email"] = email
        sess["user_name"] = name
        sess["last_tx_time"] = 0  # reset rate-limiting


def test_deposit_valid_flow(client):
    u_id, a_id = setup_user_and_account(balance=2000.0)
    login_session(client, u_id, a_id)

    res = client.post("/api/deposit", json={"amount": 500.0, "pin": "1234"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["balance"] == 2500.0
    assert "transaction_id" in data

    # Verify DB state
    account = accounts_col.find_one({"_id": ObjectId(a_id)})
    assert account["balance"] == 2500.0
    tx = transactions_col.find_one({"account_id": ObjectId(a_id), "type": "deposit"})
    assert tx is not None
    assert tx["amount"] == 500.0


def test_deposit_invalid_amounts_and_limits(client):
    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    # Negative amount
    res_neg = client.post("/api/deposit", json={"amount": -100, "pin": "1234"})
    assert res_neg.status_code == 400

    # Zero amount
    res_zero = client.post("/api/deposit", json={"amount": 0, "pin": "1234"})
    assert res_zero.status_code == 400

    # Exceeding 10,000 limit
    res_over = client.post("/api/deposit", json={"amount": 10001, "pin": "1234"})
    assert res_over.status_code == 400


def test_deposit_wrong_pin(client):
    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    res = client.post("/api/deposit", json={"amount": 500, "pin": "9999"})
    assert res.status_code == 400
    assert "incorrect" in res.get_json()["error"]


def test_withdraw_valid_flow(client):
    u_id, a_id = setup_user_and_account(balance=4000.0)
    login_session(client, u_id, a_id)

    res = client.post("/api/withdraw", json={"amount": 1000.0, "pin": "1234"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["balance"] == 3000.0

    account = accounts_col.find_one({"_id": ObjectId(a_id)})
    assert account["balance"] == 3000.0
    tx = transactions_col.find_one({"account_id": ObjectId(a_id), "type": "withdraw"})
    assert tx is not None
    assert tx["amount"] == 1000.0

    # Verify notification created
    notif = notifications_col.find_one({"account_id": ObjectId(a_id), "metadata.type": "withdraw"})
    assert notif is not None


def test_withdraw_insufficient_balance_and_min_balance(client):
    # Savings account with balance 1500 (min_balance 1000)
    u_id, a_id = setup_user_and_account(balance=1500.0, acct_type="savings")
    login_session(client, u_id, a_id)

    # Exceeding total balance
    res_over = client.post("/api/withdraw", json={"amount": 2000.0, "pin": "1234"})
    assert res_over.status_code == 400

    # Reset rate limiter
    with client.session_transaction() as sess:
        sess["last_tx_time"] = 0

    # Violating minimum balance of 1000 (1500 - 600 = 900 < 1000)
    res_min = client.post("/api/withdraw", json={"amount": 600.0, "pin": "1234"})
    assert res_min.status_code == 400
    assert "Minimum balance" in res_min.get_json()["error"]


def test_withdraw_rate_limiting(client):
    u_id, a_id = setup_user_and_account(balance=5000.0)
    login_session(client, u_id, a_id)

    res1 = client.post("/api/withdraw", json={"amount": 100.0, "pin": "1234"})
    assert res1.status_code == 200

    # Immediate second withdrawal should be rate-limited
    res2 = client.post("/api/withdraw", json={"amount": 100.0, "pin": "1234"})
    assert res2.status_code == 429


def test_transfer_valid_flow_and_no_email_value_error(client):
    sender_uid, sender_aid = setup_user_and_account(email="sender@example.com", name="Sender", balance=6000.0)
    receiver_uid, receiver_aid = setup_user_and_account(email="receiver@example.com", name="Receiver", balance=2000.0)

    login_session(client, sender_uid, sender_aid, email="sender@example.com", name="Sender")

    res = client.post(
        "/api/transfer",
        json={"receiver_email": "receiver@example.com", "amount": 1500.0, "pin": "1234"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["balance"] == 4500.0

    # Check recipient got funds
    receiver_acct = accounts_col.find_one({"_id": ObjectId(receiver_aid)})
    assert receiver_acct["balance"] == 3500.0

    # Check sender ledger
    sender_tx = transactions_col.find_one({"account_id": ObjectId(sender_aid), "type": "transfer"})
    assert sender_tx is not None
    assert sender_tx["amount"] == 1500.0

    # Check receiver ledger
    receiver_tx = transactions_col.find_one({"account_id": ObjectId(receiver_aid), "type": "transfer"})
    assert receiver_tx is not None
    assert receiver_tx["amount"] == 1500.0

    # Check email notifications recorded without ValueError
    notifs = list(notifications_col.find({"account_id": ObjectId(sender_aid), "metadata.type": "transfer"}))
    assert len(notifs) >= 1


def test_transfer_to_self_forbidden(client):
    u_id, a_id = setup_user_and_account(email="myself@example.com")
    login_session(client, u_id, a_id, email="myself@example.com")

    res = client.post(
        "/api/transfer",
        json={"receiver_email": "myself@example.com", "amount": 100.0, "pin": "1234"},
    )
    assert res.status_code == 400
    assert "own account" in res.get_json()["error"]


def test_transfer_nonexistent_recipient(client):
    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    res = client.post(
        "/api/transfer",
        json={"receiver_email": "ghost@example.com", "amount": 100.0, "pin": "1234"},
    )
    assert res.status_code == 404


def test_decimal_precision_rounding(client):
    u_id, a_id = setup_user_and_account(balance=1000.0)
    login_session(client, u_id, a_id)

    # Deposit with 3 decimal places: 50.126 -> rounds to 50.13
    res = client.post("/api/deposit", json={"amount": 50.126, "pin": "1234"})
    assert res.status_code == 200
    account = accounts_col.find_one({"_id": ObjectId(a_id)})
    assert account["balance"] == 1050.13
