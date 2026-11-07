"""Plan identity and save-time leveling guards that need no ffmpeg (so they can run in CI)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import level_clips
import soundbite


def make_plan(gains, previous=None):
    plan = {"target": -18, "chain": level_clips.CHAIN_DEFAULTS,
            "voices": {v: {"gain_db": g} for v, g in gains.items()}}
    if previous:
        plan["previous_hashes"] = previous
    plan["plan_hash"] = level_clips.plan_hash(plan)
    return plan


def library(root, voices, journal_plan=None):
    """Library with one clip per voice; with journal_plan every clip is journaled done by that plan hash."""
    manifest, lines = {}, []
    for i, vid in enumerate(voices):
        provider, voice = vid.split("/")
        rel = f"{provider}/{voice}/c{i}.mp3"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"AUDIO%d" % i)
        manifest[f"k{i}"] = {"provider": provider, "voice": voice, "file": rel, "bytes": 6}
        lines.append({"state": "done", "key": f"k{i}", "file": rel, "plan": journal_plan, "gain_db": 5.0, "bytes": 6})
    (root / "manifest.json").write_text(json.dumps(manifest))
    if journal_plan:
        (root / level_clips.APPLIED_LOG).write_text("".join(json.dumps(j) + "\n" for j in lines))
    return root


def run_apply(plan, lib, *extra):
    path = lib.parent / "plan.json"
    path.write_text(json.dumps(plan))
    return level_clips.main(["apply", str(path), "--library", str(lib), *extra])


def test_plan_hash_of_an_old_plan_is_unchanged_and_ids_are_just_that_hash():
    plan = make_plan({"openai/a": 3.0})
    assert level_clips.plan_ids(plan) == {plan["plan_hash"]}


def test_ids_include_earlier_hashes():
    old = make_plan({"openai/a": 3.0})
    new = make_plan({"openai/a": 3.0, "openai/b": 2.0}, previous=[old["plan_hash"]])
    assert new["plan_hash"] != old["plan_hash"]
    assert level_clips.plan_ids(new) == {new["plan_hash"], old["plan_hash"]}


def test_journal_of_the_plan_before_a_voice_was_added_still_belongs(tmp_path, capsys):
    old = make_plan({"openai/a": 3.0})
    new = make_plan({"openai/a": 3.0, "openai/b": 2.0}, previous=[old["plan_hash"]])
    lib = library(tmp_path / "lib", ["openai/a"], journal_plan=old["plan_hash"])
    assert run_apply(new, lib, "--dry-run") == 0
    out = capsys.readouterr()
    assert "refusing" not in out.err
    assert "would level openai/b" not in out.out  # b has no clips yet; a is done
    assert "nothing to apply" in out.out


def test_journal_of_an_unrelated_plan_is_refused(tmp_path, capsys):
    other = make_plan({"openai/a": 9.0})
    new = make_plan({"openai/a": 3.0}, previous=["0123456789abcdef"])
    lib = library(tmp_path / "lib", ["openai/a"], journal_plan=other["plan_hash"])
    assert run_apply(new, lib, "--dry-run") == 1
    assert "another plan" in capsys.readouterr().err


def test_old_plan_without_previous_hashes_still_applies_its_own_journal(tmp_path, capsys):
    old = make_plan({"openai/a": 3.0})
    lib = library(tmp_path / "lib", ["openai/a"], journal_plan=old["plan_hash"])
    assert run_apply(old, lib) == 0
    assert "nothing to apply" in capsys.readouterr().out


def test_open_pending_after_an_older_done_is_recovered_once(tmp_path):
    lib = library(tmp_path / "lib", ["openai/a"])
    path = lib / "openai/a/c0.mp3"
    old_sha = level_clips.file_sha256(path)
    path.write_bytes(b"LEVELED")  # the replace happened, the crash came before done
    journal = [{"state": "done", "key": "k0", "file": "openai/a/c0.mp3", "plan": "p", "bytes": 6},
               {"state": "pending", "key": "k0", "file": "openai/a/c0.mp3", "plan": "p", "gain_db": 5.0,
                "old_sha256": old_sha}]
    level_clips.journal_append(lib, journal[0])
    level_clips.journal_append(lib, journal[1])
    after = level_clips.recover_pending(lib, "p", journal)
    assert [j["state"] for j in after] == ["done", "pending", "done"] and after[-1]["bytes"] == 7


def test_save_with_no_plan_leaves_the_clip_byte_identical(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))
    monkeypatch.setenv("SOUNDBITE_PLAN", str(tmp_path / "level-plan.json"))
    monkeypatch.setattr(level_clips, "reencode_guarded",
                        lambda *a: pytest.fail("save-time leveling ran with no plan"))
    path = soundbite.save("Hi", "openai", "onyx", b"RAW", "tts-1")
    assert path.read_bytes() == b"RAW"
    assert not (tmp_path / level_clips.APPLIED_LOG).exists()
    assert "left unleveled" not in capsys.readouterr().err  # an unleveled library is quiet


def test_save_fails_open_and_says_so_when_the_plan_is_broken(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))
    plan = tmp_path / "level-plan.json"
    plan.write_text("{not json")
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    path = soundbite.save("Hi", "openai", "onyx", b"RAW", "tts-1")
    assert path.read_bytes() == b"RAW"
    err = capsys.readouterr().err
    assert err.count("left unleveled") == 1


def test_save_over_a_leveled_key_without_a_gain_says_stale(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path))
    monkeypatch.setenv("SOUNDBITE_PLAN", str(tmp_path / "level-plan.json"))
    path = soundbite.save("Hi", "openai", "onyx", b"RAW", "tts-1")
    key = soundbite.make_key("Hi", "openai", "onyx", "tts-1", 1.0)
    level_clips.journal_append(tmp_path, {"state": "done", "key": key, "file": "x", "plan": "p", "bytes": 3})
    capsys.readouterr()
    soundbite.save("Hi", "openai", "onyx", b"RAW2", "tts-1")
    assert path.read_bytes() == b"RAW2"
    assert "stale-unleveled" in capsys.readouterr().err
