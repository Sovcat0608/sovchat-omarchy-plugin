# Changelog

All notable changes to the SovChat Omarchy plugin are documented here.

## 0.2.0 - 2026-09-11

First native migration release, published for real Omarchy testing. This is a
source-only Quickshell/QML plugin with a Python helper and native Qt video bridge;
the old AppImage launcher, its installer and obsolete preview are retired from
this tree (available in Git history and tag v0.1.6).

- Restores the original compact Linux styling, six themes, desktop-structured
  login and compact room switcher with keyboard/outside-click dismissal.
- Implements shared authentication, rooms, chat, profile/settings, LiveKit voice,
  portal sharing, selected-app audio, native video viewing and usage controls.
- Fixes verified sign-out/relogin and requires the Qt WebP decoder for avatars.
- Adds native release pings, a bar badge and an in-panel update notice.
- Requires explicit `setup.py` after installation/update; no automatic dependency
  installation. See README for commands, prerequisites and rollback boundaries.
- Launcher 0.1.6 and earlier need one manual update to acquire the new checker.

Validation: 93 Python tests (one Linux-only skip on Windows), 16 JavaScript tests
and 13 QML parser checks; prior Omarchy VM component and live login/chat/logout
checks. Real two-party native media, physical microphone dropouts, Google OAuth,
real room switching and high-resolution network performance remain unaccepted.
Device hot-unplug currently requires rejoining. No Krisp-equivalent claim.

The existing marketplace approval is for launcher 0.1.6, not this new native
implementation. The upstream release does not imply marketplace re-verification.

## 0.1.6 - 2026-09-08

### Fixed

- Dynamic panel messages and version labels now render as plain text, preventing
  process output from being interpreted as rich text by the Omarchy shell.
- Security documentation now matches the installer's actual artifact pin, with a
  regression test to prevent future version, size and digest drift.

### Changed

- Pins verified SovChat Omarchy 0.4.9, which removes the extra voice gate that
  could clip quiet words, preserves suppression choices and labels RNNoise accurately.
- Existing Omarchy clients receive 0.4.9 through the dedicated update feed.
- Known capture retry and device-recovery work remains in the client quality plan.

## 0.1.5 - 2026-09-03

### Changed

- SovChat account signup is open while capacity remains; users no longer need
  an access code or a separate Omarchy grant.
- The marketplace preview and quick start now explain the server-enforced
  500-account limit.
- Plugin metadata and the in-panel version label now identify release 0.1.5.

### Security

- The 500-account ceiling is enforced by the SovChat API and database, not by
  this client-side plugin, so the plugin cannot override it.
- The plugin pins the verified Omarchy client v0.4.8 URL, exact byte count,
  and SHA-512 digest. Existing clients discover v0.4.8 through the dedicated
  update feed on launch, hourly, or after resume and unlock.

## 0.1.4 - 2026-09-03

### Added

- A dedicated SovChat Omarchy client lane, App ID, install directory, and
  stable update feed.
- Explicit migration status for plugin 0.1.3 users, with a side-by-side
  **Install Omarchy edition** action that preserves the standalone Linux client.
- A branded marketplace preview, user-first quick start, requirements, limits,
  security reference, and release notes.
- Search alias `screen-share` for marketplace and bar discovery.

### Fixed

- The pinned client is now v0.4.7, whose Omarchy capture flow retains the
  PipeWire/XDG portal source selected by the user instead of enumerating it a
  second time. This fixes monitor or application sharing returning to source
  selection without starting.
- Malformed or partially updated helper responses now fail closed, and actions
  stay disabled while local client status is refreshing.
- Existing Omarchy clients receive update checks shortly after launch, hourly,
  and after resume or unlock.

### Security

- The user-level installer pins the immutable v0.4.7 AppImage URL, exact byte
  count, and SHA-512 digest.
- Legacy-client detection rejects exact-path, symlink, and hardlink attempts to
  launch the standalone client as the Omarchy edition.
- Descriptor-pinned directories, bounded downloads, redirect refusal, and
  atomic publication remain enforced.

## 0.1.3

- Previous marketplace release, which installed the generic standalone Linux
  client.
