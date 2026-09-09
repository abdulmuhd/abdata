// Shared network helpers — brand logos served from /img + phone-prefix detection.
import { esc } from "./ui.js";

export const NET_LOGOS = {
  mtn: "/img/mtn.png",
  airtel: "/img/airtel.png",
  glo: "/img/glo.png",
  "9mobile": "/img/9mobile.png",
  // Cable TV brands
  dstv: "/img/dstv.png",
  gotv: "/img/gotv.png",
  startimes: "/img/startimes.png",
  // Electricity distributors (DisCos)
  ikedc: "/img/ikeja.png",
  ekedc: "/img/ekedc.png",
  aedc: "/img/aedc.png",
  ibedc: "/img/ibedc.png",
  kedco: "/img/kedco.png",
  phed: "/img/phedc.png",
  jed: "/img/jos.png",
};

export const PREFIX_MAP = [
  { code: "mtn", prefixes: ["0803", "0806", "0703", "0706", "0810", "0813", "0814", "0816", "0903", "0906", "0913", "0916"] },
  { code: "airtel", prefixes: ["0701", "0708", "0802", "0808", "0812", "0901", "0902", "0904", "0907", "0911", "0912"] },
  { code: "glo", prefixes: ["0705", "0805", "0807", "0811", "0815", "0905", "0915"] },
  { code: "9mobile", prefixes: ["0809", "0817", "0818", "0908", "0909"] },
];

export const detectNetwork = (digits = "") =>
  PREFIX_MAP.find((m) => m.prefixes.some((p) => digits.startsWith(p)))?.code || null;

export const logoFor = (code) => NET_LOGOS[code] || null;
export const hasLogo = (code) => !!logoFor(code);

// Inner markup for a network logo tile: brand image when available,
// coloured initials otherwise.
export function netLogo(code, name, color = "#98a2b3") {
  const src = logoFor(code);
  if (!src) {
    return `<span style="background:${esc(color)}">${esc(String(name || "").slice(0, 2).toUpperCase())}</span>`;
  }
  return `<img src="${src}" alt="${esc(name)}" loading="lazy">`;
}

export const fmtPhone = (d) =>
  [d.slice(0, 4), d.slice(4, 7), d.slice(7, 11)].filter(Boolean).join(" ");

export const CHECK =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4.5 12.5 5 5L19.5 7"/></svg>';
