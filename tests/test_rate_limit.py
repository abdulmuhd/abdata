from .conftest import API


def test_login_rate_limited_after_burst(client):
    """The 11th login attempt from the same IP within the window is throttled."""
    for _ in range(10):
        r = client.post(f"{API}/auth/login", json={"phone": "08099999999", "password": "wrong-pass"})
        assert r.status_code == 401

    r = client.post(f"{API}/auth/login", json={"phone": "08099999999", "password": "wrong-pass"})
    assert r.status_code == 429
    assert r.json()["code"] == "rate_limited"
