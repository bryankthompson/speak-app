#!/usr/bin/env python3
"""Soundbite repository: a git-friendly store of already-paid-for TTS audio.

Layout (default ~/soundbite, override with SOUNDBITE_DIR):
    manifest.json                    key -> metadata (text, provider, voice, model, speed, file, ...)
    <provider>/<voice>/<slug>-<hash8>.mp3

The key covers everything that changes the audio: normalized text, provider,
voice, model and speed. A hit means the API is never called for that phrase.

Stdlib only, so every provider script can import it.

CLI:
    python3 tts/soundbite.py stats
    python3 tts/soundbite.py list [--provider P] [--voice V]
    python3 tts/soundbite.py import-cache      # one-off import from ~/.cache/speak-app
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional


def repo_dir() -> Path:
    return Path(os.getenv("SOUNDBITE_DIR", "~/soundbite")).expanduser()


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def make_key(text: str, provider: str, voice: str, model: str = "", speed: float = 1.0) -> str:
    raw = "|".join([normalize(text), provider, voice, model, f"{float(speed):g}"])
    return hashlib.sha256(raw.encode()).hexdigest()


def _manifest_path() -> Path:
    return repo_dir() / "manifest.json"


def _load() -> dict:
    path = _manifest_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write(manifest: dict) -> None:
    """Atomic write so a crash or a parallel speak never leaves a half-written manifest."""
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def _locked():
    """Serialize manifest read-modify-write across processes (parallel recorders lost entries without it)."""
    repo_dir().mkdir(parents=True, exist_ok=True)
    with open(repo_dir() / ".manifest.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def rel_path(text: str, provider: str, voice: str, model: str = "", speed: float = 1.0):
    key = make_key(text, provider, voice, model, speed)
    slug = re.sub(r"[^a-z0-9]+", "-", normalize(text))[:40].strip("-") or "bite"
    return key, f"{provider}/{voice}/{slug}-{key[:8]}.mp3"


def adopt(text: str, provider: str, voice: str, model: str = "", speed: float = 1.0) -> bool:
    """Index an mp3 that is already on disk but missing from the manifest. True if an entry was added."""
    key, rel = rel_path(text, provider, voice, model, speed)
    path = repo_dir() / rel
    with _locked():
        manifest = _load()
        if key in manifest or not path.exists() or path.stat().st_size < 1024:
            return False
        manifest[key] = {
            "text": text.strip(), "provider": provider, "voice": voice, "model": model, "speed": speed,
            "file": rel, "bytes": path.stat().st_size,
            "created": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }
        _write(manifest)
        return True


def lookup(text: str, provider: str, voice: str, model: str = "", speed: float = 1.0) -> Optional[Path]:
    """Return the stored mp3 path, or None on a miss. Never raises: a broken repo is a miss."""
    try:
        entry = _load().get(make_key(text, provider, voice, model, speed))
        if entry:
            path = repo_dir() / entry["file"]
            if path.exists():
                return path
    except Exception as e:
        print(f"soundbite lookup failed (treating as miss): {e}", file=sys.stderr)
    return None


def save(text: str, provider: str, voice: str, audio: bytes, model: str = "", speed: float = 1.0) -> Optional[Path]:
    """Store audio and index it. Failure is logged and returns None; speaking must not break."""
    try:
        key, rel = rel_path(text, provider, voice, model, speed)
        path = repo_dir() / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        try:
            tmp.write_bytes(audio)
            os.replace(tmp, path)  # a crash leaves the old clip or none, never a torn mp3
        finally:
            tmp.unlink(missing_ok=True)
        with _locked():
            manifest = _load()
            manifest[key] = {
                "text": text.strip(),
                "provider": provider,
                "voice": voice,
                "model": model,
                "speed": speed,
                "file": rel,
                "bytes": len(audio),
                "created": datetime.now().isoformat(timespec="seconds"),
            }
            _write(manifest)
        print(f"soundbite saved: {rel}", file=sys.stderr)
        return path
    except Exception as e:
        print(f"soundbite save failed: {e}", file=sys.stderr)
        return None


def import_cache(cache_dir: str = "~/.cache/speak-app", model: str = "tts-1") -> int:
    """Import the legacy TTSCache files (OpenAI only; they recorded no model, so tts-1 is assumed)."""
    cache = Path(cache_dir).expanduser()
    meta = json.loads((cache / "phrase_cache.json").read_text())
    added = 0
    for old_key, m in meta.items():
        src = cache / f"{old_key}.mp3"
        if not src.exists() or not m.get("voice") or src.stat().st_size < 1024:
            continue  # real speech is several KB; tiny files are test fixtures
        if lookup(m["text"], m["provider"], m["voice"], model, 1.0):
            continue
        if save(m["text"], m["provider"], m["voice"], src.read_bytes(), model, 1.0):
            added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description="Soundbite repository tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    ls = sub.add_parser("list")
    ls.add_argument("--provider")
    ls.add_argument("--voice")
    sub.add_parser("import-cache")
    args = ap.parse_args()

    if args.cmd == "import-cache":
        print(f"imported {import_cache()} soundbites into {repo_dir()}")
        return 0

    manifest = _load()
    if args.cmd == "stats":
        by = {}
        for e in manifest.values():
            by[(e["provider"], e["voice"])] = by.get((e["provider"], e["voice"]), 0) + 1
        print(f"{len(manifest)} soundbites, {sum(e['bytes'] for e in manifest.values()) / 1024:.0f} KB in {repo_dir()}")
        for (p, v), n in sorted(by.items()):
            print(f"  {p}/{v}: {n}")
    else:
        for e in sorted(manifest.values(), key=lambda e: (e["provider"], e["voice"], e["text"])):
            if args.provider and e["provider"] != args.provider:
                continue
            if args.voice and e["voice"] != args.voice:
                continue
            print(f"{e['provider']}/{e['voice']}\t{e['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
