import { get, post, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { netLogo, hasLogo, CHECK } from "../networks.js";

const AMOUNTS = [1000, 2000, 5000, 10000];
const MIN_AMOUNT = 1000;

export function renderElectricity(screen) {
  let discos = [];
  let disco = null;
  let meterType = "prepaid";
  let customer = null; // {customer_name, address, meter}
  const state = { meter: "", amount: 0 };

  screen.innerHTML = `
    ${appBar({ title: "Electricity", sub: "Prepaid tokens & postpaid bills" })}

    <section class="hero-preview" id="preview" aria-live="polite">
      <span class="hero-preview__logo" id="pv-logo">${I.electricity}</span>
      <div class="hero-preview__body">
        <div class="hero-preview__to">Paying</div>
        <div class="hero-preview__num num" id="pv-num">Enter meter number</div>
        <div class="hero-preview__net" id="pv-net">Pick a provider below</div>
      </div>
      <div class="hero-preview__amt"><b class="num" id="pv-amt">₦0</b><small id="pv-plan">prepaid</small></div>
    </section>

    <section class="section">
      <div class="section__head">
        <div class="section__title">Provider</div>
      </div>
      <div class="net-grid" id="discos" style="grid-template-columns:repeat(3,1fr)">${'<div class="skel" style="height:74px"></div>'.repeat(3)}</div>
    </section>

    <section class="card form-card" id="form-part" hidden>
      <label class="field__label">Meter type</label>
      <div class="segmented" id="mtype">
        <button data-t="prepaid" class="is-active">Prepaid</button>
        <button data-t="postpaid">Postpaid</button>
      </div>

      <label class="field__label" for="meter" style="margin-top:14px">Meter number</label>
      <div class="phone-field">
        <span class="phone-field__tile" id="meter-tile">${I.electricity}</span>
        <input id="meter" type="text" inputmode="numeric" placeholder="e.g. 45011234567" maxlength="20" />
        <button class="phone-field__clear" id="meter-clear" type="button" aria-label="Clear number" hidden>${I.close}</button>
        <button type="button" class="btn btn--soft btn--sm" id="validate-btn" disabled>Validate</button>
      </div>
      <div class="field__hint">Tip: sandbox meters starting with “0000” will fail validation</div>

      <div id="customer-box"></div>

      <label class="field__label" for="amt" style="margin-top:14px">Amount</label>
      <div class="amount-wrap">
        <span class="cur">₦</span>
        <input id="amt" type="number" inputmode="numeric" placeholder="0" min="${MIN_AMOUNT}" step="50" />
      </div>
      <div class="chip-row chip-row--line" id="chips">
        ${AMOUNTS.map((a) => `<button class="chip num" data-a="${a}">₦${a.toLocaleString()}</button>`).join("")}
      </div>
      <div class="field__error" id="amt-err" hidden></div>
      <div class="field__hint" style="margin:10px 0 12px">Min ₦1,000 — token delivered instantly after payment</div>
    </section>

    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="pay" disabled>Pay Bill</button>
    </div>`;

  const $ = (sel) => screen.querySelector(sel);
  const payBtn = $("#pay");

  load();

  async function load() {
    try {
      const cat = await get("/services");
      discos = cat.electricity_providers;
      const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("p");
      if (pre) disco = discos.find((d) => d.code === pre) || null;
      paintDiscos();
      $("#form-part").hidden = !disco;
      update();
    } catch (err) {
      $("#discos").innerHTML = `<div class="empty-state" style="grid-column:1/-1;padding:18px"><h4>Couldn't load providers</h4><p>${esc(err.message)}</p></div>`;
      toast(err.message, "err");
    }
  }

  function paintDiscos() {
    $("#discos").innerHTML = discos
      .map(
        (d) => `
        <button class="net-card ${disco?.code === d.code ? "is-active" : ""}" data-code="${esc(d.code)}" aria-pressed="${disco?.code === d.code}">
          <span class="net-card__check">${CHECK}</span>
          <span class="net-card__logo" style="background:${hasLogo(d.code) ? "#fff" : esc(d.color || "#1273b5")}">${netLogo(d.code, d.short_name, d.color)}</span>
          ${esc(d.short_name)}
        </button>`
      )
      .join("");

    $("#discos").querySelectorAll("[data-code]").forEach((b) =>
      b.addEventListener("click", () => {
        disco = discos.find((d) => d.code === b.dataset.code);
        customer = null;
        clearCustomerBox();
        $("#form-part").hidden = false;
        paintDiscos();
        update();
      })
    );
  }

  $("#mtype").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    meterType = b.dataset.t;
    $("#mtype").querySelectorAll("button").forEach((x) => x.classList.toggle("is-active", x === b));
    invalidateCustomer();
    update();
  });

  $("#chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    $("#amt").value = chip.dataset.a;
    state.amount = Number(chip.dataset.a);
    update();
    $("#amt").blur();
  });
  $("#amt").addEventListener("input", (e) => { state.amount = Math.floor(Number(e.target.value)) || 0; update(); });

  function amountError() {
    if (!$("#amt").value) return "";
    if (state.amount < MIN_AMOUNT) return `Minimum amount is ₦${MIN_AMOUNT.toLocaleString()}`;
    return "";
  }

  $("#meter").addEventListener("input", () => {
    state.meter = $("#meter").value.trim();
    $("#meter").value = state.meter;
    invalidateCustomer();
    update();
  });

  $("#meter-clear").addEventListener("click", () => {
    state.meter = "";
    $("#meter").value = "";
    invalidateCustomer();
    update();
    $("#meter").focus();
  });

  function invalidateCustomer() {
    if (customer && customer.meter !== state.meter) {
      customer = null;
      clearCustomerBox();
    }
    $("#validate-btn").disabled = state.meter.length < 6 || !disco;
  }

  function clearCustomerBox() {
    $("#customer-box").innerHTML = "";
  }

  $("#validate-btn").addEventListener("click", async () => {
    const btn = $("#validate-btn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const info = await post("/electricity/validate", {
        provider_code: disco.code,
        meter_number: state.meter,
        meter_type: meterType,
      });
      if (!info.found) {
        customer = null;
        $("#customer-box").innerHTML = `
          <div class="customer-card" style="background:var(--danger-050);border-color:#fbd5d1">
            <span class="customer-card__icon" style="color:var(--danger)">!</span>
            <div><div class="customer-card__name">Customer not found</div>
            <div class="customer-card__addr">Check the meter number and try again.</div></div>
          </div>`;
      } else {
        customer = { ...info, meter: state.meter };
        $("#customer-box").innerHTML = `
          <div class="customer-card">
            <span class="customer-card__icon">${I.checkCircle.replace('width="54" height="54"', 'width="26" height="26"')}</span>
            <div>
              <div class="customer-card__name">${esc(info.customer_name)}</div>
              <div class="customer-card__addr">${esc(info.address || disco.name)} · ${esc(state.meter)}</div>
            </div>
          </div>`;
      }
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "Validate";
      update();
    }
  });

  function update() {
    // live preview card
    const pvLogo = $("#pv-logo");
    pvLogo.innerHTML = disco ? netLogo(disco.code, disco.short_name, disco.color) : I.electricity;
    pvLogo.style.background = disco && hasLogo(disco.code) ? "#fff" : "rgba(255,255,255,.16)";
    $("#pv-num").textContent = customer?.customer_name || state.meter || "Enter meter number";
    $("#pv-net").textContent = disco
      ? `${disco.name}${customer ? " · verified" : ""}`
      : "Pick a provider below";
    const total = state.amount >= MIN_AMOUNT ? state.amount : 0;
    $("#pv-amt").textContent = `₦${total.toLocaleString()}`;
    $("#pv-plan").textContent = meterType;

    // meter field tile mirrors the selected provider brand
    const tile = $("#meter-tile");
    if (tile) tile.innerHTML = disco ? netLogo(disco.code, disco.short_name, disco.color) : I.electricity;
    const clearBtn = $("#meter-clear");
    if (clearBtn) clearBtn.hidden = !state.meter;

    // amount input state
    screen.querySelectorAll("#chips .chip").forEach((c) =>
      c.classList.toggle("is-active", Number(c.dataset.a) === state.amount)
    );
    const err = amountError();
    const errBox = $("#amt-err");
    errBox.hidden = !err;
    errBox.textContent = err;
    screen.querySelector(".amount-wrap").style.boxShadow = err
      ? "0 0 0 2px rgba(209, 72, 54, 0.35)"
      : "";

    // dock
    $("#dock-total").textContent = `₦${total.toLocaleString()}`;
    const bal = naira(store.balanceKobo || 0);
    const short = total > 0 && (store.balanceKobo || 0) < total * 100;
    $("#dock-bal").innerHTML = total
      ? short
        ? `<span class="bal-bad">Balance ${bal} — too low</span>`
        : `<span class="bal-ok">Balance ${bal}</span>`
      : "";

    const ok = disco && customer && state.amount >= MIN_AMOUNT;
    payBtn.disabled = !ok;
    payBtn.textContent = state.amount >= MIN_AMOUNT ? `Pay ₦${state.amount.toLocaleString()}` : "Pay Bill";
  }

  payBtn.addEventListener("click", () => {
    confirmAndPay({
      title: `Confirm ${disco.short_name} payment`,
      subtitle: "Prepaid tokens arrive by SMS & email",
      summaryRows: [
        ["Provider", disco.name],
        ["Meter number", state.meter],
        ["Meter type", meterType[0].toUpperCase() + meterType.slice(1)],
        ["Customer", customer.customer_name],
      ],
      totalKobo: state.amount * 100,
      endpoint: "/electricity/pay",
      payload: {
        provider_code: disco.code,
        meter_number: state.meter,
        meter_type: meterType,
        customer_name: customer.customer_name || "",
        amount_naira: state.amount,
        phone: store.user?.phone,
      },
      onSuccess: () => history.back(),
    });
  });
}
