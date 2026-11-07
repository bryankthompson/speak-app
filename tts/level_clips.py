#!/usr/bin/env python3
"""Even out voice loudness in the soundbite library: one gain per (provider, voice).

    python3 tts/level_clips.py measure [--library DIR] [--out plan.json] [--target -18]
    python3 tts/level_clips.py apply PLAN [--library DIR] [--dry-run]
    python3 tts/level_clips.py verify [--library DIR] [--target -18] [--sample N]
    python3 tts/level_clips.py run [--library DIR] [--target -18] [--out PLAN] [--dry-run]

measure is read-only. apply re-encodes clips in place (same path, same manifest key) and
journals every clip it replaced in <library>/levels-applied.jsonl, so a crashed run resumes by rerunning.
The chain per clip (one ffmpeg re-encode): highpass, acompressor, volume (the voice gain), alimiter.
Measuring uses ~/audio-observation-core (loudness_block: integratedLufs, levels_block:
samplePeakDbfs / truePeakDbtp); it needs numpy, scipy, soxr and soundfile, so the script
re-runs itself under `uv run --with ...` when they are missing. Everything else is stdlib.
"""

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import statistics
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DEFAULT_TARGET = -18.0
LIMIT_LINEAR = round(10 ** (-1.0 / 20), 3)  # -1 dBFS
# The whole processing chain lives here; measure and apply both build their ffmpeg filters from it.
CHAIN_DEFAULTS = {"highpass_hz": 80, "threshold_db": -24.0, "ratio": 2.5, "attack_ms": 8,
                  "release_ms": 120, "makeup": 1, "limit": LIMIT_LINEAR}
PEAK_CEILING_DBFS = -1.0
VERIFY_MAX_PEAK_DBTP = -0.5
PEAK_GUARD_DBFS = -0.8  # apply re-encodes a clip with extra attenuation when its decoded peak is above this
PEAK_GUARD_TRIES = 3
PEAK_GUARD_MARGIN_DB = 0.3
FLAG_LIMITED_FRACTION = 0.10
FLAG_REDUCTION_DB = 6.0
MIN_MEDIAN_SECONDS = 1.0
MIN_GAIN_DB = 0.5
MAX_SPREAD_DB = 3.0
DURATION_TOLERANCE_S = 0.05
STALE_TEMPDIR_S = 3600
TEMPDIR_PREFIX = "level-"
APPLIED_LOG = "levels-applied.jsonl"
AOC_SRC = Path("~/audio-observation-core/src").expanduser()
DEPS = ("numpy", "scipy", "soxr", "soundfile")


def default_library() -> Path:
    return Path(os.getenv("SOUNDBITE_DIR", "~/soundbite")).expanduser()


def voice_id(entry: dict) -> str:
    return f"{entry['provider']}/{entry['voice']}"


def chain_prefilter(chain: dict) -> str:
    """highpass + compressor: what measure renders before reading loudness (acompressor wants a linear threshold)."""
    return (f"highpass=f={chain['highpass_hz']},acompressor=threshold={10 ** (chain['threshold_db'] / 20):.6f}"
            f":ratio={chain['ratio']}:attack={chain['attack_ms']}:release={chain['release_ms']}"
            f":makeup={chain['makeup']}")


def chain_filter(chain: dict, gain_db: float, extra_atten_db: float = 0.0) -> str:
    """The full per-clip chain apply runs in one ffmpeg pass. extra_atten_db comes after the limiter."""
    out = f"{chain_prefilter(chain)},volume={gain_db}dB,alimiter=limit={chain['limit']}:attack=5:release=50:level=0"
    return f"{out},volume=-{extra_atten_db}dB" if extra_atten_db else out


def plan_hash(plan: dict) -> str:
    """Identity of a plan: target, chain and per-voice gains (not the measured stats)."""
    body = {"target": plan["target"], "chain": plan["chain"],
            "gains": {v: d["gain_db"] for v, d in sorted(plan["voices"].items())}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


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
    """Worker: (key, path, prefilter, tmpdir) -> dict with lufs, peak and duration, or {"error": ...}. Never raises.

    With a prefilter the clip is first rendered through it to a temp wav, so the reading is of the
    compressed signal; without one the file is measured as it is.
    """
    key, path, prefilter, tmpdir = args
    rendered = None
    try:
        if importlib.util.find_spec("audio_observation") is None:
            sys.path.insert(0, str(AOC_SRC))
        from audio_observation.levels import levels_block
        from audio_observation.loudness import loudness_block
        seconds = float(probe(Path(path), "duration")["duration"])
        target = path
        if prefilter:
            fd, rendered = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
            os.close(fd)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af", prefilter,
                            "-c:a", "pcm_f32le", rendered], check=True)
            target = rendered
        loud = loudness_block(target)
        lev = levels_block(target)
        lufs = loud["integratedLufs"]
        # BS.1770 gives no integrated value for some very short clips; they never feed the median
        # (< 1 s), so only their peak counts. A null on a longer clip is a real failure.
        if lufs is None and seconds >= MIN_MEDIAN_SECONDS:
            return {"key": key, "error": "integratedLufs is null (silent clip?)"}
        peak = max(lev["samplePeakDbfs"], lev["truePeakDbtp"])
        return {"key": key, "lufs": lufs, "peak": peak, "seconds": seconds}
    except Exception as exc:  # reported by the caller, which exits non-zero
        return {"key": key, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if rendered:
            Path(rendered).unlink(missing_ok=True)


def clean_stale_tempdirs() -> None:
    """Delete level-* temp dirs a killed measure left in the temp root more than an hour ago."""
    root = Path(tempfile.gettempdir())
    for d in root.glob(f"{TEMPDIR_PREFIX}*"):
        if d.is_dir() and time.time() - d.stat().st_mtime > STALE_TEMPDIR_S:
            shutil.rmtree(d, ignore_errors=True)


def measure_all(lib: Path, manifest: dict, only_keys=None, prefilter=None):
    """Measure every non-sfx clip. Returns (results by key, failures list)."""
    clean_stale_tempdirs()
    results, failures = {}, []
    start = time.time()
    # one temp dir per run holds every rendered wav, so a killed run leaves one dir for the next run to sweep
    with tempfile.TemporaryDirectory(prefix=TEMPDIR_PREFIX) as tmpdir, \
            ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
        jobs = [(k, str(lib / e["file"]), prefilter, tmpdir) for k, e in manifest.items()
                if e["provider"] != "sfx" and (only_keys is None or k in only_keys)]
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
                      "crest_db": round(statistics.median(c["peak"] - c["lufs"] for c in basis), 2),
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
    lines = [f"{'voice':<48}{'clips':>6}{'median LUFS':>13}{'peak dBFS':>11}{'crest':>7}{'gain dB':>9}{'limited':>9}{'max GR':>8}  note"]
    for vid, v in sorted(voices.items(), key=lambda kv: kv[1]["gain_db"]):
        note = " ".join(n for n, on in (("LIMITER-HEAVY", v["flagged"]), ("short-only", v["short_only"])) if on)
        lines.append(f"{vid:<48}{v['clips']:>6}{v['median_lufs']:>13.2f}{v['max_peak_dbfs']:>11.2f}{v['crest_db']:>7.2f}"
                     f"{v['gain_db']:>+9.2f}{v['limited_clips']:>9}{v['max_reduction_db']:>8.2f}  {note}")
    return "\n".join(lines)


def cmd_measure(args) -> int:
    lib = Path(args.library)
    done = [j for j in read_journal(lib) if j.get("state", "done") == "done"]
    if done:
        hashes = ", ".join(sorted({j["plan"] for j in done}))
        msg = (f"{lib / APPLIED_LOG} has {len(done)} done line(s) (plan {hashes}): this library is already leveled, "
               f"and measuring it would plan gains near 0 while apply compresses the clips again")
        if not args.force_remeasure:
            print(f"refusing to measure: {msg}. Restore the originals first, or pass --force-remeasure.",
                  file=sys.stderr)
            return 1
        print(f"WARNING: {msg}. --force-remeasure: the plan is only valid if the originals are restored "
              f"before apply:\n  {restore_command(lib)}", file=sys.stderr)
    manifest = load_manifest(lib)
    sfx = sorted(e["file"] for e in manifest.values() if e["provider"] == "sfx")
    chain = {**CHAIN_DEFAULTS, "ratio": args.ratio, "threshold_db": args.threshold_db}
    began = time.time()
    results, failures = measure_all(lib, manifest, prefilter=chain_prefilter(chain))
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
    print(f"\nvoices: {len(voices)}  clips measured: {len(results)}  spread of compressed medians (before gain): {spread} LU"
          f"  took: {time.time() - began:.0f}s")
    print(f"sfx left unchanged ({len(sfx)}): {', '.join(sfx) or 'none'}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        plan = {"target": args.target, "chain": chain, "compressed_spread_lu": spread,
                "sfx_skipped": sfx, "voices": voices}
        plan["plan_hash"] = plan_hash(plan)
        write_json_atomic(out, plan)
        out.with_name(f"{out.stem}.table.txt").write_text(table + "\n")
    return report_failures(failures)


def git_dirty_paths(lib: Path) -> set:
    out = subprocess.run(["git", "-C", str(lib), "status", "--porcelain", "-uall", "-z"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{lib} is not a git repository: {out.stderr.strip()}")
    return {e[3:] for e in out.stdout.split("\0") if e and not Path(e[3:]).name.startswith(".level-")}


def decoded_peak_dbfs(path: Path) -> float:
    """Sample peak of the decoded file (float decode, so overshoot above 0 dBFS is not clipped away)."""
    out = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", str(path), "-af", "astats=measure_perchannel=none",
                          "-f", "null", "-"], capture_output=True, text=True, check=True)
    peaks = [float(m) for m in re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", out.stderr)]
    if not peaks:
        raise RuntimeError(f"{path}: ffmpeg astats gave no peak level")
    return peaks[-1]


def reencode_guarded(src: Path, gain_db: float, chain: dict):
    """(temp file, extra_atten_db, peak_dbfs). libmp3lame overshoots the limiter ceiling, so the decoded
    temp file is measured and, above PEAK_GUARD_DBFS, redone from src with more attenuation after the limiter."""
    extra = 0.0
    for _ in range(PEAK_GUARD_TRIES + 1):
        tmp = reencode(src, gain_db, chain, extra) if extra else reencode(src, gain_db, chain)
        try:
            peak = decoded_peak_dbfs(tmp)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        if peak <= PEAK_GUARD_DBFS:
            return tmp, extra, peak
        tmp.unlink(missing_ok=True)
        extra = round(extra + peak - PEAK_GUARD_DBFS + PEAK_GUARD_MARGIN_DB, 2)
    raise RuntimeError(f"{src}: peak {peak:.2f} dBFS is still above {PEAK_GUARD_DBFS} after "
                       f"{PEAK_GUARD_TRIES} extra-attenuation tries")


def reencode(src: Path, gain_db: float, chain: dict, extra_atten_db: float = 0.0) -> Path:
    """Chain-processed copy next to src (temp file), verified to decode with the same duration."""
    bitrate = probe(src, "bit_rate,duration")
    tmp = src.with_name(f".level-{src.name}")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", chain_filter(chain, gain_db, extra_atten_db),
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


def read_journal(lib: Path) -> list:
    """Journal lines in order. A torn last line (crash mid-write) is dropped with a warning."""
    path = lib / APPLIED_LOG
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    entries = []
    for i, line in enumerate(lines):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise SystemExit(f"{path}: line {i + 1} is not valid JSON")
            print(f"warning: ignoring torn last line of {path}", file=sys.stderr)
    return entries


def journal_append(lib: Path, entry: dict) -> None:
    with open(lib / APPLIED_LOG, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def sync_manifest(lib: Path, plan_id: str) -> None:
    """Set manifest bytes from the journal (the record of what was replaced), under the soundbite lock."""
    sizes = {j["key"]: j["bytes"] for j in read_journal(lib)
             if j["plan"] == plan_id and j.get("state", "done") == "done"}
    with manifest_locked(lib):
        fresh = load_manifest(lib)
        changed = False
        for key, size in sizes.items():
            if key in fresh and fresh[key]["bytes"] != size:
                fresh[key]["bytes"] = size
                changed = True
        if changed:
            write_json_atomic(lib / "manifest.json", fresh)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recover_pending(lib: Path, plan_id: str, journal: list) -> list:
    """Write-ahead recovery: a pending line with no done line means the run died around os.replace.
    If the file no longer matches old_sha256 the replace happened, so record done (never re-level it)."""
    done = {j["key"] for j in journal if j.get("state", "done") == "done"}
    latest = {j["key"]: j for j in journal if j.get("state") == "pending" and j["key"] not in done}
    for key, pend in latest.items():
        path = lib / pend["file"]
        if file_sha256(path) != pend["old_sha256"]:
            journal_append(lib, {"state": "done", "key": key, "file": pend["file"], "plan": plan_id,
                                 "gain_db": pend["gain_db"], "bytes": path.stat().st_size})
            print(f"recovered {pend['file']}: replaced before the crash, marked done", file=sys.stderr)
    return read_journal(lib)


def restore_command(lib: Path) -> str:
    journal = shlex.quote(str(lib / APPLIED_LOG))
    files = ("python3 -c \"import json,sys;print(*[json.loads(l)['file'] for l in open(sys.argv[1])],sep='\\n')\" "
             f"{journal}")
    git = f"git -C {shlex.quote(str(lib))}"
    return f"{files} | xargs -d '\\n' {git} checkout -- && {git} checkout -- manifest.json && rm {journal}"


def dirty_message(lib: Path) -> str:
    return f"refusing to apply: {lib} has uncommitted changes (commit or stash them first)"


def cmd_apply(args) -> int:
    lib = Path(args.library)
    plan = json.loads(Path(args.plan).read_text())
    plan_id = plan_hash(plan)
    if plan.get("plan_hash") != plan_id:
        print(f"refusing to apply: plan hash {plan.get('plan_hash')} does not match its content "
              f"({plan_id}); the plan was edited", file=sys.stderr)
        return 1
    chain, journal = plan["chain"], read_journal(lib)
    committed = False
    if any(j["plan"] != plan_id for j in journal) and not args.dry_run:
        for stale in lib.rglob(".level-*"):  # re-encode temp files left by a killed run
            stale.unlink()
        # a journal that git sees as clean was committed with a finished leveling: start a fresh one
        committed = APPLIED_LOG not in git_dirty_paths(lib)
        if committed:
            journal = []
    if any(j["plan"] != plan_id for j in journal):
        print(f"refusing to apply: {lib / APPLIED_LOG} holds clips leveled by another plan (different "
              f"target, chain or gains). Restore the library first:\n  {restore_command(lib)}", file=sys.stderr)
        return 1
    if journal and not args.dry_run:
        journal = recover_pending(lib, plan_id, journal)
    done = {j["key"] for j in journal if j.get("state", "done") == "done"}
    manifest = load_manifest(lib)
    todo = {}
    for vid, v in sorted(plan["voices"].items()):
        if abs(v["gain_db"]) < MIN_GAIN_DB:
            continue
        keys = [k for k, e in sorted(manifest.items())
                if e["provider"] != "sfx" and voice_id(e) == vid and k not in done]
        if keys:
            todo[vid] = keys
    if not todo:
        print("nothing to apply: every voice is within 0.5 dB or already leveled by this plan")
        return 0
    if not args.dry_run:
        owned = {APPLIED_LOG, "manifest.json"} | {j["file"] for j in journal}
        dirty = git_dirty_paths(lib) - {".manifest.lock"}
        if dirty - (owned if journal else set()):
            print(dirty_message(lib), file=sys.stderr)
            return 1
        if committed:
            (lib / APPLIED_LOG).write_text("")
    try:
        for vid, keys in todo.items():
            gain = plan["voices"][vid]["gain_db"]
            print(f"{'would level' if args.dry_run else 'leveling'} {vid}: {gain:+.2f} dB, {len(keys)} clips")
            if args.dry_run:
                continue
            for key in keys:
                path = lib / manifest[key]["file"]
                journal_append(lib, {"state": "pending", "key": key, "file": manifest[key]["file"],
                                     "plan": plan_id, "gain_db": gain, "old_sha256": file_sha256(path)})
                tmp, extra, peak = reencode_guarded(path, gain, chain)
                os.replace(tmp, path)
                journal_append(lib, {"state": "done", "key": key, "file": manifest[key]["file"],
                                     "plan": plan_id, "gain_db": gain, "bytes": path.stat().st_size,
                                     "extra_atten_db": extra, "peak_dbfs": round(peak, 2)})
            sync_manifest(lib, plan_id)
    except BaseException:
        print("apply stopped part-way: rerun the same command to resume where it left off", file=sys.stderr)
        raise
    finally:
        if not args.dry_run:
            sync_manifest(lib, plan_id)
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
        print(f"{vid:<48}{s['clips']:>6}{s['median_lufs']:>10.2f} LUFS  crest {s['crest_db']:.2f} dB")
    medians = [s["median_lufs"] for s in stats.values()]
    spread = round(max(medians) - min(medians), 2) if medians else 0.0
    print(f"\nspread across {len(stats)} voices: {spread} LU (limit {MAX_SPREAD_DB}, target {args.target})")
    top = max((r["peak"] for r in results.values()), default=-99.0)
    print(f"max peak (sample/true): {top:.2f} dBTP (limit {VERIFY_MAX_PEAK_DBTP})")
    return 1 if report_failures(failures) or spread > MAX_SPREAD_DB or top > VERIFY_MAX_PEAK_DBTP else 0


def cmd_run(args) -> int:
    """measure -> table -> apply -> verify, stopping at the first step that fails."""
    lib = Path(args.library)
    out = args.out or str(Path("~/.cache/speak-app/level-plan.json").expanduser())
    resuming = False
    if not args.dry_run and (lib / APPLIED_LOG).exists() and Path(out).exists():
        try:  # a journal written by the plan at `out` means a crashed run: skip measure, apply resumes it
            resuming = any(j["plan"] == json.loads(Path(out).read_text()).get("plan_hash") for j in read_journal(lib))
        except (OSError, ValueError, KeyError):
            resuming = False
    if not args.dry_run and not resuming and git_dirty_paths(lib) - {".manifest.lock"}:
        print(dirty_message(lib), file=sys.stderr)
        return 1
    steps = [("measure", lambda: cmd_measure(argparse.Namespace(
                 library=args.library, target=args.target, ratio=CHAIN_DEFAULTS["ratio"],
                 threshold_db=CHAIN_DEFAULTS["threshold_db"], out=out, force_remeasure=False))),
             ("apply --dry-run" if args.dry_run else "apply",
              lambda: cmd_apply(argparse.Namespace(plan=out, library=args.library, dry_run=args.dry_run)))]
    if resuming:
        print(f"resuming: journal {lib / APPLIED_LOG} matches plan {out}; skipping measure")
        steps = steps[1:]
    if not args.dry_run:
        steps.append(("verify", lambda: cmd_verify(argparse.Namespace(library=args.library, target=args.target,
                                                                      sample=0))))
    for i, (name, step) in enumerate(steps, 1):
        print(f"== step {i}/{len(steps)}: {name} ==", flush=True)
        if step():
            print(f"run stopped: step {name} failed", file=sys.stderr)
            return 1
    print(f"== run finished (plan {out}) ==")
    return 0


def ensure_deps(argv) -> None:
    if all(importlib.util.find_spec(m) for m in DEPS):
        return
    cmd = ["uv", "run", "--quiet"] + [a for d in DEPS for a in ("--with", d)] + ["python3", __file__] + argv
    os.execvpe("uv", cmd, {**os.environ, "PYTHONPATH": f"{AOC_SRC}:{os.environ.get('PYTHONPATH', '')}"})


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("measure", "apply", "verify", "run"):
        s = sub.add_parser(name)
        if name in ("apply", "run"):
            if name == "apply":
                s.add_argument("plan")
            s.add_argument("--dry-run", action="store_true")
        if name != "apply":
            s.add_argument("--target", type=float, default=DEFAULT_TARGET)
        if name == "measure":
            s.add_argument("--ratio", type=float, default=CHAIN_DEFAULTS["ratio"])
            s.add_argument("--threshold-db", type=float, default=CHAIN_DEFAULTS["threshold_db"])
        s.add_argument("--library", default=str(default_library()))
        if name == "measure":
            s.add_argument("--force-remeasure", action="store_true",
                           help="measure even though the library is already leveled (restore originals before apply)")
        if name in ("measure", "run"):
            s.add_argument("--out", help="plan file (run default: ~/.cache/speak-app/level-plan.json)")
        if name == "verify":
            s.add_argument("--sample", type=int, default=0, help="clips per voice (default all)")
    args = p.parse_args(argv)
    if args.cmd != "apply":
        ensure_deps(argv)
    return {"measure": cmd_measure, "apply": cmd_apply, "verify": cmd_verify, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
