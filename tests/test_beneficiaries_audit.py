import os
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

os.environ["USE_MOCK_DB"] = "1"

from app import app
from models.db import get_collections

cols = get_collections()
users_col = cols["users"]
beneficiaries_col = cols["beneficiaries"]


@pytest.fixture(autouse=True)
def clean_db():
    users_col.delete_many({})
    beneficiaries_col.delete_many({})
    yield
    users_col.delete_many({})
    beneficiaries_col.delete_many({})


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def setup_user(email="user@example.com", name="User"):
    u_res = users_col.insert_one({
        "name": name,
        "email": email,
        "password_hash": generate_password_hash("Password123!"),
    })
    return str(u_res.inserted_id)


def login_session(client, user_id, email="user@example.com", name="User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_email"] = email
        sess["user_name"] = name


def test_add_beneficiary_valid(client):
    u_id = setup_user()
    login_session(client, u_id)

    res = client.post(
        "/api/beneficiaries",
        json={"name": "Alice Friend", "email": "alice@example.com", "nickname": "Ali"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "beneficiary" in data
    assert data["beneficiary"]["name"] == "Alice Friend"
    assert data["beneficiary"]["email"] == "alice@example.com"

    # Check DB
    b = beneficiaries_col.find_one({"user_id": ObjectId(u_id), "email": "alice@example.com"})
    assert b is not None
    assert b["nickname"] == "Ali"


def test_add_beneficiary_validation_and_duplicate(client):
    u_id = setup_user(email="me@example.com")
    login_session(client, u_id, email="me@example.com")

    # Missing fields
    res_miss = client.post("/api/beneficiaries", json={"name": ""})
    assert res_miss.status_code == 400

    # Invalid email format
    res_inv = client.post("/api/beneficiaries", json={"name": "Bad", "email": "not-an-email"})
    assert res_inv.status_code == 400

    # Self-beneficiary forbidden
    res_self = client.post("/api/beneficiaries", json={"name": "Myself", "email": "me@example.com"})
    assert res_self.status_code == 400
    assert "own account" in res_self.get_json()["error"]

    # Valid add
    res_ok = client.post("/api/beneficiaries", json={"name": "Bob", "email": "bob@example.com"})
    assert res_ok.status_code == 200

    # Duplicate add
    res_dup = client.post("/api/beneficiaries", json={"name": "Bob", "email": "bob@example.com"})
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.get_json()["error"]


def test_list_and_delete_beneficiary_idor(client):
    u1_id = setup_user(email="u1@example.com")
    u2_id = setup_user(email="u2@example.com")

    # User 1 adds beneficiary
    login_session(client, u1_id, email="u1@example.com")
    res1 = client.post("/api/beneficiaries", json={"name": "U1 Contact", "email": "contact1@example.com"})
    b1_id = res1.get_json()["beneficiary"]["id"]

    # User 2 adds beneficiary
    login_session(client, u2_id, email="u2@example.com")
    res2 = client.post("/api/beneficiaries", json={"name": "U2 Contact", "email": "contact2@example.com"})
    b2_id = res2.get_json()["beneficiary"]["id"]

    # User 2 lists beneficiaries - must only see their own
    list_res = client.get("/api/beneficiaries")
    assert list_res.status_code == 200
    b_list = list_res.get_json()["beneficiaries"]
    assert len(b_list) == 1
    assert b_list[0]["id"] == b2_id

    # User 2 attempts to delete User 1's beneficiary (IDOR attack)
    del_idor = client.delete(f"/api/beneficiaries/{b1_id}")
    assert del_idor.status_code == 400
    assert "not found or not owned" in del_idor.get_json()["error"]

    # User 2 deletes own beneficiary
    del_own = client.delete(f"/api/beneficiaries/{b2_id}")
    assert del_own.status_code == 200
    assert beneficiaries_col.find_one({"_id": ObjectId(b2_id)}) is None
