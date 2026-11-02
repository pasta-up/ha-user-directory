# Agent notes

## Conventions

- Docs for people stay minimal (README). Agent/maintainer detail lives here.
- Code comments: one or two lines max; point here for anything longer.
- Layout, CI and test setup mirror `pasta-up/ha-gravatar-sync`.

## Naming

Repo `pasta-up/ha-user-directory` (renamed from ha-profile-extender, v0.1.x).
Domain `user_directory`. Admin-facing name (manifest, hacs.json, config entry title,
options dialog) is "ha-user-directory"; user-facing sidebar/page is "User-Directory".
The domain change means installs from ha-profile-extender must be removed and re-added;
no data migration (owner's decision).

## Design

- Custom integration (domain `user_directory`), distributed via HACS/Marketplace as a
  custom repository. Not a core candidate: core only accepts integrations for a device or service.
- HA's built-in profile page can't be extended by integrations without patching the
  frontend, so the UI is a separate sidebar panel "User-Directory"
  (`panel_custom`, `require_admin=False`) at `/user-directory`. JS is a plain web
  component in `frontend/`, no build step, styled with HA theme CSS variables rather
  than HA's internal elements (those rename often).
- Single config entry. Options flow (admin-only by HA design) is a menu: Directory
  (publish policy), Single sign-on, Email verification (SMTP). Each step saves its own
  keys on top of the others.
- Data, all `private=True`:
  - `.storage/user_directory.contacts`: `{user_id: {email?, phone?, github?}}` users/admins entered.
  - `.storage/user_directory.oidc`: same shape, last values fetched from SSO.
    Kept apart so toggling enforcement never loses user input.
  - `.storage/user_directory.settings`: `{user_id: {listed: bool, shared: [social fields]}}`.
  - `.storage/user_directory.verified`: `{user_id: casefolded email they proved they own}`.
- Cleanup: `user_removed` deletes that user everywhere (only while loaded);
  `async_remove_entry` deletes all files; turning SSO off deletes the SSO file and token.

## Directory (`directory.py`)

- Policy (`publish_policy` option): `choice` (default; users opt in, unlisted until then),
  `oidc` (users with an `auth_oidc` credential always listed, others choose),
  `all` (everyone listed). Forced users can't set `listed: false` (`listed_locked` error).
- Listed users show name, person `entity_picture` (any person linked by `user_id`,
  YAML ones included), email, phone. `SOCIAL_FIELDS` (GitHub) only if in `shared`.
  Filtering is server-side; hidden fields never reach other users' browsers.
- System-generated and inactive users never appear.
- Clicking an entry downloads a vCard 3.0 built client-side (no photo).
  Add a social: add to `CONTACT_FIELDS`/`SOCIAL_FIELDS`, `clean_contact` validation,
  the panel's `FIELDS` (with `social: true`) and the vCard builder.

## Access control

All enforced server-side in `websocket.py`:

| Command | Who |
| --- | --- |
| `user_directory/contact/get` `{user_id?}` | self; admin for others |
| `user_directory/contact/update` `{user_id?, email?, phone?, github?, listed?, shared?}` | self; admin for others |
| `user_directory/gravatar/set` `{user_id?, enabled}` | self; admin for others |
| `user_directory/email/send_code` `{user_id?}` | self; admin for others |
| `user_directory/email/confirm` `{user_id?, code}` | self; admin for others |
| `user_directory/contact/list` | admin (full, unfiltered) |
| `user_directory/directory/list` | any user (filtered by policy and sharing) |

get/update/send_code/confirm return `{contact, sso, locked, gravatar: {enabled, available},
email_verification: {available, verified, pending}, listed, listed_locked, shared}`. `listed`/`shared` omitted in update = unchanged.
`update` replaces the whole manual contact: omitted fields are cleared. Values equal to
the SSO value aren't stored, so later SSO changes still show. Errors: `unauthorized`,
`not_found` (admin + unknown user), `invalid_format`, `field_locked`, `listed_locked`,
`not_loaded`.
The panel lists users via core `config/auth/list` (admin only).

## SSO

Only combination supported: hass-oidc-auth (`auth_oidc`) + Authentik. Only email is synced
(Authentik has no standard phone/GitHub field).

- hass-oidc-auth v1.2.1 drops the email claim and stores only
  `credential.data["sub"] = sha256("<issuer>.<sub>")`, so we query Authentik ourselves.
- "Active" check: `hass.auth.get_auth_providers("auth_oidc")` non-empty (public API;
  stays true until restart after removal, since auth_oidc can't unload).
- Discovery URL: auth_oidc config entry `data["discovery_url"]`, else
  `hass.data["auth_oidc"]["yaml_config"]["discovery_url"]` (their internals; if it
  moves we report `provider_not_active`). Discovery doc gives `issuer`; Authentik API is
  `<issuer before /application/o/>/api/v3`. Non-Authentik issuer -> `unsupported_idp`.
- Token: Authentik service account API token with only "view user". Stored in entry
  options (plain text, like all HA storage). Checked on save via `core/users/?page_size=1`.
- Matching: for each Authentik user, hash `issuer.<candidate>` for uid, pk, username,
  email (covers every Authentik subject mode, default first) and compare to HA credentials.
- Sync: at setup, hourly, and on `user_added` (first SSO login creates the user).
  Failures keep the last cached values. If the cache is empty, nothing is locked.
- Merge: enforce off -> manual wins, SSO fills gaps. Enforce on -> SSO wins and those
  fields are locked for everyone, admins included (they'd be overwritten on next sync).
- Uses HA's default aiohttp session: ignores auth_oidc's `network.tls_verify`/CA settings,
  so Authentik needs a publicly trusted cert (or one HA already trusts).

## Gravatar

Replaces the retired `pasta-up/ha-gravatar-sync` (code in `gravatar.py` is ported from it).

- HA shows a user's avatar from their linked person, so we set the picture of the
  UI-managed person whose `user_id` matches. YAML persons can't be changed (`no_person`).
- Email = the effective contact email (manual or SSO), and it must be verified (see
  "Email verification"). Gravatar gets only its SHA-256 hash.
- `user_directory/gravatar/set {user_id?, enabled}`: same owner-or-admin rule. Enabling
  fetches immediately; errors `no_person`, `no_email`, `not_verified`, `no_gravatar`,
  `cannot_connect`.
- Avatar cached in `.storage/user_directory/avatars/<user_id>` and served by
  `AvatarView` at `/api/user_directory/avatar/<user_id>?v=<digest>` **without auth**:
  browsers load person pictures with plain `<img>`, like core's `/api/image/serve`.
  Only images already public on Gravatar are served.
- `.storage/user_directory.gravatar`: `{user_id: {email, original_picture}}`.
  Off/removal restores `original_picture` only if the picture is still ours.
- Refresh: every 6h (forced); after contact updates and SSO syncs, only users whose
  email changed, and once at setup. No verified email -> Gravatar turned off (so after
  upgrading to 0.3.0, existing users lose it until they verify). Unreachable/404 keeps
  the last avatar.
- `hass.data["person"]` is a tuple up to 2026.11 and a dataclass later;
  `person_collection` handles both.

## Email verification (`verify.py`, `mail.py`)

- Optional. Admin sets SMTP (server, STARTTLS/SSL/none, port, login, from) under
  Configure > Email verification; saving tests connect + login. Blank password keeps
  the saved one; blank server removes all SMTP options. Password is plain text in options.
- "Send a test email" menu item (only once SMTP is saved) sends with the saved settings.
  Recipient defaults to the admin's own contact email, found via `current_request`
  (options flows don't record the user; core's Plex flow does the same). Failures show
  the SMTP server's message, since only admins see it.
- `send_code` emails a 6-digit code (`secrets`) to the *saved* email; `confirm` checks it
  (`hmac.compare_digest`). Codes are in memory only: 15 min, 5 guesses, 1 min before
  resending to the same address, 5 codes per user per hour.
- Verified = stored casefolded address matches the current email, so changing the email
  unverifies it and changing back re-verifies. SSO-provided emails (value equals the SSO
  value) count as verified without a code: the IdP vouches for them.
- Errors: `not_configured`, `no_email`, `already_verified`, `too_soon`, `too_many_codes`,
  `send_failed` (SMTP cause logged), `no_code` (none, expired, or email changed),
  `wrong_code`, `too_many_attempts`.
- Directory entries carry `email_verified`; the panel shows a check mark.
- Tests patch `mail.smtplib.SMTP` (conftest `smtp`) and read the code from the sent message.

## Validation (`store.py`)

- email: `x@y.z`, no spaces, <= 254 chars. Ownership is checked separately (above).
- phone: digits, spaces, `()-.`, optional leading `+`; 7-15 digits.
- github: GitHub username rules; leading `@` stripped.

## Testing

Needs Python 3.14 (HA 2026.10). `home-assistant-frontend` is in
`requirements_test.txt` because `frontend` is a dependency. Run on the sandbox:
`uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt && .venv/bin/pytest`.
SSO tests fake auth_oidc by inserting into `hass.auth._providers` and mock Authentik
with `aioclient_mock`.

## Releases

HACS offers updates from GitHub releases, comparing the tag with the installed
`manifest.json` version. To release:

1. Bump `version` in `manifest.json` (semver), commit, push, wait for CI.
2. `gh release create vX.Y.Z --title vX.Y.Z --notes "..."`. Notes are shown in HA's update dialog.
3. `release.yml` fails if the tag and manifest version differ; fix and re-release.

## Not done yet

- Do not submit to `hacs/default`: the owner wants it installed as a custom repository only.
- Not tested on a live HA instance (panel UI and real Authentik untested).
- Contact info isn't exposed to automations/notify yet (possible next step:
  admin-only action returning contacts, or person-entity attributes).
