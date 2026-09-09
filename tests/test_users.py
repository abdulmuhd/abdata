from .conftest import API


def test_me_profile(client, auth_headers):
    r = client.get(f"{API}/users/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["email"] == "demo@zaply.ng"


def test_dashboard_aggregate(client, auth_headers):
    r = client.get(f"{API}/users/me/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "wallet" in data or "balance_kobo" in str(data)


def test_update_profile(client, new_user):
    headers, _ = new_user(2)
    r = client.patch(f"{API}/users/me", headers=headers, json={"full_name": "Renamed User"})
    assert r.status_code == 200
    assert client.get(f"{API}/users/me", headers=headers).json()["data"]["full_name"] == "Renamed User"


def test_change_password_requires_current(client, new_user):
    headers, _ = new_user(3)
    r = client.put(
        f"{API}/users/me/password",
        headers=headers,
        json={"current_password": "wrong-current", "new_password": "NewPassw0rd!"},
    )
    assert r.status_code in (400, 401)


def test_change_password_then_login_with_new(client):
    # register via API so we know the current password
    payload = {
        "full_name": "Pass Changer",
        "email": "pass-change@example.com",
        "phone": "08130000001",
        "password": "OldPassw0rd!",
    }
    reg = client.post(f"{API}/auth/register", json=payload)
    headers = {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}

    r = client.put(
        f"{API}/users/me/password",
        headers=headers,
        json={"current_password": payload["password"], "new_password": "NewPassw0rd!"},
    )
    assert r.status_code == 200

    old_login = client.post(f"{API}/auth/login", json={"identifier": payload["email"], "password": payload["password"]})
    new_login = client.post(f"{API}/auth/login", json={"identifier": payload["email"], "password": "NewPassw0rd!"})
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_change_pin_and_purchase_with_it(client, auth_headers):
    r = client.put(f"{API}/users/me/pin", headers=auth_headers, json={"current_pin": "1234", "new_pin": "4321"})
    assert r.status_code == 200

    buy = client.post(
        f"{API}/airtime/purchase",
        headers=auth_headers,
        json={"network_code": "mtn", "phone": "08012345678", "amount_naira": 50, "pin": "4321"},
    )
    assert buy.status_code == 200

    # restore original PIN for other tests / demo parity
    back = client.put(f"{API}/users/me/pin", headers=auth_headers, json={"current_pin": "4321", "new_pin": "1234"})
    assert back.status_code == 200


def test_pin_wrong_current_rejected(client, auth_headers):
    r = client.put(f"{API}/users/me/pin", headers=auth_headers, json={"current_pin": "0000", "new_pin": "5678"})
    assert r.status_code in (400, 401, 403)
