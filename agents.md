# Agent notes

## Conventions

- Docs for people stay minimal (README). Agent/maintainer detail lives here.
- Code comments: one or two lines max; point here for anything longer.
- Layout, CI and test setup mirror `pasta-up/ha-gravatar-sync`.

## Design

- Custom integration (domain `profile_extender`), distributed via HACS/Marketplace.
  Not a core candidate: core only accepts integrations for a device or service.
- HA's built-in profile page can't be extended by integrations without patching the
  frontend, so the UI is a separate sidebar panel (`panel_custom`, `require_admin=False`)
  at `/contact-info`. JS is a plain web component in `frontend/`, no build step,
  styled with HA theme CSS variables rather than HA's internal elements (those rename often).
- Single config entry; nothing to configure.
- Data: `.storage/profile_extender.contacts`, `{user_id: {email, phone, github}}`,
  saved with `private=True`. Empty fields are not stored; an empty contact drops the user key.
- Cleanup: `user_removed` event deletes that user's data (only while loaded);
  `async_remove_entry` deletes the file.

## Access control

All enforced server-side in `websocket.py`:

| Command | Who |
| --- | --- |
| `profile_extender/contact/get` `{user_id?}` | self; admin for others |
| `profile_extender/contact/update` `{user_id?, email?, phone?, github?}` | self; admin for others |
| `profile_extender/contact/list` | admin |

`update` replaces the whole contact: omitted fields are cleared. Errors:
`unauthorized`, `not_found` (admin + unknown user), `invalid_format`, `not_loaded`.
The panel lists users via core `config/auth/list` (admin only).

## Validation (`store.py`)

- email: `x@y.z`, no spaces, <= 254 chars. Not verified.
- phone: digits, spaces, `()-.`, optional leading `+`; 7-15 digits.
- github: GitHub username rules; leading `@` stripped.

## Testing

Needs Python 3.14 (HA 2026.10). `home-assistant-frontend` is in
`requirements_test.txt` because `frontend` is a dependency. Run on the sandbox:
`uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt && .venv/bin/pytest`.

## Not done yet

- No GitHub release; not submitted to `hacs/default`.
- Not tested on a live HA instance (panel UI untested in a browser).
- Contact info isn't exposed to automations/notify yet (possible next step:
  admin-only action returning contacts, or person-entity attributes).
