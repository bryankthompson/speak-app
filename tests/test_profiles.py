"""Profiles and assignments: re-pointing a cockpit changes its voice with no API call. Uses a temp profiles file."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import phrase_join
import profiles
import soundbite


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path / "lib"))
    pf = tmp_path / "profiles.json"
    pf.write_text(json.dumps({
        "profiles": {
            "fable": {"provider": "openai", "voice": "fable", "character": "storyteller"},
            "george": {"provider": "elevenlabs", "voice": "JBFq", "character": "British", "label": "George"},
        },
        "assignments": {"hades": {"profile": "fable"},
                        "nashville-suno-studio": {"profile": "george", "say": "studio"}},
    }))
    monkeypatch.setattr(phrase_join, "PROFILES", pf)
    return pf


def record(profile_id, say):
    c = phrase_join.load_casting()
    prof = c["profiles"][profile_id]
    for t in [say, *c["clauses"]]:
        soundbite.save(t, prof["provider"], prof["voice"], b"x" * 2000, phrase_join.bite_model(prof, c), 1.0)


def test_alias_assignment_uses_say_for_the_name_clip():
    e = phrase_join.resolve_cast("nashville-suno-studio-cockpit", phrase_join.load_casting())
    assert (e["profile"], e["name"]) == ("george", "studio")


def test_assign_repoints_a_cockpit_and_reports_missing_name_clip(capsys):
    record("george", "george")           # audition set exists, but not the name clip "hades"
    assert profiles.assign("Hades", "george") == 0
    assert "missing 1 clip" in capsys.readouterr().err
    assert phrase_join.resolve_cast("hades", phrase_join.load_casting())["voice"] == "JBFq"


def test_assign_unknown_profile_fails_loudly_and_changes_nothing(env, capsys):
    before = env.read_text()
    assert profiles.assign("hades", "nobody") == 1
    assert "unknown profile" in capsys.readouterr().err and env.read_text() == before


def test_audition_never_calls_an_api_when_clips_are_missing(capsys):
    assert profiles.audition("george") == 1       # nothing recorded: refuses, no network
    assert "never call the API" in capsys.readouterr().err


def test_join_follows_the_new_assignment():
    record("fable", "hades"); record("george", "hades")
    c = phrase_join.load_casting()
    assert phrase_join.plan("hades: go or no-go?", c)[1]["voice"] == "fable"
    profiles.assign("hades", "george")
    assert phrase_join.plan("hades: go or no-go?", phrase_join.load_casting())[1]["voice"] == "JBFq"


def _provider_voice_lists():
    """The voice lists tts/openai_tts.py accepts, read from its source (stdlib only: the script needs openai/pygame to import)."""
    import ast
    tree = ast.parse((Path(__file__).parent.parent / "tts" / "openai_tts.py").read_text())
    literal, choices = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "VoiceType" for t in node.targets):
            literal = {e.value for e in ast.walk(node.value) if isinstance(e, ast.Constant) and isinstance(e.value, str)} - {"Literal"}
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument" and node.args \
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "--voice":
            for kw in node.keywords:
                if kw.arg == "choices":
                    choices = {e.value for e in ast.walk(kw.value) if isinstance(e, ast.Constant)}
    return literal, choices


def test_every_openai_profile_voice_is_accepted_by_the_provider_cli():
    """A voice added to profiles.json but missing from openai_tts.py's whitelist fails on any phrase not yet stored,
    then speaks in the default voice instead (found by the DRC when ash, coral and sage were added)."""
    real = json.loads((Path(__file__).parent.parent / "phrases" / "profiles.json").read_text())
    voices = {p["voice"] for p in real["profiles"].values() if p["provider"] == "openai"}
    literal, choices = _provider_voice_lists()
    assert literal and choices, "could not read the voice lists from tts/openai_tts.py"
    assert voices <= literal, f"not in VoiceType: {sorted(voices - literal)}"
    assert voices <= choices, f"not in --voice choices: {sorted(voices - choices)}"


def test_list_profiles_reads_the_manifest_once_not_per_clip(monkeypatch, capsys):
    """speak --profiles took 30-90 s because each clip lookup reloaded the 2 MB manifest."""
    record("fable", "hades")
    loads = []
    real = soundbite._load
    monkeypatch.setattr(soundbite, "_load", lambda: loads.append(1) or real())
    assert profiles.list_profiles() == 0
    out = capsys.readouterr().out
    assert len(loads) == 1
    assert "fable" in out and "menu" in out and f"{len(phrase_join.load_casting()['clauses'])}/" in out
