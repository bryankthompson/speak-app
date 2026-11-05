"""Routing for 'name: clause' lines. No audio, no network: a temp library holds fake clips."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import phrase_join
import soundbite


@pytest.fixture
def casting():
    return phrase_join.load_casting()


@pytest.fixture(autouse=True)
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))


def stock(casting, name, clauses):
    e = phrase_join.resolve_cast(name, casting)
    for t in [e["name"], *clauses]:
        soundbite.save(t, e["provider"], e["voice"], b"x" * 2000, phrase_join.bite_model(e, casting), 1.0)
    return e


@pytest.mark.parametrize("prefix,cast", [
    ("hades", "hades"), ("Hades lead", "hades"), ("governor-cockpit", "governor"),
    ("claude-dev-harness", "harness lead"), ("Studio lead", "studio"),
    ("nashville-suno-studio", "studio"), ("2D-to-3D-SBS-Converter", "converter"),
    ("claude-dev-harness-speak-menu", "harness lead"), ("speak-app-voice-docs", "speak-app"),
])
def test_session_names_resolve_to_cast(casting, prefix, cast):
    assert phrase_join.resolve_cast(prefix, casting)["name"] == cast


def test_unknown_lane_name_stays_unresolved(casting):
    assert phrase_join.resolve_cast("totally-unknown-lane", casting) is None


def test_known_clause_joins_two_stored_clips(casting):
    stock(casting, "hades", ["go or no-go?"])
    kind, entry, paths = phrase_join.plan("hades: go or no-go?", casting)
    assert kind == "join" and entry["voice"] == "fable" and len(paths) == 2


def test_clause_matches_without_exact_punctuation(casting):
    assert phrase_join.match_clause("Merge it", casting) == "merge it?"
    assert phrase_join.match_clause("is done?", casting) == "is done"


def test_known_name_free_text_uses_the_leads_voice_not_a_join(casting):
    stock(casting, "hades", ["go or no-go?"])
    assert phrase_join.plan("hades: PR 57 ready, merge it?", casting)[0] == "voice"


def test_missing_clip_falls_back_instead_of_playing_half(casting):
    stock(casting, "hades", [])  # name stored, clause not
    assert phrase_join.plan("hades: go or no-go?", casting)[0] == "voice"


def test_unknown_name_is_a_miss_and_safety_hook_text_is_not_split(casting):
    assert phrase_join.plan("nobody: go or no-go?", casting) == ("miss", "nobody")
    assert phrase_join.plan("Warning: Dangerous command blocked", casting) == ("miss", "Warning")


def test_plain_text_is_left_alone(casting):
    assert phrase_join.plan("Build complete", casting) is None
