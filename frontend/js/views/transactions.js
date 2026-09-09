import { get } from "../api.js";
import { I } from "../icons.js";
import { skeletonRows, emptyState, esc } from "../ui.js";
import { appBar } from "../app.js";
import { txnRow } from "./home.js";

const FILTERS = [
  { key: "", label: "All" },
  { key: "airtime", label: "Airtime" },
  { key: "data", label: "Data" },
  { key: "exam_pins", label: "Exam" },
  { key: "education", label: "School" },
  { key: "electricity", label: "Electricity" },
  { key: "cable", label: "Cable" },
  { key: "funding", label: "Funding" },
  { key: "refund", label: "Refunds" },
];

export function renderTransactions(screen, isCurrent) {
  let filter = "";
  let query = "";
  let page = 1;
  let items = [];
  let totalPages = 1;
  let debounceTimer = null;

  screen.innerHTML = `
    ${appBar({ title: "Transactions", sub: "Every payment in one place", back: false })}
    <div style="padding:2px 20px 0">
      <div class="field">
        <div class="field__wrap">
          ${I.search}
          <input id="txn-search" type="search" placeholder="Search reference, phone or narration" style="border:none;outline:none;background:transparent" />
        </div>
      </div>
    </div>
    <div class="filter-scroll" id="filters">
      ${FILTERS.map(
        (f) => `<button class="chip ${f.key === "" ? "is-active" : ""}" data-k="${f.key}">${f.label}</button>`
      ).join("")}
    </div>
    <section class="section"><div class="txn-cols" id="list">${skeletonRows(4)}</div></section>
    <div style="padding:14px 20px"><button class="btn btn--ghost" id="more" hidden>Load more</button></div>`;

  const listBox = screen.querySelector("#list");
  const moreBtn = screen.querySelector("#more");
  const searchEl = screen.querySelector("#txn-search");

  screen.querySelector("#filters").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    filter = chip.dataset.k;
    page = 1;
    items = [];
    screen.querySelectorAll("#filters .chip").forEach((c) => c.classList.toggle("is-active", c === chip));
    load();
  });

  moreBtn.addEventListener("click", () => { page += 1; load(true); });

  searchEl.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      query = searchEl.value.trim();
      page = 1;
      items = [];
      load();
    }, 350);
  });

  async function load(append = false) {
    if (!append) listBox.innerHTML = skeletonRows(4);
    moreBtn.hidden = true;
    try {
      const d = await get(
        `/transactions?per_page=10&page=${page}${filter ? `&service=${filter}` : ""}${query ? `&q=${encodeURIComponent(query)}` : ""}`
      );
      if (!isCurrent()) return;
      items = append ? items.concat(d.items) : d.items;
      totalPages = d.meta.total_pages;
      renderList();
    } catch (err) {
      if (isCurrent()) listBox.innerHTML = emptyState("Couldn't load", err.message);
    }
  }

  function renderList() {
    listBox.className = "txn-list";
    if (!items.length) {
      listBox.innerHTML = emptyState(
        query ? "No matches" : "Nothing here yet",
        query ? `Nothing found for “${esc(query)}”.` : "Purchases and wallet funding will appear here."
      );
    } else {
      listBox.innerHTML = items.map(txnRow).join("");
      listBox.querySelectorAll(".txn-row").forEach((row) =>
        row.addEventListener("click", () =>
          import("./receipt-view.js").then((m) => m.openReceipt(row.dataset.ref, { onDone: () => {} }))
        )
      );
    }
    moreBtn.hidden = page >= totalPages;
  }

  load();
}
