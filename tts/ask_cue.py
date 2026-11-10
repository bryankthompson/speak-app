#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: say "<repo>: needs your answer" from stored clips.

A session that asks the user through AskUserQuestion has no prose to speak, so this is the one deterministic
"needs your answer" cue. It reads the hook payload on stdin, names the cockpit after the repo's main checkout
(worktrees and lanes follow it, as in the speak gate), applies the per-repo gate and records spoke/skipped in
speech.log like `speak` does. It plays only two stored clips (the repo's name clip and the clause), in a detached
child so the question dialog never waits; it never calls `speak`, so it cannot fall back to synthesizing the line
(a paid call). With no assigned voice, a missing clip or plain-voice mode it stays silent and writes the reason to
~/.cache/speak-app/ask_cue.log. Always exits 0: a hook failure must never block the question.
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
LOG = Path.home() / ".cache" / "speak-app" / "ask_cue.log"


def _log(log_path, kind, msg):
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(f"{time.strftime('%F %T')}\t{kind}\t{msg}\n")
    except OSError:
        pass


def run(stdin_text, spawn=subprocess.Popen, log_path=LOG):
    """Returns the text it played, or None. Never raises."""
    try:
        payload = json.loads(stdin_text or "{}")
        if payload.get("tool_name") != "AskUserQuestion":
            return None
        root, _ = repo_gate.repo_root(payload.get("cwd") or os.getenv("CLAUDE_PROJECT_DIR"))
        text = f"{root.name.lower()}: {CLAUSE}"
        allow, voices, repo, reason = repo_gate.decide(cwd=root)
        if not allow:
            repo_gate.log(reason, repo, text)  # an unlisted repo stays silent; the skip shows in speak --repos
            return None
        if not voices:
            _log(log_path, "silent", f"{root.name}: plain-voice repo (no cockpit voice to play)")
            return None
        p = phrase_join.plan(text)
        if p is None or p[0] == "miss":
            _log(log_path, "silent", f"{root.name}: no cast voice (assign one: speak --assign)")
            return None
        if p[0] != "join":
            _log(log_path, "silent", f"{root.name}: name clip or '{CLAUSE}' not stored for its voice "
                                     f"(record it: phrases/record.py --assigned)")
            return None
        repo_gate.log(reason, repo, text)
        spawn([sys.executable, str(Path(__file__).resolve()), "--play", *map(str, p[2])],
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True)
        return text
    except Exception as e:  # noqa: BLE001 - a cue must never block the question
        _log(log_path, "failed", f"{type(e).__name__}: {e}")
        return None


def play(paths, log_path=LOG):
    """The detached child: play these stored files. It has no way to synthesize anything."""
    try:
        import playback
        playback.play_files([Path(p) for p in paths])
    except Exception as e:  # noqa: BLE001
        _log(log_path, "failed", f"play: {type(e).__name__}: {e}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--play"]:
        play(sys.argv[2:])
    else:
        run(sys.stdin.read())
    sys.exit(0)
