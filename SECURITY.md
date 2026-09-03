# Security

## Supported versions

| Component | Supported version |
| --- | --- |
| Omarchy plugin | 0.1.4 |
| SovChat Omarchy client | 0.4.7 |

Security updates are delivered through a new reviewed plugin snapshot or the
dedicated Omarchy client update feed.

## Trust boundary

Omarchy shell plugins run unsandboxed in the long-lived shell process. This
plugin keeps that surface intentionally narrow:

- QML invokes only the bundled `bin/sovchat-control` helper and fixed Omarchy
  launch commands.
- The helper accepts only `status`, `status-v2`, `launch`, and `install`.
- The plugin does not read SovChat credentials, browser storage, voice tokens,
  room messages, or sessions.
- Client installation is an explicit user action.
- No service is installed and no administrator privilege is requested.

## Installation controls

The installer accepts only the reviewed versioned AppImage URL. Before
publication it verifies:

- an exact byte count of `129110268` bytes;
- SHA-512
  `48540f5f2f0882990dd6e1ccc5f8eb7c2c60efe65f14a426e40593561e3ff82d3a36f8184f8a4007cf37ecc3cee1e6180a255f83a222eb3792c18b3aae7aa229`;
- HTTPS without redirects;
- strict connection, overall, stall, and 256 MiB transfer limits;
- descriptor-pinned destination directories with symlink protection;
- atomic, fail-closed publication when a path changes concurrently.

The helper installs only beneath these user-owned paths:

- `~/.local/opt/sovchat-omarchy`
- `~/.local/share/applications/com.sovchat.omarchy.desktop`
- `~/.local/share/icons/hicolor/scalable/apps/com.sovchat.omarchy.svg`

It never removes or overwrites the standalone Linux client.

## Network boundary

The installed client connects to:

- `https://sovchat.com` for the application and Omarchy update feed;
- `wss://livekit.sovchat.com` for real-time room media.

The bar widget itself performs local status checks and launches the reviewed
helper. It does not handle account credentials or room tokens.

## Reporting a vulnerability

Please email [info@sovchat.com](mailto:info@sovchat.com) with the subject
`SovChat Omarchy security report`. Include affected versions, reproduction
steps, and impact. Avoid including credentials, room tokens, private messages,
or other users' data.

Please allow time for investigation before public disclosure.
