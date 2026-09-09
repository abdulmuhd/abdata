import { get } from "../api.js";
import { I } from "../icons.js";
import { esc, toast } from "../ui.js";
import { appBar } from "../app.js";

const COMING_ICONS = { graduation: I.graduation, trophy: I.trophy, school: I.school };

export function renderServices(screen) {
  screen.innerHTML = `
    ${appBar({ title: "All Services", sub: "One app for every top-up" })}
    <section class="section" id="catalog"><div class="skel"></div><div class="skel"></div><div class="skel"></div></section>`;

  load();
  async function load() {
    try {
      const cat = await get("/services");
      const box = screen.querySelector("#catalog");

      const group = (title, items, href) => `
        <div class="section__head" style="margin-top:18px"><div class="section__title">${title}</div></div>
        <div class="card menu-group">
          ${items
            .map(
              (n) => `
              <a class="menu-item" href="#${href}?p=${esc(n.code)}">
                <span class="provider-card__logo" style="background:${esc(n.color || "#98a2b3")};width:34px;height:34px;font-size:10px">${esc(n.short_name.slice(0, 2).toUpperCase())}</span>
                <span>${esc(n.name)}</span>
                <span class="menu-item__right">${I.chevronRight}</span>
              </a>`
            )
            .join("")}
        </div>`;

      box.innerHTML = `
        <div class="section__head" style="margin-top:18px"><div class="section__title">Top-ups</div></div>
        <div class="card menu-group">
          <a class="menu-item" href="#/airtime"><span class="provider-card__logo" style="background:#e40000;width:34px;height:34px;font-size:10px">AI</span><span>Buy Airtime</span><span class="menu-item__right">${I.chevronRight}</span></a>
          <a class="menu-item" href="#/data"><span class="provider-card__logo" style="background:var(--brand);width:34px;height:34px;font-size:10px">DA</span><span>Buy Data</span><span class="menu-item__right">${I.chevronRight}</span></a>
        </div>
        ${group("Exam PINs", cat.exam_bodies || [], "/exams")}
        ${group("Electricity", cat.electricity_providers, "/electricity")}
        ${group("Cable TV", cat.cable_providers, "/cable")}
        ${group("School Fees", cat.institutions || [], "/education")}
        ${(cat.coming_soon || []).length
          ? `<div class="section__head" style="margin-top:18px"><div class="section__title">Coming soon</div></div>
             <div class="card menu-group">
               ${cat.coming_soon
                 .map(
                   (c) => `
                   <div class="menu-item" style="opacity:.65">
                     <span style="color:var(--muted)">${COMING_ICONS[c.icon] || I.grid}</span>
                     <span>${esc(c.name)}</span>
                     <span class="menu-item__right">${esc(c.note)}</span>
                   </div>`
                 )
                 .join("")}
             </div>`
          : ""}`;
    } catch (err) {
      toast(err.message, "err");
    }
  }
}
