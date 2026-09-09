import { get, post, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { netLogo, hasLogo, CHECK } from "../networks.js";

export function renderCable(screen) {
  let cables = [];
  let cable = null;
  let customer = null;
  let packages = [];
  let pkg = null;
  const state = { card: "" };

  screen.innerHTML = `
    ${appBar({ title: "Cable TV", sub: "DStv · GOtv · StarTimes" })}

    <section class="hero-preview" id="preview" aria-live="polite">
      <span class="hero-preview__logo" id="pv-logo">${I.cable}</span>
      <div class="hero-preview__body">
        <div class="hero-preview__to">Subscribing to</div>
        <div class="hero-preview__num num" id="pv-num">Enter smartcard number</div>
        <div class="hero-preview__net" id="pv-net">Pick a provider below</div>
      </div>
      <div class="hero-preview__amt"><b class="num" id="pv-amt">₦0</b><small id="pv-plan">no package yet</small></div>
    </section>

    <section class="section">
      <div class="section__head">
        <div class="section__title">Provider</div>
        <span style="font-size:12px;color:var(--brand-600);font-weight:600" id="detect-note"></span>
      </div>
      <div class="net-grid" id="cables" style="grid-template-columns:repeat(3,1fr)">${'<div class="skel" style="height:74px"></div>'.repeat(3)}</div>
    </section>

    <section class="card form-card">
      <label class="field__label" for="card">Smartcard / IUC number</label>
      <div class="phone-field">
        <span class="phone-field__tile" id="card-tile">${I.cable}</span>
        <input id="card" type="text" inputmode="numeric" placeholder="e.g. 7042133785" maxlength="15" />
        <button class="phone-field__clear" id="card-clear" type="button" aria-label="Clear number" hidden>${I.close}</button>
        <button type="button" class="btn btn--soft btn--sm" id="validate-btn" disabled>Validate</button>
      </div>

      <div id="customer-box"></div>

      <div id="plan-area" hidden>
        <label class="field__label" style="margin-top:14px">Choose a package</label>
        <div class="plan-grid" id="packages" style="margin-top:10px"></div>
        <div class="field__hint" style="margin:10px 0 12px">Subscription activates instantly after payment</div>
      </div>
    </section>

    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="pay" disabled>Subscribe</button>
    </div>`;

  const $ = (sel) => screen.querySelector(sel);
  const cardEl = $("#card");
  const payBtn = $("#pay");
  const PKG_SKELS = '<div class="skel" style="height:82px"></div>'.repeat(4);

  load();

  async function load() {
    try {
      const cat = await get("/services");
      cables = cat.cable_providers;
      const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("p");
      if (pre) cable = cables.find((c) => c.code === pre) || null;
      paintCables();
      if (cable) await loadPackages();
      update();
    } catch (err) {
      $("#cables").innerHTML = `<div class="empty-state" style="grid-column:1/-1;padding:18px"><h4>Couldn't load providers</h4><p>${esc(err.message)}</p></div>`;
      toast(err.message, "err");
    }
  }

  function paintCables() {
    $("#cables").innerHTML = cables
      .map(
        (c) => `
        <button class="net-card ${cable?.code === c.code ? "is-active" : ""}" data-code="${esc(c.code)}" aria-pressed="${cable?.code === c.code}">
          <span class="net-card__check">${CHECK}</span>
          <span class="net-card__logo" style="background:${esc(c.color || "#98a2b3")}">${netLogo(c.code, c.short_name, c.color)}</span>
          ${esc(c.short_name)}
        </button>`
      )
      .join("");

    screen.querySelectorAll("[data-code]").forEach((b) =>
      b.addEventListener("click", async () => {
        pkg = null;
        customer = null;
        cable = cables.find((c) => c.code === b.dataset.code);
        $("#detect-note").textContent = "";
        paintCables();
        clearCustomerBox();
        await loadPackages();
        update();
      })
    );
  }

  async function loadPackages() {
    const area = $("#plan-area");
    area.hidden = !cable;
    if (!cable) return;

    const box = $("#packages");
    box.innerHTML = PKG_SKELS;
    try {
      packages = await get(`/cable/packages?provider=${encodeURIComponent(cable.code)}`);
      paintPackages();
    } catch (err) {
      toast(err.message, "err");
      packages = [];
      paintPackages();
    }
  }

  function paintPackages() {
    const box = $("#packages");
    if (!packages.length) {
      box.innerHTML = `<p style="grid-column:1/-1;font-size:12.5px;color:var(--muted)">No packages available for ${esc(cable?.short_name || "this provider")} right now.</p>`;
      return;
    }
    box.innerHTML = packages
      .map(
        (p) => `
        <button class="plan-tile ${pkg?.package_code === p.package_code ? "is-active" : ""}" data-pkg="${esc(p.package_code)}">
          <span class="plan-tile__check">${CHECK}</span>
          <span class="plan-tile__vol">${esc(p.name)}</span>
          <span class="plan-tile__meta">${p.validity_days}-day subscription</span>
          <span class="plan-tile__price num">${naira(p.price_kobo)}</span>
        </button>`
      )
      .join("");

    box.querySelectorAll("[data-pkg]").forEach((b) =>
      b.addEventListener("click", () => {
        pkg = packages.find((p) => p.package_code === b.dataset.pkg);
        paintPackages();
        update();
      })
    );
  }

  cardEl.addEventListener("input", () => {
    state.card = cardEl.value.replace(/\D/g, "").slice(0, 15);
    cardEl.value = state.card;
    invalidateCustomer();
    update();
  });

  $("#card-clear").addEventListener("click", () => {
    state.card = "";
    cardEl.value = "";
    invalidateCustomer();
    update();
  });

  function invalidateCustomer() {
    if (customer && customer.card !== state.card) {
      customer = null;
      clearCustomerBox();
    }
    $("#validate-btn").disabled = state.card.length < 8;
  }

  function clearCustomerBox() {
    $("#customer-box").innerHTML = "";
  }

  $("#validate-btn").addEventListener("click", async () => {
    const btn = $("#validate-btn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const info = await post("/cable/validate", { provider_code: cable.code, smartcard_number: state.card });
      if (!info.found) {
        customer = null;
        $("#customer-box").innerHTML = `
          <div class="customer-card" style="background:var(--danger-050);border-color:#fbd5d1">
            <span class="customer-card__icon" style="color:var(--danger)">!</span>
            <div><div class="customer-card__name">Customer not found</div>
            <div class="customer-card__addr">Check the smartcard number and try again.</div></div>
          </div>`;
      } else {
        customer = { ...info, card: state.card };
        $("#customer-box").innerHTML = `
          <div class="customer-card">
            <span class="customer-card__icon">${I.checkCircle.replace('width="54" height="54"', 'width="26" height="26"')}</span>
            <div>
              <div class="customer-card__name">${esc(info.customer_name)}</div>
              <div class="customer-card__addr">${esc(cable.name)} · ${esc(state.card)}</div>
            </div>
          </div>`;
      }
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "Validate";
      invalidateCustomer();
      update();
    }
  });

  function update() {
    // live preview card
    const pvLogo = $("#pv-logo");
    pvLogo.innerHTML = cable ? netLogo(cable.code, cable.short_name, cable.color) : I.cable;
    pvLogo.style.background = cable && hasLogo(cable.code) ? "#fff" : cable ? esc(cable.color || "rgba(255,255,255,.16)") : "rgba(255,255,255,.16)";
    $("#pv-num").textContent = customer?.customer_name || state.card || "Enter smartcard number";
    $("#pv-net").textContent = cable
      ? `${cable.name}${customer ? " · verified" : ""}`
      : "Pick a provider below";
    $("#pv-amt").textContent = pkg ? naira(pkg.price_kobo) : "₦0";
    $("#pv-plan").textContent = pkg ? `${pkg.validity_days}-day plan` : "select a package";

    // card field tile mirrors the selected provider brand
    const cardTile = $("#card-tile");
    if (cardTile) cardTile.innerHTML = cable ? netLogo(cable.code, cable.short_name, cable.color) : I.cable;
    const cardClear = $("#card-clear");
    if (cardClear) cardClear.hidden = !state.card;

    // dock
    $("#dock-total").textContent = pkg ? naira(pkg.price_kobo) : "₦0";
    const bal = naira(store.balanceKobo || 0);
    const short = pkg && (store.balanceKobo || 0) < pkg.price_kobo;
    $("#dock-bal").innerHTML = pkg
      ? short
        ? `<span class="bal-bad">Balance ${bal} — too low</span>`
        : `<span class="bal-ok">Balance ${bal}</span>`
      : "";

    payBtn.disabled = !(cable && customer && pkg);
    payBtn.textContent = pkg ? `Subscribe — ${naira(pkg.price_kobo)}` : "Subscribe";
  }

  payBtn.addEventListener("click", () => {
    confirmAndPay({
      title: `Confirm ${cable.short_name} subscription`,
      subtitle: "Activation usually completes in seconds",
      summaryRows: [
        ["Provider", cable.name],
        ["Smartcard", state.card],
        ["Customer", customer.customer_name],
        ["Package", `${pkg.name} · ${pkg.validity_days} days`],
      ],
      totalKobo: pkg.price_kobo,
      endpoint: "/cable/pay",
      payload: {
        provider_code: cable.code,
        smartcard_number: state.card,
        package_code: pkg.package_code,
        customer_name: customer.customer_name || "",
        phone: store.user?.phone,
      },
      onSuccess: () => history.back(),
    });
  });
}
