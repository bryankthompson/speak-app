# Voice Testing Guide

Simple guide to test if TTS voices are working properly.

## Quick Test

The fastest way to test all voices:

```bash
# From the speak-app directory
python test_voices_quick.py
```

This will test each provider and play audio to verify they work.

## Manual Voice Tests

### Test All OpenAI Voices

```bash
# Test all 6 OpenAI voices
pytest tests/test_manual_openai_voices.py -v -s -m audio_output

# Or run directly
python tests/test_manual_openai_voices.py
```

OpenAI voices:
- **alloy** - Neutral and balanced
- **echo** - Warm and engaging  
- **fable** - Expressive and dynamic
- **onyx** - Deep and authoritative
- **nova** - Natural and conversational (default)
- **shimmer** - Gentle and soothing

### Test ElevenLabs Voices

```bash
# Test ElevenLabs voices
pytest tests/test_manual_elevenlabs_voices.py -v -s -m audio_output
```

### Test All Providers Side-by-Side

```bash
# Compare all providers
pytest tests/test_manual_provider_comparison.py -v -s -m audio_output
```

## Automated Voice Tests

Run automated tests that verify voices work (with actual audio):

```bash
# Test all voices automatically
pytest tests/test_all_voices_simple.py -v -s -m voice_test

# Quick test (one voice per provider)
pytest tests/test_all_voices_simple.py -v -s -m quick
```

## Command Line Testing

Test individual providers directly:

```bash
# Test pyttsx3 (always works, no API key needed)
python -m tts.pyttsx3_tts "Test offline voice"

# Test OpenAI (requires OPENAI_API_KEY)
python -m tts.openai_tts "Test OpenAI" --voice nova
python -m tts.openai_tts --test
python -m tts.openai_tts --list-voices

# Test ElevenLabs (requires ELEVENLABS_API_KEY)
python -m tts.elevenlabs_tts "Test ElevenLabs"
python -m tts.elevenlabs_tts --list-voices
```

## Using the speak Command

```bash
# Test default provider
speak "Test message"

# Test specific provider
speak --provider pyttsx3 "Offline test"
speak --provider openai "OpenAI test"  
speak --provider elevenlabs "ElevenLabs test"

# Test without audio (useful for checking setup)
speak --off "Test without playing audio"

# Check current configuration
speak --status
speak --list
```

## Setting Up API Keys

For OpenAI and ElevenLabs to work, you need API keys:

```bash
# Add to ~/.bash_aliases or ~/.bashrc
export OPENAI_API_KEY="your-openai-key"
export ELEVENLABS_API_KEY="your-elevenlabs-key"

# Set default voices (optional)
export OPENAI_TTS_VOICE="nova"  # or alloy, echo, fable, onyx, shimmer
export ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"  # Rachel voice
```

## Troubleshooting

### No Sound
- Check volume is not muted
- Try `speak --provider pyttsx3 "Test"` (works offline)
- Check `speak --status` for errors

### API Errors
- Verify API keys are set: `echo $OPENAI_API_KEY`
- Check API key is valid
- Try with `--off` flag to skip audio playback

### Provider Not Working
- Use `speak --list` to see available providers
- Try fallback: `speak --provider pyttsx3 "Test"`
- Check error messages in stderr

## Cost Notes

- **pyttsx3**: Free (offline)
- **OpenAI**: ~$0.015 per 1,000 characters
- **ElevenLabs**: ~$0.30 per 1,000 characters

See [docs/PROVIDERS.md](../docs/PROVIDERS.md) for the provider price comparison.