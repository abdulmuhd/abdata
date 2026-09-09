import { post } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { field, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderReset(screen) {
  const token = new URLSearchParams(location.hash.split("?")[1] || "").get("token") || "";

  screen.innerHTML = `
  <div style="padding:calc(18px + env(safe-area-inset-top,0px)) 24px 0">
    <button class="appbar__back" onclick="history.back()" aria-label="Back">${I.back}</button>
  </div>
  <div class="auth-body">
    <div class="auth-head">
      <h1>Choose a new password</h1>
      <p>Your new password must be at least 8 characters.</p>
    </div>
    <form id="reset-form" style="margin-top:22px">
      ${field({ id: "new_password", label: "New password", type: "password", icon: I.lock, placeholder: "••••••••", attrs: "required minlength='8'" })}
      ${field({ id: "confirm", label: "Confirm password", type: "password", icon: I.lock, placeholder: "••••••••", attrs: "required minlength='8'" })}
      <button class="btn btn--primary" id="submit-btn" data-label="Update password">Update password</button>
    </form>
  </div>`;

  const form = screen.querySelector("#reset-form");
  setBtnLabel(form.querySelector("#submit-btn"), "Update password");
  bindSubmit(form, "submit-btn", async () => {
    if (form.new_password.value !== form.confirm.value) throw new Error("Passwords do not match");
    await post("/auth/reset-password", { reset_token: token, new_password: form.new_password.value });
    toast("Password updated. Please sign in.", "ok");
    location.hash = "#/login";
  });
}
