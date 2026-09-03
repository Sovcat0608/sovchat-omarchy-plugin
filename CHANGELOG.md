# Changelog

All notable changes to the SovChat Omarchy plugin are documented here.

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
