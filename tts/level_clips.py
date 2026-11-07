#!/usr/bin/env python3
"""Even out voice loudness in the soundbite library: one gain per (provider, voice).

    python3 tts/level_clips.py measure [--library DIR] [--out plan.json] [--target -18]
    python3 tts/level_clips.py apply PLAN [--library DIR] [--dry-run]
    python3 tts/level_clips.py verify [--library DIR] [--target -18] [--sample N]

measure is read-only. apply re-encodes clips in place (same path, same manifest key) and
records what it did in <library>/levels-applied.json so a second run skips finished voices.
Measuring uses ~/audio-observation-core (loudness_block: integratedLufs, levels_block:
samplePeakDbfs / truePeakDbtp); it needs numpy, scipy, soxr and soundfile, so the script
re-runs itself under `uv run --with ...` when they are missing. Everything else is stdlib.
"""

import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DEFAULT_TARGET = -18.0
LIMIT_LINEAR = round(10 ** (-1.0 / 20), 3)  # -1 dBFS
PEAK_CEILING_DBFS = -1.0
VERIFY_MAX_PEAK_DBTP = -0.5
FLAG_LIMITED_FRACTION = 0.10
FLAG_REDUCTION_DB = 6.0
MIN_MEDIAN_SECONDS = 1.0
MIN_GAIN_DB = 0.5
MAX_SPREAD_DB = 3.0
DURATION_TOLERANCE_S = 0.05
APPLIED_LOG = "levels-applied.json"
AOC_SRC = Path("~/audio-observation-core/src").expanduser()
DEPS = ("numpy", "scipy", "soxr", "soundfile")


def default_library() -> Path:
    return Path(os.getenv("SOUNDBITE_DIR", "~/soundbite")).expanduser()


def voice_id(entry: dict) -> str:
    return f"{entry['provider']}/{entry['voice']}"


def compute_gain(target: float, median_lufs: float) -> float:
    """Move the voice median to target. Peaks are held by the limiter in reencode, not by this gain."""
    return round(target - median_lufs, 2)


def limiting_estimate(peaks, gain_db: float):
    """(clips pushed over the ceiling, largest reduction in dB), from peak + gain vs the ceiling."""
    over = [p + gain_db - PEAK_CEILING_DBFS for p in peaks]
    return sum(1 for o in over if o > 0), round(max([0.0] + over), 2)


def load_manifest(lib: Path) -> dict:
    return json.loads((lib / "manifest.json").read_text())


@contextlib.contextmanager
def manifest_locked(lib: Path):
    """Same flock soundbite uses, so a concurrent recorder's entries are not lost."""
    with open(lib / ".manifest.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write_json_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def probe(path: Path, entries: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", f"format={entries}", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["format"]


def measure_clip(args):
    """Worker: (key, path) -> dict with lufs, peak and duration, or {"error": ...}. Never raises."""
    key, path = args
    try:
        if importlib.util.find_spec("audio_observation") is None:
            sys.path.insert(0, str(AOC_SRC))
        from audio_observation.levels import levels_block
        from audio_observation.loudness import loudness_block
        loud = loudness_block(path)
        lev = levels_block(path)
        lufs = loud["integratedLufs"]
        seconds = float(probe(Path(path), "duration")["duration"])
        # BS.1770 gives no integrated value for some very short clips; they never feed the median
        # (< 1 s), so only their peak counts. A null on a longer clip is a real failure.
        if lufs is None and seconds >= MIN_MEDIAN_SECONDS:
            return {"key": key, "error": "integratedLufs is null (silent clip?)"}
        peak = max(lev["samplePeakDbfs"], lev["truePeakDbtp"])
        return {"key": key, "lufs": lufs, "peak": peak, "seconds": seconds}
    except Exception as exc:  # reported by the caller, which exits non-zero
        return {"key": key, "error": f"{type(exc).__name__}: {exc}"}


def measure_all(lib: Path, manifest: dict, only_keys=None):
    """Measure every non-sfx clip. Returns (results by key, failures list)."""
    jobs = [(k, str(lib / e["file"])) for k, e in manifest.items()
            if e["provider"] != "sfx" and (only_keys is None or k in only_keys)]
    results, failures = {}, []
    start = time.time()
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        for i, res in enumerate(pool.map(measure_clip, jobs, chunksize=8), 1):
            if "error" in res:
                failures.append((manifest[res["key"]]["file"], res["error"]))
            else:
                results[res["key"]] = res
            if i % 100 == 0 or i == len(jobs):
                print(f"\r  measured {i}/{len(jobs)} ({time.time() - start:.0f}s)", end="",
                      file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return results, failures


def voice_stats(manifest: dict, results: dict) -> dict:
    """Per voice: median LUFS over clips >= 1 s (all clips if the voice has none), max peak, count."""
    groups = {}
    for key, res in results.items():
        groups.setdefault(voice_id(manifest[key]), []).append(res)
    stats = {}
    for vid, clips in sorted(groups.items()):
        long_clips = [c for c in clips if c["seconds"] >= MIN_MEDIAN_SECONDS]
        basis = long_clips or [c for c in clips if c["lufs"] is not None]
        if not basis:
            print(f"skipping {vid}: no clip has a loudness reading", file=sys.stderr)
            continue
        stats[vid] = {"median_lufs": round(statistics.median(c["lufs"] for c in basis), 2),
                      "max_peak_dbfs": round(max(c["peak"] for c in clips), 2),
                      "peaks": [c["peak"] for c in clips],
                      "clips": len(clips), "short_only": not long_clips}
    return stats


def report_failures(failures) -> int:
    if not failures:
        return 0
    print(f"FAILED to measure {len(failures)} clip(s):", file=sys.stderr)
    for path, err in failures:
        print(f"  {path}: {err}", file=sys.stderr)
    return 1


def format_table(voices: dict) -> str:
    lines = [f"{'voice':<48}{'clips':>6}{'median LUFS':>13}{'peak dBFS':>11}{'gain dB':>9}{'limited':>9}{'max GR':>8}  note"]
    for vid, v in sorted(voices.items(), key=lambda kv: kv[1]["gain_db"]):
        note = " ".join(n for n, on in (("LIMITER-HEAVY", v["flagged"]), ("short-only", v["short_only"])) if on)
        lines.append(f"{vid:<48}{v['clips']:>6}{v['median_lufs']:>13.2f}{v['max_peak_dbfs']:>11.2f}"
                     f"{v['gain_db']:>+9.2f}{v['limited_clips']:>9}{v['max_reduction_db']:>8.2f}  {note}")
    return "\n".join(lines)


def cmd_measure(args) -> int:
    lib = Path(args.library)
    manifest = load_manifest(lib)
    sfx = sorted(e["file"] for e in manifest.values() if e["provider"] == "sfx")
    began = time.time()
    results, failures = measure_all(lib, manifest)
    stats = voice_stats(manifest, results)
    voices = {}
    for vid, s in stats.items():
        gain = compute_gain(args.target, s["median_lufs"])
        limited, reduction = limiting_estimate(s.pop("peaks"), gain)
        flagged = limited / s["clips"] > FLAG_LIMITED_FRACTION or reduction > FLAG_REDUCTION_DB
        voices[vid] = {**s, "gain_db": gain, "limited_clips": limited, "max_reduction_db": reduction,
                       "flagged": flagged}
    medians = [v["median_lufs"] for v in voices.values()]
    spread = round(max(medians) - min(medians), 2) if medians else 0.0
    table = format_table(voices)
    print(table)
    print(f"\nvoices: {len(voices)}  clips measured: {len(results)}  before-spread: {spread} LU"
          f"  took: {time.time() - began:.0f}s")
    print(f"sfx left unchanged ({len(sfx)}): {', '.join(sfx) or 'none'}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out, {"target": args.target, "before_spread_lu": spread,
                                "sfx_skipped": sfx, "voices": voices})
        out.with_name("table.txt").write_text(table + "\n")
    return report_failures(failures)


def git_dirty(lib: Path) -> bool:
    out = subprocess.run(["git", "-C", str(lib), "status", "--porcelain"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{lib} is not a git repository: {out.stderr.strip()}")
    return bool(out.stdout.strip())


def reencode(src: Path, gain_db: float) -> Path:
    """Gain-adjusted copy next to src (temp file), verified to decode with the same duration."""
    bitrate = probe(src, "bit_rate,duration")
    tmp = src.with_name(f".level-{src.name}")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"volume={gain_db}dB,alimiter=limit={LIMIT_LINEAR}:attack=5:release=50:level=0",
                        "-c:a", "libmp3lame", "-b:a", str(bitrate["bit_rate"]), "-f", "mp3", str(tmp)],
                       check=True)
        new = probe(tmp, "duration")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(tmp), "-f", "null", "-"], check=True)
        if abs(float(new["duration"]) - float(bitrate["duration"])) > DURATION_TOLERANCE_S:
            raise RuntimeError(f"{src}: duration changed {bitrate['duration']} -> {new['duration']}")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def cmd_apply(args) -> int:
    lib = Path(args.library)
    plan = json.loads(Path(args.plan).read_text())
    target = plan["target"]
    log_path = lib / APPLIED_LOG
    log = json.loads(log_path.read_text()) if log_path.exists() else {"levels": {}}
    todo = {}
    for vid, v in plan["voices"].items():
        if abs(v["gain_db"]) < MIN_GAIN_DB:
            continue
        done = log["levels"].get(vid)
        if done and done["target"] == target:
            continue
        todo[vid] = v
    if not todo:
        print("nothing to apply: every voice is within 0.5 dB or already leveled at this target")
        return 0
    if not args.dry_run and git_dirty(lib):
        print(f"refusing to apply: {lib} has uncommitted changes (commit or stash them first)",
              file=sys.stderr)
        return 1
    manifest = load_manifest(lib)
    for vid, v in sorted(todo.items()):
        keys = [k for k, e in manifest.items() if e["provider"] != "sfx" and voice_id(e) == vid]
        print(f"{'would level' if args.dry_run else 'leveling'} {vid}: {v['gain_db']:+.2f} dB, "
              f"{len(keys)} clips")
        if args.dry_run:
            continue
        sizes = {}
        try:
            for key in keys:
                path = lib / manifest[key]["file"]
                tmp = reencode(path, v["gain_db"])
                os.replace(tmp, path)
                sizes[key] = path.stat().st_size
        except BaseException:
            print(f"apply failed part-way through {vid}: restore the library with "
                  f"`git -C {lib} checkout -- .` before rerunning", file=sys.stderr)
            raise
        with manifest_locked(lib):
            fresh = load_manifest(lib)
            for key, size in sizes.items():
                if key in fresh:
                    fresh[key]["bytes"] = size
            write_json_atomic(lib / "manifest.json", fresh)
            manifest = fresh
        log["levels"][vid] = {"target": target, "gain_db": v["gain_db"]}
        write_json_atomic(log_path, log)
    return 0


def cmd_verify(args) -> int:
    lib = Path(args.library)
    manifest = load_manifest(lib)
    only = None
    if args.sample:
        seen, only = {}, set()
        for k, e in sorted(manifest.items()):
            if e["provider"] != "sfx" and seen.get(voice_id(e), 0) < args.sample:
                seen[voice_id(e)] = seen.get(voice_id(e), 0) + 1
                only.add(k)
    results, failures = measure_all(lib, manifest, only)
    if not results:
        print("verify measured no clips (empty library or --sample below 1)", file=sys.stderr)
        return 1
    stats = voice_stats(manifest, results)
    if not stats:
        print("verify has no voice with a loudness reading, so no spread can be checked", file=sys.stderr)
        return 1
    for vid, s in sorted(stats.items(), key=lambda kv: kv[1]["median_lufs"]):
        print(f"{vid:<48}{s['clips']:>6}{s['median_lufs']:>10.2f} LUFS")
    medians = [s["median_lufs"] for s in stats.values()]
    spread = round(max(medians) - min(medians), 2) if medians else 0.0
    print(f"\nspread across {len(stats)} voices: {spread} LU (limit {MAX_SPREAD_DB}, target {args.target})")
    top = max((r["peak"] for r in results.values()), default=-99.0)
    print(f"max peak (sample/true): {top:.2f} dBTP (limit {VERIFY_MAX_PEAK_DBTP})")
    return 1 if report_failures(failures) or spread > MAX_SPREAD_DB or top > VERIFY_MAX_PEAK_DBTP else 0


def ensure_deps(argv) -> None:
    if all(importlib.util.find_spec(m) for m in DEPS):
        return
    cmd = ["uv", "run", "--quiet"] + [a for d in DEPS for a in ("--with", d)] + ["python3", __file__] + argv
    os.execvpe("uv", cmd, {**os.environ, "PYTHONPATH": f"{AOC_SRC}:{os.environ.get('PYTHONPATH', '')}"})


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("measure", "apply", "verify"):
        s = sub.add_parser(name)
        if name == "apply":
            s.add_argument("plan")
            s.add_argument("--dry-run", action="store_true")
        else:
            s.add_argument("--target", type=float, default=DEFAULT_TARGET)
        s.add_argument("--library", default=str(default_library()))
        if name == "measure":
            s.add_argument("--out")
        if name == "verify":
            s.add_argument("--sample", type=int, default=0, help="clips per voice (default all)")
    args = p.parse_args(argv)
    if args.cmd != "apply":
        ensure_deps(argv)
    return {"measure": cmd_measure, "apply": cmd_apply, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
