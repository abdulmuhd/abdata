"""bsokdata.com VTU adapter — real fulfilment for airtime (VTU) and data.

Activated with VTU_PROVIDER=bsokdata plus BSOKDATA_API_KEY. Other services
(electricity, cable, betting…) are NOT routed here: get_provider() falls back
to whichever registered adapter supports them (mock today).

API surface used:
  POST /api/topup/   {"network": <id>, "amount": <naira>, "mobile_number": …,
                      "Ported_number": true, "airtime_type": "VTU"}
  POST /api/data/    {"network": <id>, "mobile_number": …, "plan": <id>,
                      "Ported_number": true}

Auth header:  Authorization: Token <BSOKDATA_API_KEY>

Data-plan ids come from the plan_code itself (codes like ``mtn-256`` embed the
provider's numeric plan id) or from an optional AppSetting override
``bsokdata.plan_map`` = {"<plan_code>": <provider_plan_id>}.
"""

import re
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.errors import ProviderError
from ...models import AppSetting
from ...models.enums import MeterType
from .base import BaseVtuProvider, CustomerInfo, ProviderResult, register_provider

PLAN_MAP_KEY = "bsokdata.plan_map"

NETWORK_IDS = {"mtn": 1, "glo": 2, "9mobile": 3, "airtel": 4}

_SUCCESS = {"success", "successful", "delivered", "completed", "true"}
_PENDING = {"processing", "pending", "initiated"}

# Short-lived in-process cache for get_balance(): the admin console polls it
# continuously, and bsokdata does not need a fresh read on every request.
_BALANCE_TTL_SECONDS = 30.0
_balance_cache: dict[str, Any] = {}
_balance_cached_at: float = 0.0
_user_plans_cache: list[dict[str, Any]] | None = None


@register_provider
class BsokDataProvider(BaseVtuProvider):
    name = "bsokdata"
    supports = {"airtime", "data"}

    # ── plumbing ─────────────────────────────────────────────
    def _post(self, db: Session, endpoint: str, payload: dict, reference: str | None) -> dict[str, Any]:
        if not settings.BSOKDATA_API_KEY:
            raise ProviderError("BSOKDATA_API_KEY is not configured")
        started = time.perf_counter()
        headers = {"Authorization": f"Token {settings.BSOKDATA_API_KEY}"}
        try:
            resp = httpx.post(
                f"{settings.BSOKDATA_BASE_URL}{endpoint}",
                json=payload,
                headers=headers,
                timeout=25.0,
            )
            body: Any = None
            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text[:500]}
        except httpx.HTTPError as exc:
            self._log(db, endpoint, payload, {"error": str(exc)}, False, started)
            raise ProviderError(f"Provider unreachable ({exc.__class__.__name__})") from exc

        ok = resp.status_code in (200, 201) and isinstance(body, dict)
        self._log(db, endpoint, payload, body if isinstance(body, dict) else {"raw": str(body)[:500]}, ok, started)
        if not ok:
            msg = ""
            if isinstance(body, dict):
                for k in ("msg", "message", "error", "detail"):
                    v = body.get(k)
                    if isinstance(v, (list, tuple)):
                        v = " ".join(str(x) for x in v)
                    if v:
                        msg = str(v)
                        break
            raise ProviderError(msg or f"Provider returned HTTP {resp.status_code}")
        return body

    def _interpret(self, body: dict, endpoint: str, reference: str) -> ProviderResult:
        """Tolerant status mapping across the provider's varying shapes."""
        flat: dict[str, Any] = {}

        def flatten(prefix_obj: dict) -> None:
            for k, v in prefix_obj.items():
                lk = k.lower()
                if lk not in flat:
                    flat[lk] = v
                if isinstance(v, dict):
                    flatten(v)

        flatten(body)

        status = str(flat.get("status") or flat.get("order_status") or "").strip().lower()
        ref = flat.get("ref") or flat.get("reference") or flat.get("order_id") or flat.get("tranx_id")
        message = str(flat.get("msg") or flat.get("message") or flat.get("api_message") or "")

        if status in _SUCCESS or (not status and bool(flat.get("success"))):
            return ProviderResult(
                success=True,
                provider_reference=str(ref) if ref else reference,
                message=message or "Delivered",
                raw={"provider_response": body},
            )
        if status in _PENDING:
            return ProviderResult(success=True, resolved=False, message="Processing at provider.", raw={"provider_response": body})
        if status:
            return ProviderResult(success=False, message=message or f"Provider status: {status}", raw={"provider_response": body})
        # Unrecognised shape — assume accepted (HTTP 200 already verified).
        return ProviderResult(
            success=True,
            provider_reference=str(ref) if ref else reference,
            message="Accepted by provider",
            raw={"provider_response": body},
        )

    def _network_id(self, network_code: str) -> int:
        nid = NETWORK_IDS.get(network_code.lower())
        if nid is None:
            raise ProviderError(f"Network '{network_code}' is not supported by this provider")
        return nid

    def _plan_id(self, db: Session, plan_code: str, provider_plan_id: int | None = None) -> int | None:
        if provider_plan_id is not None:
            return provider_plan_id
        m = re.match(r"^[a-z0-9_]+-(\d+)$", plan_code.strip().lower())
        if m:
            return int(m.group(1))
        row = db.get(AppSetting, PLAN_MAP_KEY)
        if row and isinstance(row.value, dict):
            pid = row.value.get(plan_code)
            if pid is not None:
                return int(pid)
        return None

    # ── account info / catalogues ────────────────────────────
    def _get(self, endpoint: str) -> dict[str, Any]:
        if not settings.BSOKDATA_API_KEY:
            raise ProviderError("BSOKDATA_API_KEY is not configured")
        try:
            resp = httpx.get(
                f"{settings.BSOKDATA_BASE_URL}{endpoint}",
                headers={"Authorization": f"Token {settings.BSOKDATA_API_KEY}"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Provider unreachable ({exc.__class__.__name__})") from exc
        if resp.status_code != 200:
            raise ProviderError(f"Provider returned HTTP {resp.status_code}")
        return resp.json()

    def get_balance(self) -> dict[str, Any]:
        """Reseller wallet balance from GET /api/user/ (cached briefly).

        Also caches ``Dataplans`` from the same response so that
        :meth:`fetch_data_plans` can reuse it without a redundant call.
        """
        global _balance_cache, _balance_cached_at, _user_plans_cache
        now = time.monotonic()
        if _balance_cache and (now - _balance_cached_at) < _BALANCE_TTL_SECONDS:
            return dict(_balance_cache)

        body = self._get("/api/user/")
        user = body.get("user", body) if isinstance(body, dict) else {}
        bal = user.get("Account_Balance", user.get("wallet_balance", 0))
        try:
            bal = float(bal or 0)
        except (TypeError, ValueError):
            bal = 0.0
        result = {
            "balance_naira": bal,
            "username": user.get("username"),
            "email": user.get("email"),
            "bonus_naira": float(user.get("bonus_balance") or 0),
        }
        _balance_cache, _balance_cached_at = dict(result), now

        # Cache data plans from the same response to avoid a second /api/user/ call
        raw_dataplans = (body or {}).get("Dataplans", {})
        if raw_dataplans:
            _user_plans_cache = self._parse_dataplans(raw_dataplans)

        return result

    def fetch_cable_plans(self, db: Session | None = None) -> list[dict[str, Any]]:
        """Full cable bouquet list from GET /api/cable/."""
        body = self._get("/api/cable/")
        out: list[dict[str, Any]] = []
        mapping = {"gotvplan": "gotv", "dstvplan": "dstv", "startime": "startimes"}
        for key, items in (body or {}).items():
            code = mapping.get(str(key).lower())
            if not code or not isinstance(items, list):
                continue
            for it in items:
                try:
                    out.append(
                        {
                            "provider_code": code,
                            "provider_plan_id": int(it.get("cableplan_id") or it.get("id")),
                            "name": str(it.get("package") or "").strip(),
                            "amount_naira": float(it.get("plan_amount") or 0),
                        }
                    )
                except (TypeError, ValueError):
                    continue
        return out

    NETWORK_IDS_R = {1: "mtn", 2: "glo", 3: "9mobile", 4: "airtel"}
    PLAN_TYPE_MAP = {
        "SME": "SME", "SME2": "SME2", "GIFTING": "Gifting", "CORPORATE": "Corporate",
        "CORPORATE GIFTING": "Corporate Gifting", "CORPORATEGIFTING": "Corporate Gifting",
        "DATA COUPONS": "Data Coupons", "DATACOUPONS": "Data Coupons",
        "DATA SHARE": "Data Share", "DATASHARE": "Data Share",
        "DAILY": "Daily", "WEEKLY": "Weekly", "MONTHLY": "Monthly",
        "MEGA": "Mega", "SMEBOX": "SME", "ASTUTE": "SME",
    }

    def _parse_dataplans(self, raw: dict) -> list[dict[str, Any]]:
        """Normalise the ``Dataplans`` dict from ``/api/user/`` into a flat list."""
        out: list[dict[str, Any]] = []
        for plan_key, networks in raw.items():
            if not isinstance(networks, dict):
                continue
            for cat_key, plans in networks.items():
                if not isinstance(plans, list):
                    continue
                for it in plans:
                    try:
                        nid = int(it.get("network", 0))
                        network_code = self.NETWORK_IDS_R.get(nid)
                        if not network_code:
                            continue
                        raw_type = str(it.get("plan_type", "")).strip()
                        cat = self.PLAN_TYPE_MAP.get(raw_type.upper(), "")
                        if not cat:
                            cat = self.PLAN_TYPE_MAP.get(cat_key.upper(), cat_key.strip().title() if cat_key.strip() else "Other")
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
                            "provider_plan_id": int(dp_id),
                        })
                    except (TypeError, ValueError, IndexError):
                        continue
        return out

    def fetch_data_plans(self, db: Session | None = None) -> list[dict[str, Any]]:
        """Data plan list from GET /api/user/ → Dataplans.

        Reuses the cached response from :meth:`get_balance` when available
        to avoid a redundant API call to the same endpoint.
        """
        global _user_plans_cache
        if _user_plans_cache is not None:
            plans = _user_plans_cache
            _user_plans_cache = None  # consume the cache
            return plans

        body = self._get("/api/user/")
        raw = (body or {}).get("Dataplans", {})
        return self._parse_dataplans(raw)

    # ── airtime ──────────────────────────────────────────────
    def buy_airtime(self, db: Session, *, network_code: str, phone: str, amount_kobo: int, reference: str) -> ProviderResult:
        payload = {
            "network": self._network_id(network_code),
            "amount": max(amount_kobo // 100, 1),
            "mobile_number": phone,
            "Ported_number": True,
            "airtime_type": "VTU",
        }
        body = self._post(db, "/api/topup/", payload, reference)
        return self._interpret(body, "/api/topup/", reference)

    # ── data ─────────────────────────────────────────────────
    def buy_data(self, db: Session, *, network_code: str, phone: str, plan_code: str, amount_kobo: int, reference: str, provider_plan_id: int | None = None) -> ProviderResult:
        plan_id = self._plan_id(db, plan_code, provider_plan_id)
        if plan_id is None:
            return ProviderResult(
                success=False,
                message=f"Plan '{plan_code}' is not available from this provider. Please sync data plans from the API Manager first.",
            )
        payload = {
            "network": self._network_id(network_code),
            "mobile_number": phone,
            "plan": plan_id,
            "Ported_number": True,
        }
        body = self._post(db, "/api/data/", payload, reference)
        return self._interpret(body, "/api/data/", reference)

    # ── services this provider does not offer ────────────────
    @staticmethod
    def _unsupported() -> ProviderResult:
        return ProviderResult(success=False, message="This service is not available on the current provider.")

    def validate_meter(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_electricity(self, db, *, disco_code, meter_number, meter_type, amount_kobo, reference) -> ProviderResult:
        return self._unsupported()

    def validate_smartcard(self, db, *, cable_code, smartcard_number) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_cable(self, db, *, cable_code, smartcard_number, package_code, amount_kobo, reference) -> ProviderResult:
        return self._unsupported()

    def buy_exam_pin(self, db, *, body_code, product_code, amount_kobo, reference) -> ProviderResult:
        return self._unsupported()

    def validate_student(self, db, *, institution_code, student_ref) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_school_fees(self, db, *, institution_code, student_ref, amount_kobo, reference) -> ProviderResult:
        return self._unsupported()
