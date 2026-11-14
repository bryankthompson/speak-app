"""Per-lead voices and the name + clause join, above the providers.

`speak "hades: go or no-go?"`:
  1. "hades" resolves to a cast entry (phrases/casting.json: names, aliases, a trailing "-cockpit" or " lead" is dropped).
  2. If the tail is a known clause, the stored name clip and clause clip play back to back. No API call.
     If they will not play, try_join raises StoredClipsFailed: the default path must not pay for a stored line.
  3. Otherwise the whole line is spoken in that lead's own voice (provider script; it saves to the library).
  4. Unknown name, no ": ", or an explicit voice: not handled here (try_join returns False), and the
     unknown name is logged to ~/.cache/speak-app/voice_misses.log.
Stdlib only.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import soundbite  # noqa: E402

CASTING = Path(__file__).parent.parent / "phrases" / "casting.json"
PROFILES = Path(os.getenv("SPEAK_PROFILES", Path(__file__).parent.parent / "phrases" / "profiles.json"))
MISS_LOG = Path("~/.cache/speak-app/voice_misses.log").expanduser()


class StoredClipsFailed(Exception):
    """The stored clips were found but would not play. Not a miss: the default path would pay to synthesize a line
    that is already paid for, then play it the same broken way."""


def load_casting() -> dict:
    """casting.json (models, clause menu) merged with profiles.json (profiles, assignments)."""
    return {**json.loads(CASTING.read_text()), **json.loads(PROFILES.read_text())}


def _norm(s: str) -> str:
    return soundbite.normalize(s)


def _bare(s: str) -> str:
    """Normalized with trailing punctuation dropped, so 'Merge it' matches the stored 'merge it?'."""
    return _norm(s).rstrip("?.!, ")


def resolve_cast(prefix: str, casting: dict) -> Optional[dict]:
    """Cockpit name -> profile dict plus 'name' (what its name clip says) and 'profile' (its id)."""
    key = _norm(prefix)
    candidates = [key] + [key[: -len(x)] for x in ("-cockpit", " lead") if key.endswith(x)]
    # A lane speaks as its cockpit: "claude-dev-harness-speak-menu" -> longest hyphen prefix that is an assignment.
    parts = key.split("-")
    candidates += ["-".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]
    assignments = {_norm(k): v for k, v in casting["assignments"].items()}
    for cand in candidates:
        a = assignments.get(cand)
        if a and a["profile"] in casting["profiles"]:
            return {**casting["profiles"][a["profile"]], "profile": a["profile"], "name": a.get("say", cand)}
    return None


def match_clause(tail: str, casting: dict) -> Optional[str]:
    want = _bare(tail)
    for clause in casting["clauses"]:
        if _bare(clause) == want:
            return clause
    return None


def expressive_settings(text: str, casting: dict) -> Optional[dict]:
    """ElevenLabs voice settings for a line recorded in the livelier style (casting.json "expressive"), else None."""
    ex = casting.get("expressive") or {}
    if _norm(text) in {_norm(t) for t in ex.get("lines", [])}:
        return ex.get("elevenlabs_settings")
    return None


def bite_model(entry: dict, casting: dict) -> str:
    """The model string the recorder stored the clip under (must match for the lookup to hit)."""
    if entry["provider"] == "openai":
        return casting["openai_model"]
    s = casting["elevenlabs_settings"]
    return f"{casting['elevenlabs_model']}|s{s['stability']:g}|b{s['similarity_boost']:g}"


def plan(text: str, casting: Optional[dict] = None):
    """Return ('join', entry, [paths]) | ('voice', entry) | ('miss', prefix) | None (not a 'name: tail' line)."""
    casting = casting or load_casting()
    prefix, sep, tail = text.partition(": ")
    if not sep or not tail.strip() or len(prefix) > 40:
        return None
    entry = resolve_cast(prefix, casting)
    if not entry:
        return ("miss", prefix)
    clause = match_clause(tail, casting)
    if clause:
        model = bite_model(entry, casting)
        name_clip = soundbite.lookup(entry["name"], entry["provider"], entry["voice"], model, 1.0)
        clause_clip = soundbite.lookup(clause, entry["provider"], entry["voice"], model, 1.0)
        if name_clip and clause_clip:
            return ("join", entry, [name_clip, clause_clip])
    return ("voice", entry)


def last_line(stderr: str) -> str:
    """The last non-empty stderr line (a provider script ends with its error), or a placeholder."""
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    return lines[-1][:200] if lines else "no error text"


def _log_miss(prefix: str) -> None:
    try:
        MISS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with MISS_LOG.open("a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{prefix}\n")
    except OSError:
        pass


def try_join(text: str, failures: Optional[list] = None) -> bool:
    """Speak `text` via the lead's voice if it names a cast lead. True only if it was spoken.
    Why a lead's voice did not play (API out of credit, playback error) is appended to `failures`."""
    failures = [] if failures is None else failures
    try:
        casting = load_casting()
        p = plan(text, casting)
        if p is None:
            return False
        if p[0] == "miss":
            print(f"voice map: no cast voice for '{p[1]}', using the default voice", file=sys.stderr)
            _log_miss(p[1])
            return False
        entry = p[1]
        if p[0] == "join":
            import playback
            try:
                playback.play_files(p[2])
            except Exception as e:
                failures.append(f"stored clips: {e}")
                raise StoredClipsFailed(str(e)) from e
            return True
        script = Path(__file__).parent / f"{entry['provider']}_tts.py"
        if entry["provider"] == "openai":
            cmd = [str(script), text, "--voice", entry["voice"], "--model", casting["openai_model"]]
        else:
            cmd = [str(script), text, "--voice-id", entry["voice"]]
        env = None
        style = expressive_settings(text, casting) if entry["provider"] == "elevenlabs" else None
        if style:  # the livelier recording is stored under these settings; the provider script reads them from env
            env = {**os.environ, "ELEVENLABS_STABILITY": f"{style['stability']:g}",
                   "ELEVENLABS_SIMILARITY_BOOST": f"{style['similarity_boost']:g}"}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
        if r.returncode != 0:
            failures.append(f"{entry['provider']} voice: {last_line(r.stderr)}")
        return r.returncode == 0
    except StoredClipsFailed:
        raise
    except Exception as e:
        print(f"phrase join failed, using the default path: {e}", file=sys.stderr)
        failures.append(f"lead voice: {e}")
        return False
