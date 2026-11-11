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
transactions_col = cols["transactions"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})
    yield
    users_col.delete_many({})
    accounts_col.delete_many({})
    transactions_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user_and_account(email="user@example.com", name="User", balance=5000.0):
    hashed_pass = generate_password_hash("Password123!")
    hashed_pin = generate_password_hash("1234")
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
        "balance": float(balance),
        "account_type": "savings",
        "min_balance": 1000.0,
    })
    account_id = a_res.inserted_id
    return str(user_id), str(account_id)


def login_session(client, user_id, account_id, email="user@example.com", name="User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["account_id"] = account_id
        sess["user_email"] = email
        sess["user_name"] = name


def test_get_transactions_idor_protection(client):
    u1_id, a1_id = setup_user_and_account(email="u1@example.com")
    u2_id, a2_id = setup_user_and_account(email="u2@example.com")

    # Log in as User 1
    login_session(client, u1_id, a1_id, email="u1@example.com")

    # Try to access User 2's transactions
    res = client.get(f"/api/transactions/{a2_id}")
    assert res.status_code == 403
    assert "Unauthorized" in res.get_json()["error"]


def test_get_transactions_filtering_and_search(client):
    from services.transactions import record_transaction

    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    # Insert test transactions
    record_transaction(transactions_col, ObjectId(a_id), "deposit", 500.0)
    record_transaction(transactions_col, ObjectId(a_id), "deposit", 1500.0)
    record_transaction(transactions_col, ObjectId(a_id), "withdraw", 200.0)
    record_transaction(transactions_col, ObjectId(a_id), "transfer", 300.0, metadata={"to_account_id": "target123"})

    # Filter by type=deposit
    res_type = client.get(f"/api/transactions/{a_id}?type=deposit")
    assert res_type.status_code == 200
    data_type = res_type.get_json()
    assert len(data_type["transactions"]) == 2
    for tx in data_type["transactions"]:
        assert tx["type"] == "deposit"

    # Filter by min_amount and max_amount
    res_amount = client.get(f"/api/transactions/{a_id}?min_amount=400&max_amount=1000")
    assert res_amount.status_code == 200
    data_amount = res_amount.get_json()
    assert len(data_amount["transactions"]) == 1
    assert data_amount["transactions"][0]["amount"] == 500.0

    # Search query q (verifying DEF-002 fix)
    res_q = client.get(f"/api/transactions/{a_id}?q=deposit")
    assert res_q.status_code == 200
    assert len(res_q.get_json()["transactions"]) == 2

    res_q_meta = client.get(f"/api/transactions/{a_id}?q=target123")
    assert res_q_meta.status_code == 200
    assert len(res_q_meta.get_json()["transactions"]) == 1


def test_get_transactions_pagination_and_sorting(client):
    from services.transactions import record_transaction

    u_id, a_id = setup_user_and_account()
    login_session(client, u_id, a_id)

    # Create 5 transactions
    for i in range(1, 6):
        record_transaction(transactions_col, ObjectId(a_id), "deposit", float(i * 100))

    # Page 1, limit 2
    res_p1 = client.get(f"/api/transactions/{a_id}?page=1&limit=2&sort_by=amount&order=asc")
    assert res_p1.status_code == 200
    d1 = res_p1.get_json()
    assert len(d1["transactions"]) == 2
    assert d1["transactions"][0]["amount"] == 100.0
    assert d1["transactions"][1]["amount"] == 200.0

    # Page 2, limit 2
    res_p2 = client.get(f"/api/transactions/{a_id}?page=2&limit=2&sort_by=amount&order=asc")
    assert res_p2.status_code == 200
    d2 = res_p2.get_json()
    assert len(d2["transactions"]) == 2
    assert d2["transactions"][0]["amount"] == 300.0
    assert d2["transactions"][1]["amount"] == 400.0


def test_export_csv_flow_and_idor(client):
    from services.transactions import record_transaction

    u1_id, a1_id = setup_user_and_account(email="csv1@example.com")
    u2_id, a2_id = setup_user_and_account(email="csv2@example.com")

    record_transaction(transactions_col, ObjectId(a1_id), "deposit", 250.0)

    # User 1 exports own CSV
    login_session(client, u1_id, a1_id, email="csv1@example.com")
    res_csv = client.get(f"/api/transactions/{a1_id}/export/csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.content_type
    assert b"250.0" in res_csv.data or b"250" in res_csv.data

    # User 1 attempts to export User 2's CSV
    res_idor = client.get(f"/api/transactions/{a2_id}/export/csv")
    assert res_idor.status_code == 403


def test_export_pdf_flow_and_idor(client):
    from services.transactions import record_transaction

    u1_id, a1_id = setup_user_and_account(email="pdf1@example.com")
    u2_id, a2_id = setup_user_and_account(email="pdf2@example.com")

    record_transaction(transactions_col, ObjectId(a1_id), "deposit", 500.0)

    # User 1 exports own PDF
    login_session(client, u1_id, a1_id, email="pdf1@example.com")
    res_pdf = client.get(f"/api/transactions/{a1_id}/export/pdf")
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.content_type
    assert res_pdf.data.startswith(b"%PDF")

    # User 1 attempts to export User 2's PDF
    res_idor = client.get(f"/api/transactions/{a2_id}/export/pdf")
    assert res_idor.status_code == 403
