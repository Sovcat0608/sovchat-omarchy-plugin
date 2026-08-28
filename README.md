# SovChat for Omarchy

An Omarchy Quattro shell companion for SovChat. It adds a theme-aware bar widget and popup panel without embedding the Electron app inside the long-running shell process.

## What it does

- Shows whether the local SovChat desktop client is running, installed, or missing.
- Opens the panel with a left click, launches or focuses the client with a right click, and opens the web app with a middle click.
- Provides native Omarchy actions for the desktop client and web app.
- Restores a client sent to Omarchy's scratchpad when it is launched or focused again.
- Can install the reviewed x64 AppImage snapshot into `~/.local/opt/sovchat/` after verifying its pinned size and SHA-512 checksum.
- Follows the active Omarchy popup palette, typography, spacing, borders, and bar geometry.

The plugin does not read SovChat sessions, browser storage, Electron data, account credentials, or voice tokens.

## Requirements

- Omarchy with Quattro shell plugin support.
- An x86-64 Linux system for the optional AppImage installer.
- `curl` and standard GNU userland tools, which are present on a normal Omarchy installation.
- FUSE 2 for AppImage mounting. If needed, install it once with `omarchy pkg add fuse2`.

The web-app action works without a desktop client.

## Install

Install and enable the plugin directly from its public repository:

```bash
omarchy plugin add https://github.com/Sovcat0608/sovchat-omarchy-plugin.git --enable
```

## Install from a development checkout

Run this on the Omarchy PC, using the actual path to this directory:

```bash
omarchy plugin add /path/to/sovchat/variants/omarchy-plugin --enable
```

Omarchy copies the plugin to `~/.config/omarchy/plugins/com.sovchat.omarchy/`, validates the manifest, and enables the bar widget. It does not execute an install hook or request root access.

For development without installing the checkout, set `SOVCHAT_OMARCHY_PLUGIN_DIR` to this directory before restarting the shell.

## Remove

```bash
omarchy plugin remove com.sovchat.omarchy
```

Removal deletes the copied plugin directory only. The optional SovChat desktop client remains installed until the user removes it separately.

## Client discovery

The widget automatically checks the standard SovChat install target, command path, `~/Applications`, `~/Downloads`, and common extracted-archive locations. A custom absolute executable can be set in the Omarchy bar settings for the SovChat widget.

The optional installer is deliberately user initiated. Its immutable AppImage URL, exact byte size, and SHA-512 digest are pinned in the reviewed plugin source. It refuses redirects, enforces strict connection and overall timeouts, caps the download at 256 MiB, verifies the effective URL, and installs only inside the current user's home directory. A newer client requires a reviewed plugin update. The installer never calls `sudo` or a package manager.

On Omarchy, SovChat's title-bar minimise button follows the native scratchpad convention. Launching or focusing SovChat from the plugin moves it back to the active workspace. On another Linux desktop, the client falls back to hiding the window and can be reopened from the desktop launcher.

## Validate

On Omarchy:

```bash
omarchy plugin validate .
qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml Panel.qml
```

From the SovChat repository on any supported development machine:

```bash
npm run test:omarchy-plugin
npm run pack:omarchy-plugin
```

The package command creates a standalone archive with `manifest.json` at its root. The public plugin repository contains this directory as its root so Omarchy can install it directly from git.

## Security boundary

Omarchy shell plugins run unsandboxed in the long-lived `omarchy-shell` process. This plugin keeps that surface intentionally narrow:

- QML runs only the bundled helper and fixed Omarchy launch commands.
- The helper accepts only `status`, `launch`, and `install` actions.
- No credentials or secrets are read or written.
- The installer accepts only the exact reviewed HTTPS URL and refuses redirects.
- The downloaded client is installed only after its byte size and pinned SHA-512 checksum match the reviewed release.
