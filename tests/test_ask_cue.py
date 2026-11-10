"""tts/ask_cue.py: the AskUserQuestion hook that says "<repo>: needs your answer" (stored clips only)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import ask_cue  # noqa: E402


def git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def payload(cwd, tool="AskUserQuestion"):
    return json.dumps({"tool_name": tool, "cwd": str(cwd)})


@pytest.fixture
def stored(monkeypatch):
    """The repo is enabled with its own voice and both clips stored (the real registry and library are not read)."""
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: (True, True, str(cwd), "spoke"))
    monkeypatch.setattr(ask_cue.phrase_join, "plan", lambda text, casting=None: ("join", {}, ["a.mp3", "b.mp3"]))


def test_asking_the_user_speaks_the_stored_cue_in_the_repos_name(tmp_path, stored):
    repo = git_repo(tmp_path / "My-Cockpit")
    calls = []
    text = ask_cue.run(payload(repo), spawn=lambda cmd, **kw: calls.append((cmd, kw)), log_path=tmp_path / "log")
    assert text == "my-cockpit: needs your answer"
    cmd, kw = calls[0]
    assert cmd[1] == text and cmd[0].endswith("/speak")
    assert kw["start_new_session"] is True and kw["stdout"] == subprocess.DEVNULL  # detached: the dialog never waits
    # speak's own gate reads its cwd: it must judge the same repo this hook did, not wherever the hook was started
    assert kw["cwd"] == str(repo.resolve()) and kw["env"]["CLAUDE_PROJECT_DIR"] == str(repo.resolve())


def test_a_worktree_speaks_as_its_main_checkout(tmp_path, stored):
    repo = git_repo(tmp_path / "cockpit")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    lane = tmp_path / "cockpit-lane"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(lane), "-b", "lane/x"], check=True)
    assert ask_cue.run(payload(lane), spawn=lambda *a, **k: None, log_path=tmp_path / "log") == "cockpit: needs your answer"


def test_other_tools_and_bad_input_stay_silent_and_a_failed_launch_is_logged(tmp_path, stored):
    repo = git_repo(tmp_path / "r")
    spawned = []
    spawn = lambda *a, **k: spawned.append(1)  # noqa: E731
    assert ask_cue.run(payload(repo, tool="Bash"), spawn=spawn, log_path=tmp_path / "log") is None
    assert ask_cue.run("not json", spawn=spawn, log_path=tmp_path / "log") is None
    assert spawned == []

    def boom(*a, **k):
        raise FileNotFoundError("no speak")
    log = tmp_path / "cache" / "ask_cue.log"
    assert ask_cue.run(payload(repo), spawn=boom, log_path=log) is None  # never raises into the hook
    assert "FileNotFoundError: no speak" in log.read_text()


@pytest.mark.parametrize("gate, plan, why", [
    ((True, False, "r", "spoke"), ("join", {}, []), "plain-voice repo"),          # speak would synthesize the line
    ((True, True, "r", "spoke"), ("miss", "r"), "no cast voice"),                  # unassigned repo: whole line is paid
    ((True, True, "r", "spoke"), ("voice", {}), "not stored"),                     # name clip or clause missing
])
def test_a_cue_that_would_cost_money_stays_silent_and_says_why(tmp_path, monkeypatch, gate, plan, why):
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: gate)
    monkeypatch.setattr(ask_cue.phrase_join, "plan", lambda text, casting=None: plan)
    spawned = []
    log = tmp_path / "ask_cue.log"
    assert ask_cue.run(payload(git_repo(tmp_path / "r")), spawn=lambda *a, **k: spawned.append(1), log_path=log) is None
    assert spawned == []
    assert "silent" in log.read_text() and why in log.read_text()


def test_an_unlisted_repo_still_goes_through_speak_which_skips_it_free_and_records_it(tmp_path, monkeypatch):
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: (False, False, "r", "skipped"))
    spawned = []
    ask_cue.run(payload(git_repo(tmp_path / "r")), spawn=lambda *a, **k: spawned.append(1), log_path=tmp_path / "log")
    assert spawned == [1]
