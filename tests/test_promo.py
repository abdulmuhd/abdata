"""Promo code validation tests (user-facing)."""

import pytest

from .conftest import API, DEMO_PHONE, DEMO_PASSWORD


@pytest.fixture()
def admin_headers(client):
    r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


class TestPromoValidation:
    def _create_promo(self, client, admin_headers, **kwargs):
        defaults = {
            "code": "TESTPROMO",
            "discount_percent": 10,
            "max_uses": 100,
            "is_active": True,
        }
        defaults.update(kwargs)
        r = client.post(f"{API}/admin/promos", headers=admin_headers, json=defaults)
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def test_valid_promo(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="VALID10", discount_percent=10)
        r = client.get(f"{API}/admin/promos/validate/VALID10?amount_kobo=10000", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["code"] == "VALID10"
        assert data["discount_kobo"] == 1000  # 10% of 10000

    def test_fixed_discount_promo(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="FIXED500", discount_kobo=50000, discount_percent=0)
        r = client.get(f"{API}/admin/promos/validate/FIXED500?amount_kobo=100000", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["data"]["discount_kobo"] == 50000

    def test_inactive_promo_rejected(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="INACTIVE", discount_percent=10, is_active=False)
        r = client.get(f"{API}/admin/promos/validate/INACTIVE?amount_kobo=10000", headers=admin_headers)
        assert r.status_code == 404

    def test_unknown_promo_rejected(self, client, admin_headers):
        r = client.get(f"{API}/admin/promos/validate/DOESNOTEXIST?amount_kobo=10000", headers=admin_headers)
        assert r.status_code == 404

    def test_promo_below_min_amount(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="MINAMT", discount_percent=10, min_amount_kobo=50000)
        r = client.get(f"{API}/admin/promos/validate/MINAMT?amount_kobo=10000", headers=admin_headers)
        assert r.status_code == 404

    def test_promo_discount_cannot_exceed_amount(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="BIGDISC", discount_percent=90)
        r = client.get(f"{API}/admin/promos/validate/BIGDISC?amount_kobo=1000", headers=admin_headers)
        assert r.status_code == 200
        # 90% of 1000 = 900, which is less than 1000, so discount is 900
        assert r.json()["data"]["discount_kobo"] == 900

    def test_expired_promo_rejected(self, client, admin_headers):
        from datetime import datetime, timedelta, timezone
        self._create_promo(client, admin_headers, code="EXPIRED", discount_percent=10,
                           expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
        r = client.get(f"{API}/admin/promos/validate/EXPIRED?amount_kobo=10000", headers=admin_headers)
        assert r.status_code == 404

    def test_max_uses_promo(self, client, admin_headers):
        self._create_promo(client, admin_headers, code="MAXUSES", discount_percent=10, max_uses=2)
        # first two validations should work
        r1 = client.get(f"{API}/admin/promos/validate/MAXUSES?amount_kobo=10000", headers=admin_headers)
        assert r1.status_code == 200
        # use it twice via apply
        client.post(f"{API}/admin/promos", headers=admin_headers, json={
            "code": "MAXUSES", "discount_percent": 10, "max_uses": 2, "is_active": True,
        })
        # manually set used_count to max
        from app.core.database import get_db
        from app.models.promo import PromoCode
        with client.app.dependency_overrides.get(get_db, lambda: None)() as db:
            if db:
                promo = db.query(PromoCode).filter(PromoCode.code == "MAXUSES").first()
                if promo:
                    promo.used_count = 2
                    db.commit()
        # now it should be rejected
        r2 = client.get(f"{API}/admin/promos/validate/MAXUSES?amount_kobo=10000", headers=admin_headers)
        assert r2.status_code == 404
