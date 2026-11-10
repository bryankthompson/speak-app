#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest>=7.0.0",
#   "pytest-mock>=3.10.0",
#   "psutil>=5.9.0",
# ]
# ///

"""
Comprehensive test suite for CLI Script Pipe Integration Stress Testing.
Tests pipe input handling, high-volume operations, concurrent usage, and error recovery.
"""

import os
import sys
import subprocess
import tempfile
import time
import threading
import queue
import signal
import psutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest

# Add the project root to the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))



def _keyless_env(home):
    """Environment for a real `speak` run that cannot reach a paid provider: no keys in the environment, and a
    HOME with no brainpods/.env (the provider scripts reload keys from there) and no soundbite library.
    uv's cache and Python folders stay where they were so the run does not download anything."""
    real_home = Path.home()
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        env.pop(key, None)
    env.setdefault("UV_CACHE_DIR", str(real_home / ".cache" / "uv"))
    env.setdefault("UV_PYTHON_INSTALL_DIR", str(real_home / ".local" / "share" / "uv" / "python"))
    env["HOME"] = str(home)
    # openai_tts.py asks the 1Password `op` CLI for a key when the environment has none: put a failing stub first on PATH
    stub_dir = Path(home) / "stub-bin"
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / "op"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


class TestBasicPipeIntegration:
    """Test basic pipe input handling."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_simple_pipe_input(self, speak_script_path):
        """Test simple pipe input handling."""
        result = subprocess.run(
            f"echo 'Test message' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        # Should not output error messages
        assert "error" not in result.stderr.lower()
    
    def test_multiple_line_pipe_input(self, speak_script_path):
        """Test multiple line pipe input."""
        multi_line = "Line 1\nLine 2\nLine 3"
        result = subprocess.run(
            f"echo '{multi_line}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_empty_pipe_input(self, speak_script_path):
        """Test empty pipe input handling."""
        result = subprocess.run(
            f"echo '' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should handle empty input gracefully
        assert result.returncode == 0
    
    def test_pipe_input_with_unicode(self, speak_script_path):
        """Test pipe input with unicode characters."""
        unicode_text = "Hello 世界 🌍 émojis"
        result = subprocess.run(
            f"echo '{unicode_text}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_input_with_special_chars(self, speak_script_path):
        """Test pipe input with special characters."""
        # Use printf to handle special characters properly
        result = subprocess.run(
            f'printf "%s" "Special chars: !@#$%%^&*()_+{{}}|:<>?[]\\\\;\\",./" | {speak_script_path} --off',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_input_with_provider_selection(self, speak_script_path):
        """Test pipe input with provider selection."""
        result = subprocess.run(
            f"echo 'Test message' | {speak_script_path} --provider pyttsx3 --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_input_from_file(self, speak_script_path):
        """Test pipe input from file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("File content line 1\nFile content line 2\n")
            temp_file = f.name
        
        try:
            result = subprocess.run(
                f"cat {temp_file} | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            assert result.returncode == 0
        finally:
            os.unlink(temp_file)
    
    def test_pipe_input_with_large_content(self, speak_script_path):
        """Test pipe input with large content."""
        # Create 10KB of text
        large_text = "Large content test. " * 500  # ~10KB
        
        result = subprocess.run(
            f"echo '{large_text}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        assert result.returncode == 0


class TestHighVolumePipeOperations:
    """Test high-volume pipe operations."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_rapid_pipe_operations(self, speak_script_path):
        """Test rapid successive pipe operations."""
        results = []
        
        # Execute 50 rapid pipe operations
        for i in range(50):
            result = subprocess.run(
                f"echo 'Message {i}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            results.append(result.returncode)
        
        # All operations should succeed
        assert all(rc == 0 for rc in results)
    
    def test_bulk_pipe_processing(self, speak_script_path):
        """Test bulk pipe processing with large input."""
        # Create 100 lines of input
        lines = [f"Bulk message {i}" for i in range(100)]
        bulk_input = '\n'.join(lines)
        
        result = subprocess.run(
            f"echo '{bulk_input}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
    
    def test_memory_usage_during_large_pipe(self, speak_script_path):
        """Test memory usage during large pipe operations."""
        # Create smaller but still large input to avoid argument size limits
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Write 1MB of data
            for _ in range(50000):
                f.write("Memory test content. ")
            temp_file = f.name
        
        try:
            # Monitor memory usage
            initial_memory = psutil.Process().memory_info().rss
            
            result = subprocess.run(
                f"cat {temp_file} | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            final_memory = psutil.Process().memory_info().rss
            memory_increase = final_memory - initial_memory
            
            assert result.returncode == 0
            # Memory increase should be reasonable (less than 100MB)
            assert memory_increase < 100 * 1024 * 1024
        finally:
            os.unlink(temp_file)
    
    def test_continuous_pipe_stream(self, speak_script_path):
        """Test continuous pipe stream processing."""
        # Create a continuous stream of data
        script = f"""
        for i in {{1..20}}; do
            echo "Stream message $i"
            sleep 0.1
        done | {speak_script_path} --off
        """
        
        result = subprocess.run(
            script,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_different_sizes(self, speak_script_path):
        """Test pipe operations with different input sizes."""
        sizes = [10, 100, 1000, 10000]  # Different message sizes
        
        for size in sizes:
            message = "x" * size
            result = subprocess.run(
                f"echo '{message}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            assert result.returncode == 0, f"Failed with size {size}"


class TestConcurrentPipeUsage:
    """Test concurrent pipe usage scenarios."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_concurrent_pipe_operations(self, speak_script_path):
        """Test concurrent pipe operations."""
        def pipe_operation(message_id):
            result = subprocess.run(
                f"echo 'Concurrent message {message_id}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode
        
        # Run 10 concurrent operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(pipe_operation, i) for i in range(10)]
            results = [future.result() for future in as_completed(futures)]
        
        # All operations should succeed
        assert all(rc == 0 for rc in results)
    
    def test_concurrent_different_providers(self, speak_script_path):
        """Test concurrent operations with different providers."""
        def pipe_with_provider(provider):
            result = subprocess.run(
                f"echo 'Provider test {provider}' | {speak_script_path} --provider {provider} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode
        
        # Test concurrent operations with different providers
        providers = ['pyttsx3', 'auto', 'pyttsx3']  # Use only available providers
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(pipe_with_provider, provider) for provider in providers]
            results = [future.result() for future in as_completed(futures)]
        
        # All operations should succeed
        assert all(rc == 0 for rc in results)
    
    def test_resource_contention_handling(self, speak_script_path):
        """Test handling of resource contention during concurrent operations."""
        def heavy_pipe_operation(operation_id):
            # Create moderately large input
            large_input = f"Heavy operation {operation_id}: " + "data " * 1000
            
            result = subprocess.run(
                f"echo '{large_input}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=15
            )
            return result.returncode
        
        # Run 5 concurrent heavy operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(heavy_pipe_operation, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]
        
        # All operations should succeed
        assert all(rc == 0 for rc in results)
    
    def test_concurrent_pipe_stress_test(self, speak_script_path):
        """Test concurrent pipe stress scenario."""
        success_count = 0
        error_count = 0
        
        def stress_operation(op_id):
            nonlocal success_count, error_count
            try:
                result = subprocess.run(
                    f"echo 'Stress test {op_id}' | {speak_script_path} --off",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    success_count += 1
                else:
                    error_count += 1
            except subprocess.TimeoutExpired:
                error_count += 1
            except Exception:
                error_count += 1
        
        # Run 20 concurrent stress operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(stress_operation, i) for i in range(20)]
            for future in as_completed(futures):
                future.result()
        
        # At least 80% should succeed
        success_rate = success_count / (success_count + error_count)
        assert success_rate >= 0.8


class TestCommandChainingScenarios:
    """Test command chaining scenarios."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_success_chaining(self, speak_script_path):
        """Test successful command chaining."""
        result = subprocess.run(
            f"echo 'Success test' | {speak_script_path} --off && echo 'Chain success'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "Chain success" in result.stdout
    
    def test_failure_chaining(self, speak_script_path):
        """Test command chaining with failure handling."""
        result = subprocess.run(
            f"echo 'Test message' | {speak_script_path} --off || echo 'Chain failure'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        # Should not show failure message since speak should succeed
        assert "Chain failure" not in result.stdout
    
    def test_build_notification_pattern(self, speak_script_path):
        """Test common build notification pattern."""
        # Simulate successful build
        result = subprocess.run(
            f"echo 'Build complete' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        
        # Simulate failed build
        result = subprocess.run(
            f"false && echo 'Build failed' | {speak_script_path} --off || echo 'Build failed' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_test_completion_pattern(self, speak_script_path):
        """Test common test completion pattern."""
        # Simulate test success
        result = subprocess.run(
            f"true && echo 'All tests passed' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        
        # Simulate test failure
        result = subprocess.run(
            f"false || echo 'Tests failed' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_deployment_notification_pattern(self, speak_script_path):
        """Test deployment notification pattern."""
        script = f"""
        if true; then
            echo 'Deployment successful' | {speak_script_path} --off
        else
            echo 'Deployment failed' | {speak_script_path} --off
        fi
        """
        
        result = subprocess.run(
            script,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_complex_chaining_scenario(self, speak_script_path):
        """Test complex command chaining scenario."""
        script = f"""
        echo 'Starting process' | {speak_script_path} --off &&
        sleep 0.1 &&
        echo 'Process running' | {speak_script_path} --off &&
        echo 'Process complete' | {speak_script_path} --off
        """
        
        result = subprocess.run(
            script,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        assert result.returncode == 0


class TestErrorRecoveryInPipeScenarios:
    """Test error recovery in pipe scenarios."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_pipe_input_with_invalid_provider(self, speak_script_path, tmp_path):
        """Test pipe input with invalid provider."""
        result = subprocess.run(
            f"echo 'Test message' | {speak_script_path} --provider invalid_provider",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=_keyless_env(tmp_path)
        )
        
        # Should handle invalid provider gracefully
        assert result.returncode != 0 or "error" in result.stderr.lower()
    
    def test_pipe_input_with_missing_api_key(self, speak_script_path, tmp_path):
        """Test pipe input when API keys are missing (also from ~/brainpods/.env, which speak reloads)."""
        env = _keyless_env(tmp_path)

        result = subprocess.run(
            f"echo 'Test message' | {speak_script_path} --provider openai",
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
            env=env
        )
        
        # Should handle gracefully (might fall back to pyttsx3)
        assert result.returncode in [0, 1]  # Either success or expected failure
    
    def test_pipe_input_with_network_issues(self, speak_script_path):
        """Test pipe input behavior during network issues."""
        # Force offline mode
        result = subprocess.run(
            f"echo 'Network test' | {speak_script_path} --provider pyttsx3 --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should work with offline provider
        assert result.returncode == 0
    
    def test_pipe_input_with_corrupted_input(self, speak_script_path):
        """Test pipe input with corrupted/invalid input."""
        # Test with binary data
        result = subprocess.run(
            f"echo -e '\\x00\\x01\\x02\\x03' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should handle gracefully
        assert result.returncode == 0
    
    def test_pipe_input_timeout_handling(self, speak_script_path):
        """Test pipe input timeout handling."""
        # Use file approach to avoid argument size limits
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Write 1MB of data
            f.write("x" * 1000000)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                f"cat {temp_file} | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Should either succeed or fail gracefully
            assert result.returncode in [0, 1]
        finally:
            os.unlink(temp_file)
    
    def test_pipe_input_interrupted_process(self, speak_script_path):
        """Test pipe input when process is interrupted."""
        # Start a process that can be interrupted
        process = subprocess.Popen(
            f"echo 'Interrupt test' | {speak_script_path} --off",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Let it run briefly then terminate
        time.sleep(0.1)
        process.terminate()
        
        # Wait for termination
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        
        # Should handle interruption gracefully
        assert process.returncode in [0, -15, 1]  # Success, SIGTERM, or error
    
    def test_pipe_input_with_system_resource_limits(self, speak_script_path):
        """Test pipe input under system resource constraints."""
        # Create multiple processes to stress system
        processes = []
        
        try:
            for i in range(5):
                process = subprocess.Popen(
                    f"echo 'Resource test {i}' | {speak_script_path} --off",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                processes.append(process)
            
            # Wait for all processes
            results = []
            for process in processes:
                process.wait(timeout=10)
                results.append(process.returncode)
            
            # At least some should succeed
            success_count = sum(1 for rc in results if rc == 0)
            assert success_count >= len(processes) // 2
            
        except Exception:
            # Clean up processes
            for process in processes:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except:
                    try:
                        process.kill()
                        process.wait()
                    except:
                        pass
            raise


class TestPerformanceUnderStress:
    """Test performance under stress conditions."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_pipe_response_time_consistency(self, speak_script_path):
        """Test that pipe response times are consistent."""
        response_times = []
        
        for i in range(10):
            start_time = time.time()
            
            result = subprocess.run(
                f"echo 'Response time test {i}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            end_time = time.time()
            response_times.append(end_time - start_time)
            
            assert result.returncode == 0
        
        # Response times should be reasonably consistent
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        
        # Max time should not be more than 3x average
        assert max_time <= avg_time * 3
    
    def test_pipe_throughput_measurement(self, speak_script_path):
        """Test pipe throughput under load."""
        messages_per_second = []
        
        for batch in range(3):
            start_time = time.time()
            
            # Process 20 messages
            for i in range(20):
                result = subprocess.run(
                    f"echo 'Throughput test {batch}-{i}' | {speak_script_path} --off",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                assert result.returncode == 0
            
            end_time = time.time()
            elapsed = end_time - start_time
            throughput = 20 / elapsed
            messages_per_second.append(throughput)
        
        # Average throughput should be reasonable
        avg_throughput = sum(messages_per_second) / len(messages_per_second)
        assert avg_throughput >= 5  # At least 5 messages per second
    
    def test_memory_leak_detection(self, speak_script_path):
        """Test for memory leaks during repeated pipe operations."""
        initial_memory = psutil.Process().memory_info().rss
        
        # Run 100 pipe operations
        for i in range(100):
            result = subprocess.run(
                f"echo 'Memory test {i}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            assert result.returncode == 0
        
        final_memory = psutil.Process().memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be minimal (less than 50MB)
        assert memory_increase < 50 * 1024 * 1024
    
    def test_cpu_usage_during_pipe_operations(self, speak_script_path):
        """Test CPU usage during pipe operations."""
        # Monitor CPU usage
        cpu_percent_before = psutil.cpu_percent(interval=1)
        
        # Run several pipe operations
        for i in range(10):
            result = subprocess.run(
                f"echo 'CPU test {i}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            assert result.returncode == 0
        
        cpu_percent_after = psutil.cpu_percent(interval=1)
        
        # CPU usage should not spike dramatically
        cpu_increase = cpu_percent_after - cpu_percent_before
        assert cpu_increase < 50  # Less than 50% increase
    
    def test_disk_io_efficiency(self, speak_script_path):
        """Test disk I/O efficiency during pipe operations."""
        # Get initial disk I/O stats
        disk_io_before = psutil.disk_io_counters()
        
        # Run pipe operations
        for i in range(20):
            result = subprocess.run(
                f"echo 'Disk IO test {i}' | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            assert result.returncode == 0
        
        # Get final disk I/O stats
        disk_io_after = psutil.disk_io_counters()
        
        # Disk I/O should be reasonable
        read_bytes = disk_io_after.read_bytes - disk_io_before.read_bytes
        write_bytes = disk_io_after.write_bytes - disk_io_before.write_bytes
        
        # Should not exceed 10MB of I/O
        assert read_bytes < 10 * 1024 * 1024
        assert write_bytes < 10 * 1024 * 1024


class TestPipeIntegrationEdgeCases:
    """Test edge cases for pipe integration."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_pipe_with_null_bytes(self, speak_script_path):
        """Test pipe input with null bytes."""
        result = subprocess.run(
            f"printf 'Test\\x00message' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should handle null bytes gracefully
        assert result.returncode == 0
    
    def test_pipe_with_very_long_single_line(self, speak_script_path):
        """Test pipe with very long single line."""
        # Create 100KB single line
        long_line = "x" * 100000
        
        result = subprocess.run(
            f"echo '{long_line}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_many_short_lines(self, speak_script_path):
        """Test pipe with many short lines."""
        # Create 1000 short lines
        lines = '\n'.join([f"Line {i}" for i in range(1000)])
        
        result = subprocess.run(
            f"echo '{lines}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_mixed_encodings(self, speak_script_path):
        """Test pipe with mixed character encodings."""
        # Mix of ASCII, UTF-8, and special chars
        mixed_text = "ASCII text, UTF-8: café, émojis: 🎉, symbols: ∑∞"
        
        result = subprocess.run(
            f"echo '{mixed_text}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_control_characters(self, speak_script_path):
        """Test pipe with control characters."""
        # Include various control characters
        control_text = "Test\t\n\r\f\v\b\a"
        
        result = subprocess.run(
            f"echo '{control_text}' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_environment_variables(self, speak_script_path):
        """Test pipe with environment variables in input."""
        # Set test environment variable
        env = os.environ.copy()
        env['TEST_VAR'] = 'test_value'
        
        result = subprocess.run(
            f"echo 'Environment test: $TEST_VAR' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=env
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_shell_metacharacters(self, speak_script_path):
        """Test pipe with shell metacharacters."""
        # Use printf to properly escape shell metacharacters
        result = subprocess.run(
            f'printf "%s" "Test with | & ; ( ) < > $ \\` \\\\ \\"" | {speak_script_path} --off',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
    
    def test_pipe_stdin_closure(self, speak_script_path):
        """Test pipe behavior when stdin is closed."""
        # Test with closed stdin
        result = subprocess.run(
            f"echo 'Stdin test' | {speak_script_path} --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL
        )
        
        assert result.returncode == 0
    
    def test_pipe_with_binary_input(self, speak_script_path):
        """Test pipe with binary input."""
        # Create binary data
        binary_data = bytes(range(256))
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(binary_data)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                f"cat {temp_file} | {speak_script_path} --off",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Should handle binary input gracefully
            assert result.returncode == 0
        finally:
            os.unlink(temp_file)


class TestPipeIntegrationFailureRecovery:
    """Test failure recovery scenarios for pipe integration."""
    
    @pytest.fixture
    def speak_script_path(self):
        """Get the path to the speak script."""
        return PROJECT_ROOT / "speak"
    
    def test_pipe_recovery_after_provider_failure(self, speak_script_path):
        """Test recovery after provider failure."""
        # First, try with a provider that might fail
        result1 = subprocess.run(
            f"echo 'Provider test' | {speak_script_path} --provider openai --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Then try with a reliable provider
        result2 = subprocess.run(
            f"echo 'Fallback test' | {speak_script_path} --provider pyttsx3 --off",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # At least the fallback should work
        assert result2.returncode == 0
    
    def test_pipe_graceful_degradation(self, speak_script_path):
        """Test graceful degradation under adverse conditions."""
        # Create adverse conditions by using many processes
        processes = []
        
        try:
            # Start multiple processes
            for i in range(10):
                process = subprocess.Popen(
                    f"echo 'Degradation test {i}' | {speak_script_path} --off",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                processes.append(process)
            
            # Wait for all processes
            success_count = 0
            for process in processes:
                process.wait(timeout=15)
                if process.returncode == 0:
                    success_count += 1
            
            # At least half should succeed
            assert success_count >= len(processes) // 2
            
        finally:
            # Clean up any remaining processes
            for process in processes:
                try:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=1)
                except:
                    try:
                        process.kill()
                        process.wait()
                    except:
                        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])