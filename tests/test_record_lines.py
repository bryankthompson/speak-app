"""record.py --lines: batch fill for free-text cockpit lines. No network, no paid call (a fake provider call)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))
sys.path.insert(0, str(ROOT / "phrases"))
import record  # noqa: E402
import soundbite  # noqa: E402


@pytest.fixture(autouse=True)
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path / "bite"))
    return tmp_path


def _openai_cast():
    for k, a in record.PROFILES["assignments"].items():
        p = record.PROFILES["profiles"][a["profile"]]
        if p["provider"] == "openai":
            return k, p
    pytest.skip("no openai assignment")


def _file(tmp_path, *rows):
    f = tmp_path / "lines.txt"
    f.write_text("\n".join(rows) + "\n")
    return f


def fake(calls):
    def call(provider, voice, text):
        calls.append((provider, voice, text))
        return 200, b"AUDIO"
    return call


def test_dry_run_lists_prices_and_calls_nothing(repo, capsys):
    name, _ = _openai_cast()
    f = _file(repo, "# comment", "", f"{name}: check the build log")
    calls = []
    assert record.run_lines(f, "openai", True, fake(calls)) == 0
    err = capsys.readouterr().err
    assert f"{name}: check the build log" in err and "1 lines to record" in err and "$0.001" in err
    assert calls == []


def test_elevenlabs_dry_run_prices_credits_with_worst_case(repo, capsys):
    name = next(k for k, a in record.PROFILES["assignments"].items()
                if record.PROFILES["profiles"][a["profile"]]["provider"] == "elevenlabs")
    record.run_lines(_file(repo, f"{name}: abcd"), "elevenlabs", True, fake([]))
    assert f"{len(name) + 2 + 4} worst case" in capsys.readouterr().err


def test_stored_key_is_the_one_the_live_path_looks_up(repo):
    name, prof = _openai_cast()
    line = f"{name}: check the build log"
    calls = []
    assert record.run_lines(_file(repo, line), "openai", False, fake(calls)) == 0
    assert calls == [("openai", prof["voice"], line)]
    # openai_tts.py looks up (whole line, "openai", voice, model, speed) with the model it was given
    assert soundbite.lookup(line, "openai", prof["voice"], record.CFG["openai_model"], 1.0).read_bytes() == b"AUDIO"
    # a second run finds it stored and calls nothing
    calls.clear()
    assert record.run_lines(_file(repo, line), "openai", False, fake(calls)) == 0
    assert calls == []


def test_menu_clause_with_both_clips_stored_is_skipped(repo):
    name, prof = _openai_cast()
    entry = record.phrase_join.resolve_cast(name, {**record.CFG, **record.PROFILES})
    clause = record.CFG["clauses"][0]
    for t in (entry["name"], clause):
        soundbite.save(t, "openai", prof["voice"], b"A", record.CFG["openai_model"], 1.0)
    calls = []
    assert record.run_lines(_file(repo, f"{name}: {clause}"), "openai", False, fake(calls)) == 0
    assert calls == []


def test_unknown_name_is_reported_skipped_and_exits_1(repo, capsys):
    name, _ = _openai_cast()
    calls = []
    rc = record.run_lines(_file(repo, "nobody-here: hello", f"{name}: hello there"), "openai", False, fake(calls))
    assert rc == 1 and len(calls) == 1
    assert "unknown name, skipped: nobody-here: hello" in capsys.readouterr().err


def test_elevenlabs_quota_error_stops_the_run(repo):
    name = next(k for k, a in record.PROFILES["assignments"].items()
                if record.PROFILES["profiles"][a["profile"]]["provider"] == "elevenlabs")
    calls = []

    def call(provider, voice, text):
        calls.append(text)
        return 402, "quota"
    assert record.run_lines(_file(repo, f"{name}: one", f"{name}: two"), "elevenlabs", False, call) == 2
    assert len(calls) == 1
