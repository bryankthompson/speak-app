#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=7.0.0",
#   "pytest-mock>=3.10.0",
# ]
# ///

"""
Regression Test Suite for Script Invocation Method
Tests for bug where speak script used python3 instead of direct execution,
preventing shebang from being honored and breaking uv dependency management.
"""

import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

# Add the project root to the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestScriptInvocationRegression:
    """Regression tests for the script invocation bug fix."""

    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"

    @pytest.fixture
    def tts_scripts(self):
        """Get paths to all TTS provider scripts."""
        tts_dir = PROJECT_ROOT / "tts"
        return {
            "tts_provider": tts_dir / "tts_provider.py",
            "openai_tts": tts_dir / "openai_tts.py",
            "elevenlabs_tts": tts_dir / "elevenlabs_tts.py",
            "pyttsx3_tts": tts_dir / "pyttsx3_tts.py"
        }

    def test_tts_scripts_have_uv_shebang(self, tts_scripts):
        """
        Regression test: Verify all TTS provider scripts use uv shebang.

        This test prevents the bug where scripts are executed with python3 directly,
        bypassing the uv dependency management system.
        """
        expected_shebang = "#!/usr/bin/env -S uv run"

        for script_name, script_path in tts_scripts.items():
            if script_path.exists():
                with open(script_path, 'r') as f:
                    first_line = f.readline().strip()

                assert first_line.startswith(expected_shebang), \
                    f"{script_name} missing uv shebang. Found: {first_line[:50]}..."

                # Verify script is executable
                assert os.access(script_path, os.X_OK), \
                    f"{script_name} is not executable"

    def test_tts_provider_direct_execution(self, tts_scripts):
        """
        Regression test: Verify tts_provider.py can be executed directly.

        If the script is executed with python3 directly, dependencies won't load.
        Direct execution uses the shebang, which invokes uv for dependency management.
        """
        script_path = tts_scripts["tts_provider"]

        # Execute the script directly (not via python3)
        result = subprocess.run(
            [str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )

        # Should succeed if shebang is working
        # Would fail with ModuleNotFoundError if python3 is used directly
        assert result.returncode == 0, \
            f"Direct execution failed: {result.stderr}"

    def test_openai_dependency_loads_via_shebang(self, tts_scripts):
        """
        Regression test: Verify OpenAI dependency loads when script is executed.

        The bug caused ModuleNotFoundError for openai because python3 bypassed
        the uv dependency management in the shebang.
        """
        script_path = tts_scripts["tts_provider"]

        # Set up environment to use OpenAI provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        env['OPENAI_API_KEY'] = 'test-key-for-dependency-check'

        # Execute with a test message to trigger provider initialization
        # This requires the openai module to be loaded via uv
        result = subprocess.run(
            [str(script_path), "test message"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )

        # Should not fail with ModuleNotFoundError
        assert "ModuleNotFoundError: No module named 'openai'" not in result.stderr, \
            "OpenAI dependency not loaded - shebang may not be honored"

        # May fail with API error (expected), but not import error
        # The key is that the openai module loads successfully

    def test_speak_script_invokes_provider_correctly(self, speak_script_path):
        """
        Regression test: Verify speak script doesn't use python3 to invoke providers.

        This test checks the speak script content to ensure it uses direct execution.
        """
        with open(speak_script_path, 'r') as f:
            content = f.read()

        # Check that TTS_PROVIDER_SCRIPT is invoked directly, not via python3
        # Look for incorrect patterns like: python3 "$TTS_PROVIDER_SCRIPT"
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith('#'):
                continue

            # Check for problematic patterns
            if 'TTS_PROVIDER_SCRIPT' in line and 'python3' in line:
                # Allow python3 in comments or fallback code
                if 'python3 -c' in line or 'python3' in line and '#' in line:
                    continue

                # Check if it's the problematic pattern
                if 'python3 "$TTS_PROVIDER_SCRIPT"' in line or \
                   'python3 "${TTS_PROVIDER_SCRIPT}"' in line:
                    pytest.fail(
                        f"Line {i}: speak script uses 'python3' to invoke provider script. "
                        f"Should use direct execution to honor shebang.\n"
                        f"Found: {line.strip()}"
                    )

    def test_speak_list_command_works(self, speak_script_path):
        """
        Regression test: Verify speak --list works with dependency loading.

        This command triggers provider initialization and would fail if
        dependencies aren't loaded correctly.
        """
        result = subprocess.run(
            [str(speak_script_path), "--list"],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should not fail with ModuleNotFoundError
        assert "ModuleNotFoundError" not in result.stderr, \
            f"Dependency loading failed: {result.stderr}"

        # Should succeed
        assert result.returncode == 0, \
            f"speak --list failed: {result.stderr}"

        # Should show provider information
        assert "provider" in result.stdout.lower() or "available" in result.stdout.lower(), \
            "Provider list not shown in output"

    def test_speak_status_loads_providers(self, speak_script_path):
        """
        Regression test: Verify speak --status loads provider information.

        Status command requires provider initialization, testing dependency loading.
        """
        result = subprocess.run(
            [str(speak_script_path), "--status"],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Should not fail with dependency errors
        assert "ModuleNotFoundError" not in result.stderr
        assert "ImportError" not in result.stderr

        # Should succeed
        assert result.returncode == 0

    @pytest.mark.integration
    def test_end_to_end_with_pyttsx3(self, speak_script_path):
        """
        Integration test: Verify complete workflow with offline provider.

        Uses pyttsx3 to test without requiring API keys, verifying that
        dependencies load correctly in a real execution scenario.
        """
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        env['TTS_ENABLED'] = 'true'

        # Execute a complete workflow
        result = subprocess.run(
            [str(speak_script_path), "Integration test message"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )

        # Should not fail with dependency errors
        assert "ModuleNotFoundError" not in result.stderr
        assert "ImportError" not in result.stderr

        # Should succeed (pyttsx3 always available)
        assert result.returncode == 0, \
            f"Integration test failed: {result.stderr}"


class TestScriptExecutability:
    """Test that all scripts are properly executable."""

    @pytest.fixture
    def all_scripts(self):
        """Get paths to all executable scripts."""
        return [
            PROJECT_ROOT / "speak",
            PROJECT_ROOT / "speak-dev",
            PROJECT_ROOT / "speak-with-tracking",
            PROJECT_ROOT / "tts" / "tts_provider.py",
            PROJECT_ROOT / "tts" / "openai_tts.py",
            PROJECT_ROOT / "tts" / "elevenlabs_tts.py",
            PROJECT_ROOT / "tts" / "pyttsx3_tts.py"
        ]

    def test_all_scripts_are_executable(self, all_scripts):
        """Verify all scripts have executable permissions."""
        for script_path in all_scripts:
            if script_path.exists():
                assert os.access(script_path, os.X_OK), \
                    f"{script_path.name} is not executable"

    def test_python_scripts_have_shebang(self, all_scripts):
        """Verify all Python scripts have proper shebang lines."""
        for script_path in all_scripts:
            if script_path.exists() and script_path.suffix == '.py':
                with open(script_path, 'r') as f:
                    first_line = f.readline().strip()

                assert first_line.startswith('#!'), \
                    f"{script_path.name} missing shebang"

                # For Python scripts in tts directory, should use uv
                if 'tts' in str(script_path):
                    assert 'uv run' in first_line or 'python' in first_line, \
                        f"{script_path.name} has invalid shebang: {first_line}"


class TestDependencyIsolation:
    """Test that dependencies are properly isolated and loaded."""

    @pytest.fixture
    def clean_python_env(self):
        """Create a clean environment without global Python packages."""
        env = os.environ.copy()
        # Remove Python path variables to ensure uv handles dependencies
        env.pop('PYTHONPATH', None)
        return env

    def test_openai_tts_loads_dependencies(self, clean_python_env):
        """
        Test that openai_tts.py loads its own dependencies via uv.

        This verifies the shebang works even without global packages.
        """
        script_path = PROJECT_ROOT / "tts" / "openai_tts.py"

        # Try to execute with --help (shouldn't require API key)
        result = subprocess.run(
            [str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_python_env
        )

        # Should not fail with ModuleNotFoundError
        # Note: Script might not have --help, but should not fail on import
        assert "ModuleNotFoundError: No module named 'openai'" not in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
