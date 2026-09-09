import { get, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { netLogo, hasLogo, detectNetwork, fmtPhone, CHECK } from "../networks.js";

const AMOUNTS = [100, 200, 500, 1000, 2000];
const MIN = 50;
const MAX = 20000;

export function renderAirtime(screen) {
  let networks = [];
  let network = null;
  let netAuto = false;
  const state = { phone: "", amount: 0 };

  screen.innerHTML = `
    ${appBar({ title: "Buy Airtime", sub: "Instant VTU top-up, zero fees" })}

    <section class="hero-preview" id="preview" aria-live="polite">
      <span class="hero-preview__logo" id="pv-logo">${I.airtime}</span>
      <div class="hero-preview__body">
        <div class="hero-preview__to">Sending to</div>
        <div class="hero-preview__num num" id="pv-num">Enter a number</div>
        <div class="hero-preview__net" id="pv-net">Pick a network below</div>
      </div>
      <div class="hero-preview__amt"><b class="num" id="pv-amt">₦0</b><small>no fees</small></div>
    </section>

    <section class="section">
      <div class="section__head">
        <div class="section__title">Network</div>
        <span style="font-size:12px;color:var(--brand-600);font-weight:600" id="detect-note"></span>
      </div>
      <div class="net-grid" id="networks">${'<div class="skel" style="height:74px"></div>'.repeat(4)}</div>
    </section>

    <section class="card form-card">
      <label class="field__label" for="phone">Phone number</label>
      <div class="phone-field">
        <span class="phone-field__tile" id="phone-tile">${I.phoneIco}</span>
        <input id="phone" type="tel" inputmode="tel" placeholder="0801 234 5678" maxlength="13" autocomplete="tel" />
        <button class="phone-field__clear" id="clear-btn" type="button" aria-label="Clear number" hidden>${I.close}</button>
        <button class="btn--sm btn btn--soft" id="me-btn" type="button" style="display:none">Me</button>
      </div>

      <label class="field__label" for="amt" style="margin-top:14px">Amount</label>
      <div class="amount-wrap">
        <span class="cur">₦</span>
        <input id="amt" type="number" inputmode="numeric" placeholder="0" min="${MIN}" max="${MAX}" />
      </div>
      <div class="chip-row chip-row--line" id="chips">
        ${AMOUNTS.map((a) => `<button class="chip num" data-a="${a}">₦${a.toLocaleString()}</button>`).join("")}
      </div>
      <div class="field__error" id="amt-err" hidden></div>
      <div class="field__hint" style="margin:8px 0 12px">Min ₦50 · Max ₦20,000 — delivered instantly</div>
    </section>

    <section class="section" id="recent-sec" hidden>
      <div class="field__label">Recent recipients</div>
      <div class="recent-scroll" id="recent"></div>
    </section>

    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="buy" disabled>Buy Airtime</button>
    </div>`;

  const $ = (sel) => screen.querySelector(sel);
  const phoneEl = $("#phone");
  const amtEl = $("#amt");
  const buyBtn = $("#buy");

  // prefill with the user's own number
  if (store.user?.phone) {
    state.phone = store.user.phone.replace(/\D/g, "").slice(0, 11);
    phoneEl.value = fmtPhone(state.phone);
    autoDetect();
  }

  load();
  loadRecent();

  async function load() {
    try {
      const cat = await get("/services");
      networks = cat.airtime_networks;
      const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("p");
      if (!network && pre) network = networks.find((n) => n.code === pre) || null;
      paintNetworks();
      autoDetect();
      update();
    } catch (err) {
      $("#networks").innerHTML = `<div class="empty-state" style="grid-column:1/-1;padding:18px"><h4>Couldn't load networks</h4><p>${esc(err.message)}</p></div>`;
      toast(err.message, "err");
    }
  }

  async function loadRecent() {
    try {
      const d = await get("/transactions?per_page=25");
      if (!store.session) return;
      const seen = new Set();
      const people = d.items
        .filter((t) => t.service_type === "airtime" && /^0[789]\d{9}$/.test(t.customer_ref || ""))
        .filter((t) => !seen.has(t.customer_ref) && seen.add(t.customer_ref))
        .slice(0, 4);
      if (!people.length) return;
      paintRecent(people);
    } catch {
      /* optional feature — stay quiet */
    }
  }

  function paintRecent(people) {
    $("#recent-sec").hidden = false;
    $("#recent").innerHTML = people
      .map(
        (p) => `
        <button class="recent-chip" data-num="${esc(p.customer_ref)}">
          <i>${esc(p.customer_ref.slice(1, 3))}</i><span class="num">${fmtPhone(p.customer_ref)}</span>
        </button>`
      )
      .join("");
    screen.querySelectorAll(".recent-chip").forEach((c) =>
      c.addEventListener("click", () => {
        state.phone = c.dataset.num;
        phoneEl.value = fmtPhone(state.phone);
        autoDetect();
        update();
      })
    );
  }

  function paintNetworks() {
    $("#networks").innerHTML = networks
      .map(
        (n) => `
        <button class="net-card ${network?.code === n.code ? "is-active" : ""}" data-code="${esc(n.code)}" aria-pressed="${network?.code === n.code}">
          <span class="net-card__check">${CHECK}</span>
          <span class="net-card__logo" style="background:${esc(n.color || "#98a2b3")}">${netLogo(n.code, n.short_name, n.color)}</span>
          ${esc(n.short_name)}
        </button>`
      )
      .join("");

    screen.querySelectorAll("[data-code]").forEach((b) =>
      b.addEventListener("click", () => {
        network = networks.find((n) => n.code === b.dataset.code);
        netAuto = false;
        const note = $("#detect-note");
        if (note) note.textContent = "";
        paintNetworks();
        update();
      })
    );
  }

  screen.querySelectorAll("#chips .chip").forEach((c) =>
    c.addEventListener("click", () => {
      amtEl.value = c.dataset.a;
      state.amount = Number(c.dataset.a);
      update();
    })
  );

  amtEl.addEventListener("input", () => {
    state.amount = Math.floor(Number(amtEl.value));
    update();
  });

  phoneEl.addEventListener("input", () => {
    const digits = phoneEl.value.replace(/\D/g, "").slice(0, 11);
    state.phone = digits;
    phoneEl.value = fmtPhone(digits);
    autoDetect();
    update();
  });

  $("#me-btn")?.addEventListener("click", () => {
    if (!store.user?.phone) return;
    state.phone = store.user.phone.replace(/\D/g, "").slice(0, 11);
    phoneEl.value = fmtPhone(state.phone);
    autoDetect();
    update();
  });

  $("#clear-btn").addEventListener("click", () => {
    state.phone = "";
    phoneEl.value = "";
    if (netAuto) {
      network = null;
      netAuto = false;
      const note = $("#detect-note");
      if (note) note.textContent = "";
      paintNetworks();
    }
    update();
  });

  function autoDetect() {
    if (network || state.phone.length < 4) return;
    const code = detectNetwork(state.phone);
    if (code && networks.length) {
      network = networks.find((n) => n.code === code) || null;
      if (network) {
        netAuto = true;
        $("#detect-note").textContent = `${network.name} detected`;
        paintNetworks();
      }
    }
  }

  function amountError() {
    if (!amtEl.value) return "";
    if (state.amount < MIN) return `Minimum amount is ₦${MIN.toLocaleString()}`;
    if (state.amount > MAX) return `Maximum amount is ₦${MAX.toLocaleString()}`;
    return "";
  }

  function valid() {
    return network && /^0[789]\d{9}$/.test(state.phone) && state.amount >= MIN && state.amount <= MAX;
  }

  function update() {
    // live preview card
    const pvLogo = $("#pv-logo");
    pvLogo.innerHTML = network ? netLogo(network.code, network.short_name, network.color) : I.airtime;
    pvLogo.style.background = network && hasLogo(network.code) ? "#fff" : network ? esc(network.color || "rgba(255,255,255,.16)") : "rgba(255,255,255,.16)";
    $("#pv-num").textContent = state.phone ? fmtPhone(state.phone) : "Enter a number";
    $("#pv-net").textContent = network ? `${network.name} · instant delivery` : "Pick a network below";
    $("#pv-amt").textContent = `₦${state.amount > 0 ? state.amount.toLocaleString() : 0}`;

    // phone field tile mirrors the detected / chosen brand
    const showBrand = network && (!netAuto || state.phone);
    const tile = $("#phone-tile");
    if (tile) tile.innerHTML = showBrand ? netLogo(network.code, network.short_name, network.color) : I.phoneIco;
    const clearBtn = $("#clear-btn");
    if (clearBtn) clearBtn.hidden = !state.phone;

    // chips + validation
    screen.querySelectorAll("#chips .chip").forEach((c) =>
      c.classList.toggle("is-active", Number(c.dataset.a) === state.amount)
    );
    const meBtn = $("#me-btn");
    if (meBtn) meBtn.style.display = state.phone ? "none" : store.user?.phone ? "" : "none";
    const err = amountError();
    $("#amt-err").hidden = !err;
    $("#amt-err").textContent = err;

    // dock
    const total = state.amount >= MIN ? state.amount : 0;
    $("#dock-total").textContent = `₦${total.toLocaleString()}`;
    const bal = naira(store.balanceKobo || 0);
    const short = total > 0 && (store.balanceKobo || 0) < total * 100;
    $("#dock-bal").innerHTML = short
      ? `<span class="bal-bad">Balance ${bal} — too low</span>`
      : `<span class="bal-ok">Balance ${bal}</span>`;

    buyBtn.disabled = !valid();
    buyBtn.textContent = state.amount >= MIN ? `Buy ₦${state.amount.toLocaleString()} Airtime` : "Buy Airtime";
  }

  buyBtn.addEventListener("click", () => {
    confirmAndPay({
      title: "Confirm airtime purchase",
      subtitle: "Review the details before you continue",
      summaryRows: [
        ["Network", network.name],
        ["Recipient", state.phone],
        ["Type", "VTU airtime"],
      ],
      totalKobo: state.amount * 100,
      endpoint: "/airtime/purchase",
      payload: { network_code: network.code, phone: state.phone, amount_naira: state.amount },
      onSuccess: goBackHomeAfterPurchase(),
    });
  });
}

export function goBackHomeAfterPurchase() {
  return () => history.back();
}
