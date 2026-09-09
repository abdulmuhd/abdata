// Zaply Admin console — vanilla JS SPA on /admin.html
const TOKEN_KEY = "zaply.admin.token";
const API_BASE_KEY = "zaply.admin.apiBase";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const naira = (kobo) => "₦" + Math.round((kobo || 0) / 100).toLocaleString("en-NG");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Point the console at a website's API with /admin.html?api=https://your-site.com
// (persisted for later visits). Empty base = same origin as this page.
const qsApi = new URLSearchParams(location.search).get("api");
if (qsApi !== null) localStorage.setItem(API_BASE_KEY, qsApi.trim().replace(/\/+$/, ""));
const API_BASE = localStorage.getItem(API_BASE_KEY) || "";

// ── api ──────────────────────────────────────────────────────────────────
function token() { return localStorage.getItem(TOKEN_KEY); }

async function api(method, path, body) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw Object.assign(
      new Error(
        `Can't reach the Zaply server${API_BASE ? ` at ${API_BASE}` : ""}. Check your connection and that the backend is running.`
      ),
      { status: 0 }
    );
  }
  const payload = await res.json().catch(() => null);
  if (res.status === 401 && !path.startsWith("/auth/")) { logout(); throw Object.assign(new Error(payload?.message || "Session expired"), { status: 401 }); }
  if (!res.ok) throw Object.assign(new Error(payload?.message || `Request failed (${res.status})`), { status: res.status });
  return payload?.data ?? payload;
}

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .25s"; setTimeout(() => el.remove(), 260); }, 2800);
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  $("#shell").hidden = true;
  $("#login-view").hidden = false;
}

// ── boot / login ─────────────────────────────────────────────────────────
const APP_SESSION_KEY = "zaply.session.v1";

function appSessionToken() {
  try {
    return JSON.parse(localStorage.getItem(APP_SESSION_KEY))?.access_token || null;
  } catch {
    return null;
  }
}

// Validity probe: cheap endpoint that still enforces admin rights.
function tokenWorks() {
  return api("GET", "/admin/webhook");
}

(async () => {
  // Reuse an existing console token, or transparently adopt the main app's session.
  if (!token()) {
    const inherited = appSessionToken();
    if (inherited) localStorage.setItem(TOKEN_KEY, inherited);
  }

  if (token()) {
    try {
      await tokenWorks();
      await boot();
      return;
    } catch (ex) {
      // expired or not an admin — drop it and require sign-in
      localStorage.removeItem(TOKEN_KEY);
      const err = $("#login-err");
      if (ex.status === 403 || /admin/i.test(ex.message || "")) {
        err.textContent = ex.message || "Admin access required.";
        err.hidden = false;
      }
    }
  }
  $("#login-view").hidden = false;
})();

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-btn");
  const err = $("#login-err");
  err.hidden = true;
  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    const d = await api("POST", "/auth/admin-login", {
      email: e.target.email.value.trim(),
      password: e.target.password.value,
    });
    // verify admin rights before entering
    localStorage.setItem(TOKEN_KEY, d.access_token);
    try {
      await tokenWorks();
    } catch (ex) {
      logout();
      throw ex;
    }
    await boot();
  } catch (ex) {
    err.textContent = ex.message || "Sign-in failed.";
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign In";
  }
});

$("#logout-btn").addEventListener("click", logout);

async function boot() {
  $("#login-view").hidden = true;
  $("#shell").hidden = false;

  // Fetch permissions and hide restricted tabs
  try {
    const perms = await api("GET", "/admin/system-users/me/permissions");
    if (!perms.is_superadmin) {
      const allowed = new Set(perms.permissions || []);
      const tabPerms = {
        users: "users.view",
        transactions: "transactions.view",
        plans: "pricing.view",
        cables: "pricing.view",
        webhook: "settings.view",
        "api-manager": "providers.view",
        "system-users": "system_users.view",
        "site-settings": "settings.manage",
        promos: "pricing.view",
        broadcast: "broadcast.send",
      };
      document.querySelectorAll("#side-nav button[data-tab]").forEach((btn) => {
        const tab = btn.dataset.tab;
        const required = tabPerms[tab];
        if (required && !allowed.has(required)) {
          btn.style.display = "none";
        }
      });
    }
  } catch { /* ignore */ }

  switchTab("overview");
  try {
    const me = await api("GET", "/users/me");
    $("#whoami").textContent = me.email || "";
  } catch { /* ignore */ }
}

// ── tabs ─────────────────────────────────────────────────────────────────
const state = { usersPage: 1, txnsPage: 1 };

$("#side-nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (b) switchTab(b.dataset.tab);
});

function switchTab(tab) {
  document.querySelectorAll("#side-nav button").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tab));
  document.querySelectorAll("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== tab));
  const loaders = {
    overview: loadOverview,
    users: () => loadUsers(state.usersPage),
    transactions: () => loadTxns(state.txnsPage),
    plans: async () => { await loadDcCategories(); await loadDisabledCategories(); await loadPlanCategories(); await loadPlans(); },
    cables: loadCablePlans,
    webhook: loadWebhook,
    "api-manager": loadApiProviders,
    "system-users": loadSystemUsers,
    "site-settings": loadSiteSettings,
    "promos": loadPromos,
  };
  loaders[tab]?.().catch((ex) => toast(ex.message, "err"));
}

// ── overview ─────────────────────────────────────────────────────────────
async function loadOverview() {
  const d = await api("GET", "/admin/overview");
  const s = d.transactions.by_status;
  const successful = s.successful || { count: 0, volume_kobo: 0 };
  const failed = s.failed || { count: 0, volume_kobo: 0 };

  $("#ov-updated").textContent = `Updated ${new Date().toLocaleTimeString("en-NG")}`;
  $("#stat-cards").innerHTML = `
    <div class="stat"><span>Today's Profit</span><b class="num">${naira(d.profit?.today_kobo || 0)}</b><em>from successful sales</em></div>
    <div class="stat"><span>Monthly Profit</span><b class="num">${naira(d.profit?.month_kobo || 0)}</b><em>current month</em></div>
    <div class="stat"><span>Total Profit</span><b class="num">${naira(d.profit?.total_kobo || 0)}</b><em>all-time earnings</em></div>
    <div class="stat"><span>Total users</span><b>${d.users.total.toLocaleString()}</b><em>+${d.users.new_7d} in 7 days</em></div>
    <div class="stat"><span>Active / Blocked</span><b>${d.users.active} <em>/ ${d.users.blocked}</em></b><em>account status</em></div>
    <div class="stat"><span>Users Wallet</span><b class="num">${naira(d.wallet.balance_sum_kobo)}</b><em>held across wallets</em></div>
    <div class="stat"><span>Lifetime funding</span><b class="num">${naira(d.wallet.funded_sum_kobo)}</b><em>all-time top-ups</em></div>
    <div class="stat"><span>Successful sales</span><b>${successful.count.toLocaleString()}</b><em class="num">${naira(successful.volume_kobo)} volume</em></div>
    <div class="stat"><span>Failed</span><b>${failed.count.toLocaleString()}</b><em class="num">${naira(failed.volume_kobo)} reversed</em></div>
    <div class="stat"><span>Referrals</span><b>${(d.referrals?.total || 0).toLocaleString()}</b><em>+${d.referrals?.new_7d || 0} in 7 days</em></div>`;

  drawAreaChart($("#chart-area"), d.series_14d);

  const mixMax = Math.max(1, ...Object.values(d.transactions.by_service).map((x) => x.volume_kobo));
  const services = Object.entries(d.transactions.by_service).sort((a, b) => b[1].volume_kobo - a[1].volume_kobo);
  $("#service-mix").innerHTML = services.length
    ? services.map(([svc, x]) => `
      <div class="mix-row">
        <span style="text-transform:capitalize">${esc(svc.replace("_", " "))}</span>
        <span class="bar"><i style="width:${Math.max(3, (x.volume_kobo / mixMax) * 100)}%"></i></span>
        <span class="val num">${naira(x.volume_kobo)}</span>
      </div>`).join("")
    : '<p class="mix-row empty">No successful transactions yet.</p>';

  const stMax = Math.max(1, ...Object.values(s).map((x) => x.count));
  $("#status-mix").innerHTML = Object.keys({ successful: 1, pending: 1, failed: 1 })
    .map((st) => {
      const x = s[st] || { count: 0, volume_kobo: 0 };
      return `
      <div class="mix-row">
        <span><span class="pill ${st}">${st}</span></span>
        <span class="bar"><i style="width:${Math.max(x.count ? 3 : 0, (x.count / stMax) * 100)}%"></i></span>
        <span class="val num">${x.count} · ${naira(x.volume_kobo)}</span>
      </div>`;
    }).join("");

  $("#signup-tbl tbody").innerHTML = d.recent_signups.map((u) => `
    <tr><td class="num">${u.id}</td><td>${esc(u.full_name)}</td><td>${esc(u.email)}</td><td class="num">${new Date(u.created_at).toLocaleDateString("en-NG")}</td></tr>
  `  ).join("");

  // Load provider balances asynchronously
  loadProviderBalances();

  // Load P&L data
  loadProfitLoss();
}

async function loadProviderBalances() {
  try {
    const d = await api("GET", "/admin/api-manager/providers?per_page=100");
    const providers = (d.items || []).filter((p) => p.is_active && p.supports_balance_check);
    if (!providers.length) {
      $("#provider-balances-card").style.display = "none";
      return;
    }
    const box = $("#provider-balances");
    box.innerHTML = providers.map((p) =>
      `<div class="mix-row" data-pid="${p.id}">
        <span style="font-weight:500;">${esc(p.name)}</span>
        <span class="val num muted" data-bal-for="${p.id}">Loading…</span>
      </div>`
    ).join("");
    $("#provider-balances-card").style.display = "";

    // Fetch each balance in parallel
    providers.forEach(async (p) => {
      try {
        const r = await api("GET", `/admin/api-manager/providers/${p.id}/balance`);
        const el = $(`[data-bal-for="${p.id}"]`);
        if (!el) return;
        if (r && r.balance !== null && r.balance !== undefined) {
          el.textContent = naira(r.balance * 100);
          el.classList.remove("muted");
        } else {
          el.textContent = "N/A";
        }
      } catch {
        const el = $(`[data-bal-for="${p.id}"]`);
        if (el) el.textContent = "Error";
      }
    });
  } catch {
    $("#provider-balances-card").style.display = "none";
  }
}

async function loadProfitLoss() {
  try {
    const d = await api("GET", "/admin/profit-loss?days=30");
    $("#pnl-period").textContent = `Last ${d.days} days`;
    const profitColor = d.profit_kobo >= 0 ? "var(--brand)" : "var(--danger)";
    const profitLabel = d.profit_kobo >= 0 ? "Profit" : "Loss";
    $("#pnl-summary").innerHTML = `
      <div class="mix-row">
        <span>Revenue</span>
        <span class="val num">${naira(d.revenue_kobo)}</span>
      </div>
      <div class="mix-row">
        <span>Cost</span>
        <span class="val num">${naira(d.cost_kobo)}</span>
      </div>
      <div class="mix-row">
        <span style="font-weight:600;">${profitLabel}</span>
        <span class="val num" style="color:${profitColor};font-weight:600;">${naira(d.profit_kobo)}</span>
      </div>
      <div class="mix-row">
        <span>Transactions</span>
        <span class="val num">${d.transaction_count}</span>
      </div>`;

    if (d.services && d.services.length) {
      const maxProfit = Math.max(1, ...d.services.map((s) => Math.abs(s.profit_kobo)));
      $("#pnl-by-service").innerHTML = d.services.map((s) => {
        const color = s.profit_kobo >= 0 ? "var(--brand)" : "var(--danger)";
        const barWidth = Math.max(3, (Math.abs(s.profit_kobo) / maxProfit) * 100);
        return `
          <div class="mix-row">
            <span style="text-transform:capitalize">${esc(s.service.replace("_", " "))}</span>
            <span class="bar"><i style="width:${barWidth}%;background:${color};"></i></span>
            <span class="val num" style="color:${color};">${naira(s.profit_kobo)}</span>
          </div>`;
      }).join("");
    } else {
      $("#pnl-by-service").innerHTML = '<p class="mix-row empty">No successful transactions yet.</p>';
    }
  } catch {
    $("#pnl-summary").innerHTML = '<p class="mix-row empty">Unable to load P&L data.</p>';
  }
}

// dependency-free SVG area chart
function drawAreaChart(box, series) {
  const W = 640, H = 190, P = 34; // viewBox dims + padding
  const maxV = Math.max(...series.map((d) => d.volume_kobo), 1);
  const x = (i) => P + (i * (W - P * 2)) / (series.length - 1);
  const y = (v) => H - 26 - (v / maxV) * (H - 56);
  const pts = series.map((d, i) => [x(i), y(d.volume_kobo)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${x(series.length - 1)},${H - 26} L${x(0)},${H - 26} Z`;

  box.innerHTML = `
    <div class="chart-wrap">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="14 day volume chart">
        <defs>
          <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" class="chart-gradient-start" stop-opacity=".28"/>
            <stop offset="100%" class="chart-gradient-end" stop-opacity="0"/>
          </linearGradient>
        </defs>
        ${[0.25, 0.5, 0.75].map((f) => `<line x1="${P}" x2="${W - P}" y1="${(H - 26) * f}" y2="${(H - 26) * f}" stroke="#e7ebef" stroke-dasharray="4 4"/>`).join("")}
        <path d="${area}" fill="url(#ag)"/>
        <path d="${line}" fill="none" class="chart-line" stroke-width="2.4" stroke-linejoin="round"/>
        ${pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="#fff" class="chart-dot" stroke-width="2"><title>${series[i].day}: ${naira(series[i].volume_kobo)} · ${series[i].count} txns</title></circle>`).join("")}
        ${series.map((d, i) => i % 2 ? "" : `<text x="${x(i)}" y="${H - 8}" font-size="9.5" fill="#98a2b3" text-anchor="middle">${d.day.slice(5)}</text>`).join("")}
      </svg>
    </div>`;
}

// ── users ────────────────────────────────────────────────────────────────
$("#user-search").addEventListener("click", () => { state.usersPage = 1; loadUsers(1).catch((e) => toast(e.message, "err")); });
$("#user-q").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#user-search").click(); });
$("#users-prev").addEventListener("click", () => loadUsers(Math.max(1, state.usersPage - 1)).catch((e) => toast(e.message, "err")));
$("#users-next").addEventListener("click", () => loadUsers(state.usersPage + 1).catch((e) => toast(e.message, "err")));
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-export]");
  if (!btn) return;
  e.preventDefault();
  const which = btn.dataset.export;
  const fmt = btn.dataset.fmt;
  const ext = fmt;
  try {
    let url;
    if (which === "users") {
      const q = encodeURIComponent($("#user-q").value.trim());
      url = `/api/v1/admin/users/export?q=${q}&format=${fmt}`;
    } else {
      const params = new URLSearchParams({ format: fmt });
      const q = $("#txn-q").value.trim();
      const s = $("#txn-status").value;
      const svc = $("#txn-service").value;
      if (q) params.set("q", q);
      if (s) params.set("status", s);
      if (svc) params.set("service_type", svc);
      url = `/api/v1/admin/transactions/export?${params}`;
    }
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token()}` } });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `${which}-${new Date().toISOString().slice(0, 10)}.${ext}`;
    a.click();
    URL.revokeObjectURL(blobUrl);
  } catch (ex) { toast(ex.message, "err"); }
});

async function loadUsers(page) {
  const q = encodeURIComponent($("#user-q").value.trim());
  const d = await api("GET", `/admin/users?page=${page}&per_page=12&q=${q}`);
  state.usersPage = page;
  $("#users-page").textContent = `Page ${d.meta.page} of ${d.meta.total_pages} · ${d.meta.total} users`;
  $("#users-prev").disabled = d.meta.page <= 1;
  $("#users-next").disabled = d.meta.page >= d.meta.total_pages;

  $("#users-tbl tbody").innerHTML = d.items.map((u) => `
    <tr data-user="${u.id}">
      <td class="num">${u.id}</td>
      <td>${esc(u.full_name)}</td>
      <td>${esc(u.email)}</td>
      <td class="num">${esc(u.phone)}</td>
      <td class="num">${naira(u.balance_kobo)}</td>
      <td class="num">${u.txn_count}</td>
      <td><span class="pill ${u.is_active ? "active" : "blocked"}">${u.is_active ? "Active" : "Blocked"}</span></td>
      <td style="display:flex;gap:6px;">
        <button class="btn-primary btn-sm" data-view-user="${u.id}">View</button>
        <button class="btn-ghost btn-sm ${u.is_active ? "danger-text" : ""}" data-toggle-user="${u.id}">${u.is_active ? "Block" : "Unblock"}</button>
      </td>
    </tr>`).join("");

  const byId = new Map(d.items.map((u) => [u.id, u]));
  $("#users-tbl tbody").querySelectorAll("[data-view-user]").forEach((b) =>
    b.addEventListener("click", () => {
      const u = byId.get(Number(b.dataset.viewUser));
      if (u) openProfileModal(u);
    })
  );
  $("#users-tbl tbody").querySelectorAll("[data-toggle-user]").forEach((b) =>
    b.addEventListener("click", async () => {
      const u = byId.get(Number(b.dataset.toggleUser));
      if (!u) return;
      b.disabled = true;
      try {
        const r = await api("PATCH", `/admin/users/${u.id}/status`, { is_active: !u.is_active });
        toast(r.message);
        await loadUsers(state.usersPage).catch(() => {});
      } catch (ex) {
        toast(ex.message, "err");
      } finally {
        b.disabled = false;
      }
    })
  );
}

// ── fund a user's wallet ─────────────────────────────────────────────────
let fundTarget = null;

function openFundModal(u) {
  fundTarget = u;
  $("#fund-title").textContent = `Fund ${u.full_name.split(" ")[0]}'s wallet`;
  $("#fund-user").textContent = `${u.full_name} · ${u.email} · balance ${naira(u.balance_kobo)}`;
  $("#fund-amt").value = "";
  $("#fund-note").value = "";
  const err = $("#fund-err");
  err.hidden = true;
  err.textContent = "";
  $("#fund-modal").hidden = false;
  setTimeout(() => $("#fund-amt").focus(), 30);
}

function closeFundModal() {
  $("#fund-modal").hidden = true;
  fundTarget = null;
}

$("#fund-cancel").addEventListener("click", closeFundModal);
$("#fund-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeFundModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#fund-modal").hidden) closeFundModal();
});

$("#fund-go").addEventListener("click", async () => {
  if (!fundTarget) return;
  const amt = Number($("#fund-amt").value);
  const err = $("#fund-err");
  err.hidden = true;
  if (!amt || amt < 50) {
    err.textContent = "Enter an amount of at least ₦50.";
    err.hidden = false;
    return;
  }
  const btn = $("#fund-go");
  btn.disabled = true;
  btn.textContent = "Crediting…";
  try {
    const r = await api("POST", `/admin/users/${fundTarget.id}/fund`, {
      amount_naira: amt,
      note: $("#fund-note").value.trim() || null,
    });
    toast(r.message);
    closeFundModal();
    await loadUsers(state.usersPage).catch(() => {});
  } catch (ex) {
    err.textContent = ex.message || "Funding failed.";
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Credit wallet";
  }
});
$("#fund-amt").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#fund-go").click();
});

// ── user profile modal ──────────────────────────────────────────────────
let profileTarget = null;

function openProfileModal(u) {
  profileTarget = u;
  $("#pm-title").textContent = u.full_name;
  $("#pm-info").innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:14px;">
      <div><span class="muted">ID:</span> ${u.id}</div>
      <div><span class="muted">Status:</span> <span class="pill ${u.is_active ? "active" : "blocked"}">${u.is_active ? "Active" : "Blocked"}</span></div>
      <div><span class="muted">Email:</span> ${esc(u.email)}</div>
      <div><span class="muted">Phone:</span> ${esc(u.phone || "—")}</div>
      <div><span class="muted">Balance:</span> <b class="num">${naira(u.balance_kobo)}</b></div>
      <div><span class="muted">Transactions:</span> ${u.txn_count}</div>
    </div>`;
  const toggleBtn = $("#pm-toggle-status");
  toggleBtn.textContent = u.is_active ? "Block" : "Unblock";
  toggleBtn.style.color = u.is_active ? "var(--danger)" : "var(--brand)";
  $("#profile-modal").hidden = false;
}

function closeProfileModal() {
  $("#profile-modal").hidden = true;
  profileTarget = null;
}

function closeAllSubModals() {
  $("#edit-name-modal").hidden = true;
  $("#admin-pw-modal").hidden = true;
  $("#admin-pin-modal").hidden = true;
  $("#debit-modal").hidden = true;
}

$("#pm-close").addEventListener("click", closeProfileModal);
$("#profile-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeProfileModal();
});

// ── edit name ───────────────────────────────────────────────────────────
$("#pm-edit-name").addEventListener("click", () => {
  if (!profileTarget) return;
  closeAllSubModals();
  $("#en-name").value = profileTarget.full_name;
  const err = $("#en-err");
  err.hidden = true;
  err.textContent = "";
  $("#edit-name-modal").hidden = false;
  setTimeout(() => $("#en-name").focus(), 30);
});

$("#en-cancel").addEventListener("click", () => { $("#edit-name-modal").hidden = true; });
$("#edit-name-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) $("#edit-name-modal").hidden = true;
});

$("#en-save").addEventListener("click", async () => {
  if (!profileTarget) return;
  const name = $("#en-name").value.trim();
  const err = $("#en-err");
  err.hidden = true;
  if (!name || name.length < 2) {
    err.textContent = "Name must be at least 2 characters.";
    err.hidden = false;
    return;
  }
  const btn = $("#en-save");
  btn.disabled = true;
  try {
    const r = await api("PATCH", `/admin/users/${profileTarget.id}`, { full_name: name });
    toast(r.message);
    profileTarget.full_name = name;
    $("#pm-title").textContent = name;
    $("#edit-name-modal").hidden = true;
    await loadUsers(state.usersPage).catch(() => {});
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
});
$("#en-name").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#en-save").click(); });

// ── change password ─────────────────────────────────────────────────────
$("#pm-change-pw").addEventListener("click", () => {
  if (!profileTarget) return;
  closeAllSubModals();
  $("#admin-pw-user").textContent = `${profileTarget.full_name} · ${profileTarget.email}`;
  $("#admin-pw-input").value = "";
  const err = $("#admin-pw-err");
  err.hidden = true;
  err.textContent = "";
  $("#admin-pw-modal").hidden = false;
  setTimeout(() => $("#admin-pw-input").focus(), 30);
});

$("#admin-pw-cancel").addEventListener("click", () => { $("#admin-pw-modal").hidden = true; });
$("#admin-pw-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) $("#admin-pw-modal").hidden = true;
});

$("#admin-pw-save").addEventListener("click", async () => {
  if (!profileTarget) return;
  const pw = $("#admin-pw-input").value;
  const err = $("#admin-pw-err");
  err.hidden = true;
  if (!pw || pw.length < 6) {
    err.textContent = "Password must be at least 6 characters.";
    err.hidden = false;
    return;
  }
  const btn = $("#admin-pw-save");
  btn.disabled = true;
  try {
    const r = await api("POST", `/admin/users/${profileTarget.id}/reset-password`, { new_password: pw });
    toast(r.message);
    $("#admin-pw-modal").hidden = true;
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
});
$("#admin-pw-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#admin-pw-save").click(); });

// ── change PIN ──────────────────────────────────────────────────────────
$("#pm-change-pin").addEventListener("click", () => {
  if (!profileTarget) return;
  closeAllSubModals();
  $("#admin-pin-user").textContent = `${profileTarget.full_name} · ${profileTarget.email}`;
  $("#admin-pin-input").value = "";
  const err = $("#admin-pin-err");
  err.hidden = true;
  err.textContent = "";
  $("#admin-pin-modal").hidden = false;
  setTimeout(() => $("#admin-pin-input").focus(), 30);
});

$("#admin-pin-cancel").addEventListener("click", () => { $("#admin-pin-modal").hidden = true; });
$("#admin-pin-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) $("#admin-pin-modal").hidden = true;
});

$("#admin-pin-save").addEventListener("click", async () => {
  if (!profileTarget) return;
  const pin = $("#admin-pin-input").value;
  const err = $("#admin-pin-err");
  err.hidden = true;
  if (!/^\d{4}$/.test(pin)) {
    err.textContent = "PIN must be exactly 4 digits.";
    err.hidden = false;
    return;
  }
  const btn = $("#admin-pin-save");
  btn.disabled = true;
  try {
    const r = await api("POST", `/admin/users/${profileTarget.id}/reset-pin`, { new_pin: pin });
    toast(r.message);
    $("#admin-pin-modal").hidden = true;
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
});
$("#admin-pin-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#admin-pin-save").click(); });

// ── credit wallet (reuse fund modal) ────────────────────────────────────
$("#pm-credit").addEventListener("click", () => {
  if (!profileTarget) return;
  closeAllSubModals();
  closeProfileModal();
  openFundModal(profileTarget);
});

// ── debit wallet ────────────────────────────────────────────────────────
$("#pm-debit").addEventListener("click", () => {
  if (!profileTarget) return;
  closeAllSubModals();
  $("#debit-user").textContent = `${profileTarget.full_name} · balance ${naira(profileTarget.balance_kobo)}`;
  $("#debit-amt").value = "";
  $("#debit-note").value = "";
  const err = $("#debit-err");
  err.hidden = true;
  err.textContent = "";
  $("#debit-modal").hidden = false;
  setTimeout(() => $("#debit-amt").focus(), 30);
});

// ── toggle user status (block/unblock) ─────────────────────────────────
$("#pm-toggle-status").addEventListener("click", async () => {
  if (!profileTarget) return;
  const btn = $("#pm-toggle-status");
  btn.disabled = true;
  try {
    const nextActive = !profileTarget.is_active;
    const r = await api("PATCH", `/admin/users/${profileTarget.id}/status`, { is_active: nextActive });
    toast(r.message);
    profileTarget.is_active = nextActive;
    openProfileModal(profileTarget);
    await loadUsers(state.usersPage).catch(() => {});
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
  }
});

$("#debit-cancel").addEventListener("click", () => { $("#debit-modal").hidden = true; });
$("#debit-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) $("#debit-modal").hidden = true;
});

$("#debit-go").addEventListener("click", async () => {
  if (!profileTarget) return;
  const amt = Number($("#debit-amt").value);
  const err = $("#debit-err");
  err.hidden = true;
  if (!amt || amt < 50) {
    err.textContent = "Enter an amount of at least ₦50.";
    err.hidden = false;
    return;
  }
  const btn = $("#debit-go");
  btn.disabled = true;
  btn.textContent = "Debiting…";
  try {
    const r = await api("POST", `/admin/users/${profileTarget.id}/debit`, {
      amount_naira: amt,
      note: $("#debit-note").value.trim() || null,
    });
    toast(r.message);
    $("#debit-modal").hidden = true;
    closeProfileModal();
    await loadUsers(state.usersPage).catch(() => {});
  } catch (ex) {
    err.textContent = ex.message || "Debit failed.";
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Debit Wallet";
  }
});
$("#debit-amt").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#debit-go").click(); });

// close sub-modals on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!$("#profile-modal").hidden) closeProfileModal();
    closeAllSubModals();
  }
});

// ── transactions ─────────────────────────────────────────────────────────
$("#txn-search").addEventListener("click", () => { state.txnsPage = 1; loadTxns(1).catch((e) => toast(e.message, "err")); });
$("#txns-prev").addEventListener("click", () => loadTxns(Math.max(1, state.txnsPage - 1)).catch((e) => toast(e.message, "err")));
$("#txns-next").addEventListener("click", () => loadTxns(state.txnsPage + 1).catch((e) => toast(e.message, "err")));

async function loadTxns(page) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: "12",
    q: $("#txn-q").value.trim(),
    status: $("#txn-status").value,
    service_type: $("#txn-service").value,
  });
  const d = await api("GET", `/admin/transactions?${params}`);
  state.txnsPage = page;
  $("#txns-page").textContent = `Page ${d.meta.page} of ${d.meta.total_pages} · ${d.meta.total} records`;
  $("#txns-prev").disabled = d.meta.page <= 1;
  $("#txns-next").disabled = d.meta.page >= d.meta.total_pages;

  $("#txns-tbl tbody").innerHTML = d.items.map((t) => `
    <tr>
      <td class="num">${esc(t.reference.slice(0, 18))}…</td>
      <td>${esc(t.user?.email || "—")}</td>
      <td style="text-transform:capitalize">${esc(t.service_type.replace("_", " "))}</td>
      <td class="num">${esc(t.customer_ref)}</td>
      <td class="num">${naira(t.amount_kobo)}</td>
      <td><span class="pill ${t.status}">${t.status}</span></td>
      <td class="num">${new Date(t.created_at).toLocaleDateString("en-NG", { day: "numeric", month: "short" })}</td>
    </tr>`).join("");
}

// ── data plans ───────────────────────────────────────────────────────────
const NETWORKS = ["mtn", "airtel", "glo", "9mobile"];
const NETWORK_LABELS = { mtn: "MTN", airtel: "Airtel", glo: "Glo", "9mobile": "9mobile" };

let allPlans = [];
let planSearch = "";

let _planSearchTimer;
$("#plan-search").addEventListener("input", () => {
  clearTimeout(_planSearchTimer);
  _planSearchTimer = setTimeout(() => { planSearch = $("#plan-search").value.trim().toLowerCase(); renderPlanTable(); }, 200);
});
$("#plan-net").addEventListener("change", () => {
  $("#plan-cat").value = "";
  loadPlans().catch((e) => toast(e.message, "err"));
});
$("#plan-cat").addEventListener("change", () => renderPlanTable());

// ── disable category ────────────────────────────────────────────────────
let disabledCats = [];

async function loadDisabledCategories() {
  try {
    const rows = await api("GET", "/admin/data-plans/disabled-categories");
    disabledCats = rows || [];
  } catch { disabledCats = []; }
  renderDisabledPills();
  updateDcButton();
}

function renderDisabledPills() {
  const box = $("#dc-list");
  if (!disabledCats.length) { box.innerHTML = '<span class="muted">None disabled.</span>'; return; }
  box.innerHTML = disabledCats.map((r) =>
    `<span class="pill" style="margin:2px;">${NETWORK_LABELS[r.network_code] || r.network_code} — ${esc(r.category)} <button class="btn-ghost btn-sm" data-enable-cat="${esc(r.category)}" data-enable-net="${esc(r.network_code)}" style="margin-left:4px;padding:0 4px;">&times;</button></span>`
  ).join("");
  box.querySelectorAll("[data-enable-cat]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api("POST", "/admin/data-plans/disabled-categories/toggle", {
          network_code: b.dataset.enableNet,
          category: b.dataset.enableCat,
        });
        toast("Category enabled.");
        await loadDisabledCategories();
      } catch (ex) { toast(ex.message, "err"); }
    })
  );
}

function updateDcButton() {
  const net = $("#dc-net").value;
  const cat = $("#dc-cat").value;
  const btn = $("#dc-toggle-btn");
  if (!cat) { btn.textContent = "Disable"; return; }
  const isDisabled = disabledCats.some((d) => d.network_code === net && d.category === cat);
  btn.textContent = isDisabled ? "Enable" : "Disable";
}

async function loadDcCategories() {
  try {
    const cats = await api("GET", "/admin/data-plans/categories");
    const sel = $("#dc-cat");
    const prev = sel.value;
    sel.innerHTML = '<option value="">Select…</option>' +
      (cats || []).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    sel.value = prev;
  } catch { /* ignore */ }
}

$("#dc-net").addEventListener("change", updateDcButton);
$("#dc-cat").addEventListener("change", updateDcButton);

$("#dc-toggle-btn").addEventListener("click", async () => {
  const net = $("#dc-net").value;
  const cat = $("#dc-cat").value;
  if (!cat) return toast("Select a category.", "err");
  try {
    await api("POST", "/admin/data-plans/disabled-categories/toggle", {
      network_code: net,
      category: cat,
    });
    const isDisabled = disabledCats.some((d) => d.network_code === net && d.category === cat);
    toast(isDisabled ? "Category enabled." : "Category disabled.");
    await loadDisabledCategories();
  } catch (ex) { toast(ex.message, "err"); }
});

// ── create / edit data plan modal ───────────────────────────────────────
let _editingPlanCode = null;

function openPlanModal(d = {}) {
  _editingPlanCode = d.plan_code || null;
  $("#plan-m-title").textContent = _editingPlanCode ? "Edit Data Plan" : "Create Data Plan";
  $("#plan-m-edit-code").value = _editingPlanCode || "";
  $("#plan-m-net").value = d.network_code || "mtn";
  $("#plan-m-cat").value = d.category || "";
  $("#plan-m-name").value = d.name || "";
  $("#plan-m-code").value = d.plan_code || "";
  $("#plan-m-code").disabled = !!_editingPlanCode;
  $("#plan-m-vol").value = d.volume_mb || "";
  $("#plan-m-validity").value = d.validity_days || 30;
  $("#plan-m-buy").value = d.buying_price_kobo ? (d.buying_price_kobo / 100).toFixed(0) : "";
  $("#plan-m-sell").value = d.selling_price_kobo ? (d.selling_price_kobo / 100).toFixed(0) : "";
  $("#plan-m-promo").value = d.promo_price_kobo ? (d.promo_price_kobo / 100).toFixed(0) : "";
  $("#plan-m-active").checked = d.is_active !== false;
  const err = $("#plan-m-err");
  err.hidden = true;
  err.textContent = "";
  $("#plan-modal").hidden = false;
  setTimeout(() => $("#plan-m-name").focus(), 30);
}

function closePlanModal() {
  $("#plan-modal").hidden = true;
  _editingPlanCode = null;
}

$("#data-create-btn").addEventListener("click", () => openPlanModal());
$("#plan-m-cancel").addEventListener("click", closePlanModal);
$("#plan-modal").addEventListener("click", (e) => { if (e.target === e.currentTarget) closePlanModal(); });

$("#plan-m-save").addEventListener("click", async () => {
  const err = $("#plan-m-err");
  err.hidden = true;
  const name = $("#plan-m-name").value.trim();
  const code = $("#plan-m-code").value.trim();
  const cat = $("#plan-m-cat").value.trim();
  const vol = parseInt($("#plan-m-vol").value);
  const validity = parseInt($("#plan-m-validity").value);
  const buyNaira = parseFloat($("#plan-m-buy").value) || 0;
  const sellNaira = parseFloat($("#plan-m-sell").value) || 0;
  const promoNaira = parseFloat($("#plan-m-promo").value) || 0;
  const net = $("#plan-m-net").value;
  const active = $("#plan-m-active").checked;

  if (!name) { err.textContent = "Plan name is required."; err.hidden = false; return; }
  if (!code) { err.textContent = "Plan code is required."; err.hidden = false; return; }
  if (!cat) { err.textContent = "Category is required."; err.hidden = false; return; }
  if (!vol || vol <= 0) { err.textContent = "Enter a valid volume in MB."; err.hidden = false; return; }
  if (!validity || validity <= 0) { err.textContent = "Enter a valid validity in days."; err.hidden = false; return; }

  const btn = $("#plan-m-save");
  btn.disabled = true;
  try {
    if (_editingPlanCode) {
      await api("PUT", `/admin/data-plans/${encodeURIComponent(_editingPlanCode)}`, {
        network_code: net,
        name,
        category: cat,
        volume_mb: vol,
        validity_days: validity,
        buying_price_kobo: Math.round(buyNaira * 100) || null,
        selling_price_kobo: Math.round(sellNaira * 100) || null,
        promo_price_kobo: promoNaira ? Math.round(promoNaira * 100) : null,
        is_active: active,
      });
      toast("Plan updated.");
    } else {
      await api("POST", "/admin/data-plans", {
        network_code: net,
        plan_code: code,
        name,
        category: cat,
        volume_mb: vol,
        validity_days: validity,
        buying_price_kobo: Math.round(buyNaira * 100) || null,
        selling_price_kobo: Math.round(sellNaira * 100) || null,
        promo_price_kobo: promoNaira ? Math.round(promoNaira * 100) : null,
        is_active: active,
      });
      toast("Plan created.");
    }
    closePlanModal();
    await loadPlans();
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    btn.disabled = false;
  }
});

async function loadPlans() {
  const net = $("#plan-net").value;
  const params = new URLSearchParams();
  if (net) params.set("network", net);
  const qs = params.toString();
  allPlans = await api("GET", `/admin/data-plans${qs ? `?${qs}` : ""}`);
  renderPlanTable();
}

async function loadPlanCategories() {
  const cats = await api("GET", "/admin/data-plans/categories");
  const catSel = $("#plan-cat");
  const prevCat = catSel.value;
  catSel.innerHTML = `<option value="">All categories</option>` + cats.map((c) => `<option value="${esc(c)}" ${c === prevCat ? "selected" : ""}>${esc(c)}</option>`).join("");
}

function renderPlanTable() {
  const cat = $("#plan-cat").value;
  let rows = cat ? allPlans.filter((p) => p.category === cat) : allPlans;
  if (planSearch) {
    rows = rows.filter((p) =>
      p.name.toLowerCase().includes(planSearch) ||
      p.plan_code.toLowerCase().includes(planSearch) ||
      p.category.toLowerCase().includes(planSearch)
    );
  }

  if (!rows.length) {
    $("#plans-tbl tbody").innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:24px;">No plans found.</td></tr>`;
    return;
  }

  $("#plans-tbl tbody").innerHTML = rows.map((p) => `
    <tr>
      <td style="text-transform:capitalize">${esc(p.network_code)}</td>
      <td>${esc(p.name)}<br /><small style="color:var(--muted);font-size:11px">${esc(p.plan_code)}</small></td>
      <td class="num">${p.validity_days}d</td>
      <td class="num">${naira(p.buying_price_kobo)}</td>
      <td>
        <span class="price-edit">
          <input type="number" min="5" step="1" data-selling-price="${esc(p.plan_code)}" value="${((p.selling_price_kobo || 0) / 100).toFixed(0)}" />
        </span>
      </td>
      <td>
        <span class="price-edit">
          <input type="number" min="0" step="1" data-promo-price="${esc(p.plan_code)}" value="${p.promo_price_kobo ? ((p.promo_price_kobo) / 100).toFixed(0) : ""}" placeholder="None" />
        </span>
      </td>
      <td><span class="pill ${p.is_active ? "active" : "blocked"}">${p.is_active ? "Yes" : "No"}</span></td>
      <td class="row-actions">
        <button class="icon-btn" data-action="save" data-plan-code="${esc(p.plan_code)}" title="Save prices">💾</button>
        <button class="icon-btn" data-action="edit" data-plan-code="${esc(p.plan_code)}" title="Edit plan">✏️</button>
        <button class="icon-btn" data-action="toggle" data-plan-code="${esc(p.plan_code)}" title="${p.is_active ? "Disable" : "Enable"}">${p.is_active ? "⏸️" : "▶️"}</button>
        <button class="icon-btn icon-btn--danger" data-action="delete" data-plan-code="${esc(p.plan_code)}" title="Delete">🗑️</button>
      </td>
    </tr>`).join("");

  // Suppress browser validation tooltips on price inputs
  $("#plans-tbl").querySelectorAll("input[data-selling-price]").forEach((inp) => {
    inp.addEventListener("invalid", (e) => e.preventDefault());
  });
  $("#plans-tbl").querySelectorAll("input[data-promo-price]").forEach((inp) => {
    inp.addEventListener("invalid", (e) => e.preventDefault());
  });

  $("#plans-tbl tbody").querySelectorAll(".icon-btn").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      const code = btn.dataset.planCode;
      const plan = allPlans.find((p) => p.plan_code === code);
      if (!plan) return;
      try {
        if (action === "save") {
          const sellingInput = $(`input[data-selling-price="${code}"]`);
          const sellingNaira = Number(sellingInput.value);
          if (!sellingNaira || sellingNaira < 5) return toast("Enter a valid selling price (min ₦5)", "err");
          const promoInput = $(`input[data-promo-price="${code}"]`);
          const promoNaira = Number(promoInput.value) || 0;
          const r = await api("PATCH", `/admin/data-plans/${encodeURIComponent(code)}`, {
            selling_price_kobo: Math.round(sellingNaira * 100),
            promo_price_kobo: promoNaira ? Math.round(promoNaira * 100) : null,
          });
          toast(r.message);
        } else if (action === "edit") {
          openPlanModal(plan);
        } else if (action === "toggle") {
          const r = await api("PATCH", `/admin/data-plans/${encodeURIComponent(code)}`, { is_active: !plan.is_active });
          toast(r.message);
          await loadPlans();
        } else if (action === "delete") {
          if (!confirm(`Delete plan "${code}"? This cannot be undone.`)) return;
          const r = await api("DELETE", `/admin/data-plans/${encodeURIComponent(code)}`);
          toast(r.message);
          await loadPlans();
        }
      } catch (ex) {
        toast(ex.message, "err");
      }
    })
  );
}

// ── cable plans ──────────────────────────────────────────────────────────
const CABLE_PROVIDER_LABELS = { gotv: "GOtv", dstv: "DStv", startimes: "Startimes" };

$("#cab-provider").addEventListener("change", () => loadCablePlans().catch((e) => toast(e.message, "err")));

async function syncCablePlans(msgEl, btn) {
  btn.disabled = true;
  if (msgEl) msgEl.textContent = "Syncing…";
  try {
    const r = await api("POST", "/admin/provider/sync-plans");
    if (msgEl) msgEl.textContent = r.message;
    toast(r.message);
    return true;
  } catch (ex) {
    if (msgEl) msgEl.textContent = ex.message;
    toast(ex.message, "err");
    return false;
  } finally {
    btn.disabled = false;
  }
}

$("#cab-sync-btn").addEventListener("click", async (e) => {
  const ok = await syncCablePlans($("#cab-sync-msg"), e.target);
  if (ok) await loadCablePlans().catch(() => {});
});

async function loadCablePlans() {
  const provider = $("#cab-provider").value;
  const rows = await api("GET", `/admin/cable-plans${provider ? `?provider=${provider}` : ""}`);
  $("#cables-tbl tbody").innerHTML = rows.length
    ? rows.map((c) => `
      <tr>
        <td>${esc(CABLE_PROVIDER_LABELS[c.provider_code] || c.provider_code)}</td>
        <td>${esc(c.name)}</td>
        <td class="num">${naira(c.buying_price_kobo)}</td>
        <td>
          <span class="price-edit">
            <input type="number" min="50" step="1" data-cab-selling="${esc(c.package_code)}" value="${((c.selling_price_kobo || 0) / 100).toFixed(0)}" />
          </span>
        </td>
        <td><span class="pill ${c.is_active ? "active" : "blocked"}">${c.is_active ? "Yes" : "No"}</span></td>
        <td>
          <button class="btn-primary btn-sm" data-cab-save="${esc(c.package_code)}">Save</button>
          <button class="btn-ghost btn-sm" data-cab-toggle="${esc(c.package_code)}" data-next="${c.is_active ? "false" : "true"}">${c.is_active ? "Disable" : "Enable"}</button>
        </td>
      </tr>`).join("")
    : '<tr><td colspan="6" class="muted">No cable packages yet — press "Sync from Provider" to pull the bouquet list.</td></tr>';

  $("#cables-tbl tbody").querySelectorAll("[data-cab-save]").forEach((b) =>
    b.addEventListener("click", async () => {
      const input = $(`input[data-cab-selling="${b.dataset.cabSave}"]`);
      const nairaVal = Number(input.value);
      if (!nairaVal || nairaVal < 50) return toast("Enter a valid selling price (min ₦50)", "err");
      b.disabled = true;
      try {
        const r = await api("PATCH", `/admin/cable-plans/${encodeURIComponent(b.dataset.cabSave)}`, { selling_price_kobo: Math.round(nairaVal * 100) });
        toast(r.message);
      } catch (ex) {
        toast(ex.message, "err");
      } finally {
        b.disabled = false;
      }
    })
  );

  $("#cables-tbl tbody").querySelectorAll("[data-cab-toggle]").forEach((b) =>
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await api("PATCH", `/admin/cable-plans/${encodeURIComponent(b.dataset.cabToggle)}`, { is_active: b.dataset.next === "true" });
        toast(r.message);
        await loadCablePlans();
      } catch (ex) {
        toast(ex.message, "err");
        b.disabled = false;
      }
    })
  );
}

// ── broadcast ────────────────────────────────────────────────────────────
$("#bc-recipient").addEventListener("change", () => {
  const isSpecific = $("#bc-recipient").value === "specific";
  $("#bc-email-wrap").style.display = isSpecific ? "" : "none";
  $("#bc-email").required = isSpecific;
});

$("#bc-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector(".btn-primary");
  const isSpecific = $("#bc-recipient").value === "specific";
  const email = isSpecific ? $("#bc-email").value.trim() : null;
  if (isSpecific && !email) return toast("Enter a user email", "err");
  btn.disabled = true;
  try {
    const r = await api("POST", "/admin/notifications/broadcast", {
      title: $("#bc-title").value.trim(),
      body: $("#bc-body").value.trim(),
      email,
    });
    toast(r.message);
    e.target.reset();
    $("#bc-email-wrap").style.display = "none";
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
  }
});

// ── webhook ──────────────────────────────────────────────────────────────
$("#wh-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const r = await api("PUT", "/admin/webhook", { url: $("#wh-url").value.trim() });
    toast(r.message);
  } catch (ex) {
    toast(ex.message, "err");
  }
});

$("#wh-test").addEventListener("click", async () => {
  const btn = $("#wh-test");
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const r = await api("POST", "/admin/webhook/test");
    toast(r.message, r.success ? "ok" : "err");
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send test event";
  }
});

async function loadWebhook() {
  const d = await api("GET", "/admin/webhook");
  $("#wh-url").value = d.url || "";
}

// ── API Manager ─────────────────────────────────────────────────────────
const amState = { logsPage: 1, providers: [], editingProvider: null };

$("#am-add-provider")?.addEventListener("click", () => {
  amState.editingProvider = null;
  $("#am-provider-id").value = "";
  $("#am-p-name").value = "";
  $("#am-p-code").value = "";
  $("#am-p-code").disabled = false;
  $("#am-p-url").value = "";
  $("#am-p-desc").value = "";
  $("#am-p-balance").checked = false;
  $("#am-p-token").value = "";
  $("#am-p-token").placeholder = "Just the token, no prefix";
  $$("#am-service-urls input[data-svc-url]").forEach((inp) => (inp.value = ""));
  const balInp = $('input[data-svc-url="check_balance"]');
  if (balInp) balInp.value = "";
  $$('select[data-svc-method]').forEach((sel) => { if (sel.dataset.svcMethod !== "check_balance") sel.selectedIndex = 0; });
  $("#am-form-title").textContent = "Add API Provider";
  $("#am-providers-view").style.display = "none";
  $("#am-provider-detail-view").style.display = "none";
  $("#am-provider-form-view").style.display = "";
});

$("#am-cancel-btn")?.addEventListener("click", () => {
  $("#am-provider-form-view").style.display = "none";
  $("#am-providers-view").style.display = "";
});

// Map service type → operation name for endpoints
const SVC_OP_MAP = {
  check_balance: "check_balance",
  airtime: "buy_airtime",
  data: "buy_data",
  cable: "pay_cable",
  electricity: "pay_electricity",
  epin: "buy_epin",
  bulk_sms: "send_bulk_sms",
  exam_pins: "buy_exam_pin",
  education: "pay_school_fees",
};
const OP_SVC_MAP = Object.fromEntries(Object.entries(SVC_OP_MAP).map(([k, v]) => [v, k]));

$("#am-provider-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#am-save-btn");
  btn.disabled = true;
  try {
    const providerId = $("#am-provider-id").value;
    const isEdit = !!providerId;
    const baseUrl = $("#am-p-url").value.trim();
    const newToken = $("#am-p-token").value.trim();

    // Build services + endpoints from URL inputs
    const services = [];
    const endpoints = [];
    const urlInputs = $$('input[data-svc-url]');
    urlInputs.forEach((inp) => {
      const svc = inp.dataset.svcUrl;
      const urlPath = inp.value.trim();
      if (!urlPath) return;
      const methodSel = $(`select[data-svc-method="${svc}"]`);
      const method = methodSel ? methodSel.value : (svc === "check_balance" ? "GET" : "POST");
      if (svc === "check_balance") {
        endpoints.push({ operation: "check_balance", path: urlPath, method });
      } else {
        services.push({ service_type: svc, is_enabled: true });
        endpoints.push({ operation: SVC_OP_MAP[svc] || svc, path: urlPath, method });
      }
    });

    // 1. Create or update provider
    let pid = providerId;
    if (isEdit) {
      await api("PUT", `/admin/api-manager/providers/${providerId}`, {
        name: $("#am-p-name").value.trim(),
        base_url: baseUrl,
        description: $("#am-p-desc").value.trim() || null,
        supports_balance_check: $("#am-p-balance").checked,
      });
    } else {
      const r = await api("POST", "/admin/api-manager/providers", {
        name: $("#am-p-name").value.trim(),
        code: $("#am-p-code").value.trim(),
        base_url: baseUrl,
        description: $("#am-p-desc").value.trim() || null,
        supports_balance_check: $("#am-p-balance").checked,
      });
      pid = r.id;
    }
    if (!pid) throw new Error("Failed to get provider ID");

    // 2. Save services
    await api("PUT", `/admin/api-manager/providers/${pid}/services`, services);

    // 3. Save bearer token (only if user entered something new)
    if (newToken && newToken !== "") {
      // On edit: delete old token credential first
      if (isEdit) {
        for (const c of amState.editingProvider?.credentials || []) {
          if (c.credential_key === "bearer_token") {
            await api("DELETE", `/admin/api-manager/credentials/${c.id}`);
          }
        }
      }
      await api("POST", `/admin/api-manager/providers/${pid}/credentials`, {
        credential_key: "bearer_token",
        credential_value: newToken,
        is_sensitive: true,
      });
    }

    // 4. Save endpoints: delete old, create new
    if (isEdit) {
      for (const e of amState.editingProvider?.endpoints || []) {
        await api("DELETE", `/admin/api-manager/endpoints/${e.id}`);
      }
    }
    for (const ep of endpoints) {
      await api("POST", `/admin/api-manager/providers/${pid}/endpoints`, ep);
    }

    toast(isEdit ? "Provider updated." : "Provider created.");
    $("#am-provider-form-view").style.display = "none";
    $("#am-providers-view").style.display = "";
    await loadApiProviders();
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
  }
});

async function loadApiProviders() {
  const d = await api("GET", "/admin/api-manager/providers?per_page=100");
  amState.providers = d.items || [];
  const tbody = $("#am-providers-tbl tbody");
  tbody.innerHTML = amState.providers.length
    ? amState.providers.map((p) => `
      <tr class="is-clickable" data-am-provider="${p.id}">
        <td><strong>${esc(p.name)}</strong></td>
        <td class="num muted" data-bal-for="p-${p.id}">${p.supports_balance_check ? "Loading…" : "—"}</td>
        <td><span class="pill ${p.is_active ? "active" : "blocked"}">${p.is_active ? "Active" : "Inactive"}</span></td>
        <td>${(p.services || []).map((s) => `<span class="pill" style="font-size:10px;margin:1px;">${esc(s)}</span>`).join(" ")}</td>
        <td><button class="btn-ghost btn-sm" data-am-view="${p.id}">View</button>
            <button class="btn-ghost btn-sm" data-am-toggle="${p.id}" data-next="${p.is_active ? "false" : "true"}">${p.is_active ? "Deactivate" : "Activate"}</button></td>
      </tr>`).join("")
    : '<tr><td colspan="5" class="muted">No providers configured yet. Use quick-add below or click "+ Add Provider".</td></tr>';

  // Fetch balances for providers that support it
  amState.providers.filter((p) => p.is_active && p.supports_balance_check).forEach(async (p) => {
    try {
      const r = await api("GET", `/admin/api-manager/providers/${p.id}/balance`);
      const el = $(`[data-bal-for="p-${p.id}"]`);
      if (!el) return;
      if (r && r.balance !== null && r.balance !== undefined) {
        el.textContent = naira(r.balance * 100);
        el.classList.remove("muted");
      } else {
        el.textContent = "N/A";
      }
    } catch {
      const el = $(`[data-bal-for="p-${p.id}"]`);
      if (el) el.textContent = "Error";
    }
  });

  tbody.querySelectorAll("[data-am-view]").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      viewApiProvider(Number(b.dataset.amView));
    })
  );
  tbody.querySelectorAll("[data-am-toggle]").forEach((b) =>
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      b.disabled = true;
      try {
        await api("PUT", `/admin/api-manager/providers/${b.dataset.amToggle}`, {
          is_active: b.dataset.next === "true",
        });
        toast("Provider updated.");
        await loadApiProviders();
      } catch (ex) {
        toast(ex.message, "err");
        b.disabled = false;
      }
    })
  );
  tbody.querySelectorAll("tr[data-am-provider]").forEach((tr) =>
    tr.addEventListener("click", () => viewApiProvider(Number(tr.dataset.amProvider)))
  );

  // Load routing form
  await loadRoutingForm();
  // Load logs
  await loadApiLogs();
}

async function viewApiProvider(id) {
  try {
    const d = await api("GET", `/admin/api-manager/providers/${id}`);
    $("#am-providers-view").style.display = "none";
    $("#am-provider-form-view").style.display = "none";
    $("#am-provider-detail-view").style.display = "";
    $("#am-detail-name").textContent = d.name;
    $("#am-detail-test-result").style.display = "none";

    $("#am-detail-info").innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div><span class="muted">Code:</span> ${esc(d.code)}</div>
        <div><span class="muted">Status:</span> <span class="pill ${d.is_active ? "active" : "blocked"}">${d.is_active ? "Active" : "Inactive"}</span></div>
        <div><span class="muted">Base URL:</span> ${esc(d.base_url)}</div>
        <div><span class="muted">Balance Check:</span> ${d.supports_balance_check ? "Yes" : "No"}</div>
        ${d.description ? `<div style="grid-column:1/-1;"><span class="muted">Description:</span> ${esc(d.description)}</div>` : ""}
      </div>`;

    const tokenCred = (d.credentials || []).find((c) => c.credential_key === "bearer_token");
    $("#am-detail-credentials").innerHTML = `
      <h4>Bearer Token</h4>
      ${tokenCred
        ? `<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;"><span class="pill active" style="font-size:11px;">bearer_token</span><span class="muted">${esc(tokenCred.credential_value_masked)}</span></div>`
        : '<p class="muted">No token configured.</p>'}`;

    const svcLabels = { check_balance: "Balance Check", airtime: "Airtime", data: "Data", cable: "Cable TV", electricity: "Electricity", epin: "ePIN", bulk_sms: "Bulk SMS", exam_pins: "Exam PINs", education: "Education" };
    const opToSvc = {};
    Object.entries(SVC_OP_MAP).forEach(([svc, op]) => { opToSvc[op] = svc; });
    const svcEndpoints = (d.endpoints || []).map((e) => ({ svc: opToSvc[e.operation] || e.operation, ...e })).sort((a, b) => a.svc.localeCompare(b.svc));
    $("#am-detail-endpoints").innerHTML = `
      <h4>Service URLs</h4>
      ${svcEndpoints.length
        ? svcEndpoints.map((e) => `<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;"><span class="pill" style="font-size:10px;background:#e9f0fe;color:#175cd3;">${esc(svcLabels[e.svc] || e.svc)}</span><span class="muted">${esc(e.path)}</span></div>`).join("")
        : '<p class="muted">No service URLs configured.</p>'}`;

    // Wire up detail buttons
    $("#am-detail-edit").onclick = () => editApiProvider(d);
    $("#am-detail-test").onclick = () => testApiProvider(d.id);
    $("#am-detail-balance").onclick = () => checkProviderBalance(d.id);
    $("#am-detail-delete").onclick = () => deleteApiProvider(d.id, d.name);
    $("#am-detail-back").onclick = () => {
      $("#am-provider-detail-view").style.display = "none";
      $("#am-providers-view").style.display = "";
    };
  } catch (ex) {
    toast(ex.message, "err");
  }
}

function editApiProvider(d) {
  amState.editingProvider = d;
  $("#am-provider-id").value = d.id;
  $("#am-p-name").value = d.name;
  $("#am-p-code").value = d.code;
  $("#am-p-code").disabled = true;
  $("#am-p-url").value = d.base_url;
  $("#am-p-desc").value = d.description || "";
  $("#am-p-balance").checked = d.supports_balance_check;

  // Token: show placeholder, don't pre-fill masked value
  const hasToken = (d.credentials || []).some((c) => c.credential_key === "bearer_token");
  $("#am-p-token").value = "";
  $("#am-p-token").placeholder = hasToken ? "Just the token, no prefix (leave empty to keep current)" : "Just the token, no prefix";

  // Pre-fill service URLs from existing endpoints
  const pathByOp = {};
  const methodByOp = {};
  (d.endpoints || []).forEach((e) => { pathByOp[e.operation] = e.path; methodByOp[e.operation] = e.method; });
  // Balance check
  const balInp = $('input[data-svc-url="check_balance"]');
  const balMet = $('select[data-svc-method="check_balance"]');
  if (balInp) balInp.value = pathByOp["check_balance"] || "";
  if (balMet) balMet.value = methodByOp["check_balance"] || "GET";
  // Service URLs
  $$("#am-service-urls input[data-svc-url]").forEach((inp) => {
    const op = SVC_OP_MAP[inp.dataset.svcUrl];
    inp.value = op ? (pathByOp[op] || "") : "";
    const met = $(`select[data-svc-method="${inp.dataset.svcUrl}"]`);
    if (met && methodByOp[op]) met.value = methodByOp[op];
  });

  $("#am-form-title").textContent = "Edit API Provider";
  $("#am-provider-detail-view").style.display = "none";
  $("#am-provider-form-view").style.display = "";
}

async function testApiProvider(id) {
  const btn = $("#am-detail-test");
  btn.disabled = true;
  btn.textContent = "Testing…";
  try {
    const r = await api("POST", "/admin/api-manager/providers/test", { provider_id: id });
    const box = $("#am-detail-test-result");
    box.style.display = "";
    let ok = false;
    let msg = "Unknown result.";
    if (r && r.http_status !== undefined) {
      ok = r.http_status >= 200 && r.http_status < 400;
      msg = `Connection ${ok ? "successful" : "failed"}. HTTP ${r.http_status} (${r.duration_ms}ms).`;
    } else if (r && r.message) {
      msg = r.message;
    } else if (r && r.success === false) {
      msg = r.message || "Connection failed.";
    } else {
      msg = JSON.stringify(r);
    }
    box.innerHTML = `<div class="card" style="border-left:4px solid ${ok ? "var(--brand)" : "var(--danger)"};">
      <p style="color:${ok ? "var(--brand)" : "var(--danger)"}; font-weight:600;">${ok ? "✓" : "✕"} ${esc(msg)}</p>
    </div>`;
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Connection";
  }
}

async function checkProviderBalance(id) {
  try {
    const r = await api("GET", `/admin/api-manager/providers/${id}/balance`);
    if (r && r.balance !== null && r.balance !== undefined) {
      toast(`Balance: ${naira(r.balance * 100)}`);
    } else if (r === null) {
      toast("Balance checking not configured for this provider.");
    } else {
      toast("Balance not available.");
    }
  } catch (ex) {
    toast(ex.message, "err");
  }
}

async function deleteApiProvider(id, name) {
  if (!confirm(`Delete provider "${name}"? This cannot be undone.`)) return;
  try {
    await api("DELETE", `/admin/api-manager/providers/${id}`);
    toast("Provider deleted.");
    $("#am-provider-detail-view").style.display = "none";
    $("#am-providers-view").style.display = "";
    await loadApiProviders();
  } catch (ex) {
    toast(ex.message, "err");
  }
}

// ── Service Routing ─────────────────────────────────────────────────────
async function loadRoutingForm() {
  try {
    const d = await api("GET", "/admin/api-manager/routing");
    const box = $("#am-routing-form");
    const serviceTypes = ["airtime", "data", "cable", "electricity", "epin", "bulk_sms", "exam_pins", "education"];
    const providers = amState.providers.filter((p) => p.is_active);

    box.innerHTML = serviceTypes.map((svc) => {
      const entries = d[svc] || [];
      const primary = entries.find((e) => e.priority === 1);
      const backup = entries.find((e) => e.priority === 2);
      return `
        <div style="display:grid;grid-template-columns:120px 1fr 1fr;gap:8px;align-items:center;margin-bottom:8px;">
          <span style="font-weight:600;text-transform:capitalize;">${esc(svc.replace("_", " "))}</span>
          <select data-routing-svc="${svc}" data-routing-priority="1" class="routing-select">
            <option value="">— None —</option>
            ${providers.map((p) => `<option value="${p.id}" ${primary && primary.provider_id === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
          </select>
          <select data-routing-svc="${svc}" data-routing-priority="2" class="routing-select" style="opacity:.8;">
            <option value="">— Backup —</option>
            ${providers.map((p) => `<option value="${p.id}" ${backup && backup.provider_id === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
          </select>
        </div>`;
    }).join("");
  } catch (ex) {
    toast(ex.message, "err");
  }
}

$("#am-save-routing")?.addEventListener("click", async () => {
  const btn = $("#am-save-routing");
  btn.disabled = true;
  try {
    const selects = document.querySelectorAll(".routing-select");
    for (const sel of selects) {
      const svc = sel.dataset.routingSvc;
      const priority = Number(sel.dataset.routingPriority);
      if (sel.value) {
        await api("POST", "/admin/api-manager/routing", {
          service_type: svc,
          provider_id: Number(sel.value),
          priority: priority,
        });
      }
    }
    toast("Routing saved.");
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
  }
});

// ── API Logs ────────────────────────────────────────────────────────────
$("#am-refresh-logs")?.addEventListener("click", () => loadApiLogs().catch((e) => toast(e.message, "err")));
$("#am-log-filter")?.addEventListener("change", () => { amState.logsPage = 1; loadApiLogs().catch((e) => toast(e.message, "err")); });
$("#am-logs-prev")?.addEventListener("click", () => loadApiLogs(Math.max(1, amState.logsPage - 1)).catch((e) => toast(e.message, "err")));
$("#am-logs-next")?.addEventListener("click", () => loadApiLogs(amState.logsPage + 1).catch((e) => toast(e.message, "err")));

async function loadApiLogs(page) {
  page = page || 1;
  const filter = $("#am-log-filter")?.value || "";
  const params = new URLSearchParams({ page: String(page), per_page: "10" });
  if (filter) params.set("success", filter);
  const d = await api("GET", `/admin/api-manager/logs?${params}`);
  amState.logsPage = page;
  $("#am-logs-page").textContent = `Page ${d.meta.page} of ${d.meta.total_pages}`;
  $("#am-logs-prev").disabled = d.meta.page <= 1;
  $("#am-logs-next").disabled = d.meta.page >= d.meta.total_pages;
  $("#am-logs-tbl tbody").innerHTML = (d.items || []).map((l) => `
    <tr>
      <td>${esc(l.provider_name)}</td>
      <td>${esc(l.operation)}</td>
      <td><span class="pill ${l.success ? "active" : "failed"}">${l.success ? "OK" : "Failed"}</span></td>
      <td class="num">${l.http_status_code || "—"}</td>
      <td class="num">${l.duration_ms}ms</td>
      <td class="num">${new Date(l.created_at).toLocaleDateString("en-NG", { day: "numeric", month: "short" })}</td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">No logs yet.</td></tr>';
}

// ── System Users ────────────────────────────────────────────────────────
const suState = { page: 1, actPage: 1, editingUser: null, selectedUserId: null, searchTimer: null };

$("#su-add-user")?.addEventListener("click", () => {
  suState.editingUser = null;
  suState.selectedUserId = null;
  $("#su-user-id").value = "";
  $("#su-selected-user-id").value = "";
  $("#su-user-search").value = "";
  $("#su-user-results").style.display = "none";
  $("#su-user-results").innerHTML = "";
  $("#su-selected-user").style.display = "none";
  $("#su-role").value = "moderator";
  $("#su-save-btn").disabled = true;
  $("#su-form-title").textContent = "Promote User to System User";
  $("#su-list-view").style.display = "none";
  $("#su-form-view").style.display = "";
});

$("#su-cancel-btn")?.addEventListener("click", () => {
  $("#su-form-view").style.display = "none";
  $("#su-list-view").style.display = "";
});

// User search with debounce
$("#su-user-search")?.addEventListener("input", () => {
  clearTimeout(suState.searchTimer);
  const q = $("#su-user-search").value.trim();
  if (q.length < 2) {
    $("#su-user-results").style.display = "none";
    return;
  }
  suState.searchTimer = setTimeout(async () => {
    try {
      const users = await api("GET", `/admin/system-users/search-users?q=${encodeURIComponent(q)}`);
      const box = $("#su-user-results");
      if (!users.length) {
        box.innerHTML = '<div style="padding:10px;color:var(--muted)">No users found</div>';
      } else {
        box.innerHTML = users.map((u) => `
          <div class="su-user-option" data-uid="${u.id}" data-name="${esc(u.full_name)}" data-email="${esc(u.email)}" style="padding:8px 10px;cursor:pointer;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;">
            <div><b>${esc(u.full_name)}</b><br/><span style="font-size:12px;color:var(--muted)">${esc(u.email)}</span></div>
            <span style="font-size:11px;color:var(--brand)">Select</span>
          </div>`).join("");
        box.querySelectorAll(".su-user-option").forEach((opt) => {
          opt.addEventListener("click", () => {
            suState.selectedUserId = Number(opt.dataset.uid);
            $("#su-selected-user-id").value = opt.dataset.uid;
            $("#su-user-search").value = "";
            $("#su-user-results").style.display = "none";
            $("#su-selected-user").style.display = "";
            $("#su-selected-user").innerHTML = `<b>${opt.dataset.name}</b><br/><span style="font-size:12px;color:var(--muted)">${opt.dataset.email}</span>`;
            $("#su-save-btn").disabled = false;
          });
        });
      }
      box.style.display = "";
    } catch {
      $("#su-user-results").style.display = "none";
    }
  }, 300);
});

// Clear selected user
$("#su-selected-user")?.addEventListener("click", () => {
  suState.selectedUserId = null;
  $("#su-selected-user-id").value = "";
  $("#su-selected-user").style.display = "none";
  $("#su-save-btn").disabled = true;
});

$("#su-user-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#su-save-btn");
  btn.disabled = true;
  try {
    const systemUserId = $("#su-user-id").value;
    if (systemUserId) {
      await api("PUT", `/admin/system-users/${systemUserId}`, {
        role: $("#su-role").value,
      });
      toast("System user updated.");
    } else {
      const userId = $("#su-selected-user-id").value;
      if (!userId) return toast("Select a user first", "err");
      const r = await api("POST", "/admin/system-users", {
        user_id: Number(userId),
        role: $("#su-role").value,
      });
      toast(r.message);
    }
    $("#su-form-view").style.display = "none";
    $("#su-list-view").style.display = "";
    await loadSystemUsers();
  } catch (ex) {
    toast(ex.message, "err");
  } finally {
    btn.disabled = false;
  }
});

$("#su-search-btn")?.addEventListener("click", () => { suState.page = 1; loadSystemUsers().catch((e) => toast(e.message, "err")); });
$("#su-search")?.addEventListener("keydown", (e) => { if (e.key === "Enter") $("#su-search-btn").click(); });
$("#su-prev")?.addEventListener("click", () => loadSystemUsers(Math.max(1, suState.page - 1)).catch((e) => toast(e.message, "err")));
$("#su-next")?.addEventListener("click", () => loadSystemUsers(suState.page + 1).catch((e) => toast(e.message, "err")));

async function loadSystemUsers(page) {
  page = page || 1;
  const q = encodeURIComponent($("#su-search")?.value?.trim() || "");
  const status = $("#su-status-filter")?.value || "";
  const params = new URLSearchParams({ page: String(page), per_page: "12", q });
  if (status) params.set("status", status);
  const d = await api("GET", `/admin/system-users?${params}`);
  suState.page = page;
  $("#su-page").textContent = `Page ${d.meta.page} of ${d.meta.total_pages} · ${d.meta.total} users`;
  $("#su-prev").disabled = d.meta.page <= 1;
  $("#su-next").disabled = d.meta.page >= d.meta.total_pages;

  $("#su-users-tbl tbody").innerHTML = (d.items || []).map((u) => `
    <tr>
      <td>${esc(u.full_name)}</td>
      <td>${esc(u.email)}</td>
      <td class="muted">${esc(u.username)}</td>
      <td><span class="pill" style="font-size:11px;">${esc(u.role_name)}</span></td>
      <td><span class="pill ${u.status === "active" ? "active" : "blocked"}">${u.status}</span></td>
      <td class="num">${u.last_login_at ? new Date(u.last_login_at).toLocaleDateString("en-NG", { day: "numeric", month: "short" }) : "—"}</td>
      <td>
        <select class="su-action-select" data-su-id="${u.id}" data-su-status="${u.status}">
          <option value="">Action…</option>
          <option value="edit">Edit</option>
          <option value="toggle">${u.status === "active" ? "Suspend" : "Activate"}</option>
          <option value="delete">Delete</option>
        </select>
      </td>
    </tr>`).join("") || '<tr><td colspan="7" class="muted">No system users found.</td></tr>';

  // Wire up dropdown
  const byId = new Map((d.items || []).map((u) => [u.id, u]));
  $("#su-users-tbl tbody").querySelectorAll(".su-action-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const action = sel.value;
      const id = Number(sel.dataset.suId);
      const status = sel.dataset.suStatus;
      sel.value = "";
      if (!action) return;
      const u = byId.get(id);
      if (!u) return;
      try {
        if (action === "edit") {
          editSystemUser(u);
        } else if (action === "toggle") {
          const next = status === "active" ? "suspended" : "active";
          await api("PUT", `/admin/system-users/${id}`, { status: next });
          toast("User status updated.");
          await loadSystemUsers(suState.page);
        } else if (action === "delete") {
          if (!confirm("Delete this system user?")) return;
          await api("DELETE", `/admin/system-users/${id}`);
          toast("User deleted.");
          await loadSystemUsers(suState.page);
        }
      } catch (ex) {
        toast(ex.message, "err");
      }
    });
  });

  // Load activity log
  await loadActivityLogs();
}

function editSystemUser(u) {
  suState.editingUser = u;
  $("#su-user-id").value = u.id;
  $("#su-selected-user-id").value = "";
  $("#su-user-search").value = "";
  $("#su-user-results").style.display = "none";
  $("#su-selected-user").style.display = "";
  $("#su-selected-user").innerHTML = `<b>${esc(u.full_name)}</b><br/><span style="font-size:12px;color:var(--muted)">${esc(u.email)}</span>`;
  $("#su-role").value = u.role_name === "Super Admin" ? "super_admin" : u.role_name === "Admin" ? "admin" : "moderator";
  $("#su-form-title").textContent = "Edit System User";
  $("#su-save-btn").disabled = false;
  $("#su-list-view").style.display = "none";
  $("#su-form-view").style.display = "";
}

// ── Activity Log ────────────────────────────────────────────────────────
$("#su-act-prev")?.addEventListener("click", () => loadActivityLogs(Math.max(1, suState.actPage - 1)).catch((e) => toast(e.message, "err")));
$("#su-act-next")?.addEventListener("click", () => loadActivityLogs(suState.actPage + 1).catch((e) => toast(e.message, "err")));

async function loadActivityLogs(page) {
  page = page || 1;
  const d = await api("GET", `/admin/system-users/activity/logs?page=${page}&per_page=8`);
  suState.actPage = page;
  $("#su-act-page").textContent = `Page ${d.meta.page} of ${d.meta.total_pages}`;
  $("#su-act-prev").disabled = d.meta.page <= 1;
  $("#su-act-next").disabled = d.meta.page >= d.meta.total_pages;
  $("#su-activity-tbl tbody").innerHTML = (d.items || []).map((l) => `
    <tr>
      <td>${esc(l.user_name)}</td>
      <td><span class="pill" style="font-size:10px;">${esc(l.action)}</span></td>
      <td class="muted">${esc(l.details || l.previous_value || "—")}</td>
      <td class="num">${new Date(l.created_at).toLocaleDateString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
    </tr>`).join("") || '<tr><td colspan="4" class="muted">No activity yet.</td></tr>';
}


// ── site settings ───────────────────────────────────────────────────────

let selectedTheme = "light";

async function loadSiteSettings() {
  try {
    const d = await api("GET", "/admin/site-settings");
    $("#ss-name").value = d.site_name || "Zaply";
    $("#ss-support-phone").value = d.support_phone || "";
    $("#ss-support-email").value = d.support_email || "";
    selectedTheme = d.theme || "light";
    const themes = d.themes || {};

    const sel = $("#ss-theme-select");
    if (sel) {
      sel.innerHTML = Object.entries(themes).map(([key, t]) =>
        `<option value="${esc(key)}" ${key === selectedTheme ? "selected" : ""}>${esc(t.label)}</option>`
      ).join("");
      const updatePreview = () => {
        const t = themes[sel.value];
        const pv = $("#ss-theme-preview");
        if (t && pv) pv.style.background = `linear-gradient(135deg, ${t.brand}, ${t.brand700})`;
      };
      sel.addEventListener("change", () => { selectedTheme = sel.value; updatePreview(); });
      updatePreview();
    }
  } catch (ex) {
    toast("Failed to load site settings: " + ex.message, "err");
  }

  $("#ss-save-name").onclick = async () => {
    const name = $("#ss-name").value.trim();
    if (!name) { toast("Site name cannot be empty", "err"); return; }
    try {
      await api("PUT", "/admin/site-settings", { site_name: name });
      toast("Site name updated", "ok");
    } catch (ex) { toast(ex.message, "err"); }
  };

  $("#ss-save-theme").onclick = async () => {
    try {
      await api("PUT", "/admin/site-settings", { theme: selectedTheme });
      toast("Theme updated", "ok");
    } catch (ex) { toast(ex.message, "err"); }
  };

  $("#ss-save-contact").onclick = async () => {
    const phone = $("#ss-support-phone").value.trim();
    const email = $("#ss-support-email").value.trim();
    try {
      await api("PUT", "/admin/site-settings", { support_phone: phone, support_email: email });
      toast("Support contact updated", "ok");
    } catch (ex) { toast(ex.message, "err"); }
  };
}

// ── promo codes ────────────────────────────────────────────────────────

let _editingPromoId = null;

async function loadPromos() {
  try {
    const rows = await api("GET", "/admin/promos");
    renderPromoTable(rows);
  } catch (ex) { toast(ex.message, "err"); }
}

function renderPromoTable(rows) {
  if (!rows.length) {
    $("#promo-table").innerHTML = '<p class="muted">No promo codes yet.</p>';
    return;
  }
  let h = '<table class="tbl"><thead><tr><th>Code</th><th>Discount</th><th>Uses</th><th>Status</th><th></th></tr></thead><tbody>';
  for (const p of rows) {
    const disc = p.discount_percent ? `${p.discount_percent}%` : p.discount_kobo ? `₦${(p.discount_kobo / 100).toLocaleString()}` : "—";
    const uses = p.max_uses ? `${p.used_count}/${p.max_uses}` : `${p.used_count} / ∞`;
    const status = p.is_active ? '<span class="badge badge--ok">Active</span>' : '<span class="badge">Disabled</span>';
    h += `<tr>
      <td><code>${esc(p.code)}</code></td>
      <td>${disc}</td>
      <td>${uses}</td>
      <td>${status}</td>
      <td>
        <button class="btn-ghost btn-sm promo-edit" data-id="${p.id}" data-code="${esc(p.code)}" data-pct="${p.discount_percent}" data-amt="${p.discount_kobo}" data-max="${p.max_uses}" data-min="${p.min_amount_kobo}" data-active="${p.is_active}" data-exp="${p.expires_at || ''}">Edit</button>
        <button class="btn-ghost btn-sm danger-text promo-del" data-id="${p.id}">Del</button>
      </td>
    </tr>`;
  }
  h += '</tbody></table>';
  $("#promo-table").innerHTML = h;

  $$(".promo-edit", $("#promo-table")).forEach(b => b.onclick = () => openPromoModal(b.dataset));
  $$(".promo-del", $("#promo-table")).forEach(b => b.onclick = async () => {
    if (!confirm("Delete promo " + b.dataset.id + "?")) return;
    try { await api("DELETE", `/admin/promos/${b.dataset.id}`); loadPromos(); toast("Deleted", "ok"); } catch (ex) { toast(ex.message, "err"); }
  });
}

function openPromoModal(d = {}) {
  _editingPromoId = d.id || null;
  $("#promo-m-title").textContent = _editingPromoId ? "Edit promo" : "Create promo";
  $("#promo-m-code").value = d.code || "";
  $("#promo-m-code").disabled = !!_editingPromoId;
  $("#promo-m-pct").value = d.pct || "";
  $("#promo-m-amt").value = d.amt ? d.amt / 100 : "";
  $("#promo-m-max").value = d.max || "";
  $("#promo-m-min").value = d.min ? d.min / 100 : "";
  $("#promo-m-exp").value = d.exp ? d.exp.slice(0, 16) : "";
  $("#promo-m-err").hidden = true;
  $("#promo-modal").hidden = false;
}

$("#promo-create-btn").onclick = () => openPromoModal();
$("#promo-m-cancel").onclick = () => { $("#promo-modal").hidden = true; };

$("#promo-m-save").onclick = async () => {
  const code = $("#promo-m-code").value.trim().toUpperCase();
  const discount_percent = parseInt($("#promo-m-pct").value) || 0;
  const discount_kobo = (parseInt($("#promo-m-amt").value) || 0) * 100;
  const max_uses = parseInt($("#promo-m-max").value) || 0;
  const min_amount_kobo = (parseInt($("#promo-m-min").value) || 0) * 100;
  const expires_at = $("#promo-m-exp").value ? new Date($("#promo-m-exp").value).toISOString() : null;
  const err = $("#promo-m-err");

  if (!code) { err.textContent = "Code required"; err.hidden = false; return; }

  try {
    if (_editingPromoId) {
      await api("PATCH", `/admin/promos/${_editingPromoId}`, { discount_percent, discount_kobo, max_uses, min_amount_kobo, expires_at });
    } else {
      await api("POST", "/admin/promos", { code, discount_percent, discount_kobo, max_uses, min_amount_kobo, expires_at });
    }
    $("#promo-modal").hidden = true;
    toast("Saved", "ok");
    loadPromos();
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
};
