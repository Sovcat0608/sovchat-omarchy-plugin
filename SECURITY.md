# Security

## Native release boundary

Version 0.2.0 replaces the 0.1.x launcher. It is an early native release, not a
security-audited or fully media-accepted build. Previous marketplace verification
of launcher 0.1.6 does not cover this implementation.

Omarchy plugins run unsandboxed in the desktop shell. The QML interface now
handles account/session state, room messages and media controls. A Python helper
uses private inherited pipes for commands and session responses; this is not an
OS sandbox against another plugin or software running as your user.

The helper uses the existing SovChat HTTPS API for authentication, accounts and
rooms, and LiveKit for real-time media. Credentials are never put in command-line
arguments. Remember me is opt-in and requires an unlocked Secret Service; no
plaintext token file fallback is provided. Explicit sign-out clears local state,
stops media, revokes the server session and checks that the old bearer is rejected.
Offline or forcibly terminated processes cannot guarantee server revocation.

## Explicit installation

`setup.py` must be run deliberately as the desktop user. It downloads six exact
hash-locked Python wheels, builds the bundled Qt video bridge against host Qt and
selects the private runtime only after validation. It never installs system
packages, requests sudo, or runs automatically when the panel opens. An offline
wheelhouse is supported and is subject to the same hashes. See `runtime/requirements.lock`
and the README for platform requirements and retained runtime rollback data.

The native source package contains no AppImage, Electron client, host-specific
binary, backend, account data or VM data. Old desktop installations are not removed.
Rolling back the dependency runtime does not roll back the plugin source.

## Media and network access

Screen/window capture uses the desktop portal and PipeWire. Application audio
requires explicit selection of a playing application; the native SovChat output
and whole speaker mix are excluded. Source links are checked and source loss
fails closed. LiveKit, GStreamer and a small native Qt video module process media.
Component tests are not proof of end-to-end media or physical-device quality.

Account and room traffic uses the shared SovChat service at `https://sovchat.com`;
real-time media uses the configured SovChat LiveKit service. Google sign-in opens
the system browser and uses a temporary nonce-checked loopback callback. Release
checks use the public GitHub API for `Sovcat0608/sovchat-omarchy-plugin`, without
an account bearer token. They notify only: no update is downloaded or executed.

## Reporting a vulnerability

Email [info@sovchat.com](mailto:info@sovchat.com) with the subject
`SovChat Omarchy security report`, affected version, reproduction steps and impact.
Do not include passwords, bearer tokens, private messages or other users' data.
Please allow time for investigation before public disclosure.
