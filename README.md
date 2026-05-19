# chrome-profile

> Deterministic per-profile Chrome control for AI agents driving the browser through [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp).

An [Agent Skill](https://agentskills.io) that lets you tell an AI agent **"open this URL in my work profile"** and have it actually land in the right profile — addressed by Google account email, not by brittle `Profile 17`-style directory numbers. Works on macOS, Linux, Windows. One Chrome process. Real cookies, real fingerprint, real you.

## How it works

`chrome-devtools-mcp` sees every tab across every Chrome profile as one flat list, with no profile labels. This skill bridges the gap:

1. The CLI uses Chrome's native `--profile-directory` IPC to ask your running Chrome to open a URL in a specific profile.
2. It appends a `#cdp-profile=<key>` fragment to the URL so the agent can locate the new tab unambiguously via `list_pages`.
3. Profile keys map to **emails** (or display-name substrings) and resolve to the local `Profile XX` dir at every call by reading `Local State` — so the same config works on any machine.

Full architecture: [`references/architecture.md`](references/architecture.md).

## Prerequisites

| Required | Check with |
|---|---|
| Google Chrome stable, version 144+ | `chrome --version` |
| Python 3.9+ on PATH | `python3 --version` |
| Node.js + `npx` on PATH | `npx --version` |
| `chrome-devtools-mcp` configured in your agent (Claude Code / Codex / Cursor / etc.) | see below |
| `~/.local/bin` (Unix) or `%USERPROFILE%\.local\bin` (Windows) on PATH | or set `PREFIX=...` |

The skill does NOT bundle Chrome, manage `chrome-devtools-mcp`, or touch profile data.

### Set up `chrome-devtools-mcp` in your agent

**Claude Code:**
```bash
claude mcp add -s user chrome-devtools npx -- chrome-devtools-mcp@latest --autoConnect --channel=stable
```

**Codex CLI:**
```bash
codex mcp add chrome-devtools -- npx chrome-devtools-mcp@latest --autoConnect --channel=stable
```

**Cursor / other clients** — equivalent JSON in `mcp.json`:
```json
{ "mcpServers": { "chrome-devtools": {
  "command": "npx",
  "args": ["chrome-devtools-mcp@latest", "--autoConnect", "--channel=stable"]
}}}
```

`--autoConnect` needs two one-time gates from you:

1. In Chrome, open `chrome://inspect/#remote-debugging` and toggle the remote-debugging server on. Without this the MCP has nothing to attach to.
2. The first agent call to `chrome-devtools-mcp` triggers a Chrome **"Allow remote debugging"** prompt. Click **Allow** (or **Always Allow** for persistence).

> Alternative: explicit `--browserUrl http://127.0.0.1:9222` against a Chrome you launched with `--remote-debugging-port=9222 --user-data-dir=<non-default>`. Chrome 136+ blocks `--remote-debugging-port` against the default user-data-dir, so `--autoConnect` is smoother for everyday use.

## Install

```bash
# Recommended
npx skills add kaitranntt/chrome-profile

# Install the CLI shim onto PATH
bash ~/.claude/skills/chrome-profile/scripts/install.sh                    # macOS / Linux
"%USERPROFILE%\.agents\skills\chrome-profile\scripts\install.cmd"          :: Windows
```

Manual: `git clone https://github.com/kaitranntt/chrome-profile ~/.claude/skills/chrome-profile && bash ~/.claude/skills/chrome-profile/scripts/install.sh`.

## Use

```bash
chrome-profile discover            # list all Chrome profiles on this machine
chrome-profile setup               # interactive: pick keys, write profiles.json
chrome-profile setup --yes         # non-interactive: auto-derive all keys
chrome-profile list                # show keys and what they resolve to here
chrome-profile <key> <url>         # open URL in the profile named <key>
```

Once a tab is open via `chrome-profile <key> <url>`, your agent finds and drives it:

```text
1. list_pages → match the tab whose URL contains "cdp-profile=<key>"
2. select_page on that pageId
3. evaluate_script / navigate_page / click — all in that profile's CDP context,
   with that profile's cookies, logins, and extensions.
```

## Config

`profiles.json` lookup order (first found wins):

1. `$XDG_CONFIG_HOME/chrome-profile/profiles.json` *(default for `setup`; survives `npx skills update`)*
2. `<skill-dir>/profiles.json` *(only via `setup --shared`; wiped by `npx skills update` — don't use this unless you fork the repo)*

```json
{
  "profiles": {
    "personal": { "email": "you@gmail.com" },
    "work":     { "email": "you@work-company.com" },
    "research": { "name_contains": "Research" }
  }
}
```

Spec types, in priority order:

| Spec | Use when | Portable? |
|---|---|---|
| `{"email": "x@y.z"}` | Profile has a Google account signed in | ✅ |
| `{"name_contains": "substring"}` | Profile has a distinctive display name | ✅ |
| `{"dir": "Profile 17"}` | Last-resort escape hatch | ❌ |

`Profile XX` directory numbers are assigned per-machine in creation order; addressing by email/name lets the same config work everywhere. Sign into a missing account on a new machine, re-run `chrome-profile list`, key resolves automatically.

## Update / Uninstall

```bash
# Update
npx skills update chrome-profile                                           # skill files
bash ~/.claude/skills/chrome-profile/scripts/install.sh                    # CLI shim (idempotent)

# Uninstall
bash ~/.claude/skills/chrome-profile/scripts/uninstall.sh [--purge]        # remove shim (+config if --purge)
npx skills remove chrome-profile                                           # remove skill files
```

Windows: substitute `*.cmd` and `/purge`. `profiles.json` survives updates; `--purge` also removes it.

## Limits

| Limit | Detail |
|---|---|
| Can't pre-pin a profile via MCP config | Profile selection is runtime-only. Use the CLI. |
| MCP `new_page` opens in default profile | Use `chrome-profile <key> <url>` for non-default profiles. |
| Fragment-stripping SPAs | If a JS app overwrites `location.hash`, hold the `pageId` from your first `list_pages` and don't re-match by fragment. |
| Copy-profile workarounds | Don't. macOS Keychain / Windows ABE bind cookie decryption to the original user-data-dir path. See [`references/architecture.md`](references/architecture.md). |

More in [`references/troubleshooting.md`](references/troubleshooting.md).

## Development

```bash
pytest                              # 22 tests, no third-party deps
npx skills-ref validate ./SKILL.md  # optional metadata check
```

## License

MIT. See [`LICENSE`](LICENSE).

## Security

The skill executes only `chrome.exe` / `Google Chrome`, reads `Local State` once for profile enumeration, and writes a `profiles.json` you control. It does not touch cookies, passwords, or network. URLs are passed verbatim to Chrome; agents should verify any URL from untrusted upstream before running. Report issues via GitHub Security Advisories.
