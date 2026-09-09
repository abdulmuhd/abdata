import { store, put, get } from "../api.js";
import { I } from "../icons.js";
import { esc, naira, toast, copyText } from "../ui.js";
import { appBar } from "../app.js";

export function renderProfile(screen) {
  const u = store.user || {};

  screen.innerHTML = `
    ${appBar({ title: "Profile", back: false })}
    <section class="section" style="margin-top:8px">
      <div class="card profile-card">
        <div class="avatar"><img src="/img/user.png" alt="${esc(u.full_name || "Profile")}" /></div>
        <div style="min-width:0">
          <div style="font-size:16px;font-weight:750">${esc(u.full_name || "")}</div>
          <div style="font-size:12.5px;color:var(--muted);margin-top:2px">${esc(u.email || "")}</div>
          <div style="display:flex;gap:6px;margin-top:7px">
            <span class="status-pill ${u.is_verified ? "successful" : "pending"}">${u.is_verified ? "Email verified" : "Email unverified"}</span>
            <span class="status-pill successful">KYC Tier 1</span>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="card menu-group">
        <button class="menu-item" id="m-edit">${I.edit}<span>Edit profile</span><span class="menu-item__right">${I.chevronRight}</span></button>
        <button class="menu-item" id="m-pin">${I.lock}<span>Transaction PIN</span><span class="menu-item__right">${store.user?.has_pin ? "Change" : "Set up now"}${I.chevronRight}</span></button>
        <button class="menu-item" id="m-pass">${I.shield}<span>Change password</span><span class="menu-item__right">${I.chevronRight}</span></button>
        ${u.is_admin ? `<button class="menu-item" onclick="window.open('/admin.html','_blank')">${I.settings}<span>Admin console</span><span class="menu-item__right">${I.chevronRight}</span></button>` : ""}
      </div>
      <div style="height:14px"></div>
      <div class="card" id="referral-card" style="padding:14px 16px;display:none">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
          <span style="color:var(--brand)">${I.gift}</span>
          <span style="font-size:13px;font-weight:700">Refer & earn ₦1,000</span>
        </div>
        <p style="font-size:12px;color:var(--muted);margin:0 0 10px">Share your code with friends. You both get ₦1,000 when they sign up!</p>
        <div style="display:flex;align-items:center;gap:8px">
          <code id="ref-code" style="flex:1;padding:8px 12px;background:var(--card-alt,#f3f4f6);border-radius:8px;font-size:15px;font-weight:700;letter-spacing:.06em"></code>
          <button class="btn btn--primary btn--sm" id="copy-ref" style="white-space:nowrap">Copy</button>
        </div>
        <div id="ref-count" style="font-size:12px;color:var(--muted);margin-top:8px"></div>
      </div>
      <div style="height:14px"></div>
      <div class="card menu-group">
        <button class="menu-item" onclick="location.hash='#/notifications'">${I.bell}<span>Notifications</span><span class="menu-item__right">${store.unread || 0} new${I.chevronRight}</span></button>
        <div class="menu-item" style="justify-content:space-between">
          <span style="display:flex;align-items:center;gap:10px">${I.bell}<span>Push notifications</span></span>
          <label class="toggle">
            <input type="checkbox" id="push-toggle" />
            <span class="toggle__track"></span>
          </label>
        </div>
        <a class="menu-item" href="#/transactions">${I.receipt}<span>Transaction history</span><span class="menu-item__right">${I.chevronRight}</span></a>
        <button class="menu-item" id="m-support">${I.help}<span>Help &amp; support</span><span class="menu-item__right">${I.chevronRight}</span></button>
      </div>
      <div style="height:14px"></div>
      <div class="card menu-group">
        <button class="menu-item danger" id="m-logout">${I.logout}<span>Log out</span></button>
      </div>
      <p style="text-align:center;font-size:11px;color:var(--faint);margin-top:16px">Zaply v1.0 · Made for Nigeria 🇳🇬</p>
    </section>`;

  screen.querySelector("#m-edit").addEventListener("click", () => (location.hash = "#/settings/edit-profile"));
  screen.querySelector("#m-pin").addEventListener("click", () => (location.hash = "#/settings/pin"));
  screen.querySelector("#m-pass").addEventListener("click", () => (location.hash = "#/settings/password"));
  screen.querySelector("#m-logout").addEventListener("click", doLogout);
  screen.querySelector("#m-support").addEventListener("click", showSupportSheet);
  loadReferralInfo(screen);
  setupPushToggle(screen);
}

async function loadReferralInfo(screen) {
  try {
    const d = await get("/users/me/referrals");
    const card = screen.querySelector("#referral-card");
    const code = screen.querySelector("#ref-code");
    const count = screen.querySelector("#ref-count");
    if (card && d.referral_code) {
      code.textContent = d.referral_code;
      count.textContent = d.referral_count ? `${d.referral_count} friend${d.referral_count === 1 ? "" : "s"} referred` : "No referrals yet";
      card.style.display = "";
      screen.querySelector("#copy-ref").addEventListener("click", () => {
        copyText(d.referral_code);
        toast("Referral code copied!", "ok");
      });
    }
  } catch {}
}

async function showSupportSheet() {
  const { openSheet, closeSheet } = await import("../ui.js");
  const { get } = await import("../api.js");
  let phone = "0800 0000 0000";
  let email = "support@zaply.ng";
  try {
    const d = await get("/admin/site-settings/public");
    if (d.support_phone) phone = d.support_phone;
    if (d.support_email) email = d.support_email;
  } catch {}
  const phoneClean = phone.replace(/\D/g, "");
  openSheet(`
    <div class="sheet__grabber"></div>
    <div class="sheet__title">Help &amp; support</div>
    <div class="sheet__subtitle">We typically respond within minutes.</div>
    <div style="display:grid;gap:10px;margin-top:16px">
      <a class="btn btn--soft" href="mailto:${esc(email)}">${I.mail} ${esc(email)}</a>
      <a class="btn btn--ghost" href="tel:+234${esc(phoneClean)}">${I.phoneIco} ${esc(phone)}</a>
      <a class="btn btn--ghost" href="/terms.html" target="_blank" rel="noopener">Terms of Service</a>
      <a class="btn btn--ghost" href="/privacy.html" target="_blank" rel="noopener">Privacy Policy</a>
      <button class="btn btn--ghost" onclick="closeSheet()">Close</button>
    </div>`);
}

async function doLogout() {
  const { post, clearSession } = await import("../api.js");
  const refresh = store.session?.refresh_token || "";
  try {
    await post("/auth/logout", { refresh_token: refresh });
  } catch {}
  clearSession();
  location.hash = "#/welcome";
}

async function setupPushToggle(screen) {
  const toggle = screen.querySelector("#push-toggle");
  if (!toggle) return;

  try {
    const d = await get("/notifications/push/status");
    toggle.checked = d.enabled;
  } catch {}

  toggle.addEventListener("change", async () => {
    if (toggle.checked) {
      try {
        const reg = await navigator.serviceWorker.ready;
        const keyRes = await get("/notifications/push/vapid-key");
        if (!keyRes.public_key) {
          toast("Push notifications not available", "err");
          toggle.checked = false;
          return;
        }
        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(keyRes.public_key),
        });
        const keys = sub.getKey("p256dh");
        const authKey = sub.getKey("auth");
        await post("/notifications/push/subscribe", {
          endpoint: sub.endpoint,
          p256dh: keys ? btoa(String.fromCharCode(...new Uint8Array(keys))) : "",
          auth: authKey ? btoa(String.fromCharCode(...new Uint8Array(authKey))) : "",
        });
        toast("Push notifications enabled", "ok");
      } catch (err) {
        console.error("Push subscribe error:", err);
        toast("Failed to enable push notifications", "err");
        toggle.checked = false;
      }
    } else {
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          const keys = sub.getKey("p256dh");
          const authKey = sub.getKey("auth");
          await post("/notifications/push/unsubscribe", {
            endpoint: sub.endpoint,
            p256dh: keys ? btoa(String.fromCharCode(...new Uint8Array(keys))) : "",
            auth: authKey ? btoa(String.fromCharCode(...new Uint8Array(authKey))) : "",
          });
          await sub.unsubscribe();
        }
        toast("Push notifications disabled", "ok");
      } catch (err) {
        console.error("Push unsubscribe error:", err);
      }
    }
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
