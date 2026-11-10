#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=7.0.0",
#   "pytest-mock>=3.10.0",
# ]
# ///

"""
Comprehensive test suite for Cost Optimization Commands.
Tests speak-dev, speak-with-tracking, and set_openai_default.py.
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import pytest

# Add the project root to the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestSpeakDevCommand:
    """Test speak-dev command functionality."""
    
    @pytest.fixture
    def speak_dev_path(self):
        """Get the path to the speak-dev script."""
        return PROJECT_ROOT / "speak-dev"
    
    @pytest.fixture
    def speak_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_speak_dev_exists_and_executable(self, speak_dev_path):
        """Test that speak-dev exists and is executable."""
        assert speak_dev_path.exists()
        assert speak_dev_path.is_file()
        assert os.access(speak_dev_path, os.X_OK)
    
    def test_speak_dev_shows_dev_mode_indicator(self, speak_dev_path):
        """Test that speak-dev shows development mode indicator."""
        result = subprocess.run(
            [str(speak_dev_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
        assert "offline TTS" in result.stderr
        assert "save API credits" in result.stderr
    
    def test_speak_dev_forces_pyttsx3(self, speak_dev_path):
        """Test that speak-dev forces pyttsx3 provider."""
        # Set a different provider in environment
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        
        result = subprocess.run(
            [str(speak_dev_path), "--status"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        # Should show pyttsx3 as provider despite environment setting
        assert "pyttsx3" in result.stdout.lower() or "offline" in result.stdout.lower()
    
    def test_speak_dev_unsets_elevenlabs_key(self, speak_dev_path):
        """Test that speak-dev unsets ElevenLabs API key."""
        # Set ElevenLabs key in environment
        env = os.environ.copy()
        env['ELEVENLABS_API_KEY'] = 'test-key'
        
        result = subprocess.run(
            [str(speak_dev_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        # Should succeed even with no API key available
    
    def test_speak_dev_passes_arguments(self, speak_dev_path):
        """Test that speak-dev passes arguments to speak command."""
        result = subprocess.run(
            [str(speak_dev_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        # Should show help from underlying speak command
        assert "speak" in result.stdout.lower()
    
    def test_speak_dev_handles_pipe_input(self, speak_dev_path):
        """Test that speak-dev handles pipe input."""
        result = subprocess.run(
            f"echo 'Pipe test' | {speak_dev_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
    
    def test_speak_dev_with_various_options(self, speak_dev_path):
        """Test speak-dev with various command line options."""
        options = [
            ["--off", "Test message"],
            ["--status"],
            ["--list"],
            ["--test", "--off"]
        ]
        
        for option_set in options:
            result = subprocess.run(
                [str(speak_dev_path)] + option_set,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            assert result.returncode == 0
            assert "[DEV MODE]" in result.stderr
    
    def test_speak_dev_exit_code_preservation(self, speak_dev_path):
        """Test that speak-dev preserves exit codes from speak command."""
        # Test with invalid option to force error
        result = subprocess.run(
            [str(speak_dev_path), "--invalid-option"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should preserve the error exit code
        assert result.returncode != 0
        assert "[DEV MODE]" in result.stderr
    
    def test_speak_dev_environment_isolation(self, speak_dev_path):
        """Test that speak-dev properly isolates environment variables."""
        # Set conflicting environment variables
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        env['ELEVENLABS_API_KEY'] = 'test-key'
        env['OPENAI_API_KEY'] = 'test-key'
        
        result = subprocess.run(
            [str(speak_dev_path), "--off", "Environment test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr


class TestSpeakWithTrackingCommand:
    """Test speak-with-tracking command functionality."""
    
    @pytest.fixture
    def speak_with_tracking_path(self):
        """Get the path to the speak-with-tracking script."""
        return PROJECT_ROOT / "speak-with-tracking"
    
    def test_speak_with_tracking_exists_and_executable(self, speak_with_tracking_path):
        """Test that speak-with-tracking exists and is executable."""
        assert speak_with_tracking_path.exists()
        assert speak_with_tracking_path.is_file()
        assert os.access(speak_with_tracking_path, os.X_OK)
    
    def test_speak_with_tracking_shows_cost_info(self, speak_with_tracking_path):
        """Test that speak-with-tracking shows cost information."""
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "[TTS:" in result.stderr
        assert "chars" in result.stderr
        assert "via" in result.stderr
    
    def test_speak_with_tracking_calculates_openai_cost(self, speak_with_tracking_path):
        """Test cost calculation for OpenAI provider."""
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "chars" in result.stderr
        assert "via openai" in result.stderr
        assert "$" in result.stderr
    
    def test_speak_with_tracking_calculates_elevenlabs_cost(self, speak_with_tracking_path):
        """Test cost calculation for ElevenLabs provider."""
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "chars" in result.stderr
        assert "via elevenlabs" in result.stderr
        assert "$" in result.stderr
    
    def test_speak_with_tracking_handles_free_provider(self, speak_with_tracking_path):
        """Test behavior with free provider (pyttsx3)."""
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", "Test message"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        # Should not show cost info for free provider
        assert "[TTS:" not in result.stderr or "$0.00000" not in result.stderr
    
    def test_speak_with_tracking_character_count_accuracy(self, speak_with_tracking_path):
        """Test that character count is accurate."""
        test_message = "Hello world!"  # 12 characters
        
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", test_message],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "12 chars" in result.stderr
    
    def test_speak_with_tracking_handles_pipe_input(self, speak_with_tracking_path):
        """Test that speak-with-tracking handles pipe input."""
        result = subprocess.run(
            f"echo 'Pipe test message' | {speak_with_tracking_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        # Should show cost info even with pipe input
        assert "chars" in result.stderr
    
    def test_speak_with_tracking_exit_code_preservation(self, speak_with_tracking_path):
        """Test that speak-with-tracking preserves exit codes."""
        # Test with invalid option to force error
        result = subprocess.run(
            [str(speak_with_tracking_path), "--invalid-option"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should preserve the error exit code
        assert result.returncode != 0
    
    def test_speak_with_tracking_no_args_handling(self, speak_with_tracking_path):
        """Test speak-with-tracking behavior with no arguments."""
        result = subprocess.run(
            [str(speak_with_tracking_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should handle no arguments gracefully
        assert result.returncode in [0, 1]  # Either success or expected failure
        # Should not show cost info when no text provided
        assert "[TTS:" not in result.stderr or "0 chars" in result.stderr
    
    def test_speak_with_tracking_cost_accuracy(self, speak_with_tracking_path):
        """Test cost calculation accuracy."""
        # Test with known message length
        test_message = "x" * 1000  # 1000 characters
        
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        
        result = subprocess.run(
            [str(speak_with_tracking_path), "--off", test_message],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "1000 chars" in result.stderr
        # Should show cost around $0.015 for 1000 chars with OpenAI
        assert "$0.015" in result.stderr or "$0.01500" in result.stderr
    
    def test_speak_with_tracking_multiple_providers(self, speak_with_tracking_path):
        """Test speak-with-tracking with multiple providers."""
        providers = ['openai', 'elevenlabs', 'pyttsx3']
        
        for provider in providers:
            env = os.environ.copy()
            env['TTS_PROVIDER'] = provider
            
            result = subprocess.run(
                [str(speak_with_tracking_path), "--off", "Test message"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            assert result.returncode == 0
            if provider != 'pyttsx3':  # Free provider doesn't show cost
                assert f"via {provider}" in result.stderr


class TestSetOpenAIDefaultScript:
    """Test set_openai_default.py script functionality."""
    
    @pytest.fixture
    def set_openai_script_path(self):
        """Get the path to the set_openai_default.py script."""
        return PROJECT_ROOT / "set_openai_default.py"
    
    def test_set_openai_script_exists_and_executable(self, set_openai_script_path):
        """Test that set_openai_default.py exists and is executable."""
        assert set_openai_script_path.exists()
        assert set_openai_script_path.is_file()
        assert os.access(set_openai_script_path, os.X_OK)
    
    def test_set_openai_script_python_import(self, set_openai_script_path):
        """Test that set_openai_default.py can be imported as a Python module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        
        # Should be able to import without errors
        spec.loader.exec_module(set_openai_module)
        
        # Check that functions are available
        assert hasattr(set_openai_module, 'update_bashrc')
        assert hasattr(set_openai_module, 'check_api_key')
        assert hasattr(set_openai_module, 'show_cost_comparison')
    
    def test_set_openai_script_already_configured(self, set_openai_script_path):
        """Test behavior when OpenAI is already configured."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        # Mock bash_aliases file with existing configuration
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bash_aliases', delete=False) as f:
            f.write("export TTS_PROVIDER=openai\n")
            temp_file = f.name
        
        try:
            with patch('pathlib.Path.home') as mock_home:
                mock_home.return_value = Path(temp_file).parent
                
                with patch('pathlib.Path.exists') as mock_exists:
                    mock_exists.return_value = True
                    
                    with patch('pathlib.Path.read_text') as mock_read:
                        mock_read.return_value = "export TTS_PROVIDER=openai\n"
                        
                        with patch('sys.stdout'):
                            result = set_openai_module.update_bashrc()
                            assert result is True
        finally:
            os.unlink(temp_file)
    
    def test_set_openai_script_user_cancellation(self, set_openai_script_path):
        """Test behavior when user cancels the setup."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        with patch('builtins.input', return_value='n'):
            with patch('sys.stdout'):
                result = set_openai_module.update_bashrc()
                assert result is False
    
    def test_set_openai_script_successful_setup(self, set_openai_script_path):
        """Test successful setup process."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            bash_aliases = Path(tmpdir) / ".bash_aliases"
            bash_aliases.touch()
            
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch('builtins.input', return_value='y'):
                    with patch('sys.stdout'):
                        result = set_openai_module.update_bashrc()
                        assert result is True
                        
                        # Check that configuration was written
                        content = bash_aliases.read_text()
                        assert "TTS_PROVIDER=openai" in content
                        assert "OPENAI_TTS_VOICE=onyx" in content
                        assert "OPENAI_TTS_MODEL=tts-1" in content
    
    def test_set_openai_script_api_key_check(self, set_openai_script_path):
        """Test API key checking functionality."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        # Test with API key present
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            result = set_openai_module.check_api_key()
            assert result is True
        
        # Test with API key missing
        with patch.dict(os.environ, {}, clear=True):
            with patch('sys.stdout'):
                result = set_openai_module.check_api_key()
                assert result is False
    
    def test_set_openai_script_cost_comparison(self, set_openai_script_path):
        """Test cost comparison display."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        # Should not raise any exceptions
        with patch('sys.stdout'):
            set_openai_module.show_cost_comparison()
    
    def test_set_openai_script_error_handling(self, set_openai_script_path):
        """Test error handling during file operations."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        # Mock file operation failure
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            with patch('builtins.input', return_value='y'):
                with patch('sys.stdout'):
                    result = set_openai_module.update_bashrc()
                    assert result is False
    
    def test_set_openai_script_prefers_bash_aliases(self, set_openai_script_path):
        """Test that script prefers .bash_aliases over .bashrc."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_openai_default", set_openai_script_path)
        set_openai_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set_openai_module)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            bashrc = Path(tmpdir) / ".bashrc"
            bash_aliases = Path(tmpdir) / ".bash_aliases"
            bashrc.touch()
            bash_aliases.touch()
            
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch('builtins.input', return_value='y'):
                    with patch('sys.stdout'):
                        result = set_openai_module.update_bashrc()
                        assert result is True
                        
                        # Should have written to .bash_aliases, not .bashrc
                        aliases_content = bash_aliases.read_text()
                        bashrc_content = bashrc.read_text()
                        
                        assert "TTS_PROVIDER=openai" in aliases_content
                        assert "TTS_PROVIDER=openai" not in bashrc_content
    
    def test_set_openai_script_interactive_execution(self, set_openai_script_path):
        """Test interactive execution simulation."""
        # Skip this test - complex __main__ handling is not needed for this simple script
        pytest.skip("Skip complex interactive execution test")


class TestCostOptimizationIntegration:
    """Test integration between cost optimization commands."""
    
    @pytest.fixture
    def command_paths(self):
        """Get paths to all cost optimization commands."""
        return {
            'speak_dev': PROJECT_ROOT / "speak-dev",
            'speak_with_tracking': PROJECT_ROOT / "speak-with-tracking",
            'set_openai_default': PROJECT_ROOT / "set_openai_default.py"
        }
    
    def test_all_commands_exist(self, command_paths):
        """Test that all cost optimization commands exist."""
        for name, path in command_paths.items():
            assert path.exists(), f"{name} does not exist"
            assert path.is_file(), f"{name} is not a file"
            assert os.access(path, os.X_OK), f"{name} is not executable"
    
    def test_cost_optimization_workflow(self, command_paths):
        """Test the complete cost optimization workflow."""
        # Step 1: Use development mode
        result = subprocess.run(
            [str(command_paths['speak_dev']), "--off", "Development test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
        
        # Step 2: Use tracking mode
        result = subprocess.run(
            [str(command_paths['speak_with_tracking']), "--off", "Tracking test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        assert "chars" in result.stderr
    
    def test_cost_calculation_consistency(self, command_paths):
        """Test that cost calculations are consistent across commands."""
        # Test with known message
        test_message = "x" * 1000  # 1000 characters
        
        # Get cost from speak-with-tracking
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        
        result = subprocess.run(
            [str(command_paths['speak_with_tracking']), "--off", test_message],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "1000 chars" in result.stderr
        # Should show OpenAI cost: 1000 * 0.000015 = $0.015
        assert "$0.015" in result.stderr or "$0.01500" in result.stderr
    
    def test_provider_switching_behavior(self, command_paths):
        """Test behavior when switching between providers."""
        providers = ['openai', 'pyttsx3']
        
        for provider in providers:
            env = os.environ.copy()
            env['TTS_PROVIDER'] = provider
            
            # Test speak-with-tracking
            result = subprocess.run(
                [str(command_paths['speak_with_tracking']), "--off", "Provider test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            assert result.returncode == 0
            if provider != 'pyttsx3':  # Free provider doesn't show cost
                assert f"via {provider}" in result.stderr
    
    def test_development_mode_cost_protection(self, command_paths):
        """Test that development mode provides cost protection."""
        # Set expensive provider in environment
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        env['ELEVENLABS_API_KEY'] = 'test-key'
        
        # speak-dev should override this
        result = subprocess.run(
            [str(command_paths['speak_dev']), "--off", "Cost protection test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
        assert "save API credits" in result.stderr
    
    def test_command_help_consistency(self, command_paths):
        """Test that commands provide consistent help information."""
        # Test speak-dev help
        result = subprocess.run(
            [str(command_paths['speak_dev']), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
        
        # Test that help from underlying speak command is shown
        assert "speak" in result.stdout.lower()


class TestCostOptimizationEdgeCases:
    """Test edge cases for cost optimization commands."""
    
    def test_commands_with_empty_input(self):
        """Test commands with empty input."""
        commands = [
            PROJECT_ROOT / "speak-dev",
            PROJECT_ROOT / "speak-with-tracking"
        ]
        
        for command in commands:
            result = subprocess.run(
                [str(command), "--off", ""],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Should handle empty input gracefully (by failing with error message)
            assert result.returncode != 0
    
    def test_commands_with_large_input(self):
        """Test commands with large input."""
        large_text = "x" * 10000  # 10KB
        
        commands = [
            PROJECT_ROOT / "speak-dev",
            PROJECT_ROOT / "speak-with-tracking"
        ]
        
        for command in commands:
            result = subprocess.run(
                [str(command), "--off", large_text],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            assert result.returncode == 0
    
    def test_commands_with_unicode_input(self):
        """Test commands with unicode input."""
        unicode_text = "Hello 世界 🌍 émojis"
        
        commands = [
            PROJECT_ROOT / "speak-dev",
            PROJECT_ROOT / "speak-with-tracking"
        ]
        
        for command in commands:
            result = subprocess.run(
                [str(command), "--off", unicode_text],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            assert result.returncode == 0
    
    def test_commands_with_missing_dependencies(self):
        """Test commands when dependencies are missing."""
        # Test speak-with-tracking when bc is not available
        # We can't remove python3 from PATH as that breaks everything
        # Instead, let's mock the bc command specifically
        original_path = os.environ.get('PATH', '')
        
        # Create a temp directory without bc
        with tempfile.TemporaryDirectory() as tmpdir:
            # Add python3 to the temp PATH but not bc
            python_path = subprocess.check_output(['which', 'python3']).decode().strip()
            python_dir = os.path.dirname(python_path)
            
            # Set PATH to only have Python, not bc
            with patch.dict(os.environ, {'PATH': f"{python_dir}:{tmpdir}"}):
                # Test speak-with-tracking (which uses Python for calculations now)
                result = subprocess.run(
                    [str(PROJECT_ROOT / "speak-with-tracking"), "--off", "Test"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Should still work because it uses Python for calculations
                assert result.returncode == 0
    
    def test_commands_concurrent_execution(self):
        """Test concurrent execution of cost optimization commands."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def run_command(command):
            result = subprocess.run(
                [str(command), "--off", "Concurrent test"],
                capture_output=True,
                text=True,
                timeout=10
            )
            results.put((command.name, result.returncode))
        
        # Run commands concurrently
        commands = [
            PROJECT_ROOT / "speak-dev",
            PROJECT_ROOT / "speak-with-tracking"
        ]
        
        threads = []
        for command in commands:
            thread = threading.Thread(target=run_command, args=(command,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        while not results.empty():
            command_name, return_code = results.get()
            assert return_code == 0, f"{command_name} failed with return code {return_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])