# chrome-profile

> Deterministic per-profile Chrome control for AI agents driving the browser through [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp).

An [Agent Skill](https://agentskills.io) that gives your AI agent a missing primitive: **"open this URL in my work profile"** — not "Profile 17" (which differs per machine), not "the profile that happens to have GitHub open" (which is brittle), but the profile bound to a known Google account email. Then the agent finds that tab unambiguously via a URL anchor and drives it through `chrome-devtools-mcp`'s normal tools.

Works on macOS, Linux, and Windows. One Chrome process. No copy-profile hacks. No multi-port multi-MCP gymnastics. Real cookies, real fingerprint, real you.

---

## Why this exists

When `chrome-devtools-mcp` attaches to your real Chrome, it sees the whole browser — every tab in every profile, flat-listed. The Chrome DevTools Protocol exposes `browserContextId` per tab, but the MCP doesn't surface it. So from the agent's view, profiles are invisible.

Two patterns people commonly try, and why they fail:

| Attempt | Failure mode |
|---|---|
| Copy a profile to `/tmp` and launch a separate Chrome | On macOS, cookies are encrypted with a key bound to the original user-data-dir path. Bytes copy fine; decryption fails silently. Logins gone. |
| Spawn N Chrome processes on N debug ports | Works, but abandons your already-signed-in profiles. Re-login per profile. Plus you now run an extra Chrome alongside your daily Chrome. |

This skill takes a different route: **Chromium's `--profile-directory` IPC.** When you invoke `Chrome --profile-directory="Profile X"` against an already-running Chrome, the second binary detects the `SingletonLock`, messages the running Chrome over IPC, and the existing Chrome opens a tab in profile X. That tab appears in the same CDP connection your MCP already uses. To make the tab uniquely identifiable to the agent, the skill appends a `#cdp-profile=<key>` fragment to the URL. The agent matches the fragment in `list_pages`.

Profiles are addressed by **Google account email** (or display-name substring), never by `Profile XX` directory number — because directory numbers are assigned in creation order and differ per machine.

See [`references/architecture.md`](references/architecture.md) for the full why.

---

## Prerequisites

- Google Chrome (stable channel). The skill works on macOS, Linux, Windows.
- Python 3.9 or newer on PATH (`python3 --version`).
- [`chrome-devtools-mcp`](https://github.com/ChromeDevTools/chrome-devtools-mcp) already configured in your AI agent (Claude Code, Cursor, etc.). The agent needs to be attached to your live Chrome via the official MCP's "Allow remote debugging" gesture.
- `$HOME/.local/bin` on PATH (or set `PREFIX=/some/path` when running `install.sh`).

The skill does NOT bundle Chrome, does NOT manage your `chrome-devtools-mcp` configuration, and does NOT touch your existing profiles' data.

---

## Install

### Via `npx skills add` (recommended)

```bash
npx skills add <owner>/<this-repo>
```

This installs the skill into the standard Agent-Skills directory for your client (Claude Code: `~/.claude/skills/chrome-profile/`).

After install, run the bundled installer to put the `chrome-profile` CLI on `$PATH`:

```bash
# macOS / Linux
bash ~/.claude/skills/chrome-profile/scripts/install.sh
```

```cmd
:: Windows (cmd.exe or PowerShell)
"%USERPROFILE%\.agents\skills\chrome-profile\scripts\install.cmd"
```

On Windows the shim lands in `%USERPROFILE%\.local\bin\`. If that's not on PATH yet, the installer prints the `setx` command to add it (run once, then reopen the terminal).

### Manual

```bash
git clone https://github.com/<owner>/<this-repo> ~/.claude/skills/chrome-profile
bash ~/.claude/skills/chrome-profile/scripts/install.sh
```

---

## Quick start

```bash
# 1. Discover what profiles you have
chrome-profile discover

# 2. Generate a profile-key → email mapping (interactive, edits a profiles.json)
chrome-profile setup

# 3. List your configured keys (verify each resolves on this machine)
chrome-profile list

# 4. Open a URL in a specific profile
chrome-profile work "https://github.com/your-org/repo/pulls"
```

After step 4, the agent driving Chrome through `chrome-devtools-mcp` finds the tab like this:

```text
1. Call list_pages
2. Find the tab whose URL contains "cdp-profile=work"
3. Call select_page with that pageId
4. Run evaluate_script / navigate_page / click — all in the work profile's context.
```

---

## Configuration

The skill reads `profiles.json` from one of two locations (first found wins):

1. `$XDG_CONFIG_HOME/chrome-profile/profiles.json` (per-machine override, defaults to `~/.config/chrome-profile/profiles.json`)
2. `<skill-dir>/profiles.json` (shared, ships with the skill)

`chrome-profile setup` writes to the per-machine config (`$XDG_CONFIG_HOME/chrome-profile/profiles.json`) by default — this survives `npx skills update`. Pass `--shared` to write inside the skill directory instead (useful only when you fork this repo and manage `profiles.json` via your own sync setup; otherwise the next `npx skills update` will wipe it).

A minimal `profiles.json`:

```json
{
  "profiles": {
    "personal": { "email": "you@gmail.com" },
    "work":     { "email": "you@work-company.com" },
    "research": { "name_contains": "Research" }
  }
}
```

Spec types (in priority order):

| Spec | Use when |
|---|---|
| `{"email": "x@y.z"}` | Profile has a Google account signed in. Exact match on `info_cache.<dir>.user_name` in Chrome's Local State. Most portable. |
| `{"name_contains": "substring"}` | Profile has no signed-in account but its display name is distinctive. Case-insensitive substring match. |
| `{"dir": "Profile 17"}` | Escape hatch. NOT portable across machines — directory numbers are assigned in profile-creation order. |

See [`profiles.example.json`](profiles.example.json) for a starter.

---

## Commands

```text
chrome-profile <key> <url>     Open URL in the profile named <key>
chrome-profile setup           Interactive: discover profiles and write profiles.json
chrome-profile setup --yes     Non-interactive: accept all auto-derived keys
chrome-profile setup --shared  Write inside skill dir (NOT recommended; wiped by npx skills update)
chrome-profile list            Show configured keys and what they resolve to on this machine
chrome-profile discover        Show all Chrome profiles on this machine (no config needed)
```

---

## Cross-machine setup

Profiles directory names (`Profile 1`, `Profile 17`, etc.) are assigned by Chrome in creation order, so the same Google account lives in different directory numbers on different machines. Because this skill resolves by **email**, the same `profiles.json` works on every machine — the CLI reads each machine's `Local State` fresh and resolves emails to local directory names at every invocation.

To set up on a new machine:

1. Install the skill (see above) and run `scripts/install.sh`.
2. Sign in to your Google accounts in Chrome (one profile per account, the normal way).
3. Run `chrome-profile list` and confirm each key resolves to a `Profile XX`. If a key shows `UNRESOLVED on this machine`, you haven't signed in to that account yet on this machine — do that in Chrome's UI, then re-run.

---

## How agents use this skill

Most usage is from inside an AI agent (Claude Code, Cursor, etc.) with `chrome-devtools-mcp` configured. The agent's natural flow when the user asks something like *"open the PR in my work profile and summarize it"*:

```text
1. Run the shell command:
   chrome-profile work "https://github.com/org/repo/pull/123"

2. Use the MCP to find the new tab:
   list_pages  →  find tab whose url contains "cdp-profile=work"

3. Operate on it via select_page + evaluate_script / navigate_page / click.

4. The tab is in the work profile's CDP context, so all cookies, login state, and
   extensions for that profile are live. The agent gets real signed-in behavior.
```

The `SKILL.md` in this repo is what trains the agent to follow this flow. When the agent is loaded with Anthropic Agent Skills (Claude Code) or compatible runtimes, `SKILL.md`'s description triggers auto-activation.

---

## Limitations and known issues

| Limit | Detail |
|---|---|
| `chrome-devtools-mcp` config cannot pre-pin a profile | The `--browserUrl` attach mode ignores `--chromeArg=--profile-directory=` because Chrome's SingletonLock routes the launch to the existing process. Runtime is the only knob. |
| `new_page` MCP tool opens in default profile | Always use `chrome-profile <key> <url>` to materialize a tab in a non-default profile. Do NOT use `new_page` for cross-profile tab creation. |
| Fragment-stripping SPAs | If a target URL is a JS app that overwrites `location.hash`, the marker may disappear after navigation. Mitigation: read `pageId` immediately after `list_pages` and hold it; do not re-match by fragment later. |
| Copy-profile workarounds | Cookie encryption is path-bound on macOS — copying to a different user-data-dir breaks login. See `references/architecture.md`. |

More in [`references/troubleshooting.md`](references/troubleshooting.md).

---

## Update

The skill has two install layers — both have deterministic update commands:

```bash
# Layer 1: skill files (pulls the latest from this repo's default branch)
npx skills update chrome-profile

# Layer 2: the chrome-profile shim on PATH (regenerates the shim, idempotent)
bash ~/.claude/skills/chrome-profile/scripts/install.sh           # macOS / Linux
"%USERPROFILE%\.agents\skills\chrome-profile\scripts\install.cmd" :: Windows
```

Re-running `install.sh` / `install.cmd` is idempotent — safe any time, no flags needed. Your `profiles.json` is preserved across updates (it lives outside the skill dir, or is .gitignored if inside).

## Uninstall

Deterministic teardown is two steps (mirrors install):

```bash
# Step 1: remove the chrome-profile shim from PATH
bash ~/.claude/skills/chrome-profile/scripts/uninstall.sh         # macOS / Linux
"%USERPROFILE%\.agents\skills\chrome-profile\scripts\uninstall.cmd" :: Windows

# Step 2: remove the skill files
npx skills remove chrome-profile
```

By default the uninstall scripts preserve your `profiles.json` so reinstalling later restores your key mappings. Pass `--purge` (Unix) / `/purge` (Windows) to wipe the config too.

Nothing else is touched — no Chrome data, no cookies, no profiles. The skill only ever wrote two locations (the shim and the optional `~/.config/chrome-profile/`), both of which the uninstall script knows about.

## Development

```bash
# Run tests
pytest

# Validate skill metadata (requires npx, optional)
npx skills-ref validate ./SKILL.md
```

The Python CLI has no third-party dependencies. Tests use only the standard library + pytest.

---

## License

MIT. See [`LICENSE`](LICENSE).

---

## Security

This skill executes only one external command (your installed Chrome binary, located via standard OS paths). It reads (never writes) Chrome's `Local State` for profile metadata. It does NOT read or write your cookies, passwords, or any profile-internal data, and does NOT send anything over the network.

When invoked with a URL, the URL is passed verbatim to Chrome. Agents should treat URLs from untrusted upstream as instructions to verify with the user before running.

Report security issues privately via GitHub Security Advisories on this repo.
