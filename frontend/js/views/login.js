import { post, saveSession } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { field, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderLogin(screen) {
  screen.innerHTML = `
  <div style="padding:calc(18px + env(safe-area-inset-top,0px)) 24px 0">
    <button class="appbar__back" onclick="history.back()" aria-label="Back">${I.back}</button>
  </div>
  <div class="auth-body">
    <div class="auth-head">
      <div class="logo-mark" style="margin-bottom:14px">${I.logo}</div>
      <h1>Welcome back</h1>
      <p>Sign in to continue topping up and paying bills.</p>
    </div>
    <form id="login-form" style="margin-top:22px">
      ${field({ id: "phone", label: "Phone number", icon: I.phoneIco, placeholder: "0801 234 5678", attrs: "required inputmode='tel' maxlength='13'" })}
      ${field({ id: "password", label: "Password", type: "password", icon: I.lock, placeholder: "••••••••", attrs: "required minlength='8'" })}
      <button class="btn btn--primary" id="submit-btn" data-label="Sign In">Sign In</button>
    </form>
    <div class="link-row"><button id="go-forgot">Forgot password?</button></div>
    <div class="link-row" style="margin-top:8px">New to Zaply? <button onclick="location.hash='#/register'">Create account</button></div>
  </div>`;

  screen.querySelector("#go-forgot").addEventListener("click", () => (location.hash = "#/forgot"));

  const form = screen.querySelector("#login-form");
  const btn = form.querySelector("#submit-btn");
  setBtnLabel(btn, "Sign In");
  bindSubmit(form, "submit-btn", async () => {
    const data = await post("/auth/login", {
      phone: form.phone.value.trim().replace(/\s|-/g, ""),
      password: form.password.value,
    });
    saveSession({ access_token: data.access_token, refresh_token: data.refresh_token });
    sessionStorage.setItem("zaply_announce", "1");
    toast("Signed in. Welcome back!", "ok");
    location.hash = "#/home";
  });
}
