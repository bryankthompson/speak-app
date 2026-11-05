# speak-voices

A Claude Code plugin over a local speak-app checkout. Commands:

| Command | Does | Writes |
|---|---|---|
| `/voices` | lists profiles, stored menu clips, and which cockpits use each | nothing |
| `/voice-assign COCKPIT PROFILE [SAY]` | points a cockpit at a profile | `phrases/profiles.json` |
| `/voice-audition PROFILE [TEXT]` | plays stored clips only | nothing |
| `/voice-health` | clip counts, missing mp3s, unknown cockpit names | nothing |

The skill `voice-lines` explains how a `speak "<name>: <text>"` line is resolved.

None of them calls a TTS API or records. The checkout is `$SPEAK_APP_DIR` (default `~/speak-app`); if it is not
there, every command exits 1 and says so.

Install from a clone of speak-app:

    claude plugin marketplace add ~/speak-app
    claude plugin install speak-voices@speak-app

Full guide: docs/VOICES.md.
