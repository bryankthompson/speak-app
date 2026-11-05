#!/usr/bin/env python3
"""Per-repo control of speech, from one central registry (~/.config/speak-app/repos.json):

    {"gate": true, "repos": {"/abs/main/checkout": {"voices": true}}}

Gate off or no registry: everything speaks (the default). Gate on: a repo speaks only if it is listed.
"voices": false = plain default voice (no cockpit voice, no name+clause join).
Warnings (`speak --alert`) always speak, in the repo's own voice setting. Worktrees follow their main checkout.
Every decision is appended to ~/.cache/speak-app/speech.log, also while the gate is off.

    repo_gate.py here [on [--plain] | off]   show or edit this repo's entry
    repo_gate.py repos                       repos seen in the last 7 days
    repo_gate.py gate on|off                 switch the gate
SPEAK_REPOS and SPEAK_LOG override the two paths (tests only).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def registry_path():
    return Path(os.getenv("SPEAK_REPOS") or "~/.config/speak-app/repos.json").expanduser()


def log_path():
    return Path(os.getenv("SPEAK_LOG") or "~/.cache/speak-app/speech.log").expanduser()


def load():
    """-> registry dict, or None when absent; raises ValueError when invalid."""
    path = registry_path()
    if not path.exists():
        return None
    try:
        reg = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"{path} is not valid JSON ({e})")
    if not isinstance(reg, dict) or not isinstance(reg.get("repos", {}), dict):
        raise ValueError(f"{path} must be an object with a 'repos' object")
    if not all(isinstance(v, dict) for v in reg.get("repos", {}).values()):
        raise ValueError(f"{path}: every entry in 'repos' must be an object")
    return reg


def save(reg):
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(reg, indent=2) + "\n")
    os.replace(tmp, path)


def repo_root(cwd=None):
    """(root, is_git): the main checkout of the repo containing cwd, else cwd itself."""
    cwd = Path(cwd or os.getenv("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).parent, True
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd, False


def find_entry(repos, root, is_git):
    """The listed key for root (non-git folders: nearest listed ancestor), else None."""
    for p in ([root] if is_git else [root, *root.parents]):
        if str(p) in repos:
            return str(p)
    return None


def decide(alert=False, cwd=None):
    """-> (allow, voices, repo, reason); reason is spoke|skipped|alert|invalid."""
    root, is_git = repo_root(cwd)
    try:
        reg = load()
    except ValueError as e:
        return alert, False, str(root), "alert" if alert else f"invalid: {e}"
    if reg is None or not reg.get("gate"):
        return True, True, str(root), "alert" if alert else "spoke"
    key = find_entry(reg.get("repos", {}), root, is_git)
    if key is None:
        return alert, False, str(root), "alert" if alert else "skipped"
    voices = reg["repos"][key].get("voices", True) is not False
    return True, voices, key, "alert" if alert else "spoke"


def log(reason, repo, text=""):
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = reason.split(":")[0]
        with path.open("a") as f:
            f.write(f"{time.strftime('%F %T')}\t{kind}\t{repo}\t{text[:60]}\n")
    except OSError as e:
        print(f"speak: cannot write {log_path()}: {e}", file=sys.stderr)


def cmd_here(args):
    root, _ = repo_root()
    reg = load() or {}
    repos = reg.setdefault("repos", {})
    if args[:1] == ["on"]:
        repos[str(root)] = {"voices": "--plain" not in args}
        save(reg)
    elif args[:1] == ["off"]:
        repos.pop(str(root), None)
        save(reg)
    elif args:
        print("usage: speak --here [on [--plain] | off]", file=sys.stderr)
        return 2
    entry = repos.get(str(root))
    state = "not listed" if entry is None else ("listed, plain voice" if entry.get("voices") is False else "listed, cockpit voices")
    print(f"{root}: {state}; gate {'on' if reg.get('gate') else 'off'}")
    return 0


def cmd_repos():
    reg = load() or {}
    seen = {}
    cutoff = time.time() - 7 * 86400
    try:
        lines = log_path().read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            if time.mktime(time.strptime(parts[0], "%Y-%m-%d %H:%M:%S")) < cutoff:
                continue
        except ValueError:
            continue
        seen[parts[2]] = seen.get(parts[2], 0) + 1
    print(f"gate {'on' if reg.get('gate') else 'off'}")
    for repo, n in sorted(seen.items(), key=lambda kv: -kv[1]):
        entry = reg.get("repos", {}).get(repo)
        state = "not listed" if entry is None else ("plain" if entry.get("voices") is False else "voices")
        print(f"{n:5d}  {state:10s}  {repo}")
    return 0


def cmd_gate(args):
    if args not in (["on"], ["off"]):
        print("usage: speak --gate on|off", file=sys.stderr)
        return 2
    reg = load() or {}
    reg["gate"] = args == ["on"]
    reg.setdefault("repos", {})
    save(reg)
    print(f"gate {args[0]}")
    return 0


def main(argv):
    cmd, rest = (argv[0] if argv else ""), argv[1:]
    try:
        if cmd == "here":
            return cmd_here(rest)
        if cmd == "repos":
            return cmd_repos()
        if cmd == "gate":
            return cmd_gate(rest)
    except ValueError as e:
        print(f"speak: {e}", file=sys.stderr)
        return 3
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
