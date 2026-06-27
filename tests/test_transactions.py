import os

import pytest

os.environ["USE_MOCK_DB"] = "1"

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def signup_user(client, email="user@example.com", password="secret123"):
    return client.post(
        "/api/signup",
        json={"name": "Test User", "email": email, "password": password, "pin": "1234"},
    )


def login_user(client, email="user@example.com", password="secret123"):
    return client.post("/api/login", json={"email": email, "password": password})


def test_deposit_with_invalid_amount(client):
    response = client.post(
        "/api/deposit",
        json={"account_id": "507f1f77bcf86cd799439011", "amount": -10},
    )
    assert response.status_code in (400, 401)


def test_withdraw_with_invalid_amount(client):
    response = client.post(
        "/api/withdraw",
        json={"account_id": "507f1f77bcf86cd799439011", "amount": 0},
    )
    assert response.status_code in (400, 401)


def test_transfer_requires_receiver(client):
    response = client.post("/api/transfer", json={"amount": 100})
    assert response.status_code in (400, 401)


def test_signup_and_login_flow(client):
    signup = signup_user(client)
    assert signup.status_code == 200
    login = login_user(client)
    assert login.status_code in (200, 403)


def test_password_reset_flow(client):
    signup_user(client, email="reset@example.com")
    response = client.post("/api/password/forgot", json={"email": "reset@example.com"})
    assert response.status_code == 200
