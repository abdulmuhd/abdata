import { post, saveSession } from "../api.js";
import { I } from "../icons.js";
import { toast, openSheet, closeSheet, esc } from "../ui.js";
import { field, phoneField, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderRegister(screen) {
  screen.innerHTML = `
  <div style="padding:calc(18px + env(safe-area-inset-top,0px)) 24px 0">
    <button class="appbar__back" onclick="history.back()" aria-label="Back">${I.back}</button>
  </div>
  <div class="auth-body">
    <div class="auth-head">
      <h1>Create your account</h1>
      <p>Join thousands paying bills the smart way.</p>
    </div>
    <form id="reg-form" style="margin-top:22px">
      ${field({ id: "full_name", label: "Full name", icon: I.user.replace('width="22" height="22"', 'width="18" height="18"'), placeholder: "Adaeze Okafor", attrs: "required minlength='3'" })}
      ${field({ id: "email", label: "Email address", icon: I.mail, placeholder: "you@example.com", type: "email", attrs: "required" })}
      ${phoneField({ id: "phone", attrs: "required", hint: "Your default airtime & data recipient" })}
      ${field({ id: "password", label: "Password", type: "password", icon: I.lock, placeholder: "At least 8 characters", attrs: "required minlength='8'" })}
      ${field({ id: "referral_code", label: "Referral code (optional)", icon: I.gift, placeholder: "e.g. ABC12345", attrs: "maxlength='8' style='text-transform:uppercase'" })}
      <label style="display:flex;gap:9px;font-size:12.5px;color:var(--muted);margin:-4px 2px 18px;align-items:flex-start">
        <input type="checkbox" required style="margin-top:2px" />
        <span>I agree to the <a href="/terms.html" target="_blank" rel="noopener" style="color:var(--brand-600);font-weight:600">Terms of Service</a> and <a href="/privacy.html" target="_blank" rel="noopener" style="color:var(--brand-600);font-weight:600">Privacy Policy</a></span>
      </label>
      <button class="btn btn--primary" id="submit-btn" data-label="Create Account">Create Account</button>
    </form>
    <div class="link-row">Already have an account? <button onclick="location.hash='#/login'">Sign In</button></div>
  </div>`;

  const form = screen.querySelector("#reg-form");
  setBtnLabel(form.querySelector("#submit-btn"), "Create Account");
  bindSubmit(form, "submit-btn", async () => {
    const payload = {
      full_name: form.full_name.value.trim(),
      email: form.email.value.trim(),
      phone: form.phone.value.trim().replace(/\s|-/g, ""),
      password: form.password.value,
    };
    const ref = form.referral_code.value.trim().toUpperCase();
    if (ref) payload.referral_code = ref;
    const data = await post("/auth/register", payload);
    saveSession({ access_token: data.access_token, refresh_token: data.refresh_token });
    sessionStorage.setItem("zaply_announce", "1");
    showVerifySheet(data);
    if (!data.has_pin) {
      setTimeout(() => toast("Tip: set your transaction PIN (Profile → Transaction PIN) to enable payments", "ok"), 1600);
    }
    location.hash = "#/home";
  });

  function showVerifySheet(data) {
    const ev = data.email_verification;
    toast("Account created — welcome to Zaply! 🎉", "ok");
    if (ev?.dev_code) {
      openSheet(`
        <div class="sheet__grabber"></div>
        <div class="sheet__title">Verify your email</div>
        <div class="sheet__subtitle">We sent a 6-digit code to ${esc(data.email)}. Sandbox mode shows it here: <b>${esc(ev.dev_code)}</b></div>
        <form id="verify-form">
          <div class="otp-row">${[0, 1, 2, 3, 4, 5].map((i) => `<input inputmode="numeric" maxlength="1" required />`).join("")}</div>
          <button class="btn btn--primary" id="verify-btn">Verify email</button>
          <button type="button" class="btn btn--ghost" style="margin-top:10px" onclick="closeSheet()">Skip for now</button>
        </form>`);

      const inputs = [...document.querySelectorAll(".otp-row input")];
      inputs[0].focus();
      inputs.forEach((inp, i) => {
        inp.addEventListener("input", () => { if (inp.value && i < 5) inputs[i + 1].focus(); });
        inp.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !inp.value && i > 0) inputs[i - 1].focus(); });
      });
      document.getElementById("verify-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await post("/auth/verify-email", { email: data.email, code: inputs.map((x) => x.value).join("") });
          closeSheet();
          toast("Email verified ✅", "ok");
        } catch (err) {
          toast(err.message, "err");
        }
      });
    }
  }
}
