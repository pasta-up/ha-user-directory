# Agent notes

## Conventions

- Docs for people stay minimal (README). Agent/maintainer detail lives here.
- Code comments: one or two lines max; point here for anything longer.
- Layout, CI and test setup mirror `pasta-up/ha-gravatar-sync`.

## Design

- Custom integration (domain `profile_extender`), distributed via HACS/Marketplace as a
  custom repository. Not a core candidate: core only accepts integrations for a device or service.
- HA's built-in profile page can't be extended by integrations without patching the
  frontend, so the UI is a separate sidebar panel "User Extended Info"
  (`panel_custom`, `require_admin=False`) at `/user-extended-info`. JS is a plain web
  component in `frontend/`, no build step, styled with HA theme CSS variables rather
  than HA's internal elements (those rename often).
- Single config entry. Options flow (admin-only by HA design) holds the SSO settings.
- Data, both `private=True`, `{user_id: {email?, phone?, github?}}`:
  - `.storage/profile_extender.contacts`: what users/admins entered.
  - `.storage/profile_extender.oidc`: last values fetched from SSO.
  Kept apart so toggling enforcement never loses user input.
- Cleanup: `user_removed` deletes that user from both (only while loaded);
  `async_remove_entry` deletes both files; turning SSO off deletes the SSO file and token.

## Access control

All enforced server-side in `websocket.py`:

| Command | Who |
| --- | --- |
| `profile_extender/contact/get` `{user_id?}` | self; admin for others |
| `profile_extender/contact/update` `{user_id?, email?, phone?, github?}` | self; admin for others |
| `profile_extender/contact/list` | admin |

get/update return `{contact, sso: [fields showing SSO values], locked: [fields]}`.
`update` replaces the whole manual contact: omitted fields are cleared. Values equal to
the SSO value aren't stored, so later SSO changes still show. Errors: `unauthorized`,
`not_found` (admin + unknown user), `invalid_format`, `field_locked`, `not_loaded`.
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
- Email = the effective contact email (manual or SSO). Gravatar gets only its SHA-256 hash.
- `profile_extender/gravatar/set {user_id?, enabled}`: same owner-or-admin rule. Enabling
  fetches immediately; errors `no_person`, `no_email`, `no_gravatar`, `cannot_connect`.
- Avatar cached in `.storage/profile_extender/avatars/<user_id>` and served by
  `AvatarView` at `/api/profile_extender/avatar/<user_id>?v=<digest>` **without auth**:
  browsers load person pictures with plain `<img>`, like core's `/api/image/serve`.
  Only images already public on Gravatar are served.
- `.storage/profile_extender.gravatar`: `{user_id: {email, original_picture}}`.
  Off/removal restores `original_picture` only if the picture is still ours.
- Refresh: every 6h (forced); after contact updates and SSO syncs, only users whose
  email changed. Email gone -> Gravatar turned off. Unreachable/404 keeps the last avatar.
- `hass.data["person"]` is a tuple up to 2026.11 and a dataclass later;
  `person_collection` handles both.

## Validation (`store.py`)

- email: `x@y.z`, no spaces, <= 254 chars. Not verified.
- phone: digits, spaces, `()-.`, optional leading `+`; 7-15 digits.
- github: GitHub username rules; leading `@` stripped.

## Testing

Needs Python 3.14 (HA 2026.10). `home-assistant-frontend` is in
`requirements_test.txt` because `frontend` is a dependency. Run on the sandbox:
`uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt && .venv/bin/pytest`.
SSO tests fake auth_oidc by inserting into `hass.auth._providers` and mock Authentik
with `aioclient_mock`.

## Not done yet

- No GitHub release.
- Do not submit to `hacs/default`: the owner wants it installed as a custom repository only.
- Not tested on a live HA instance (panel UI and real Authentik untested).
- Contact info isn't exposed to automations/notify yet (possible next step:
  admin-only action returning contacts, or person-entity attributes).
