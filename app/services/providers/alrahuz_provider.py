"""alrahuzdata.com.ng VTU adapter — reuses bsokdata API structure.

Activated via API Manager with provider code 'alrahuz'. Reads credentials
from the ApiProviderCredential table (bearer_token).
"""

from sqlalchemy.orm import Session

from ...core.errors import ProviderError
from ...core.config import settings
from ...core.encryption import decrypt
from ...models import ApiProvider, ApiProviderCredential, AppSetting
from ...models.enums import MeterType
from .base import BaseVtuProvider, CustomerInfo, ProviderResult, register_provider

NETWORK_IDS = {"mtn": 1, "glo": 2, "9mobile": 3, "airtel": 4}

_SUCCESS = {"success", "successful", "delivered", "completed", "true"}
_PENDING = {"processing", "pending", "initiated"}


@register_provider
class AlrahuzProvider(BaseVtuProvider):
    name = "alrahuz"
    supports = {"airtime", "data"}

    def _get_creds(self, db: Session) -> tuple[str, str]:
        """Get base_url and bearer_token from API Manager database."""
        provider = db.query(ApiProvider).filter(ApiProvider.code == "alrahuz").first()
        if not provider:
            raise ProviderError("Alrahuz provider not configured in API Manager")
        cred = (
            db.query(ApiProviderCredential)
            .filter(
                ApiProviderCredential.provider_id == provider.id,
                ApiProviderCredential.credential_key == "bearer_token",
            )
            .first()
        )
        if not cred or not cred.credential_value:
            raise ProviderError("Alrahuz bearer_token not configured in API Manager")
        return provider.base_url, decrypt(cred.credential_value, settings.SECRET_KEY)

    def _request(self, db: Session, method: str, endpoint: str, payload: dict | None = None) -> dict:
        import httpx

        base_url, token = self._get_creds(db)
        headers = {"Authorization": f"Token {token}"}
        url = f"{base_url}{endpoint}"

        if method.upper() == "GET":
            resp = httpx.get(url, headers=headers, timeout=20.0)
        else:
            resp = httpx.post(url, json=payload, headers=headers, timeout=25.0)

        if resp.status_code not in (200, 201):
            raise ProviderError(f"Provider returned HTTP {resp.status_code}")
        return resp.json()

    def get_balance(self, db: Session) -> dict:
        body = self._request(db, "GET", "/api/user/")
        user = body.get("user", body) if isinstance(body, dict) else {}
        bal = user.get("Account_Balance", user.get("wallet_balance", 0))
        try:
            bal = float(bal or 0)
        except (TypeError, ValueError):
            bal = 0.0
        return {"balance_naira": bal, "username": user.get("username")}

    def fetch_data_plans(self, db: Session) -> list[dict]:
        body = self._request(db, "GET", "/api/user/")
        raw = (body or {}).get("Dataplans", {})

        NETWORK_IDS_R = {1: "mtn", 2: "glo", 3: "9mobile", 4: "airtel"}
        PLAN_TYPE_MAP = {
            "SME": "SME", "SME2": "SME2", "GIFTING": "Gifting",
            "CORPORATE": "Corporate", "CORPORATE GIFTING": "Corporate Gifting",
            "CORPORATEGIFTING": "Corporate Gifting", "DATA COUPONS": "Data Coupons",
            "DATACOUPONS": "Data Coupons", "DATA SHARE": "Data Share",
            "DATASHARE": "Data Share", "DAILY": "Daily", "WEEKLY": "Weekly",
            "MONTHLY": "Monthly", "MEGA": "Mega",
        }

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
                        raw_type = str(it.get("plan_type", "")).strip()
                        cat = PLAN_TYPE_MAP.get(raw_type.upper(), "")
                        if not cat:
                            cat = PLAN_TYPE_MAP.get(cat_key.upper(), cat_key.strip().title() if cat_key.strip() else "Other")
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

    def buy_airtime(self, db: Session, *, network_code: str, phone: str, amount_kobo: int, reference: str) -> ProviderResult:
        nid = NETWORK_IDS.get(network_code.lower())
        if nid is None:
            raise ProviderError(f"Network '{network_code}' not supported")
        payload = {
            "network": nid,
            "amount": max(amount_kobo // 100, 1),
            "mobile_number": phone,
            "Ported_number": True,
            "airtime_type": "VTU",
        }
        body = self._request(db, "POST", "/api/topup/", payload)
        status = str(body.get("status", "")).lower()
        if status in _SUCCESS or body.get("success"):
            return ProviderResult(success=True, provider_reference=reference, message="Delivered", raw=body)
        return ProviderResult(success=False, message=body.get("msg", "Failed"), raw=body)

    def buy_data(self, db: Session, *, network_code: str, phone: str, plan_code: str, amount_kobo: int, reference: str, provider_plan_id: int | None = None) -> ProviderResult:
        import re
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
        payload = {"network": nid, "mobile_number": phone, "plan": plan_id, "Ported_number": True}
        body = self._request(db, "POST", "/api/data/", payload)
        status = str(body.get("status", "")).lower()
        if status in _SUCCESS or body.get("success"):
            return ProviderResult(success=True, provider_reference=reference, message="Delivered", raw=body)
        return ProviderResult(success=False, message=body.get("msg", "Failed"), raw=body)

    def validate_meter(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_electricity(self, db, *, disco_code, meter_number, meter_type, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported")

    def validate_smartcard(self, db, *, cable_code, smartcard_number) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_cable(self, db, *, cable_code, smartcard_number, package_code, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported")

    def buy_exam_pin(self, db, *, body_code, product_code, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported")

    def validate_student(self, db, *, institution_code, student_ref) -> CustomerInfo:
        return CustomerInfo(found=False)

    def pay_school_fees(self, db, *, institution_code, student_ref, amount_kobo, reference) -> ProviderResult:
        return ProviderResult(success=False, message="Not supported")
