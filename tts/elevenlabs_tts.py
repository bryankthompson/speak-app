#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests>=2.31.0",
#   "pygame>=2.5.0",
#   "python-dotenv>=1.0.0",
# ]
# ///

"""
ElevenLabs TTS provider for Claude Code hooks.
High-quality AI voice synthesis with multiple voice options.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
import soundbite

def get_available_voices() -> Optional[list]:
    """
    Get list of available voices from ElevenLabs API.
    
    Returns:
        List of voice data or None if failed
    """
    try:
        import requests
        
        # Load environment variables
        env_path = Path.home() / "brainpods" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        # Get API key
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            print("ElevenLabs API key not found in environment", file=sys.stderr)
            return None
        
        # ElevenLabs voices API endpoint
        url = "https://api.elevenlabs.io/v1/voices"
        
        headers = {
            "Accept": "application/json",
            "xi-api-key": api_key
        }
        
        # Make API request
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"ElevenLabs API error: {response.status_code} - {response.text}", file=sys.stderr)
            return None
        
        return response.json().get("voices", [])
        
    except Exception as e:
        print(f"Error getting ElevenLabs voices: {e}", file=sys.stderr)
        return None

def validate_voice_settings(settings: dict) -> bool:
    """
    Validate voice settings parameters.
    
    Args:
        settings: Voice settings dictionary
        
    Returns:
        True if settings are valid, False otherwise
    """
    if not isinstance(settings, dict):
        return False
    
    stability = settings.get("stability", 0.5)
    similarity_boost = settings.get("similarity_boost", 0.5)
    
    # Validate ranges
    if not (0.0 <= stability <= 1.0):
        return False
    if not (0.0 <= similarity_boost <= 1.0):
        return False
    
    return True

def find_voice_by_name(name: str) -> Optional[str]:
    """
    Find voice ID by voice name.
    
    Args:
        name: Voice name to search for
        
    Returns:
        Voice ID if found, None otherwise
    """
    voices = get_available_voices()
    if not voices:
        return None
    
    for voice in voices:
        if voice.get("name", "").lower() == name.lower():
            return voice.get("voice_id")
    
    return None

def validate_voice_id(voice_id: str) -> bool:
    """
    Validate that a voice ID exists and is available.
    
    Args:
        voice_id: Voice ID to validate
        
    Returns:
        True if voice ID is valid, False otherwise
    """
    if not voice_id:
        return False
    
    voices = get_available_voices()
    if not voices:
        return False
    
    for voice in voices:
        if voice.get("voice_id") == voice_id:
            return True
    
    return False

def speak_with_elevenlabs(text: str, voice_id: Optional[str] = None, voice_settings: Optional[dict] = None) -> bool:
    """
    Convert text to speech using ElevenLabs API.
    
    Args:
        text: Text to convert to speech
        voice_id: Optional voice ID (defaults to Rachel)
        voice_settings: Optional voice settings (stability, similarity_boost)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import requests
        import tempfile
        import pygame
        from pathlib import Path as PathLib
        
        # Load environment variables
        env_path = Path.home() / "brainpods" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        # Default to Rachel voice if not specified
        if not voice_id:
            voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        
        # Default voice settings if not specified
        if not voice_settings:
            voice_settings = {
                "stability": float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
                "similarity_boost": float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.5"))
            }
        
        # Validate voice settings
        if not validate_voice_settings(voice_settings):
            print(f"Invalid voice settings: {voice_settings}", file=sys.stderr)
            return False
        
        # Soundbite repository: model + settings are part of the key because they change the audio
        model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
        bite_model = f"{model_id}|s{voice_settings['stability']:g}|b{voice_settings['similarity_boost']:g}"
        bite = soundbite.lookup(text, "elevenlabs", voice_id, bite_model)
        if bite:
            print(f"soundbite hit: {bite.name}", file=sys.stderr)
            tmp_path = str(bite)
            keep = True
        else:
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                print("ElevenLabs API key not found in environment", file=sys.stderr)
                return False

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key
            }
            data = {
                "text": text,
                "model_id": model_id,
                "voice_settings": voice_settings
            }

            response = requests.post(url, json=data, headers=headers)
            if response.status_code != 200:
                print(f"ElevenLabs API error: {response.status_code} - {response.text}", file=sys.stderr)
                return False

            saved = soundbite.save(text, "elevenlabs", voice_id, response.content, bite_model)
            if saved:
                tmp_path = str(saved)
                keep = True
            else:
                keep = False
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                    tmp_file.write(response.content)
                    tmp_path = tmp_file.name

        # Play using pygame
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
        
        return True
        
    except Exception as e:
        print(f"ElevenLabs TTS error: {e}", file=sys.stderr)
        return False

def main():
    """Main entry point for standalone usage."""
    import random
    import argparse
    
    parser = argparse.ArgumentParser(description='ElevenLabs TTS provider')
    parser.add_argument('text', nargs='*', help='Text to speak')
    parser.add_argument('--voice-id', '--voice', help='Voice ID to use')
    parser.add_argument('--voice-name', help='Voice name to use')
    parser.add_argument('--stability', type=float, help='Voice stability (0.0-1.0)')
    parser.add_argument('--similarity-boost', type=float, help='Voice similarity boost (0.0-1.0)')
    parser.add_argument('--list-voices', action='store_true', help='List available voices')
    parser.add_argument('--test-voice', help='Test a specific voice')
    
    args = parser.parse_args()
    
    # List voices if requested
    if args.list_voices:
        voices = get_available_voices()
        if voices:
            print("Available ElevenLabs voices:")
            for voice in voices:
                print(f"  {voice['name']} ({voice['voice_id']}) - {voice['category']}")
                print(f"    {voice['description']}")
        else:
            print("No voices available or API error")
        return
    
    # Test specific voice if requested
    if args.test_voice:
        voice_id = args.test_voice
        # Try to find by name first
        if not validate_voice_id(voice_id):
            voice_id = find_voice_by_name(args.test_voice)
        
        if voice_id:
            text = f"Testing voice {args.test_voice}"
            success = speak_with_elevenlabs(text, voice_id)
            sys.exit(0 if success else 1)
        else:
            print(f"Voice not found: {args.test_voice}", file=sys.stderr)
            sys.exit(1)
    
    # Get text from command line or use default
    if args.text:
        text = " ".join(args.text)
    else:
        # Fun default messages
        messages = [
            "Hello! Claude Code TTS is now active.",
            "ElevenLabs integration successful!",
            "Ready to provide audio feedback for your coding session.",
            "Voice synthesis online and operational.",
        ]
        text = random.choice(messages)
    
    # Determine voice ID
    voice_id = args.voice_id
    if args.voice_name:
        voice_id = find_voice_by_name(args.voice_name)
        if not voice_id:
            print(f"Voice not found: {args.voice_name}", file=sys.stderr)
            sys.exit(1)
    
    # Build voice settings
    voice_settings = None
    if args.stability is not None or args.similarity_boost is not None:
        voice_settings = {}
        if args.stability is not None:
            voice_settings["stability"] = args.stability
        if args.similarity_boost is not None:
            voice_settings["similarity_boost"] = args.similarity_boost
    
    # Speak the text
    success = speak_with_elevenlabs(text, voice_id, voice_settings)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()