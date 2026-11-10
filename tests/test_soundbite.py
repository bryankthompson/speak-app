"""Soundbite repository: hits must be free, and anything that changes the audio must change the key."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import soundbite

AUDIO = b"AUDIO" * 300  # lookup treats a file under 1,024 bytes as not a clip


@pytest.fixture(autouse=True)
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))
    return tmp_path


def test_miss_then_hit_returns_stored_bytes():
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1") is None
    soundbite.save("Build complete", "openai", "onyx", AUDIO, "tts-1")
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1").read_bytes() == AUDIO


def test_case_and_whitespace_do_not_change_the_key():
    soundbite.save("Build complete", "openai", "onyx", AUDIO, "tts-1")
    assert soundbite.lookup("  build   COMPLETE ", "openai", "onyx", "tts-1")


@pytest.mark.parametrize("other", [
    dict(provider="elevenlabs"), dict(voice="nova"), dict(model="tts-1-hd"), dict(speed=1.5),
])
def test_anything_that_changes_the_audio_is_a_miss(other):
    base = dict(provider="openai", voice="onyx", model="tts-1", speed=1.0)
    soundbite.save("Hi", audio=AUDIO, **base)
    assert soundbite.lookup("Hi", **{**base, **other}) is None


def test_missing_file_or_corrupt_manifest_is_a_miss_not_a_crash(repo):
    p = soundbite.save("Hi", "openai", "onyx", b"A", "tts-1")
    p.unlink()
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") is None
    (repo / "manifest.json").write_text("{not json")
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") is None


def _writer(args):
    repo, start = args
    import os
    os.environ["SOUNDBITE_DIR"] = repo
    for i in range(start, start + 15):
        soundbite.save(f"phrase {i}", "openai", "onyx", b"A" * 2000, "tts-1", 1.0)


def test_parallel_recorders_do_not_lose_manifest_entries(repo):
    """Two recording jobs ran at once and silently dropped entries before the manifest was locked."""
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(4) as pool:
        pool.map(_writer, [(str(repo), n * 15) for n in range(4)])
    assert len(soundbite._load()) == 60


def test_adopt_reindexes_a_clip_that_is_on_disk_but_not_in_the_manifest(repo):
    soundbite.save("Build complete", "openai", "onyx", b"A" * 2000, "tts-1")
    (repo / "manifest.json").write_text("{}")  # the lost-update symptom
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1") is None
    assert soundbite.adopt("Build complete", "openai", "onyx", "tts-1") is True
    assert soundbite.lookup("Build complete", "openai", "onyx", "tts-1")
    assert soundbite.adopt("Build complete", "openai", "onyx", "tts-1") is False  # already indexed


def test_adopt_ignores_missing_and_tiny_files(repo):
    assert soundbite.adopt("never recorded", "openai", "onyx", "tts-1") is False
    p = soundbite.save("tiny", "openai", "onyx", b"x" * 2000, "tts-1")
    p.write_bytes(b"fake")
    (repo / "manifest.json").write_text("{}")
    assert soundbite.adopt("tiny", "openai", "onyx", "tts-1") is False


def test_crash_while_writing_leaves_the_old_clip_and_no_temp_file(monkeypatch):
    p = soundbite.save("Hi", "openai", "onyx", b"OLD", "tts-1")
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(soundbite.os, "replace", boom)
    assert soundbite.save("Hi", "openai", "onyx", b"NEW", "tts-1") is None
    assert p.read_bytes() == b"OLD"
    assert not list(p.parent.glob("*.tmp"))


def test_an_indexed_but_empty_clip_is_a_miss():
    """A zero-byte file the manifest still lists must not count as stored (it would play silence, or fail playback)."""
    p = soundbite.save("Hi", "openai", "onyx", AUDIO, "tts-1")
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") == p
    p.write_bytes(b"")
    assert soundbite.lookup("Hi", "openai", "onyx", "tts-1") is None
