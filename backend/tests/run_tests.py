#!/usr/bin/env python3
"""
Test runner script for backend API tests
"""
import sys
import subprocess
import argparse
import os
from pathlib import Path

def run_tests(test_pattern=None, verbose=False, coverage=False, parallel=False):
    """Run tests with specified options"""
    
    # Change to backend directory
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test directory
    cmd.append("tests/")
    
    # Add pattern if specified
    if test_pattern:
        cmd.append(f"-k {test_pattern}")
    
    # Add verbose flag
    if verbose:
        cmd.append("-v")
    
    # Add parallel execution
    if parallel:
        cmd.extend(["-n", "auto"])
    
    # Add coverage if requested
    if coverage:
        cmd.extend([
            "--cov=.",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-exclude=tests/*",
            "--cov-exclude=venv/*"
        ])
    
    # Add other useful options
    cmd.extend([
        "--tb=short",  # Shorter traceback format
        "--strict-markers",  # Strict marker checking
        "--disable-warnings",  # Disable warnings for cleaner output
    ])
    
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 50)
    
    # Run tests
    result = subprocess.run(cmd)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="Run backend API tests")
    parser.add_argument(
        "-k", "--pattern",
        help="Test pattern to match (e.g., 'test_auth' or 'test_login')"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Run with coverage report"
    )
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available tests"
    )
    
    args = parser.parse_args()
    
    if args.list:
        # List all tests
        cmd = ["python", "-m", "pytest", "tests/", "--collect-only", "-q"]
        subprocess.run(cmd)
        return 0
    
    # Run tests
    return run_tests(
        test_pattern=args.pattern,
        verbose=args.verbose,
        coverage=args.coverage,
        parallel=args.parallel
    )

if __name__ == "__main__":
    sys.exit(main())

