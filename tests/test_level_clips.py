"""level_clips: gain logic, in-place leveling, idempotence. Tiny ffmpeg sine mp3s in a temp git library."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import level_clips

TOOL = str(Path(__file__).parent.parent / "tts" / "level_clips.py")


def run(*args):
    return subprocess.run([sys.executable, TOOL, *map(str, args)], capture_output=True, text=True)


def sine(path, volume_db, seconds=2.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}:sample_rate=44100", "-af",
                    f"volume={volume_db}dB", "-c:a", "libmp3lame", "-b:a", "64k", str(path)], check=True)


def make_library(root, clips):
    """clips: [(voice, name, volume_db, seconds)] -> library dir committed in git."""
    manifest = {}
    for i, (voice, name, vol, secs) in enumerate(clips):
        rel = f"openai/{voice}/{name}.mp3"
        sine(root / rel, vol, secs)
        manifest[f"k{i}"] = {"provider": "openai", "voice": voice, "file": rel, "text": name,
                             "bytes": (root / rel).stat().st_size}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True)
    return root


@pytest.fixture
def lib(tmp_path):
    return make_library(tmp_path / "lib", [("quiet", "a", -6, 2), ("quiet", "b", -6, 2),
                                           ("loud", "a", 8, 2), ("loud", "b", 8, 2)])


def plan_for(lib, tmp_path, target=-18):
    out = tmp_path / "plan.json"
    assert run("measure", "--library", lib, "--out", out, "--target", target).returncode == 0
    return out


def test_gain_has_no_peak_cap_and_limiting_is_estimated():
    assert level_clips.compute_gain(-18, -26) == 8.0
    assert level_clips.compute_gain(-18, -10) == -8.0
    assert level_clips.limiting_estimate([-10, -4], 8.0) == (1, 5.0)  # -4 + 8 = +4 dBFS, 5 dB over -1


def journal_lines(lib):
    return [json.loads(line) for line in (lib / "levels-applied.jsonl").read_text().splitlines()]


def write_plan(path, gains, target=-18):
    plan = {"target": target, "chain": level_clips.CHAIN_DEFAULTS,
            "voices": {v: {"gain_db": g} for v, g in gains.items()}}
    plan["plan_hash"] = level_clips.plan_hash(plan)
    path.write_text(json.dumps(plan))
    return path


def test_clip_pushed_over_ceiling_ends_under_it(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -3, 2)])  # peak about -21 dBFS
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 30.0})  # +30 -> +9 dBFS before the limiter
    assert run("apply", plan, "--library", lib).returncode == 0
    ver = run("verify", "--library", lib)
    peak = float(ver.stdout.split("max peak (sample/true):")[1].split("dBTP")[0])
    assert peak <= -0.5, ver.stdout


def test_measure_plan_gains_have_right_sign(lib, tmp_path):
    voices = json.loads(plan_for(lib, tmp_path).read_text())["voices"]
    assert voices["openai/quiet"]["gain_db"] > voices["openai/loud"]["gain_db"] + 3  # quiet voice gets much more gain


def test_short_clip_excluded_from_median(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "long", 0, 2), ("v", "short", 10, 0.5)])
    plan = plan_for(lib, tmp_path)
    med = json.loads(plan.read_text())["voices"]["openai/v"]["median_lufs"]
    pre = level_clips.chain_prefilter(level_clips.CHAIN_DEFAULTS)
    alone = level_clips.measure_clip(("k", str(lib / "openai/v/long.mp3"), pre, None))["lufs"]
    assert med == pytest.approx(alone, abs=0.05)  # the 2 s clip alone; the loud 0.5 s clip is ignored


def test_apply_levels_updates_bytes_and_is_idempotent(lib, tmp_path):
    plan = plan_for(lib, tmp_path)
    before = json.loads((lib / "manifest.json").read_text())
    audio_before = (lib / before["k0"]["file"]).read_bytes()
    assert run("apply", plan, "--library", lib).returncode == 0
    after = json.loads((lib / "manifest.json").read_text())
    assert (lib / after["k0"]["file"]).read_bytes() != audio_before
    assert after["k0"]["bytes"] == (lib / after["k0"]["file"]).stat().st_size
    assert {k: {f: v for f, v in e.items() if f != "bytes"} for k, e in after.items()} == \
           {k: {f: v for f, v in e.items() if f != "bytes"} for k, e in before.items()}
    ver = run("verify", "--library", lib)
    assert ver.returncode == 0, ver.stdout
    # idempotent: commit, apply again, nothing changes
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "lvl"]):
        subprocess.run(["git", "-C", str(lib), *cmd], check=True)
    again = run("apply", plan, "--library", lib)
    assert again.returncode == 0 and "nothing to apply" in again.stdout
    assert subprocess.run(["git", "-C", str(lib), "status", "--porcelain"], capture_output=True,
                          text=True).stdout == ""


def test_apply_refuses_dirty_tree(lib, tmp_path):
    plan = plan_for(lib, tmp_path)
    (lib / "stray.txt").write_text("x")
    res = run("apply", plan, "--library", lib)
    assert res.returncode == 1 and "uncommitted" in res.stderr


def test_unmeasurable_file_fails_measure(lib, tmp_path):
    (lib / "openai/quiet/a.mp3").write_bytes(b"not audio")
    res = run("measure", "--library", lib)
    assert res.returncode == 1 and "openai/quiet/a.mp3" in res.stderr


def test_verify_fails_when_every_voice_is_skipped(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "tiny", 0, 0.2)])  # too short for a loudness reading
    res = run("verify", "--library", lib)
    assert res.returncode == 1 and "no voice with a loudness reading" in res.stderr, res.stdout + res.stderr


def test_crash_midway_resumes_without_leveling_twice(tmp_path, monkeypatch):
    lib = make_library(tmp_path / "lib", [("v", f"c{i}", -6, 2) for i in range(4)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    real, calls = level_clips.reencode, []

    def flaky(src, gain, chain):
        calls.append(src.name)
        if len(calls) == 3:
            raise RuntimeError("boom")
        return real(src, gain, chain)

    monkeypatch.setattr(level_clips, "reencode", flaky)
    with pytest.raises(RuntimeError):
        level_clips.main(["apply", str(plan), "--library", str(lib)])
    first_two = [j["file"] for j in journal_lines(lib) if j["state"] == "done"]
    assert len(first_two) == 2
    # manifest bytes already match the two replaced files even though the run died (finally block)
    man = json.loads((lib / "manifest.json").read_text())
    assert all(man[k]["bytes"] == (lib / e["file"]).stat().st_size for k, e in man.items() if e["file"] in first_two)

    calls.clear()
    assert level_clips.main(["apply", str(plan), "--library", str(lib)]) == 0
    assert len(calls) == 2 and not set(calls) & {Path(f).name for f in first_two}  # no clip leveled twice
    man = json.loads((lib / "manifest.json").read_text())
    assert all(e["bytes"] == (lib / e["file"]).stat().st_size for e in man.values())
    assert len([j for j in journal_lines(lib) if j["state"] == "done"]) == 4


def test_stale_plan_refused_with_restore_command(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    assert run("apply", write_plan(tmp_path / "p1.json", {"openai/v": 6.0}), "--library", lib).returncode == 0
    res = run("apply", write_plan(tmp_path / "p2.json", {"openai/v": 3.0}), "--library", lib)
    assert res.returncode == 1 and "another plan" in res.stderr and "checkout --" in res.stderr


def test_edited_plan_refused(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "p.json", {"openai/v": 6.0})
    doc = json.loads(plan.read_text())
    doc["voices"]["openai/v"]["gain_db"] = 9.0
    plan.write_text(json.dumps(doc))
    assert run("apply", plan, "--library", lib).returncode == 1


def test_compression_lowers_peak_to_loudness_on_a_burst(tmp_path):
    src = tmp_path / "burst.wav"  # quiet tone with a loud burst: a high crest factor
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=3:sample_rate=44100", "-af",
                    "volume=10dB,volume=enable='between(t,1,1.5)':volume=8dB", str(src)], check=True)
    res = {}
    for name, pre in (("raw", None), ("comp", level_clips.chain_prefilter({**level_clips.CHAIN_DEFAULTS, "ratio": 8, "threshold_db": -30, "attack_ms": 1}))):
        pytest.importorskip("numpy")
        res[name] = level_clips.measure_clip(("k", str(src), pre, None))
    crest = {n: r["peak"] - r["lufs"] for n, r in res.items()}
    assert crest["comp"] < crest["raw"] - 1.0, crest


def test_crash_between_replace_and_done_levels_exactly_once(tmp_path, monkeypatch):
    clips = [("v", "a", -6, 2)]
    ref = make_library(tmp_path / "ref", clips)
    lib = make_library(tmp_path / "lib", clips)
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    assert level_clips.main(["apply", str(plan), "--library", str(ref)]) == 0

    real = level_clips.journal_append

    def die_on_done(lib_, entry):
        if entry["state"] == "done":
            raise RuntimeError("killed after os.replace")
        real(lib_, entry)

    monkeypatch.setattr(level_clips, "journal_append", die_on_done)
    with pytest.raises(RuntimeError):
        level_clips.main(["apply", str(plan), "--library", str(lib)])
    monkeypatch.setattr(level_clips, "journal_append", real)
    assert [j["state"] for j in journal_lines(lib)] == ["pending"]
    assert level_clips.main(["apply", str(plan), "--library", str(lib)]) == 0
    # resume saw the file already replaced: marked done, not re-leveled (a second pass would differ)
    assert (lib / "openai/v/a.mp3").read_bytes() == (ref / "openai/v/a.mp3").read_bytes()
    man = json.loads((lib / "manifest.json").read_text())
    assert man["k0"]["bytes"] == (lib / "openai/v/a.mp3").stat().st_size
    assert [j["state"] for j in journal_lines(lib)] == ["pending", "done"]


def test_crash_before_replace_redoes_the_clip(tmp_path, monkeypatch):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    real = level_clips.reencode
    monkeypatch.setattr(level_clips, "reencode", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        level_clips.main(["apply", str(plan), "--library", str(lib)])
    monkeypatch.setattr(level_clips, "reencode", real)
    assert level_clips.main(["apply", str(plan), "--library", str(lib)]) == 0
    assert [j["state"] for j in journal_lines(lib)] == ["pending", "pending", "done"]


def test_measure_table_is_named_after_the_plan(lib, tmp_path):
    plan_for(lib, tmp_path)
    assert (tmp_path / "plan.table.txt").exists() and not (tmp_path / "table.txt").exists()


def test_stale_level_tempdirs_are_swept(tmp_path, monkeypatch):
    import os, time
    monkeypatch.setattr(level_clips.tempfile, "tempdir", str(tmp_path))
    old, fresh = tmp_path / "level-old", tmp_path / "level-fresh"
    old.mkdir(); fresh.mkdir()
    os.utime(old, (time.time() - 7200,) * 2)
    level_clips.clean_stale_tempdirs()
    assert not old.exists() and fresh.exists()


def noise_library(root, amplitude=0.5):
    """White-noise clip: after the chain, libmp3lame's re-encode overshoots the -1 dBFS limiter ceiling."""
    rel = "openai/v/n.mp3"
    (root / "openai/v").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"anoisesrc=color=white:amplitude={amplitude}:duration=1:sample_rate=44100:seed=1",
                    "-c:a", "libmp3lame", "-b:a", "64k", str(root / rel)], check=True)
    (root / "manifest.json").write_text(json.dumps({"k0": {"provider": "openai", "voice": "v", "file": rel,
                                                           "text": "n", "bytes": (root / rel).stat().st_size}}))
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True)
    return root


def test_peak_guard_pulls_an_overshooting_clip_under_the_guard(tmp_path):
    lib = noise_library(tmp_path / "lib")
    src = lib / "openai/v/n.mp3"
    unguarded = level_clips.reencode(src, 20.0, level_clips.CHAIN_DEFAULTS)
    assert level_clips.decoded_peak_dbfs(unguarded) > level_clips.PEAK_GUARD_DBFS  # the failure the guard exists for
    unguarded.unlink()
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 20.0})
    assert run("apply", plan, "--library", lib).returncode == 0
    assert level_clips.decoded_peak_dbfs(src) <= level_clips.PEAK_GUARD_DBFS
    done = [j for j in journal_lines(lib) if j["state"] == "done"][0]
    assert done["extra_atten_db"] > 0 and done["peak_dbfs"] <= level_clips.PEAK_GUARD_DBFS
    assert not list(lib.rglob(".level-*"))


def test_peak_guard_leaves_a_clip_that_needs_none(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    assert run("apply", write_plan(tmp_path / "plan.json", {"openai/v": 6.0}), "--library", lib).returncode == 0
    done = [j for j in journal_lines(lib) if j["state"] == "done"][0]
    assert done["extra_atten_db"] == 0 and done["peak_dbfs"] <= level_clips.PEAK_GUARD_DBFS


def test_peak_guard_fails_loudly_naming_the_clip(tmp_path, monkeypatch):
    lib = noise_library(tmp_path / "lib")
    monkeypatch.setattr(level_clips, "decoded_peak_dbfs", lambda p: 1.0)
    with pytest.raises(RuntimeError, match="n.mp3.*still above"):
        level_clips.main(["apply", str(write_plan(tmp_path / "plan.json", {"openai/v": 20.0})), "--library", str(lib)])
    assert not list(lib.rglob(".level-*"))


def test_resumed_run_still_guards_the_peak(tmp_path, monkeypatch):
    lib = noise_library(tmp_path / "lib")
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 20.0})
    real = level_clips.reencode_guarded
    monkeypatch.setattr(level_clips, "reencode_guarded", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        level_clips.main(["apply", str(plan), "--library", str(lib)])
    monkeypatch.setattr(level_clips, "reencode_guarded", real)
    assert level_clips.main(["apply", str(plan), "--library", str(lib)]) == 0
    assert level_clips.decoded_peak_dbfs(lib / "openai/v/n.mp3") <= level_clips.PEAK_GUARD_DBFS


def test_measure_refuses_an_already_leveled_library(lib, tmp_path):
    plan = plan_for(lib, tmp_path)
    assert run("apply", plan, "--library", lib).returncode == 0
    res = run("measure", "--library", lib, "--out", tmp_path / "again.json")
    h = json.loads(plan.read_text())["plan_hash"]
    assert res.returncode == 1 and "levels-applied.jsonl" in res.stderr and h in res.stderr
    assert not (tmp_path / "again.json").exists()
    forced = run("measure", "--library", lib, "--out", tmp_path / "again.json", "--force-remeasure")
    assert forced.returncode == 0 and "WARNING" in forced.stderr and "originals" in forced.stderr


def test_run_levels_and_verifies(lib, tmp_path):
    plan = tmp_path / "p.json"
    res = run("run", "--library", lib, "--out", plan)
    assert res.returncode == 0, res.stdout + res.stderr
    for step in ("measure", "apply", "verify"):
        assert f": {step} ==" in res.stdout
    assert plan.exists() and (lib / "levels-applied.jsonl").exists()


def test_run_dry_run_changes_nothing(lib, tmp_path):
    res = run("run", "--library", lib, "--out", tmp_path / "p.json", "--dry-run")
    assert res.returncode == 0 and "would level" in res.stdout and "verify" not in res.stdout
    assert not (lib / "levels-applied.jsonl").exists()


def test_run_refuses_dirty_tree_before_measuring(lib, tmp_path):
    (lib / "stray.txt").write_text("x")
    res = run("run", "--library", lib, "--out", tmp_path / "p.json")
    assert res.returncode == 1 and "uncommitted" in res.stderr and "step" not in res.stdout
    assert not (tmp_path / "p.json").exists()


def test_new_clip_of_a_leveled_voice_is_leveled_by_rerunning_the_same_plan(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    assert run("apply", plan, "--library", lib).returncode == 0
    ref = make_library(tmp_path / "ref", [("v", "a", -6, 2)])
    assert run("apply", plan, "--library", ref).returncode == 0
    # a new clip is recorded and the library committed (journal included)
    sine(lib / "openai/v/new.mp3", -6, 2)
    man = json.loads((lib / "manifest.json").read_text())
    man["k9"] = {"provider": "openai", "voice": "v", "file": "openai/v/new.mp3", "text": "new",
                 "bytes": (lib / "openai/v/new.mp3").stat().st_size}
    (lib / "manifest.json").write_text(json.dumps(man))
    fresh = (lib / "openai/v/new.mp3").read_bytes()
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "new"]):
        subprocess.run(["git", "-C", str(lib), *cmd], check=True)
    old_a = (lib / "openai/v/a.mp3").read_bytes()
    res = run("apply", plan, "--library", lib)
    assert res.returncode == 0 and "1 clips" in res.stdout, res.stdout + res.stderr
    assert (lib / "openai/v/new.mp3").read_bytes() != fresh
    assert (lib / "openai/v/a.mp3").read_bytes() == old_a  # the already-leveled clip is not touched again
    assert json.loads((lib / "manifest.json").read_text())["k9"]["bytes"] == (lib / "openai/v/new.mp3").stat().st_size
