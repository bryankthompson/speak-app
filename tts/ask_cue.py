#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: say "<repo>: needs your answer" from stored clips.

A session that asks the user through AskUserQuestion has no prose to speak, so this is the one deterministic
"needs your answer" cue. It reads the hook payload on stdin, names the cockpit after the repo's main checkout
(worktrees and lanes follow it, as in the speak gate), and starts `speak` detached so the question dialog never
waits for the clip. `speak` applies the per-repo gate (an unlisted repo stays silent) and records spoke/skipped
in speech.log. The name clip and the clause are both stored, so this costs nothing. Always exits 0: a hook
failure must never block the question. A failed launch is logged to ~/.cache/speak-app/ask_cue.log.
Stdlib only.  Wire it up in ~/.claude/settings.json (docs/VOICES-COCKPIT.md).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import repo_gate  # noqa: E402

CLAUSE = "needs your answer"
SPEAK = Path(__file__).resolve().parent.parent / "speak"
LOG = Path.home() / ".cache" / "speak-app" / "ask_cue.log"


def run(stdin_text, spawn=subprocess.Popen, log_path=LOG):
    """Returns the text it launched `speak` with, or None. Never raises."""
    try:
        payload = json.loads(stdin_text or "{}")
        if payload.get("tool_name") != "AskUserQuestion":
            return None
        root, _ = repo_gate.repo_root(payload.get("cwd") or os.getenv("CLAUDE_PROJECT_DIR"))
        text = f"{root.name.lower()}: {CLAUSE}"
        spawn([str(SPEAK), text], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, start_new_session=True)
        return text
    except Exception as e:  # noqa: BLE001 - a cue must never block the question
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as f:
                f.write(f"{time.strftime('%F %T')}\tfailed\t{type(e).__name__}: {e}\n")
        except OSError:
            pass
        return None


if __name__ == "__main__":
    run(sys.stdin.read())
    sys.exit(0)
