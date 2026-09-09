import { get, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { phoneField, attachPhoneDetector } from "./formkit.js";

export function renderExams(screen) {
  let bodies = [];
  let body = null;
  let products = [];
  let product = null;
  const state = { phone: "" };

  screen.innerHTML = `
    ${appBar({ title: "Exam PINs", sub: "WAEC · JAMB · NECO result checkers & e-PINs" })}
    <section class="section">
      <div class="field__label">Exam body</div>
      <div class="filter-scroll" style="padding:0 0 4px" id="bodies">${'<div class="skel"></div>'.repeat(3)}</div>
    </section>
    <section id="products-part" hidden>
      <section class="section">
        <div class="field__label">Choose a product</div>
        <div id="products"></div>
      </section>
      <section class="section">
        ${phoneField({ id: "phone", label: 'Phone to receive PIN <span style="color:var(--faint);font-weight:500">(optional)</span>' })}
      </section>
    </section>
    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="buy" disabled>Buy PIN</button>
    </div>`;

  if (store.user?.phone) state.phone = store.user.phone;
  load();

  const phoneInput = screen.querySelector("#phone");
  const phoneCtl = attachPhoneDetector(phoneInput, ({ digits }) => {
    state.phone = digits;
  });

  async function load() {
    try {
      bodies = await get("/exam/bodies");
      const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("p");
      paintBodies();
      if (pre) {
        const target = bodies.find((b) => b.code === pre);
        if (target) await selectBody(target);
      }
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function paintBodies() {
    const box = screen.querySelector("#bodies");
    box.innerHTML = bodies
      .map(
        (b) => `
        <button class="chip ${body?.code === b.code ? "is-active" : ""}" data-code="${esc(b.code)}">
          <span style="display:inline-flex;align-items:center;gap:6px">
            <span style="width:8px;height:8px;border-radius:99px;background:${esc(b.color || "#98a2b3")}"></span>${esc(b.name)}
          </span>
        </button>`
      )
      .join("");
    box.querySelectorAll("[data-code]").forEach((chip) =>
      chip.addEventListener("click", () => selectBody(bodies.find((b) => b.code === chip.dataset.code)))
    );
  }

  async function selectBody(b) {
    body = b;
    product = null;
    paintBodies();
    await loadProducts();
  }

  async function loadProducts() {
    const part = screen.querySelector("#products-part");
    part.hidden = !body;
    update();
    if (!body) return;

    const box = screen.querySelector("#products");
    box.innerHTML = '<div class="skel"></div><div class="skel"></div>';
    try {
      products = await get(`/exam/products?body=${encodeURIComponent(body.code)}`);
      phoneInput.value = state.phone || "";
      phoneCtl.paint();
      paintProducts();
    } catch (err) {
      toast(err.message, "err");
      products = [];
      paintProducts();
    }
  }

  function paintProducts() {
    const box = screen.querySelector("#products");
    if (!products.length && body) {
      box.innerHTML = `<p style="font-size:12.5px;color:var(--muted)">No ${esc(body.name)} products available right now.</p>`;
      return;
    }
    box.innerHTML = products
      .map(
        (p) => `
        <button class="plan-item ${product?.product_code === p.product_code ? "is-active" : ""}" data-prod="${esc(p.product_code)}">
          <span class="radio-dot"></span>
          <span><span class="plan-item__vol">${esc(p.name)}</span></span>
          <span class="plan-item__price num">${naira(p.price_kobo)}</span>
        </button>`
      )
      .join("");

    box.querySelectorAll("[data-prod]").forEach((b) =>
      b.addEventListener("click", () => {
        product = products.find((p) => p.product_code === b.dataset.prod);
        paintProducts();
        update();
      })
    );
  }

  function update() {
    const buyBtn = screen.querySelector("#buy");
    buyBtn.disabled = !(body && product);
    buyBtn.textContent = product ? `Buy — ${naira(product.price_kobo)}` : "Buy PIN";

    // dock
    screen.querySelector("#dock-total").textContent = product ? naira(product.price_kobo) : "₦0";
    const bal = naira(store.balanceKobo || 0);
    const short = product && (store.balanceKobo || 0) < product.price_kobo;
    screen.querySelector("#dock-bal").innerHTML = product
      ? short
        ? `<span class="bal-bad">Balance ${bal} — too low</span>`
        : `<span class="bal-ok">Balance ${bal}</span>`
      : "";
  }

  screen.querySelector("#buy").addEventListener("click", () => {
    confirmAndPay({
      title: "Confirm exam PIN purchase",
      subtitle: "Your PIN will be shown on the receipt immediately",
      summaryRows: [
        ["Body", body.name],
        ["Product", product.name],
        ["Price", naira(product.price_kobo)],
      ],
      totalKobo: product.price_kobo,
      endpoint: "/exam/purchase",
      payload: { body_code: body.code, product_code: product.product_code, phone: state.phone || null },
      onSuccess: () => history.back(),
    });
  });
}
