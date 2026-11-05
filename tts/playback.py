"""Play one or more mp3 files back to back in a single player session (no gap from process startup).

WSL: one PowerShell/MediaPlayer script plays every file in order. Elsewhere: pygame if importable.
Raises on failure so callers can fall back; never deletes the files it plays.
"""
import platform
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()


def play_files(paths: Sequence[Path]) -> None:
    if not paths:
        return
    if is_wsl():
        wins = [subprocess.check_output(["wslpath", "-w", str(p)], text=True).strip() for p in paths]
        body = "\n".join(f"""
$p = New-Object System.Windows.Media.MediaPlayer
$p.Open([uri]"{w}")
$p.Play()
Start-Sleep -Seconds 1
while ($p.NaturalDuration.HasTimeSpan -and $p.Position.TotalSeconds -lt $p.NaturalDuration.TimeSpan.TotalSeconds) {{ Start-Sleep -Milliseconds 100 }}
$p.Stop(); $p.Close()""" for w in wins)
        r = subprocess.run(["powershell.exe", "-Command", "Add-Type -AssemblyName PresentationCore\n" + body],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"PowerShell playback failed: {r.stderr.strip()[:200]}")
        return
    try:
        import pygame
    except ImportError as e:
        raise RuntimeError("no player: not WSL and pygame is not installed") from e
    pygame.mixer.init()
    try:
        for p in paths:
            pygame.mixer.music.load(str(p))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
    finally:
        pygame.mixer.quit()


if __name__ == "__main__":  # audition: python3 tts/playback.py a.mp3 b.mp3
    play_files([Path(a) for a in sys.argv[1:]])
