# ha-user-directory for Home Assistant

A phone book of the users on your Home Assistant. Each user can add their email, phone
and GitHub username, choose what's shown, and use their [Gravatar](https://gravatar.com)
as their profile picture.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pasta-up&repository=ha-user-directory&category=integration)

## Install

1. In **Settings** > **Marketplace** (or **HACS**), open the top-right menu > **Custom repositories**.
2. Add `https://github.com/pasta-up/ha-user-directory` as an **Integration**.
3. Download **ha-user-directory** and restart Home Assistant.
4. Go to **Settings** > **Devices & services** > **Add integration** > **ha-user-directory**.

Or copy `custom_components/user_directory` into your config's `custom_components` folder.

Moving from Profile Extender? Remove it first, then install this as above.
Info entered in Profile Extender isn't carried over.

## Use

Open **User-Directory** in the sidebar to see everyone who's listed. Click someone to save
their contact card.

Click **My info** to add your own details:

- **List me in the User-Directory** shows your name, picture, email and phone to all users.
- Social links like GitHub only show if you tick **Show in the directory** next to them.
- Only you and admins can change your info. Admins can pick any user at the top.

Admins choose who's listed under **ha-user-directory** > **Configure** > **Directory**:
users choose for themselves (default), SSO users always, or everyone.

## Email verification (optional)

An admin sets up an SMTP server under **ha-user-directory** > **Configure** >
**Email verification**, then checks it with **Send a test email**. Users can then click **Email me a code** under their email in
**My info** and enter the code to verify it. Verified emails get a ✓ in the directory.
Emails from SSO count as verified.

## Gravatar

In **My info**, tick **Use my Gravatar as my profile picture**. Your picture becomes the Gravatar for
your email, and refreshes every 6 hours and whenever the email changes. Untick it to get
your old picture back.

Your email must be verified first. Changing it to an unverified email turns Gravatar off.

Your user needs a linked person created in the UI (**Settings** > **People**).

## Single sign-on (optional)

If you sign in with [OpenID Connect/SSO](https://github.com/christiaangoossens/hass-oidc-auth)
and Authentik, emails can come from Authentik.

1. In Authentik, create a service account that can only view users, and an API token for it.
2. In Home Assistant, open **ha-user-directory** > **Configure** > **Single sign-on**.
3. Turn on **Use SSO contact info** and paste the token.
4. Optionally turn on **Enforce SSO contact info** so SSO emails can only be changed in Authentik.

Emails refresh every hour and when someone signs in with SSO for the first time.

Requires Home Assistant 2026.10 or later.

## License

[MIT](LICENSE)
