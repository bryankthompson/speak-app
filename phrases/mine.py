#!/usr/bin/env python3
"""Mine the real phrases cockpit sessions speak, from Claude transcripts.

Writes phrases/corpus.tsv (count, kind, text) and prints coverage of the clause list.
Run: python3 -I phrases/mine.py        (read-only; calls no API)
"""
import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

OUT = Path(__file__).parent / "corpus.tsv"

# Fixed clauses worth recording once per voice. Order matters: first match wins.
CLAUSES = [
    ("what_next",   r"what (should (we|i) )?(work on|plan|do)? ?next|what next|pick next work|which \w+ first"),
    ("go_no_go",    r"go or no-?go|\bgo\b\?$|go for\b"),
    ("merge",       r"\bmerge( it)?\?"),
    ("approve",     r"\bapprove\b|\bconfirm\b|\bok\?$"),
    ("run_now",     r"\brun\b.*\bnow\b|\bnow or later\b|\bstart\b.*\bnow\b|\bdeploy\b"),
    ("needs_you",   r"needs you|need you|waiting for you|decisions? waiting|question for (you|bryan)|has a question"),
    ("done",        r"\bdone\b|\bready\b|\bmerged\b|\bcomplete"),
    ("blocked",     r"blocked|never connected|wrong account|failed"),
    ("held",        r"held your message"),
]
CLAUSE_RES = [(n, re.compile(p, re.I)) for n, p in CLAUSES]
CALL = re.compile(
    r'''(?:^|[;&|(]\s*|\n\s*)(?:~/bin/|/home/bryan/bin/)?speak(?:-dev)?\s+((?:--?[\w-]+(?:\s+[\w.-]+)?\s+)*)(["'])(.+?)\2''',
    re.S)


def mine():
    calls = collections.Counter()
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        for line in open(f, errors="ignore"):
            if "speak" not in line:
                continue
            try:
                content = json.loads(line).get("message", {}).get("content")
            except Exception:
                continue
            if not isinstance(content, list):
                continue
            for b in content:
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    for m in CALL.finditer(b["input"].get("command", "")):
                        t = m.group(3).strip()
                        if "$(" not in t and "`" not in t and "$" not in t:
                            calls[t] += 1
    return calls


def main():
    calls = mine()
    total = sum(calls.values())
    names = collections.Counter()
    clause_hits = collections.Counter()
    rows = []
    covered = 0
    for text, n in calls.most_common():
        name, _, rest = text.partition(":")
        has_name = bool(rest) and len(name) < 40
        if has_name:
            names[name.strip().lower()] += n
        body = rest.strip() if has_name else text
        kind = "free"
        for cname, rx in CLAUSE_RES:
            if rx.search(body):
                kind = cname
                break
        if kind != "free":
            clause_hits[kind] += n
            covered += n
        rows.append((n, kind, text))
    with OUT.open("w") as f:
        f.write("count\tclause\ttext\n")
        for n, kind, text in rows:
            f.write(f"{n}\t{kind}\t{text}\n")
    print(f"{total} speak calls, {len(calls)} unique -> {OUT}")
    print(f"calls whose body matches a fixed clause: {covered}/{total} ({100*covered//max(total,1)}%)")
    print("clauses:", dict(clause_hits.most_common()))
    print(f"names ({len(names)}):", dict(names.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
