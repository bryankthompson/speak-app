# Voices for dev-harness cockpits

How the cockpit leads and lanes of the dev-harness use speak-app voices. The user guide is docs/VOICES.md.

## The lead-brief line

The dev-harness cockpit-lead template (`templates/cockpit/domains/cockpit-lead.md` in the dev-harness repo) gives
this instruction to every lead:

    When you need direction, run `speak "<session name>: <question in 10 words or fewer>"`,
    then end the turn with a QUESTION:/BLOCKED: block.

So every lead line has the form `NAME: TEXT`, which is what speak-app's join reads. With the session name assigned
to a profile, the line is spoken in that cockpit's voice. When the text is a clause from `phrases/casting.json`
(`go or no-go?`, `needs you now`, `is done`, ...), it plays from two stored clips for free; free text is spoken whole
once and stored.

In progress, not yet merged: the harness lead is changing this line (lane `speak-menu`) to a menu of
`<name>: <fixed clause>` with free text as the fallback, the list read from `casting.json`. Until that merges, the
line above is what leads are told.

## The "needs your answer" cue (AskUserQuestion hook)

A lead that asks the user through AskUserQuestion has no prose to speak, so a PreToolUse hook says
`<repo>: needs your answer` from stored clips (free; no API call). `tts/ask_cue.py` reads the hook payload, names the
cockpit after the repo's main checkout (worktrees and lanes follow it), and starts `speak` detached so the dialog never
waits for the clip. The per-repo gate still applies (an unlisted repo stays silent). It always exits 0; a failed launch
is written to `~/.cache/speak-app/ask_cue.log`, and `speak --repos` shows what was spoken or skipped.

Wire it once in `~/.claude/settings.json`, in the `PreToolUse` list next to the safety hook (`|| true` keeps a missing
script from blocking the question):

    {"matcher": "AskUserQuestion", "hooks": [{"type": "command",
      "command": "python3 /home/bryan/speak-app/tts/ask_cue.py || true"}]}

Remove that entry to turn the cue off.

## Assignments are keyed by cockpit name

`assignments` in `phrases/profiles.json` maps a lower-case cockpit name to a profile. Give each spelling a lead
actually says its own entry; several names may share a profile, as the dev-harness does:

    "claude-dev-harness": {"profile": "echo", "say": "harness lead"},
    "dev-harness":        {"profile": "echo", "say": "harness lead"},
    "harness lead":       {"profile": "echo"}

`say` is what the name clip speaks, so every alias plays the same recorded "harness lead". A trailing `-cockpit` or
` lead` is dropped before lookup, so `hades-cockpit` and `hades lead` both reach `hades`.

## Giving a new cockpit a voice

1. `speak --profiles` and pick a profile, ideally one with `used by: -` so voices stay distinct.
2. `speak --profile ID` to hear it (stored clips only).
3. `speak --assign COCKPIT ID`. To set the spoken name too: `python3 tts/profiles.py assign COCKPIT ID "SAY"`.
4. If it reports a missing clip (the new name), see the cost with
   `phrases/record.py --provider PROVIDER --assigned --dry-run`, then record it without `--dry-run`. One clip of a
   short name costs a few characters.

Until step 4, the cockpit's lines are spoken whole in its voice (paid once per distinct line, then stored). A
cockpit that was never assigned speaks in the default voice and its name lands in
`~/.cache/speak-app/voice_misses.log`; check that log to find cockpits that need a voice.

From Claude Code, the speak-voices plugin does the same: `/voices`, `/voice-audition ID`,
`/voice-assign COCKPIT ID [SAY]`, `/voice-health`.

## What the dev-harness does and does not do

- **Does:** tells leads (the template above) and lanes (the `speak_rule` in `scripts/cockpit`) to speak
  `"<session name>: <question>"`. The session name is what speak-app looks up.
- **Does, separately:** its own "held message" ding. When a lead holds a message, the harness plays a phrase it
  makes once with ElevenLabs and keeps in `~/.cache/dev-harness/ding/`, tuned by `~/.config/dev-harness/ding.json`
  (docs/cockpit.md in the dev-harness repo). That path does not use speak-app's profiles or library.
- **Does not:** read `profiles.json`, assign voices, record clips or install this plugin. Voices are set in
  speak-app, by hand or with the plugin.

## Installing the plugin

From a speak-app clone (the repo has a `.claude-plugin/marketplace.json`, the same layout the dev-harness uses):

    claude plugin marketplace add ~/speak-app
    claude plugin install speak-voices@speak-app

Set `SPEAK_APP_DIR` if the clone is not at `~/speak-app`; without a checkout every command exits 1 and says where it
looked.
