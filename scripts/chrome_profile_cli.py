#!/usr/bin/env python3
"""chrome-profile: Open a URL in a specific Chrome profile via the running Chrome.

Profile selection is resolved AT RUNTIME from Chrome's Local State by matching the
Google account email (or a substring of the display name) — never by the brittle
`Profile <N>` directory name (which differs per machine and per profile-creation order).

The opened URL gets a `#cdp-profile=<key>` fragment so an agent driving the browser
through chrome-devtools-mcp can find the resulting tab in `list_pages` without
ambiguity.

Config resolution order (first found wins):
  1. $XDG_CONFIG_HOME/chrome-profile/profiles.json   (per-machine override)
  2. <skill>/profiles.json                                (shared, ships with the skill)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILL_CONFIG = SKILL_DIR / "profiles.json"
LOCAL_CONFIG = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "chrome-profile"
    / "profiles.json"
)


def chrome_binary() -> str:
    sys_name = platform.system()
    if sys_name == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if sys_name == "Linux":
        for candidate in ("google-chrome", "google-chrome-stable", "chromium"):
            path = shutil.which(candidate)
            if path:
                return path
        sys.exit("chrome-profile: could not find google-chrome on PATH")
    if sys_name == "Windows":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            candidate = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.exists():
                return str(candidate)
        sys.exit("chrome-profile: could not find chrome.exe in standard locations")
    sys.exit(f"chrome-profile: unsupported OS: {sys_name}")


def chrome_user_data_dir() -> Path:
    sys_name = platform.system()
    home = Path.home()
    if sys_name == "Darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    if sys_name == "Linux":
        return home / ".config" / "google-chrome"
    if sys_name == "Windows":
        return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    sys.exit(f"chrome-profile: unsupported OS: {sys_name}")


def load_local_state() -> dict:
    p = chrome_user_data_dir() / "Local State"
    if not p.exists():
        sys.exit(f"chrome-profile: Local State not found at {p}")
    return json.loads(p.read_text())


def info_cache() -> dict:
    return load_local_state().get("profile", {}).get("info_cache", {})


def load_config() -> tuple[dict, Path]:
    if LOCAL_CONFIG.exists():
        return json.loads(LOCAL_CONFIG.read_text()), LOCAL_CONFIG
    if SKILL_CONFIG.exists():
        return json.loads(SKILL_CONFIG.read_text()), SKILL_CONFIG
    sys.exit(
        "chrome-profile: no profiles.json found.\n"
        f"  Expected: {LOCAL_CONFIG}  (per-machine override)\n"
        f"  or:       {SKILL_CONFIG}  (shared)\n"
        "Run `chrome-profile setup` to generate one."
    )


def save_config(cfg: dict, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cfg, indent=2) + "\n")
    return target


def resolve_profile_dir(key: str, spec: dict, cache: dict) -> tuple[str, dict]:
    """Resolve a profile spec to the current machine's Chrome profile dir.

    spec can be:
      {"email": "x@y.z"}             — exact match on info_cache.<dir>.user_name
      {"name_contains": "Cognition"} — case-insensitive substring of info_cache.<dir>.name
      {"dir": "Profile 17"}          — explicit dir name (escape hatch; NOT portable)
    """
    email = (spec.get("email") or "").strip().lower()
    name_sub = (spec.get("name_contains") or "").strip().lower()
    explicit_dir = (spec.get("dir") or "").strip()

    if explicit_dir:
        info = cache.get(explicit_dir)
        if not info:
            sys.exit(
                f"chrome-profile: key '{key}' has dir='{explicit_dir}' but Chrome has no such profile here."
            )
        return explicit_dir, info

    matches = []
    for d, info in cache.items():
        if email and (info.get("user_name") or "").lower() == email:
            matches.append((d, info))
            continue
        if name_sub and name_sub in (info.get("name") or "").lower():
            matches.append((d, info))

    if not matches:
        sys.exit(
            f"chrome-profile: key '{key}' could not be resolved on this machine.\n"
            f"  Spec: {spec}\n"
            f"  Run `chrome-profile discover` to see available profiles.\n"
            f"  If this profile does not exist yet, create it in Chrome first."
        )
    if len(matches) > 1:
        dirs = ", ".join(d for d, _ in matches)
        print(
            f"[!] key '{key}' matches multiple profiles ({dirs}); using first match.",
            file=sys.stderr,
        )
    return matches[0]


def cmd_list(_args) -> None:
    cfg, source = load_config()
    cache = info_cache()
    profiles = cfg.get("profiles", {})
    if not profiles:
        print(f"(no profile keys configured in {source})")
        return
    print(f"# config: {source}")
    width = max(len(k) for k in profiles)
    for key in sorted(profiles):
        spec = profiles[key]
        try:
            d, info = resolve_profile_dir(key, spec, cache)
            status = f"-> {d:<14}  {info.get('user_name',''):<40}  ({info.get('name','')})"
        except SystemExit:
            status = "-> UNRESOLVED on this machine"
        print(f"  {key:<{width}}  {status}")


def cmd_open(args) -> None:
    cfg, _ = load_config()
    profiles = cfg.get("profiles", {})
    if args.key not in profiles:
        sys.exit(
            f"chrome-profile: unknown key '{args.key}'.\n"
            f"Known: {', '.join(sorted(profiles)) or '(none)'}"
        )
    profile_dir, info = resolve_profile_dir(args.key, profiles[args.key], info_cache())
    url = args.url
    sep = "&" if "#" in url else "#"
    anchored = f"{url}{sep}cdp-profile={args.key}"
    subprocess.Popen(
        [chrome_binary(), f"--profile-directory={profile_dir}", anchored],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"[+] {args.key} -> {profile_dir} ({info.get('user_name','')})")
    print(f"    opened: {anchored}")
    print(f"    find:   list_pages -> tab whose url contains 'cdp-profile={args.key}'")


def cmd_discover(_args) -> None:
    cache = info_cache()
    print(f"# Chrome profiles in {chrome_user_data_dir()}")
    for d in sorted(cache):
        info = cache[d]
        print(f"  {d:<14}  {info.get('name',''):<40}  {info.get('user_name','')}")


def derive_key(info: dict) -> str:
    name = info.get("name", "")
    m = re.search(r"\[([a-z0-9_-]+)\]", name, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    email = info.get("user_name", "")
    if email and "@" in email:
        local = email.split("@", 1)[0]
        return re.sub(r"[^a-z0-9]+", "-", local.lower()).strip("-")
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def cmd_setup(args) -> None:
    cache = info_cache()
    if not cache:
        sys.exit("chrome-profile: no profiles found in Local State")

    # Default: per-machine config (survives `npx skills update`).
    # --shared writes inside the skill dir; useful only when you control the skill
    # source (e.g. a forked repo or a personal sync setup).
    target = SKILL_CONFIG if args.shared else LOCAL_CONFIG

    existing = {}
    if target.exists():
        existing = (json.loads(target.read_text()) or {}).get("profiles", {})
    existing_by_email = {
        (v.get("email") or "").lower(): k for k, v in existing.items() if v.get("email")
    }

    proposed: list[tuple[str, dict, dict]] = []
    used_keys: set[str] = set()
    for d in sorted(cache):
        info = cache[d]
        email = (info.get("user_name") or "").lower()
        if email and email in existing_by_email:
            key = existing_by_email[email]
        else:
            key = derive_key(info)
            base = key
            i = 2
            while key in used_keys:
                key = f"{base}-{i}"
                i += 1
        used_keys.add(key)

        # Prefer email (portable); fall back to name_contains; dir only as last resort.
        if email:
            spec = {"email": info["user_name"]}
        elif info.get("name"):
            spec = {"name_contains": info["name"]}
        else:
            spec = {"dir": d}
        proposed.append((key, spec, info))

    if args.yes or args.non_interactive:
        chosen = {k: spec for k, spec, _ in proposed}
        path = save_config({"profiles": chosen}, target)
        print(f"[+] Wrote {len(chosen)} profile mapping(s) to {path}")
        return

    print(f"[*] Found {len(cache)} Chrome profile(s) at {chrome_user_data_dir()}")
    print(f"[*] Writing to {target}\n")
    print("[*] Per profile: press <Enter> to keep auto key, type a new key, '-' to skip, 'q' to abort.\n")

    chosen: dict[str, dict] = {}
    for key, spec, info in proposed:
        label = f"{info.get('name','')[:32]:<32}  {info.get('user_name','')}"
        try:
            answer = input(f"  [{key:<14}]  {label}\n  key> ").strip()
        except EOFError:
            answer = ""
        if answer == "q":
            print("aborted; no changes written.")
            return
        if answer == "-":
            print(f"  (skipped {info.get('user_name','')})")
            continue
        new_key = answer or key
        if new_key in chosen:
            print(f"  ! key '{new_key}' already used; auto-renaming")
            i = 2
            while f"{new_key}-{i}" in chosen:
                i += 1
            new_key = f"{new_key}-{i}"
        chosen[new_key] = spec
        print()

    path = save_config({"profiles": chosen}, target)
    print(f"\n[+] Wrote {len(chosen)} profile mapping(s) to {path}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="chrome-profile", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    p_open = sub.add_parser("open", help="open URL in a profile (default if KEY URL given)")
    p_open.add_argument("key"); p_open.add_argument("url")
    p_open.set_defaults(func=cmd_open)

    p_setup = sub.add_parser("setup", help="discover profiles and write profiles.json")
    p_setup.add_argument("--yes", "-y", action="store_true", help="accept all auto-derived keys")
    p_setup.add_argument("--non-interactive", action="store_true")
    p_setup.add_argument(
        "--shared",
        action="store_true",
        help=f"write to {SKILL_CONFIG} (shared with the skill) instead of the per-machine config. WARNING: `npx skills update` overwrites the skill dir, which wipes a shared profiles.json. Prefer the default (per-machine) location unless you fork this repo.",
    )
    p_setup.set_defaults(func=cmd_setup)

    p_list = sub.add_parser("list", help="show configured keys and what they resolve to on this machine")
    p_list.set_defaults(func=cmd_list)

    p_disc = sub.add_parser("discover", help="show all Chrome profiles on this machine (no config needed)")
    p_disc.set_defaults(func=cmd_discover)

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] not in {"open", "setup", "list", "discover", "-h", "--help"}:
        argv = ["open", *argv]
    args = ap.parse_args(argv)
    if not hasattr(args, "func"):
        ap.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
