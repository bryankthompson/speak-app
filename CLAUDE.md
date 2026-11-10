# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Speak is a cost-optimized, universal text-to-speech command-line tool with intelligent provider fallback and a stored-clip library.

## Installation

For complete installation instructions, see **[INSTALLATION.md](INSTALLATION.md)**

**Quick setup checklist:**
1. Clone repo to `~/speak-app`
2. Create symlinks in `~/bin` for all `speak*` commands
3. Add `~/bin` to PATH in `~/.bash_aliases`
4. Configure TTS environment variables in `~/.bash_aliases` (OpenAI recommended)
5. Source `~/.bash_aliases` and test with `speak --status`

## Key Architecture

### Provider System
- **Abstract Interface**: All providers inherit from `TTSProvider` base class in `tts/tts_provider.py`
- **Provider Selection**: OpenAI (default) → ElevenLabs → pyttsx3 (always available)
- **Cost Optimization**: OpenAI provides 95% cost reduction vs ElevenLabs
- **Provider Scripts**: Each provider has its own implementation in `tts/[provider]_tts.py`

### Cost Optimization System
- **Stored Clips**: `tts/soundbite.py` keeps every paid clip and looks it up first, so a phrase is paid for once
- **Development Mode**: `speak-dev` forces offline TTS to prevent accidental API usage

### Python Execution Model
- Scripts use `#!/usr/bin/env -S uv run --quiet --script` for dependency management
- Main entry point: `speak` (Bash) → `tts/tts_provider.py` (Python)
- Non-blocking execution for CLI integration
- **All providers execute scripts directly** to respect shebang: `cmd = [str(script_path), text]`
- This ensures `uv` handles dependencies automatically for all providers

### Audio Playback Architecture
- **Native Linux**: Uses `pygame.mixer` for audio playback with ALSA/PulseAudio
- **WSL2 Auto-Detection**: Automatically detects Windows Subsystem for Linux environments
- **WSL Audio Solution**: Uses `System.Windows.Media.MediaPlayer` via PowerShell
  - Detects WSL by checking for "microsoft" in `platform.uname().release`
  - Converts Linux paths to Windows paths using `wslpath -w`
  - Plays audio through Windows audio subsystem (no visible windows)
  - Handles WSLGd audio issues automatically
- **Fallback Strategy**: If pygame fails, gracefully degrades without breaking execution

### Voice Profiles (docs/VOICES.md)
- **Profiles**: `phrases/profiles.json` (voices + cockpit assignments), `phrases/casting.json` (models, append-only clause menu); `tts/profiles.py` backs `speak --profiles | --assign | --profile`
- **Join**: `tts/phrase_join.py` turns `speak "name: clause"` into stored name + clause clips; free text in that voice; unknown names logged to `~/.cache/speak-app/voice_misses.log`
- **Soundbite**: `tts/soundbite.py`, library at `~/soundbite` (`SOUNDBITE_DIR`); every paid clip is stored and looked up first
- **Leveling**: `tts/level_clips.py measure|apply|verify|run` evens voice loudness; guide in docs/LEVELING.md
- **Record**: `phrases/record.py --provider P [--profile ID | --only IDS | --reindex]`, run `--dry-run` first; it and `phrases/sfx.py` call paid APIs on purpose (free-text lines also pay once)
- **Plugin**: `plugins/speak-voices` (Claude Code), docs/VOICES-COCKPIT.md for cockpit use; `tests/test_voices_docs.py` keeps the docs' flags honest

- **Per-repo gate**: `tts/repo_gate.py` (registry `~/.config/speak-app/repos.json`, log `speech.log`); gate runs in `tts_provider.main` before `phrase_join`; `speak --alert` = warning, always speaks (docs/VOICES.md)

### Observability System (`tts/observability.py`)
- **Event Priority Levels**: CRITICAL (100%) → HIGH (80%) → NORMAL (50%) → LOW (20%) → MINIMAL (5%)
- **Rate Limiting**: Per-category limits to prevent audio spam
- **Burst Detection**: Detects rapid event sequences and filters accordingly

## Development Commands

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_openai_tts.py

# Run tests with specific marker
pytest -m unit
pytest -m api
pytest -m elevenlabs
pytest -m audio_output  # Manual audio tests
pytest -m manual  # Tests requiring human verification

# Run single test
pytest tests/test_openai_tts.py::test_openai_tts_basic_functionality -v
```

### Testing TTS Functionality
```bash
# Test TTS functionality
speak --test

# Test specific provider
speak --provider openai "Test message"
speak --provider elevenlabs "Test message"
speak --provider pyttsx3 "Test message"

# Cost-optimized testing
speak-dev "Test message"  # Always uses pyttsx3 (free)
speak-with-tracking "Test message"  # Shows cost per message

# List available providers and configuration
speak --list
speak --status

# Test voice selection (ElevenLabs)
speak --list-voices
speak --test-voice Rachel
speak --voice 21m00Tcm4TlvDq8ikWAM "Custom voice test"

# Test Python components directly
python3 tts/tts_provider.py "test message"
python3 tts/observability.py  # Run observability tests

# Cost per message
speak-with-tracking "Test message"
```

### Voice Testing (Priority)
```bash
# Run all voice quality tests (most important tests)
pytest tests/test_manual_audio.py -v -s -m audio_output

# Test specific provider voices
pytest tests/test_manual_elevenlabs_voices.py -v -s
pytest tests/test_manual_openai_voices.py -v -s

# Provider comparison
pytest tests/test_manual_provider_comparison.py -v -s

# Quick voice test
pytest tests/test_manual_audio.py::TestManualAudio::test_basic_tts_provider -v -s
```

## Configuration

Environment variables should be set globally in `~/.bash_aliases`:
- `TTS_ENABLED`: Enable/disable TTS globally (default: true)
- `TTS_PROVIDER`: Default provider (openai/elevenlabs/pyttsx3/auto) - **Recommended: openai**
- `OPENAI_API_KEY`: For OpenAI TTS (primary provider)
- `ELEVENLABS_API_KEY`: For ElevenLabs TTS (premium only)
- `OPENAI_TTS_VOICE`: OpenAI voice selection (default: nova, recommended: onyx)
- `OPENAI_TTS_MODEL`: Model selection (tts-1/tts-1-hd, default: tts-1)
- `ELEVENLABS_VOICE_ID`: Custom voice selection (default: Rachel - 21m00Tcm4TlvDq8ikWAM)
- `ELEVENLABS_MODEL_ID`: Model selection (default: eleven_turbo_v2_5)
- `ENGINEER_NAME`: For personalized messages
- `PYTTSX3_VOICE_ID`: Specific voice for pyttsx3 (optional)
- `ESPEAK_RATE`: Speech rate for espeak fallback (default: 180)
- `ESPEAK_VOICE`: Voice for espeak fallback (default: en)

### Cost Optimization Setup
Quick setup for 95% cost reduction:
```bash
# Run the setup script
./set_openai_default.py

# Or manually add to ~/.bash_aliases
export TTS_PROVIDER=openai
export OPENAI_API_KEY="your-openai-key"
export OPENAI_TTS_VOICE=onyx
```

The speak script also checks `~/brainpods/.env` as a fallback for additional configuration.

## Code Patterns

### Adding New Provider
1. Create `tts/[provider]_tts.py` implementing the provider interface
2. Add provider to `PROVIDERS` dict in `tts/tts_provider.py`
3. Handle API key and configuration in provider class
4. Implement `is_available()` and `speak()` methods
5. Add tests in `tests/test_[provider]_tts.py`

### Error Handling
- Use proper exit codes: 0 (success), 1 (general error), 2 (provider error)
- Log errors to stderr, not stdout
- Fail silently in non-critical contexts (e.g., notifications)
- Provider fallback is automatic on failures
- pyttsx3 automatically falls back to espeak on Linux when initialization fails

### Testing Infrastructure
- Test framework: pytest with fixtures in `tests/conftest.py`
- Test markers: unit, integration, voice, api, elevenlabs, regression, slow, audio_output, manual, interactive, openai, pyttsx3
- Mock fixtures for API responses, audio playback, and environment variables
- Provider-specific test files for comprehensive coverage
- Voice quality tests are the highest priority (test_manual_audio.py)

## Documentation

### README.md
Comprehensive user guide covering:
- Installation and setup instructions
- All command-line options (`--provider`, `--list`, `--test`, `--status`, `--off`, etc.)
- Provider details with latency characteristics
- Integration patterns for scripts and CI/CD
- Security best practices
- Troubleshooting guide

### CHANGELOG.md
- Version history starting from v1.0.0 (2025-07-18)
- Planned features roadmap including voice selection, multi-language support, and web API

### Integration Patterns
- **Scripts**: Use `--off` flag in loops to prevent spam
- **CI/CD**: Set `TTS_ENABLED=false` or use `TTS_PROVIDER=pyttsx3` for offline mode
- **Error Handling**: `speak "message" || echo "TTS failed, using fallback"`
- **Performance**: ElevenLabs (~500ms), OpenAI (~300ms), pyttsx3 (<10ms)

## Voice Configuration

### ElevenLabs Voices
- Default: Rachel (21m00Tcm4TlvDq8ikWAM) - calm narration voice
- Alternative voices: Domi, Bella, custom voices
- Voice settings: stability (0.0-1.0), similarity_boost (0.0-1.0)
- List available voices: `speak --list-voices`
- Test specific voice: `speak --test-voice [voice_name_or_id]`

### OpenAI Voices
- Available voices: alloy, echo, fable, onyx, nova, shimmer
- Default: nova
- Models: tts-1 (faster), tts-1-hd (higher quality)
- Speed control: 0.25 to 4.0x

## Project Status Notes
- Comprehensive test suite with 126+ tests across providers
- Production-ready with mature error handling and fallback mechanisms
- Missing: git repository initialization (project not under version control)
- Voice quality testing is the top priority for the application
- pyttsx3 offline fallback working with automatic espeak support on Linux

## Documentation Structure

### User Documentation
- [README.md](README.md) - Main user guide with installation, usage, and examples
- [CHANGELOG.md](CHANGELOG.md) - Version history and feature roadmap
- [CONTRIBUTING.md](CONTRIBUTING.md) - Guidelines for contributing to the project

### Integration Guides
- [Claude Code Integration Guide](docs/CLAUDE_CODE_INTEGRATION.md) - Hook system and voice notifications
- [Shell Script Integration](docs/INTEGRATION.md) - Bash scripts and workflow integration
- [API Documentation](docs/API.md) - Programmatic usage and Python integration
- [Get-Up-To-Speed Integration Example](examples/get-up-to-speed-integration.sh) - Real-world integration with Claude Code commands
- [notify_tts() Function](docs/NOTIFY_TTS_INTEGRATION.md) - Standard TTS notification function for Claude Code slash commands

### Provider Documentation
- [Provider Configuration](docs/PROVIDERS.md) - Setting up TTS providers
- [pyttsx3 Configuration Guide](docs/PYTTSX3_CONFIG.md) - Offline TTS setup and troubleshooting

### Testing Documentation
- [Voice Testing Guide](docs/VOICE_TESTING_GUIDE.md) - Comprehensive voice quality testing procedures
- [Testing Priorities](docs/TESTING_PRIORITIES.md) - Voice functionality is Priority 1 (CRITICAL)
- [Voice Test Summary](tests/VOICE_TEST_SUMMARY.md) - Quick reference for running voice tests

### Function Documentation
- [notify_tts() Integration](docs/NOTIFY_TTS_INTEGRATION.md) - Comprehensive guide for the notify_tts() function used in get-up-to-speed scripts
- [notify_tts() Quick Reference](docs/NOTIFY_TTS_QUICK_REFERENCE.md) - Quick reference for notify_tts() usage and priority levels