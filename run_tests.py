#!/usr/bin/env python3
"""Test runner script for EDU ASR toolkit."""

import subprocess
import sys
import argparse
from pathlib import Path


def run_tests(test_type="all", verbose=False, coverage=False, markers=None):
    """Run tests with specified options."""
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test path
    cmd.append("tests/")
    
    # Add verbosity
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add coverage
    if coverage:
        cmd.extend(["--cov=eduasr", "--cov-report=html", "--cov-report=term"])
    
    # Add markers for test selection
    if test_type != "all":
        if test_type == "unit":
            cmd.extend(["-m", "not integration and not slow"])
        elif test_type == "integration":
            cmd.extend(["-m", "integration"])
        elif test_type == "fast":
            cmd.extend(["-m", "not slow"])
    
    # Add custom markers
    if markers:
        cmd.extend(["-m", markers])
    
    # Add color output
    cmd.append("--color=yes")
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 50)
    
    return subprocess.run(cmd).returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run EDU ASR tests")
    
    parser.add_argument(
        "--type", 
        choices=["all", "unit", "integration", "fast"],
        default="all",
        help="Type of tests to run"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate coverage report"
    )
    
    parser.add_argument(
        "--markers", "-m",
        help="Custom pytest markers to select tests"
    )
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not Path("tests").exists():
        print("Error: tests directory not found. Run this from the project root.")
        return 1
    
    return run_tests(
        test_type=args.type,
        verbose=args.verbose,
        coverage=args.coverage,
        markers=args.markers
    )


if __name__ == "__main__":
    sys.exit(main())
