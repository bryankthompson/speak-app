#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.0.0", "requests>=2.31.0"]
# ///
"""Record the cast's name + clause clips into the soundbite library. Generates only; never plays audio.

    record.py --dry-run                 # plan + character/credit/dollar totals, no API call
    record.py --provider openai         # OPENAI_API_KEY must be set (e.g. from 1Password via op)
    record.py --provider elevenlabs     # ELEVENLABS_API_KEY; stops on the first quota/auth error

Already-stored clips are skipped. An OpenAI error stops the run. On ElevenLabs a 404 (unknown
voice id) skips that voice; 401/402/429 or any quota text stops the whole run, no retry.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import soundbite  # noqa: E402

CFG = json.loads((Path(__file__).parent / "casting.json").read_text())
PROFILES = json.loads((Path(__file__).parent / "profiles.json").read_text())
OPENAI_USD_PER_M = {"tts-1": 15, "tts-1-hd": 30}  # published rates, unverified here


def jobs(provider, profile_ids=None, only=None):
    """(profile, text) to record. Default: every assigned cockpit's name + the clause menu.
    With profile_ids: those profiles, the name clip being the profile id (an audition set)."""
    seen = set()
    if profile_ids:
        pairs = [(pid, pid) for pid in profile_ids]
    else:
        pairs = [(a["profile"], a.get("say", cockpit)) for cockpit, a in PROFILES["assignments"].items()]
    for pid, say in pairs:
        prof = PROFILES["profiles"][pid]
        if prof["provider"] != provider or (only and pid not in only):
            continue
        for text in [say, *CFG["clauses"]]:
            if (pid, text) not in seen:
                seen.add((pid, text))
                yield {**prof, "name": pid}, text


def bite_model(provider):
    if provider == "openai":
        return CFG["openai_model"]
    s = CFG["elevenlabs_settings"]
    return f"{CFG['elevenlabs_model']}|s{s['stability']:g}|b{s['similarity_boost']:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "elevenlabs"], required=True)
    ap.add_argument("--profile", action="append", help="record this profile's audition set (repeatable); default: --assigned")
    ap.add_argument("--reindex", action="store_true", help="re-add clips that are on disk but missing from the manifest; no API calls")
    ap.add_argument("--only", help="comma-separated profile ids to limit the run to")
    ap.add_argument("--assigned", action="store_true", help="record every assigned cockpit's name + menu (the default)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    unknown = [p for p in (a.profile or []) if p not in PROFILES["profiles"]]
    if unknown:
        print(f"unknown profile id(s): {', '.join(unknown)} (see phrases/profiles.json)", file=sys.stderr)
        return 2
    model = bite_model(a.provider)
    if a.reindex:
        n = sum(soundbite.adopt(t, a.provider, c["voice"], model, 1.0)
                for c, t in jobs(a.provider, a.profile, a.only.split(",") if a.only else None))
        print(f"{a.provider}: re-indexed {n} clip(s) that were on disk but not in the manifest", file=sys.stderr)
        return 0
    stored = soundbite._load()  # read the manifest once, not once per clip

    def have(c, t):
        e = stored.get(soundbite.make_key(t, a.provider, c["voice"], model, 1.0))
        return bool(e) and (soundbite.repo_dir() / e["file"]).exists()

    todo = [(c, t) for c, t in jobs(a.provider, a.profile, a.only.split(',') if a.only else None) if not have(c, t)]
    chars = sum(len(t) for _, t in todo)
    price = f"${chars * OPENAI_USD_PER_M[CFG['openai_model']] / 1e6:.3f}" if a.provider == "openai" else f"{chars} chars = {chars // 2} credits at the measured 0.5/char ({chars} worst case)"
    print(f"{a.provider}: {len(todo)} clips to record, {chars} chars, {price} (model {model})", file=sys.stderr)
    if a.dry_run:
        return 0

    done = 0
    if a.provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        for c, t in todo:
            audio = b"".join(client.audio.speech.create(
                model=CFG["openai_model"], voice=c["voice"], input=t, speed=1.0).iter_bytes())
            soundbite.save(t, "openai", c["voice"], audio, model, 1.0)
            done += 1
    else:
        import requests
        key = os.environ["ELEVENLABS_API_KEY"]
        skipped = set()
        for c, t in todo:
            if c["voice"] in skipped:
                continue
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{c['voice']}",
                headers={"xi-api-key": key, "Accept": "audio/mpeg", "Content-Type": "application/json"},
                json={"text": t, "model_id": CFG["elevenlabs_model"], "voice_settings": CFG["elevenlabs_settings"]},
                timeout=60)
            if r.status_code == 404:
                print(f"voice not found, skipping {c['name']} ({c.get('label')}): {r.text[:120]}", file=sys.stderr)
                skipped.add(c["voice"])
                continue
            if r.status_code != 200:
                print(f"STOP on first error: HTTP {r.status_code} {r.text[:200]}", file=sys.stderr)
                print(f"recorded {done} before stopping", file=sys.stderr)
                return 2
            soundbite.save(t, "elevenlabs", c["voice"], r.content, model, 1.0)
            done += 1
        if skipped:
            print(f"{len(skipped)} voice(s) skipped (404)", file=sys.stderr)
    print(f"recorded {done} clips", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
