"""Per-repo speech gate: decision table, repo identity, logging, wiring in tts_provider.main. No audio, no network."""
import json
import os
import subprocess
import sys

import pytest

import repo_gate
import tts_provider


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def repo(tmp_path):
    root = (tmp_path / "main").resolve()
    root.mkdir()
    git("init", "-q", cwd=root)
    git("commit", "-q", "--allow-empty", "-m", "x", cwd=root)
    return root


def registry(gate, repos):
    repo_gate.registry_path().parent.mkdir(parents=True, exist_ok=True)
    repo_gate.registry_path().write_text(json.dumps({"gate": gate, "repos": repos}))


def log_lines():
    return repo_gate.log_path().read_text().splitlines()


# (registry state, alert) -> (allow, voices, kind)
@pytest.mark.parametrize("state,alert,expect", [
    ("none", False, (True, True, "spoke")),
    ("none", True, (True, True, "alert")),
    ("off", False, (True, True, "spoke")),
    ("on-voices", False, (True, True, "spoke")),
    ("on-voices", True, (True, True, "alert")),
    ("on-plain", False, (True, False, "spoke")),
    ("on-plain", True, (True, False, "alert")),
    ("on-unlisted", False, (False, False, "skipped")),
    ("on-unlisted", True, (True, False, "alert")),
])
def test_decision_table(repo, state, alert, expect):
    if state == "off":
        registry(False, {})
    elif state == "on-voices":
        registry(True, {str(repo): {"voices": True}})
    elif state == "on-plain":
        registry(True, {str(repo): {"voices": False}})
    elif state == "on-unlisted":
        registry(True, {"/somewhere/else": {}})
    allow, voices, _, reason = repo_gate.decide(alert, cwd=repo)
    assert (allow, voices, reason) == expect


def test_worktree_follows_main_checkout(repo, tmp_path):
    wt = tmp_path / "lane"
    git("worktree", "add", "-q", str(wt), "-b", "lane", cwd=repo)
    registry(True, {str(repo): {}})
    allow, _, key, _ = repo_gate.decide(cwd=wt)
    assert allow and key == str(repo)


def test_project_dir_wins_over_cwd(repo, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    registry(True, {str(repo): {}})
    monkeypatch.chdir(other)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    assert repo_gate.decide()[0] is True
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert repo_gate.decide()[0] is False


def test_non_git_folder_uses_listed_ancestor(tmp_path):
    parent = (tmp_path / "plain").resolve()
    child = parent / "a" / "b"
    child.mkdir(parents=True)
    registry(True, {})
    assert repo_gate.decide(cwd=child)[0] is False
    registry(True, {str(parent): {"voices": False}})
    allow, voices, key, _ = repo_gate.decide(cwd=child)
    assert (allow, voices, key) == (True, False, str(parent))


def test_invalid_registry(repo):
    repo_gate.registry_path().parent.mkdir(parents=True)
    repo_gate.registry_path().write_text("{nope")
    allow, _, _, reason = repo_gate.decide(cwd=repo)
    assert not allow and reason.startswith("invalid")
    assert repo_gate.decide(alert=True, cwd=repo)[0] is True


def test_here_and_gate_cli_edit_registry(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert repo_gate.main(["here", "on", "--plain"]) == 0
    assert repo_gate.main(["gate", "on"]) == 0
    reg = json.loads(repo_gate.registry_path().read_text())
    assert reg == {"gate": True, "repos": {str(repo): {"voices": False}}}
    assert repo_gate.main(["here", "off"]) == 0
    assert json.loads(repo_gate.registry_path().read_text())["repos"] == {}


def run_main(monkeypatch, repo, text="hello", extra=()):
    calls = {"join": 0, "speak": 0}
    import phrase_join
    monkeypatch.setattr(phrase_join, "try_join", lambda t, failures=None: calls.__setitem__("join", calls["join"] + 1) or False)
    monkeypatch.setattr(tts_provider.TTSProvider, "speak_with_fallback",
                        lambda self, *a, **k: calls.__setitem__("speak", calls["speak"] + 1) or True)
    monkeypatch.setattr(tts_provider.TTSProvider, "get_available_providers", lambda self: [])
    monkeypatch.setattr(tts_provider.TTSProvider, "select_provider", lambda self: "x")
    monkeypatch.setattr(sys, "argv", ["tts_provider.py", *extra, text])
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        tts_provider.main()
    return e.value.code, calls


def test_main_skips_unlisted_repo(repo, monkeypatch, capsys):
    registry(True, {})
    code, calls = run_main(monkeypatch, repo)
    assert code == 0 and calls == {"join": 0, "speak": 0}
    assert "skipped:" in capsys.readouterr().out
    assert "\tskipped\t" in log_lines()[-1]


def test_main_alert_speaks(repo, monkeypatch):
    registry(True, {})
    code, calls = run_main(monkeypatch, repo, extra=["--alert"])
    assert code == 0 and calls["speak"] == 1 and calls["join"] == 0
    assert "\talert\t" in log_lines()[-1]


def test_main_plain_repo_skips_join(repo, monkeypatch):
    registry(True, {str(repo): {"voices": False}})
    _, calls = run_main(monkeypatch, repo)
    assert calls == {"join": 0, "speak": 1}


def test_main_voices_repo_tries_join_and_logs_gate_off(repo, monkeypatch):
    _, calls = run_main(monkeypatch, repo)  # no registry: gate off
    assert calls == {"join": 1, "speak": 1}
    assert "\tspoke\t" in log_lines()[-1]


def test_main_invalid_registry_exits_3(repo, monkeypatch, capsys):
    repo_gate.registry_path().parent.mkdir(parents=True)
    repo_gate.registry_path().write_text("[")
    code, calls = run_main(monkeypatch, repo)
    assert code == 3 and calls["speak"] == 0
    assert "invalid" in capsys.readouterr().err
    assert "\tinvalid\t" in log_lines()[-1]


def test_here_json_and_check_are_machine_readable(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    registry(True, {})
    assert repo_gate.main(["here", "--check"]) == 1  # gate on, not listed: silent
    assert repo_gate.main(["here", "--json"]) == 0
    off = json.loads(capsys.readouterr().out)
    assert off == {"repo": str(repo), "listed": False, "voices": False, "gate": True, "speaks": False}
    registry(True, {str(repo): {"voices": True}})
    assert repo_gate.main(["here", "--check"]) == 0
    assert repo_gate.main(["here", "--json"]) == 0
    on = json.loads(capsys.readouterr().out)
    assert on["speaks"] is True and on["voices"] is True and on["listed"] is True
    assert repo_gate.main(["here", "--bogus"]) == 2


def test_main_failure_is_logged_with_its_cause(repo, monkeypatch, capsys):
    registry(True, {str(repo): {"voices": False}})
    def fail(self, *a, **k):
        self.failures.append("openai: insufficient_quota")
        return False
    monkeypatch.setattr(tts_provider.TTSProvider, "speak_with_fallback", fail)
    monkeypatch.setattr(sys, "argv", ["tts_provider.py", "hello"])
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        tts_provider.main()
    assert e.value.code == 1
    assert log_lines()[-1].split("\t")[1:] == ["failed", str(repo), "hello", "openai: insufficient_quota"]
    assert "speak: openai: insufficient_quota" in capsys.readouterr().err


def test_main_fallback_success_is_logged_and_repos_counts_the_line_once(repo, monkeypatch, capsys):
    registry(True, {str(repo): {"voices": False}})
    def degraded(self, *a, **k):
        self.failures.append("openai: insufficient_quota")
        return True
    monkeypatch.setattr(tts_provider.TTSProvider, "speak_with_fallback", degraded)
    monkeypatch.setattr(sys, "argv", ["tts_provider.py", "hello"])
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit) as e:
        tts_provider.main()
    assert e.value.code == 0
    assert [l.split("\t")[1] for l in log_lines()] == ["spoke", "fallback"]
    capsys.readouterr()
    repo_gate.cmd_repos()
    assert f"    1  plain       {repo}" in capsys.readouterr().out


def test_provider_records_why_each_script_failed(monkeypatch):
    monkeypatch.setattr(tts_provider.TTSProvider, "get_available_providers", lambda self: ["openai", "pyttsx3"])
    done = subprocess.CompletedProcess([], 1, "", "noise\nOpenAI TTS error: 429 insufficient_quota\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: done)
    tts = tts_provider.TTSProvider()
    assert tts.speak_with_fallback("hi") is False
    assert tts.failures == ["openai: OpenAI TTS error: 429 insufficient_quota",
                            "pyttsx3: OpenAI TTS error: 429 insufficient_quota"]


def test_main_stops_when_stored_clips_will_not_play(repo, monkeypatch, capsys):
    import phrase_join
    def broken(text, failures=None):
        failures.append("stored clips: PowerShell playback failed")
        raise phrase_join.StoredClipsFailed("PowerShell playback failed")
    monkeypatch.setattr(phrase_join, "try_join", broken)
    spoke = []
    monkeypatch.setattr(tts_provider.TTSProvider, "speak_with_fallback", lambda self, *a, **k: spoke.append(a) or True)
    monkeypatch.setattr(sys, "argv", ["tts_provider.py", "hades: needs your answer"])
    monkeypatch.chdir(repo)  # no registry: gate off, voices on
    with pytest.raises(SystemExit) as e:
        tts_provider.main()
    assert e.value.code == 1 and spoke == []  # the default (paid) path never ran
    assert log_lines()[-1].split("\t")[1:] == ["failed", str(repo), "hades: needs your answer",
                                               "stored clips: PowerShell playback failed"]
    assert "speak: stored clips: PowerShell playback failed" in capsys.readouterr().err


def test_log_never_keeps_a_key_the_api_quoted_back(repo):
    repo_gate.log("failed", repo, "hello", "OpenAI 401: Incorrect API key provided: sk-proj-********abcd. See docs")
    row = log_lines()[-1].split("\t")
    assert "sk-proj" not in row[4] and "abcd" not in row[4] and "[key]" in row[4]


def test_provider_with_nothing_to_run_says_so(monkeypatch):
    monkeypatch.setattr(tts_provider.TTSProvider, "select_provider", lambda self: None)
    tts = tts_provider.TTSProvider()
    assert tts.speak("hi") is False and tts.failures == ["no TTS provider available"]
