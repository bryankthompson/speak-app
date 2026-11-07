#!/usr/bin/env python3
"""Voice profiles and who uses them.  speak --profiles | --assign COCKPIT PROFILE | --profile ID [text]

A profile is a voice (provider + voice id + a one-line character) in phrases/profiles.json. An assignment
points a cockpit at a profile. Clips are keyed on the voice, so re-assigning never re-records the menu;
at most the cockpit's own name clip is missing (this prints the command that records it).
Stdlib only. Auditioning plays stored clips only and never calls an API.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import phrase_join  # noqa: E402
import soundbite  # noqa: E402

SAMPLE = ["what next?", "go or no-go?", "is done"]


def _clips(profile_id, casting, say=None):
    """(stored, wanted) clip counts for a profile: the clause menu, plus the name clip when `say` is given."""
    prof = casting["profiles"][profile_id]
    model = phrase_join.bite_model(prof, casting)
    texts = ([say] if say else []) + list(casting["clauses"])
    have = sum(1 for t in texts if soundbite.lookup(t, prof["provider"], prof["voice"], model, 1.0))
    return have, len(texts)


def list_profiles():
    c = phrase_join.load_casting()
    users = {}
    for cockpit, a in c["assignments"].items():
        users.setdefault(a["profile"], []).append(cockpit)
    for pid, prof in sorted(c["profiles"].items(), key=lambda kv: (kv[0] not in users, kv[0])):
        have, want = _clips(pid, c)
        who = ", ".join(sorted(users.get(pid, []))) or "-"
        print(f"{pid:<10} {prof['provider']:<10} {have:>3}/{want} menu  {prof['character']:<32} used by: {who}")
    return 0


def assign(cockpit, profile_id, say=None):
    c = phrase_join.load_casting()
    if profile_id not in c["profiles"]:
        print(f"unknown profile '{profile_id}'. Profiles: {', '.join(sorted(c['profiles']))}", file=sys.stderr)
        return 1
    data = json.loads(phrase_join.PROFILES.read_text())
    key = cockpit.strip().lower()
    data["assignments"][key] = {"profile": profile_id, **({"say": say} if say else {})}
    phrase_join.PROFILES.write_text(json.dumps(data, indent=2) + "\n")
    c = phrase_join.load_casting()
    have, want = _clips(profile_id, c, say or key)
    print(f"{key} -> {profile_id}: {have}/{want} clips stored")
    if have < want:
        print(f"missing {want - have} clip(s) (usually the name clip '{say or key}'). Record with: "
              f"phrases/record.py --assigned", file=sys.stderr)
    return 0


def audition(profile_id, text=None):
    c = phrase_join.load_casting()
    prof = c["profiles"].get(profile_id)
    if not prof:
        print(f"unknown profile '{profile_id}'. Profiles: {', '.join(sorted(c['profiles']))}", file=sys.stderr)
        return 1
    model = phrase_join.bite_model(prof, c)
    texts = [text] if text else [profile_id, *SAMPLE]
    paths = [soundbite.lookup(t, prof["provider"], prof["voice"], model, 1.0) for t in texts]
    missing = [t for t, p in zip(texts, paths) if not p]
    if missing:
        print(f"not recorded for {profile_id}: {missing}. Auditions never call the API; record with "
              f"phrases/record.py --profile {profile_id}", file=sys.stderr)
        return 1
    import playback
    playback.play_files(paths)
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        return list_profiles()
    if cmd == "assign" and len(rest) >= 2:
        return assign(rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    if cmd == "audition" and rest:
        return audition(rest[0], " ".join(rest[1:]) or None)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
