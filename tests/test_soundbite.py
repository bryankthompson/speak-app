"""Soundbite repository: hits must be free, and anything that changes the audio must change the key."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import soundbite


@pytest.fixture(autouse=True)
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))
    return tmp_path


def test_miss_then_hit_returns_stored_bytes():
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1") is None
    soundbite.save("Build complete", "openai", "onyx", b"AUDIO", "tts-1")
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1").read_bytes() == b"AUDIO"


def test_case_and_whitespace_do_not_change_the_key():
    soundbite.save("Build complete", "openai", "onyx", b"A", "tts-1")
    assert soundbite.lookup("  build   COMPLETE ", "openai", "onyx", "tts-1")


@pytest.mark.parametrize("other", [
    dict(provider="elevenlabs"), dict(voice="nova"), dict(model="tts-1-hd"), dict(speed=1.5),
])
def test_anything_that_changes_the_audio_is_a_miss(other):
    base = dict(provider="openai", voice="onyx", model="tts-1", speed=1.0)
    soundbite.save("Hi", audio=b"A", **base)
    assert soundbite.lookup("Hi", **{**base, **other}) is None


def test_missing_file_or_corrupt_manifest_is_a_miss_not_a_crash(repo):
    p = soundbite.save("Hi", "openai", "onyx", b"A", "tts-1")
    p.unlink()
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") is None
    (repo / "manifest.json").write_text("{not json")
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") is None
