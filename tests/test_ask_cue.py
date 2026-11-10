"""tts/ask_cue.py: the AskUserQuestion hook that plays "<repo>: needs your answer" from two stored clips, never synthesis."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import ask_cue  # noqa: E402
import playback  # noqa: E402


def git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def payload(cwd, tool="AskUserQuestion"):
    return json.dumps({"tool_name": tool, "cwd": str(cwd)})


@pytest.fixture
def speech_log(monkeypatch):
    """Stands in for speech.log (the real one is not touched): the (reason, repo, text) rows the hook wrote."""
    rows = []
    monkeypatch.setattr(ask_cue.repo_gate, "log", lambda reason, repo, text="": rows.append((reason, repo, text)))
    return rows


@pytest.fixture
def stored(monkeypatch, speech_log):
    """The repo is enabled with its own voice and both clips stored (the real registry and library are not read)."""
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: (True, True, str(cwd), "spoke"))
    monkeypatch.setattr(ask_cue.phrase_join, "plan", lambda text, casting=None: ("join", {}, ["a.mp3", "b.mp3"]))
    return speech_log


def test_asking_the_user_plays_the_two_stored_clips_in_the_repos_name(tmp_path, stored):
    repo = git_repo(tmp_path / "My-Cockpit")
    calls = []
    text = ask_cue.run(payload(repo), spawn=lambda cmd, **kw: calls.append((cmd, kw)), log_path=tmp_path / "log")
    assert text == "my-cockpit: needs your answer"
    cmd, kw = calls[0]
    # it plays the files itself in a detached child: no `speak`, so no way to fall back to a paid synthesis
    assert cmd[1].endswith("tts/ask_cue.py") and cmd[2:] == ["--play", "a.mp3", "b.mp3"]
    assert not any(c.endswith("/speak") for c in cmd)
    assert kw["start_new_session"] is True and kw["stdout"] == subprocess.DEVNULL  # the dialog never waits
    assert stored == [("spoke", str(repo.resolve()), text)]  # recorded like speak does, for `speak --repos`


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
        raise FileNotFoundError("no python")
    log = tmp_path / "cache" / "ask_cue.log"
    assert ask_cue.run(payload(repo), spawn=boom, log_path=log) is None  # never raises into the hook
    assert "FileNotFoundError: no python" in log.read_text()


@pytest.mark.parametrize("gate, plan, why", [
    ((True, False, "r", "spoke"), ("join", {}, ["a", "b"]), "plain-voice repo"),   # no cockpit voice to play
    ((True, True, "r", "spoke"), ("miss", "r"), "no cast voice"),                  # unassigned repo
    ((True, True, "r", "spoke"), ("voice", {}), "not stored"),                     # name clip or clause missing
])
def test_a_cue_with_nothing_stored_to_play_stays_silent_and_says_why(tmp_path, monkeypatch, speech_log, gate, plan, why):
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: gate)
    monkeypatch.setattr(ask_cue.phrase_join, "plan", lambda text, casting=None: plan)
    spawned = []
    log = tmp_path / "ask_cue.log"
    assert ask_cue.run(payload(git_repo(tmp_path / "r")), spawn=lambda *a, **k: spawned.append(1), log_path=log) is None
    assert spawned == [] and speech_log == []
    assert "silent" in log.read_text() and why in log.read_text()


def test_an_unlisted_repo_stays_silent_and_the_skip_is_recorded(tmp_path, monkeypatch, speech_log):
    monkeypatch.setattr(ask_cue.repo_gate, "decide", lambda alert=False, cwd=None: (False, False, "r", "skipped"))
    spawned = []
    assert ask_cue.run(payload(git_repo(tmp_path / "r")), spawn=lambda *a, **k: spawned.append(1),
                       log_path=tmp_path / "log") is None
    assert spawned == [] and [r[0] for r in speech_log] == ["skipped"]


def test_a_playback_failure_is_logged_and_never_raises(tmp_path, monkeypatch):
    def boom(paths):
        raise RuntimeError("no audio device")
    monkeypatch.setattr(playback, "play_files", boom)
    log = tmp_path / "ask_cue.log"
    ask_cue.play(["a.mp3"], log_path=log)
    assert "play: RuntimeError: no audio device" in log.read_text()
