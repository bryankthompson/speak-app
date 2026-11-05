---
description: Play a voice profile's stored clips (its name and three menu clauses, or a given phrase). Never calls an API.
argument-hint: "PROFILE [TEXT]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh:*)
---

# /voice-audition

Arguments: `$ARGUMENTS`.

If no profile is given, run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" list` and ask which one to hear.
Otherwise run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" audition PROFILE [TEXT]`.

With no text it plays the profile id, then "what next?", "go or no-go?" and "is done". With text it plays that one
stored phrase. Exit 1 means a clip is not recorded (it names them and the `phrases/record.py --profile ID` command)
or the profile is unknown (it lists the ids). Report that; do not record anything.
