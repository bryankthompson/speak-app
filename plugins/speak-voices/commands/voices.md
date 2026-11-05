---
description: List speak-app voice profiles, how many of the clause menu each has stored, and which cockpits use each one. Read-only.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh:*)
---

# /voices

Run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" list` and show its output as is.

Each row is: profile id, provider, stored menu clips / menu size, the one-line character, and the cockpits assigned to it.
Profiles that a cockpit uses come first. If the script exits 1 with "no speak-app checkout", tell the user to set
`SPEAK_APP_DIR` to their speak-app clone (default `~/speak-app`) and stop.
