import { get, post, store } from "../api.js";
import { I } from "../icons.js";
import { esc, toast, naira } from "../ui.js";
import { appBar } from "../app.js";
import { confirmAndPay } from "./purchase.js";

export function renderEducation(screen) {
  let institutions = [];
  let institution = null;
  let student = null; // {student_name}
  const state = { ref: "", amount: 0 };

  screen.innerHTML = `
    ${appBar({ title: "School Fees", sub: "Pay any supported institution" })}
    <section class="section">
      <div class="field__label">Select institution</div>
      <div id="institutions" style="display:grid;gap:9px">${'<div class="skel" style="height:62px"></div>'.repeat(3)}</div>
    </section>
    <section class="section" hidden id="form-part">
      <div class="field">
        <label class="field__label" for="ref">Student / Matric / Application no.</label>
        <div class="field__wrap">
          ${I.graduation.replace('width="21" height="21"', 'width="18" height="18"')}
          <input id="ref" type="text" placeholder="e.g. 20191234567" maxlength="40" />
          <button type="button" class="btn btn--soft btn--sm" id="validate-btn">Validate</button>
        </div>
      </div>
      <div id="student-box"></div>
      <div class="field" style="margin-top:6px">
        <label class="field__label" for="amt">Amount</label>
        <div class="field__wrap"><span style="font-size:18px;font-weight:700">₦</span><input id="amt" class="input-amount" type="number" inputmode="numeric" placeholder="0" min="100" /></div>
      </div>
    </section>
    <div style="height:118px"></div>

    <div class="buy-dock">
      <div class="buy-dock__meta num">
        <span>Total <b id="dock-total">₦0</b></span>
        <span id="dock-bal"></span>
      </div>
      <button class="btn btn--primary" id="pay" disabled>Pay Fees</button>
    </div>`;

  load();
  async function load() {
    try {
      institutions = await get("/education/institutions");
      const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("p");
      if (pre) {
        institution = institutions.find((i) => i.code === pre) || null;
        if (institution) screen.querySelector("#form-part").hidden = false;
      }
      paint();
      update();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function paint() {
    const box = screen.querySelector("#institutions");
    box.innerHTML = institutions
      .map(
        (i) => `
        <button class="provider-card ${institution?.code === i.code ? "is-active" : ""}" style="grid-template-columns:auto 1fr auto;display:flex;width:100%" data-code="${esc(i.code)}">
          <span class="provider-card__logo" style="background:${esc(i.color || "#1B4FA0")}">${esc(i.short_name.slice(0, 2).toUpperCase())}</span>
          <span>${esc(i.name)}</span>
          <span class="radio-dot"></span>
        </button>`
      )
      .join("");
    box.querySelectorAll("[data-code]").forEach((b) =>
      b.addEventListener("click", () => {
        institution = institutions.find((x) => x.code === b.dataset.code);
        student = null;
        state.ref = "";
        screen.querySelector("#ref").value = "";
        screen.querySelector("#student-box").innerHTML = "";
        screen.querySelector("#form-part").hidden = false;
        paint();
        invalidate();
        update();
      })
    );
  }

  function invalidate() {
    if (student && state.ref && !student.ref.startsWith(state.ref)) student = null;
    if (!state.ref) student = null;
    screen.querySelector("#validate-btn").disabled = state.ref.length < 5;
    update();
  }

  screen.querySelector("#ref").addEventListener("input", (e) => {
    state.ref = e.target.value.trim();
    invalidate();
  });
  screen.querySelector("#amt").addEventListener("input", (e) => { state.amount = Number(e.target.value); update(); });

  screen.querySelector("#validate-btn").addEventListener("click", async () => {
    const btn = screen.querySelector("#validate-btn");
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const info = await post("/education/validate", { institution_code: institution.code, student_ref: state.ref });
      student = info.found ? { ...info, ref: state.ref } : null;
      screen.querySelector("#student-box").innerHTML = info.found
        ? `
          <div class="customer-card">
            <span class="customer-card__icon">${I.checkCircle.replace('width="54" height="54"', 'width="26" height="26"')}</span>
            <div>
              <div class="customer-card__name">${esc(info.customer_name)}</div>
              <div class="customer-card__addr">${esc(institution.short_name)} · ${esc(state.ref)}</div>
            </div>
          </div>`
        : `
          <div class="customer-card" style="background:var(--danger-050);border-color:#fbd5d1">
            <span class="customer-card__icon" style="color:var(--danger)">!</span>
            <div><div class="customer-card__name">Record not found</div>
            <div class="customer-card__addr">Check the student number and try again.</div></div>
          </div>`;
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "Validate";
      update();
    }
  });

  function update() {
    const ok = institution && student && state.amount >= 100;
    screen.querySelector("#pay").disabled = !ok;
    screen.querySelector("#pay").textContent = state.amount >= 100 ? `Pay ₦${state.amount.toLocaleString()}` : "Pay Fees";

    // dock
    const total = state.amount >= 100 ? state.amount : 0;
    screen.querySelector("#dock-total").textContent = `₦${total.toLocaleString()}`;
    const bal = naira(store.balanceKobo || 0);
    const short = total > 0 && (store.balanceKobo || 0) < total * 100;
    screen.querySelector("#dock-bal").innerHTML = short
      ? `<span class="bal-bad">Balance ${bal} — too low</span>`
      : `<span class="bal-ok">Balance ${bal}</span>`;
  }

  screen.querySelector("#pay").addEventListener("click", () => {
    confirmAndPay({
      title: "Confirm school fees payment",
      subtitle: "A receipt number is generated instantly",
      summaryRows: [
        ["Institution", institution.name],
        ["Student", `${student.customer_name} · ${state.ref}`],
      ],
      totalKobo: state.amount * 100,
      endpoint: "/education/pay",
      payload: {
        institution_code: institution.code,
        student_ref: state.ref,
        student_name: student.customer_name || "",
        amount_naira: state.amount,
        phone: store.user?.phone,
      },
      onSuccess: () => history.back(),
    });
  });
}
