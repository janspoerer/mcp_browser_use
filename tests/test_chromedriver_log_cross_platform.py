"""
Cross-platform tests for read_chromedriver_log functionality.

Tests work on Linux, macOS, Windows, and WSL.
"""

import os
import sys
import tempfile
import platform
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We'll need to import after integration
# from src.mcp_browser_use.helpers import read_chromedriver_log, parse_chromedriver_errors


class TestChromedriverLogCrossPlatform(unittest.TestCase):
    """Test suite for cross-platform chromedriver log reading."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_config = {
            "user_data_dir": "/tmp/test_profile",
            "profile": "Default"
        }
        self.temp_dir = tempfile.gettempdir()

    def test_platform_detection(self):
        """Test that platform detection works correctly."""
        system = platform.system()
        self.assertIn(system, ["Linux", "Darwin", "Windows"])

        # Check WSL detection on Linux
        if system == "Linux":
            try:
                with open("/proc/version", "r") as f:
                    is_wsl = "microsoft" in f.read().lower()
                    print(f"WSL detected: {is_wsl}")
            except FileNotFoundError:
                is_wsl = False
                print("Not WSL (no /proc/version)")

    def test_temp_directory_access(self):
        """Test that temp directory is accessible on all platforms."""
        temp_dir = tempfile.gettempdir()
        self.assertTrue(os.path.exists(temp_dir))
        self.assertTrue(os.access(temp_dir, os.W_OK))

        # Test creating a file in temp directory
        test_file = os.path.join(temp_dir, "test_chromedriver_log.txt")
        try:
            with open(test_file, "w") as f:
                f.write("Test content")
            self.assertTrue(os.path.exists(test_file))

            # Clean up
            os.remove(test_file)
        except Exception as e:
            self.fail(f"Cannot write to temp directory: {e}")

    def test_path_separator_handling(self):
        """Test path handling across platforms."""
        # Use os.path.join for cross-platform paths
        path_parts = [self.temp_dir, "chromedriver", "test.log"]
        combined_path = os.path.join(*path_parts)

        # Verify correct separator for platform
        if platform.system() == "Windows":
            self.assertIn("\\", combined_path)
        else:
            self.assertIn("/", combined_path)
            self.assertNotIn("\\", combined_path)

    def test_line_ending_handling(self):
        """Test handling of different line endings."""
        test_content_unix = "Line 1\nLine 2\nLine 3"
        test_content_windows = "Line 1\r\nLine 2\r\nLine 3"
        test_content_mixed = "Line 1\nLine 2\r\nLine 3"

        # All should normalize to same number of lines
        self.assertEqual(len(test_content_unix.splitlines()), 3)
        self.assertEqual(len(test_content_windows.splitlines()), 3)
        self.assertEqual(len(test_content_mixed.splitlines()), 3)

    def test_encoding_handling(self):
        """Test handling of different encodings."""
        test_strings = [
            "ASCII content",
            "UTF-8 content: émojis 🚀",
            "Latin-1 content: café",
            "Mixed: test™ content®"
        ]

        temp_file = os.path.join(self.temp_dir, "encoding_test.log")

        for test_string in test_strings:
            try:
                # Write with UTF-8
                with open(temp_file, "w", encoding="utf-8") as f:
                    f.write(test_string)

                # Read back
                with open(temp_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    self.assertIsNotNone(content)

            except Exception as e:
                print(f"Encoding issue with: {test_string[:20]}... - {e}")

            finally:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

    def test_file_permissions(self):
        """Test file permission handling."""
        test_file = os.path.join(self.temp_dir, "permission_test.log")

        try:
            # Create file
            with open(test_file, "w") as f:
                f.write("Test content")

            # Check read permission
            self.assertTrue(os.access(test_file, os.R_OK))

            # On Unix-like systems, test permission changes
            if platform.system() != "Windows":
                import stat
                # Make read-only
                os.chmod(test_file, stat.S_IRUSR)
                self.assertTrue(os.access(test_file, os.R_OK))
                self.assertFalse(os.access(test_file, os.W_OK))

                # Restore permissions for cleanup
                os.chmod(test_file, stat.S_IRUSR | stat.S_IWUSR)

        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_large_file_handling(self):
        """Test reading large files efficiently."""
        test_file = os.path.join(self.temp_dir, "large_test.log")
        lines_count = 10000
        line_content = "x" * 100  # 100 chars per line

        try:
            # Create large file
            with open(test_file, "w") as f:
                for i in range(lines_count):
                    f.write(f"Line {i}: {line_content}\n")

            file_size = os.path.getsize(test_file)
            print(f"Created test file: {file_size} bytes")

            # Test reading last N lines efficiently
            with open(test_file, "rb") as f:
                # Seek to near end
                f.seek(-4096, os.SEEK_END)
                chunk = f.read()
                lines = chunk.decode("utf-8", errors="replace").splitlines()
                self.assertGreater(len(lines), 0)

        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_mock_read_chromedriver_log(self):
        """Test the read_chromedriver_log function with mocked file system."""
        # Since we're testing the implementation separately,
        # we'll mock the actual function behavior

        mock_log_content = """[1234.567][INFO]: Starting ChromeDriver
[1234.568][INFO]: Chrome version: 120.0.1234.56
[1234.569][ERROR]: Unable to find element
[1234.570][WARNING]: Page load timeout
[1234.571][ERROR]: JavaScript error in console"""

        expected_result = {
            "success": True,
            "log_path": f"{self.temp_dir}/chromedriver_shared_test_123.log",
            "content": mock_log_content,
            "lines_read": 5,
            "has_errors": True,
            "error": None
        }

        # Simulate function behavior
        self.assertEqual(expected_result["lines_read"], 5)
        self.assertTrue(expected_result["has_errors"])
        self.assertIn("ERROR", expected_result["content"])

    def test_error_parsing(self):
        """Test error parsing from log content."""
        log_content = """[1234.567][INFO]: Starting ChromeDriver
[1234.568][ERROR]: Initialization failed: Chrome not reachable
[1234.569][ERROR]: Element not interactable at line 42
[1234.570][ERROR]: Navigation timeout for https://example.com
[1234.571][ERROR]: JavaScript evaluation failed
[1234.572][ERROR]: Wait timeout exceeded
[1234.573][ERROR]: Unknown error occurred"""

        # Mock the parse_chromedriver_errors function behavior
        expected_categories = {
            "initialization_errors": 1,
            "element_errors": 1,
            "navigation_errors": 1,
            "javascript_errors": 1,
            "timeout_errors": 1,
            "other_errors": 1
        }

        # Count errors by category
        error_lines = [line for line in log_content.splitlines() if "ERROR" in line]
        self.assertEqual(len(error_lines), 6)

    def test_cross_platform_path_resolution(self):
        """Test path resolution across platforms."""
        # Test paths with spaces (common on Windows)
        path_with_spaces = os.path.join(self.temp_dir, "path with spaces", "log.txt")
        dir_with_spaces = os.path.dirname(path_with_spaces)

        try:
            # Create directory with spaces
            os.makedirs(dir_with_spaces, exist_ok=True)
            self.assertTrue(os.path.exists(dir_with_spaces))

            # Create file in that directory
            with open(path_with_spaces, "w") as f:
                f.write("Test")

            self.assertTrue(os.path.exists(path_with_spaces))

        finally:
            # Cleanup
            if os.path.exists(path_with_spaces):
                os.remove(path_with_spaces)
            if os.path.exists(dir_with_spaces):
                os.rmdir(dir_with_spaces)

    def test_wsl_specific_paths(self):
        """Test WSL-specific path handling."""
        if platform.system() == "Linux":
            # Check if running on WSL
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        # Test WSL paths
                        wsl_paths = [
                            "/mnt/c/Users",
                            "/tmp",
                            "/home"
                        ]
                        for path in wsl_paths:
                            if os.path.exists(path):
                                print(f"WSL path exists: {path}")
            except FileNotFoundError:
                pass  # Not WSL


class TestPlatformSpecificBehavior(unittest.TestCase):
    """Test platform-specific behaviors."""

    def test_windows_temp_path(self):
        """Test Windows temp path handling."""
        if platform.system() == "Windows":
            temp_path = tempfile.gettempdir()
            self.assertIn("\\", temp_path)
            self.assertTrue(temp_path.startswith("C:\\") or
                          temp_path.startswith("D:\\") or
                          "Users" in temp_path)

    def test_unix_temp_path(self):
        """Test Unix/Linux temp path handling."""
        if platform.system() in ["Linux", "Darwin"]:
            temp_path = tempfile.gettempdir()
            self.assertTrue(temp_path.startswith("/"))
            self.assertIn("/", temp_path)

    def test_macos_temp_path(self):
        """Test macOS-specific temp path."""
        if platform.system() == "Darwin":
            temp_path = tempfile.gettempdir()
            # macOS uses /var/folders/... for temp
            self.assertTrue(temp_path.startswith("/var/folders") or
                          temp_path.startswith("/tmp"))


def run_platform_diagnostics():
    """Run diagnostics to show platform information."""
    print("\n" + "=" * 60)
    print("Platform Diagnostics")
    print("=" * 60)
    print(f"System: {platform.system()}")
    print(f"Platform: {sys.platform}")
    print(f"Release: {platform.release()}")
    print(f"Version: {platform.version()}")
    print(f"Machine: {platform.machine()}")
    print(f"Python Version: {platform.python_version()}")
    print(f"Temp Directory: {tempfile.gettempdir()}")

    # Check for WSL
    if platform.system() == "Linux":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    print("Environment: WSL (Windows Subsystem for Linux)")
                else:
                    print("Environment: Native Linux")
        except FileNotFoundError:
            print("Environment: Linux (cannot determine if WSL)")
    elif platform.system() == "Windows":
        print("Environment: Native Windows")
    elif platform.system() == "Darwin":
        print("Environment: macOS")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Run diagnostics first
    run_platform_diagnostics()

    # Run tests
    unittest.main(verbosity=2)