import { I } from "../icons.js";

export function renderWelcome(screen) {
  screen.innerHTML = `
  <div class="welcome">
    <div class="welcome__logo">
      <div class="logo-mark">${I.logo}</div>
      <span>Zaply</span>
    </div>

    <div class="welcome__hero">
      <div class="float-chips">
        <div class="phone"></div>
        <div class="chip-float c1">
          <span class="chip-ico" style="background:#e40000">${I.airtime.replace('width="21" height="21"', 'width="13" height="13"')}</span>
          <span>Airtime<small>MTN · Airtel · Glo</small></span>
        </div>
        <div class="chip-float c2">
          <span class="chip-ico" style="background:var(--brand)">${I.data.replace('width="21" height="21"', 'width="13" height="13"')}</span>
          <span>Data<small>From ₦250</small></span>
        </div>
        <div class="chip-float c3">
          <span class="chip-ico" style="background:#f79009">${I.electricity.replace('width="21" height="21"', 'width="13" height="13"')}</span>
          <span>Bills<small>NEPA · DStv · GOtv</small></span>
        </div>
      </div>

      <h1 style="text-align:center">Everything You Need,<br/>One Tap Away</h1>
      <p class="desc" style="text-align:center">Buy airtime, data, pay bills, fund your wallet and manage your transactions easily from one secure app.</p>
    </div>

    <button class="btn btn--primary" id="go-start">Get Started</button>
    <div class="link-row">Already have an account? <button id="go-signin">Sign In</button></div>
  </div>`;

  screen.querySelector("#go-start").addEventListener("click", () => (location.hash = "#/register"));
  screen.querySelector("#go-signin").addEventListener("click", () => (location.hash = "#/login"));
}
