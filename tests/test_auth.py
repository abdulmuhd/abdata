import pytest

from .conftest import API, DEMO_EMAIL, DEMO_PHONE, DEMO_PASSWORD


def test_login_success(client):
    r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": "nope-nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_login_unknown_user(client):
    r = client.post(f"{API}/auth/login", json={"phone": "08099999999", "password": "whatever1"})
    assert r.status_code == 401


def test_register_returns_token_pair_and_wallet(client):
    payload = {
        "full_name": "Ada Tester",
        "email": "ada-register@example.com",
        "phone": "08100000001",
        "password": "Passw0rd!23",
    }
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["access_token"]
    assert data["email_verification"]["required"] is True

    # wallet exists and starts at zero
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    w = client.get(f"{API}/wallet", headers=headers)
    assert w.status_code == 200
    assert w.json()["data"]["balance_kobo"] == 0


def test_register_duplicate_email_conflict(client):
    payload = {
        "full_name": "Dup User",
        "email": DEMO_EMAIL,
        "phone": "08100000002",
        "password": "Passw0rd!23",
    }
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 409


def test_register_duplicate_phone_conflict(client):
    payload = {
        "full_name": "Dup User 2",
        "email": "dup-phone@example.com",
        "phone": "08012345678",
        "password": "Passw0rd!23",
    }
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 409


def test_register_short_password_rejected(client):
    payload = {
        "full_name": "Shorty",
        "email": "shorty@example.com",
        "phone": "08100000003",
        "password": "short",
    }
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 422


def test_refresh_flow(client):
    login = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    refresh = login.json()["data"]["refresh_token"]

    r = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_pair = r.json()["data"]
    assert new_pair["access_token"]

    # old access token should still verify within its TTL; new one must work too
    for tok in (login.json()["data"]["access_token"], new_pair["access_token"]):
        me = client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200


def test_refresh_with_garbage_token(client):
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401


def test_protected_route_without_token(client):
    r = client.get(f"{API}/users/me")
    assert r.status_code == 401


def test_protected_route_with_bad_token(client):
    r = client.get(f"{API}/users/me", headers={"Authorization": "Bearer tampered.token.value"})
    assert r.status_code == 401


@pytest.mark.parametrize("field", ["email", "phone", "full_name", "password"])
def test_register_missing_field_422(client, field):
    payload = {
        "full_name": "Missing Field",
        "email": "missing-field@example.com",
        "phone": "08100000004",
        "password": "Passw0rd!23",
    }
    del payload[field]
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 422
