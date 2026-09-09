import { get, post, store } from "../api.js";
import { I } from "../icons.js";
import { naira, shortDate, esc, pill, skeletonRows, emptyState, copyText, openSheet, closeSheet, fullDate, toast } from "../ui.js";
import { appBar, navigate } from "../app.js";
import { openFundSheet, getAcct } from "./fund.js";
import { TYPE_STYLE } from "./notifications.js";

let hideBalance = false;

const QUICK = [
  { path: "/airtime", label: "Airtime", icon: I.airtime, bg: "#e40000" },
  { path: "/data", label: "Data", icon: I.data, bg: "var(--brand)" },
  { path: "/electricity", label: "Electricity", icon: I.electricity, bg: "#f79009" },
  { path: "/cable", label: "Cable TV", icon: I.cable, bg: "#0a5da6" },
];

function txnIcon(item) {
  if (item.txn_type === "funding") return { el: `<span style="color:var(--success)">${I.in}</span>`, bg: "var(--success-050)" };
  if (item.txn_type === "refund") return { el: `<span style="color:#175cd3">${I.in}</span>`, bg: "var(--info-050)" };
  const map = {
    airtime: { i: I.airtime, bg: "#fee2e2", c: "#e40000" },
    data: { i: I.data, bg: "var(--brand-050)", c: "var(--brand-600)" },
    electricity: { i: I.electricity, bg: "var(--warn-050)", c: "#c77400" },
    cable: { i: I.cable, bg: "#e0ecfa", c: "#0a5da6" },
    exam_pins: { i: I.graduation, bg: "#f1eafb", c: "#5b2d8e" },
    education: { i: I.school, bg: "#fdf3e7", c: "#b25e09" },
  };
  const m = map[item.service_type] || map.airtime;
  return { el: `<span style="color:${m.c}">${m.i}</span>`, bg: m.bg };
}

export function txnRow(item) {
  const ic = txnIcon(item);
  return `
    <button class="txn-row" data-ref="${esc(item.reference)}">
      <div class="txn-row__icon" style="background:${ic.bg}">${ic.el}</div>
      <div class="txn-row__body">
        <div class="txn-row__title">${esc(item.title)}</div>
        <div class="txn-row__date num">${shortDate(item.created_at)}</div>
      </div>
      <div class="txn-row__right">
        <div class="txn-row__amt num ${item.direction === "credit" ? "credit" : ""}">${
          item.direction === "credit" ? "+" : ""
        }${naira(item.amount_kobo)}</div>
        ${pill(item.status)}
      </div>
    </button>`;
}

export function renderHome(screen, isCurrent) {
  const name = (store.user?.full_name || "").split(" ")[0];
  const bank = store.bank;

  screen.innerHTML = `
    <header class="appbar">
      <div class="avatar" style="width:34px;height:34px"><img src="/img/user.png" alt="${esc(name || "Profile")}" /></div>
      <div style="flex:1;min-width:0">
        <div class="appbar__sub">Good ${greeting()},</div>
        <div class="appbar__title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(name || "there")} 👋</div>
      </div>
      <a class="icon-btn" href="#/notifications" aria-label="Notifications">
        ${I.bell}${(store.unread || 0) > 0 ? '<span class="dot"></span>' : ""}
      </a>
    </header>

    <section class="balance-card">
      <div class="balance-card__label">
        <span>Zaply balance</span>
        <button class="balance-card__eye" id="eye-btn" aria-label="Toggle balance visibility">${hideBalance ? I.eyeOff : I.eye}</button>
      </div>
      <div class="balance-card__amount num" id="bal-amt">${hideBalance ? "₦ ••••••" : naira(store.balanceKobo)}</div>
      <div class="balance-card__meta">
        <button class="btn-fund" id="fund-btn">${I.in} Fund Wallet</button>
        <button class="btn-transfer" id="transfer-btn">${I.out} Transfer</button>
      </div>
    </section>

    <section class="bonus-card">
      <div class="bonus-card__row">
        <span class="bonus-card__icon">🎁</span>
        <div class="bonus-card__info">
          <span class="bonus-card__label">Bonus balance</span>
          <span class="bonus-card__amount num">${hideBalance ? "₦ ••••••" : naira(store.bonusKobo)}</span>
        </div>
      </div>
    </section>

    ${
      (() => {
        const ACCTS = [
          { bank: "Palmpay", number: "8037465910", name: "Zaply Tech" },
          { bank: "Moniepoint", number: "5123456789", name: "Zaply Tech" },
          { bank: "Wema Bank", number: "0234567890", name: "Zaply Tech" },
        ];
        const saved = localStorage.getItem("zaply_fund_acct");
        if (saved === null) return "";
        const acct = ACCTS[Number(saved)] || ACCTS[0];
        return `
    <section class="section sec-sm" id="fund-section">
      <div class="bank-card" id="fund-bank-card">
        <div class="bank-card__head">
          <span class="bank-card__logo">${I.wallet}</span>
          <div style="min-width:0">
            <div class="bank-card__bank" id="fb-bank">${esc(acct.bank)}</div>
            <div class="bank-card__name" id="fb-name">${esc(acct.name)}</div>
          </div>
          <span class="bank-card__badge">Transfers</span>
        </div>
        <div class="bank-card__num-row">
          <span class="bank-card__num num" id="fb-num">${esc(acct.number)}</span>
          <button class="copy-btn" id="copy-acct" data-copy="${esc(acct.number)}" aria-label="Copy account number">${I.copy} Copy</button>
        </div>
        <p class="bank-card__hint">Transfer to this account and your wallet is credited instantly.</p>
      </div>
    </section>`;
      })()
    }

    <section class="section sec-sm">
      <div class="quick-grid">
        ${QUICK.map(
          (q) => `
          <a class="quick-tile" href="#${q.path}">
            <span class="tile-icon" style="background:${q.bg}">${q.icon}</span>${q.label}
          </a>`
        ).join("")}
      </div>
      <a class="quick-tile" href="#/services" style="flex-direction:row;justify-content:center;margin-top:8px;padding:10px">
        ${I.grid}<span style="font-size:13px">More Services</span>
      </a>
    </section>

    <section class="section sec-sm">
      <div class="section__head">
        <div class="section__title">Recent transactions</div>
        <a class="section__link" href="#/transactions">View all</a>
      </div>
      <div id="recent"><div class="skel"></div></div>
    </section>`;

  function updateBankCard() {
    const saved = localStorage.getItem("zaply_fund_acct");
    const section = screen.querySelector("#fund-section");
    if (saved === null) {
      if (section) section.remove();
      return;
    }
    const acct = getAcct(saved) || getAcct("0");
    if (!section) {
      renderHome(screen, isCurrent);
      return;
    }
    screen.querySelector("#fb-bank").textContent = acct.bank;
    screen.querySelector("#fb-name").textContent = acct.name;
    screen.querySelector("#fb-num").textContent = acct.number;
    screen.querySelector("#copy-acct").dataset.copy = acct.number;
  }

  screen.querySelector("#fund-btn").addEventListener("click", () => openFundSheet(updateBankCard));
  screen.querySelector("#transfer-btn").addEventListener("click", () => navigate("/transfer"));
  screen.querySelector("#eye-btn").addEventListener("click", () => {
    hideBalance = !hideBalance;
    renderHome(screen, isCurrent);
  });
  screen.querySelector("#copy-acct")?.addEventListener("click", (e) => {
    copyText(e.currentTarget.dataset.copy);
  });

  loadRecent(screen, isCurrent);
  showLatestNotif(screen, isCurrent);
  showAnnouncement(screen, isCurrent);
}

// Announcement popup — once per day, right after a successful sign-in.
async function showAnnouncement(screen, isCurrent) {
  try {
    if (!sessionStorage.getItem("zaply_announce")) return;
    sessionStorage.removeItem("zaply_announce");
    if (!isCurrent()) return;

    const a = await get("/announcements/active");
    if (!a?.id || !isCurrent()) return;

    const key = `zaply.ann.${a.id}`;
    const today = new Date().toDateString();
    if (localStorage.getItem(key) === today) return; // already shown today

    const dismiss = () => {
      try { localStorage.setItem(key, today); } catch {}
      closeSheet();
    };

    const sheet = openSheet(
      `
      <div class="sheet__grabber"></div>
      <div class="announce-hero">
        <span class="announce-hero__ico">${I.megaphone}</span>
        <span class="announce-hero__tag">Announcement</span>
      </div>
      <div class="sheet__title" style="text-align:center;margin-top:12px">${esc(a.title)}</div>
      <p class="announce-modal__body">${esc(a.body)}</p>
      ${a.cta_label ? `<button class="btn btn--primary" id="ann-cta">${esc(a.cta_label)}</button>` : ""}
      <button class="btn btn--ghost" id="ann-dismiss" style="margin-top:10px">Maybe later</button>`,
      { onClose: () => { try { localStorage.setItem(key, today); } catch {} } }
    );

    sheet.querySelector("#ann-dismiss").addEventListener("click", dismiss);
    sheet.querySelector("#ann-cta")?.addEventListener("click", () => {
      dismiss();
      toast(a.cta_label || "Let's go!", "ok");
      navigate(a.cta_path || "/home");
    });
  } catch {
    /* optional feature — stay quiet */
  }
}

// Popup for the newest unread notification — shown once per notification.
async function showLatestNotif(screen, isCurrent) {
  try {
    const d = await get("/notifications?per_page=1");
    const n = d.items?.[0];
    if (!n || n.is_read || !isCurrent()) return;

    const st = TYPE_STYLE[n.type] || TYPE_STYLE.system;
    let acknowledged = false;
    const acknowledge = async () => {
      if (acknowledged) return;
      acknowledged = true;
      try { await post(`/notifications/${n.id}/read`); } catch {}
      import("../app.js").then((m) => m.refreshBalance());
    };

    const sheet = openSheet(
      `
      <div class="sheet__grabber"></div>
      <div style="display:flex;flex-direction:column;align-items:center;text-align:center">
        <span class="notif-modal__ico" style="background:${st.bg};color:${st.c}">${st.i}</span>
        <span class="notif-modal__tag">New notification</span>
        <div class="sheet__title" style="margin-top:9px">${esc(n.title)}</div>
        <div class="notif-modal__date num">${fullDate(n.created_at)}</div>
      </div>
      <p class="notif-modal__body">${esc(n.body)}</p>
      <button class="btn btn--primary" id="nm-ok">Got it</button>
      <button class="btn btn--ghost" id="nm-all" style="margin-top:10px">View all notifications</button>`,
      { onClose: acknowledge }
    );

    sheet.querySelector("#nm-ok").addEventListener("click", closeSheet);
    sheet.querySelector("#nm-all").addEventListener("click", () => {
      location.hash = "#/notifications";
    });
  } catch {
    /* optional feature — stay quiet */
  }
}

async function loadRecent(screen, isCurrent) {
  try {
    const d = await get("/transactions?per_page=5");
    if (!isCurrent()) return;
    const box = screen.querySelector("#recent");
    if (!box) return;
    box.innerHTML = d.items.length
      ? `<div class="txn-list">${d.items.map(txnRow).join("")}</div>`
      : emptyState("No transactions yet", "Your airtime, data & bill payments will show up here.");
    box.querySelectorAll(".txn-row").forEach((row) =>
      row.addEventListener("click", () => import("./receipt-view.js").then((m) => m.openReceipt(row.dataset.ref)))
    );
  } catch {
    /* leave skeleton */
  }
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}
