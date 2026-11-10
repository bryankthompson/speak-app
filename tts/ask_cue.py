#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: say "<repo>: needs your answer" from stored clips.

A session that asks the user through AskUserQuestion has no prose to speak, so this is the one deterministic
"needs your answer" cue. It reads the hook payload on stdin, names the cockpit after the repo's main checkout
(worktrees and lanes follow it, as in the speak gate), and starts `speak` detached so the question dialog never
waits for the clip. `speak` applies the per-repo gate (an unlisted repo stays silent) and records spoke/skipped
in speech.log. It speaks only when the cue plays from stored clips (the repo has an assigned voice, its name clip
and the clause are stored, and it is not in plain-voice mode); otherwise `speak` would synthesize the whole line, a
paid call, so the hook stays silent and writes the reason to ~/.cache/speak-app/ask_cue.log. Always exits 0: a hook
failure must never block the question.
Stdlib only.  Wire it up in ~/.claude/settings.json (docs/VOICES-COCKPIT.md).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import phrase_join  # noqa: E402
import repo_gate  # noqa: E402

CLAUSE = "needs your answer"
SPEAK = Path(__file__).resolve().parent.parent / "speak"
LOG = Path.home() / ".cache" / "speak-app" / "ask_cue.log"


def _log(log_path, kind, msg):
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(f"{time.strftime('%F %T')}\t{kind}\t{msg}\n")
    except OSError:
        pass


def not_free(root, text):
    """Why `speak text` would not play from stored clips (so it could pay for synthesis), else None."""
    allow, voices, _repo, _reason = repo_gate.decide(cwd=root)
    if not allow:
        return None  # an unlisted repo: speak skips it for free and records the skip
    if not voices:
        return f"{root.name}: plain-voice repo (speak would synthesize the whole line)"
    p = phrase_join.plan(text)
    if p is None or p[0] == "miss":
        return f"{root.name}: no cast voice (assign one: speak --assign)"
    if p[0] != "join":
        return f"{root.name}: name clip or '{CLAUSE}' not stored for its voice (record it: phrases/record.py --assigned)"
    return None


def run(stdin_text, spawn=subprocess.Popen, log_path=LOG):
    """Returns the text it launched `speak` with, or None. Never raises."""
    try:
        payload = json.loads(stdin_text or "{}")
        if payload.get("tool_name") != "AskUserQuestion":
            return None
        root, _ = repo_gate.repo_root(payload.get("cwd") or os.getenv("CLAUDE_PROJECT_DIR"))
        text = f"{root.name.lower()}: {CLAUSE}"
        why = not_free(root, text)
        if why:
            _log(log_path, "silent", why)
            return None
        # speak applies its own gate from its working directory: pin it to the repo this hook just decided about
        spawn([str(SPEAK), text], cwd=str(root), env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True)
        return text
    except Exception as e:  # noqa: BLE001 - a cue must never block the question
        _log(log_path, "failed", f"{type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    run(sys.stdin.read())
    sys.exit(0)
