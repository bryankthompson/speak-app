"""speak --lines NAME: a cockpit's recorded line list. Reads files only; no network, no audio."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))
import profiles  # noqa: E402


def test_lists_lines_without_comments_and_the_other_names_in_the_voice(tmp_path, monkeypatch, capsys):
    (tmp_path / "lyrika.txt").write_text("# heading\nlyrika: spend needs your approval\n\nlyrika: that worked\n")
    monkeypatch.setattr(profiles, "LINES_DIR", tmp_path)
    assert profiles.show_lines("lyrika") == 0
    out = capsys.readouterr().out.splitlines()
    assert "lyrika: spend needs your approval" in out and "lyrika: that worked" in out
    assert not any(l.startswith("#") for l in out)
    assert not any("heading" in l for l in out)


def test_unknown_name_exits_1_and_names_the_lists(tmp_path, monkeypatch, capsys):
    (tmp_path / "lyrika.txt").write_text("lyrika: x\n")
    monkeypatch.setattr(profiles, "LINES_DIR", tmp_path)
    assert profiles.show_lines("nobody") == 1
    assert "Lists: lyrika" in capsys.readouterr().err


def test_every_recorded_list_row_starts_with_its_own_name():
    for f in (ROOT / "phrases" / "lines").glob("*.txt"):
        rows = [r for r in f.read_text().splitlines() if r.strip() and not r.startswith("#")]
        assert rows and all(r.startswith(f"{f.stem}: ") for r in rows), f.name
