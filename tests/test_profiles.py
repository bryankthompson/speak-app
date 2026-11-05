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
