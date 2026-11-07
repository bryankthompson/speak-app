"""The voices docs name only flags that exist, and the speak-voices plugin manifest is valid.

Reads files only: no network, no soundbite library, no audio.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "docs" / "VOICES.md", ROOT / "docs" / "VOICES-COCKPIT.md", ROOT / "docs" / "LEVELING.md"]
PLUGIN = ROOT / "plugins" / "speak-voices"


def _code(text):
    """Inline code spans and indented/fenced code lines: where commands are written."""
    spans = re.findall(r"`([^`\n]+)`", text)
    lines = [l.strip() for l in text.splitlines() if l.startswith("    ")]
    fenced = [l.strip() for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S) for l in block.splitlines()]
    return spans + lines + fenced


def documented_flags(command):
    """--flags written after `command` (e.g. 'speak', 'record.py') in the docs."""
    flags = set()
    for doc in DOCS:
        for chunk in _code(doc.read_text()):
            for m in re.finditer(rf"(?:^|[\s/]){re.escape(command)}\s+(.*)", chunk):
                flags.update(re.findall(r"(?<![\w-])--[a-z][a-z-]*", m.group(1).split("#")[0]))
    return flags


def speak_flags():
    """Long options the speak bash script's case statement accepts."""
    return set(re.findall(r"(?:^\s*|\|)(--[a-z][a-z-]*)(?=[|)])", (ROOT / "speak").read_text(), re.M))


def argparse_flags(script):
    return set(re.findall(r"add_argument\(\s*\"(--[a-z][a-z-]*)\"", (ROOT / script).read_text()))


def test_docs_name_speak_and_record_flags():
    # Guards against a parser that silently finds nothing and passes.
    assert {"--profiles", "--assign", "--profile"} <= documented_flags("speak")
    assert {"--provider", "--dry-run", "--reindex"} <= documented_flags("record.py")


def test_every_documented_speak_flag_exists():
    missing = documented_flags("speak") - speak_flags()
    assert not missing, f"docs name speak flags the speak script does not accept: {sorted(missing)}"


def test_every_documented_record_flag_exists():
    missing = documented_flags("record.py") - argparse_flags("phrases/record.py")
    assert not missing, f"docs name record.py flags it does not define: {sorted(missing)}"


def test_every_documented_level_clips_flag_exists():
    # level_clips.py defines its flags in one loop over subcommands (measure, apply, verify, run); every
    # add_argument("--x") in it counts, so a flag documented for the wrong subcommand is not caught here.
    assert {"--library", "--dry-run", "--target"} <= documented_flags("level_clips.py")
    missing = documented_flags("level_clips.py") - argparse_flags("tts/level_clips.py")
    assert not missing, f"docs name level_clips.py flags it does not define: {sorted(missing)}"


def test_every_documented_soundbite_flag_exists():
    missing = documented_flags("soundbite.py") - argparse_flags("tts/soundbite.py")
    assert not missing, f"docs name soundbite.py flags it does not define: {sorted(missing)}"


def test_docs_name_files_that_exist():
    for rel in ["phrases/profiles.json", "phrases/casting.json", "phrases/record.py", "phrases/sfx.py",
                "tts/profiles.py", "tts/phrase_join.py", "tts/soundbite.py", "run_local.sh", "docs/SOUNDBITE.md"]:
        assert rel in DOCS[0].read_text(), f"docs/VOICES.md no longer mentions {rel}"
        assert (ROOT / rel).exists(), f"docs/VOICES.md names {rel}, which is gone"


@pytest.mark.parametrize("manifest", [PLUGIN / ".claude-plugin" / "plugin.json"])
def test_plugin_manifest_has_name_and_version(manifest):
    data = json.loads(manifest.read_text())
    assert data["name"] == "speak-voices"
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])


def test_marketplace_lists_the_plugin_folder():
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = {p["name"]: p for p in data["plugins"]}["speak-voices"]
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").exists()


def test_plugin_commands_call_the_helper():
    helper = PLUGIN / "scripts" / "speak-voices.sh"
    assert helper.stat().st_mode & 0o111, "speak-voices.sh must be executable"
    for md in (PLUGIN / "commands").glob("*.md"):
        assert md.read_text().startswith("---\ndescription:"), f"{md.name}: missing frontmatter description"
        assert "scripts/speak-voices.sh" in md.read_text(), f"{md.name}: does not call the helper"
