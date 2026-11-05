#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Voice gallery: a read-only page of every voice profile and the soundbite library (127.0.0.1 only, no API calls).
#   ./run_local.sh [--port N] [--open]   start it (default port 8765); --open also opens the browser
#   ./run_local.sh --stop [--port N]     stop this checkout's gallery on that port
#   ./run_local.sh --status [--port N]   say what is listening on the port
# Library: $SOUNDBITE_DIR or ~/soundbite. Profiles and clause menu: phrases/profiles.json, phrases/casting.json.
action=start
port=8765
open_browser=false
previous=
for arg in "$@"; do
  case "$arg" in
    --stop) action=stop ;;
    --status) action=status ;;
    --open) open_browser=true ;;
    --port=*) port="${arg#--port=}" ;;
    --port) ;;
    *) [[ "$previous" == "--port" ]] && port="$arg" || { echo "run_local.sh: unknown argument: $arg" >&2; exit 2; } ;;
  esac
  previous="$arg"
done

web=tts/library_web.py
# Until lane/voice-gallery is merged the module only exists in its worktree; drop this fallback after the merge.
[[ -f "$web" ]] || web=../speak-app-voice-gallery/tts/library_web.py
[[ -f "$web" ]] || { echo "run_local.sh: tts/library_web.py not found" >&2; exit 1; }
web="$(realpath -- "$web")"

if [[ "$action" == status ]]; then
  # Reads /proc via pgrep: names the gallery on this port, or says the port is free.
  pgrep -af "library_web.py.*--port[= ]$port( |$)" || { echo "nothing from this checkout on port $port"; exit 1; }
  exit 0
fi

if [[ "$action" == stop ]]; then
  pkill -f "library_web.py.*--port[= ]$port( |$)" && echo "stopped the gallery on port $port" || { echo "no gallery on port $port"; exit 1; }
  exit 0
fi

if [[ "$open_browser" == true ]]; then
  # Open after the server is listening; WSL first, then Linux.
  ( for _ in $(seq 1 50); do
      (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && break
      sleep 0.1
    done
    if command -v wslview >/dev/null; then wslview "http://127.0.0.1:$port"
    elif command -v explorer.exe >/dev/null; then explorer.exe "http://127.0.0.1:$port" || true
    else xdg-open "http://127.0.0.1:$port" || true
    fi ) &
fi

exec python3 "$web" --port "$port" --library "${SOUNDBITE_DIR:-$HOME/soundbite}" \
  --profiles "$PWD/phrases/profiles.json" --casting "$PWD/phrases/casting.json"
