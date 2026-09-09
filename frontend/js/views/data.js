import { get, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { netLogo, hasLogo, detectNetwork, fmtPhone, CHECK } from "../networks.js";

export function renderData(screen) {
  let networks = [];
  let network = null;
  let netAuto = false;
  let plans = {};      // grouped by category for selected network
  let activeCat = null;
  let plan = null;
  const state = { phone: "" };

  screen.innerHTML = `
    ${appBar({ title: "Buy Data", sub: "Instant data bundles, zero fees" })}

    <section class="hero-preview" id="preview" aria-live="polite">
      <span class="hero-preview__logo" id="pv-logo">${I.data}</span>
      <div class="hero-preview__body">
        <div class="hero-preview__to">Sending to</div>
        <div class="hero-preview__num num" id="pv-num">Enter a number</div>
        <div class="hero-preview__net" id="pv-net">Pick a network below</div>
      </div>
      <div class="hero-preview__amt"><b class="num" id="pv-amt">₦0</b><small id="pv-plan">no plan yet</small></div>
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

      <div id="plan-area" hidden>
        <label class="field__label" style="margin-top:14px">Choose a plan</label>
        <div class="chip-row" id="cats"></div>
        <div class="plan-grid" id="plans" style="margin-top:10px"></div>
        <div class="field__hint" style="margin:10px 0 12px">Bundle is delivered instantly after payment</div>
      </div>
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
      <button class="btn btn--primary" id="buy" disabled>Buy Data</button>
    </div>`;

  const $ = (sel) => screen.querySelector(sel);
  const phoneEl = $("#phone");
  const buyBtn = $("#buy");
  const PLAN_SKELS = '<div class="skel" style="height:82px"></div>'.repeat(4);

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
      if (network) await loadPlans();
      update();
    } catch (err) {
      $("#networks").innerHTML = `<div class="empty-state" style="grid-column:1/-1;padding:18px"><h4>Couldn't load networks</h4><p>${esc(err.message)}</p></div>`;
      toast(err.message, "err");
    }
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
      b.addEventListener("click", async () => {
        plan = null;
        activeCat = null;
        plans = {};
        network = networks.find((n) => n.code === b.dataset.code);
        netAuto = false;
        const note = $("#detect-note");
        if (note) note.textContent = "";
        paintNetworks();
        await loadPlans();
        update();
      })
    );
  }

  async function loadPlans() {
    const area = $("#plan-area");
    area.hidden = !network;
    if (!network) return;

    const box = $("#plans");
    box.innerHTML = PLAN_SKELS;
    phoneEl.value = fmtPhone(state.phone);

    try {
      plans = await get(`/data/plans?network=${encodeURIComponent(network.code)}`);
      const cats = Object.keys(plans);
      activeCat = cats.includes("Monthly") ? "Monthly" : cats[0];
      paintCats();
    } catch (err) {
      toast(err.message, "err");
      box.innerHTML = "";
    }
    update();
  }

  function paintCats() {
    const catsBox = $("#cats");
    catsBox.innerHTML = Object.keys(plans)
      .map((c) => `<button class="chip ${c === activeCat ? "is-active" : ""}" data-c="${esc(c)}">${esc(c)}</button>`)
      .join("");
    catsBox.querySelectorAll(".chip").forEach((chip) =>
      chip.addEventListener("click", () => {
        activeCat = chip.dataset.c;
        plan = null;
        paintCats();
        paintPlans();
        update();
      })
    );
    $("#plan-area").hidden = false;
    paintPlans();
  }

  function volLabel(mb) {
    return mb >= 1000 ? `${Number.isInteger(mb / 1000) ? mb / 1000 : (mb / 1000).toFixed(1)}GB` : `${mb}MB`;
  }

  function paintPlans() {
    const list = plans[activeCat] || [];
    const box = $("#plans");
    if (!list.length) {
      box.innerHTML = `<p style="grid-column:1/-1;font-size:12.5px;color:var(--muted)">No ${esc(activeCat || "")} plans for ${esc(network?.short_name || "this network")} right now.</p>`;
      return;
    }
    box.innerHTML = list
      .map(
        (p) => {
          const hasPromo = p.promo_price_kobo && p.promo_price_kobo < p.price_kobo;
          const promoPct = hasPromo ? Math.round((1 - p.promo_price_kobo / p.price_kobo) * 100) : 0;
          return `
        <button class="plan-tile ${plan?.plan_code === p.plan_code ? "is-active" : ""}" data-plan="${esc(p.plan_code)}">
          <span class="plan-tile__check">${CHECK}</span>
          <span class="plan-tile__vol">${volLabel(p.volume_mb)}</span>
          <span class="plan-tile__meta">${p.validity_days}-day validity</span>
          ${hasPromo ? `<span class="plan-tile__prices num"><span class="plan-tile__old-price">${naira(p.price_kobo)}</span><span class="plan-tile__promo-price">${naira(p.promo_price_kobo)}</span><span class="plan-tile__badge">${promoPct}% off</span></span>` : `<span class="plan-tile__price num">${naira(p.price_kobo)}</span>`}
        </button>`;
        }
      )
      .join("");

    box.querySelectorAll("[data-plan]").forEach((b) =>
      b.addEventListener("click", () => {
        plan = (plans[activeCat] || []).find((p) => p.plan_code === b.dataset.plan);
        paintPlans();
        update();
      })
    );
  }

  async function loadRecent() {
    try {
      const d = await get("/transactions?per_page=25");
      if (!store.session) return;
      const seen = new Set();
      const people = d.items
        .filter((t) => t.service_type === "data" && /^0[789]\d{9}$/.test(t.customer_ref || ""))
        .filter((t) => !seen.has(t.customer_ref) && seen.add(t.customer_ref))
        .slice(0, 4);
      if (!people.length) return;
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
    } catch {
      /* optional feature — stay quiet */
    }
  }

  phoneEl.addEventListener("input", () => {
    state.phone = phoneEl.value.replace(/\D/g, "").slice(0, 11);
    phoneEl.value = fmtPhone(state.phone);
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
      plan = null;
      activeCat = null;
      plans = {};
      const note = $("#detect-note");
      if (note) note.textContent = "";
      paintNetworks();
      $("#plan-area").hidden = true;
    }
    update();
  });

  function autoDetect() {
    if (network || state.phone.length < 4 || !networks.length) return;
    const code = detectNetwork(state.phone);
    if (code) {
      network = networks.find((n) => n.code === code) || null;
      if (network) {
        netAuto = true;
        $("#detect-note").textContent = `${network.name} detected`;
        paintNetworks();
        loadPlans();
      }
    }
  }

  screen.addEventListener("input", update);

  function update() {
    const effectivePrice = plan ? (plan.promo_price_kobo && plan.promo_price_kobo < plan.price_kobo ? plan.promo_price_kobo : plan.price_kobo) : 0;

    // live preview card
    const pvLogo = $("#pv-logo");
    pvLogo.innerHTML = network ? netLogo(network.code, network.short_name, network.color) : I.data;
    pvLogo.style.background = network && hasLogo(network.code) ? "#fff" : network ? esc(network.color || "rgba(255,255,255,.16)") : "rgba(255,255,255,.16)";
    $("#pv-num").textContent = state.phone ? fmtPhone(state.phone) : "Enter a number";
    $("#pv-net").textContent = network ? `${network.name} · zero fees` : "Pick a network below";
    $("#pv-amt").textContent = effectivePrice ? naira(effectivePrice) : "₦0";
    $("#pv-plan").textContent = plan ? volLabel(plan.volume_mb) : "select a plan";

    // phone field tile mirrors the detected / chosen brand
    const showBrand = network && (!netAuto || state.phone);
    const tile = $("#phone-tile");
    if (tile) tile.innerHTML = showBrand ? netLogo(network.code, network.short_name, network.color) : I.phoneIco;
    const clearBtn = $("#clear-btn");
    if (clearBtn) clearBtn.hidden = !state.phone;
    const meBtn = $("#me-btn");
    if (meBtn) meBtn.style.display = state.phone ? "none" : store.user?.phone ? "" : "none";

    // chips reflect the active category
    screen.querySelectorAll("#cats .chip").forEach((c) =>
      c.classList.toggle("is-active", c.dataset.c === activeCat)
    );

    // dock
    $("#dock-total").textContent = effectivePrice ? naira(effectivePrice) : "₦0";
    const bal = naira(store.balanceKobo || 0);
    const short = plan && (store.balanceKobo || 0) < effectivePrice;
    $("#dock-bal").innerHTML = plan
      ? short
        ? `<span class="bal-bad">Balance ${bal} — too low</span>`
        : `<span class="bal-ok">Balance ${bal}</span>`
      : "";

    const phoneOk = /^0[789]\d{9}$/.test(state.phone);
    buyBtn.disabled = !(network && plan && phoneOk);
    buyBtn.textContent = plan ? `Buy ${volLabel(plan.volume_mb)} — ${naira(effectivePrice)}` : "Buy Data";
  }

  buyBtn.addEventListener("click", () => {
    const effectivePrice = plan.promo_price_kobo && plan.promo_price_kobo < plan.price_kobo ? plan.promo_price_kobo : plan.price_kobo;
    confirmAndPay({
      title: "Confirm data purchase",
      subtitle: "Review the details before you continue",
      summaryRows: [
        ["Network", network.name],
        ["Plan", `${plan.name} · ${plan.validity_days} days`],
        ["Recipient", state.phone],
      ],
      totalKobo: effectivePrice,
      endpoint: "/data/purchase",
      payload: {
        network_code: network.code,
        plan_code: plan.plan_code,
        phone: state.phone,
      },
      onSuccess: () => history.back(),
    });
  });
}
