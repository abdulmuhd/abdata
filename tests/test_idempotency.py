from .conftest import API, DEMO_PIN


def test_same_idempotency_key_returns_same_reference(client, auth_headers):
    key = {"idempotency_key": "itest-001"}
    payload = {**key, "network_code": "mtn", "phone": "08111111111", "amount_naira": 50, "pin": DEMO_PIN}

    r1 = client.post(f"{API}/airtime/purchase", headers=auth_headers, json=payload)
    r2 = client.post(f"{API}/airtime/purchase", headers=auth_headers, json=payload)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["reference"] == r2.json()["data"]["reference"]


def test_different_keys_create_distinct_purchases(client, auth_headers):
    base = {"network_code": "mtn", "phone": "08122222222", "amount_naira": 50, "pin": DEMO_PIN}

    r1 = client.post(f"{API}/airtime/purchase", headers=auth_headers, json={**base, "idempotency_key": "k-a"})
    r2 = client.post(f"{API}/airtime/purchase", headers=auth_headers, json={**base, "idempotency_key": "k-b"})

    refs = {r1.json()["data"]["reference"], r2.json()["data"]["reference"]}
    assert len(refs) == 2
