"""Shared fixtures.

The test database is a throwaway SQLite file created fresh for each pytest
session; the env var is set *before* any app import so the engine picks it up.
"""

import os
import tempfile

_TEST_DIR = tempfile.mkdtemp(prefix="zaply-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
os.environ.setdefault("SEED_DEMO_DATA", "true")
# tests always run against the deterministic sandbox adapter, never a live one
os.environ.setdefault("VTU_PROVIDER", "mock")

import hmac as hmac_mod  # noqa: E402
import hashlib  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.ratelimit import rate_limiter  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
DEMO_PHONE = "08012345678"
DEMO_EMAIL = "demo@zaply.ng"
DEMO_PASSWORD = "Demo1234!"
DEMO_PIN = "1234"


def webhook_sign(body: bytes) -> str:
    return hmac_mod.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    rate_limiter._hits.clear()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture()
def balance(client, auth_headers):
    def get() -> int:
        r = client.get(f"{API}/wallet", headers=auth_headers)
        assert r.status_code == 200
        return r.json()["data"]["balance_kobo"]

    return get


@pytest.fixture()
def new_user(client):
    """Register a fresh user; returns (headers, pin)."""

    def make(idx: int):
        payload = {
            "full_name": f"Test User {idx}",
            "email": f"test-user-{idx}@example.com",
            "phone": f"080{idx:08d}",
            "password": "Passw0rd!23",
        }
        r = client.post(f"{API}/auth/register", json=payload)
        assert r.status_code == 200, r.text
        token = r.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}, DEMO_PIN

    return make
