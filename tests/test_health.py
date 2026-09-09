from .conftest import API


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


def test_frontend_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
