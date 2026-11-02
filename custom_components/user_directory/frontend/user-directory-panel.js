// Sidebar panel: the user directory, plus an editor for your own info (admins: anyone's).
const FIELDS = [
  { key: "email", label: "Email", type: "email", autocomplete: "email" },
  { key: "phone", label: "Phone", type: "tel", autocomplete: "tel" },
  { key: "github", label: "GitHub username", type: "text", autocomplete: "username", social: true },
];

// Shown under the email field.
const VERIFY = `
  <div id="verify" hidden>
    <div class="note" id="verify-note"></div>
    <div class="verify-row" id="verify-row">
      <button type="button" id="send-code">Email me a code</button>
      <input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="Code" aria-label="Code" hidden>
      <button type="button" id="confirm-code" hidden>Verify</button>
    </div>
  </div>`;

const TEMPLATE = `
  <style>
    :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
    header { display: flex; align-items: center; gap: 8px; height: var(--header-height, 56px); padding: 0 12px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); font-size: 20px; }
    header .title { flex: 1; }
    header button { background: transparent; color: inherit; border: 1px solid currentColor; }
    .card { max-width: 640px; margin: 24px auto; padding: 16px 24px 24px; background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); }
    label { display: block; margin-top: 16px; font-size: 14px; color: var(--secondary-text-color); }
    input, select { box-sizing: border-box; width: 100%; margin-top: 4px; padding: 10px; font-size: 16px; color: var(--primary-text-color); background: var(--input-fill-color, transparent); border: 1px solid var(--input-idle-line-color, var(--divider-color)); border-radius: 4px; }
    input[readonly] { color: var(--disabled-text-color, var(--secondary-text-color)); border-style: dashed; }
    label.check { display: flex; align-items: center; gap: 8px; margin-top: 8px; color: var(--primary-text-color); }
    label.check.top { margin-top: 24px; }
    label.check input { width: auto; margin: 0; }
    .note { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
    .actions { display: flex; align-items: center; gap: 12px; margin-top: 24px; }
    button { padding: 10px 20px; font-size: 14px; border: none; border-radius: 4px; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
    button:disabled { opacity: 0.5; cursor: default; }
    .status { font-size: 14px; }
    .error { color: var(--error-color, #db4437); }
    .ok { color: var(--success-color, #43a047); }
    .verify-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
    .verify-row button { padding: 8px 12px; }
    .verify-row input { width: 8em; margin: 0; }
    .hint { font-size: 12px; color: var(--secondary-text-color); margin-top: 16px; }
    ul { list-style: none; margin: 16px 0 0; padding: 0; }
    li { display: flex; align-items: center; gap: 16px; padding: 12px 8px; border-top: 1px solid var(--divider-color); cursor: pointer; }
    li:hover { background: var(--secondary-background-color); }
    .avatar { flex: none; width: 48px; height: 48px; border-radius: 50%; background: var(--primary-color) center / cover; color: var(--text-primary-color, #fff); display: flex; align-items: center; justify-content: center; font-size: 20px; }
    .who { min-width: 0; }
    .name { font-size: 16px; }
    .details { font-size: 14px; color: var(--secondary-text-color); display: flex; flex-wrap: wrap; gap: 4px 16px; }
    .details a { color: var(--primary-color); text-decoration: none; }
    .empty { margin-top: 16px; color: var(--secondary-text-color); }
    [hidden] { display: none !important; }
  </style>
  <header>
    <ha-menu-button></ha-menu-button><span class="title">User-Directory</span>
    <button id="to-editor">My info</button><button id="to-directory" hidden>Directory</button>
  </header>
  <div class="card" id="directory">
    <input id="search" type="search" placeholder="Search" aria-label="Search">
    <ul id="people"></ul>
    <div class="empty" id="empty" hidden>No one is listed yet.</div>
    <div class="hint">Click someone to save their contact card.</div>
  </div>
  <form class="card" id="editor" hidden>
    <div id="user-row" hidden>
      <label for="user">User</label>
      <select id="user"></select>
    </div>
    <label class="check top"><input id="listed" type="checkbox"> List me in the User-Directory</label>
    <div class="note" id="listed-note"></div>
    ${FIELDS.map((f) => `<label for="${f.key}">${f.label}</label><input id="${f.key}" type="${f.type}" autocomplete="${f.autocomplete}"><div class="note" id="${f.key}-note" hidden></div>${f.key === "email" ? VERIFY : ""}${f.social ? `<label class="check"><input id="share-${f.key}" type="checkbox"> Show in the directory</label>` : ""}`).join("")}
    <label class="check top"><input id="gravatar" type="checkbox"> Use my Gravatar as my profile picture</label>
    <div class="note" id="gravatar-note"></div>
    <div class="hint">Everything is optional. Only you and admins can change it.</div>
    <div class="actions"><button type="submit">Save</button><span class="status"></span></div>
  </form>
`;

// vCard 3.0, the version phones import most reliably.
function vcard(person) {
  const esc = (v) => String(v).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/([,;])/g, "\\$1");
  const parts = person.name.trim().split(/\s+/);
  const last = parts.length > 1 ? parts.pop() : "";
  const lines = ["BEGIN:VCARD", "VERSION:3.0", `N:${esc(last)};${esc(parts.join(" "))};;;`, `FN:${esc(person.name)}`];
  if (person.email) lines.push(`EMAIL;TYPE=INTERNET:${esc(person.email)}`);
  if (person.phone) lines.push(`TEL;TYPE=CELL:${esc(person.phone)}`);
  if (person.github) lines.push(`URL;TYPE=GitHub:https://github.com/${esc(person.github)}`);
  lines.push("END:VCARD");
  return lines.join("\r\n") + "\r\n";
}

class UserDirectoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" }).innerHTML = TEMPLATE;
    this._loaded = false;
    this._people = [];
    const $ = (id) => this.shadowRoot.getElementById(id);
    this._$ = $;
    $("editor").addEventListener("submit", (ev) => { ev.preventDefault(); this._save(); });
    $("user").addEventListener("change", () => this._load());
    $("gravatar").addEventListener("change", (ev) => this._setGravatar(ev.target));
    $("search").addEventListener("input", () => this._render());
    $("send-code").addEventListener("click", () => this._verify({ type: "user_directory/email/send_code" }, "Code sent. Check your email."));
    $("confirm-code").addEventListener("click", () => this._verify({ type: "user_directory/email/confirm", code: $("code").value }, "Email verified"));
    $("email").addEventListener("input", () => this._showVerify());
    $("to-editor").addEventListener("click", () => this._view("editor"));
    $("to-directory").addEventListener("click", () => this._view("directory"));
  }

  set hass(hass) {
    this._hass = hass;
    this.shadowRoot.querySelector("ha-menu-button").hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._init();
    }
  }

  set narrow(narrow) {
    this.shadowRoot.querySelector("ha-menu-button").narrow = narrow;
  }

  get _userId() {
    return this._$("user").value || this._hass.user.id;
  }

  _view(name) {
    const editing = name === "editor";
    this._$("editor").hidden = !editing;
    this._$("directory").hidden = editing;
    this._$("to-editor").hidden = editing;
    this._$("to-directory").hidden = !editing;
    if (editing) this._load();
    else this._loadDirectory();
  }

  async _init() {
    this._loadDirectory();
    if (!this._hass.user.is_admin) return;
    try {
      const users = await this._hass.callWS({ type: "config/auth/list" });
      const select = this._$("user");
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
      this._$("user-row").hidden = false;
    } catch (err) {
      // Not fatal: admins can still edit their own info.
    }
  }

  async _loadDirectory() {
    try {
      this._people = await this._hass.callWS({ type: "user_directory/directory/list" });
    } catch (err) {
      this._people = [];
    }
    this._render();
  }

  _render() {
    const query = this._$("search").value.trim().toLowerCase();
    const list = this._$("people");
    list.replaceChildren();
    const shown = this._people.filter((p) =>
      [p.name, p.email, p.phone, p.github].some((v) => v && v.toLowerCase().includes(query)));
    shown.forEach((p) => list.append(this._row(p)));
    this._$("empty").hidden = shown.length > 0;
  }

  // Built with DOM calls, not innerHTML, because names and values come from users.
  _row(person) {
    const li = document.createElement("li");
    li.title = `Save ${person.name}'s contact card`;
    li.addEventListener("click", () => this._download(person));
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    if (person.picture) avatar.style.backgroundImage = `url("${encodeURI(person.picture)}")`;
    else avatar.textContent = (person.name[0] || "?").toUpperCase();
    const who = document.createElement("div");
    who.className = "who";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = person.name;
    const details = document.createElement("div");
    details.className = "details";
    const link = (text, href) => {
      const a = document.createElement("a");
      a.textContent = text;
      a.href = href;
      a.addEventListener("click", (ev) => ev.stopPropagation());
      if (href.startsWith("https:")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
      details.append(a);
    };
    if (person.email) {
      link(person.email, `mailto:${person.email}`);
      if (person.email_verified) {
        details.lastChild.title = "Verified email";
        details.lastChild.append(" ✓");
      }
    }
    if (person.phone) link(person.phone, `tel:${person.phone.replace(/[^\d+]/g, "")}`);
    if (person.github) link(`GitHub: ${person.github}`, `https://github.com/${encodeURIComponent(person.github)}`);
    who.append(name, details);
    li.append(avatar, who);
    return li;
  }

  _download(person) {
    const url = URL.createObjectURL(new Blob([vcard(person)], { type: "text/vcard" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${person.name.replace(/[^\w\s-]/g, "").trim() || "contact"}.vcf`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async _load() {
    this._status("");
    try {
      this._show(await this._hass.callWS({ type: "user_directory/contact/get", user_id: this._userId }));
    } catch (err) {
      this._status(err.message, true);
    }
  }

  async _save() {
    const button = this.shadowRoot.querySelector("button[type=submit]");
    const msg = {
      type: "user_directory/contact/update",
      user_id: this._userId,
      listed: this._$("listed").checked,
      shared: FIELDS.filter((f) => f.social && this._$(`share-${f.key}`).checked).map((f) => f.key),
    };
    FIELDS.forEach((f) => { msg[f.key] = this._$(f.key).value; });
    button.disabled = true;
    try {
      this._show(await this._hass.callWS(msg));
      this._status("Saved");
    } catch (err) {
      this._status(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async _verify(msg, done) {
    const buttons = [this._$("send-code"), this._$("confirm-code")];
    buttons.forEach((b) => { b.disabled = true; });
    this._status("");
    try {
      this._show(await this._hass.callWS({ ...msg, user_id: this._userId }));
      this._$("code").value = "";
      this._status(done);
    } catch (err) {
      this._status(err.message, true);
    } finally {
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  // Verification is about the saved email, so it pauses while the field is edited.
  _showVerify() {
    const v = this._verification;
    const saved = this._savedEmail;
    const block = this._$("verify");
    block.hidden = !saved;
    if (!saved) return;
    const note = this._$("verify-note");
    const editing = this._$("email").value.trim() !== saved;
    const canVerify = !v.verified && v.available && !editing;
    note.classList.toggle("ok", v.verified && !editing);
    note.textContent = editing ? "Save to verify the new email."
      : v.verified ? "Verified ✓"
      : !v.available ? "Not verified. Email verification isn't set up; ask an admin."
      : v.pending ? "Not verified. Enter the code we emailed you."
      : "Not verified.";
    this._$("verify-row").hidden = !canVerify;
    this._$("send-code").textContent = v.pending ? "Send a new code" : "Email me a code";
    this._$("code").hidden = !v.pending;
    this._$("confirm-code").hidden = !v.pending;
  }

  async _setGravatar(box) {
    box.disabled = true;
    this._status("");
    try {
      this._show(await this._hass.callWS({ type: "user_directory/gravatar/set", user_id: this._userId, enabled: box.checked }));
    } catch (err) {
      box.checked = !box.checked;
      box.disabled = false;
      this._status(err.message, true);
    }
  }

  // result: see agents.md "Access control" for the shape.
  _show(result) {
    FIELDS.forEach((f) => {
      const input = this._$(f.key);
      const note = this._$(`${f.key}-note`);
      const locked = result.locked.includes(f.key);
      input.value = result.contact[f.key] || "";
      input.readOnly = locked;
      note.hidden = !result.sso.includes(f.key);
      note.textContent = locked ? "Managed by SSO. Change it in your identity provider." : "From SSO. Type to override.";
      if (f.social) this._$(`share-${f.key}`).checked = result.shared.includes(f.key);
    });
    const listed = this._$("listed");
    listed.checked = result.listed;
    listed.disabled = result.listed_locked;
    this._$("listed-note").textContent = result.listed_locked
      ? "An admin has made the directory required for you. Your name, picture, email and phone are shown to all users."
      : "Shows your name, picture, email and phone to all users of this Home Assistant.";
    this._savedEmail = result.contact.email || "";
    this._verification = result.email_verification;
    this._showVerify();
    const verified = result.email_verification.verified;
    const box = this._$("gravatar");
    box.checked = result.gravatar.enabled;
    box.disabled = !result.gravatar.enabled && (!result.gravatar.available || !verified);
    this._$("gravatar-note").textContent = !result.gravatar.available
      ? "Needs a person linked to this user. Ask an admin to link one in Settings > People."
      : !verified ? "Needs a verified email. Verify the email above first."
      : "Uses the email above. Turning it off puts your old picture back.";
  }

  _status(text, isError = false) {
    const el = this.shadowRoot.querySelector(".status");
    el.textContent = text;
    el.classList.toggle("error", isError);
  }
}

customElements.define("user-directory-panel", UserDirectoryPanel);
