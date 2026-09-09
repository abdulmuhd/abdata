"""Deterministic sandbox VTU provider.

Behaviour (great for demos & tests):
  * customer ids starting with `0000`          → validation fails (unknown customer)
  * amounts that are an exact multiple of ₦997 → purchase fails (simulated decline)
  * otherwise                                  → instant success

Swap by setting VTU_PROVIDER=<name> once a real adapter is registered.
"""

import hashlib
import secrets
import time

from sqlalchemy.orm import Session

from ...models.enums import MeterType
from .base import BaseVtuProvider, CustomerInfo, ProviderResult, get_provider, register_provider

_FIRST_NAMES = ["Adaeze", "Chinedu", "Fatima", "Ibrahim", "Ngozi", "Tunde", "Yemi", "Aisha", "Emeka", "Halima"]
_LAST_NAMES = ["Okafor", "Bello", "Adeyemi", "Muhammad", "Eze", "Balogun", "Ogunleye", "Abubakar"]


def _fake_person(seed: str) -> tuple[str, str]:
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return f"{_FIRST_NAMES[h % len(_FIRST_NAMES)]} {_LAST_NAMES[(h >> 8) % len(_LAST_NAMES)]}"


@register_provider
class MockVtuProvider(BaseVtuProvider):
    name = "mock"

    def _decline(self, amount_kobo: int) -> bool:
        return amount_kobo > 0 and amount_kobo % 99_700 == 0  # multiples of ₦997 simulate declines

    def _ok(self, prefix: str) -> ProviderResult:
        return ProviderResult(success=True, provider_reference=f"{prefix}-{secrets.token_hex(5).upper()}", message="Delivered")

    def buy_airtime(self, db: Session, *, network_code: str, phone: str, amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Operator declined this transaction. Try a different amount.")
        elif phone.startswith("0000"):
            result = ProviderResult(success=False, message="Phone number is not registered on this network.")
        else:
            result = self._ok("AIR")
        self._log(db, "/airtime/purchase", {"network": network_code, "phone": phone, "amount": amount_kobo, "ref": reference},
                 {"status": "success" if result.success else "declined"}, result.success, started)
        return result

    def buy_data(self, db: Session, *, network_code: str, phone: str, plan_code: str, amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Operator declined this transaction. Try again shortly.")
        elif phone.startswith("0000"):
            result = ProviderResult(success=False, message="Phone number is not registered on this network.")
        else:
            result = self._ok("DAT")
        self._log(db, "/data/purchase", {"network": network_code, "phone": phone, "plan": plan_code, "ref": reference},
                 {"status": "success" if result.success else "declined"}, result.success, started)
        return result

    def validate_meter(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType) -> CustomerInfo:
        started = time.perf_counter()
        if meter_number.startswith("0000") or len(meter_number) < 8:
            info = CustomerInfo(found=False)
        else:
            name = _fake_person(meter_number)
            info = CustomerInfo(
                found=True,
                customer_name=name.upper(),
                address=f"{(int(hashlib.sha256(meter_number.encode()).hexdigest(), 16) % 90) + 1} Awolowo Road, Ikoyi",
                meta={"meter_type": meter_type.value, "disco": disco_code},
            )
        self._log(db, "/electricity/validate", {"disco": disco_code, "meter": meter_number},
                  {"found": info.found}, info.found, started)
        return info

    def pay_electricity(self, db: Session, *, disco_code: str, meter_number: str, meter_type: MeterType,
                        amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Disco temporarily unavailable. Amount refunded.")
        else:
            result = self._ok("PWR")
        self._log(db, "/electricity/pay", {"disco": disco_code, "meter": meter_number, "amount": amount_kobo, "ref": reference},
                 {"status": "success" if result.success else "declined"}, result.success, started)
        return result

    def validate_smartcard(self, db: Session, *, cable_code: str, smartcard_number: str) -> CustomerInfo:
        started = time.perf_counter()
        if smartcard_number.startswith("0000") or len(smartcard_number) < 8:
            info = CustomerInfo(found=False)
        else:
            name = _fake_person(smartcard_number)
            info = CustomerInfo(found=True, customer_name=name.upper(),
                                meta={"provider": cable_code})
        self._log(db, "/cable/validate", {"cable": cable_code, "smartcard": smartcard_number},
                  {"found": info.found}, info.found, started)
        return info

    def pay_cable(self, db: Session, *, cable_code: str, smartcard_number: str, package_code: str,
                  amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Operator declined subscription. Amount refunded.")
        else:
            result = self._ok("TV")
        self._log(db, "/cable/pay", {"cable": cable_code, "smartcard": smartcard_number, "package": package_code, "ref": reference},
                  {"status": "success" if result.success else "declined"}, result.success, started)
        return result

    # ── exam pins ────────────────────────────────────────────

    def buy_exam_pin(self, db: Session, *, body_code: str, product_code: str,
                     amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Exam body declined the request. Amount refunded.")
        else:
            seed = hashlib.sha256(f"{reference}:{product_code}".encode()).hexdigest()
            pin = seed[:10].upper()
            serial = f"{int(seed[10:18], 16):010d}"
            result = ProviderResult(
                success=True,
                provider_reference=f"EXM-{secrets.token_hex(5).upper()}",
                message="PIN generated",
                raw={"exam_pin": pin, "exam_serial": serial},
            )
        self._log(db, "/exam/purchase", {"body": body_code, "product": product_code, "amount": amount_kobo, "ref": reference},
                  {"status": "success" if result.success else "declined"}, result.success, started)
        return result

    # ── school fees ──────────────────────────────────────────

    def validate_student(self, db: Session, *, institution_code: str, student_ref: str) -> CustomerInfo:
        started = time.perf_counter()
        if student_ref.upper().startswith("0000") or len(student_ref) < 5:
            info = CustomerInfo(found=False)
        else:
            info = CustomerInfo(
                found=True,
                customer_name=_fake_person(student_ref).upper(),
                meta={"institution": institution_code},
            )
        self._log(db, "/education/validate", {"institution": institution_code, "student": student_ref},
                  {"found": info.found}, info.found, started)
        return info

    def pay_school_fees(self, db: Session, *, institution_code: str, student_ref: str,
                        amount_kobo: int, reference: str) -> ProviderResult:
        started = time.perf_counter()
        if self._decline(amount_kobo):
            result = ProviderResult(success=False, message="Institution portal unavailable. Amount refunded.")
        else:
            seed = hashlib.sha256(reference.encode()).hexdigest()[:8].upper()
            result = ProviderResult(success=True, provider_reference=f"SCH-{secrets.token_hex(5).upper()}",
                                    message="Payment accepted", raw={"school_fee_receipt_no": f"FEE-{seed}"})
        self._log(db, "/education/pay", {"institution": institution_code, "student": student_ref,
                                         "amount": amount_kobo, "ref": reference},
                  {"status": "success" if result.success else "declined"}, result.success, started)
        return result
