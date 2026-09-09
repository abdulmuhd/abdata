import { store, patch } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { appBar } from "../app.js";
import { field, phoneField, attachPhoneDetector, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderEditProfile(screen) {
  const u = store.user || {};
  screen.innerHTML = `
    ${appBar({ title: "Edit profile" })}
    <section class="section">
      <form id="form">
        ${field({ id: "full_name", label: "Full name", icon: I.user.replace('width="22" height="22"', 'width="18" height="18"'), value: u.full_name || "", attrs: "required minlength='3'" })}
        <div class="field">
          <label class="field__label">Email address</label>
          <div class="field__wrap" style="opacity:.7">${I.mail}<input value="${u.email || ""}" disabled /></div>
          <div class="field__hint">Email can't be changed in this version</div>
        </div>
        ${phoneField({ id: "phone", value: u.phone || "", attrs: "required" })}
        <button class="btn btn--primary" id="submit-btn" data-label="Save changes">Save changes</button>
      </form>
    </section>`;

  const form = screen.querySelector("#form");
  setBtnLabel(form.querySelector("#submit-btn"), "Save changes");
  attachPhoneDetector(form.phone);
  bindSubmit(form, "submit-btn", async () => {
    await patch("/users/me", {
      full_name: form.full_name.value.trim(),
      phone: form.phone.value.trim().replace(/\s|-/g, ""),
    });
    toast("Profile updated", "ok");
    history.back();
  });
}
