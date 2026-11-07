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


def test_gain_sign_and_cap():
    assert level_clips.compute_gain(-18, -26, -10) == (8.0, False)
    assert level_clips.compute_gain(-18, -10, -3) == (-8.0, False)
    assert level_clips.compute_gain(-18, -26, -4) == (3.0, True)  # peak -4 + 8 would pass -1


def test_measure_plan_gains_have_right_sign(lib, tmp_path):
    voices = json.loads(plan_for(lib, tmp_path).read_text())["voices"]
    assert voices["openai/quiet"]["gain_db"] > 0 > voices["openai/loud"]["gain_db"]


def test_short_clip_excluded_from_median(tmp_path):
    lib = make_library(tmp_path / "lib", [("v", "long", 0, 2), ("v", "short", 10, 0.5)])
    plan = plan_for(lib, tmp_path)
    med = json.loads(plan.read_text())["voices"]["openai/v"]["median_lufs"]
    assert med == pytest.approx(-22.2, abs=0.5)  # the 2 s clip alone (-18 dBFS sine); the loud 0.5 s clip is ignored


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
