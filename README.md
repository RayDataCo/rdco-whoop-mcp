# whoop-mcp

**Your Whoop data, in your agent's hands. Local-only. No middleware. You own the keys.**

A local Model Context Protocol (MCP) server that exposes your personal Whoop API v2 data to Claude Code, Claude Desktop, or any MCP-compatible client. Read-only. Runs entirely on your machine. The author has no access to your data, your tokens, or your API usage.

## v0.0.2 changelog

- Added `whoop_get_body_measurements` tool for historical body-composition data (height, weight, max heart rate).
- Made the 1Password vault and item names configurable via `WHOOP_MCP_OP_VAULT` and `WHOOP_MCP_OP_ITEM` env vars (default: `Personal` / `whoop-mcp`).
- Investigated `whoop_get_journal_entries`: the v1 `/v1/user/journal_entry` endpoint is **not present in Whoop API v2**. Whoop's v1-to-v2 migration guide and changelog do not mention journal data. The tool is intentionally not shipped in v0.0.2; we will revisit if Whoop adds it back. See "Journal entries" below.

## What it does

Six read tools, all returning JSON:

| Tool | Returns |
|---|---|
| `whoop_get_recovery` | HRV, RHR, recovery score, sleep_id, cycle_id |
| `whoop_get_sleep` | sleep stages, efficiency, debt, performance |
| `whoop_get_strain` | day strain, max HR, average HR, calories |
| `whoop_get_workouts` | sport, duration, strain, calories |
| `whoop_get_profile` | name, member-since, height, weight, baseline metrics |
| `whoop_get_body_measurements` | historical height, weight, max heart rate (date range) |

All date-range tools accept `start_date` and `end_date` as ISO `YYYY-MM-DD`.

## Quickstart for Claude Code

```bash
# 1. Install the package + run the OAuth wizard (~10 minutes, mostly the developer.whoop.com app creation)
uvx --from rdco-whoop-mcp whoop-mcp-setup

# 2. Register the MCP with Claude Code
claude mcp add whoop -- uvx --from rdco-whoop-mcp whoop-mcp-server

# 3. Verify
claude mcp list
```

Then ask Claude: *"Pull my last 30 days of recovery from Whoop and tell me the trend."*

## Quickstart for Claude Desktop

A single-click DXT bundle is on the Phase 1 roadmap. For now, Desktop users can install via the same Python path:

```bash
uvx --from rdco-whoop-mcp whoop-mcp-setup
```

Then add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "whoop": {
      "command": "uvx",
      "args": ["--from", "rdco-whoop-mcp", "whoop-mcp-server"]
    }
  }
}
```

## Bring your own keys

You create your own OAuth app at developer.whoop.com. The author of this MCP never sees your credentials.

1. Go to <https://developer.whoop.com/> and sign in with your Whoop account.
2. Create a new app. Any name works (e.g. `personal-mcp`).
3. **Redirect URI:** `http://127.0.0.1:53682/callback` (must match exactly). Port 53682 follows the gcloud/Stripe-CLI convention - uncommon enough to rarely collide with local dev tools (unlike 8080, which is heavily used by Tomcat, dev servers, etc.). If 53682 is in use on your machine, set `WHOOP_MCP_REDIRECT_PORT` env var to a free port and ALSO add `http://127.0.0.1:<your-port>/callback` to your Whoop OAuth app's redirect URI list (Whoop allows multiple).
4. **Scopes:** `read:recovery`, `read:cycles`, `read:sleep`, `read:workout`, `read:profile`, `read:body_measurement`, `offline`.
5. Save, then copy the **Client ID** and **Client Secret**.
6. Run `uvx --from rdco-whoop-mcp whoop-mcp-setup` and paste them when prompted.

The wizard launches your browser, captures the OAuth callback on localhost, exchanges the code for tokens, and stores everything in the most secure backend it can find on your system (see Privacy below).

> Screenshots placeholder: TODO add walkthrough images for the developer.whoop.com app form once Phase 0.6 ships.

## Privacy

This MCP runs entirely on your machine. The only network egress is **YOUR machine to api.whoop.com**, fetching **YOUR data**. The author of this package has no access to your data, your tokens, or your API usage.

**Credential storage** is tiered. The wizard picks the strongest backend available:

1. **1Password CLI** (`op`). If `op` is installed and signed in, credentials live in your `Personal` vault under the `whoop-mcp` item by default. Nothing on disk. Override the vault and item names with the env vars below if your 1Password layout uses different names.
2. **System keyring** (macOS Keychain, Linux secret-service, Windows Credential Manager) via the `keyring` Python library.
3. **Fallback file** at `~/.config/whoop-mcp/credentials.json` with `0700` directory and `0600` file permissions. The wizard prints a warning when this fallback is used and recommends installing 1Password CLI or a system keyring.

**1Password env-var overrides** (only relevant when using the 1Password backend):

| Env var | Default | Purpose |
|---|---|---|
| `WHOOP_MCP_OP_VAULT` | `Personal` | Name of the 1Password vault to read/write credentials in. Useful if your account uses `Private`, a shared vault, or a per-project vault. |
| `WHOOP_MCP_OP_ITEM` | `whoop-mcp` | Name of the 1Password item that holds the credential fields. Override if you want to namespace by user or environment. |

Set them in the same shell that runs `whoop-mcp-setup` and `whoop-mcp-server` (e.g. add `export WHOOP_MCP_OP_VAULT=Private` to your shell profile, or set them in your MCP client's env block).

You can rotate or revoke at any time:
- Revoke the OAuth grant in your Whoop account settings.
- Delete the keyring entry / file / 1Password item.
- Re-run the setup wizard.

## Journal entries

Whoop API v1 used to expose journal entries (alcohol, caffeine, supplements, mood) via `/v1/user/journal_entry`. As of the v2 API surface documented at <https://developer.whoop.com/api/>, that endpoint is **not present**. Neither the v1-to-v2 migration guide nor the public changelog mentions journal data. Until Whoop publishes a v2 equivalent, this MCP does not expose a `whoop_get_journal_entries` tool. If you spot a re-introduction, file an issue and we will wire it up.

## Development

```bash
git clone <this-repo>
cd rdco-whoop-mcp
uv sync --extra dev
pytest                                  # unit tests only
WHOOP_INTEGRATION_TEST=1 pytest -s     # hits the live Whoop API
```

## License

MIT. See `LICENSE`.

> Recommendation to founder: stick with **MIT**. It is the lowest-friction license for a personal-data MCP that you want others to clone, fork, and self-host. Apache 2.0's patent grant matters more for company-backed open source; MIT is plenty for solo-shipped tooling.

## Roadmap

- **Phase 0** (this release): OAuth + 5 read tools + smoke test path.
- **Phase 1**: DXT bundle for Claude Desktop, write endpoints (notes/tags), coaching skills, multi-user packaging.
