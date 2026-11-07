#!/usr/bin/env python3
"""Read-only local gallery for cached voice clips."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

# Running as `python3 tts/library_web.py` puts tts/, not the repository root, on sys.path.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from tts.soundbite import make_key

PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Soundbite / Voice gallery</title><style>
:root{color-scheme:dark;
  --bg:#101114;
  --panel:#191b20;
  --line:#2d3038;
  --muted:#9297a3;
  --ink:#f3f2ed;
  --lime:#c9f36a;
  --purple:#a79aff}
*{box-sizing:border-box}
body{margin:0;
  background:radial-gradient(ellipse at 70% -20%,#333541 0,transparent 42%),var(--bg);
  color:var(--ink);
  font:14px/1.45 system-ui,sans-serif}
header{padding:30px max(22px,calc((100vw - 1440px)/2));
  border-bottom:1px solid var(--line)}
.eyebrow{color:var(--lime);
  text-transform:uppercase;
  letter-spacing:.16em;
  font-size:11px;
  font-weight:700}
h1{margin:4px 0 20px;
  font-size:clamp(28px,4vw,46px);
  letter-spacing:-.04em}
.totals{display:grid;
  grid-template-columns:repeat(6,minmax(90px,1fr));
  gap:10px}
.total,.card,.panel{background:var(--panel);
  border:1px solid var(--line);
  border-radius:12px}
.total{padding:12px 14px}
.total strong{display:block;
  font-size:21px}
.total span,.muted{color:var(--muted);
  font-size:12px}
main{max-width:1484px;
  margin:auto;
  padding:24px}
.section{margin:22px 0 34px}
.section-head{display:flex;
  align-items:end;
  justify-content:space-between;
  margin-bottom:13px}
h2{font-size:20px;
  margin:0;
  letter-spacing:-.02em}
.voices{display:grid;
  grid-template-columns:repeat(auto-fill,minmax(245px,1fr));
  gap:12px}
.card{padding:16px}
.card h3{margin:2px 0 6px;
  font-size:17px}
.badge{display:inline-block;
  border:1px solid #444751;
  border-radius:99px;
  padding:2px 8px;
  color:var(--purple);
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.1em}
.play{background:var(--lime);
  color:#15170f;
  border:0;
  border-radius:7px;
  padding:8px 12px;
  font-weight:700;
  cursor:pointer}
.play:hover{filter:brightness(1.08)}
.meta{margin:10px 0;
  color:#c3c5cc;
  font-size:12px}
.coverage{height:5px;
  background:#34363d;
  border-radius:5px;
  overflow:hidden;
  margin-top:7px}
.coverage i{display:block;
  height:100%;
  background:var(--lime)}
.panel{padding:16px;
  overflow:hidden}
.map-wrap{overflow:auto;
  max-height:640px}
.matrix{border-collapse:separate;
  border-spacing:2px;
  font-size:10px}
.matrix th{position:sticky;
  top:0;
  background:#202229;
  color:var(--muted);
  writing-mode:vertical-rl;
  transform:rotate(180deg);
  height:108px;
  max-width:22px;
  padding:4px}
.matrix th:first-child{writing-mode:horizontal-tb;
  transform:none;
  position:sticky;
  left:0;
  z-index:2;
  min-width:160px;
  text-align:left}
.matrix td:first-child{position:sticky;
  left:0;
  background:#191b20;
  z-index:1;
  padding:4px 8px;
  white-space:nowrap}
.cell{width:15px;
  height:15px;
  padding:0;
  background:#30323a;
  border:0;
  border-radius:3px;
  cursor:pointer}
.cell.yes{background:var(--lime)}
.cell:hover{outline:2px solid white}
.charts{display:grid;
  grid-template-columns:1fr 1fr;
  gap:12px}
.barrow{display:grid;
  grid-template-columns:minmax(90px,170px) 1fr auto;
  align-items:center;
  gap:10px;
  margin:9px 0;
  font-size:12px}
.bar{height:9px;
  background:#30323a;
  border-radius:8px;
  overflow:hidden}
.bar i{display:block;
  background:var(--purple);
  height:100%}
table{width:100%;
  border-collapse:collapse;
  text-align:left}
td,th{border-bottom:1px solid var(--line);
  padding:9px 8px}
th{color:var(--muted);
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.07em}
.effects,.clips{display:grid;
  gap:7px}
.row{display:flex;
  justify-content:space-between;
  align-items:center;
  gap:14px;
  padding:10px 12px;
  background:#202229;
  border-radius:8px}
.row .text{overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap}
input{background:#202229;
  color:var(--ink);
  border:1px solid var(--line);
  padding:10px 12px;
  border-radius:8px;
  min-width:min(340px,60vw)}
.clips{margin-top:10px}
.empty{padding:20px;
  color:var(--muted)}
@media(max-width:700px){main{padding:14px}
.totals{grid-template-columns:repeat(3,1fr)}
.charts{grid-template-columns:1fr}
.section-head{align-items:start;
  gap:10px;
  flex-direction:column}
}

</style><header><div class="eyebrow">Local sound library / read only</div><h1>Voice gallery<span style="color:var(--lime)">.</span></h1><div class="totals" id="totals"></div></header><main><section class="section"><div class="section-head"><h2>Voices</h2><span class="muted">Hear a name and three menu lines</span></div><div class="voices" id="voices"></div></section><section class="section"><div class="section-head"><h2>Library map</h2><span class="muted">Each dot is one voice × one menu clause</span></div><div class="panel map-wrap"><table class="matrix" id="matrix"></table></div></section><section class="section"><h2 style="margin-bottom:13px">Breakdown</h2><div class="charts"><div class="panel"><h3>By provider</h3><div id="providers"></div></div><div class="panel"><h3>By voice</h3><div id="byvoice"></div></div></div></section><section class="section"><h2 style="margin-bottom:13px">Cockpit assignments</h2><div class="panel"><table><thead><tr><th>Cockpit</th><th>Profile</th><th>Name clip</th><th></th></tr></thead><tbody id="assignments"></tbody></table></div></section><section class="section"><h2 style="margin-bottom:13px">Sound effects</h2><div class="panel effects" id="effects"></div></section><section class="section"><div class="section-head"><h2>Clip browser</h2><input id="filter" placeholder="Filter text, voice, or provider…"></div><div class="clips" id="clips"></div><div class="muted" id="clip-count"></div></section></main><audio id="player"></audio><script>const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
let data;
let active = 0;
let cancelSequence = null;

function setClip(audio, path) {
  audio.src = '/audio/' + path.split('/').map(encodeURIComponent).join('/');
  audio.load();
  return audio.play();
}

function play(path) {
  const audio = $('#player');
  active++;
  if (cancelSequence) cancelSequence();
  audio.pause();
  setClip(audio, path).catch(() => {});
}

async function sequence(paths) {
  const audio = $('#player');
  if (cancelSequence) cancelSequence();
  const token = ++active;
  audio.pause();
  let cancelPending;
  cancelSequence = () => { if (cancelPending) cancelPending(); };
  try {
    for (const path of paths) {
      if (token !== active) return;
      await new Promise((resolve, reject) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          audio.removeEventListener('ended', finish);
          audio.removeEventListener('error', failed);
          cancelPending = null;
          resolve();
        };
        const failed = () => {
          if (settled) return;
          settled = true;
          audio.removeEventListener('ended', finish);
          audio.removeEventListener('error', failed);
          cancelPending = null;
          reject(new Error('Audio playback failed'));
        };
        cancelPending = finish;
        audio.addEventListener('ended', finish, { once: true });
        audio.addEventListener('error', failed, { once: true });
        setClip(audio, path).catch(failed);
      });
    }
  } catch (_) {
    // A failed clip ends this preview sequence.
  } finally {
    if (token === active) cancelSequence = null;
  }
}

function btn(path, label = 'Play') {
  return `<button class="play" data-play="${esc(path)}">▶ ${label}</button>`;
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-play]');
  if (button) play(button.dataset.play);
  const sequenceButton = event.target.closest('[data-seq]');
  if (sequenceButton) sequence(JSON.parse(sequenceButton.dataset.seq));
  const cell = event.target.closest('[data-path]');
  if (cell) play(cell.dataset.path);
});

function bars(target, items) {
  const max = Math.max(1, ...items.map(item => item.bytes));
  $(target).innerHTML = items.map(item => `
    <div class="barrow">
      <span>${esc(item.name)}</span>
      <div class="bar"><i style="width:${item.bytes / max * 100}%"></i></div>
      <span>${item.count} · ${(item.bytes / 1048576).toFixed(1)} MB</span>
    </div>`).join('') || '<div class="empty">No clips</div>';
}

function render() {
  const profiles = data.profiles;
  const clauses = data.clauses;
  const totals = [
    [data.summary.clips, 'clips'],
    [(data.summary.bytes / 1048576).toFixed(1) + ' MB', 'audio'],
    [data.summary.providers, 'providers'],
    [profiles.length, 'profiles'],
    [data.assignments.length, 'cockpits assigned'],
    [data.sound_effects.length, 'sound effects']
  ];
  $('#totals').innerHTML = totals.map(([value, label]) => `
    <div class="total"><strong>${value}</strong><span>${label}</span></div>`).join('');
  const sorted = [...profiles].sort((a, b) =>
    (b.cockpits.length > 0) - (a.cockpits.length > 0) || a.id.localeCompare(b.id));
  $('#voices').innerHTML = sorted.map(profile => {
    const samples = ['what next?', 'go or no-go?', 'is done'].map(text => profile.clips[text]);
    const sequencePaths = [profile.name_clip, ...samples].filter(Boolean);
    return `<article class="card">
      <span class="badge">${esc(profile.provider)}</span>
      <h3>${esc(profile.character || profile.id)}</h3>
      <div class="muted">${esc(profile.id)} · ${esc(profile.voice)}</div>
      <div class="meta">${esc([profile.label, profile.account].filter(Boolean).join(' · ') || 'No label')}<br>
        ${esc(profile.cockpits.join(', ') || 'unassigned')}</div>
      <div class="muted">Menu coverage ${profile.coverage}/${clauses.length}</div>
      <div class="coverage"><i style="width:${clauses.length ? profile.coverage / clauses.length * 100 : 0}%"></i></div>
      <p>${sequencePaths.length
        ? `<button class="play" data-seq='${esc(JSON.stringify(sequencePaths))}'>▶ Play voice</button>`
        : '<span class="muted">No name clip</span>'}</p>
    </article>`;
  }).join('');
  const header = '<thead><tr><th>Profile</th>' + clauses.map(clause =>
    `<th title="${esc(clause)}">${esc(clause)}</th>`).join('') + '</tr></thead>';
  const rows = sorted.map(profile => `<tr><td>${esc(profile.id)} <small>${profile.coverage}/${clauses.length}</small></td>${
    clauses.map(clause => profile.clips[clause]
      ? `<td><button class="cell yes" title="${esc(clause)}" aria-label="Play ${esc(clause)}" data-path="${esc(profile.clips[clause])}"></button></td>`
      : `<td><button class="cell" title="Missing: ${esc(clause)}" aria-label="Missing ${esc(clause)}" disabled></button></td>`
    ).join('')}</tr>`).join('');
  $('#matrix').innerHTML = header + '<tbody>' + rows + '</tbody>';
  bars('#providers', data.provider_breakdown);
  bars('#byvoice', data.voice_breakdown);
  $('#assignments').innerHTML = data.assignments.map(assignment => `
    <tr><td>${esc(assignment.cockpit)}</td><td>${esc(assignment.profile)}</td>
      <td>${esc(assignment.say || '')}</td><td>${assignment.name_clip ? btn(assignment.name_clip) : ''}</td></tr>`).join('');
  $('#effects').innerHTML = data.sound_effects.map(effect => `
    <div class="row"><span class="text">${esc(effect.text)}</span>${btn(effect.file)}</div>`).join('')
    || '<div class="empty">No sound effects</div>';
  filter();
}

function filter() {
  if (!data) return;
  const query = $('#filter').value.toLowerCase();
  const hits = data.clips.filter(clip =>
    [clip.text, clip.voice, clip.provider].join(' ').toLowerCase().includes(query));
  const shown = hits.slice(0, 100);
  $('#clips').innerHTML = shown.map(clip => `
    <div class="row"><span class="text"><b>${esc(clip.voice)}</b> · ${esc(clip.provider)} · ${esc(clip.text)}</span>${btn(clip.file)}</div>`).join('')
    || '<div class="empty">No matching clips</div>';
  $('#clip-count').textContent = `Showing ${shown.length} of ${hits.length} matching clips (100 max)`;
}

$('#filter').addEventListener('input', filter);
fetch('/api/library').then(response => {
  if (!response.ok) throw Error('Could not load library');
  return response.json();
}).then(result => {
  data = result;
  render();
}).catch(error => {
  $('main').innerHTML = `<p>${esc(error.message)}</p>`;
});
</script></html>'''


def _safe_rel(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        return None
    return path.as_posix()


def build_data(library: Path, profiles_file: Path, casting_file: Path) -> tuple[dict, dict[str, str]]:
    manifest_path = library / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    profile_data = json.loads(profiles_file.read_text())
    casting = json.loads(casting_file.read_text())
    clauses = casting.get("clauses", [])
    settings = casting.get("elevenlabs_settings") or {}
    eleven_model = (
        f'{casting.get("elevenlabs_model", "")}'
        f'|s{float(settings.get("stability", 0)):g}'
        f'|b{float(settings.get("similarity_boost", 0)):g}'
    )
    allowed: dict[str, str] = {}
    clips = []
    manifest = {k: v for k, v in manifest.items() if isinstance(v, dict)}
    for key, entry in manifest.items():
        rel = _safe_rel(entry.get("file"))
        if rel is None:
            continue
        allowed[rel] = key
        clip = {key: entry.get(key) for key in (
            "text", "provider", "voice", "model", "speed", "bytes", "created"
        )}
        clips.append({**clip, "file": rel})
    profiles = []
    for pid, p in profile_data.get("profiles", {}).items():
        provider, voice = p.get("provider") or "", p.get("voice") or ""
        model = casting.get("openai_model", "") if provider == "openai" else eleven_model
        by_clause = {}
        for clause in clauses:
            key = make_key(clause, provider, voice, model, 1.0)
            if key in manifest:
                rel = _safe_rel(manifest[key].get("file"))
                if rel in allowed:
                    by_clause[clause] = rel
        assignments_for_profile = [
            (name, assignment)
            for name, assignment in profile_data.get("assignments", {}).items()
            if assignment.get("profile") == pid
        ]
        assigned = [name for name, _ in assignments_for_profile]
        name_text = (assignments_for_profile[0][1].get("say") or assignments_for_profile[0][0]) if assignments_for_profile else pid
        name_key = make_key(name_text, provider, voice, model, 1.0)
        name_clip = _safe_rel(manifest.get(name_key, {}).get("file")) if name_key in manifest else None
        profiles.append({
            **p,
            "id": pid,
            "provider": provider,
            "voice": voice,
            "cockpits": assigned,
            "clips": by_clause,
            "coverage": len(by_clause),
            "name_clip": name_clip if name_clip in allowed else None,
            "name_text": name_text,
        })
    assignments = []
    for cockpit, a in profile_data.get("assignments", {}).items():
        p = next((p for p in profiles if p["id"] == a.get("profile")), None)
        name_text = a.get("say") or cockpit
        model = casting.get("openai_model", "") if p and p["provider"] == "openai" else eleven_model
        name_key = make_key(name_text, p["provider"], p["voice"], model, 1.0) if p else ""
        name_clip = _safe_rel(manifest.get(name_key, {}).get("file")) if name_key in manifest else None
        assignments.append({"cockpit": cockpit, "profile": a.get("profile"), "say": name_text, "name_clip": name_clip if name_clip in allowed else None})
    def breakdown(field):
        totals = {}
        for item in clips:
            name = item.get(field) or "unknown"
            row = totals.setdefault(name, {"name": name, "bytes": 0, "count": 0})
            row["bytes"] += int(item.get("bytes") or 0)
            row["count"] += 1
        return sorted(totals.values(), key=lambda x: (-x["bytes"], x["name"]))
    data = {
        "summary": {
            "clips": len(clips),
            "bytes": sum(int(item.get("bytes") or 0) for item in clips),
            "providers": len({item.get("provider") for item in clips}),
        },
        "profiles": profiles,
        "clauses": clauses,
        "assignments": assignments,
        "sound_effects": [item for item in clips if item.get("provider") == "sfx"],
        "clips": clips,
        "provider_breakdown": breakdown("provider"),
        "voice_breakdown": breakdown("voice"),
    }
    return data, allowed


def make_handler(data: dict, allowed: dict[str, str], library: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"{self.address_string()} {fmt % args}", file=sys.stderr)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                body, typ = PAGE.encode(), "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", typ)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/library":
                body = json.dumps(data, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path.startswith("/audio/"):
                rel = unquote(path[len("/audio/"):])
                safe = _safe_rel(rel)
                target = (library / safe).resolve() if safe is not None else None
                try:
                    target.relative_to(library.resolve())
                except (ValueError, AttributeError):
                    target = None
                if safe not in allowed or target is None or not target.is_file():
                    self.send_error(404)
                    return
                size = target.stat().st_size
                start, end, partial = 0, size - 1, False
                range_header = self.headers.get("Range")
                if range_header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                    if not match or (not match.group(1) and not match.group(2)):
                        self.send_error(416)
                        return
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = int(last) if last else size - 1
                    else:
                        length = int(last)
                        start = max(0, size - length)
                    if start >= size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    end = min(end, size - 1)
                    partial = True
                length = max(0, end - start + 1)
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                with target.open("rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
            else:
                self.send_error(404)
    Handler.wbufsize = 1
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--library", type=Path, default=Path(os.getenv("SOUNDBITE_DIR", "~/soundbite")).expanduser())
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--profiles", type=Path, default=root / "phrases/profiles.json")
    parser.add_argument("--casting", type=Path, default=root / "phrases/casting.json")
    args = parser.parse_args(argv)
    try:
        if not (1 <= args.port <= 65535):
            raise ValueError("port must be between 1 and 65535")
        library = args.library.expanduser().resolve()
        data, allowed = build_data(
            library, args.profiles.expanduser().resolve(), args.casting.expanduser().resolve()
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port), make_handler(data, allowed, library)
        )
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        print(f"voice gallery: {exc}", file=sys.stderr)
        return 1
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
