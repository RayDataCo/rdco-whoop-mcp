# Privacy Policy — rdco-whoop-mcp

**Effective date:** 2026-05-10
**Maintainer:** Ray Data Co (Ben Wilson)
**Repository:** https://github.com/RayDataCo/rdco-whoop-mcp

## Summary in one paragraph

`rdco-whoop-mcp` is a local-only Model Context Protocol (MCP) server that runs on YOUR machine and reads YOUR Whoop data via Whoop's official API. The maintainer does not collect, receive, store, transmit, or have any access to your Whoop data, your OAuth tokens, your API usage, or any other information about you. The only network traffic is from your machine to `api.whoop.com` over TLS, exactly the same connection the Whoop mobile app makes. If you trust your machine and you trust Whoop's API, no additional trust is required.

## What data is collected by the maintainer

**None.**

The maintainer (Ray Data Co / Ben Wilson) operates no servers, no analytics, no telemetry, no error reporting, no usage tracking, and no third-party integrations associated with this software. There is no account to create, no login to perform with the maintainer, and no credentials shared with the maintainer at any point.

## What data is processed locally on your machine

When you install and configure this MCP, the following data is processed entirely on your local machine and never leaves it except to communicate with `api.whoop.com`:

| Data | Where it lives | Why |
|---|---|---|
| Your Whoop OAuth Client ID | First-choice: 1Password CLI vault. Fallback: system keyring (macOS Keychain / Linux Secret Service / Windows Credential Manager). Last-resort fallback: `~/.config/whoop-mcp/credentials.json` with `0o600` file permissions. | Required by the OAuth2 flow to identify your Whoop developer app. |
| Your Whoop OAuth Client Secret | Same as above. | Required by Whoop to authorize token exchange. |
| Your Whoop OAuth refresh token | Same as above. | Allows the MCP to renew access tokens without re-prompting you for browser authorization. |
| Your Whoop API responses (recovery, sleep, strain, workouts, profile) | In-memory only by default. The MCP fetches data on-demand when your AI agent (e.g. Claude Code, Claude Desktop) requests it; the data is returned to your agent and is not persisted by the MCP itself. | Functional. |

**The maintainer cannot decrypt, read, or access any of the above.** The OAuth tokens authenticate your machine to Whoop's servers; they grant no access to the maintainer.

## Network egress

The MCP makes outbound network requests only to:

- `https://api.whoop.com/*` — Whoop's official REST API, same endpoint Whoop's own mobile app uses.
- `https://api.prod.whoop.com/oauth/oauth2/token` — Whoop's OAuth token exchange endpoint, used during the initial setup flow and for periodic token refreshes.

**No requests are made to any servers operated by the maintainer.** No telemetry. No "phone home." No update checks against private servers (updates flow through standard package-manager channels: `uv` / `pip` / `npm` etc., from public registries you already trust).

## Children's data

This software is intended for adults using their own Whoop wearable. Whoop's terms require members to be 18 years or older. The maintainer does not knowingly process data from anyone under 13. If you believe a minor has installed this software, uninstall it; the local credentials file can be deleted at `~/.config/whoop-mcp/credentials.json`, and the corresponding 1Password / keyring entries can be removed manually.

## Third parties

The maintainer shares no data with any third party because the maintainer collects no data.

The MCP integrates with:

- **Whoop, Inc.** — your data is governed by Whoop's own privacy policy at https://www.whoop.com/legal/privacy/. The MCP only retrieves the data you have already agreed to share with Whoop.
- **Your AI agent host** (Claude Code, Claude Desktop, Claude Cowork, or another MCP-compatible client) — the data the MCP returns is passed to your agent of choice, which is governed by that agent's own privacy policy. For Claude products, see https://www.anthropic.com/legal/privacy.

## Cookies and tracking

The MCP is not a web application and does not use cookies, web beacons, or any tracking technology.

## Data retention

The maintainer retains no data, so there is no maintainer-side retention policy.

On your machine, OAuth tokens persist until you remove them (delete the 1Password item, the keyring entry, or the `~/.config/whoop-mcp/` directory). API responses are not persisted by the MCP.

## Your rights

Because the maintainer collects no data, there is no maintainer-side data-subject access request, deletion request, or opt-out to honor.

For your data held by Whoop, exercise your rights through Whoop directly (https://www.whoop.com/legal/privacy/).

For your data held by your AI agent host, exercise your rights through that host directly.

## Security

The MCP uses TLS 1.2+ for all communication with Whoop's API (this is enforced by Whoop's servers). The OAuth flow uses the standard authorization-code-with-PKCE pattern recommended by Whoop. Token storage prefers system-keyring or 1Password over plain-file storage; if plain-file storage is used, the file is restricted to user-only read/write permissions.

The MCP source code is open and auditable. Pinned dependencies and reproducible builds are enforced via `pyproject.toml` lockfiles.

## Changes to this policy

Material changes to this policy will be committed to the repository's `PRIVACY.md` file with a corresponding version-control history. The "Effective date" at the top of this document will be updated. Users tracking the repository will receive notifications of changes through standard GitHub mechanisms (releases, watch, etc.).

## Contact

For privacy questions, security concerns, or to report a bug:

- File an issue: https://github.com/RayDataCo/rdco-whoop-mcp/issues
- Maintainer: Ben Wilson, Ray Data Co (ben@raydata.co)

## Jurisdiction

The maintainer is a US company. This software is provided as open-source under the LICENSE specified in the repository. Use of this software does not establish a service relationship with the maintainer.
