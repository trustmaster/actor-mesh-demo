#!/usr/bin/env python3
"""
Test setup validation script for Actor Mesh E-commerce Support Agent.

This script validates that the test environment is properly configured
and all dependencies are available before running the full test suite.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_python_version():
    """Check Python version compatibility."""
    print("🐍 Checking Python version...")
    version = sys.version_info

    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python {version.major}.{version.minor} is not supported. Please use Python 3.8+")
        return False

    print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True


def check_required_packages():
    """Check that required packages are available."""
    print("\n📦 Checking required packages...")

    required_packages = [
        ("pytest", "pytest"),
        ("pytest_asyncio", "pytest-asyncio"),
        ("pydantic", "pydantic"),
        ("asyncio", "built-in asyncio"),
        ("json", "built-in json"),
        ("unittest.mock", "built-in unittest.mock"),
    ]

    missing_packages = []

    for package, display_name in required_packages:
        try:
            __import__(package)
            print(f"✅ {display_name}")
        except ImportError:
            print(f"❌ {display_name} - not found")
            missing_packages.append(display_name)

    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Install missing packages with: pip install pytest pytest-asyncio")
        return False

    return True


def check_project_structure():
    """Check that the project structure is correct."""
    print("\n📁 Checking project structure...")

    required_paths = [
        "models/__init__.py",
        "models/message.py",
        "actors/__init__.py",
        "actors/base.py",
        "actors/sentiment_analyzer.py",
        "storage/__init__.py",
        "storage/redis_client.py",
        "mock_services/__init__.py",
        "mock_services/customer_api.py",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/unit",
        "tests/integration",
    ]

    missing_paths = []

    for path in required_paths:
        full_path = project_root / path
        if full_path.exists():
            print(f"✅ {path}")
        else:
            print(f"❌ {path} - not found")
            missing_paths.append(path)

    if missing_paths:
        print(f"\n❌ Missing paths: {missing_paths}")
        return False

    return True


def test_basic_imports():
    """Test that basic project modules can be imported."""
    print("\n🔧 Testing basic imports...")

    test_imports = [
        ("models.message", "Message models"),
        ("actors.base", "Base actor classes"),
        ("actors.sentiment_analyzer", "Sentiment analyzer"),
        ("storage.redis_client", "Redis client"),
        ("mock_services.customer_api", "Customer API"),
    ]

    failed_imports = []

    for module, description in test_imports:
        try:
            __import__(module)
            print(f"✅ {description}")
        except ImportError as e:
            print(f"❌ {description} - {e}")
            failed_imports.append(description)

    if failed_imports:
        print(f"\n❌ Failed imports: {failed_imports}")
        return False

    return True


async def test_basic_functionality():
    """Test basic functionality of core components."""
    print("\n⚙️ Testing basic functionality...")

    try:
        # Test message creation
        from models.message import MessagePayload, StandardRoutes, create_support_message

        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")

        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="Test message", customer_email="test@example.com", session_id="test-session", route=route
        )

        print("✅ Message creation works")

        # Test sentiment analyzer
        from actors.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        result = await analyzer.process(payload)

        assert result is not None
        assert "sentiment" in result
        assert "urgency" in result
        print("✅ Sentiment analyzer works")

        # Test route navigation
        assert route.get_current_actor() == "sentiment_analyzer"
        assert route.advance() is True
        assert route.get_current_actor() == "intent_analyzer"
        print("✅ Route navigation works")

        return True

    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False


def test_pytest_configuration():
    """Test that pytest is properly configured."""
    print("\n🧪 Testing pytest configuration...")

    try:
        # Check if pytest.ini exists
        pytest_ini = project_root / "pytest.ini"
        if pytest_ini.exists():
            print("✅ pytest.ini configuration found")
        else:
            print("❌ pytest.ini not found")
            return False

        # Check if conftest.py exists
        conftest = project_root / "tests" / "conftest.py"
        if conftest.exists():
            print("✅ conftest.py found")
        else:
            print("❌ conftest.py not found")
            return False

        return True

    except Exception as e:
        print(f"❌ Pytest configuration test failed: {e}")
        return False


async def run_validation():
    """Run all validation checks."""
    print("=" * 60)
    print("ACTOR MESH E-COMMERCE SUPPORT AGENT")
    print("Test Setup Validation")
    print("=" * 60)

    checks = [
        ("Python Version", check_python_version()),
        ("Required Packages", check_required_packages()),
        ("Project Structure", check_project_structure()),
        ("Basic Imports", test_basic_imports()),
        ("Basic Functionality", await test_basic_functionality()),
        ("Pytest Configuration", test_pytest_configuration()),
    ]

    all_passed = True

    for check_name, result in checks:
        if not result:
            all_passed = False

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for check_name, result in checks:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{check_name:.<40} {status}")

    if all_passed:
        print("\n🎉 All validation checks passed! The test environment is ready.")
        print("\nNext steps:")
        print("  • Run unit tests: make test-unit")
        print("  • Run all tests: make test")
        print("  • Run with coverage: make test-coverage")
        print("  • Run test runner: python tests/test_runner.py")
        return True
    else:
        print("\n❌ Some validation checks failed. Please fix the issues above.")
        print("\nCommon solutions:")
        print("  • Install dependencies: pip install -r requirements.txt")
        print("  • Check Python version: python --version")
        print("  • Verify project structure is complete")
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(run_validation())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
