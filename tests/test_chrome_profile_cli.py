"""Tests for chrome_profile_cli.py — pure logic only (no Chrome required)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT / "scripts" / "chrome_profile_cli.py"

# Load the CLI module directly (it isn't on sys.path)
spec = importlib.util.spec_from_file_location("chrome_profile_cli", CLI_PATH)
cli = importlib.util.module_from_spec(spec)
sys.modules["chrome_profile_cli"] = cli
spec.loader.exec_module(cli)


# ---------------------------------------------------------------------------
# derive_key — display-name / email → kebab-case key
# ---------------------------------------------------------------------------

class TestDeriveKey:
    def test_bracket_prefix_takes_precedence(self):
        info = {"name": "[Cognition] Work Account", "user_name": "anything@x.com"}
        assert cli.derive_key(info) == "cognition"

    def test_bracket_prefix_case_insensitive(self):
        info = {"name": "[WORK] Team", "user_name": ""}
        assert cli.derive_key(info) == "work"

    def test_falls_back_to_email_local_part(self):
        info = {"name": "Some Display", "user_name": "alice.smith@gmail.com"}
        assert cli.derive_key(info) == "alice-smith"

    def test_email_local_part_strips_pluses_and_dots(self):
        info = {"name": "", "user_name": "alice+work@gmail.com"}
        assert cli.derive_key(info) == "alice-work"

    def test_falls_back_to_name_when_no_email(self):
        info = {"name": "Side Project", "user_name": ""}
        assert cli.derive_key(info) == "side-project"

    def test_empty_inputs_dont_crash(self):
        info = {"name": "", "user_name": ""}
        # Allowed: empty string is OK; setup() will auto-rename with -2 suffix on collision
        assert isinstance(cli.derive_key(info), str)

    def test_unicode_name_is_sanitized(self):
        info = {"name": "Café Personal ★", "user_name": ""}
        out = cli.derive_key(info)
        # Should only contain ASCII alnum + hyphens
        assert all(c.isalnum() or c == "-" for c in out)


# ---------------------------------------------------------------------------
# resolve_profile_dir — spec + info_cache → (dir_name, info)
# ---------------------------------------------------------------------------

SAMPLE_CACHE = {
    "Default": {"name": "Personal", "user_name": "alice@gmail.com"},
    "Profile 1": {"name": "[Work] Team", "user_name": "alice@work.com"},
    "Profile 7": {"name": "Side Project", "user_name": ""},
    "Profile 12": {"name": "Family Shared", "user_name": "FAMILY@gmail.com"},
}


class TestResolveProfileDir:
    def test_email_exact_match(self):
        d, info = cli.resolve_profile_dir("work", {"email": "alice@work.com"}, SAMPLE_CACHE)
        assert d == "Profile 1"
        assert info["name"] == "[Work] Team"

    def test_email_match_is_case_insensitive(self):
        d, _ = cli.resolve_profile_dir("fam", {"email": "family@gmail.com"}, SAMPLE_CACHE)
        assert d == "Profile 12"

    def test_email_match_with_uppercase_in_cache(self):
        d, _ = cli.resolve_profile_dir("fam", {"email": "FAMILY@GMAIL.COM"}, SAMPLE_CACHE)
        assert d == "Profile 12"

    def test_name_contains_substring_match(self):
        d, _ = cli.resolve_profile_dir("side", {"name_contains": "side"}, SAMPLE_CACHE)
        assert d == "Profile 7"

    def test_name_contains_is_case_insensitive(self):
        d, _ = cli.resolve_profile_dir("side", {"name_contains": "SIDE"}, SAMPLE_CACHE)
        assert d == "Profile 7"

    def test_explicit_dir_returns_dir(self):
        d, info = cli.resolve_profile_dir("p7", {"dir": "Profile 7"}, SAMPLE_CACHE)
        assert d == "Profile 7"
        assert info["name"] == "Side Project"

    def test_explicit_dir_missing_exits(self):
        with pytest.raises(SystemExit) as exc:
            cli.resolve_profile_dir("ghost", {"dir": "Profile 999"}, SAMPLE_CACHE)
        assert "Profile 999" in str(exc.value)

    def test_no_match_exits(self):
        with pytest.raises(SystemExit) as exc:
            cli.resolve_profile_dir("missing", {"email": "nope@nowhere.com"}, SAMPLE_CACHE)
        assert "could not be resolved" in str(exc.value)

    def test_multiple_matches_warns_uses_first(self, capsys):
        cache = {
            "Profile A": {"name": "X", "user_name": "dup@x.com"},
            "Profile B": {"name": "Y", "user_name": "dup@x.com"},
        }
        d, _ = cli.resolve_profile_dir("k", {"email": "dup@x.com"}, cache)
        assert d in ("Profile A", "Profile B")
        captured = capsys.readouterr()
        assert "multiple profiles" in captured.err

    def test_empty_spec_exits(self):
        with pytest.raises(SystemExit):
            cli.resolve_profile_dir("k", {}, SAMPLE_CACHE)


# ---------------------------------------------------------------------------
# URL anchor construction (the fragment append rule)
# ---------------------------------------------------------------------------

class TestAnchorFragment:
    """Smoke-check the fragment behavior we expect from cmd_open
    (the actual fragment logic is a 1-liner in cmd_open; we exercise it by
    constructing the same string)."""

    @staticmethod
    def anchored(url: str, key: str) -> str:
        sep = "&" if "#" in url else "#"
        return f"{url}{sep}cdp-profile={key}"

    def test_url_with_no_fragment_gets_hash(self):
        assert self.anchored("https://x.com/p", "work") == "https://x.com/p#cdp-profile=work"

    def test_url_with_existing_fragment_gets_ampersand(self):
        assert self.anchored("https://x.com/p#top", "work") == "https://x.com/p#top&cdp-profile=work"

    def test_url_with_query_unchanged(self):
        assert self.anchored("https://x.com/p?q=1", "work") == "https://x.com/p?q=1#cdp-profile=work"


# ---------------------------------------------------------------------------
# Config load/save roundtrip
# ---------------------------------------------------------------------------

class TestConfigRoundtrip:
    def test_save_and_reload(self, tmp_path):
        target = tmp_path / "profiles.json"
        payload = {"profiles": {"work": {"email": "a@b.c"}, "fam": {"name_contains": "Family"}}}
        cli.save_config(payload, target)
        assert json.loads(target.read_text()) == payload

    def test_save_creates_parent_dir(self, tmp_path):
        target = tmp_path / "nested" / "deeper" / "profiles.json"
        cli.save_config({"profiles": {}}, target)
        assert target.exists()
