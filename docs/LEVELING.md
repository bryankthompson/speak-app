# Leveling the soundbite voices

Even out loudness across the voices in the soundbite library with `tts/level_clips.py`.

## Why

The voices differed by about 17 dB, so some were muffled and weak and hard to understand next to others. Bryan
listened to the leveled result: "level, smooth, easy to understand... before they sounded muffled and weak; it's
the compression bringing out the frequencies that were too low".

## What was measured

Library of 35 voices, target -18 LUFS (median per voice, BS.1770 integrated loudness):

| Stage | Spread between voices |
|---|---|
| Before | 15.41 LU |
| Compression alone (before the gain) | 7.65 LU |
| Full chain (verify, after apply) | 0.38 LU |

Clips the limiter had to act on: 1,874 (34%) with gain only, 613 (11%) with compression first. The compressor
lowers peaks, so the gain a quiet voice needs no longer drives most clips into the limiter.

## The chain

One ffmpeg re-encode per clip, settings in `CHAIN_DEFAULTS` (tts/level_clips.py), used by both `measure` and `apply`:

| Stage | Setting | Why |
|---|---|---|
| highpass | 80 Hz | Removes rumble below speech that costs headroom and loudness reading; speech has nothing there. |
| acompressor | threshold -24 dB, ratio 2.5:1, attack 8 ms, release 120 ms, makeup 1 | Gentle: it lifts the quiet parts and brings out the low-level frequencies without pumping. 8 ms attack lets the first consonant through. |
| volume | gain per voice | Moves the voice median to the target. |
| alimiter | -1 dBFS (0.891), attack 5 ms, release 50 ms | Catches what the gain pushes over. |
| peak guard | decoded peak <= -0.8 dBFS | libmp3lame re-encoding overshoots the limiter ceiling; see the safety model. |

- **Gain per voice, not per clip**: clips of one voice keep their natural differences (a shout stays louder than a
  whisper); only the voices are brought together. Per-clip gain would flatten every line to the same level.
- **Clips under 1 s are left out of the median** (`MIN_MEDIAN_SECONDS`): BS.1770 is unreliable on them (some give no
  value at all). They still get the voice gain and still count for peaks.
- **sfx is untouched**: it is not speech and the provider `sfx` is skipped everywhere.
- A voice whose gain is under 0.5 dB (`MIN_GAIN_DB`) is left alone.

## Tooling

- Measurement uses `~/audio-observation-core` (BS.1770 loudness and peak, `loudness_block` and `levels_block`). It
  needs numpy, scipy, soxr and soundfile; the script re-runs itself under `uv run --with ...` when they are missing.
- ffmpeg does all the processing.
- The Matchering `master.py` on nashville-suno-studio, branch `private/full-state`, was considered and not used:
  it is built for whole music tracks, not short speech clips.

## Commands

All run as `python3 tts/level_clips.py <command>`. `--library` defaults to `$SOUNDBITE_DIR`, else `~/soundbite`.

```
python3 tts/level_clips.py measure [--library DIR] [--target -18] [--out PLAN] [--ratio 2.5] [--threshold-db -24] [--force-remeasure]
python3 tts/level_clips.py apply PLAN [--library DIR] [--dry-run]
python3 tts/level_clips.py verify [--library DIR] [--target -18] [--sample N]
python3 tts/level_clips.py run [--library DIR] [--target -18] [--out PLAN] [--dry-run]
```

- `measure`: read-only. Renders each clip through highpass and compressor, reads the loudness, prints the table
  (gain, clips the limiter would touch, `LIMITER-HEAVY` flags) and writes the plan with `--out` (plus
  `PLAN.table.txt`). It refuses a library whose `levels-applied.jsonl` has any `done` line (measuring leveled
  clips would plan gains near 0 while `apply` compressed them again); `--force-remeasure` overrides it with a
  warning that the originals must be restored before `apply`.
- `apply PLAN`: re-encodes clips in place, same path and manifest key, updates manifest `bytes`. `--dry-run` lists
  what it would do.
- `verify`: measures the library and exits 1 if the spread across voices is over 3 LU or any peak is above
  -0.5 dBTP. `--sample N` checks N clips per voice.
- `run`: measure, table, apply, verify; prints each step name and stops with a non-zero exit at the first failure.
  Without `--out` the plan goes to `~/.cache/speak-app/level-plan.json`. It refuses a dirty library tree before
  doing anything. `--dry-run` is measure plus `apply --dry-run` (no tree check, nothing written but the plan).

## Safety model

- **Clean tree and a snapshot**: `apply` refuses if the library git tree has uncommitted changes. Commit the library
  first; that commit is the snapshot to restore from.
- **Write-ahead journal** `<library>/levels-applied.jsonl`: a `pending` line (with the old file's sha256) before each
  replace, a `done` line (bytes, `extra_atten_db`, `peak_dbfs`) after. A crashed run resumes by rerunning the same
  command: a clip whose file already changed is marked done and never leveled twice; one that did not is redone.
- **Plan hash**: the plan carries a hash of target, chain and gains. `apply` refuses an edited plan, and a library
  whose journal belongs to another plan (it prints the restore command).
- **Restore**: when `apply` refuses for another plan it prints the exact command: `git checkout` of every journaled
  file and of `manifest.json` from the snapshot commit, then removal of the journal.
- **Post-encode peak guard**: after encoding to a temp file and before the replace, `apply` decodes it and measures
  the sample peak. Above `PEAK_GUARD_DBFS` (-0.8) it re-encodes from the original with extra attenuation after the
  limiter (overshoot + 0.3 dB), up to 3 more tries; if still over it stops non-zero and names the clip. The
  attenuation used is `extra_atten_db` in the journal. Without it, 9 of 5,587 clips came out above the verify limit
  (worst +1.3 dBFS, clipping).

## Hear a before/after

Take a clip from the snapshot commit and the leveled file, then play both:

```
git -C ~/soundbite show SNAPSHOT:openai/onyx/CLIP.mp3 > /tmp/before.mp3
cp ~/soundbite/openai/onyx/CLIP.mp3 /tmp/after.mp3
```

Pick the real path from `levels-applied.jsonl` (`file`). To render a leveled copy of any file without touching the
library, run the chain by hand with `ffmpeg -i in.mp3 -af "<chain_filter output>" out.mp3`; `chain_filter` in
tts/level_clips.py builds the string.

## Leveling new clips

- **New clips of an already-leveled voice**: commit the library (new files, manifest and journal), then rerun
  `apply` with the same plan file. It levels only the clips not in the journal, with that voice's gain, and leaves
  the leveled ones alone. Tested in tests/test_level_clips.py.
- **A new voice is not supported yet**: the plan has no gain for it, and `measure` refuses a leveled library, so
  there is no way to add one short of restoring the originals and re-running everything.

## Known limits

- CI runs only tests/test_soundbite.py; tests/test_level_clips.py is run locally.
- A torn last journal line after a power loss is ignored with a warning, not truncated.
- The first play of a freshly recorded clip is not leveled; it is leveled by the next `apply`.
