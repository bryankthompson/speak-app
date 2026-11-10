# speak-app Test Suite

This directory contains the comprehensive test suite for the speak-app, with a focus on **voice quality and functionality testing**.

## Test Organization

### Voice Tests (Priority 1)
These are the most important tests - they verify actual audio output:

- **`test_manual_audio.py`** - Core TTS functionality tests
- **`test_manual_elevenlabs_voices.py`** - ElevenLabs voice variety tests  
- **`test_manual_openai_voices.py`** - OpenAI voice variety tests
- **`test_manual_provider_comparison.py`** - Side-by-side provider comparison

### Integration Tests
- **`test_speak_bash_integration.py`** - Bash script integration
- **`test_pipe_integration.py`** - Unix pipe functionality
- **`test_e2e_integration.py`** - End-to-end workflows

### Unit Tests
- **`test_tts_provider_selection.py`** - Provider selection logic
- **`test_error_handling.py`** - Error recovery mechanisms
- **`test_provider_fallback.py`** - Fallback functionality
- **`test_environment_config.py`** - Configuration handling

### API Tests
- **`test_openai_api_integration.py`** - OpenAI API integration
- **`test_api_integration.py`** - General API functionality

### Utility Tests
- **`test_observability.py`** - Monitoring system

## Running Voice Tests

### Quick Start
```bash
# Test that TTS works at all (most important!)
pytest test_manual_audio.py::TestManualAudio::test_basic_tts_provider -v -s

# Test all providers
pytest test_manual_audio.py -v -s -m audio_output
```

### Full Voice Test Suite
```bash
# All manual audio tests (includes all voice tests)
pytest test_manual_*.py -v -s -m audio_output

# Specific provider
pytest -k "elevenlabs" -v -s -m audio_output
pytest -k "openai" -v -s -m audio_output  
pytest -k "pyttsx3" -v -s -m audio_output
```

### Interactive Testing
```bash
# Try custom text with any provider
pytest test_manual_audio.py::TestManualAudio::test_interactive_mode -v -s

# Compare all providers with your text
pytest test_manual_provider_comparison.py::TestProviderComparison::test_interactive_comparison -v -s
```

## Test Markers

- `@pytest.mark.audio_output` - Tests that produce actual audio (requires speakers)
- `@pytest.mark.manual` - Tests requiring human verification
- `@pytest.mark.interactive` - Tests with user input
- `@pytest.mark.elevenlabs` - ElevenLabs-specific tests
- `@pytest.mark.openai` - OpenAI-specific tests
- `@pytest.mark.pyttsx3` - pyttsx3-specific tests
- `@pytest.mark.slow` - Long-running tests

## Prerequisites

### For Voice Tests
1. **Audio Output**: Speakers or headphones connected
2. **API Keys** (optional, for cloud providers):
   ```bash
   export ELEVENLABS_API_KEY="your-key"
   export OPENAI_API_KEY="your-key"
   ```

### For All Tests
```bash
# Install test dependencies
pip install pytest pytest-mock

# Or use uv (recommended)
uv pip install pytest pytest-mock
```

## Test Coverage Areas

### 1. Voice Quality (Most Important)
- Audio clarity and pronunciation
- Voice naturalness
- Emotional expression
- Technical content handling

### 2. Functionality
- Provider selection
- Fallback mechanisms
- Error handling
- Configuration

### 3. Performance
- Response latency
- Long content handling
- Concurrent requests
- Resource usage

### 4. Integration
- Shell script usage
- Pipe support
- CI/CD compatibility
- Cross-platform

## Writing New Tests

### Voice Test Template
```python
@pytest.mark.manual
@pytest.mark.audio_output
def test_new_voice_feature(self):
    """Test description for human verification."""
    print("\n🎤 Testing new feature...")
    
    # Perform TTS
    result = speak_with_provider("Test text")
    assert result is True
    
    # Pause for listening
    time.sleep(3)
    
    print("✅ Test completed")
    print("❓ Did the audio sound correct?")
```

### Key Principles
1. **Human Verification**: Voice tests need human ears
2. **Clear Output**: Print what's being tested
3. **Adequate Pauses**: Allow time to listen
4. **Multiple Providers**: Test across all providers
5. **Real Content**: Use realistic test text

## Debugging Test Failures

### Common Issues

1. **No Audio Output**
   - Check system volume
   - Verify audio device: `speaker-test`
   - Test espeak directly: `espeak "test"`

2. **API Errors**
   - Verify API keys are set
   - Check API quotas/limits
   - Test provider directly

3. **Import Errors**
   - Run from project root
   - Check Python path includes `tts/`

### Debug Commands
```bash
# Verbose test output
pytest test_manual_audio.py -vvs

# Run specific test with full traceback
pytest test_manual_audio.py::TestManualAudio::test_basic_tts_provider -vvs --tb=long

# Check test collection
pytest --collect-only test_manual_audio.py
```

## Continuous Integration

While voice quality tests require human verification, these tests can run in CI:

```bash
# Non-audio tests only
pytest -m "not audio_output" 

# Unit tests only  
pytest test_tts_provider_selection.py test_error_handling.py -v

# Integration tests (no audio)
pytest test_environment_config.py test_soundbite.py -v
```

## Test Maintenance

### Regular Testing Schedule
- **Daily**: Basic smoke tests (does it work?)
- **Weekly**: Full voice quality suite
- **Monthly**: Comprehensive provider comparison
- **Release**: All tests including edge cases

### Updating Tests
- Keep test audio examples relevant
- Update voice IDs when providers change
- Add tests for new features
- Document expected outcomes

## Resources

- [Voice Testing Guide](../docs/VOICE_TESTING_GUIDE.md) - Detailed testing procedures
- [Testing Priorities](../docs/TESTING_PRIORITIES.md) - What to test first
- [Test Summary](VOICE_TEST_SUMMARY.md) - Quick reference guide