#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=7.0.0",
#   "pytest-mock>=3.10.0",
#   "requests>=2.31.0",
#   "pygame>=2.5.0",
#   "python-dotenv>=1.0.0",
# ]
# ///

"""
pytest configuration and fixtures for speak-app tests.
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

# Add the project root to the path so we can import modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tts"))

@pytest.fixture
def mock_env():
    """Mock environment variables for testing."""
    with patch.dict(os.environ, {
        'ELEVENLABS_API_KEY': 'test_api_key_123',
        'ELEVENLABS_VOICE_ID': '21m00Tcm4TlvDq8ikWAM',  # Rachel voice
        'ELEVENLABS_MODEL_ID': 'eleven_turbo_v2_5',
        'TTS_ENABLED': 'true',
        'TTS_PROVIDER': 'elevenlabs'
    }):
        yield

@pytest.fixture
def mock_voices_response():
    """Mock ElevenLabs API voices response."""
    return {
        "voices": [
            {
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "name": "Rachel",
                "samples": [],
                "category": "premade",
                "fine_tuning": {
                    "model_id": "eleven_turbo_v2_5",
                    "is_allowed_to_fine_tune": True,
                    "finetuning_state": "not_finetuned"
                },
                "labels": {
                    "accent": "american",
                    "description": "calm",
                    "age": "young",
                    "gender": "female",
                    "use_case": "narration"
                },
                "description": "Calm and composed, Rachel's voice is perfect for narration and long-form content.",
                "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/21m00Tcm4TlvDq8ikWAM/df6788f9-5c96-470d-8312-aab3b3d8f50a.mp3",
                "available_for_tiers": [],
                "settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            },
            {
                "voice_id": "AZnzlk1XvdvUeBnXmlld",
                "name": "Domi",
                "samples": [],
                "category": "premade",
                "fine_tuning": {
                    "model_id": "eleven_turbo_v2_5",
                    "is_allowed_to_fine_tune": True,
                    "finetuning_state": "not_finetuned"
                },
                "labels": {
                    "accent": "american",
                    "description": "strong",
                    "age": "young",
                    "gender": "female",
                    "use_case": "narration"
                },
                "description": "Strong and confident, Domi's voice is perfect for commercials and presentations.",
                "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/AZnzlk1XvdvUeBnXmlld/21d01b2c-9b8b-4d7c-9b8b-4d7c9b8b4d7c.mp3",
                "available_for_tiers": [],
                "settings": {
                    "stability": 0.6,
                    "similarity_boost": 0.8
                }
            },
            {
                "voice_id": "EXAVITQu4vr4xnSDxMaL",
                "name": "Bella",
                "samples": [],
                "category": "premade",
                "fine_tuning": {
                    "model_id": "eleven_turbo_v2_5",
                    "is_allowed_to_fine_tune": True,
                    "finetuning_state": "not_finetuned"
                },
                "labels": {
                    "accent": "american",
                    "description": "soft",
                    "age": "young",
                    "gender": "female",
                    "use_case": "audiobook"
                },
                "description": "Soft and gentle, Bella's voice is perfect for audiobooks and meditation content.",
                "preview_url": "https://storage.googleapis.com/eleven-public-prod/premade/voices/EXAVITQu4vr4xnSDxMaL/3e5f2d1a-4b7c-4d5e-9f8a-2b3c4d5e6f7a.mp3",
                "available_for_tiers": [],
                "settings": {
                    "stability": 0.7,
                    "similarity_boost": 0.85
                }
            },
            {
                "voice_id": "custom_voice_123",
                "name": "CustomVoice",
                "samples": [],
                "category": "generated",
                "fine_tuning": {
                    "model_id": "eleven_turbo_v2_5",
                    "is_allowed_to_fine_tune": False,
                    "finetuning_state": "not_finetuned"
                },
                "labels": {
                    "accent": "british",
                    "description": "custom",
                    "age": "middle_aged",
                    "gender": "male",
                    "use_case": "general"
                },
                "description": "A custom generated voice for testing purposes.",
                "preview_url": "https://storage.googleapis.com/eleven-public-prod/generated/voices/custom_voice_123/preview.mp3",
                "available_for_tiers": [],
                "settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
        ]
    }

@pytest.fixture
def mock_audio_response():
    """Mock audio response from ElevenLabs API."""
    # Create a minimal MP3-like binary content for testing
    return b'\xff\xfb\x90\x00' + b'\x00' * 1000  # Simplified MP3 header + data

@pytest.fixture
def mock_requests_success(mock_audio_response):
    """Mock successful requests to ElevenLabs API."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = mock_audio_response
    mock_response.text = "OK"
    return mock_response

@pytest.fixture
def mock_requests_error():
    """Mock error responses from ElevenLabs API."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request: Invalid voice_id"
    return mock_response

@pytest.fixture
def mock_requests_voices_success(mock_voices_response):
    """Mock successful voices list response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_voices_response
    mock_response.text = "OK"
    return mock_response

@pytest.fixture
def mock_pygame():
    """Mock pygame for audio playback testing."""
    with patch('pygame.mixer') as mock_mixer:
        mock_mixer.init = Mock()
        mock_mixer.music.load = Mock()
        mock_mixer.music.play = Mock()
        mock_mixer.music.get_busy = Mock(return_value=False)
        mock_mixer.quit = Mock()
        yield mock_mixer

@pytest.fixture
def mock_tempfile():
    """Mock tempfile for testing audio file handling."""
    with patch('tempfile.NamedTemporaryFile') as mock_temp:
        mock_file = Mock()
        mock_file.name = '/tmp/test_audio.mp3'
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.write = Mock()
        mock_temp.return_value = mock_file
        yield mock_temp

@pytest.fixture
def mock_os_unlink():
    """Mock os.unlink for testing file cleanup."""
    with patch('os.unlink') as mock_unlink:
        yield mock_unlink

@pytest.fixture
def voice_test_cases():
    """Test cases for voice testing."""
    return [
        {
            "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "name": "Rachel",
            "description": "Default voice",
            "expected_success": True
        },
        {
            "voice_id": "AZnzlk1XvdvUeBnXmlld", 
            "name": "Domi",
            "description": "Alternative voice",
            "expected_success": True
        },
        {
            "voice_id": "invalid_voice_id",
            "name": "InvalidVoice",
            "description": "Invalid voice ID",
            "expected_success": False
        },
        {
            "voice_id": "",
            "name": "EmptyVoice",
            "description": "Empty voice ID",
            "expected_success": False
        }
    ]

@pytest.fixture
def voice_settings_test_cases():
    """Test cases for voice settings testing."""
    return [
        {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "expected_success": True
        },
        {
            "stability": 0.0,
            "similarity_boost": 1.0,
            "expected_success": True
        },
        {
            "stability": 1.0,
            "similarity_boost": 0.0,
            "expected_success": True
        },
        {
            "stability": -0.1,
            "similarity_boost": 0.5,
            "expected_success": False
        },
        {
            "stability": 0.5,
            "similarity_boost": 1.1,
            "expected_success": False
        }
    ]

# OpenAI-specific fixtures

@pytest.fixture
def mock_openai_env():
    """Mock OpenAI environment variables for testing."""
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'sk-test_openai_key_123',
        'OPENAI_TTS_VOICE': 'nova',
        'TTS_ENABLED': 'true',
        'TTS_PROVIDER': 'openai'
    }):
        yield

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.stream_to_file = Mock()
    mock_client.audio.speech.create.return_value = mock_response
    return mock_client

@pytest.fixture
def mock_openai_voices():
    """Mock OpenAI voice options."""
    return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

@pytest.fixture
def mock_openai_models():
    """Mock OpenAI model options."""
    return ["tts-1", "tts-1-hd"]

@pytest.fixture
def mock_openai_audio_response():
    """Mock OpenAI audio response."""
    return b'\xff\xfb\x90\x00' + b'\x00' * 2000  # Larger mock MP3 for OpenAI

@pytest.fixture
def mock_openai_error():
    """Mock OpenAI API error response."""
    from openai import APIError
    return APIError("API Error", response=Mock(status_code=400), body=None)

@pytest.fixture
def mock_openai_rate_limit_error():
    """Mock OpenAI rate limit error."""
    from openai import RateLimitError
    return RateLimitError("Rate limit exceeded", response=Mock(status_code=429), body=None)

@pytest.fixture
def mock_openai_timeout_error():
    """Mock OpenAI timeout error."""
    from openai import APITimeoutError
    return APITimeoutError("Request timeout")

# Provider fallback fixtures

@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for provider execution testing."""
    with patch('subprocess.run') as mock_run:
        yield mock_run

@pytest.fixture
def mock_all_providers_env():
    """Mock environment with all providers available."""
    with patch.dict(os.environ, {
        'ELEVENLABS_API_KEY': 'test_elevenlabs_key',
        'OPENAI_API_KEY': 'test_openai_key',
        'TTS_ENABLED': 'true',
        'TTS_PROVIDER': 'auto'
    }):
        yield

@pytest.fixture
def mock_openai_only_env():
    """Mock environment with only OpenAI available."""
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test_openai_key',
        'TTS_ENABLED': 'true',
        'TTS_PROVIDER': 'auto'
    }, clear=True):
        yield

@pytest.fixture
def mock_pyttsx3_only_env():
    """Mock environment with only pyttsx3 available."""
    with patch.dict(os.environ, {
        'TTS_ENABLED': 'true',
        'TTS_PROVIDER': 'auto'
    }, clear=True):
        yield

@pytest.fixture
def mock_provider_scripts_exist():
    """Mock provider scripts existing."""
    with patch('pathlib.Path.exists', return_value=True):
        yield

@pytest.fixture
def mock_provider_scripts_missing():
    """Mock provider scripts missing."""
    with patch('pathlib.Path.exists', return_value=False):
        yield

# Voice parameter fixtures

@pytest.fixture
def voice_parameter_test_cases():
    """Test cases for voice parameter testing."""
    return [
        {
            "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            "expected_success": True
        },
        {
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "voice_settings": {"stability": 0.8, "similarity_boost": 0.9},
            "expected_success": True
        },
        {
            "voice_id": None,
            "voice_settings": None,
            "expected_success": True
        },
        {
            "voice_id": "invalid_voice",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            "expected_success": False
        }
    ]

@pytest.fixture
def openai_voice_test_cases():
    """Test cases for OpenAI voice testing."""
    return [
        {
            "voice": "alloy",
            "model": "tts-1",
            "speed": 1.0,
            "expected_success": True
        },
        {
            "voice": "echo",
            "model": "tts-1-hd",
            "speed": 1.5,
            "expected_success": True
        },
        {
            "voice": "fable",
            "model": "tts-1",
            "speed": 0.5,
            "expected_success": True
        },
        {
            "voice": "invalid_voice",
            "model": "tts-1",
            "speed": 1.0,
            "expected_success": False
        }
    ]

# Performance and quality fixtures

@pytest.fixture
def performance_test_cases():
    """Test cases for performance testing."""
    return [
        {
            "provider": "elevenlabs",
            "expected_latency_ms": 500,
            "quality_score": 0.9
        },
        {
            "provider": "openai",
            "expected_latency_ms": 300,
            "quality_score": 0.85
        },
        {
            "provider": "pyttsx3",
            "expected_latency_ms": 10,
            "quality_score": 0.6
        }
    ]

@pytest.fixture
def quality_test_cases():
    """Test cases for quality testing."""
    return [
        {
            "text": "Hello, world!",
            "expected_quality": "high"
        },
        {
            "text": "This is a longer test message with multiple sentences. It should test the quality of speech synthesis across different providers.",
            "expected_quality": "high"
        },
        {
            "text": "Testing special characters: @#$%^&*()_+",
            "expected_quality": "medium"
        }
    ]

@pytest.fixture(autouse=True)
def _isolated_speech_gate(tmp_path, monkeypatch):
    """Tests never read the real repo registry or write the real speech log."""
    monkeypatch.setenv("SPEAK_REPOS", str(tmp_path / "gate" / "repos.json"))
    monkeypatch.setenv("SPEAK_LOG", str(tmp_path / "gate" / "speech.log"))


@pytest.fixture(autouse=True)
def _isolated_soundbite(tmp_path, monkeypatch):
    """No test can save, level or journal in the real ~/soundbite; tests that need a library set their own."""
    monkeypatch.setenv("SOUNDBITE_DIR", str(tmp_path / "soundbite-default"))
    monkeypatch.setenv("SOUNDBITE_PLAN", str(tmp_path / "soundbite-default" / "level-plan.json"))
