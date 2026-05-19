# Chrome Profile Agent Guide

Canonical agent instructions for `/Users/kaitran/CloudPersonal/apps/chrome-profile`.
`AGENTS.md` must stay a symlink to this file.

## Scope

Agent Skill for deterministic Chrome profile targeting through
`chrome-devtools-mcp`, addressed by stable profile keys instead of local
`Profile XX` directory numbers.

## Work Rules

- Keep profile resolution portable across machines; prefer email or display-name
  matching over hard-coded Chrome profile directories.
- Do not commit real `profiles.json`, account emails from local machines,
  cookies, browser state, or generated local config.
- Keep Chrome automation behavior explicit and conservative. This skill should
  open and identify the right profile tab, not take over unrelated browser
  workflows.
- Preserve cross-platform support in scripts when changing CLI behavior.

## Useful Paths

- `SKILL.md` - skill instructions consumed by agents.
- `scripts/chrome_profile_cli.py` - CLI entrypoint and profile resolution.
- `scripts/install.sh` and `scripts/install.cmd` - installer shims.
- `references/` - architecture and troubleshooting notes.
- `tests/test_chrome_profile_cli.py` - Python regression coverage.

## Validation

```bash
cd /Users/kaitran/CloudPersonal/apps/chrome-profile && python3 -m pytest tests
cd /Users/kaitran/CloudPersonal/apps/chrome-profile && python3 scripts/chrome_profile_cli.py --help
```
