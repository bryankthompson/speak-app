---
description: Point a cockpit at a voice profile (writes phrases/profiles.json in the speak-app checkout). Says if the cockpit's name clip still needs recording.
argument-hint: "COCKPIT PROFILE [SAY]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh:*)
---

# /voice-assign

Arguments: `$ARGUMENTS` (cockpit name, profile id, and optionally the words the name clip should say).

1. If either the cockpit or the profile is missing, run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" list`, show it, and ask which profile to use. Do not guess.
2. Run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" assign COCKPIT PROFILE [SAY]`. A multi-word cockpit name goes in quotes.
3. Report the line it prints (`name -> profile: N/M clips stored`). If it says clips are missing, give the user the
   record command it printed, and say that recording calls a paid API: they run it themselves, after
   `phrases/record.py --provider PROVIDER --assigned --dry-run` to see the cost. Never run a recording.

The cockpit name is stored lower-case. A trailing `-cockpit` or ` lead` in a spoken line is dropped before lookup,
so assign the bare name (`hades`, not `hades-cockpit`).
