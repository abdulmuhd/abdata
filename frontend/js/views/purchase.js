// Shared purchase flow: confirm → PIN → processing → result.
import { post, get, store, api } from "../api.js";
import { requestPin, showProcessing, hideProcessing, showResult, openSheet, closeSheet, toast, esc, naira } from "../ui.js";
import { refreshBalance, navigate } from "../app.js";

let appliedPromo = null;

function promoRowHtml() {
  if (!appliedPromo) return "";
  return `
    <div class="summary-row" style="color:var(--success)">
      <span class="summary-row__k">Promo (${esc(appliedPromo.code)})</span>
      <span class="summary-row__v">-${naira(appliedPromo.discount_kobo)}</span>
    </div>`;
}

export function confirmAndPay({ title, subtitle, summaryRows, totalKobo, endpoint, payload, onSuccess }) {
  appliedPromo = null;
  const finalKobo = () => totalKobo - (appliedPromo?.discount_kobo || 0);

  const rowsHtml = summaryRows
    .map(([k, v]) => `<div class="summary-row"><span class="summary-row__k">${esc(k)}</span><span class="summary-row__v">${esc(v)}</span></div>`)
    .join("");

  const sheetHtml = `
    <div class="sheet__grabber"></div>
    <div class="sheet__title">${esc(title)}</div>
    <div class="sheet__subtitle">${esc(subtitle)}</div>
    <div class="receipt" style="margin-top:16px">
      ${rowsHtml}
      <div id="promo-area" hidden>
        <div style="display:flex;gap:8px;margin:8px 0">
          <input id="promo-input" class="input" placeholder="Promo code (optional)" style="text-transform:uppercase;flex:1;margin:0" />
          <button class="btn btn--primary btn--sm" id="promo-apply" style="margin:0;white-space:nowrap">Apply</button>
        </div>
        <div id="promo-msg" style="font-size:12px;margin-top:2px"></div>
      </div>
      <div id="promo-row"></div>
      <div class="summary-row summary-total">
        <span class="summary-row__k">Total</span>
        <span class="summary-row__v num" id="total-display">${naira(totalKobo)}</span>
      </div>
      <div class="summary-row">
        <span class="summary-row__k">Wallet balance</span>
        <span class="summary-row__v num" style="color:${store.balanceKobo >= totalKobo ? "var(--success)" : "var(--danger)"}">${naira(store.balanceKobo)}</span>
      </div>
    </div>
    <button class="btn btn--primary" id="confirm-pay">Confirm payment</button>
    <button class="btn btn--ghost" style="margin-top:10px" onclick="closeSheet()">Cancel</button>
  `;

  openSheet(sheetHtml);

  // Check for active promos and show/hide the promo area
  get("/users/me/active-promos").then((d) => {
    const promoArea = document.getElementById("promo-area");
    if (promoArea && d?.has_promos) promoArea.hidden = false;
  }).catch(() => {});

  document.getElementById("promo-apply").addEventListener("click", async () => {
    const code = document.getElementById("promo-input").value.trim();
    if (!code) return;
    const msg = document.getElementById("promo-msg");
    try {
      msg.textContent = "Checking...";
      msg.style.color = "var(--muted)";
      const res = await api(`/admin/promos/validate/${encodeURIComponent(code)}?amount_kobo=${totalKobo}`);
      appliedPromo = res.data;
      msg.textContent = `${appliedPromo.code} — ${naira(appliedPromo.discount_kobo)} discount applied`;
      msg.style.color = "var(--success)";
      document.getElementById("promo-row").innerHTML = promoRowHtml();
      document.getElementById("total-display").textContent = naira(finalKobo());
      document.getElementById("promo-area").hidden = true;
    } catch (err) {
      appliedPromo = null;
      msg.textContent = err.message || "Invalid promo code";
      msg.style.color = "var(--danger)";
    }
  });

  document.getElementById("confirm-pay").addEventListener("click", () => {
    const payKobo = finalKobo();
    if (store.balanceKobo < payKobo) {
      toast("Insufficient wallet balance — fund your wallet first", "err");
      return;
    }
    requestPin({
      onSubmit: async (pin) => {
        closeSheet();
        showProcessing();
        const idem = payload.idempotency_key || crypto.randomUUID();
        try {
          const txn = await post(endpoint, { ...payload, idempotency_key: idem, pin, promo_code: appliedPromo?.code || null });
          await new Promise((r) => setTimeout(r, 900)); // let the user read the processing state
          hideProcessing();
          await refreshBalance();
          showResult({ txn, onDone: () => onSuccess?.(txn) });
        } catch (err) {
          await new Promise((r) => setTimeout(r, 600));
          hideProcessing();
          if (err.code === "pin_not_set") {
            toast(err.message, "err");
            navigate("/settings/pin");
            return;
          }
          toast(err.message, "err");
        }
      },
    });
  });
}

export function goHome() {
  navigate("/home");
}
