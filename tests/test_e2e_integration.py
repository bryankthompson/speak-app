#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=7.0.0",
#   "pytest-mock>=3.10.0",
#   "requests>=2.28.0",
# ]
# ///

"""
End-to-End Integration Test Suite for the speak app.
Tests complete workflows and multi-component integration scenarios.
"""

import os
import sys
import json
import subprocess
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add the project root to the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import project modules


class TestCompleteUserWorkflows:
    """Test complete user workflows from start to finish."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    @pytest.fixture
    def clean_environment(self):
        """Provide a clean test environment."""
        # Save original environment
        original_env = os.environ.copy()
        
        # Clean test environment
        test_env = {
            key: value for key, value in original_env.items()
            if not key.startswith(('TTS_', 'OPENAI_', 'ELEVENLABS_'))
        }
        
        yield test_env
        
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
    
    def test_first_time_user_workflow(self, speak_script_path, clean_environment):
        """Test complete workflow for first-time user."""
        # Step 1: First run without any configuration
        result = subprocess.run(
            [str(speak_script_path), "--off", "First time user test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=clean_environment
        )
        
        # Should succeed with default provider
        assert result.returncode == 0
        
        # Step 2: Check status
        result = subprocess.run(
            [str(speak_script_path), "--status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_environment
        )
        
        assert result.returncode == 0
        assert "provider" in result.stdout.lower()
        
        # Step 3: Test help
        result = subprocess.run(
            [str(speak_script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_environment
        )
        
        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
    
    def test_provider_configuration_workflow(self, speak_script_path, clean_environment):
        """Test workflow for configuring different providers."""
        providers = ['pyttsx3', 'openai', 'elevenlabs']
        
        for provider in providers:
            # Configure provider
            env = clean_environment.copy()
            env['TTS_PROVIDER'] = provider
            
            # Test basic functionality
            result = subprocess.run(
                [str(speak_script_path), "--off", f"Testing {provider}"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            assert result.returncode == 0
            
            # Verify provider is being used
            result = subprocess.run(
                [str(speak_script_path), "--status"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env
            )
            
            assert result.returncode == 0
            # pyttsx3 might show as "offline" in status
            if provider == 'pyttsx3':
                assert provider in result.stdout.lower() or "offline" in result.stdout.lower()
            else:
                assert provider in result.stdout.lower()
    
    def test_error_recovery_workflow(self, speak_script_path, clean_environment):
        """Test complete error recovery workflow."""
        # Step 1: Test with invalid provider
        env = clean_environment.copy()
        env['TTS_PROVIDER'] = 'invalid_provider'
        
        result = subprocess.run(
            [str(speak_script_path), "--off", "Error recovery test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        # Should still work (fallback to default)
        assert result.returncode == 0
        
        # Step 2: Test with invalid arguments
        result = subprocess.run(
            [str(speak_script_path), "--invalid-flag"],
            capture_output=True,
            text=True,
            timeout=5,
            env=clean_environment
        )
        
        # Should fail gracefully
        assert result.returncode != 0
        assert "usage" in result.stderr.lower() or "usage" in result.stdout.lower()
        
        # Step 3: Test recovery with valid operation
        result = subprocess.run(
            [str(speak_script_path), "--off", "Recovery test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=clean_environment
        )
        
        assert result.returncode == 0
    
    def test_multi_command_workflow(self, speak_script_path, clean_environment):
        """Test workflow using multiple commands in sequence."""
        # Step 1: Use development mode
        speak_dev_path = PROJECT_ROOT / "speak-dev"
        if speak_dev_path.exists():
            result = subprocess.run(
                [str(speak_dev_path), "--off", "Development mode test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=clean_environment
            )
            assert result.returncode == 0
            assert "[DEV MODE]" in result.stderr
        
        # Step 2: Use tracking mode
        speak_tracking_path = PROJECT_ROOT / "speak-with-tracking"
        if speak_tracking_path.exists():
            result = subprocess.run(
                [str(speak_tracking_path), "--off", "Tracking mode test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=clean_environment
            )
            assert result.returncode == 0
        
        # Step 3: Regular speak command
        result = subprocess.run(
            [str(speak_script_path), "--off", "Regular mode test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=clean_environment
        )
        assert result.returncode == 0


class TestProviderIntegration:
    """Test integration with different TTS providers."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_openai_provider_integration(self, speak_script_path):
        """Test complete OpenAI provider integration."""
        # Configure OpenAI provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'openai'
        env['OPENAI_API_KEY'] = 'test-key'
        
        # Test basic functionality with --off flag (no actual API call)
        result = subprocess.run(
            [str(speak_script_path), "--off", "OpenAI integration test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        
        # Test provider selection works
        result = subprocess.run(
            [str(speak_script_path), "--status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        
        assert result.returncode == 0
        assert "openai" in result.stdout.lower()
    
    def test_elevenlabs_provider_integration(self, speak_script_path):
        """Test complete ElevenLabs provider integration."""
        # Configure ElevenLabs provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        env['ELEVENLABS_API_KEY'] = 'test-key'
        
        # Test basic functionality with --off flag (no actual API call)
        result = subprocess.run(
            [str(speak_script_path), "--off", "ElevenLabs integration test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        
        # Test provider selection works
        result = subprocess.run(
            [str(speak_script_path), "--status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        
        assert result.returncode == 0
        assert "elevenlabs" in result.stdout.lower()
    
    def test_pyttsx3_provider_integration(self, speak_script_path):
        """Test complete pyttsx3 provider integration."""
        # Configure pyttsx3 provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        
        # Test basic functionality
        result = subprocess.run(
            [str(speak_script_path), "--off", "pyttsx3 integration test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        
        # pyttsx3 should work offline
        # No API calls should be made
    
    def test_provider_fallback_integration(self, speak_script_path):
        """Test provider fallback mechanism."""
        # Configure primary provider that will fail
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        # Don't set API key to force fallback
        
        # Test that fallback works
        result = subprocess.run(
            [str(speak_script_path), "--off", "Fallback test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        # Should succeed with fallback provider
        assert result.returncode == 0


class TestCostOptimizationIntegration:
    """Test cost optimization workflows and integration."""
    
    @pytest.fixture
    def command_paths(self):
        """Get paths to cost optimization commands."""
        return {
            'speak_dev': PROJECT_ROOT / "speak-dev",
            'speak_with_tracking': PROJECT_ROOT / "speak-with-tracking",
            'set_openai_default': PROJECT_ROOT / "set_openai_default.py"
        }
    
    def test_cost_optimization_workflow(self, command_paths):
        """Test complete cost optimization workflow."""
        if not command_paths['speak_dev'].exists():
            pytest.skip("speak-dev not available")
        
        # Step 1: Use expensive provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'elevenlabs'
        
        # Step 2: Switch to development mode
        result = subprocess.run(
            [str(command_paths['speak_dev']), "--off", "Cost optimization test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        assert "[DEV MODE]" in result.stderr
        assert "save API credits" in result.stderr
        
        # Step 3: Verify cost tracking
        if command_paths['speak_with_tracking'].exists():
            result = subprocess.run(
                [str(command_paths['speak_with_tracking']), "--off", "Tracking test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            assert result.returncode == 0
            # Should show cost information
            assert "chars" in result.stderr
    
    def test_openai_setup_workflow(self, command_paths):
        """Test OpenAI setup workflow."""
        if not command_paths['set_openai_default'].exists():
            pytest.skip("set_openai_default.py not available")
        
        # Test dry run (no actual file modification)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the home directory
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                # Mock user input to cancel
                with patch('builtins.input', return_value='n'):
                    with patch('sys.stdout'):
                        # Import and test the module
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(
                            "set_openai_default", 
                            command_paths['set_openai_default']
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Test the setup function
                        result = module.update_bashrc()
                        assert result is False  # User cancelled


class TestErrorHandlingIntegration:
    """Test error handling across components."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_api_error_handling_workflow(self, speak_script_path):
        """Test API error handling workflow."""
        with patch('requests.post') as mock_post:
            # Mock API failure
            mock_post.side_effect = Exception("API Error")
            
            # Configure provider that will fail
            env = os.environ.copy()
            env['TTS_PROVIDER'] = 'openai'
            env['OPENAI_API_KEY'] = 'test-key'
            
            # Test error handling
            result = subprocess.run(
                [str(speak_script_path), "--off", "API error test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            # Should handle error gracefully (fallback to pyttsx3)
            assert result.returncode == 0
    
    def test_permission_error_handling(self, speak_script_path):
        """Test permission error handling."""
        # Test with read-only environment
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        env['HOME'] = '/tmp'  # Might have permission issues
        
        # Should still work
        result = subprocess.run(
            [str(speak_script_path), "--off", "Permission test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0


class TestPerformanceIntegration:
    """Test performance across integrated workflows."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_end_to_end_performance(self, speak_script_path):
        """Test end-to-end performance workflow."""
        # Configure fast provider
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        
        # Test multiple operations
        start_time = time.time()
        
        for i in range(10):
            result = subprocess.run(
                [str(speak_script_path), "--off", f"Performance test {i}"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env
            )
            assert result.returncode == 0
        
        duration = time.time() - start_time
        
        # Should complete quickly
        assert duration < 10  # Less than 10 seconds for 10 operations
        ops_per_second = 10 / duration
        assert ops_per_second > 1  # At least 1 operation per second
    
class TestConfigurationIntegration:
    """Test configuration management across components."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_environment_configuration_workflow(self, speak_script_path):
        """Test environment-based configuration workflow."""
        # Test different configuration combinations
        configs = [
            {'TTS_PROVIDER': 'pyttsx3'},
            {'TTS_PROVIDER': 'openai', 'OPENAI_TTS_VOICE': 'nova'},
            {'TTS_PROVIDER': 'elevenlabs', 'ELEVENLABS_VOICE_ID': 'test-voice'}
        ]
        
        for config in configs:
            env = os.environ.copy()
            env.update(config)
            
            # Test configuration
            result = subprocess.run(
                [str(speak_script_path), "--off", "Config test"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            
            assert result.returncode == 0
    
    def test_configuration_precedence(self, speak_script_path):
        """Test configuration precedence workflow."""
        # Test that environment variables override defaults
        env = os.environ.copy()
        env['TTS_PROVIDER'] = 'pyttsx3'
        
        # Test with explicit provider
        result = subprocess.run(
            [str(speak_script_path), "--off", "Precedence test"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
        
        # Verify provider is used
        result = subprocess.run(
            [str(speak_script_path), "--status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        
        assert result.returncode == 0
        assert "pyttsx3" in result.stdout.lower() or "offline" in result.stdout.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])