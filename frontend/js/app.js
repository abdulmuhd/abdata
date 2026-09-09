import { store, loadSession, clearSession, isSessionExpired, apiBase, get } from "./api.js";
import { I } from "./icons.js";
import { esc } from "./ui.js";

import { renderWelcome } from "./views/welcome.js";
import { renderLogin } from "./views/login.js";
import { renderRegister } from "./views/register.js";
import { renderForgot } from "./views/forgot.js";
import { renderReset } from "./views/reset.js";
import { renderHome } from "./views/home.js";
import { renderTransactions } from "./views/transactions.js";
import { renderWallet } from "./views/wallet.js";
import { renderProfile } from "./views/profile.js";
import { renderAirtime } from "./views/airtime.js";
import { renderData } from "./views/data.js";
import { renderElectricity } from "./views/electricity.js";
import { renderCable } from "./views/cable.js";
import { renderExams } from "./views/exams.js";
import { renderEducation } from "./views/education.js";
import { renderServices } from "./views/services.js";
import { renderNotifications } from "./views/notifications.js";
import { renderTransfer } from "./views/transfer.js";
import { renderEditProfile } from "./views/edit-profile.js";
import { renderPassword } from "./views/password.js";
import { renderPinSettings } from "./views/pin-settings.js";

const routes = {
  // entry & auth screens run full-bleed without the tab bar
  "/welcome": { view: renderWelcome, bare: true, guestOnly: true, hideNav: true },
  "/login": { view: renderLogin, bare: true, guestOnly: true, hideNav: true },
  "/register": { view: renderRegister, bare: true, guestOnly: true, hideNav: true },
  "/forgot": { view: renderForgot, bare: true, guestOnly: true, hideNav: true },
  "/reset": { view: renderReset, bare: true, guestOnly: true, hideNav: true },

  "/home": { view: renderHome, tab: "home" },
  "/transactions": { view: renderTransactions, tab: "transactions" },
  "/wallet": { view: renderWallet, tab: "wallet" },
  "/profile": { view: renderProfile, tab: "profile" },

  "/notifications": { view: renderNotifications },
  "/services": { view: renderServices, hideNav: true },

  "/airtime": { view: renderAirtime, hideNav: true },
  "/data": { view: renderData, hideNav: true },
  "/electricity": { view: renderElectricity, hideNav: true },
  "/cable": { view: renderCable, hideNav: true },
  "/exams": { view: renderExams, hideNav: true },
  "/education": { view: renderEducation, hideNav: true },
  "/transfer": { view: renderTransfer, hideNav: true },

  "/settings/edit-profile": { view: renderEditProfile },
  "/settings/password": { view: renderPassword },
  "/settings/pin": { view: renderPinSettings },
};

const NAV = [
  { path: "/home", label: "Home", icon: I.home, iconActive: I.homeFill },
  { path: "/transactions", label: "History", icon: I.receipt, iconActive: I.receiptFill },
  { path: "/wallet", label: "Wallet", icon: I.wallet, iconActive: I.walletFill },
  { path: "/profile", label: "Profile", icon: I.user, iconActive: I.userFill },
];

export function navigate(path) {
  if (location.hash === `#${path}`) renderRoute();
  else location.hash = `#${path}`;
}

export async function refreshBalance() {
  try {
    const d = await get("/users/me/dashboard");
    store.user = { ...(store.user || {}), ...d.user };
    store.balanceKobo = d.balance_kobo;
    store.bonusKobo = d.bonus_balance_kobo || 0;
    store.unread = d.unread_notifications;
    store.bank = d.virtual_account || null;
    return d;
  } catch {
    return null;
  }
}

function paintChrome(route) {
  const nav = document.getElementById("bottomNav");
  nav.hidden = !store.session || !!route.hideNav;

  const activePath = route.tab ? `/${route.tab}` : location.hash.slice(1).split("?")[0];

  nav.innerHTML = NAV.map((i) => {
    const active = i.path === activePath;
    return `<a href="#${i.path}" class="${active ? "is-active" : ""}">${active ? i.iconActive || i.icon : i.icon}<span>${i.label}</span></a>`;
  }).join("");
}

let renderSeq = 0;

export async function renderRoute() {
  let path = location.hash.slice(1) || "/";
  path = path.split("?")[0];

  const route = routes[path];
  if (!route) { location.hash = "#/welcome"; return; }

  if (route.guestOnly && store.session) { location.hash = "#/home"; return; }
  if (!route.guestOnly && !store.session) { location.hash = "#/welcome"; return; }
  if (!route.guestOnly && !store.user) await refreshBalance();

  const seq = ++renderSeq;
  const screen = document.getElementById("screen");
  screen.className = `screen ${route.bare ? "screen--bare" : ""}`;
  // belt-and-braces: CSS-level kill switch for the tab bar on entry/auth screens
  document.body.classList.toggle("no-nav", !store.session || !!route.hideNav);
  window.scrollTo(0, 0);
  paintChrome(route);
  try {
    await route.view(screen, () => seq === renderSeq);
  } catch (err) {
    console.error(err);
    if (seq === renderSeq) {
      screen.innerHTML = `<div class="empty-state"><h4>Something went wrong</h4><p>${esc(err.message || "Try again.")}</p></div>`;
    }
  }
}

export function appBar({ title, sub = "", back = true }) {
  return `
    <header class="appbar">
      ${back ? `<button class="appbar__back" onclick="history.back()" aria-label="Back">${I.back}</button>` : ""}
      <div><div class="appbar__title">${title}</div>${sub ? `<div class="appbar__sub">${sub}</div>` : ""}</div>
    </header>`;
}

window.addEventListener("hashchange", () => {
  document.getElementById("sheet-root").innerHTML = "";
  document.body.style.overflow = "";
  renderRoute();
});

// ── boot ───────────────────────────────────────────────────
loadSession();
if (store.session && isSessionExpired()) {
  clearSession();
}
applyTheme().then(() => renderRoute());

async function applyTheme() {
  try {
    const base = apiBase();
    const res = await fetch(`${base}/api/v1/admin/site-settings/public`);
    if (!res.ok) return;
    const json = await res.json();
    const tv = json.data?.theme_vars;
    if (!tv) return;
    const r = document.documentElement.style;
    if (tv.bg) r.setProperty("--bg", tv.bg);
    if (tv.card) r.setProperty("--card", tv.card);
    if (tv.ink) r.setProperty("--ink", tv.ink);
    if (tv.ink2) r.setProperty("--ink-2", tv.ink2);
    if (tv.muted) r.setProperty("--muted", tv.muted);
    if (tv.brand) r.setProperty("--brand", tv.brand);
    if (tv.brand050) r.setProperty("--brand-050", tv.brand050);
    if (tv.brand100) r.setProperty("--brand-100", tv.brand100);
    if (tv.brand400) r.setProperty("--brand-400", tv.brand400);
    if (tv.brand600) r.setProperty("--brand-600", tv.brand600);
    if (tv.brand700) r.setProperty("--brand-700", tv.brand700);
    if (tv.brandShadowSm) r.setProperty("--brand-shadow-sm", tv.brandShadowSm);
    if (tv.brandShadowMd) r.setProperty("--brand-shadow-md", tv.brandShadowMd);
    if (tv.brandShadowLg) r.setProperty("--brand-shadow-lg", tv.brandShadowLg);
    if (tv.brandShadowXl) r.setProperty("--brand-shadow-xl", tv.brandShadowXl);
    if (tv.line) r.setProperty("--line", tv.line);
    if (tv.lineStrong) r.setProperty("--line-strong", tv.lineStrong);
    if (tv.danger) r.setProperty("--danger", tv.danger);
    if (tv.navBg) r.setProperty("--nav-bg", tv.navBg);
    if (tv.statusBar) {
      let meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) { meta = document.createElement("meta"); meta.name = "theme-color"; document.head.appendChild(meta); }
      meta.content = tv.statusBar;
    }
    document.title = json.data?.site_name ? `${json.data.site_name} — Zaply` : "Zaply";
  } catch { /* optional — stay quiet */ }
}

