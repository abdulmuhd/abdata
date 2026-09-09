import json

from .conftest import API, webhook_sign


def test_wallet_shape(client, auth_headers):
    r = client.get(f"{API}/wallet", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["balance_kobo"], int)
    assert data["currency"] == "NGN"


def test_fund_init_and_settle_credits_once(client, auth_headers, balance):
    before = balance()

    r = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 1000})
    assert r.status_code == 200
    init = r.json()["data"]
    assert init["amount_kobo"] == 100_000
    assert init["gateway"] == "mock"
    assert init["reference"].startswith("ZP-FND-")

    r = client.post(f"{API}/wallet/fund/settle", headers=auth_headers, params={"reference": init["reference"]})
    assert r.status_code == 200

    assert balance() == before + 100_000


def test_settle_is_idempotent_no_double_credit(client, auth_headers, balance):
    before = balance()
    init = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 500}).json()["data"]

    first = client.post(f"{API}/wallet/fund/settle", headers=auth_headers, params={"reference": init["reference"]})
    second = client.post(f"{API}/wallet/fund/settle", headers=auth_headers, params={"reference": init["reference"]})

    assert first.status_code == 200 and second.status_code == 200
    assert balance() == before + 50_000


def test_funding_status_lookup(client, auth_headers):
    init = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 750}).json()["data"]
    r = client.get(f"{API}/wallet/funding/{init['reference']}", headers=auth_headers)
    assert r.status_code == 200


def test_fund_rejects_below_minimum(client, auth_headers):
    r = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 10})
    assert r.status_code == 422


def test_webhook_settles_funding(client, auth_headers, balance):
    before = balance()
    init = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 2000}).json()["data"]
    ref = init["reference"]

    payload = json.dumps(
        {"event": "charge.success", "data": {"reference": ref, "provider_reference": "GW-TEST-1"}}
    ).encode()

    bad = client.post(f"{API}/webhooks/payment", content=payload, headers={"X-Zaply-Signature": "deadbeef"})
    assert bad.status_code == 401

    ok = client.post(f"{API}/webhooks/payment", content=payload, headers={"X-Zaply-Signature": webhook_sign(payload)})
    assert ok.status_code == 200
    assert ok.json()["settled"] is True
    assert balance() == before + 200_000


def test_webhook_replay_does_not_double_credit(client, auth_headers, balance):
    before = balance()
    init = client.post(f"{API}/wallet/fund", headers=auth_headers, json={"amount_naira": 300}).json()["data"]

    payload = json.dumps({"event": "charge.success", "data": {"reference": init["reference"]}}).encode()
    sig = {"X-Zaply-Signature": webhook_sign(payload)}

    assert client.post(f"{API}/webhooks/payment", content=payload, headers=sig).status_code == 200
    replay = client.post(f"{API}/webhooks/payment", content=payload, headers=sig)
    assert replay.status_code == 200
    assert replay.json()["settled"] is False
    assert balance() == before + 30_000


def test_webhook_malformed_payload_with_valid_signature(client):
    payload = b'{"event": "something.else"}'
    r = client.post(
        f"{API}/webhooks/payment",
        content=payload,
        headers={"X-Zaply-Signature": webhook_sign(payload)},
    )
    assert r.status_code == 400
