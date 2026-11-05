#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-dotenv>=1.0.0",
# ]
# ///

"""
TTS provider selection logic for Claude Code hooks.
Intelligently selects the best available TTS provider based on API keys and preferences.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Callable
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

class TTSProvider:
    """Manages TTS provider selection and execution."""
    
    def __init__(self):
        """Initialize TTS provider with environment configuration."""
        # Load environment variables
        if load_dotenv:
            env_path = Path.home() / "brainpods" / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        
        self.tts_enabled = os.getenv("TTS_ENABLED", "true").lower() == "true"
        self.provider_preference = os.getenv("TTS_PROVIDER", "auto")
        self.utils_dir = Path(__file__).parent
        
    def get_available_providers(self) -> List[str]:
        """Get list of available TTS providers based on API keys."""
        providers = []
        
        # Check for API keys
        if os.getenv("ELEVENLABS_API_KEY"):
            providers.append("elevenlabs")
        if os.getenv("OPENAI_API_KEY"):
            providers.append("openai")
        
        # pyttsx3 is always available as offline fallback
        providers.append("pyttsx3")
        
        return providers
    
    def select_provider(self) -> Optional[str]:
        """Select the best available TTS provider."""
        if not self.tts_enabled:
            return None
        
        available = self.get_available_providers()
        
        # If specific provider requested, check if available
        if self.provider_preference != "auto":
            if self.provider_preference in available:
                return self.provider_preference
            else:
                print(f"Requested provider '{self.provider_preference}' not available, falling back", file=sys.stderr)
        
        # Auto selection priority: OpenAI > ElevenLabs > pyttsx3
        # OpenAI is prioritized for cost optimization (95% cheaper than ElevenLabs)
        priority = ["openai", "elevenlabs", "pyttsx3"]
        
        for provider in priority:
            if provider in available:
                return provider
        
        return None
    
    def speak(self, text: str, provider: Optional[str] = None, voice_id: Optional[str] = None, 
              voice_settings: Optional[dict] = None) -> bool:
        """
        Speak text using the selected or specified provider.
        
        Args:
            text: Text to speak
            provider: Optional specific provider to use
            voice_id: Optional voice ID (for supported providers)
            voice_settings: Optional voice settings (for supported providers)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.tts_enabled:
            return False
        
        # Select provider if not specified
        if not provider:
            provider = self.select_provider()
        
        if not provider:
            print("No TTS provider available", file=sys.stderr)
            return False
        
        # Get provider script path
        script_map = {
            "elevenlabs": self.utils_dir / "elevenlabs_tts.py",
            "openai": self.utils_dir / "openai_tts.py",
            "pyttsx3": self.utils_dir / "pyttsx3_tts.py",
        }
        
        script_path = script_map.get(provider)
        if not script_path or not script_path.exists():
            print(f"TTS provider script not found: {provider}", file=sys.stderr)
            return False
        
        # Execute TTS script directly to respect shebang (for uv support)
        try:
            # Build command with voice parameters
            # Execute script directly to use uv for all providers
            cmd = [str(script_path), text]
            
            # Add voice parameters for supported providers
            if provider == "elevenlabs":
                if voice_id:
                    cmd.extend(["--voice-id", voice_id])
                if voice_settings:
                    if "stability" in voice_settings:
                        cmd.extend(["--stability", str(voice_settings["stability"])])
                    if "similarity_boost" in voice_settings:
                        cmd.extend(["--similarity-boost", str(voice_settings["similarity_boost"])])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode != 0:
                print(f"TTS provider {provider} failed: {result.stderr}", file=sys.stderr)
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            print(f"TTS provider {provider} timed out", file=sys.stderr)
            return False
        except Exception as e:
            print(f"TTS provider {provider} error: {e}", file=sys.stderr)
            return False
    
    def speak_with_fallback(self, text: str, voice_id: Optional[str] = None, 
                            voice_settings: Optional[dict] = None) -> bool:
        """
        Attempt to speak text with automatic fallback to other providers.
        
        Args:
            text: Text to speak
            voice_id: Optional voice ID (for supported providers)
            voice_settings: Optional voice settings (for supported providers)
            
        Returns:
            True if any provider succeeded, False if all failed
        """
        if not self.tts_enabled:
            return False
        
        # Get provider order
        providers = self.get_available_providers()
        
        # Try each provider in order
        for provider in providers:
            # Only pass voice parameters to supporting providers
            if provider == "elevenlabs":
                if self.speak(text, provider, voice_id, voice_settings):
                    return True
            else:
                if self.speak(text, provider):
                    return True
        
        return False

def main():
    """Main entry point for testing."""
    import random
    import argparse
    
    parser = argparse.ArgumentParser(description='TTS provider selection')
    parser.add_argument('text', nargs='*', help='Text to speak')
    parser.add_argument('--voice-id', '--voice', help='Voice ID to use')
    parser.add_argument('--stability', type=float, help='Voice stability (0.0-1.0)')
    parser.add_argument('--similarity-boost', type=float, help='Voice similarity boost (0.0-1.0)')
    parser.add_argument('--provider', help='Specific provider to use')
    parser.add_argument('--alert', action='store_true', help='A warning: always speaks (per-repo gate)')
    
    args = parser.parse_args()
    
    # Test messages
    if args.text:
        text = " ".join(args.text)
    else:
        messages = [
            "TTS provider selection is working!",
            "Intelligent voice synthesis active.",
            "Multi-provider TTS ready.",
        ]
        text = random.choice(messages)
    
    # Per-repo gate: a repo not listed while the gate is on stays silent (warnings always speak)
    sys.path.insert(0, str(Path(__file__).parent))
    import repo_gate
    allow, voices, repo, reason = repo_gate.decide(args.alert)
    repo_gate.log(reason, repo, text)
    if reason.startswith("invalid"):
        print(f"speak: {reason}; fix or remove the registry", file=sys.stderr)
        sys.exit(3)
    if not allow:
        print(f"skipped: {repo} not enabled; run: speak --here on")
        sys.exit(0)

    # A line naming a cast lead ("hades: go or no-go?") is spoken in that lead's voice from the soundbite library
    if voices and not args.voice_id and os.getenv("TTS_ENABLED", "true") != "false":
        import phrase_join
        if phrase_join.try_join(text):
            sys.exit(0)

    # Create provider and speak
    tts = TTSProvider()
    
    print(f"Available providers: {tts.get_available_providers()}")
    print(f"Selected provider: {tts.select_provider()}")
    
    # Build voice settings
    voice_settings = None
    if args.stability is not None or args.similarity_boost is not None:
        voice_settings = {}
        if args.stability is not None:
            voice_settings["stability"] = args.stability
        if args.similarity_boost is not None:
            voice_settings["similarity_boost"] = args.similarity_boost
    
    # Speak with or without fallback
    if args.provider:
        success = tts.speak(text, args.provider, args.voice_id, voice_settings)
    else:
        success = tts.speak_with_fallback(text, args.voice_id, voice_settings)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()