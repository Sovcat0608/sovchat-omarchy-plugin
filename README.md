# SovChat for Omarchy

Version `0.2.0` — the first native migration release. Native Quickshell/QML interface, Python
service helper, LiveKit audio and PipeWire/portal screen capture, with a small
native Qt video surface. No Electron, AppImage or embedded browser.

This early native release is available for real Omarchy testing. VM component
checks and live login/chat/logout have passed; two-party native media and physical
microphone quality remain unverified. Read the known limitations before updating.
The prior marketplace verification does not cover this new native implementation.

## Features

Original Linux compact layout and six colour themes; desktop-structured compact
login; shared accounts/rooms; public/private chat, replies, reactions, attachments;
profile/room-owner settings; live roster; microphone/device/processing controls;
per-person/master volume and deafen; AFK controls; native monitor/window sharing,
selected-application audio and expanded viewing; monthly usage details;
plugin-release notifications.

Open signup remains subject to the shared server's 500-account cap and email
verification. Email/password and Google sign-in use the existing shared service.
Google opens the system browser and a temporary nonce-checked loopback callback.
Remember me uses Secret Service only; no plaintext token file is written.

Sign-out clears local/private UI and capture immediately, independently revokes
the server session, and verifies the old token is rejected. Failed revocation has
an explicit retry. Non-remembered sessions are also revoked on graceful helper
exit. Offline/forced exits cannot guarantee server cleanup: use the explicit
other-device disconnect option to recover an already stale session.

## Requirements and explicit setup

Tested on Omarchy 4.0.2 / x86_64, Python 3.14, Qt 6.11.2, GStreamer 1.28.6.
Required host tools: Python with venv/pip, python-gobject, GStreamer base/good and
PipeWire elements, pactl, qmake6, qt6-imageformats, make and g++. The Qt image
formats package supplies the WebP decoder used by desktop-uploaded avatars;
setup refuses to proceed without it. Optional secret-tool plus an
unlocked Secret Service enables Remember me. Setup reports missing prerequisites;
it never installs system packages or uses sudo.

## Install or migrate from launcher 0.1.x

New install (from the upstream repository):

```sh
omarchy plugin add https://github.com/Sovcat0608/sovchat-omarchy-plugin.git --enable
python ~/.config/omarchy/plugins/com.sovchat.omarchy/setup.py
omarchy-restart-shell
```

For an existing launcher install, close its voice/screen session first, then:

```sh
omarchy plugin update com.sovchat.omarchy
python ~/.config/omarchy/plugins/com.sovchat.omarchy/setup.py
omarchy-restart-shell
```

Run setup as your desktop user after installing the listed prerequisites. It
downloads exact hash-locked Python wheels and compiles the Qt bridge locally.
It never installs OS packages. Do not skip setup: the panel can load without the
native media runtime, but voice/screen features will be unavailable. Existing
AppImages, desktop shortcuts, and account data are not deleted or modified.

If you extracted the source ZIP instead, run from its plugin directory:

```sh
python setup.py
```

In the full source repository use `python native-plugin/setup.py` instead.
Setup creates a plugin-owned versioned runtime, verifies exact wheel hashes,
builds the video surface against host Qt, and selects the runtime only after
validation. No code downloads happen when the panel opens. An offline verified
wheel directory can be passed with `--wheelhouse <directory>`.

Reload the Omarchy shell after setup. Stop voice/sharing and sign out first unless
you deliberately use Remember me. `python setup.py --rollback` selects the previous
dependency runtime only; restore plugin source separately if rolling back code.
The old runtime and build directories are retained, not deleted automatically.
After a Qt/Python platform upgrade, rerun setup and revalidate compatibility.

The plugin is an unsandboxed part of your desktop shell: another untrusted plugin
can interfere with the shared process. The private helper boundary is not an OS
sandbox against other software running as your user.

## Known limitations

Actual two-party native LiveKit and physical microphone quality acceptance is
still pending. Portal and audio/video component QA are not a live-call result.
Sharing supports up to 1440p with 15/30/60 FPS choices; Auto uses a 720p cap and
pressure-based frame pacing. High-resolution and live-network performance still
need acceptance. Application audio requires explicitly selecting a playing app;
the native SovChat output and whole speaker mix are excluded. Source links are
verified and source loss fails closed. Stream audio has independent volume/mute.
Device hot-unplug currently requires rejoining. Photos are resized natively before
upload. No Krisp-equivalent denoising claim is made.
See the release notes for verification scope and remaining gates. Do not treat
this release as proof of full desktop parity or microphone-dropout resolution.

## Updates

The checker reads stable releases of `Sovcat0608/sovchat-omarchy-plugin` every
30 minutes and at startup. It shows a desktop notification (when notify-send is
available), bar badge and panel notice. It does not execute updates automatically.

```sh
omarchy plugin update com.sovchat.omarchy
python ~/.config/omarchy/plugins/com.sovchat.omarchy/setup.py
omarchy-restart-shell
```

Launcher 0.1.6 and earlier have no release checker: they need one manual update
to acquire native update pings. Notification delivery requires a running plugin
and successful GitHub access; a published release is not proof every user was
notified. A manually copied VM build is not git-managed.
Native ZIPs contain only source/assets/license, not the legacy desktop client,
credentials or host-specific binaries. Build the Qt module on the target host.

## Removal and rollback

Sign out and leave voice/screen sharing first. Disable or remove the plugin with
Omarchy's plugin manager. Runtime/preferences under `~/.local/share/sovchat-omarchy`
and `~/.config/sovchat-omarchy` are retained; removal does not delete your account.
For a code rollback, restore the prior tagged plugin source (v0.1.6 is the old
launcher) rather than running `setup.py --rollback`, which selects dependencies
only. The old AppImage installation is left available for that rollback.
