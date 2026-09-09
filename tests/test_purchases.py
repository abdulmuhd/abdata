from .conftest import API, DEMO_PIN


def _buy_airtime(client, headers, **overrides):
    payload = {"network_code": "mtn", "phone": "08012345678", "amount_naira": 100, "pin": "1111"}
    payload.update(overrides)
    return client.post(f"{API}/airtime/purchase", headers=headers, json=payload)


def test_airtime_purchase_debits_wallet(client, auth_headers, balance):
    before = balance()
    r = _buy_airtime(client, auth_headers, amount_naira=200)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "successful"
    assert balance() == before - data["amount_kobo"] - data.get("fee_kobo", 0)


def test_airtime_wrong_pin_rejected(client, auth_headers, balance):
    before = balance()
    r = _buy_airtime(client, auth_headers, pin="9999")
    assert r.status_code == 400
    assert "PIN" in r.json()["message"]
    assert balance() == before


def test_data_purchase_validates_plan(client, auth_headers, balance):
    plans = client.get(f"{API}/data/plans", params={"network": "mtn"}, headers=auth_headers)
    assert plans.status_code == 200
    plan = next(p for cat in plans.json()["data"].values() for p in cat)

    before = balance()
    r = client.post(
        f"{API}/data/purchase",
        headers=auth_headers,
        json={"network_code": "mtn", "phone": "08012345678", "plan_code": plan["plan_code"], "pin": "1111"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["amount_kobo"] == plan["price_kobo"]
    assert balance() == before - plan["price_kobo"] - data.get("fee_kobo", 0)


def test_data_purchase_unknown_plan_rejected(client, auth_headers):
    r = client.post(
        f"{API}/data/purchase",
        headers=auth_headers,
        json={"network_code": "mtn", "phone": "08012345678", "plan_code": "nope-999", "pin": "1111"},
    )
    assert r.status_code in (400, 404)


def test_electricity_validate_and_pay_minimum(client, auth_headers, balance):
    v = client.post(
        f"{API}/electricity/validate",
        headers=auth_headers,
        json={"provider_code": "ekedc", "meter_number": "12345678901", "meter_type": "prepaid"},
    )
    assert v.status_code == 200
    assert v.json()["data"]["found"] is True

    below = client.post(
        f"{API}/electricity/pay",
        headers=auth_headers,
        json={
            "provider_code": "ekedc",
            "meter_number": "12345678901",
            "meter_type": "prepaid",
            "amount_naira": 500,
            "pin": "1111",
        },
    )
    assert below.status_code == 400

    before = balance()
    ok = client.post(
        f"{API}/electricity/pay",
        headers=auth_headers,
        json={
            "provider_code": "ekedc",
            "meter_number": "12345678901",
            "meter_type": "prepaid",
            "amount_naira": 1000,
            "pin": "1111",
        },
    )
    assert ok.status_code == 200
    assert balance() == before - ok.json()["data"]["amount_kobo"]


def test_cable_validate_and_pay(client, auth_headers, balance):
    v = client.post(
        f"{API}/cable/validate",
        headers=auth_headers,
        json={"provider_code": "dstv", "smartcard_number": "7042133785"},
    )
    assert v.status_code == 200
    assert v.json()["data"]["found"] is True

    pkgs = client.get(f"{API}/cable/packages", params={"provider": "dstv"}, headers=auth_headers)
    assert pkgs.status_code == 200
    pkg = pkgs.json()["data"][0]

    before = balance()
    r = client.post(
        f"{API}/cable/pay",
        headers=auth_headers,
        json={
            "provider_code": "dstv",
            "smartcard_number": "7042133785",
            "package_code": pkg["package_code"],
            "pin": "1111",
        },
    )
    assert r.status_code == 200
    assert balance() == before - r.json()["data"]["amount_kobo"]


def test_insufficient_funds_blocked(client, new_user):
    headers, pin = new_user(1)  # fresh wallet = ₦0
    # set a non-default PIN (avoid "1234" which is the default)
    r = client.put(f"{API}/users/me/pin", headers=headers, json={"new_pin": "1111"})
    assert r.status_code == 200

    r = client.post(
        f"{API}/airtime/purchase",
        headers=headers,
        json={"network_code": "mtn", "phone": "08012345678", "amount_naira": 100, "pin": "1111"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "insufficient_funds"


def test_invalid_network_rejected(client, auth_headers):
    r = _buy_airtime(client, auth_headers, network_code="not-a-network")
    assert r.status_code in (400, 404)


def test_malformed_phone_rejected(client, auth_headers):
    r = _buy_airtime(client, auth_headers, phone="123")
    assert r.status_code == 422
