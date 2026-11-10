"""The conftest fixture hides the paid-provider keys from tests (so none can bill OpenAI or ElevenLabs unasked)."""
import os

import pytest

LIVE_API_KEYS = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY")  # same names as the fixture in conftest.py


def test_paid_provider_keys_are_hidden_from_tests():
    if os.environ.get("SPEAK_LIVE_API") == "1":
        pytest.skip("SPEAK_LIVE_API=1: live tests are allowed to see the keys")
    assert [k for k in LIVE_API_KEYS if k in os.environ] == []
