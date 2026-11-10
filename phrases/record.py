#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.0.0", "requests>=2.31.0"]
# ///
"""Record the cast's name + clause clips into the soundbite library. Generates only; never plays audio.

    record.py --dry-run                 # plan + character/credit/dollar totals, no API call
    record.py --provider openai         # OPENAI_API_KEY must be set (e.g. from 1Password via op)
    record.py --provider elevenlabs     # ELEVENLABS_API_KEY; stops on the first quota/auth error
    record.py --provider P --lines FILE [--dry-run]   # free-text cockpit lines, one "name: text" per row

Already-stored clips are skipped. An OpenAI error stops the run. On ElevenLabs a 404 (unknown
voice id) skips that voice; 401/402/429 or any quota text stops the whole run, no retry.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import phrase_join  # noqa: E402
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


def price_text(provider, chars):
    if provider == "openai":
        return f"${chars * OPENAI_USD_PER_M[CFG['openai_model']] / 1e6:.3f}"
    return f"{chars} chars = {chars // 2} credits at the measured 0.5/char ({chars} worst case)"


def synth(provider, voice, text, settings=None):
    """One paid call: (HTTP-ish status, audio bytes or error text). 200 is success; 404 an unknown voice."""
    if provider == "openai":
        from openai import OpenAI
        audio = b"".join(OpenAI().audio.speech.create(
            model=CFG["openai_model"], voice=voice, input=text, speed=1.0).iter_bytes())
        return 200, audio
    import requests
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Accept": "audio/mpeg", "Content-Type": "application/json"},
        json={"text": text, "model_id": CFG["elevenlabs_model"], "voice_settings": settings or CFG["elevenlabs_settings"]},
        timeout=60)
    return r.status_code, (r.content if r.status_code == 200 else r.text[:200])


def run_lines(path, provider, dry_run, call=synth):
    """Record free-text cockpit lines ("name: text") under the key the live path looks up: the WHOLE line."""
    casting = {**CFG, **PROFILES}
    model = bite_model(provider)
    stored = soundbite._load()

    def line_style(text):
        """(settings, model string) for a line: the livelier style from casting.json "expressive", else the default."""
        st = phrase_join.expressive_settings(text, casting) if provider == "elevenlabs" else None
        if not st:
            return None, model
        return st, f"{CFG['elevenlabs_model']}|s{st['stability']:g}|b{st['similarity_boost']:g}"

    def have(text, voice):
        # one rule for "is it stored": soundbite.lookup (on disk, big enough to be a clip; never raises)
        return bool(soundbite.lookup(text, provider, voice, line_style(text)[1], 1.0, stored))

    todo, bad, seen = [], 0, set()
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefix, sep, tail = line.partition(": ")
        entry = phrase_join.resolve_cast(prefix, casting) if sep and tail.strip() else None
        if not entry:
            print(f"unknown name, skipped: {line}", file=sys.stderr)
            bad += 1
            continue
        if entry["provider"] != provider:
            print(f"{entry['profile']} is a {entry['provider']} voice, skipped: {line}", file=sys.stderr)
            continue
        clause = phrase_join.match_clause(tail, casting)
        if have(line, entry["voice"]) or (clause and have(entry["name"], entry["voice"]) and have(clause, entry["voice"])):
            print(f"stored, skipped: {line}", file=sys.stderr)
            continue
        if line not in seen:
            seen.add(line)
            todo.append((entry, line))
    chars = sum(len(t) for _, t in todo)
    for _, t in todo:
        print(f"  {len(t):4d} chars  {t}", file=sys.stderr)
    print(f"{provider}: {len(todo)} lines to record, {chars} chars, {price_text(provider, chars)} (model {model})", file=sys.stderr)
    if dry_run:
        return 1 if bad else 0
    done = 0
    for entry, t in todo:
        style, t_model = line_style(t)
        status, body = call(provider, entry["voice"], t, style) if style else call(provider, entry["voice"], t)
        if status == 404:
            print(f"voice not found, skipped {t}: {body}", file=sys.stderr)
            bad += 1
            continue
        if status != 200:
            print(f"STOP on first error: HTTP {status} {body}\nrecorded {done} before stopping", file=sys.stderr)
            return 2
        if soundbite.save(t, provider, entry["voice"], body, t_model, 1.0) is None:
            print(f"STOP: could not store the clip for {t}\nrecorded {done} before stopping", file=sys.stderr)
            return 2
        done += 1
    print(f"recorded {done} lines", file=sys.stderr)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["openai", "elevenlabs"], required=True)
    ap.add_argument("--profile", action="append", help="record this profile's audition set (repeatable); default: --assigned")
    ap.add_argument("--reindex", action="store_true", help="re-add clips that are on disk but missing from the manifest; no API calls")
    ap.add_argument("--only", help="comma-separated profile ids to limit the run to")
    ap.add_argument("--assigned", action="store_true", help="record every assigned cockpit's name + menu (the default)")
    ap.add_argument("--lines", metavar="FILE", help="record free-text lines, one 'name: text' per row (# comments and blanks skipped)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    unknown = [p for p in (a.profile or []) if p not in PROFILES["profiles"]]
    if unknown:
        print(f"unknown profile id(s): {', '.join(unknown)} (see phrases/profiles.json)", file=sys.stderr)
        return 2
    if a.lines:
        return run_lines(a.lines, a.provider, a.dry_run)
    model = bite_model(a.provider)
    if a.reindex:
        n = sum(soundbite.adopt(t, a.provider, c["voice"], model, 1.0)
                for c, t in jobs(a.provider, a.profile, a.only.split(",") if a.only else None))
        print(f"{a.provider}: re-indexed {n} clip(s) that were on disk but not in the manifest", file=sys.stderr)
        return 0
    stored = soundbite._load()  # read the manifest once, not once per clip

    def have(c, t):
        return bool(soundbite.lookup(t, a.provider, c["voice"], model, 1.0, stored))  # same rule as the live path

    todo = [(c, t) for c, t in jobs(a.provider, a.profile, a.only.split(',') if a.only else None) if not have(c, t)]
    chars = sum(len(t) for _, t in todo)
    price = price_text(a.provider, chars)
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
            if soundbite.save(t, "openai", c["voice"], audio, model, 1.0) is None:
                print(f"STOP: could not store the clip for {t}\nrecorded {done} before stopping", file=sys.stderr)
                return 2
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
            if soundbite.save(t, "elevenlabs", c["voice"], r.content, model, 1.0) is None:
                print(f"STOP: could not store the clip for {t}\nrecorded {done} before stopping", file=sys.stderr)
                return 2
            done += 1
        if skipped:
            print(f"{len(skipped)} voice(s) skipped (404)", file=sys.stderr)
    print(f"recorded {done} clips", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
