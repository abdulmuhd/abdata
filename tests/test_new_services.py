from .conftest import API, DEMO_PIN


def test_exam_bodies_listed(client, auth_headers):
    r = client.get(f"{API}/exam/bodies", headers=auth_headers)
    assert r.status_code == 200
    codes = [b["code"] for b in r.json()["data"]]
    assert "waec" in codes and "jamb" in codes and "neco" in codes


def test_exam_products_and_purchase(client, auth_headers, balance):
    prods = client.get(f"{API}/exam/products", params={"body": "waec"}, headers=auth_headers)
    assert prods.status_code == 200
    product = prods.json()["data"][0]

    all_prods = client.get(f"{API}/exam/products", headers=auth_headers)
    assert len(all_prods.json()["data"]) >= len(prods.json()["data"])

    before = balance()
    r = client.post(
        f"{API}/exam/purchase",
        headers=auth_headers,
        json={"body_code": "waec", "product_code": product["product_code"], "pin": DEMO_PIN},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] == "successful"
    # the generated PIN must be on the receipt
    assert d["details"]["exam_pin"]
    assert d["details"]["exam_serial"]
    assert balance() == before - product["price_kobo"]


def test_exam_unknown_product_rejected(client, auth_headers):
    r = client.post(
        f"{API}/exam/purchase",
        headers=auth_headers,
        json={"body_code": "waec", "product_code": "nope-999", "pin": DEMO_PIN},
    )
    assert r.status_code == 404


def test_education_validate_and_pay(client, auth_headers, balance):
    v = client.post(
        f"{API}/education/validate",
        headers=auth_headers,
        json={"institution_code": "unilag", "student_ref": "20191234567"},
    )
    assert v.status_code == 200
    name = v.json()["data"]["customer_name"]
    assert name

    bad = client.post(
        f"{API}/education/validate",
        headers=auth_headers,
        json={"institution_code": "unilag", "student_ref": "000099"},
    )
    assert bad.status_code == 404  # sandbox: refs starting 0000 are unknown students

    before = balance()
    p = client.post(
        f"{API}/education/pay",
        headers=auth_headers,
        json={"institution_code": "unilag", "student_ref": "20191234567", "amount_naira": 5000, "pin": DEMO_PIN},
    )
    assert p.status_code == 200
    d = p.json()["data"]
    assert d["status"] == "successful"
    assert d["details"]["school_fee_receipt_no"]
    assert d["customer_ref"] == "20191234567"
    assert balance() == before - 500_000


def test_new_services_appear_in_history_filters(client, auth_headers):
    cat = client.get(f"{API}/services", headers=auth_headers).json()["data"]
    assert cat["exam_bodies"] and cat["institutions"]

    for service, marker in [("exam_pins", "Exam PIN"), ("education", "School fees")]:
        items = client.get(f"{API}/transactions?service={service}", headers=auth_headers).json()["data"]["items"]
        assert items, f"no history rows for {service}"
