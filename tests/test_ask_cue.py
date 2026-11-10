"""tts/ask_cue.py: the AskUserQuestion hook that says "<repo>: needs your answer"."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tts"))
import ask_cue  # noqa: E402


def git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def payload(cwd, tool="AskUserQuestion"):
    return json.dumps({"tool_name": tool, "cwd": str(cwd)})


def test_asking_the_user_speaks_the_stored_cue_in_the_repos_name(tmp_path):
    repo = git_repo(tmp_path / "My-Cockpit")
    calls = []
    text = ask_cue.run(payload(repo), spawn=lambda cmd, **kw: calls.append((cmd, kw)), log_path=tmp_path / "log")
    assert text == "my-cockpit: needs your answer"
    cmd, kw = calls[0]
    assert cmd[1] == text and cmd[0].endswith("/speak")
    assert kw["start_new_session"] is True and kw["stdout"] == subprocess.DEVNULL  # detached: the dialog never waits


def test_a_worktree_speaks_as_its_main_checkout(tmp_path):
    repo = git_repo(tmp_path / "cockpit")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    lane = tmp_path / "cockpit-lane"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(lane), "-b", "lane/x"], check=True)
    assert ask_cue.run(payload(lane), spawn=lambda *a, **k: None, log_path=tmp_path / "log") == "cockpit: needs your answer"


def test_other_tools_and_bad_input_stay_silent_and_a_failed_launch_is_logged(tmp_path):
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
