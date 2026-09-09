import { get, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";
import { fmtPhone, CHECK } from "../networks.js";

const AMOUNTS = [100, 200, 500, 1000, 2000, 5000];
const MIN = 100;
const MAX = 5000;

export function renderTransfer(screen) {
  let recipient = null;
  const state = { phone: "", amount: 0 };

  screen.innerHTML = `
    ${appBar({ title: "Send Money", sub: "Transfer to any Zaply user" })}

    <section class="hero-preview" id="preview" aria-live="polite">
      <span class="hero-preview__logo" id="pv-logo" style="background:var(--brand);color:#fff;">${I.out}</span>
      <div class="hero-preview__body">
        <div class="hero-preview__to">Sending to</div>
        <div class="hero-preview__num num" id="pv-num">Enter a number</div>
        <div class="hero-preview__net" id="pv-net">Search for a Zaply user</div>
      </div>
      <div class="hero-preview__amt"><b class="num" id="pv-amt">₦0</b><small id="pv-plan">no amount yet</small></div>
    </section>

    <section class="card form-card">
      <label class="field__label" for="phone">Recipient phone number</label>
      <div class="phone-field">
        <span class="phone-field__tile" id="phone-tile" style="background:var(--brand);color:#fff;">${I.out}</span>
        <input id="phone" type="tel" inputmode="tel" placeholder="0801 234 5678" maxlength="13" autocomplete="tel" />
        <button class="phone-field__clear" id="clear-btn" type="button" aria-label="Clear number" hidden>${I.close}</button>
        <button class="btn--sm btn btn--soft" id="me-btn" type="button" style="display:none">Me</button>
      </div>

      <div id="recipient-box" hidden>
        <div class="recipient-card" id="recipient-card">
          <div class="recipient-info">
            <span class="recipient-avatar" id="rc-avatar"></span>
            <div>
              <div class="recipient-name" id="rc-name"></div>
              <div class="recipient-phone num" id="rc-phone"></div>
            </div>
          </div>
          <span class="recipient-check">${CHECK}</span>
        </div>

        <label class="field__label" style="margin-top:14px" for="amt">Amount (₦)</label>
        <div class="amount-wrap">
          <span class="cur">₦</span>
          <input id="amt" type="number" inputmode="numeric" placeholder="0" min="${MIN}" max="${MAX}" />
        </div>
        <div class="chip-row chip-row--line" id="chips">
          ${AMOUNTS.map((a) => `<button class="chip num" data-a="${a}">₦${a.toLocaleString()}</button>`).join("")}
        </div>
        <div class="field__error" id="amt-err" hidden></div>
        <div class="field__hint" style="margin:6px 0 12px">Min ₦${MIN.toLocaleString()} · Max ₦${MAX.toLocaleString()}</div>
      </div>

      <div id="search-err" class="field__error" hidden></div>
    </section>

    <section class="section" id="recent-sec" hidden>
      <div class="field__label">Recent transfers</div>
      <div class="recent-scroll" id="recent"></div>
    </section>

    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="buy" disabled>Send Money</button>
    </div>`;

  const $ = (sel) => screen.querySelector(sel);
  const phoneEl = $("#phone");
  const amtEl = $("#amt");
  const buyBtn = $("#buy");

  let searchTimeout = null;

  loadRecent();

  phoneEl.addEventListener("input", () => {
    state.phone = phoneEl.value.replace(/\D/g, "").slice(0, 11);
    phoneEl.value = fmtPhone(state.phone);
    const clearBtn = $("#clear-btn");
    if (clearBtn) clearBtn.hidden = !state.phone;
    recipient = null;
    $("#recipient-box").hidden = true;
    $("#search-err").hidden = true;
    clearTimeout(searchTimeout);
    if (/^0[789]\d{9}$/.test(state.phone)) {
      searchTimeout = setTimeout(() => lookupRecipient(), 400);
    }
    update();
  });

  $("#clear-btn").addEventListener("click", () => {
    state.phone = "";
    phoneEl.value = "";
    recipient = null;
    $("#recipient-box").hidden = true;
    $("#search-err").hidden = true;
    clearTimeout(searchTimeout);
    update();
  });

  $("#me-btn")?.addEventListener("click", () => {
    if (!store.user?.phone) return;
    state.phone = store.user.phone.replace(/\D/g, "").slice(0, 11);
    phoneEl.value = fmtPhone(state.phone);
    recipient = null;
    $("#recipient-box").hidden = true;
    $("#search-err").hidden = true;
    clearTimeout(searchTimeout);
    if (/^0[789]\d{9}$/.test(state.phone)) {
      searchTimeout = setTimeout(() => lookupRecipient(), 400);
    }
    update();
  });

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

  async function lookupRecipient() {
    const errBox = $("#search-err");
    errBox.hidden = true;
    try {
      const d = await get(`/transfer/recipient/${state.phone}`);
      recipient = d;
      const initials = (d.name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
      $("#rc-avatar").textContent = initials;
      $("#rc-name").textContent = d.name;
      $("#rc-phone").textContent = fmtPhone(d.phone);
      $("#recipient-box").hidden = false;
      $("#pv-num").textContent = fmtPhone(d.phone);
      $("#pv-net").textContent = d.name;
    } catch (ex) {
      recipient = null;
      $("#recipient-box").hidden = true;
      errBox.textContent = ex.message;
      errBox.hidden = false;
    }
    update();
  }

  function amountError() {
    if (!amtEl.value) return "";
    if (state.amount < MIN) return `Minimum amount is ₦${MIN.toLocaleString()}`;
    if (state.amount > MAX) return `Maximum amount is ₦${MAX.toLocaleString()}`;
    return "";
  }

  function update() {
    const pvNum = $("#pv-num");
    pvNum.textContent = recipient ? fmtPhone(recipient.phone) : state.phone ? fmtPhone(state.phone) : "Enter a number";
    const pvNet = $("#pv-net");
    pvNet.textContent = recipient ? recipient.name : "Search for a Zaply user";
    $("#pv-amt").textContent = state.amount > 0 ? `₦${state.amount.toLocaleString()}` : "₦0";
    $("#pv-plan").textContent = state.amount > 0 ? "transfer" : "no amount yet";

    const clearBtn = $("#clear-btn");
    if (clearBtn) clearBtn.hidden = !state.phone;

    const meBtn = $("#me-btn");
    if (meBtn) meBtn.style.display = state.phone ? "none" : store.user?.phone ? "" : "none";

    screen.querySelectorAll("#chips .chip").forEach((c) =>
      c.classList.toggle("is-active", Number(c.dataset.a) === state.amount)
    );

    const err = amountError();
    const amtErr = $("#amt-err");
    if (amtErr) { amtErr.hidden = !err; amtErr.textContent = err; }

    const phoneOk = /^0[789]\d{9}$/.test(state.phone);
    const amtOk = state.amount >= MIN && state.amount <= MAX;
    buyBtn.disabled = !(recipient && phoneOk && amtOk && state.amount > 0);
    buyBtn.textContent = state.amount > 0 ? `Send ₦${state.amount.toLocaleString()}` : "Send Money";

    const bal = naira(store.balanceKobo || 0);
    const short = state.amount > 0 && (store.balanceKobo || 0) < state.amount * 100;
    $("#dock-total").textContent = state.amount > 0 ? `₦${state.amount.toLocaleString()}` : "₦0";
    $("#dock-bal").innerHTML = state.amount > 0
      ? short
        ? `<span class="bal-bad">Balance ${bal} — too low</span>`
        : `<span class="bal-ok">Balance ${bal}</span>`
      : "";
  }

  buyBtn.addEventListener("click", () => {
    if (!recipient) return;
    confirmAndPay({
      title: "Confirm transfer",
      subtitle: "Review the details before you continue",
      summaryRows: [
        ["Recipient", recipient.name],
        ["Phone", fmtPhone(recipient.phone)],
        ["Type", "Wallet transfer"],
      ],
      totalKobo: state.amount * 100,
      endpoint: "/transfer/send",
      payload: { recipient_phone: recipient.phone, amount_naira: state.amount },
      onSuccess: () => history.back(),
    });
  });

  async function loadRecent() {
    try {
      const d = await get("/transactions?per_page=25");
      if (!store.session) return;
      const seen = new Set();
      const people = d.items
        .filter((t) => t.service_type === "transfer" && /^0[789]\d{9}$/.test(t.customer_ref || ""))
        .filter((t) => !seen.has(t.customer_ref) && seen.add(t.customer_ref))
        .slice(0, 4);
      if (!people.length) return;
      $("#recent-sec").hidden = false;
      $("#recent").innerHTML = people
        .map(
          (p) => `
          <button class="recent-chip" data-num="${esc(p.customer_ref)}" data-name="${esc(p.title || "")}">
            <i>${esc(p.customer_ref.slice(1, 3))}</i><span class="num">${fmtPhone(p.customer_ref)}</span>
          </button>`
        )
        .join("");
      screen.querySelectorAll(".recent-chip").forEach((c) =>
        c.addEventListener("click", () => {
          state.phone = c.dataset.num;
          phoneEl.value = fmtPhone(state.phone);
          recipient = null;
          $("#recipient-box").hidden = true;
          $("#search-err").hidden = true;
          clearTimeout(searchTimeout);
          if (/^0[789]\d{9}$/.test(state.phone)) {
            searchTimeout = setTimeout(() => lookupRecipient(), 400);
          }
          update();
        })
      );
    } catch {
      /* optional feature — stay quiet */
    }
  }
}
