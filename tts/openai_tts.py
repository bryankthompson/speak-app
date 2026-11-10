#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "openai>=1.0.0",
#   "python-dotenv>=1.0.0",
#   "pygame>=2.5.0",
# ]
# ///

"""
OpenAI TTS provider for Claude Code hooks.
Uses OpenAI's text-to-speech API with multiple voice options.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import soundbite

# Voice options
VoiceType = Literal["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"]


# 1Password item holding the current key (override with OPENAI_OP_ITEM)
OP_ITEM = os.getenv("OPENAI_OP_ITEM", "2bh7y4x2rbzm673mls67j6j2ry")


def _key_from_1password() -> Optional[str]:
    """Read the OpenAI key via the `op` CLI. Returns None (and says why) if that fails."""
    import subprocess
    try:
        r = subprocess.run(["op", "item", "get", OP_ITEM, "--fields", "credential", "--reveal"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"1Password lookup failed: {e}", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"1Password lookup failed: {r.stderr.strip()[:120]}", file=sys.stderr)
        return None
    return r.stdout.strip() or None

def speak_with_openai(
    text: str, 
    voice: VoiceType = "nova",
    model: str = "tts-1",
    speed: float = 1.0
) -> bool:
    """
    Convert text to speech using OpenAI's TTS API.
    
    Args:
        text: Text to convert to speech
        voice: Voice to use (alloy, ash, coral, echo, fable, onyx, nova, sage, shimmer)
        model: TTS model to use (tts-1 or tts-1-hd)
        speed: Speech speed (0.25 to 4.0)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import openai
        from openai import OpenAI
        import pygame
        
        # Load environment variables
        env_path = Path.home() / "brainpods" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        # Soundbite repository: a stored phrase plays without touching the API (or the key)
        keep = True
        tmp_path = soundbite.lookup(text, "openai", voice, model, speed)
        if tmp_path:
            print(f"soundbite hit: {tmp_path.name}", file=sys.stderr)
            tmp_path = str(tmp_path)
        else:
            # Get API key: the environment first, 1Password when it is missing or rejected
            api_key = os.getenv("OPENAI_API_KEY") or _key_from_1password()
            if not api_key:
                print("OpenAI API key not found in environment or 1Password", file=sys.stderr)
                return False

            def create(key):
                return OpenAI(api_key=key).audio.speech.create(
                    model=model, voice=voice, input=text, speed=speed)

            try:
                response = create(api_key)
            except openai.AuthenticationError:
                print("OpenAI rejected the environment key; trying 1Password", file=sys.stderr)
                op_key = _key_from_1password()
                if not op_key or op_key == api_key:
                    raise
                response = create(op_key)
            audio = b"".join(response.iter_bytes())

            saved = soundbite.save(text, "openai", voice, audio, model, speed)
            if saved:
                tmp_path = str(saved)
            else:
                # Repo unavailable: play from a throwaway temp file as before
                keep = False
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                    tmp_path = tmp_file.name
                    tmp_file.write(audio)

        # Detect WSL and use appropriate playback method
        import subprocess
        import platform
        import shutil
        import time

        is_wsl = "microsoft" in platform.uname().release.lower()

        if is_wsl:
            # WSL: Use Windows MediaPlayer class for audio playback
            try:
                # Convert WSL path to Windows path
                win_path = subprocess.check_output(['wslpath', '-w', tmp_path], text=True).strip()

                # PowerShell script using MediaPlayer (System.Windows.Media)
                ps_script = f"""
                Add-Type -AssemblyName PresentationCore
                $mediaPlayer = New-Object System.Windows.Media.MediaPlayer
                $mediaPlayer.Open([uri]"{win_path}")
                $mediaPlayer.Play()
                Start-Sleep -Seconds 1
                while ($mediaPlayer.Position.TotalSeconds -lt $mediaPlayer.NaturalDuration.TimeSpan.TotalSeconds) {{
                    Start-Sleep -Milliseconds 100
                }}
                $mediaPlayer.Stop()
                $mediaPlayer.Close()
                """

                result = subprocess.run(
                    ['powershell.exe', '-Command', ps_script],
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0 and result.stderr:
                    print(f"PowerShell error: {result.stderr}", file=sys.stderr)

            except Exception as e:
                print(f"Windows audio playback error: {e}", file=sys.stderr)
            finally:
                # Cleanup after playback
                time.sleep(0.5)
                if not keep:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        else:
            # Native Linux: Use pygame
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()

                # Wait for playback to complete
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)

                # Cleanup
                pygame.mixer.quit()
                if not keep:
                    os.unlink(tmp_path)
            except Exception as e:
                print(f"pygame audio playback error: {e}", file=sys.stderr)
                # Cleanup on error
                if not keep:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        
        return True
        
    except Exception as e:
        print(f"OpenAI TTS error: {e}", file=sys.stderr)
        return False

def main():
    """Main entry point for standalone usage."""
    import random
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='OpenAI TTS provider for Claude Code')
    parser.add_argument('text', nargs='*', help='Text to speak')
    parser.add_argument('--voice', choices=["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"], 
                        help='Voice to use (default: nova)')
    parser.add_argument('--model', choices=["tts-1", "tts-1-hd"], 
                        help='Model to use (default: tts-1)')
    parser.add_argument('--speed', type=float, 
                        help='Speech speed (0.25-4.0, default: 1.0)')
    parser.add_argument('--test', action='store_true', 
                        help='Test OpenAI TTS functionality')
    parser.add_argument('--list-voices', action='store_true',
                        help='List available voices')
    parser.add_argument('--test-voice', 
                        help='Test a specific voice')
    
    args = parser.parse_args()
    
    # Handle list voices
    if args.list_voices:
        voices = ["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"]
        print("Available OpenAI voices:")
        for voice in voices:
            print(f"  - {voice}")
        sys.exit(0)
    
    # Handle test voice
    if args.test_voice:
        if args.test_voice not in ["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"]:
            print(f"Invalid voice: {args.test_voice}", file=sys.stderr)
            sys.exit(1)
        
        test_text = f"Testing OpenAI voice: {args.test_voice}"
        success = speak_with_openai(test_text, voice=args.test_voice)
        sys.exit(0 if success else 1)
    
    # Get text from command line or use default
    if args.text:
        text = " ".join(args.text)
    elif args.test:
        # Fun test messages
        messages = [
            "OpenAI text-to-speech is operational!",
            "High-quality voice synthesis ready.",
            "Claude Code audio feedback enabled.",
            "Neural voice synthesis active.",
        ]
        text = random.choice(messages)
    else:
        # Default message
        text = "OpenAI TTS ready."
    
    # Get parameters from args or environment
    voice = args.voice or os.getenv("OPENAI_TTS_VOICE", "nova")
    model = args.model or os.getenv("OPENAI_TTS_MODEL", "tts-1")
    speed = args.speed or float(os.getenv("OPENAI_TTS_SPEED", "1.0"))
    
    # Validate parameters
    if voice not in ["alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"]:
        print(f"Invalid voice: {voice}", file=sys.stderr)
        sys.exit(1)
    
    if model not in ["tts-1", "tts-1-hd"]:
        print(f"Invalid model: {model}", file=sys.stderr)
        sys.exit(1)
    
    if not (0.25 <= speed <= 4.0):
        print(f"Invalid speed: {speed} (must be between 0.25 and 4.0)", file=sys.stderr)
        sys.exit(1)
    
    # Speak the text
    success = speak_with_openai(text, voice=voice, model=model, speed=speed)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()