"""Admin endpoint tests — covers user management, data plans, promos, overview, and exports."""

import pytest

from .conftest import API, DEMO_EMAIL, DEMO_PHONE, DEMO_PASSWORD


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def admin_headers(client):
    """Login as the demo user (who is in ADMIN_EMAILS) and return auth headers."""
    r = client.post(f"{API}/auth/login", json={"phone": DEMO_PHONE, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture()
def second_user(client, new_user):
    """Register a second non-admin user and return (headers, user_id)."""
    headers, _ = new_user(999)
    r = client.get(f"{API}/users/me", headers=headers)
    uid = r.json()["data"]["id"]
    return headers, uid


# ── overview ──────────────────────────────────────────────────────────────


class TestOverview:
    def test_overview_shape(self, client, admin_headers):
        r = client.get(f"{API}/admin/overview", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert "total_users" in d
        assert "active_users" in d
        assert "total_wallet_balance_kobo" in d
        assert "transactions_by_status" in d

    def test_overview_requires_admin(self, client, auth_headers):
        r = client.get(f"{API}/admin/overview", headers=auth_headers)
        assert r.status_code == 403

    def test_overview_requires_auth(self, client):
        r = client.get(f"{API}/admin/overview")
        assert r.status_code == 401


# ── user management ───────────────────────────────────────────────────────


class TestAdminUsers:
    def test_list_users(self, client, admin_headers):
        r = client.get(f"{API}/admin/users", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_search_users(self, client, admin_headers):
        r = client.get(f"{API}/admin/users?q=adaeze", headers=admin_headers)
        assert r.status_code == 200

    def test_fund_user_wallet(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.post(f"{API}/admin/users/{uid}/fund", headers=admin_headers, json={"amount_naira": 100})
        assert r.status_code == 200
        assert r.json()["success"]

    def test_fund_user_minimum(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.post(f"{API}/admin/users/{uid}/fund", headers=admin_headers, json={"amount_naira": 10})
        assert r.status_code == 422 or r.status_code == 400

    def test_debit_user_wallet(self, client, admin_headers, second_user):
        _, uid = second_user
        # first fund
        client.post(f"{API}/admin/users/{uid}/fund", headers=admin_headers, json={"amount_naira": 200})
        # then debit
        r = client.post(f"{API}/admin/users/{uid}/debit", headers=admin_headers, json={"amount_naira": 50})
        assert r.status_code == 200
        assert r.json()["success"]

    def test_block_user(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.patch(f"{API}/admin/users/{uid}/status", headers=admin_headers, json={"is_active": False})
        assert r.status_code == 200

    def test_edit_user(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.patch(f"{API}/admin/users/{uid}", headers=admin_headers, json={"full_name": "Updated Name"})
        assert r.status_code == 200

    def test_reset_password(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.post(f"{API}/admin/users/{uid}/reset-password", headers=admin_headers, json={"new_password": "NewPass123!"})
        assert r.status_code == 200

    def test_reset_pin(self, client, admin_headers, second_user):
        _, uid = second_user
        r = client.post(f"{API}/admin/users/{uid}/reset-pin", headers=admin_headers, json={"new_pin": "5678"})
        assert r.status_code == 200

    def test_user_not_found(self, client, admin_headers):
        r = client.patch(f"{API}/admin/users/999999/status", headers=admin_headers, json={"is_active": False})
        assert r.status_code == 404


# ── data plan management ──────────────────────────────────────────────────


class TestAdminDataPlans:
    def test_list_plans(self, client, admin_headers):
        r = client.get(f"{API}/admin/data-plans", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, list)

    def test_list_categories(self, client, admin_headers):
        r = client.get(f"{API}/admin/data-plans/categories", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_create_plan(self, client, admin_headers):
        payload = {
            "network_code": "mtn",
            "plan_code": "test-admin-plan-001",
            "name": "Test Admin Plan",
            "category": "Test",
            "volume_mb": 500,
            "validity_days": 7,
            "selling_price_kobo": 50000,
            "buying_price_kobo": 40000,
            "promo_price_kobo": 45000,
            "is_active": True,
        }
        r = client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        assert r.status_code == 200
        assert r.json()["success"]

    def test_duplicate_plan_code_rejected(self, client, admin_headers):
        payload = {
            "network_code": "mtn",
            "plan_code": "test-dup-plan",
            "name": "Dup Plan",
            "category": "Test",
            "volume_mb": 100,
            "validity_days": 1,
            "selling_price_kobo": 10000,
            "is_active": True,
        }
        r1 = client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        assert r1.status_code == 200
        r2 = client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        assert r2.status_code == 409

    def test_edit_plan(self, client, admin_headers):
        # create first
        payload = {
            "network_code": "mtn",
            "plan_code": "test-edit-plan",
            "name": "Edit Me",
            "category": "Test",
            "volume_mb": 100,
            "validity_days": 1,
            "selling_price_kobo": 10000,
            "is_active": True,
        }
        client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        # edit
        r = client.put(f"{API}/admin/data-plans/test-edit-plan", headers=admin_headers, json={
            "name": "Edited Plan",
            "selling_price_kobo": 15000,
        })
        assert r.status_code == 200

    def test_delete_plan(self, client, admin_headers):
        payload = {
            "network_code": "mtn",
            "plan_code": "test-delete-plan",
            "name": "Delete Me",
            "category": "Test",
            "volume_mb": 100,
            "validity_days": 1,
            "selling_price_kobo": 10000,
            "is_active": True,
        }
        client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        r = client.delete(f"{API}/admin/data-plans/test-delete-plan", headers=admin_headers)
        assert r.status_code == 200

    def test_patch_plan_price(self, client, admin_headers):
        payload = {
            "network_code": "mtn",
            "plan_code": "test-patch-price",
            "name": "Patch Price",
            "category": "Test",
            "volume_mb": 100,
            "validity_days": 1,
            "selling_price_kobo": 10000,
            "is_active": True,
        }
        client.post(f"{API}/admin/data-plans", headers=admin_headers, json=payload)
        r = client.patch(f"{API}/admin/data-plans/test-patch-price", headers=admin_headers, json={
            "selling_price_kobo": 12000,
            "promo_price_kobo": 11000,
        })
        assert r.status_code == 200

    def test_disabled_categories(self, client, admin_headers):
        # list
        r = client.get(f"{API}/admin/data-plans/disabled-categories", headers=admin_headers)
        assert r.status_code == 200
        # toggle
        r = client.post(f"{API}/admin/data-plans/disabled-categories/toggle", headers=admin_headers, json={
            "network_code": "mtn",
            "category": "Test",
        })
        assert r.status_code == 200
        # verify it's now disabled
        cats = client.get(f"{API}/admin/data-plans/disabled-categories", headers=admin_headers).json()["data"]
        assert any(c["category"] == "Test" and c["network_code"] == "mtn" for c in cats)
        # toggle back
        client.post(f"{API}/admin/data-plans/disabled-categories/toggle", headers=admin_headers, json={
            "network_code": "mtn",
            "category": "Test",
        })


# ── promo code management ─────────────────────────────────────────────────


class TestAdminPromos:
    def test_create_promo(self, client, admin_headers):
        r = client.post(f"{API}/admin/promos", headers=admin_headers, json={
            "code": "TESTPROMO10",
            "discount_percent": 10,
            "max_uses": 100,
            "is_active": True,
        })
        assert r.status_code == 200
        assert r.json()["success"]

    def test_list_promos(self, client, admin_headers):
        r = client.get(f"{API}/admin/promos", headers=admin_headers)
        assert r.status_code == 200

    def test_validate_promo(self, client, admin_headers):
        client.post(f"{API}/admin/promos", headers=admin_headers, json={
            "code": "VALIDATEME",
            "discount_percent": 5,
            "max_uses": 10,
            "is_active": True,
        })
        r = client.get(f"{API}/admin/promos/validate/VALIDATEME", headers=admin_headers)
        assert r.status_code == 200

    def test_update_promo(self, client, admin_headers):
        r = client.post(f"{API}/admin/promos", headers=admin_headers, json={
            "code": "UPDATEPROMO",
            "discount_percent": 5,
            "max_uses": 10,
            "is_active": True,
        })
        promo_id = r.json()["data"]["id"]
        r = client.patch(f"{API}/admin/promos/{promo_id}", headers=admin_headers, json={
            "discount_percent": 15,
        })
        assert r.status_code == 200

    def test_delete_promo(self, client, admin_headers):
        r = client.post(f"{API}/admin/promos", headers=admin_headers, json={
            "code": "DELETEPROMO",
            "discount_percent": 5,
            "max_uses": 10,
            "is_active": True,
        })
        promo_id = r.json()["data"]["id"]
        r = client.delete(f"{API}/admin/promos/{promo_id}", headers=admin_headers)
        assert r.status_code == 200


# ── transactions ──────────────────────────────────────────────────────────


class TestAdminTransactions:
    def test_list_transactions(self, client, admin_headers):
        r = client.get(f"{API}/admin/transactions", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data

    def test_filter_by_status(self, client, admin_headers):
        r = client.get(f"{API}/admin/transactions?status=successful", headers=admin_headers)
        assert r.status_code == 200

    def test_export_transactions_json(self, client, admin_headers):
        r = client.get(f"{API}/admin/transactions/export?format=json", headers=admin_headers)
        assert r.status_code == 200

    def test_export_users_json(self, client, admin_headers):
        r = client.get(f"{API}/admin/users/export?format=json", headers=admin_headers)
        assert r.status_code == 200


# ── webhook config ─────────────────────────────────────────────────────────


class TestAdminWebhook:
    def test_get_webhook(self, client, admin_headers):
        r = client.get(f"{API}/admin/webhook", headers=admin_headers)
        assert r.status_code == 200

    def test_set_webhook(self, client, admin_headers):
        r = client.put(f"{API}/admin/webhook", headers=admin_headers, json={
            "url": "https://example.com/webhook",
        })
        assert r.status_code == 200

    def test_invalid_webhook_url(self, client, admin_headers):
        r = client.put(f"{API}/admin/webhook", headers=admin_headers, json={
            "url": "not-a-url",
        })
        assert r.status_code in (400, 422)


# ── site settings ─────────────────────────────────────────────────────────


class TestAdminSiteSettings:
    def test_get_settings(self, client, admin_headers):
        r = client.get(f"{API}/admin/site-settings", headers=admin_headers)
        assert r.status_code == 200

    def test_update_settings(self, client, admin_headers):
        r = client.put(f"{API}/admin/site-settings", headers=admin_headers, json={
            "site_name": "Test Zaply",
        })
        assert r.status_code == 200

    def test_public_settings_no_auth(self, client):
        r = client.get(f"{API}/admin/site-settings/public")
        assert r.status_code == 200
