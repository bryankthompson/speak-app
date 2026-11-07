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
| peak guard | decoded true peak <= -0.8 dBTP | libmp3lame re-encoding overshoots the limiter ceiling, and the wave between samples overshoots the samples; see the safety model. |

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
python3 tts/level_clips.py fix-peaks [--library DIR] [--dry-run]
python3 tts/level_clips.py add-voice VOICE_ID... [--library DIR] [--plan PLAN]
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

- `add-voice VOICE_ID...` (for example `openai/onyx`): measures only the named voices with the plan's chain and
  target and adds their gains to the plan (default `$SOUNDBITE_PLAN`, else `<library>/level-plan.json`). It refuses a
  voice already in the plan, one with `done` lines in the journal, or one with no clips, and leaves the plan
  unchanged if any clip cannot be measured. It does not touch the audio: commit the library, then run `apply` with the
  updated plan.
- `fix-peaks`: measures the true peak of every non-sfx clip (the same number `verify` uses) and cuts each clip over
  -0.5 dBTP in place, from its current leveled audio, with a plain volume cut to about -1.0 dBTP (up to 3 tries,
  checked on the decoded file). Same temp file, decode check and `os.replace` as `apply`; updates manifest `bytes`.
  Exits 1 and names any clip still over. A second run finds nothing over and changes nothing. `--dry-run` lists
  the clips it would cut. It refuses a dirty library tree like `apply`.

## Safety model

- **Clean tree and a snapshot**: `apply` refuses if the library git tree has uncommitted changes. Commit the library
  first; that commit is the snapshot to restore from.
- **Write-ahead journal** `<library>/levels-applied.jsonl`: a `pending` line (with the old file's sha256) before each
  replace, a `done` line (bytes, `extra_atten_db`, `peak_dbfs`) after. A crashed run resumes by rerunning the same
  command: a clip whose file already changed is marked done and never leveled twice; one that did not is redone.
- **Plan hash**: the plan carries a hash of target, chain and gains. `apply` refuses an edited plan, and a library
  whose journal belongs to another plan (it prints the restore command). `add-voice` changes the gains, so it
  records the hash it replaced in `previous_hashes`; journal lines written under any hash in that list still belong
  to the plan, so the voices leveled before stay leveled. Plans without `previous_hashes` (everything measured
  before `add-voice`) work as before.
- **Restore**: when `apply` refuses for another plan it prints the exact command: `git checkout` of every journaled
  file and of `manifest.json` from the snapshot commit, then removal of the journal.
- **Post-encode peak guard**: after encoding to a temp file and before the replace, `apply` decodes it and measures
  the TRUE peak (ffmpeg `ebur128=peak=true`, 4x oversampled, the quantity `verify` uses). Above `PEAK_GUARD_DBTP`
  (-0.8) it re-encodes from the original with extra attenuation after the limiter (overshoot + 0.3 dB), up to 3
  more tries; if still over it stops non-zero and names the clip. The attenuation used is `extra_atten_db` and the
  result `peak_dbtp` in the journal. Without it, 9 of 5,587 clips came out above the verify limit (worst +1.3
  dBFS, clipping). The first version of the guard read the sample peak and still left 7 clips over, because a
  short limited clip can overshoot between samples by up to about 1.1 dB.
- **fix-peaks journal**: `peakfix_pending` (with `old_sha256`) before each replace, `peakfix` (`peak_before`,
  `peak_after`, `atten_db`) after, in the same `levels-applied.jsonl`. `apply` and `measure` ignore these lines.
  A crashed run resumes by rerunning: a clip whose file already changed is recorded, not cut twice.

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

- **Clips saved while the plan is in place are leveled when they are saved.** `soundbite.save` calls
  `level_clips.level_saved` after storing a clip. It finds the plan at `$SOUNDBITE_PLAN`, else
  `<library>/level-plan.json` (copy the plan there once, and commit it with the library). If the plan has a gain for
  the clip's voice (and sfx is skipped), the clip goes through the same chain and peak guard as `apply`, with the same
  `pending` and `done` journal lines and the manifest `bytes` update. A later `apply` with that plan sees the `done`
  line and does not encode the clip again. Measured: save plus leveling of a 3 s clip takes about 0.45 s (ffmpeg
  encode, decode check and true-peak read). level_clips is imported only then, and `ffmpeg` and
  `~/audio-observation-core` are not needed for it (measuring is not part of it).
- **It fails open.** No plan file means nothing happens and nothing is printed. Any other problem (no ffmpeg, an
  edited or unreadable plan, the peak guard giving up) keeps the unleveled clip, prints one line to stderr and
  never raises or blocks speaking. Such a clip is leveled by the next `apply` as before: commit the library, then
  rerun `apply` with the same plan file. It levels only the clips not in the journal.
- **Clean tree**: clips leveled at save time are in the journal, so `apply` counts them as its own changes and does
  not refuse for them. Any other uncommitted file (a clip whose leveling failed, for instance) still needs the commit.
- **A new voice**: `add-voice` (see Commands) measures the voice's clips and adds its gain to the plan, without
  disturbing the journal of the other voices. Order: record the voice's clips, commit the library, `add-voice`,
  copy the updated plan to `<library>/level-plan.json`, commit, `apply`. From then on its new clips are leveled at
  save time. Between the first save and `add-voice` the voice has no gain, so its clips arrive unleveled.

## Known limits

- `fix-peaks` costs one extra mp3 generation on the few clips it touches (they were encoded by `apply`, then
  decoded and encoded again). It exists for clips the guard cannot catch, such as a library leveled before the
  guard read the true peak. Its own check reads ffmpeg's true peak, which on a pure tone at fs/4 reads up to
  0.5 dB above `verify`'s (levels_block skips the file edges), so such a clip may be cut a little more than needed.
- CI runs tests/test_soundbite.py, test_library_web.py and test_voices_docs.py. tests/test_level_clips.py needs ffmpeg and ~/audio-observation-core, which the runner lacks, so it is run locally.
- A torn last journal line after a power loss is ignored with a warning, not truncated.
- A freshly recorded clip is leveled at save time only when the plan is found and has a gain for its voice. Otherwise
  its first play is at the provider's loudness until the next `apply`.
- **Stale-unleveled clip**: re-recording a text that already has a clip replaces the file under the same key. If
  save-time leveling then cannot run or fails, the journal still holds the old `done` line for that key, so `apply`
  skips it and the new file stays unleveled. `save` prints one stderr line saying so ("stale-unleveled"). To level it,
  restore the journal (or delete that key's lines in `levels-applied.jsonl`) and rerun `apply`.
- Save-time leveling and `apply` do not lock each other. A save during a running `apply` only appends to the journal
  and rewrites the manifest under the soundbite lock; the pending line's sha check keeps a clip from being leveled twice.
