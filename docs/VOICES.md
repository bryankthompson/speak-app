# Voices: profiles, the soundbite library and cockpit lines

A **profile** is a named voice: a provider (OpenAI or ElevenLabs), that provider's voice id, and a one-line
character. Each cockpit (a Claude Code session that speaks, such as `hades` or `governor`) is **assigned** a
profile, so you can tell who is talking without looking. Every clip that has been paid for once is kept in the
**soundbite library**, and a line made of a cockpit name plus a fixed **clause** ("go or no-go?", "is done") is played
from two stored clips, with no API call. Other text is spoken whole in that cockpit's voice and stored too.

| File | Holds |
|---|---|
| `phrases/profiles.json` | `profiles` (id -> provider, voice, character, optional label and account) and `assignments` (cockpit -> profile, optional `say`) |
| `phrases/casting.json` | `openai_model`, `elevenlabs_model`, `elevenlabs_settings` and `clauses`, the fixed menu |
| `~/soundbite` (or `$SOUNDBITE_DIR`) | the library: `manifest.json` plus `<provider>/<voice>/<slug>-<hash8>.mp3`, its own local git repo |
| `tts/profiles.py`, `tts/phrase_join.py`, `tts/soundbite.py`, `tts/playback.py` | list/assign/audition, the line resolver, the library, playback |
| `phrases/record.py`, `phrases/sfx.py` | the recorders (the only parts that call a paid API on purpose) |

Library basics, backup and restore are also in docs/SOUNDBITE.md.

## Quick path

    speak --profiles                     # every profile, menu clips stored, who uses it
    speak --profile fable                # hear it: "fable", "what next?", "go or no-go?", "is done"
    speak --assign my-cockpit fable      # give a cockpit that voice
    speak "my-cockpit: go or no-go?"     # name clip + clause clip, no API call

`speak --assign` prints `my-cockpit -> fable: 157/158 clips stored` and, when the name clip is not recorded yet,
the command that records it. Until it is recorded, that cockpit's lines are spoken whole by the provider (paid once,
then stored).

## Commands

All of these are read-only and make no API call unless the table says otherwise.

| Command | Does | Fails with |
|---|---|---|
| `speak --profiles` | one row per profile: id, provider, stored/total menu clips, character, `used by:` cockpits. Assigned profiles first | exit 0 |
| `speak --profile ID [TEXT]` | plays the stored clips for `ID`: its name and three sample clauses, or the one stored `TEXT` | exit 1: unknown id (lists the ids), or a clip not recorded (names it and the `record.py --profile ID` command). Never calls the API |
| `speak --assign COCKPIT PROFILE` | writes the assignment to `phrases/profiles.json` (cockpit stored lower-case), prints clip coverage | exit 1: unknown profile, or fewer than two arguments |
| `python3 tts/profiles.py assign COCKPIT PROFILE SAY` | as `--assign`, and sets `say`: the words the name clip speaks when they differ from the cockpit name | as above |
| `speak "NAME: TEXT"` | a cockpit line, resolved as below | exit 1 if the provider fails |
| `speak --off "..."` | skips speech for this call (for loops) | exit 0 |
| `speak --status`, `speak --list` | env settings (keys shown only as configured or not) and the providers that are available | |
| `speak-dev "..."` | always the offline pyttsx3 voice | |
| `python3 tts/soundbite.py stats` | clip count, size and clips per voice | exit 0 |
| `python3 tts/soundbite.py list [--provider P] [--voice V]` | every stored phrase | exit 0 |
| `phrases/record.py --provider openai --dry-run` | what would be recorded, characters and dollars; no API call | exit 0 |
| `phrases/record.py --provider elevenlabs --dry-run` | the same for ElevenLabs, in characters and credits. Over the whole cast this takes minutes (one manifest read per clip); narrow it with `--only` or `--profile` | exit 0 |
| `phrases/record.py --provider P [--assigned]` | **calls the API.** Records each assigned cockpit's name clip and the clause menu in its voice; skips stored clips | exit 2 on the first ElevenLabs auth/quota error (401/402/429), a 404 skips that voice; an OpenAI error stops the run |
| `phrases/record.py --provider P --profile ID` | **calls the API.** Records `ID`'s audition set (the id as the name clip, plus the menu). Repeatable | as above |
| `phrases/record.py --provider P --only ID1,ID2` | limits any run to those profile ids | |
| `phrases/record.py --provider P --reindex` | re-adds mp3s that are on disk but missing from the manifest; no API call | exit 0 |
| `python3 phrases/sfx.py --dry-run` / `python3 phrases/sfx.py` | the state sounds, see below; without `--dry-run` it **calls the API** | exit 2 on the first error |
| `./run_local.sh [--port N] [--open]`, `--status`, `--stop` | the local voice gallery, see below | exit 1: gallery module not found, or nothing on the port |

`record.py` needs `--provider`, and always reads `phrases/profiles.json` beside it. `SPEAK_PROFILES=FILE` points
`speak` (lines, `--profiles`, `--assign`, `--profile`) at another profiles file, for example a copy to try an
assignment on; `record.py` ignores it.

## Per-repo control

One central file, `~/.config/speak-app/repos.json`, decides which repos speak:

    {"gate": true, "repos": {"/abs/path/to/main/checkout": {"voices": true}}}

With no file, or `"gate": false`, everything speaks as before. With the gate on, a repo speaks only if it is listed.
`"voices": false` gives that repo the plain default voice (no cockpit voice, no name+clause join). Worktrees and lanes
follow their main checkout; a folder outside git uses its nearest listed parent, else stays silent.

- `speak --here` shows this repo's entry; `speak --here on` lists it (add the word `--plain` after `on` for the plain voice); `speak --here off` removes it.
- `speak --repos` lists the repos seen in the last 7 days with counts, whether each is listed, and the gate state.
- `speak --gate on` / `speak --gate off` switches the gate.
- For scripts: `speak --here` accepts the words `--json` (one JSON object: repo, listed, voices, gate, speaks) and `--check` (no output; exit 0 if the repo would speak, 1 if not). `speak --brief` prints the short guide a cockpit prompt can embed (plugins/speak-voices/BRIEF.md); it exits 1 with a message if the file is missing.
- `speak --alert "text"` marks a warning: it always speaks, in the repo's own voice setting (plain if unlisted).
  Warnings are errors and failures, safety blocks, budget and spend, credits, and disk or keys low or expired.
  `speak --test` is an alert.

A skipped line prints `skipped: REPO not enabled; run: speak --here on` and exits 0. An invalid registry skips
non-alert lines with the reason on stderr and exit 3; alerts still speak. Every decision (spoke, skipped, alert,
invalid) is appended to `~/.cache/speak-app/speech.log`, also while the gate is off.

## How a cockpit line is resolved

`speak "NAME: TEXT"` is split at the first `": "`; the name must be 40 characters or fewer. Code: `tts/phrase_join.py`.

| Line | Result |
|---|---|
| known name + known clause, both clips stored | the name clip and clause clip play back to back. No API call |
| known name + any other text, or a clause not yet stored | the whole line is spoken in that cockpit's voice, and saved to the library, so the same line is free next time |
| unknown name | the default voice speaks the line, and the name is appended to `~/.cache/speak-app/voice_misses.log` |
| no `": "`, `--voice` given, or `TTS_ENABLED=false` | no join; speak runs as usual |

The name is matched lower-case against the assignments, then again with a trailing `-cockpit` or ` lead` dropped
(`hades-cockpit: done` finds `hades`). The clause is matched ignoring case, extra spaces and trailing `?.!,`
(`Merge it` matches `merge it?`). The name clip says the assignment's `say` value if it has one, otherwise the
cockpit name.

## Add a voice

1. Add an entry under `profiles` in `phrases/profiles.json`:

       "ruth": {"provider": "elevenlabs", "voice": "<ElevenLabs voice id>", "character": "calm reviewer",
                "label": "Ruth", "account": "<which ElevenLabs account can use it>"}

   `account` is a note for you; nothing reads it. Shared-library voices work only on the account that added them.
2. Check the cost: `phrases/record.py --provider elevenlabs --profile ruth --dry-run`. It prints
   `N clips to record, C chars, C/2 credits at the measured 0.5/char (C worst case)`. ElevenLabs bills per character;
   0.5 per character is what was measured on this account, the worst case is one per character. For OpenAI it prints
   dollars from the published rate for `openai_model` (unverified in the code).
3. Record it with that account's key: `phrases/record.py --provider elevenlabs --profile ruth`.
4. `speak --profile ruth` to hear it, then `speak --assign COCKPIT ruth`.

A full menu is 157 clauses plus the name clip per voice; most voices in the library hold 158 clips.

## Add a clause

Append it to the end of `clauses` in `phrases/casting.json`, then run the dry-run and the recording for each provider
(`--assigned` covers every assigned voice). Never rename or respell a clause: clips are keyed on the exact text, so a
changed spelling orphans every stored clip of it, and cockpit briefs that use the old spelling fall back to paid,
whole-line speech. The spellings are a contract with the cockpit lead brief.

## Sound effects

`phrases/sfx.py` makes eight short state sounds (`done`, `merged`, `question`, `needs-you`, `blocked`, `alert`,
`error`, `start`, 1.5 s each) with ElevenLabs sound generation and stores them under provider `sfx`, voice
`elevenlabs`. `--dry-run` prints how many are missing and the credits (about 15 each). Nothing in speak plays them
yet; they are stored for callers that want an earcon.

## Library health

- `python3 tts/soundbite.py stats`: counts per voice. A voice well below the others is missing clips.
- `speak --profiles`: `have/want menu` per profile.
- Missing files: a manifest entry whose mp3 is gone is treated as a miss, so it would be paid for again. The
  `/voice-health` plugin command counts them. Restore from the backup rather than re-record.
- Files on disk but not in the manifest: `phrases/record.py --provider P --reindex` re-adds them, no API call.
- Unknown names: `~/.cache/speak-app/voice_misses.log` (time, name per line). Assign each, or ignore it.

## Gallery (local only)

`./run_local.sh` serves a read-only page of every profile and the library on `http://127.0.0.1:8765`
(`--port N`, `--open` opens a browser, `--status`, `--stop`). It makes no API calls. Its module,
`tts/library_web.py`, is not on main yet: it lives on the unmerged branch `lane/voice-gallery`, and `run_local.sh`
looks for it in a sibling `../speak-app-voice-gallery` checkout until then.

## Backups

`~/soundbite` and this repo's `phrases/` are in the nightly encrypted `repo-backup`. The restore command is in
docs/SOUNDBITE.md.

## Keys

The recorders read `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` from the environment. Read them from 1Password with `op`
for the one command, never paste them into a file or a chat:

    OPENAI_API_KEY="$(op read 'op://<vault>/<item>/<field>')" phrases/record.py --provider openai

Listing, assigning, auditioning, stats, `--dry-run` and `--reindex` need no key.

## Claude Code plugin

`plugins/speak-voices` wraps these as `/voices`, `/voice-assign`, `/voice-audition` and `/voice-health`, plus a
skill on the line rules. How cockpits use all this: docs/VOICES-COCKPIT.md.
