from .conftest import API


def test_history_returns_items_with_meta(client, auth_headers):
    r = client.get(f"{API}/transactions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["data"]["items"], list)
    meta = body["data"]["meta"]
    assert {"page", "per_page", "total", "total_pages"} <= set(meta)


def test_history_pagination(client, auth_headers):
    r = client.get(f"{API}/transactions", params={"page": 1, "per_page": 2}, headers=auth_headers)
    items = r.json()["data"]["items"]
    assert len(items) <= 2


def test_receipt_lookup(client, auth_headers):
    txns = client.get(f"{API}/transactions", headers=auth_headers).json()["data"]["items"]
    ref = txns[0]["reference"]
    r = client.get(f"{API}/transactions/{ref}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["reference"] == ref


def test_receipt_lookup_unknown_reference(client, auth_headers):
    r = client.get(f"{API}/transactions/ZP-XXX-DOES-NOT-EXIST", headers=auth_headers)
    assert r.status_code == 404


def test_verify_endpoint(client, auth_headers):
    txns = client.get(f"{API}/transactions", headers=auth_headers).json()["data"]["items"]
    successful = next(t for t in txns if t["status"] == "successful")
    r = client.post(f"{API}/transactions/{successful['reference']}/verify", headers=auth_headers)
    assert r.status_code == 200


def test_notifications_list_and_mark_read(client, auth_headers):
    r = client.get(f"{API}/notifications", headers=auth_headers)
    assert r.status_code == 200
    notifs = r.json()["data"]["items"]
    assert isinstance(notifs, list)

    if notifs:
        nid = notifs[0]["id"]
        one = client.post(f"{API}/notifications/{nid}/read", headers=auth_headers)
        assert one.status_code == 200

    read_all = client.post(f"{API}/notifications/read-all", headers=auth_headers)
    assert read_all.status_code == 200
