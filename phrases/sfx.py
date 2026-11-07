#!/usr/bin/env python3
"""Generate short state sounds (earcons) with ElevenLabs sound generation and store them in the soundbite library.

    ELEVENLABS_API_KEY=... python3 phrases/sfx.py [--dry-run]

Stored as provider "sfx", voice "elevenlabs", text = the prompt, model "sound-generation|<seconds>s".
Skips stored ones; stops on the first error (quota, auth, permission). Stdlib only; plays nothing.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import soundbite  # noqa: E402

SECONDS = 1.5
EFFECTS = {  # state -> prompt
    "done": "short bright success chime, two rising notes",
    "merged": "satisfying soft click then a short triumphant chime",
    "question": "curious rising two-note tone, friendly",
    "needs-you": "gentle attention bell, three soft taps then a clear ding",
    "blocked": "low soft warning buzz, two short pulses",
    "alert": "urgent but polite alarm, three quick beeps",
    "error": "dull descending failure tone, two notes",
    "start": "soft start-up whoosh with a small blip",
}


def main() -> int:
    model = f"sound-generation|{SECONDS:g}s"
    todo = {k: p for k, p in EFFECTS.items() if not soundbite.lookup(p, "sfx", "elevenlabs", model, 1.0)}
    print(f"{len(todo)} effects to generate, about {len(todo) * 15} credits ({SECONDS}s each, measured 10 per second)", file=sys.stderr)
    if "--dry-run" in sys.argv:
        return 0
    key = os.environ["ELEVENLABS_API_KEY"]
    for state, prompt in todo.items():
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/sound-generation",
            data=json.dumps({"text": prompt, "duration_seconds": SECONDS}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=60)
            audio, cost = r.read(), r.headers.get("character-cost")
        except urllib.error.HTTPError as e:
            print(f"STOP on first error ({state}): HTTP {e.code} {e.read()[:200]}", file=sys.stderr)
            return 2
        soundbite.save(prompt, "sfx", "elevenlabs", audio, model, 1.0)
        print(f"{state}: {len(audio)} bytes, cost {cost}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
