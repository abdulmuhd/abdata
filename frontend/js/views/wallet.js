import { get, store } from "../api.js";
import { I } from "../icons.js";
import { naira, shortDate, esc, skeletonRows, emptyState, copyText, fullDate } from "../ui.js";
import { appBar } from "../app.js";
import { openFundSheet, getAcct } from "./fund.js";

let hideBalance = false;

export function renderWallet(screen, isCurrent) {
  let tab = "all";
  let page = 1;
  let items = [];
  let totalPages = 1;

  screen.innerHTML = `
    ${appBar({ title: "Wallet", back: false })}

    <section class="balance-card">
      <div class="balance-card__label">
        <span>Available balance</span>
        <button class="balance-card__eye" id="eye-btn" aria-label="Toggle">${hideBalance ? I.eyeOff : I.eye}</button>
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

    <section class="section">
      <div class="filter-scroll" style="padding:0" id="tabs">
        <button class="chip is-active" data-t="all">All activity</button>
        <button class="chip" data-t="credit">Money in</button>
        <button class="chip" data-t="debit">Money out</button>
      </div>
      <div style="height:12px"></div>
      <div id="ledger">${skeletonRows(4)}</div>
    </section>
    <div style="padding:14px 20px"><button class="btn btn--ghost" id="more" hidden>Load more</button></div>`;

  screen.querySelector("#eye-btn").addEventListener("click", () => { hideBalance = !hideBalance; renderWallet(screen, isCurrent); });
  screen.querySelector("#transfer-btn").addEventListener("click", () => { location.hash = "#/transfer"; });
  screen.querySelector("#more").addEventListener("click", () => { page += 1; load(true); });

  function updateBankCard() {
    const saved = localStorage.getItem("zaply_fund_acct");
    const section = screen.querySelector("#fund-section");
    if (saved === null) {
      if (section) section.remove();
      return;
    }
    const acct = getAcct(saved) || getAcct("0");
    if (!section) {
      renderWallet(screen, isCurrent);
      return;
    }
    screen.querySelector("#fb-bank").textContent = acct.bank;
    screen.querySelector("#fb-name").textContent = acct.name;
    screen.querySelector("#fb-num").textContent = acct.number;
    screen.querySelector("#copy-acct").dataset.copy = acct.number;
  }

  screen.querySelector("#fund-btn").addEventListener("click", () => openFundSheet(updateBankCard));
  screen.querySelector("#copy-acct")?.addEventListener("click", (e) => {
    copyText(e.currentTarget.dataset.copy);
  });
  screen.querySelector("#tabs").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    tab = chip.dataset.t;
    page = 1;
    screen.querySelectorAll("#tabs .chip").forEach((c) => c.classList.toggle("is-active", c === chip));
    load();
  });

  const ledgerBox = screen.querySelector("#ledger");
  const moreBtn = screen.querySelector("#more");

  async function load(append = false) {
    if (!append) ledgerBox.innerHTML = skeletonRows(4);
    moreBtn.hidden = true;
    try {
      const d = await get(`/wallet/transactions?per_page=15&page=${page}${tab !== "all" ? `&direction=${tab}` : ""}`);
      if (!isCurrent()) return;
      items = append ? items.concat(d.items) : d.items;
      totalPages = d.meta.total_pages;
      render();
    } catch (err) {
      if (isCurrent()) ledgerBox.innerHTML = emptyState("Couldn't load", err.message);
    }
  }

  function row(t) {
    const credit = t.direction === "credit";
    const iconMap = { funding: I.in, refund: I.in, purchase: I.out, adjustment: I.out };
    const labelMap = { funding: "Wallet funding", refund: "Refund", purchase: "Payment", adjustment: "Adjustment" };
    return `
      <div class="txn-row" data-ref="${esc(t.reference.replace(/-D|-R|-C$/, ""))}" role="button">
        <div class="txn-row__icon" style="background:${credit ? "var(--success-050)" : "var(--brand-050)"};color:${credit ? "var(--success)" : "#c77400"}">${iconMap[t.category] || I.wallet}</div>
        <div class="txn-row__body">
          <div class="txn-row__title">${esc(labelMap[t.category] || t.category)}</div>
          <div class="txn-row__date num">${shortDate(t.created_at)} · Bal ${naira(t.balance_after_kobo)}</div>
        </div>
        <div class="txn-row__right">
          <div class="txn-row__amt num ${credit ? "credit" : ""}">${credit ? "+" : ""}${naira(credit ? t.amount_kobo : -t.amount_kobo)}</div>
          <div class="ref-copy" data-copy="${esc(t.reference)}" style="font-size:10.5px;margin-top:3px">${esc(t.reference.slice(0, 14))}…</div>
        </div>
      </div>`;
  }

  function render() {
    if (!items.length) {
      ledgerBox.innerHTML = emptyState("No wallet activity yet", "Funding and payments will appear here.");
    } else {
      ledgerBox.className = "txn-list";
      ledgerBox.innerHTML = items.map(row).join("");
      ledgerBox.querySelectorAll("[data-copy]").forEach((el) =>
        el.addEventListener("click", (e) => { e.stopPropagation(); copyText(el.dataset.copy); })
      );
      ledgerBox.querySelectorAll(".txn-row[data-ref]").forEach((el) =>
        el.addEventListener("click", () =>
          import("./receipt-view.js").then((m) => m.openReceipt(el.dataset.ref, { onDone: () => {} }))
        )
      );
    }
    moreBtn.hidden = page >= totalPages;
  }

  load();
}
