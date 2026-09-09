import { put } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { appBar } from "../app.js";
import { field, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderPassword(screen) {
  screen.innerHTML = `
    ${appBar({ title: "Change password" })}
    <section class="section">
      <form id="form">
        ${field({ id: "current", label: "Current password", type: "password", icon: I.lock, placeholder: "••••••••", attrs: "required" })}
        ${field({ id: "new1", label: "New password", type: "password", icon: I.lock, placeholder: "At least 8 characters", attrs: "required minlength='8'" })}
        ${field({ id: "new2", label: "Confirm new password", type: "password", icon: I.lock, placeholder: "Repeat it", attrs: "required minlength='8'" })}
        <button class="btn btn--primary" id="submit-btn" data-label="Update password">Update password</button>
      </form>
    </section>`;

  const form = screen.querySelector("#form");
  setBtnLabel(form.querySelector("#submit-btn"), "Update password");
  bindSubmit(form, "submit-btn", async () => {
    if (form.new1.value !== form.new2.value) throw new Error("New passwords do not match");
    await put("/users/me/password", { current_password: form.current.value, new_password: form.new1.value });
    toast("Password updated 🔐", "ok");
    history.back();
  });
}
