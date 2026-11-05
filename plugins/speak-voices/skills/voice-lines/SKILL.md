---
name: voice-lines
description: How speak-app turns a cockpit line like `speak "hades: go or no-go?"` into audio - which lines play free from stored clips, which call the API, and how to keep it free. Use when writing a speak line for a cockpit, choosing a clause, or asking why a line used the default voice.
---

# How a cockpit line is spoken

**First, is this repo allowed to speak?** With the per-repo gate on (`~/.config/speak-app/repos.json`), `speak` is silent in a repo
that is not listed: it prints `skipped: <repo> not enabled; run: speak --here on` and exits 0. Enable a repo with `speak --here on`
from inside it (lanes and worktrees follow their main checkout). Warnings use `speak --alert "text"`, which always speaks.
Cockpit lines such as "needs your answer" are not warnings; they follow the repo's setting. `speak --repos` shows who spoke or was skipped.

`speak "<name>: <text>"` is split at the first `": "`. The name part must be 40 characters or fewer.

1. **Name.** Lower-cased and matched against the assignments in `phrases/profiles.json`. If no match, a trailing
   `-cockpit` or ` lead` is dropped and it tries again (`hades-cockpit` finds `hades`).
2. **Known name + known clause** (the text equals a clause in `phrases/casting.json`, case and trailing `?.!,` ignored):
   the stored name clip and clause clip play back to back. No API call.
3. **Known name + any other text**, or a known clause whose clips are not stored yet: the whole line is spoken in that
   cockpit's voice by its provider, and the audio is saved to the library, so the same line is free next time.
4. **Unknown name:** the default voice speaks the line, and the name is appended to `~/.cache/speak-app/voice_misses.log`.
5. No `": "`, an explicit `--voice`, or `TTS_ENABLED=false`: the join is skipped and speak runs as usual.

To keep a line free, use a clause from `phrases/casting.json` spelled as it is there. Clauses are append-only:
renaming one orphans every stored clip of it.

Full guide: docs/VOICES.md in the speak-app checkout (`$SPEAK_APP_DIR`, default `~/speak-app`).
