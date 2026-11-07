# Soundbite library and voice profiles

Spoken audio is paid for once and stored. `speak` looks in the library first and only calls an API on a miss.

- **Library**: `~/soundbite` (override with `SOUNDBITE_DIR`), a separate local git repo: `manifest.json` plus `<provider>/<voice>/<slug>-<hash>.mp3`. Key = text, provider, voice, model, speed. Code: `tts/soundbite.py`.
- **Profiles**: `phrases/profiles.json` holds voice profiles and which cockpit uses which. `phrases/casting.json` holds the models and the clause menu. `speak --profiles` lists them, `speak --profile ID` auditions one from stored clips, `speak --assign COCKPIT PROFILE` re-points a cockpit.
- **Lines**: `speak "<cockpit>: <clause>"` plays the stored name clip then clause clip in that cockpit's voice; other text is spoken whole in the same voice and stored. Code: `tts/phrase_join.py`.
- **Recording**: `phrases/record.py --provider openai|elevenlabs [--only IDS | --profile ID] [--dry-run]`. It skips stored clips and stops on the first quota or auth error. `--reindex` re-adds clips that are on disk but missing from the manifest (no API calls). Keys come from the environment; use `op` to read them, never paste them.
- **Gallery**: `./run_local.sh [--open]` shows every voice and the library on `127.0.0.1:8765` (`--stop`, `--status`).
- **Backup**: `~/soundbite` and this repo's `phrases/` are in the nightly encrypted `repo-backup`. Restore into a scratch folder: `~/bin/repo-backup restore soundbite --identity KEYFILE --to DIR` (the age key is held by the operator).
- `phrases/corpus.tsv` (mined real phrases) stays local and is git-ignored.
