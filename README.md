# Profile Extender for Home Assistant

Lets each Home Assistant user add their own email, phone and GitHub username,
and use their [Gravatar](https://gravatar.com) as their profile picture. Everything is optional.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pasta-up&repository=ha-profile-extender&category=integration)

## Install

1. In **Settings** > **Marketplace** (or **HACS**), open the top-right menu > **Custom repositories**.
2. Add `https://github.com/pasta-up/ha-profile-extender` as an **Integration**.
3. Download **Profile Extender** and restart Home Assistant.
4. Go to **Settings** > **Devices & services** > **Add integration** > **Profile Extender**.

Or copy `custom_components/profile_extender` into your config's `custom_components` folder.

## Use

Open **User Extended Info** in the sidebar, fill in what you want, and save.

- Users can only see and change their own info.
- Admins can pick any user from a list at the top.
- Removing a user removes their info. Removing the integration removes everyone's.

## Gravatar

Tick **Use my Gravatar as my profile picture**. Your picture becomes the Gravatar for
your email, and refreshes every 6 hours and whenever the email changes. Untick it to get
your old picture back.

Your user needs a linked person created in the UI (**Settings** > **People**).

## Single sign-on (optional)

If you sign in with [OpenID Connect/SSO](https://github.com/christiaangoossens/hass-oidc-auth)
and Authentik, emails can come from Authentik.

1. In Authentik, create a service account that can only view users, and an API token for it.
2. In Home Assistant, open **Profile Extender** > **Configure**.
3. Turn on **Use SSO contact info** and paste the token.
4. Optionally turn on **Enforce SSO contact info** so SSO emails can only be changed in Authentik.

Emails refresh every hour and when someone signs in with SSO for the first time.

Requires Home Assistant 2026.10 or later.

## License

[MIT](LICENSE)
