#!/usr/bin/env bash
# speak-voices: the plugin's one entry point. Runs speak-app's own commands; no API calls.
#   speak-voices.sh list | assign COCKPIT PROFILE [SAY] | audition ID [TEXT] | health
# The checkout is $SPEAK_APP_DIR, default ~/speak-app. Missing checkout = exit 1 with the reason.
set -euo pipefail

dir="${SPEAK_APP_DIR:-$HOME/speak-app}"
if [[ ! -x "$dir/speak" || ! -f "$dir/tts/profiles.py" ]]; then
  echo "speak-voices: no speak-app checkout at $dir (need speak and tts/profiles.py)." >&2
  echo "Set SPEAK_APP_DIR to your clone, e.g. export SPEAK_APP_DIR=~/speak-app" >&2
  exit 1
fi

cmd="${1:-}"
[[ $# -gt 0 ]] && shift
case "$cmd" in
  list)
    exec "$dir/speak" --profiles
    ;;
  assign)
    [[ $# -ge 2 ]] || { echo "usage: speak-voices.sh assign COCKPIT PROFILE [SAY]" >&2; exit 1; }
    exec python3 "$dir/tts/profiles.py" assign "$@"
    ;;
  audition)
    [[ $# -ge 1 ]] || { echo "usage: speak-voices.sh audition ID [TEXT]" >&2; exit 1; }
    exec "$dir/speak" --profile "$@"
    ;;
  health)
    python3 "$dir/tts/soundbite.py" stats
    # Manifest entries whose mp3 is gone: a lookup treats them as a miss, so they would be paid for again.
    python3 - "$dir" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "tts"))
import soundbite
gone = [str(e.get("file") or "<entry without file>") for e in soundbite._load().values()
        if not e.get("file") or not (soundbite.repo_dir() / e["file"]).exists()]
print(f"missing files: {len(gone)}")
for f in gone[:10]:
    print(f"  {f}")
PY
    log="$HOME/.cache/speak-app/voice_misses.log"
    if [[ -f "$log" ]]; then
      echo "unknown cockpit names (last 10 of $log):"
      tail -n 10 "$log"
    else
      echo "unknown cockpit names: none logged"
    fi
    ;;
  *)
    echo "usage: speak-voices.sh list | assign COCKPIT PROFILE [SAY] | audition ID [TEXT] | health" >&2
    exit 1
    ;;
esac
