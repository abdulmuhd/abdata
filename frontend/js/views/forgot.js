import { post } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { field, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderForgot(screen) {
  screen.innerHTML = `
  <div style="padding:calc(18px + env(safe-area-inset-top,0px)) 24px 0">
    <button class="appbar__back" onclick="history.back()" aria-label="Back">${I.back}</button>
  </div>
  <div class="auth-body">
    <div class="auth-head">
      <h1>Reset password</h1>
      <p>Enter your email and we'll send you a reset link.</p>
    </div>
    <form id="forgot-form" style="margin-top:22px">
      ${field({ id: "email", label: "Email address", icon: I.mail, placeholder: "you@example.com", type: "email", attrs: "required" })}
      <button class="btn btn--primary" id="submit-btn" data-label="Send reset link">Send reset link</button>
    </form>
    <div id="dev-token" style="margin-top:18px"></div>
    <div class="link-row"><button onclick="location.hash='#/login'">Back to Sign In</button></div>
  </div>`;

  const form = screen.querySelector("#forgot-form");
  setBtnLabel(form.querySelector("#submit-btn"), "Send reset link");
  bindSubmit(form, "submit-btn", async () => {
    const r = await post("/auth/forgot-password", { email: form.email.value.trim() });
    toast(r.message, "ok");
    const box = screen.querySelector("#dev-token");
    if (r.dev_reset_token) {
      box.innerHTML = `
        <div class="card" style="padding:14px;font-size:12.5px;color:var(--muted)">
          Sandbox mode — open the reset link directly:
          <div style="margin-top:8px"><button class="btn btn--soft btn--sm" id="use-token">Continue to reset</button></div>
        </div>`;
      box.querySelector("#use-token").addEventListener("click", () => {
        location.hash = `#/reset?token=${encodeURIComponent(r.dev_reset_token)}`;
      });
    }
  });
}
