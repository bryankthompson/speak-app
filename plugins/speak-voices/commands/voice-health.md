---
description: Check the soundbite library - clip counts per voice, manifest entries whose mp3 is gone, and cockpit names that had no voice. Read-only.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh:*)
---

# /voice-health

Run `"${CLAUDE_PLUGIN_ROOT}/scripts/speak-voices.sh" health` and summarise it in three lines:

- the total clips and size, and any voice whose count is well below the others;
- `missing files: N` - if N > 0 those clips would be paid for again; suggest restoring them from the backup
  (docs/SOUNDBITE.md in the speak-app checkout) before recording;
- unknown cockpit names - each one is a cockpit that spoke in the default voice; suggest `/voice-assign NAME PROFILE`.

Clips on disk but missing from the manifest are not shown here. To re-add them, the user runs
`phrases/record.py --provider openai --reindex` (and `--provider elevenlabs`) in the checkout; it makes no API calls.
