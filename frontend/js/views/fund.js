// Wallet funding flow (shared by Home & Wallet screens).
import { store } from "../api.js";
import { openSheet, copyText } from "../ui.js";
import { I } from "../icons.js";

const ACCTS = [
  { bank: "Palmpay", number: "8037465910", name: "Zaply Tech" },
  { bank: "Moniepoint", number: "5123456789", name: "Zaply Tech" },
  { bank: "Wema Bank", number: "0234567890", name: "Zaply Tech" },
];

function radio(name, val, label, checked) {
  return `<label class="fund-radio${checked ? " is-active" : ""}"><input type="radio" name="fund-acct" value="${val}"${checked ? " checked" : ""}><span class="fund-radio__dot"></span>${label}</label>`;
}

export function getAcct(val) {
  return ACCTS[Number(val)] || null;
}

export function openFundSheet(onClose) {
  const saved = localStorage.getItem("zaply_fund_acct");
  const initVal = saved || "0";
  const init = getAcct(initVal) || ACCTS[0];

  const sheet = openSheet(`
    <div class="sheet__grabber"></div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:2px">
      <div style="width:40px;height:40px;border-radius:12px;background:var(--brand-050);color:var(--brand-600);display:grid;place-items:center">${I.plus}</div>
      <div>
        <div class="sheet__title">Fund your wallet</div>
        <div class="sheet__subtitle">Select an account and transfer</div>
      </div>
    </div>

    <div class="fund-radios" id="fund-radios">
      ${radio("fund-acct", "0", "Palmpay", initVal === "0")}
      ${radio("fund-acct", "1", "Moniepoint", initVal === "1")}
      ${radio("fund-acct", "2", "Wema Bank", initVal === "2")}
    </div>

    <div class="bank-card" style="margin-top:10px" id="fd-card">
      <div class="bank-card__head">
        <span class="bank-card__logo">${I.wallet}</span>
        <div style="min-width:0">
          <div class="bank-card__bank" id="fd-bank">${esc(init.bank)}</div>
          <div class="bank-card__name" id="fd-name">${esc(init.name)}</div>
        </div>
        <span class="bank-card__badge">Transfers</span>
      </div>
      <div class="bank-card__num-row">
        <span class="bank-card__num num" id="fd-num">${esc(init.number)}</span>
        <button class="copy-btn" id="fd-copy" data-copy="${esc(init.number)}" aria-label="Copy account number">${I.copy} Copy</button>
      </div>
      <p class="bank-card__hint">Transfer to this account and your wallet is credited instantly.</p>
    </div>
  `, { onClose: () => onClose?.() });

  sheet.querySelector("#fund-radios").addEventListener("change", (e) => {
    if (e.target.name !== "fund-acct") return;
    sheet.querySelectorAll(".fund-radio").forEach((r) => r.classList.toggle("is-active", r.querySelector("input").checked));
    localStorage.setItem("zaply_fund_acct", e.target.value);
  });

  sheet.querySelector("#fd-copy").addEventListener("click", (e) => {
    copyText(e.currentTarget.dataset.copy);
  });
}

function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
