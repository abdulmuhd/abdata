import { I, statusIcon } from "./icons.js";

// ── formatting ─────────────────────────────────────────────
const nairaFmt = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", minimumFractionDigits: 0 });

export function naira(kobo, { sign = false } = {}) {
  const v = (kobo || 0) / 100;
  const s = nairaFmt.format(Math.abs(v));
  if (!sign) return v < 0 ? `-${s}` : s;
  return `${v >= 0 ? "+" : "-"}${s}`;
}

export function shortDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit", hour12: true });
  if (sameDay) return `Today ${time}`;
  return `${d.toLocaleDateString("en-NG", { day: "numeric", month: "short" })}, ${time}`;
}

export function fullDate(iso) {
  return new Date(iso).toLocaleString("en-NG", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const initials = (name = "?") =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard", "ok");
  } catch {
    toast(text, "ok");
  }
}

// ── toast ──────────────────────────────────────────────────
export function toast(message, kind = "info") {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast ${kind === "err" ? "err" : "ok"}`;
  el.innerHTML = `${kind === "err" ? I.xCircle : I.checkCircle}<span>${esc(message)}</span>`;
  root.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .25s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 260);
  }, 2600);
}

// ── bottom sheet ───────────────────────────────────────────
export function openSheet(html, { onClose } = {}) {
  closeSheet();
  const root = document.getElementById("sheet-root");
  const backdrop = document.createElement("div");
  backdrop.className = "sheet-backdrop";
  backdrop.innerHTML = `<div class="sheet" role="dialog">${html}</div>`;
  root.appendChild(backdrop);
  document.body.style.overflow = "hidden";

  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeSheet(); });
  window.__sheetCleanup = () => onClose?.();
  return backdrop;
}

export function closeSheet() {
  const root = document.getElementById("sheet-root");
  if (window.__sheetCleanup) { window.__sheetCleanup(); window.__sheetCleanup = null; }
  if (root) root.innerHTML = "";
  document.body.style.overflow = "";
}
window.closeSheet = closeSheet;

// ── processing overlay ─────────────────────────────────────
export function showProcessing(label = "Processing your transaction…") {
  const root = document.getElementById("sheet-root");
  const el = document.createElement("div");
  el.className = "processing-backdrop";
  el.id = "processing-overlay";
  el.innerHTML = `
    <div class="processing-box">
      <div class="spinner"></div>
      <h3>Hold on…</h3>
      <p>${esc(label)} Do not close the app.</p>
    </div>`;
  root.appendChild(el);
}
export function hideProcessing() {
  document.getElementById("processing-overlay")?.remove();
}

// ── PIN pad sheet ──────────────────────────────────────────
export function requestPin({ title = "Enter transaction PIN", subtitle = "Confirm this payment with your 4-digit PIN", onSubmit }) {
  let pin = "";
  const sheet = openSheet(`
    <div class="sheet__grabber"></div>
    <div style="display:flex;align-items:center;gap:12px">
      <div style="width:40px;height:40px;border-radius:12px;background:var(--brand-050);color:var(--brand-600);display:grid;place-items:center">${I.lock}</div>
      <div><div class="sheet__title">${esc(title)}</div>
      <div class="sheet__subtitle">${esc(subtitle)}</div></div>
    </div>
    <div class="pin-dots" id="pin-dots"><i></i><i></i><i></i><i></i></div>
    <p style="text-align:center;font-size:11.5px;color:var(--faint)">Your PIN is never stored on this device</p>
    <div class="keypad" id="keypad">
      ${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button data-k="${n}">${n}</button>`).join("")}
      <button data-k="" disabled style="opacity:0;pointer-events:none">·</button>
      <button data-k="0">0</button>
      <button data-k="del" aria-label="delete">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 5.5H9L3.5 12 9 18.5h11a1.5 1.5 0 0 0 1.5-1.5V7A1.5 1.5 0 0 0 20 5.5Z"/><path d="m16.5 9.5-4 5M12.5 9.5l4 5"/></svg>
      </button>
    </div>`);

  const dots = [...sheet.querySelectorAll("#pin-dots i")];
  const render = () => dots.forEach((d, i) => d.classList.toggle("filled", i < pin.length));

  sheet.querySelector("#keypad").addEventListener("click", (e) => {
    const k = e.target.closest("button")?.dataset.k;
    if (k === undefined || k === "") return;
    if (k === "del") pin = pin.slice(0, -1);
    else if (pin.length < 4) pin += k;
    render();
    if (pin.length === 4) {
      setTimeout(async () => {
        try {
          await onSubmit(pin);
        } finally {
          // reset for potential retry
          pin = "";
          render();
        }
      }, 130);
    }
  });
}

// ── result / receipt sheet ─────────────────────────────────
export function showResult({ txn, onDone }) {
  const okState = txn.status === "successful";
  const pend = txn.status === "pending";
  const d = txn.details || {};
  let pinBlock = "";
  const rows = [];
  const addRow = (k, v) => v && rows.push(`<div class="summary-row"><span class="summary-row__k">${k}</span><span class="summary-row__v">${esc(v)}</span></div>`);

  if (txn.service_type === "airtime") addRow("Recipient", txn.customer_ref), addRow("Network", d.network);
  if (txn.service_type === "data") addRow("Recipient", txn.customer_ref), addRow("Plan", `${d.plan_name || ""} · ${d.validity_days} days`), addRow("Network", d.network);
  if (txn.service_type === "electricity") addRow("Meter", txn.customer_ref), addRow("Provider", d.provider), addRow("Customer", d.customer_name), addRow("Meter type", d.meter_type ? d.meter_type[0].toUpperCase() + d.meter_type.slice(1) : null);
  if (txn.service_type === "cable") addRow("Smartcard", txn.customer_ref), addRow("Package", d.package_name), addRow("Customer", d.customer_name);
  if (txn.service_type === "exam_pins") {
    addRow("Body", d.provider), addRow("Product", d.product_name);
    if (d.exam_pin) pinBlock = `
      <div class="customer-card" style="background:var(--brand-050);border-color:var(--brand-100);margin-top:12px">
        <span class="customer-card__icon" style="color:var(--brand-600)">${I.lock}</span>
        <div style="min-width:0;flex:1">
          <div class="customer-card__name">Your PIN</div>
          <div class="num" id="exam-pin-value" style="font-size:17px;font-weight:800;letter-spacing:.08em;margin:2px 0">${esc(d.exam_pin)}</div>
          ${d.exam_serial ? `<div class="customer-card__addr num">Serial: ${esc(d.exam_serial)}</div>` : ""}
        </div>
        <span class="ref-copy" id="copy-exam-pin">${I.copy}</span>
      </div>`;
  }
  if (txn.service_type === "education") addRow("Institution", d.provider), addRow("Student / Ref", txn.customer_ref), addRow("Student name", d.customer_name), addRow("Receipt no.", d.school_fee_receipt_no);

  const sheet = openSheet(`
    <div class="sheet__grabber"></div>
    <div class="result-hero">
      ${pend ? I.clock : okState ? I.checkCircle : I.xCircle}
      <div class="result-hero__amount num">${naira(txn.amount_kobo)}</div>
      <div class="result-hero__label">${
        okState ? "Payment successful" : pend ? "Transaction processing" : "Transaction failed"
      }</div>
    </div>

    ${
      !okState && !pend && txn.failure_reason
        ? `<div class="customer-card" style="background:var(--danger-050);border-color:#fbd5d1">
             <span class="customer-card__icon" style="color:var(--danger)">!</span>
             <div><div class="customer-card__name">What happened?</div>
             <div class="customer-card__addr">${esc(txn.failure_reason)}${!okState && !pend ? " Any debited amount has been refunded." : ""}</div></div>
           </div>`
        : ""
    }

    <div class="receipt">
      ${rows.map((r) => r).join("")}
      <div class="summary-row"><span class="summary-row__k">Date</span><span class="summary-row__v">${fullDate(txn.created_at)}</span></div>
      <div class="summary-row summary-total"><span class="summary-row__k">Amount</span><span class="summary-row__v num">${naira(txn.amount_kobo)}</span></div>
      <div class="summary-row">
        <span class="summary-row__k">Reference</span>
        <span class="summary-row__v ref-copy" id="copy-ref">${esc(txn.reference)} ${I.copy}</span>
      </div>
    </div>

    ${pinBlock || ""}

    <button class="btn btn--primary" id="result-done">Done</button>
    <button class="btn btn--ghost" id="result-share" style="margin-top:10px">${I.share} Share receipt</button>
  `);

  sheet.querySelector("#copy-ref").addEventListener("click", () => copyText(txn.reference));
  const pinEl = sheet.querySelector("#copy-exam-pin");
  if (pinEl) pinEl.addEventListener("click", () => copyText(d.exam_pin));
  sheet.querySelector("#result-done").addEventListener("click", () => { closeSheet(); onDone?.(); });
  sheet.querySelector("#result-share").addEventListener("click", () => {
    const text = `Zaply ${okState ? "receipt" : "update"}\nAmount: ${naira(txn.amount_kobo)}\nStatus: ${txn.status}\nReference: ${txn.reference}`;
    if (navigator.share) navigator.share({ title: "Zaply receipt", text }).catch(() => {});
    else copyText(text);
  });
}

// ── skeletons & empties ────────────────────────────────────
export const skeletonRows = (n = 4) =>
  `<div style="display:grid;gap:8px;margin-top:8px">${Array.from({ length: n }, () => `<div class="skel"></div>`).join("")}</div>`;

export const emptyState = (title, body, icon) => `
  <div class="empty-state">${icon || I.inbox}<h4>${esc(title)}</h4><p>${esc(body)}</p></div>`;

// ── status pill ────────────────────────────────────────────
export const pill = (status) =>
  `<span class="status-pill ${status}">${status === "successful" ? "Successful" : status[0].toUpperCase() + status.slice(1)}</span>`;
