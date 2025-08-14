#!/usr/bin/env python3
"""Simple test verification without pytest dependency."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from eduasr.db import format_time


def test_format_time():
    """Test the format_time utility function."""
    print("Testing format_time function...")
    
    # Test cases
    test_cases = [
        (0, "00:00:00"),
        (61, "00:01:01"),
        (3661, "01:01:01"),
        (3723.5, "01:02:03")
    ]
    
    for seconds, expected in test_cases:
        result = format_time(seconds)
        print(f"  format_time({seconds}) = {result} (expected: {expected})")
        assert result == expected, f"Expected {expected}, got {result}"
    
    print("✅ format_time tests passed!")


def test_db_module_import():
    """Test that db module can be imported."""
    print("Testing database module import...")
    
    try:
        from eduasr.db import TranscriptDB, print_search_results
        print("✅ Database module imports successfully!")
    except ImportError as e:
        print(f"❌ Database module import failed: {e}")
        return False
    
    return True


def test_cli_module_import():
    """Test that CLI module can be imported."""
    print("Testing CLI module import...")
    
    try:
        from eduasr.cli import create_parser, main
        print("✅ CLI module imports successfully!")
    except ImportError as e:
        print(f"❌ CLI module import failed: {e}")
        return False
    
    return True


def test_transcribe_module_import():
    """Test that transcribe module can be imported."""
    print("Testing transcribe module import...")
    
    try:
        from eduasr.transcribe_batch import (
            load_config, get_disk_free_gb, format_time, format_time_vtt
        )
        print("✅ Transcribe module imports successfully!")
    except ImportError as e:
        print(f"❌ Transcribe module import failed: {e}")
        return False
    
    return True


def main():
    """Run all simple tests."""
    print("🧪 Running simple verification tests...")
    print("=" * 50)
    
    tests = [
        test_db_module_import,
        test_cli_module_import, 
        test_transcribe_module_import,
        test_format_time
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test() is not False:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with error: {e}")
            failed += 1
        print()
    
    print("=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All verification tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
