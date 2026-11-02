# Profile Extender for Home Assistant

Lets each Home Assistant user add their own email, phone and GitHub username.
All fields are optional.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pasta-up&repository=ha-profile-extender&category=integration)

## Install

1. In **Settings** > **Marketplace** (or **HACS**), open the top-right menu > **Custom repositories**.
2. Add `https://github.com/pasta-up/ha-profile-extender` as an **Integration**.
3. Download **Profile Extender** and restart Home Assistant.
4. Go to **Settings** > **Devices & services** > **Add integration** > **Profile Extender**.

Or copy `custom_components/profile_extender` into your config's `custom_components` folder.

## Use

Open **Contact info** in the sidebar, fill in what you want, and save.

- Users can only see and change their own info.
- Admins can pick any user from a list at the top.
- Removing a user removes their info. Removing the integration removes everyone's.

Requires Home Assistant 2026.10 or later.

## License

[MIT](LICENSE)
