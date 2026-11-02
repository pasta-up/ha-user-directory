// Sidebar panel: edit your own contact info; admins can pick any user.
const FIELDS = [
  { key: "email", label: "Email", type: "email", autocomplete: "email" },
  { key: "phone", label: "Phone", type: "tel", autocomplete: "tel" },
  { key: "github", label: "GitHub username", type: "text", autocomplete: "username" },
];

const TEMPLATE = `
  <style>
    :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
    header { display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); font-size: 20px; }
    .card { max-width: 560px; margin: 24px auto; padding: 16px 24px 24px; background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); }
    label { display: block; margin-top: 16px; font-size: 14px; color: var(--secondary-text-color); }
    input, select { box-sizing: border-box; width: 100%; margin-top: 4px; padding: 10px; font-size: 16px; color: var(--primary-text-color); background: var(--input-fill-color, transparent); border: 1px solid var(--input-idle-line-color, var(--divider-color)); border-radius: 4px; }
    .actions { display: flex; align-items: center; gap: 12px; margin-top: 24px; }
    button { padding: 10px 20px; font-size: 14px; border: none; border-radius: 4px; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
    button:disabled { opacity: 0.5; cursor: default; }
    .status { font-size: 14px; }
    .error { color: var(--error-color, #db4437); }
    .hint { font-size: 12px; color: var(--secondary-text-color); margin-top: 16px; }
    [hidden] { display: none; }
  </style>
  <header><ha-menu-button></ha-menu-button><span>Contact info</span></header>
  <form class="card">
    <div id="user-row" hidden>
      <label for="user">User</label>
      <select id="user"></select>
    </div>
    ${FIELDS.map((f) => `<label for="${f.key}">${f.label}</label><input id="${f.key}" type="${f.type}" autocomplete="${f.autocomplete}">`).join("")}
    <div class="hint">All fields are optional. Only you and admins can see or change them.</div>
    <div class="actions"><button type="submit">Save</button><span class="status"></span></div>
  </form>
`;

class ProfileExtenderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = TEMPLATE;
    this._loaded = false;
    const root = this.shadowRoot;
    root.querySelector("form").addEventListener("submit", (ev) => { ev.preventDefault(); this._save(); });
    root.getElementById("user").addEventListener("change", () => this._load());
  }

  set hass(hass) {
    this._hass = hass;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    menu.hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._init();
    }
  }

  set narrow(narrow) {
    this.shadowRoot.querySelector("ha-menu-button").narrow = narrow;
  }

  get _userId() {
    return this.shadowRoot.getElementById("user").value || this._hass.user.id;
  }

  async _init() {
    if (this._hass.user.is_admin) {
      try {
        const users = await this._hass.callWS({ type: "config/auth/list" });
        const select = this.shadowRoot.getElementById("user");
        users
          .filter((u) => !u.system_generated)
          .sort((a, b) => a.name.localeCompare(b.name))
          .forEach((u) => {
            const opt = document.createElement("option");
            opt.value = u.id;
            opt.textContent = u.id === this._hass.user.id ? `${u.name} (you)` : u.name;
            select.append(opt);
          });
        select.value = this._hass.user.id;
        this.shadowRoot.getElementById("user-row").hidden = false;
      } catch (err) {
        // Not fatal: admins can still edit their own info.
      }
    }
    this._load();
  }

  async _load() {
    this._status("");
    try {
      const contact = await this._hass.callWS({ type: "profile_extender/contact/get", user_id: this._userId });
      FIELDS.forEach((f) => { this.shadowRoot.getElementById(f.key).value = contact[f.key] || ""; });
    } catch (err) {
      this._status(err.message, true);
    }
  }

  async _save() {
    const button = this.shadowRoot.querySelector("button");
    const msg = { type: "profile_extender/contact/update", user_id: this._userId };
    FIELDS.forEach((f) => { msg[f.key] = this.shadowRoot.getElementById(f.key).value; });
    button.disabled = true;
    try {
      const contact = await this._hass.callWS(msg);
      FIELDS.forEach((f) => { this.shadowRoot.getElementById(f.key).value = contact[f.key] || ""; });
      this._status("Saved");
    } catch (err) {
      this._status(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  _status(text, isError = false) {
    const el = this.shadowRoot.querySelector(".status");
    el.textContent = text;
    el.classList.toggle("error", isError);
  }
}

customElements.define("profile-extender-panel", ProfileExtenderPanel);
