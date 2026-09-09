import { toast } from "../ui.js";
import { I } from "../icons.js";
import { detectNetwork, fmtPhone, netLogo } from "../networks.js";

export const field = ({ id, label, type = "text", icon = "", placeholder = "", value = "", attrs = "", hint = "" }) => `
  <div class="field">
    <label class="field__label" for="${id}">${label}</label>
    <div class="field__wrap">
      ${icon}
      <input id="${id}" type="${type}" placeholder="${placeholder}" value="${value}" ${attrs} autocomplete="off" />
    </div>
    ${hint ? `<div class="field__hint">${hint}</div>` : ""}
  </div>`;

export const phoneLabel = (name) =>
  name === "9mobile" ? "9mobile" : String(name || "").toUpperCase();

// Phone field with a network-detection tile (same design as airtime/data).
export const phoneField = ({ id, label = "Phone number", placeholder = "0801 234 5678", value = "", attrs = "", hint = "" }) => `
  <div class="field">
    <label class="field__label" for="${id}">${label}</label>
    <div class="phone-field">
      <span class="phone-field__tile" id="${id}-tile">${I.phoneIco}</span>
      <input id="${id}" type="tel" inputmode="tel" placeholder="${placeholder}" maxlength="13" autocomplete="tel" value="${value}" ${attrs} />
      <button class="phone-field__clear" id="${id}-clear" type="button" aria-label="Clear number" hidden>${I.close}</button>
    </div>
    <span class="detect-pill" id="${id}-pill" hidden></span>
    ${hint ? `<div class="field__hint">${hint}</div>` : ""}
  </div>`;

// Wire formatting + prefix-based network detection into a phoneField input.
// Returns { paint, getDigits }; onChange receives { digits, code }.
export function attachPhoneDetector(input, onChange) {
  const wrap = input.closest(".phone-field");
  const tile = wrap?.querySelector(".phone-field__tile");
  const clearBtn = wrap?.querySelector(".phone-field__clear");
  const pill = document.getElementById(`${input.id}-pill`);

  const getDigits = () => input.value.replace(/\D/g, "").slice(0, 11);

  const paint = () => {
    const digits = getDigits();
    input.value = fmtPhone(digits);
    const code = detectNetwork(digits);
    if (tile) tile.innerHTML = code ? netLogo(code, phoneLabel(code), "#98a2b3") : I.phoneIco;
    if (clearBtn) clearBtn.hidden = !digits;
    if (pill) {
      pill.textContent = code ? `${phoneLabel(code)} network detected` : "";
      pill.hidden = !code;
      pill.style.display = code ? "inline-flex" : "none";
    }
    return { digits, code };
  };

  input.addEventListener("input", () => {
    const res = paint();
    onChange?.(res);
  });
  clearBtn?.addEventListener("click", () => {
    input.value = "";
    const res = paint();
    onChange?.(res);
    input.focus();
  });

  paint(); // format any prefilled value
  return { paint, getDigits };
}

export function bindSubmit(form, btnId, fn) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector(`#${btnId}`);
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = "Please wait…";
    try {
      await fn();
    } catch (err) {
      toast(err.message || "Something went wrong", "err");
    } finally {
      btn.disabled = false;
      btn.textContent = btn.dataset.label;
    }
  });
}

export function setBtnLabel(btn, label) {
  btn.dataset.label = label;
  btn.textContent = label;
}
