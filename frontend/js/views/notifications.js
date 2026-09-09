import { get, post } from "../api.js";
import { I } from "../icons.js";
import { esc, shortDate, skeletonRows, emptyState } from "../ui.js";
import { appBar } from "../app.js";

export const TYPE_STYLE = {
  transaction: { bg: "var(--brand-050)", c: "var(--brand-600)", i: I.receipt },
  wallet: { bg: "var(--info-050)", c: "#175cd3", i: I.wallet },
  security: { bg: "var(--warn-050)", c: "#c77400", i: I.shield },
  system: { bg: "#eceff2", c: "var(--ink-2)", i: I.bell },
};

export function renderNotifications(screen, isCurrent) {
  screen.innerHTML = `
    ${appBar({ title: "Notifications", back: false })}
    <section class="section" style="display:flex;justify-content:flex-end">
      <button class="btn btn--ghost btn--sm" id="read-all">Mark all as read</button>
    </section>
    <section class="section" id="list" style="display:grid;gap:8px;margin-top:4px">${skeletonRows(3)}</section>`;

  screen.querySelector("#read-all").addEventListener("click", async () => {
    await post("/notifications/read-all");
    load();
    import("../app.js").then((m) => m.refreshBalance());
  });

  load();
  async function load() {
    try {
      const d = await get("/notifications?per_page=40");
      if (!isCurrent()) return;
      const box = screen.querySelector("#list");
      if (!d.items.length) {
        box.innerHTML = emptyState("You're all caught up", "Payment updates will land here.");
        return;
      }
      box.innerHTML = d.items
        .map((n) => {
          const st = TYPE_STYLE[n.type] || TYPE_STYLE.system;
          return `
          <div class="notif-row ${n.is_read ? "" : "unread"}">
            <span class="notif-row__ico" style="background:${st.bg};color:${st.c}">${st.i}</span>
            <div style="min-width:0">
              <div class="notif-row__t">${esc(n.title)}</div>
              <div class="notif-row__b">${esc(n.body)}</div>
              <div class="notif-row__d num">${shortDate(n.created_at)}</div>
            </div>
          </div>`;
        })
        .join("");
      markVisibleRead(d.items.filter((n) => !n.is_read));
    } catch (err) {
      if (isCurrent()) screen.querySelector("#list").innerHTML = emptyState("Couldn't load", err.message);
    }
  }

  async function markVisibleRead(unreadItems) {
    if (!unreadItems.length) return;
    import("../app.js").then(async (m) => {
      for (const n of unreadItems.slice(0, 20)) {
        try { await post(`/notifications/${n.id}/read`); } catch {}
      }
      await m.refreshBalance();
    });
  }
}
