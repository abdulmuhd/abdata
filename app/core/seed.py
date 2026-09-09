"""Demo/sandbox seed: networks, discos, cable TV, data plans, packages, demo user."""

import random
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password, hash_pin
from app.models import (
    CablePackage,
    DataPlan,
    ExamProduct,
    LedgerCategory,
    Notification,
    Provider,
    ServiceTypeEnum,
    TxnStatus,
    User,
    VTUTransaction,
    Wallet,
)
from app.services import wallet_service
from app.services.providers.bsokdata_provider import BsokDataProvider


NETWORKS = [
    {"code": "mtn", "name": "MTN Nigeria", "short_name": "MTN", "color": "#FFCC00", "sort": 1},
    {"code": "airtel", "name": "Airtel Nigeria", "short_name": "Airtel", "color": "#E40000", "sort": 2},
    {"code": "glo", "name": "Globacom (Glo)", "short_name": "Glo", "color": "#43B02A", "sort": 3},
    {"code": "9mobile", "name": "9mobile", "short_name": "9mobile", "color": "#00694B", "sort": 4},
]

DISCOS = [
    {"code": "ikedc", "name": "Ikeja Electric (IKEDC)", "short_name": "IKEDC"},
    {"code": "ekedc", "name": "Eko Electric (EKEDC)", "short_name": "EKEDC"},
    {"code": "aedc", "name": "Abuja Electricity (AEDC)", "short_name": "AEDC"},
    {"code": "ibedc", "name": "Ibadan Electricity (IBEDC)", "short_name": "IBEDC"},
    {"code": "kedco", "name": "Kano Electricity (KEDCO)", "short_name": "KEDCO"},
    {"code": "phed", "name": "Port Harcourt Electric (PHED)", "short_name": "PHED"},
    {"code": "jed", "name": "Jos Electricity (JED)", "short_name": "JED"},
]

CABLES = [
    {"code": "dstv", "name": "DStv", "short_name": "DStv", "color": "#0A5DA6", "sort": 1},
    {"code": "gotv", "name": "GOtv", "short_name": "GOtv", "color": "#F58220", "sort": 2},
    {"code": "startimes", "name": "StarTimes", "short_name": "StarTimes", "color": "#E31837", "sort": 3},
]


EXAM_BODIES = [
    {"code": "waec", "name": "WAEC", "short_name": "WAEC", "color": "#5B2D8E", "sort": 1},
    {"code": "jamb", "name": "JAMB", "short_name": "JAMB", "color": "#0F8A4C", "sort": 2},
    {"code": "neco", "name": "NECO", "short_name": "NECO", "color": "#C77817", "sort": 3},
]

EXAM_PRODUCTS = [
    # (body, code, name, price_naira)
    ("waec", "waec-result-checker", "WASSCE Result Checker PIN", 3500),
    ("jamb", "jamb-utme-epin", "UTME e-PIN (Registration)", 5700),
    ("jamb", "jamb-direct-entry", "Direct Entry e-PIN", 5700),
    ("neco", "neco-result-token", "NECO Result Token", 2500),
    ("neco", "neco-verification", "NECO Verification of Result", 5000),
]

INSTITUTIONS = [
    {"code": "unilag", "name": "University of Lagos", "short_name": "UNILAG", "color": "#1B4FA0", "sort": 1},
    {"code": "ui", "name": "University of Ibadan", "short_name": "UI", "color": "#7A9E01", "sort": 2},
    {"code": "unilorin", "name": "University of Ilorin", "short_name": "UNILORIN", "color": "#4A7729", "sort": 3},
    {"code": "futo", "name": "Federal University of Technology Owerri", "short_name": "FUTO", "color": "#00755E", "sort": 4},
    {"code": "yabatech", "name": "Yaba College of Technology", "short_name": "YABATECH", "color": "#8C1D40", "sort": 5},
]


def _has_provider(db: Session, service: ServiceTypeEnum) -> bool:
    return db.query(Provider).filter(Provider.service_type == service).count() > 0


def _sync_data_plans_from_provider(db: Session) -> None:
    """Fetch data plans dynamically from the current VTU provider and sync to DB."""
    try:
        provider = BsokDataProvider()
        plans = provider.fetch_data_plans()
    except Exception:
        return

    for p in plans:
        if not p.get("name") or p.get("amount_naira", 0) <= 0:
            continue
        price_kobo = int(p["amount_naira"] * 100)
        row = db.query(DataPlan).filter(DataPlan.plan_code == p["plan_code"]).first()
        if row:
            row.name = p["name"]
            row.category = p["category"]
            row.volume_mb = p["volume_mb"]
            row.validity_days = p["validity_days"]
            row.price_kobo = price_kobo
            row.buying_price_kobo = price_kobo
            if row.selling_price_kobo is None:
                row.selling_price_kobo = price_kobo
            row.provider_plan_id = p.get("provider_plan_id")
            row.is_active = True
        else:
            db.add(
                DataPlan(
                    network_code=p["network_code"],
                    plan_code=p["plan_code"],
                    name=p["name"],
                    category=p["category"],
                    volume_mb=p["volume_mb"],
                    validity_days=p["validity_days"],
                    price_kobo=price_kobo,
                    buying_price_kobo=price_kobo,
                    selling_price_kobo=price_kobo,
                    provider_plan_id=p.get("provider_plan_id"),
                )
            )
    db.flush()


def _sync_cable_plans_from_provider(db: Session) -> None:
    """Fetch cable TV plans dynamically from the current VTU provider and sync to DB."""
    try:
        provider = BsokDataProvider()
        plans = provider.fetch_cable_plans()
    except Exception:
        return

    for p in plans:
        if not p.get("name") or p.get("amount_naira", 0) <= 0:
            continue
        package_code = f"{p['provider_code']}-{p['provider_plan_id']}"
        price_kobo = int(p["amount_naira"] * 100)
        row = db.query(CablePackage).filter(CablePackage.package_code == package_code).first()
        if row:
            row.name = p["name"]
            row.price_kobo = price_kobo
            row.buying_price_kobo = price_kobo
            if row.selling_price_kobo is None:
                row.selling_price_kobo = price_kobo
            row.provider_code = p["provider_code"]
            row.is_active = True
        else:
            db.add(
                CablePackage(
                    provider_code=p["provider_code"],
                    package_code=package_code,
                    name=p["name"],
                    price_kobo=price_kobo,
                    buying_price_kobo=price_kobo,
                    selling_price_kobo=price_kobo,
                )
            )
    db.flush()


def seed_demo(db: Session) -> None:
    if not _has_provider(db, ServiceTypeEnum.AIRTIME):
        for n in NETWORKS:
            db.add(Provider(service_type=ServiceTypeEnum.AIRTIME, code=n["code"], name=n["name"],
                            short_name=n["short_name"], color=n["color"], sort_order=n["sort"]))
    if not _has_provider(db, ServiceTypeEnum.ELECTRICITY):
        for d in DISCOS:
            db.add(Provider(service_type=ServiceTypeEnum.ELECTRICITY, code=d["code"], name=d["name"],
                            short_name=d["short_name"], color="#1273B5", sort_order=DISCOS.index(d) + 1))
    if not _has_provider(db, ServiceTypeEnum.CABLE):
        for c in CABLES:
            db.add(Provider(service_type=ServiceTypeEnum.CABLE, code=c["code"], name=c["name"],
                            short_name=c["short_name"], color=c["color"], sort_order=c["sort"]))
    if not _has_provider(db, ServiceTypeEnum.EXAM_PINS):
        for e in EXAM_BODIES:
            db.add(Provider(service_type=ServiceTypeEnum.EXAM_PINS, code=e["code"], name=e["name"],
                            short_name=e["short_name"], color=e["color"], sort_order=e["sort"]))
    if not _has_provider(db, ServiceTypeEnum.EDUCATION):
        for i in INSTITUTIONS:
            db.add(Provider(service_type=ServiceTypeEnum.EDUCATION, code=i["code"], name=i["name"],
                            short_name=i["short_name"], color=i["color"], sort_order=i["sort"]))
    db.commit()

    if db.query(DataPlan).count() == 0:
        _sync_data_plans_from_provider(db)

    if db.query(CablePackage).count() == 0:
        _sync_cable_plans_from_provider(db)

    if db.query(ExamProduct).count() == 0:
        for body_code, prod_code, name, price in EXAM_PRODUCTS:
            db.add(ExamProduct(body_code=body_code, product_code=prod_code, name=name,
                               price_kobo=price * 100))

    demo_email = "demo@zaply.ng"
    if not db.query(User).filter(User.email == demo_email).first():
        user = User(
            full_name="Adaeze Okafor",
            email=demo_email,
            phone="08012345678",
            password_hash=hash_password("Demo1234!"),
            pin_hash=hash_pin("1234"),
            is_verified=True,
        )
        db.add(user)
        db.flush()
        db.add(Wallet(user_id=user.id))
        db.flush()

        welcome_at = datetime.utcnow() - timedelta(days=30)
        row = wallet_service.credit(
            db, wallet_service.get_wallet(db, user.id), 50_000_00,
            category="funding", narration="Welcome bonus — sandbox funding",
            reference="ZP-FND-WELCOME01",
        )
        row.created_at = welcome_at
        user.created_at = welcome_at
        db.commit()

    demo_user = db.query(User).filter(User.email == demo_email).first()
    if demo_user and settings_seed_history(db, demo_user):
        db.commit()


def settings_seed_history(db: Session, user: User) -> bool:
    """Populate ~3 weeks of believable demo history once. Returns True when seeded."""
    if db.query(VTUTransaction).filter(VTUTransaction.user_id == user.id).count() > 0:
        return False

    rng = random.Random(20260823)  # deterministic so demos look the same everywhere
    now = datetime.utcnow()

    def ref(prefix: str) -> str:
        return f"ZP-{prefix}-{secrets.token_hex(5).upper()}"

    def when(days_ago: float) -> datetime:
        return now - timedelta(days=days_ago)

    def phone(seed: int) -> str:
        return f"08{rng.randint(0, 9)}{rng.randint(10 ** 8, 9 * 10 ** 8)}{seed % 10}"[:11]

    wallet = wallet_service.get_wallet(db, user.id)

    # (days_ago, kind, amount_naira, details) — kinds mirror the live services
    events = [
        (29.4, "fund", 20000, {}),
        (27.1, "airtime", 500, {"network": "MTN", "recipient": phone(1)}),
        (25.8, "data", 3200, {"network": "Airtel", "plan_code": "airtel-10gb-30d-monthly", "plan_name": "10GB Monthly Plan", "volume_mb": 10000, "validity_days": 30, "category": "Monthly", "recipient": phone(2)}),
        (24.0, "electricity", 5000, {"provider": "Ikeja Electric (IKEDC)", "meter_type": "prepaid", "customer_name": "YEMI OKAFOR", "address": "27 Awolowo Road, Ikoyi"}),
        (21.5, "cable", 4400, {"provider": "DStv", "package_code": "dstv-padi", "package_name": "Padi", "validity_days": 30, "customer_name": "HALIMA MUHAMMAD"}),
        (19.2, "fund", 10000, {}),
        (16.3, "exam_pins", 3500, {"provider": "WAEC", "product_code": "waec-result-checker", "product_name": "WASSCE Result Checker PIN"}),
        (14.7, "airtime", 1000, {"network": "Glo", "recipient": phone(3)}),
        (12.9, "data", 600, {"network": "MTN", "plan_code": "mtn-2gb-1d-daily", "plan_name": "2GB Daily Plan", "volume_mb": 2000, "validity_days": 1, "category": "Daily", "recipient": phone(4)}),
        (11.1, "education", 25000, {"provider": "University of Lagos", "student_name": "Ada Okafor"}),
        (9.6, "airtime_failed", 997, {"network": "Airtel", "recipient": phone(5)}),
        (7.2, "cable", 5800, {"provider": "GOtv", "package_code": "gotv-jolli", "package_name": "Jolli", "validity_days": 30, "customer_name": "IBRAHIM ABUBAKAR"}),
        (5.5, "electricity", 3000, {"provider": "Eko Electric (EKEDC)", "meter_type": "postpaid", "customer_name": "NGOZI EZE", "address": "12 Marina Road, Lagos Island"}),
        (4.0, "data", 4500, {"network": "9mobile", "plan_code": "9mobile-15gb-30d-monthly", "plan_name": "15GB Monthly Plan", "volume_mb": 15000, "validity_days": 30, "category": "Monthly", "recipient": phone(6)}),
        (2.6, "airtime", 200, {"network": "MTN", "recipient": phone(7)}),
        (1.3, "fund", 5000, {}),
        (0.6, "exam_pins", 5700, {"provider": "JAMB", "product_code": "jamb-utme-epin", "product_name": "UTME e-PIN (Registration)"}),
    ]

    # per-kind static shape: prefix, service enum, provider_code, counterparty
    KINDS = {
        "airtime": ("AIR", ServiceTypeEnum.AIRTIME, None, lambda m: m["recipient"]),
        "data": ("DAT", ServiceTypeEnum.DATA, None, lambda m: m["recipient"]),
        "electricity": ("PWR", ServiceTypeEnum.ELECTRICITY, None, lambda m: "45011234567"),
        "cable": ("TV", ServiceTypeEnum.CABLE, None, lambda m: "7042133785"),
        "exam_pins": ("EXM", ServiceTypeEnum.EXAM_PINS, None, lambda m: m["provider"]),
        "education": ("SCH", ServiceTypeEnum.EDUCATION, None, lambda m: "20191234567"),
    }
    PROVIDER_CODES = {
        "MTN": "mtn", "Airtel": "airtel", "Glo": "glo", "9mobile": "9mobile",
        "DStv": "dstv", "GOtv": "gotv",
        "WAEC": "waec", "JAMB": "jamb", "NECO": "neco",
        "Ikeja Electric (IKEDC)": "ikedc", "Eko Electric (EKEDC)": "ekedc",
        "University of Lagos": "unilag",
    }
    LABELS = {
        "airtime": "Airtime top-up", "data": "Data purchase", "electricity": "Electricity payment",
        "cable": "Cable TV subscription",
        "exam_pins": "Exam PIN", "education": "School fees payment",
    }

    for days_ago, kind, amount, meta in events:
        ts = when(days_ago)

        if kind == "fund":
            reference = f"ZP-FND-{secrets.token_hex(6).upper()}"
            row = wallet_service.credit(
                db, wallet, amount * 100, category=LedgerCategory.FUNDING,
                narration="Wallet funded via sandbox gateway", reference=reference,
            )
            row.created_at = ts
            _notify(db, user.id, "wallet", "Wallet funded",
                    f"₦{amount:,} was added to your Zaply wallet.", reference, ts)
            continue

        base_kind = kind.replace("_failed", "")
        failed = kind != base_kind
        prefix, service, _, cust_ref_of = KINDS[base_kind]

        details = {**meta}
        if base_kind == "education":
            details["school_fee_receipt_no"] = f"FEE-{rng.randrange(16 ** 8):08X}"
        if base_kind == "exam_pins":
            details["exam_pin"] = f"{rng.randrange(16 ** 10):010X}"
            details["exam_serial"] = f"{rng.randrange(10 ** 10):010d}"

        reference = ref(prefix)
        label = LABELS[base_kind]
        txn = VTUTransaction(
            user_id=user.id,
            service_type=service,
            provider_code=PROVIDER_CODES[meta.get("provider") or meta["network"]],
            customer_ref=cust_ref_of(meta),
            details=details,
            amount_kobo=amount * 100,
            status=TxnStatus.FAILED if failed else TxnStatus.SUCCESSFUL,
            failure_reason="Operator declined this transaction. Try a different amount." if failed else None,
            provider_reference=None if failed else f"{prefix}-{secrets.token_hex(4).upper()}",
            reference=reference,
            created_at=ts,
            updated_at=ts,
        )
        db.add(txn)
        db.flush()  # need txn.id to link the ledger rows

        debit = wallet_service.debit(
            db, wallet, amount * 100, category=LedgerCategory.PURCHASE,
            narration=f"{label} — {txn.customer_ref}", reference=f"{reference}-D",
            vtu_transaction_id=txn.id,
        )
        debit.created_at = ts

        if failed:
            refund_ts = ts + timedelta(minutes=4)  # auto-refund shortly after the decline
            r_row = wallet_service.credit(
                db, wallet, amount * 100, category=LedgerCategory.REFUND,
                narration=f"Refund — {label.lower()} was declined", reference=f"{reference}-R",
                vtu_transaction_id=txn.id,
            )
            r_row.created_at = refund_ts
            _notify(db, user.id, "transaction", "Transaction failed",
                    f"Your {label.lower()} of ₦{amount:,} was declined. ₦{amount:,} has been refunded to your wallet.",
                    reference, refund_ts)
        else:
            extra = ""
            if base_kind == "exam_pins":
                extra = f" Your PIN is {details['exam_pin']}."
            elif base_kind == "education":
                extra = f" Receipt no. {details['school_fee_receipt_no']}."
            _notify(db, user.id, "transaction", label,
                    f"₦{amount:,} {label.lower()} was successful.{extra}", reference, ts)

    return True


def _notify(db: Session, user_id: int, type_: str, title: str, body: str, reference: str, ts: datetime):
    db.add(Notification(user_id=user_id, type=type_, title=title, body=body, reference=reference, created_at=ts))
