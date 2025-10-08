#!/usr/bin/env python3
"""
Comprehensive test runner for the Actor Mesh E-commerce Support Agent.

This script orchestrates the execution of all unit tests, integration tests,
and system validation checks. It provides detailed reporting, performance
metrics, and coverage analysis.
"""

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestRunner:
    """Main test runner class."""

    def __init__(self, verbose: bool = False, coverage: bool = False):
        """Initialize the test runner."""
        self.verbose = verbose
        self.coverage = coverage
        self.project_root = project_root
        self.test_dir = self.project_root / "tests"

        # Test categories and their paths
        self.test_categories = {
            "unit": self.test_dir / "unit",
            "integration": self.test_dir / "integration",
        }

        # Test results tracking
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "duration": 0.0,
            "coverage": None,
        }

        self.detailed_results = {}

    def print_banner(self, title: str, char: str = "=", width: int = 80):
        """Print a formatted banner."""
        print(f"\n{char * width}")
        print(f"{title:^{width}}")
        print(f"{char * width}")

    def print_section(self, title: str, char: str = "-", width: int = 60):
        """Print a section header."""
        print(f"\n{char * width}")
        print(f" {title}")
        print(f"{char * width}")

    def check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        self.print_section("Checking Dependencies")

        required_packages = [
            "pytest",
            "pytest-asyncio",
            "pytest-cov" if self.coverage else None,
        ]

        missing_packages = []

        for package in required_packages:
            if package is None:
                continue

            try:
                __import__(package.replace("-", "_"))
                print(f"✓ {package} is available")
            except ImportError:
                missing_packages.append(package)
                print(f"✗ {package} is missing")

        if missing_packages:
            print(f"\nMissing packages: {', '.join(missing_packages)}")
            print("Please install them with: pip install " + " ".join(missing_packages))
            return False

        print("\n✓ All dependencies are available")
        return True

    def check_project_structure(self) -> bool:
        """Check if project structure is correct."""
        self.print_section("Checking Project Structure")

        required_paths = [
            self.project_root / "models",
            self.project_root / "actors",
            self.project_root / "storage",
            self.project_root / "mock_services",
            self.test_dir,
            self.test_dir / "unit",
            self.test_dir / "integration",
        ]

        missing_paths = []

        for path in required_paths:
            if path.exists():
                print(f"✓ {path.relative_to(self.project_root)}")
            else:
                missing_paths.append(path)
                print(f"✗ {path.relative_to(self.project_root)}")

        if missing_paths:
            print(f"\nMissing paths: {[str(p.relative_to(self.project_root)) for p in missing_paths]}")
            return False

        print("\n✓ Project structure is correct")
        return True

    def run_pytest_command(self, test_path: Path, additional_args: List[str] = None) -> Tuple[int, str, Dict]:
        """Run pytest command and capture results."""
        cmd = [sys.executable, "-m", "pytest"]

        # Add test path
        cmd.append(str(test_path))

        # Add verbose flag
        if self.verbose:
            cmd.extend(["-v", "-s"])
        else:
            cmd.append("-q")

        # Add coverage if requested
        if self.coverage:
            cmd.extend(
                [
                    "--cov=actors",
                    "--cov=models",
                    "--cov=storage",
                    "--cov=mock_services",
                    "--cov-report=term-missing",
                    "--cov-report=json",
                ]
            )

        # Add any additional arguments
        if additional_args:
            cmd.extend(additional_args)

        # Add JSON reporting for detailed results
        cmd.extend(["--tb=short", "--json-report", "--json-report-file=/tmp/pytest_report.json"])

        if self.verbose:
            print(f"Running command: {' '.join(cmd)}")

        # Run the command
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300,  # 5 minute timeout
            )
            duration = time.time() - start_time

            # Try to load JSON report for detailed results
            detailed_results = {}
            try:
                import json

                with open("/tmp/pytest_report.json", "r") as f:
                    detailed_results = json.load(f)
            except Exception:
                pass

            return result.returncode, result.stdout + result.stderr, detailed_results

        except subprocess.TimeoutExpired:
            return -1, "Test execution timed out after 5 minutes", {}
        except Exception as e:
            return -1, f"Error running tests: {e}", {}

    def parse_pytest_output(self, output: str, detailed_results: Dict) -> Dict:
        """Parse pytest output to extract test statistics."""
        stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0, "duration": 0.0}

        # Try to get stats from JSON report first
        if detailed_results and "summary" in detailed_results:
            summary = detailed_results["summary"]
            stats["total"] = summary.get("total", 0)
            stats["passed"] = summary.get("passed", 0)
            stats["failed"] = summary.get("failed", 0)
            stats["skipped"] = summary.get("skipped", 0)
            stats["errors"] = summary.get("error", 0)
            stats["duration"] = detailed_results.get("duration", 0.0)
            return stats

        # Fallback to parsing text output
        lines = output.split("\n")
        for line in lines:
            line = line.strip()

            # Look for summary line
            if "passed" in line or "failed" in line or "error" in line:
                # Parse patterns like "10 passed, 2 failed, 1 skipped in 5.23s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        count = int(part)
                        if i + 1 < len(parts):
                            status = parts[i + 1].rstrip(",")
                            if status in stats:
                                stats[status] = count
                            elif status == "passed":
                                stats["passed"] = count
                            elif status == "failed":
                                stats["failed"] = count
                            elif status == "skipped":
                                stats["skipped"] = count
                            elif status == "error" or status == "errors":
                                stats["errors"] = count
                    elif "in" in part and i + 1 < len(parts) and "s" in parts[i + 1]:
                        try:
                            duration_str = parts[i + 1].rstrip("s")
                            stats["duration"] = float(duration_str)
                        except ValueError:
                            pass

        stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"] + stats["errors"]
        return stats

    def run_unit_tests(self) -> bool:
        """Run all unit tests."""
        self.print_section("Running Unit Tests")

        unit_test_dir = self.test_categories["unit"]
        if not unit_test_dir.exists():
            print("✗ Unit test directory not found")
            return False

        # Find all test files
        test_files = list(unit_test_dir.glob("test_*.py"))
        if not test_files:
            print("✗ No unit test files found")
            return False

        print(f"Found {len(test_files)} unit test files:")
        for test_file in test_files:
            print(f"  - {test_file.name}")

        # Run unit tests
        return_code, output, detailed = self.run_pytest_command(unit_test_dir)

        if self.verbose:
            print("\nUnit Test Output:")
            print(output)

        # Parse results
        stats = self.parse_pytest_output(output, detailed)
        self.detailed_results["unit"] = {"stats": stats, "output": output, "return_code": return_code}

        # Update overall results
        self.results["total_tests"] += stats["total"]
        self.results["passed"] += stats["passed"]
        self.results["failed"] += stats["failed"]
        self.results["skipped"] += stats["skipped"]
        self.results["errors"] += stats["errors"]
        self.results["duration"] += stats["duration"]

        # Print summary
        print("\nUnit Test Results:")
        print(f"  Total: {stats['total']}")
        print(f"  Passed: {stats['passed']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Duration: {stats['duration']:.2f}s")

        success = return_code == 0 and stats["failed"] == 0 and stats["errors"] == 0
        print(f"  Status: {'✓ PASSED' if success else '✗ FAILED'}")

        return success

    def run_integration_tests(self) -> bool:
        """Run integration tests if they exist."""
        self.print_section("Running Integration Tests")

        integration_test_dir = self.test_categories["integration"]
        if not integration_test_dir.exists():
            print("! Integration test directory not found - skipping")
            return True

        # Find integration test files
        test_files = list(integration_test_dir.glob("test_*.py"))
        if not test_files:
            print("! No integration test files found - skipping")
            return True

        print(f"Found {len(test_files)} integration test files:")
        for test_file in test_files:
            print(f"  - {test_file.name}")

        # Run integration tests
        return_code, output, detailed = self.run_pytest_command(integration_test_dir)

        if self.verbose:
            print("\nIntegration Test Output:")
            print(output)

        # Parse results
        stats = self.parse_pytest_output(output, detailed)
        self.detailed_results["integration"] = {"stats": stats, "output": output, "return_code": return_code}

        # Update overall results
        self.results["total_tests"] += stats["total"]
        self.results["passed"] += stats["passed"]
        self.results["failed"] += stats["failed"]
        self.results["skipped"] += stats["skipped"]
        self.results["errors"] += stats["errors"]
        self.results["duration"] += stats["duration"]

        # Print summary
        print("\nIntegration Test Results:")
        print(f"  Total: {stats['total']}")
        print(f"  Passed: {stats['passed']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Duration: {stats['duration']:.2f}s")

        success = return_code == 0 and stats["failed"] == 0 and stats["errors"] == 0
        print(f"  Status: {'✓ PASSED' if success else '✗ FAILED'}")

        return success

    def run_system_validation(self) -> bool:
        """Run system validation checks."""
        self.print_section("Running System Validation")

        # Check if the original basic flow test still works
        basic_test_file = self.project_root / "test_basic_flow.py"
        if not basic_test_file.exists():
            print("! Basic flow test not found - skipping system validation")
            return True

        print("Running basic flow validation...")

        # Run the basic flow test
        cmd = [sys.executable, str(basic_test_file)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=60,  # 1 minute timeout
            )

            if result.returncode == 0:
                print("✓ Basic flow validation PASSED")
                if self.verbose:
                    print("Output:", result.stdout[-500:])  # Last 500 chars
                return True
            else:
                print("✗ Basic flow validation FAILED")
                print("Error output:", result.stderr[-500:])  # Last 500 chars
                return False

        except subprocess.TimeoutExpired:
            print("✗ Basic flow validation TIMED OUT")
            return False
        except Exception as e:
            print(f"✗ Basic flow validation ERROR: {e}")
            return False

    def check_code_quality(self) -> bool:
        """Run code quality checks if tools are available."""
        self.print_section("Code Quality Checks")

        # Check if code formatting tools are available
        tools_to_check = [
            ("black", "Code formatting"),
            ("flake8", "Linting"),
            ("mypy", "Type checking"),
        ]

        available_tools = []
        for tool, description in tools_to_check:
            try:
                result = subprocess.run([tool, "--version"], capture_output=True, timeout=10)
                if result.returncode == 0:
                    available_tools.append((tool, description))
                    print(f"✓ {description} ({tool}) is available")
                else:
                    print(f"! {description} ({tool}) is not available")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                print(f"! {description} ({tool}) is not available")

        if not available_tools:
            print("! No code quality tools available - skipping")
            return True

        # Run available tools on key directories
        target_dirs = ["actors", "models", "storage", "mock_services"]
        all_passed = True

        for tool, description in available_tools:
            print(f"\nRunning {description}...")

            for target_dir in target_dirs:
                dir_path = self.project_root / target_dir
                if not dir_path.exists():
                    continue

                try:
                    if tool == "black":
                        cmd = [tool, "--check", "--diff", str(dir_path)]
                    elif tool == "flake8":
                        cmd = [tool, str(dir_path)]
                    elif tool == "mypy":
                        cmd = [tool, str(dir_path)]
                    else:
                        continue

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                    if result.returncode == 0:
                        print(f"  ✓ {target_dir}")
                    else:
                        print(f"  ✗ {target_dir}")
                        if self.verbose and result.stdout:
                            print(f"    Output: {result.stdout[:200]}")
                        all_passed = False

                except subprocess.TimeoutExpired:
                    print(f"  ! {target_dir} (timeout)")
                    all_passed = False
                except Exception as e:
                    print(f"  ! {target_dir} (error: {e})")
                    all_passed = False

        return all_passed

    def generate_coverage_report(self) -> Optional[Dict]:
        """Generate coverage report if coverage was enabled."""
        if not self.coverage:
            return None

        self.print_section("Coverage Report")

        # Check if coverage.json exists
        coverage_file = self.project_root / "coverage.json"
        if not coverage_file.exists():
            print("! Coverage data not found")
            return None

        try:
            import json

            with open(coverage_file, "r") as f:
                coverage_data = json.load(f)

            # Extract summary
            summary = coverage_data.get("totals", {})
            coverage_percent = summary.get("percent_covered", 0)

            print(f"Overall Coverage: {coverage_percent:.1f}%")
            print(f"Lines Covered: {summary.get('covered_lines', 0)}")
            print(f"Lines Missing: {summary.get('missing_lines', 0)}")
            print(f"Total Lines: {summary.get('num_statements', 0)}")

            # Show per-file coverage for main modules
            files = coverage_data.get("files", {})
            print("\nPer-Module Coverage:")

            for file_path, file_data in files.items():
                if any(module in file_path for module in ["actors/", "models/", "storage/", "mock_services/"]):
                    module_name = Path(file_path).stem
                    file_percent = file_data.get("summary", {}).get("percent_covered", 0)
                    print(f"  {module_name}: {file_percent:.1f}%")

            self.results["coverage"] = coverage_data
            return coverage_data

        except Exception as e:
            print(f"! Error reading coverage data: {e}")
            return None

    def print_final_summary(self):
        """Print final test summary."""
        self.print_banner("Test Summary")

        # Overall results
        print(f"Total Tests Run: {self.results['total_tests']}")
        print(f"Passed: {self.results['passed']}")
        print(f"Failed: {self.results['failed']}")
        print(f"Skipped: {self.results['skipped']}")
        print(f"Errors: {self.results['errors']}")
        print(f"Total Duration: {self.results['duration']:.2f}s")

        if self.results["coverage"]:
            coverage_percent = self.results["coverage"].get("totals", {}).get("percent_covered", 0)
            print(f"Coverage: {coverage_percent:.1f}%")

        # Success rate
        if self.results["total_tests"] > 0:
            success_rate = (self.results["passed"] / self.results["total_tests"]) * 100
            print(f"Success Rate: {success_rate:.1f}%")

        # Overall status
        overall_success = (
            self.results["failed"] == 0 and self.results["errors"] == 0 and self.results["total_tests"] > 0
        )

        print(f"\nOverall Status: {'✓ ALL TESTS PASSED' if overall_success else '✗ SOME TESTS FAILED'}")

        # Detailed breakdown by category
        if self.verbose and self.detailed_results:
            print("\nDetailed Results by Category:")
            for category, details in self.detailed_results.items():
                stats = details["stats"]
                status = (
                    "PASSED"
                    if details["return_code"] == 0 and stats["failed"] == 0 and stats["errors"] == 0
                    else "FAILED"
                )
                print(f"  {category.upper()}: {status} ({stats['passed']}/{stats['total']} passed)")

    def save_results(self, output_file: Optional[str] = None):
        """Save test results to file."""
        if not output_file:
            return

        try:
            import json

            output_data = {
                "timestamp": time.time(),
                "summary": self.results,
                "detailed_results": self.detailed_results,
                "project_root": str(self.project_root),
                "test_categories": {k: str(v) for k, v in self.test_categories.items()},
            }

            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2)

            print(f"\n📊 Test results saved to: {output_file}")

        except Exception as e:
            print(f"! Error saving results: {e}")

    async def run_all_tests(self, skip_quality: bool = False, output_file: Optional[str] = None) -> bool:
        """Run all tests and checks."""
        start_time = time.time()

        self.print_banner("Actor Mesh E-commerce Support Agent - Test Suite")

        # Pre-flight checks
        if not self.check_dependencies():
            return False

        if not self.check_project_structure():
            return False

        # Run tests
        unit_success = self.run_unit_tests()
        integration_success = self.run_integration_tests()
        system_success = self.run_system_validation()

        # Code quality checks (optional)
        quality_success = True
        if not skip_quality:
            quality_success = self.check_code_quality()

        # Coverage report
        self.generate_coverage_report()

        # Final summary
        total_duration = time.time() - start_time
        self.results["duration"] = total_duration

        self.print_final_summary()

        # Save results if requested
        if output_file:
            self.save_results(output_file)

        # Return overall success
        return unit_success and integration_success and system_success and quality_success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive test runner for Actor Mesh E-commerce Support Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

    parser.add_argument("-c", "--coverage", action="store_true", help="Enable code coverage reporting")

    parser.add_argument("--skip-quality", action="store_true", help="Skip code quality checks")

    parser.add_argument("-o", "--output", type=str, help="Save detailed results to JSON file")

    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")

    parser.add_argument("--integration-only", action="store_true", help="Run only integration tests")

    args = parser.parse_args()

    # Create test runner
    runner = TestRunner(verbose=args.verbose, coverage=args.coverage)

    try:
        if args.unit_only:
            # Run only unit tests
            runner.print_banner("Unit Tests Only")
            success = runner.check_dependencies() and runner.check_project_structure() and runner.run_unit_tests()
        elif args.integration_only:
            # Run only integration tests
            runner.print_banner("Integration Tests Only")
            success = (
                runner.check_dependencies() and runner.check_project_structure() and runner.run_integration_tests()
            )
        else:
            # Run all tests
            success = asyncio.run(runner.run_all_tests(skip_quality=args.skip_quality, output_file=args.output))

        # Exit with appropriate code
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n❌ Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test execution failed with error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
