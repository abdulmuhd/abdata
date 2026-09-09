import { store, put } from "../api.js";
import { I } from "../icons.js";
import { toast } from "../ui.js";
import { appBar } from "../app.js";
import { field, bindSubmit, setBtnLabel } from "./formkit.js";

export function renderPinSettings(screen) {
  const hasPin = !!store.user?.has_pin;

  screen.innerHTML = `
    ${appBar({ title: "Transaction PIN" })}
    <section class="section">
      <div class="card" style="padding:14px 16px;display:flex;gap:10px;align-items:center">
        <span style="color:var(--brand-600)">${I.shield}</span>
        <span style="font-size:12.5px;color:var(--muted)">
          Your PIN is hashed on our servers and never stored on this device. You'll be asked for it before each transaction.
        </span>
      </div>
      <div style="height:16px"></div>
      <form id="form">
        ${hasPin
          ? field({
              id: "current",
              label: "Current PIN",
              type: "password",
              icon: I.lock,
              placeholder: "4 digits",
              attrs: "required maxlength='4' inputmode='numeric' pattern='\\d{4}'",
            })
          : ""}
        ${field({
          id: "new1",
          label: hasPin ? "New PIN" : "Create PIN",
          type: "password",
          icon: I.lock,
          placeholder: "4 digits",
          attrs: "required maxlength='4' inputmode='numeric' pattern='\\d{4}'",
        })}
        ${field({
          id: "new2",
          label: "Confirm PIN",
          type: "password",
          icon: I.lock,
          placeholder: "Repeat 4 digits",
          attrs: "required maxlength='4' inputmode='numeric' pattern='\\d{4}'",
        })}
        <button class="btn btn--primary" id="submit-btn" data-label="${hasPin ? "Change PIN" : "Set up PIN"}">${hasPin ? "Change PIN" : "Set up PIN"}</button>
      </form>
      ${!hasPin ? `<p style="font-size:12px;color:var(--muted);margin-top:10px;text-align:center">You won't be able to make payments until your PIN is set.</p>` : ""}
    </section>`;

  const form = screen.querySelector("#form");
  const submitBtn = form.querySelector("#submit-btn");
  setBtnLabel(submitBtn, hasPin ? "Change PIN" : "Set up PIN");

  bindSubmit(form, "submit-btn", async () => {
    if (form.new1.value !== form.new2.value) throw new Error("PINs do not match");
    await put("/users/me/pin", {
      current_pin: hasPin ? form.current.value : undefined,
      new_pin: form.new1.value,
    });
    store.user.has_pin = true;
    toast("Transaction PIN saved ✅", "ok");
    history.back();
  });
}