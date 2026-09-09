"""Generic VTU provider adapter — reads configuration from API Manager database.

Works with any provider added via API Manager as long as it follows
common VTU API patterns:
  - Auth via Bearer token or API key
  - Data plans in response with 'Dataplans' key or similar structure
  - Standard purchase endpoints

Configuration is read from:
  - ApiProvider (base_url, code)
  - ApiProviderCredential (auth tokens, keys)
  - ApiProviderEndpoint (paths for operations)
"""

import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ...core.errors import ProviderError
from ...core.config import settings
from ...core.encryption import decrypt
from ...models import ApiProvider, ApiProviderCredential, ApiProviderEndpoint
from ...models.enums import MeterType
from .base import BaseVtuProvider, CustomerInfo, ProviderResult, register_provider

NETWORK_IDS = {"mtn": 1, "glo": 2, "9mobile": 3, "airtel": 4}
NETWORK_IDS_R = {1: "mtn", 2: "glo", 3: "9mobile", 4: "airtel"}

_SUCCESS = {"success", "successful", "delivered", "completed", "true"}
_PENDING = {"processing", "pending", "initiated"}


@register_provider
class GenericVtuProvider(BaseVtuProvider):
    """Generic provider that works with any API Manager configured provider."""
    name = "generic"
    supports = {"airtime", "data", "cable", "electricity"}
    _active_provider_code: str | None = None

    def _get_provider_config(self, db: Session, provider_code: str | None = None) -> dict:
        """Load provider configuration from database."""
        code = provider_code or self._active_provider_code
        if not code:
            raise ProviderError("No provider code specified")

        provider = db.query(ApiProvider).filter(ApiProvider.code == code).first()
        if not provider:
            raise ProviderError(f"Provider '{code}' not found in API Manager")

        credentials = {
            c.credential_key: decrypt(c.credential_value, settings.SECRET_KEY)
            for c in db.query(ApiProviderCredential).filter(
                ApiProviderCredential.provider_id == provider.id
            ).all()
        }

        endpoints = {
            e.operation: {"path": e.path, "method": e.method.value if hasattr(e.method, "value") else e.method}
            for e in db.query(ApiProviderEndpoint).filter(
                ApiProviderEndpoint.provider_id == provider.id
            ).all()
        }

        return {
            "base_url": provider.base_url,
            "code": provider.code,
            "credentials": credentials,
            "endpoints": endpoints,
        }

    def _build_auth_headers(self, credentials: dict) -> dict:
        """Build authorization headers from credentials."""
        headers = {}

        # Try different auth methods
        auth_methods = [
            ("bearer_token", lambda k: {"Authorization": f"Token {k}"}),
            ("api_token", lambda k: {"Authorization": f"Token {k}"}),
            ("api_key", lambda k: {"Api-Key": k}),
            ("token", lambda k: {"Authorization": f"Token {k}"}),
            ("authorization", lambda k: {"Authorization": k if k.startswith("Bearer") else f"Bearer {k}"}),
        ]

        for key, header_fn in auth_methods:
            if key in credentials and credentials[key]:
                return header_fn(credentials[key])

        return headers

    def _request(self, db: Session, operation: str, payload: dict | None = None, provider_code: str | None = None) -> dict:
        """Make an API request using the configured provider."""
        config = self._get_provider_config(db, provider_code)
        endpoint_info = config["endpoints"].get(operation)

        if not endpoint_info:
            raise ProviderError(f"Operation '{operation}' not configured for provider '{provider_code}'")

        headers = self._build_auth_headers(config["credentials"])
        url = f"{config['base_url']}{endpoint_info['path']}"
        method = endpoint_info.get("method", "POST").upper()

        try:
            if method == "GET":
                resp = httpx.get(url, headers=headers, timeout=20.0)
            else:
                resp = httpx.post(url, json=payload, headers=headers, timeout=25.0)

            if resp.status_code not in (200, 201):
                raise ProviderError(f"Provider returned HTTP {resp.status_code}")

            return resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Provider unreachable: {exc}")

    def _interpret_response(self, body: dict, reference: str) -> ProviderResult:
        """Interpret provider response into standard result."""
        flat = {}
        for k, v in body.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    flat[kk.lower()] = vv
            else:
                flat[k.lower()] = v

        status = str(flat.get("status") or flat.get("order_status") or "").strip().lower()
        ref = flat.get("ref") or flat.get("reference") or flat.get("order_id")
        message = str(flat.get("msg") or flat.get("message") or flat.get("api_message") or "")

        if status in _SUCCESS or (not status and body.get("success")):
            return ProviderResult(
                success=True,
                provider_reference=str(ref) if ref else reference,
                message=message or "Delivered",
                raw=body,
            )
        if status in _PENDING:
            return ProviderResult(success=True, resolved=False, message="Processing", raw=body)

        return ProviderResult(success=False, message=message or f"Status: {status}", raw=body)

    # ── data plans ──────────────────────────────────────────

    def fetch_data_plans(self, db: Session, provider_code: str | None = None) -> list[dict]:
        """Fetch data plans from any configured provider."""
        if not provider_code:
            provider_code = self._active_provider_code

        if not provider_code:
            # Find a provider that has data plan endpoint
            providers = db.query(ApiProvider).filter(ApiProvider.is_active.is_(True)).all()
            for p in providers:
                ep = db.query(ApiProviderEndpoint).filter(
                    ApiProviderEndpoint.provider_id == p.id,
                    ApiProviderEndpoint.operation == "check_balance",  # /api/user/ is typically used for both
                ).first()
                if ep:
                    provider_code = p.code
                    break
            if not provider_code:
                raise ProviderError("No provider configured for data plans")

        config = self._get_provider_config(db, provider_code)
        body = self._request(db, "check_balance", provider_code=provider_code)

        # Try common data plan keys
        raw = {}
        for key in ["Dataplans", "dataplan", "data_plans", "plans"]:
            if key in body and isinstance(body[key], dict):
                raw = body[key]
                break

        if not raw:
            raise ProviderError(f"No data plans found in provider response (keys: {list(body.keys())})")

        out: list[dict] = []
        for plan_key, networks in raw.items():
            if not isinstance(networks, dict):
                continue
            for cat_key, plans in networks.items():
                if not isinstance(plans, list):
                    continue
                for it in plans:
                    try:
                        nid = int(it.get("network", 0))
                        network_code = NETWORK_IDS_R.get(nid)
                        if not network_code:
                            continue

                        raw_type = str(it.get("plan_type", "")).strip().upper()
                        cat = raw_type if raw_type else cat_key.strip().title() if cat_key.strip() else "Other"

                        vol_str = str(it.get("plan", "")).strip()
                        price_naira = float(it.get("plan_amount", 0))
                        dp_id = str(it.get("dataplan_id") or it.get("id", ""))
                        plan_code = f"{network_code}-{dp_id}"

                        validity_str = str(it.get("month_validate", "")).strip()
                        validity_days = 30
                        if "day" in validity_str.lower():
                            try:
                                validity_days = int("".join(c for c in validity_str.split()[0] if c.isdigit()) or 30)
                            except (ValueError, IndexError):
                                validity_days = 1

                        volume_mb = 0
                        vol_lower = vol_str.lower().replace(" ", "")
                        if "gb" in vol_lower:
                            volume_mb = int(float(vol_lower.replace("gb", "")) * 1024)
                        elif "mb" in vol_lower:
                            volume_mb = int(vol_lower.replace("mb", ""))

                        out.append({
                            "network_code": network_code,
                            "plan_code": plan_code,
                            "name": vol_str,
                            "category": cat,
                            "volume_mb": volume_mb,
                            "validity_days": validity_days,
                            "amount_naira": price_naira,
                            "provider_plan_id": int(dp_id) if dp_id.isdigit() else None,
                        })
                    except (TypeError, ValueError, IndexError):
                        continue

        seen = set()
        deduped = []
        for p in out:
            if p["plan_code"] not in seen:
                seen.add(p["plan_code"])
                deduped.append(p)
        return deduped

    # ── balance ─────────────────────────────────────────────

    def get_balance(self, db: Session, provider_code: str | None = None) -> dict:
        """Get balance from any configured provider."""
        if not provider_code:
            provider_code = self._active_provider_code

        if not provider_code:
            providers = db.query(ApiProvider).filter(ApiProvider.is_active.is_(True)).all()
            for p in providers:
                if p.supports_balance_check:
                    provider_code = p.code
                    break
            if not provider_code:
                raise ProviderError("No provider configured for balance check")

        body = self._request(db, "check_balance", provider_code=provider_code)
        user = body.get("user", body) if isinstance(body, dict) else {}
        bal = user.get("Account_Balance", user.get("wallet_balance", user.get("balance", 0)))
        try:
            bal = float(bal or 0)
        except (TypeError, ValueError):
            bal = 0.0

        return {
            "balance_naira": bal,
            "username": user.get("username"),
            "email": user.get("email"),
        }

    # ── cable plans ─────────────────────────────────────────

    def fetch_cable_plans(self, db: Session, provider_code: str | None = None) -> list[dict]:
        """Fetch cable plans from any configured provider."""
        if not provider_code:
            provider_code = self._active_provider_code

        if not provider_code:
            providers = db.query(ApiProvider).filter(ApiProvider.is_active.is_(True)).all()
            for p in providers:
                ep = db.query(ApiProviderEndpoint).filter(
                    ApiProviderEndpoint.provider_id == p.id,
                    ApiProviderEndpoint.operation == "fetch_cable_plans",
                ).first()
                if ep:
                    provider_code = p.code
                    break
            if not provider_code:
                raise ProviderError("No provider configured for cable plans")

        body = self._request(db, "fetch_cable_plans", provider_code=provider_code)
        out: list[dict] = []
        mapping = {"gotvplan": "gotv", "dstvplan": "dstv", "startime": "startimes"}

        for key, items in (body or {}).items():
            code = mapping.get(str(key).lower())
            if not code or not isinstance(items, list):
                continue
            for it in items:
                try:
                    out.append({
                        "provider_code": code,
                        "provider_plan_id": int(it.get("cableplan_id") or it.get("id")),
                        "name": str(it.get("package") or "").strip(),
                        "amount_naira": float(it.get("plan_amount") or 0),
                    })
                except (TypeError, ValueError):
                    continue
        return out

    # ── purchase operations ─────────────────────────────────

    def buy_airtime(self, db: Session, *, network_code: str, phone: str, amount_kobo: int, reference: str) -> ProviderResult:
        nid = NETWORK_IDS.get(network_code.lower())
        if nid is None:
            raise ProviderError(f"Network '{network_code}' not supported")

        # Find airtime provider
        provider_code = self._active_provider_code
        if not provider_code:
            providers = db.query(ApiProvider).filter(ApiProvider.is_active.is_(True)).all()
            for p in providers:
                ep = db.query(ApiProviderEndpoint).filter(
                    ApiProviderEndpoint.provider_id == p.id,
                    ApiProviderEndpoint.operation == "buy_airtime",
                ).first()
                if ep:
                    provider_code = p.code
                    break

        if not provider_code:
            raise ProviderError("No provider configured for airtime")

        payload = {
            "network": nid,
            "amount": max(amount_kobo // 100, 1),
            "mobile_number": phone,
            "Ported_number": True,
            "airtime_type": "VTU",
        }

        body = self._request(db, "buy_airtime", payload, provider_code=provider_code)
        return self._interpret_response(body, reference)

    def buy_data(self, db: Session, *, network_code: str, phone: str, plan_code: str, amount_kobo: int, reference: str, provider_plan_id: int | None = None) -> ProviderResult:
        nid = NETWORK_IDS.get(network_code.lower())
        if nid is None:
            raise ProviderError(f"Network '{network_code}' not supported")

        plan_id = provider_plan_id
        if plan_id is None:
            m = re.match(r"^[a-z0-9_]+-(\d+)$", plan_code.strip().lower())
            if m:
                plan_id = int(m.group(1))
        if plan_id is None:
            return ProviderResult(success=False, message=f"Plan '{plan_code}' not found")

        # Find data provider
        provider_code = self._active_provider_code
        if not provider_code:
            providers = db.query(ApiProvider).filter(ApiProvider.is_active.is_(True)).all()
            for p in providers:
                ep = db.query(ApiProviderEndpoint).filter(
                    ApiProviderEndpoint.provider_id == p.id,
                    ApiProviderEndpoint.operation == "buy_data",
                ).first()
                if ep:
                    provider_code = p.code
                    break

        if not provider_code:
            raise ProviderError("No provider configured for data")

        payload = {
            "network": nid,
            "mobile_number": phone,
            "plan": plan_id,
            "Ported_number": True,
        }

        body = self._request(db, "buy_data", payload, provider_code=provider_code)
        return self._interpret_response(body, reference)

    # ── unsupported operations ──────────────────────────────

    def validate_meter(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_electricity(self, db, *, disco_code, meter_number, meter_type, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported by generic provider")

    def validate_smartcard(self, db, *, cable_code, smartcard_number) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_cable(self, db, *, cable_code, smartcard_number, package_code, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported by generic provider")

    def buy_exam_pin(self, db, *, body_code, product_code, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported by generic provider")

    def validate_student(self, db, *, institution_code, student_ref) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_school_fees(self, db, *, institution_code, student_ref, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported by generic provider")
