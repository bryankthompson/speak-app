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
    assert level_clips.decoded_true_peak_dbtp(unguarded) > level_clips.PEAK_GUARD_DBTP  # the failure the guard exists for
    unguarded.unlink()
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 20.0})
    assert run("apply", plan, "--library", lib).returncode == 0
    assert level_clips.decoded_true_peak_dbtp(src) <= level_clips.PEAK_GUARD_DBTP
    done = [j for j in journal_lines(lib) if j["state"] == "done"][0]
    assert done["extra_atten_db"] > 0 and done["peak_dbtp"] <= level_clips.PEAK_GUARD_DBTP
    assert not list(lib.rglob(".level-*"))


def test_peak_guard_leaves_a_clip_that_needs_none(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    assert run("apply", write_plan(tmp_path / "plan.json", {"openai/v": 6.0}), "--library", lib).returncode == 0
    done = [j for j in journal_lines(lib) if j["state"] == "done"][0]
    assert done["extra_atten_db"] == 0 and done["peak_dbtp"] <= level_clips.PEAK_GUARD_DBTP


def test_peak_guard_fails_loudly_naming_the_clip(tmp_path, monkeypatch):
    lib = noise_library(tmp_path / "lib")
    monkeypatch.setattr(level_clips, "decoded_true_peak_dbtp", lambda p: 1.0)
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
    assert level_clips.decoded_true_peak_dbtp(lib / "openai/v/n.mp3") <= level_clips.PEAK_GUARD_DBTP


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


def sample_peak_dbfs(path):
    err = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path), "-af", "astats=measure_perchannel=none",
                          "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    return float(err.split("Peak level dB:")[-1].split()[0])


def intersample_library(root, name="q", amplitude=0.9):
    """Tone at fs/4 with a 45 degree phase: samples sit near -1.7 dBFS after +6 dB, the reconstructed wave near 0 dBTP."""
    rel = f"openai/v/{name}.mp3"
    (root / "openai/v").mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc={amplitude}*sin(2*PI*11025*t+PI/4):d=1:s=44100",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(root / rel)], check=True)
    return rel


def commit_all(root):
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", "--allow-empty"]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True)


def test_guard_catches_intersample_overshoot_a_sample_peak_misses(tmp_path):
    lib = tmp_path / "lib"
    rel = intersample_library(lib)
    (lib / "manifest.json").write_text(json.dumps({"k0": {"provider": "openai", "voice": "v", "file": rel, "text": "q",
                                                          "bytes": (lib / rel).stat().st_size}}))
    commit_all(lib)
    src = lib / rel
    unguarded = level_clips.reencode(src, 6.0, level_clips.CHAIN_DEFAULTS)
    assert sample_peak_dbfs(unguarded) < level_clips.PEAK_GUARD_DBTP  # a sample-peak guard would pass this
    assert level_clips.decoded_true_peak_dbtp(unguarded) > level_clips.PEAK_GUARD_DBTP  # the true peak does not
    unguarded.unlink()
    assert run("apply", write_plan(tmp_path / "plan.json", {"openai/v": 6.0}), "--library", lib).returncode == 0
    done = [j for j in journal_lines(lib) if j["state"] == "done"][0]
    assert done["extra_atten_db"] > 0
    assert level_clips.decoded_true_peak_dbtp(src) <= level_clips.PEAK_GUARD_DBTP
    assert done["peak_dbtp"] == pytest.approx(level_clips.decoded_true_peak_dbtp(src), abs=0.01)


def test_ffmpeg_true_peak_agrees_with_the_levels_block_verify_uses(tmp_path):
    pytest.importorskip("numpy")
    level_clips.sys.path.insert(0, str(level_clips.AOC_SRC))
    from audio_observation.levels import levels_block
    noise = noise_library(tmp_path / "noise", amplitude=0.9)
    tone = tmp_path / "tone"
    tone_src = tone / intersample_library(tone)
    for src, tol in ((noise / "openai/v/n.mp3", 0.15), (tone_src, 1.0)):
        ours, theirs = level_clips.decoded_true_peak_dbtp(src), levels_block(str(src))["truePeakDbtp"]
        # the pure fs/4 tone is the one case levels_block under-reads (it skips the file edges); ffmpeg never reads lower
        assert theirs - 0.01 <= ours <= theirs + tol, (src.name, ours, theirs)


def over_library(root):
    """Two clips: a normal one and an inter-sample-hot one (true peak over -0.5 dBTP), committed."""
    root.mkdir()
    sine(root / "openai/v/ok.mp3", -12, 2)
    hot = intersample_library(root, "hot", amplitude=1.0)
    man = {f"k{i}": {"provider": "openai", "voice": "v", "file": f, "text": f, "bytes": (root / f).stat().st_size}
           for i, f in enumerate(["openai/v/ok.mp3", hot])}
    (root / "manifest.json").write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    commit_all(root)
    return root


def test_fix_peaks_cuts_only_the_clip_over_the_limit(tmp_path):
    lib = over_library(tmp_path / "lib")
    ok_before = (lib / "openai/v/ok.mp3").read_bytes()
    assert level_clips.decoded_true_peak_dbtp(lib / "openai/v/hot.mp3") > level_clips.VERIFY_MAX_PEAK_DBTP
    res = run("fix-peaks", "--library", lib)
    assert res.returncode == 0, res.stdout + res.stderr
    assert (lib / "openai/v/ok.mp3").read_bytes() == ok_before
    assert level_clips.decoded_true_peak_dbtp(lib / "openai/v/hot.mp3") <= level_clips.VERIFY_MAX_PEAK_DBTP
    man = json.loads((lib / "manifest.json").read_text())
    assert man["k1"]["bytes"] == (lib / "openai/v/hot.mp3").stat().st_size
    assert man["k0"]["bytes"] == (lib / "openai/v/ok.mp3").stat().st_size
    fixed = [j for j in journal_lines(lib) if j["state"] == "peakfix"]
    assert [j["state"] for j in journal_lines(lib)] == ["peakfix_pending", "peakfix"]
    assert fixed[0]["file"] == "openai/v/hot.mp3" and fixed[0]["peak_before"] > fixed[0]["peak_after"]
    assert fixed[0]["atten_db"] > 0 and "old_sha256" in journal_lines(lib)[0]
    assert run("verify", "--library", lib).returncode in (0, 1)  # verify still reads the journal-bearing library
    assert not list(lib.rglob(".level-*"))


def test_fix_peaks_second_run_is_a_no_op(tmp_path):
    lib = over_library(tmp_path / "lib")
    assert run("fix-peaks", "--library", lib).returncode == 0
    commit_all(lib)
    snapshot = {f: f.read_bytes() for f in lib.rglob("*") if f.is_file() and ".git" not in f.parts}
    again = run("fix-peaks", "--library", lib)
    assert again.returncode == 0 and "over -0.5 dBTP: 0" in again.stdout, again.stdout + again.stderr
    assert snapshot == {f: f.read_bytes() for f in lib.rglob("*") if f.is_file() and ".git" not in f.parts}


def test_fix_peaks_dry_run_writes_nothing(tmp_path):
    lib = over_library(tmp_path / "lib")
    res = run("fix-peaks", "--library", lib, "--dry-run")
    assert res.returncode == 0 and "would cut openai/v/hot.mp3" in res.stdout
    assert subprocess.run(["git", "-C", str(lib), "status", "--porcelain"], capture_output=True, text=True).stdout == ""


def test_fix_peaks_refuses_dirty_tree(tmp_path):
    lib = over_library(tmp_path / "lib")
    (lib / "stray.txt").write_text("x")
    res = run("fix-peaks", "--library", lib)
    assert res.returncode == 1 and "uncommitted" in res.stderr
    assert not (lib / "levels-applied.jsonl").exists()


def test_fix_peaks_names_a_clip_still_over_after_its_tries(tmp_path, monkeypatch):
    lib = over_library(tmp_path / "lib")
    monkeypatch.setattr(level_clips, "decoded_true_peak_dbtp", lambda p: 1.0)
    assert level_clips.main(["fix-peaks", "--library", str(lib)]) == 1
    assert not list(lib.rglob(".level-*"))


def test_fix_peaks_crash_after_replace_is_recovered_not_cut_twice(tmp_path, monkeypatch):
    lib = over_library(tmp_path / "lib")
    real = level_clips.journal_append

    def die_on_fix(lib_, entry):
        if entry["state"] == "peakfix":
            raise RuntimeError("killed after os.replace")
        real(lib_, entry)

    monkeypatch.setattr(level_clips, "journal_append", die_on_fix)
    with pytest.raises(RuntimeError):
        level_clips.main(["fix-peaks", "--library", str(lib)])
    monkeypatch.setattr(level_clips, "journal_append", real)
    cut = (lib / "openai/v/hot.mp3").read_bytes()
    assert level_clips.main(["fix-peaks", "--library", str(lib)]) == 0
    assert (lib / "openai/v/hot.mp3").read_bytes() == cut
    assert [j["state"] for j in journal_lines(lib)] == ["peakfix_pending", "peakfix"]


def test_apply_ignores_peakfix_lines(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    assert run("apply", plan, "--library", lib).returncode == 0
    level_clips.journal_append(lib, {"state": "peakfix", "key": "k0", "file": "openai/v/a.mp3", "peak_before": 0.1,
                                     "peak_after": -1.0, "atten_db": 1.1})
    again = run("apply", plan, "--library", lib)
    assert again.returncode == 0 and "nothing to apply" in again.stdout, again.stderr


# --- add-voice and save-time leveling ---

def commit(root, msg="x"):
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg]):
        subprocess.run(["git", "-C", str(root), *cmd], check=True)


def add_clip(lib, voice, name, vol, secs=2):
    """Add a clip + manifest entry (no commit); returns its key."""
    rel = f"openai/{voice}/{name}.mp3"
    sine(lib / rel, vol, secs)
    man = json.loads((lib / "manifest.json").read_text())
    key = f"n-{voice}-{name}"
    man[key] = {"provider": "openai", "voice": voice, "file": rel, "text": name, "bytes": (lib / rel).stat().st_size}
    (lib / "manifest.json").write_text(json.dumps(man))
    return key


def test_add_voice_measures_only_the_new_voice_and_keeps_the_old_journal_valid(tmp_path):
    lib = make_library(tmp_path / "lib", [("old", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/old": 6.0})
    old_hash = json.loads(plan.read_text())["plan_hash"]
    assert run("apply", plan, "--library", lib).returncode == 0
    old_bytes = (lib / "openai/old/a.mp3").read_bytes()
    add_clip(lib, "fresh", "a", -12)
    add_clip(lib, "fresh", "b", -12)
    commit(lib)
    res = run("add-voice", "openai/fresh", "--library", lib, "--plan", plan)
    assert res.returncode == 0, res.stderr
    new = json.loads(plan.read_text())
    assert set(new["voices"]) == {"openai/old", "openai/fresh"}
    assert new["voices"]["openai/fresh"]["gain_db"] > 6.0  # quieter voice, bigger gain
    assert new["voices"]["openai/old"] == {"gain_db": 6.0}  # the old voice was not re-measured
    assert new["previous_hashes"] == [old_hash] and new["plan_hash"] != old_hash
    res = run("apply", plan, "--library", lib)
    assert res.returncode == 0 and "2 clips" in res.stdout and "openai/old" not in res.stdout, res.stdout + res.stderr
    assert (lib / "openai/old/a.mp3").read_bytes() == old_bytes
    assert {j["plan"] for j in journal_lines(lib)} == {old_hash, new["plan_hash"]}


def test_add_voice_refuses_a_leveled_or_planned_voice_and_an_unknown_one(tmp_path):
    lib = make_library(tmp_path / "lib", [("old", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/old": 6.0})
    before = plan.read_text()
    assert run("apply", plan, "--library", lib).returncode == 0
    for voice in ("openai/old", "openai/nobody"):
        res = run("add-voice", voice, "--library", lib, "--plan", plan)
        assert res.returncode == 1 and "refusing" in res.stderr, res.stderr
    assert plan.read_text() == before


def saved_clip(lib, voice, name, vol, secs=3):
    """A new clip as soundbite.save leaves it: file + manifest entry, raw. Returns (key, path)."""
    key = add_clip(lib, voice, name, vol, secs)
    return key, lib / f"openai/{voice}/{name}.mp3"


def test_save_time_leveling_then_apply_does_not_encode_twice(tmp_path, monkeypatch):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    assert run("apply", plan, "--library", lib).returncode == 0
    commit(lib)
    key, path = saved_clip(lib, "v", "new", -6)
    raw = path.read_bytes()
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    assert level_clips.level_saved(lib, key) is True
    leveled = path.read_bytes()
    assert leveled != raw
    states = [j["state"] for j in journal_lines(lib) if j["key"] == key]
    assert states == ["pending", "done"]
    assert json.loads((lib / "manifest.json").read_text())[key]["bytes"] == len(leveled)
    res = run("apply", plan, "--library", lib)  # journal-owned files do not trip the clean-tree rule
    assert res.returncode == 0 and "nothing to apply" in res.stdout, res.stdout + res.stderr
    assert path.read_bytes() == leveled


def test_save_time_result_matches_what_apply_would_produce(tmp_path, monkeypatch):
    clips = [("v", "a", -6, 3)]
    lib = make_library(tmp_path / "lib", clips)
    ref = make_library(tmp_path / "ref", clips)
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    assert level_clips.level_saved(lib, "k0") is True
    assert level_clips.main(["apply", str(plan), "--library", str(ref)]) == 0
    assert (lib / "openai/v/a.mp3").read_bytes() == (ref / "openai/v/a.mp3").read_bytes()


def test_crash_between_save_time_encode_and_done_recovers_like_apply(tmp_path, monkeypatch):
    clips = [("v", "a", -6, 3)]
    lib = make_library(tmp_path / "lib", clips)
    ref = make_library(tmp_path / "ref", clips)
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    assert level_clips.main(["apply", str(plan), "--library", str(ref)]) == 0
    real = level_clips.journal_append

    def die_on_done(lib_, entry):
        if entry["state"] == "done":
            raise RuntimeError("killed after os.replace")
        real(lib_, entry)

    monkeypatch.setattr(level_clips, "journal_append", die_on_done)
    assert level_clips.level_saved(lib, "k0") is False  # fails open, does not raise
    monkeypatch.setattr(level_clips, "journal_append", real)
    assert [j["state"] for j in journal_lines(lib)] == ["pending"]
    assert level_clips.main(["apply", str(plan), "--library", str(lib)]) == 0
    assert (lib / "openai/v/a.mp3").read_bytes() == (ref / "openai/v/a.mp3").read_bytes()  # leveled once
    assert [j["state"] for j in journal_lines(lib)] == ["pending", "done"]


def test_save_time_ffmpeg_failure_keeps_the_clip_and_does_not_raise(tmp_path, monkeypatch, capsys):
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 2)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    raw = (lib / "openai/v/a.mp3").read_bytes()
    monkeypatch.setenv("PATH", str(tmp_path))  # no ffmpeg
    assert level_clips.level_saved(lib, "k0") is False
    assert (lib / "openai/v/a.mp3").read_bytes() == raw
    assert capsys.readouterr().err.count("left unleveled") == 1
    assert not (lib / level_clips.APPLIED_LOG).exists()


def test_save_time_leveling_through_soundbite_save_stays_fast(tmp_path, monkeypatch):
    import time
    import soundbite
    lib = make_library(tmp_path / "lib", [("v", "a", -6, 3)])
    plan = write_plan(tmp_path / "plan.json", {"openai/v": 6.0})
    sine(tmp_path / "in.mp3", -6, 3)
    monkeypatch.setenv("SOUNDBITE_DIR", str(lib))
    monkeypatch.setenv("SOUNDBITE_PLAN", str(plan))
    raw = (tmp_path / "in.mp3").read_bytes()
    start = time.time()
    path = soundbite.save("a brand new line", "openai", "v", raw, "tts-1")
    took = time.time() - start
    print(f"save + level of a 3 s clip: {took:.2f}s")
    assert path.read_bytes() != raw and took < 2.0
