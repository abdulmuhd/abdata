"""P2P transfer tests."""

import pytest

from .conftest import API, DEMO_PHONE, DEMO_PASSWORD, DEMO_PIN


@pytest.fixture()
def funded_user(client, new_user):
    """Register a fresh user, fund their wallet, return (headers, pin)."""
    headers, pin = new_user(500)
    # fund the user via admin (login as demo admin first)
    admin_r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    admin_headers = {"Authorization": f"Bearer {admin_r.json()['data']['access_token']}"}
    me = client.get(f"{API}/users/me", headers=headers)
    uid = me.json()["data"]["id"]
    client.post(f"{API}/admin/users/{uid}/fund", headers=admin_headers, json={"amount_naira": 500})
    return headers, pin


@pytest.fixture()
def recipient_user(client, new_user):
    """Register a recipient user, return (headers, phone)."""
    headers, _ = new_user(600)
    me = client.get(f"{API}/users/me", headers=headers)
    phone = me.json()["data"]["phone"]
    return headers, phone


class TestTransferLookup:
    def test_lookup_recipient(self, client, funded_user, recipient_user):
        _, recipient_phone = recipient_user
        headers, _ = funded_user
        r = client.get(f"{API}/transfer/recipient/{recipient_phone}", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "name" in data
        assert data["phone"]

    def test_lookup_unknown_recipient(self, client, funded_user):
        headers, _ = funded_user
        r = client.get(f"{API}/transfer/recipient/08099999999", headers=headers)
        assert r.status_code == 404


class TestTransferSend:
    def test_send_money(self, client, funded_user, recipient_user):
        headers, pin = funded_user
        _, recipient_phone = recipient_user
        r = client.post(f"{API}/transfer/send", headers=headers, json={
            "recipient_phone": recipient_phone,
            "amount_naira": 200,
            "pin": pin,
        })
        assert r.status_code == 200
        assert r.json()["success"]

    def test_send_wrong_pin(self, client, funded_user, recipient_user):
        headers, _ = funded_user
        _, recipient_phone = recipient_user
        r = client.post(f"{API}/transfer/send", headers=headers, json={
            "recipient_phone": recipient_phone,
            "amount_naira": 200,
            "pin": "0000",
        })
        assert r.status_code in (400, 401, 403)

    def test_send_insufficient_funds(self, client, funded_user, recipient_user):
        headers, pin = funded_user
        _, recipient_phone = recipient_user
        r = client.post(f"{API}/transfer/send", headers=headers, json={
            "recipient_phone": recipient_phone,
            "amount_naira": 5000,
            "pin": pin,
        })
        assert r.status_code in (400, 402)

    def test_send_below_minimum(self, client, funded_user, recipient_user):
        headers, pin = funded_user
        _, recipient_phone = recipient_user
        r = client.post(f"{API}/transfer/send", headers=headers, json={
            "recipient_phone": recipient_phone,
            "amount_naira": 50,
            "pin": pin,
        })
        assert r.status_code == 422

    def test_send_to_self(self, client, funded_user):
        headers, pin = funded_user
        me = client.get(f"{API}/users/me", headers=headers)
        my_phone = me.json()["data"]["phone"]
        r = client.post(f"{API}/transfer/send", headers=headers, json={
            "recipient_phone": my_phone,
            "amount_naira": 200,
            "pin": pin,
        })
        assert r.status_code in (400, 409)
