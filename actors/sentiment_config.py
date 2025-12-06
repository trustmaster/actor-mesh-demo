#!/usr/bin/env python3
"""
Configuration for Sentiment Analyzer Selection

This module provides configuration and factory functions to easily switch
between different sentiment analyzer implementations:
- rule_based: Fast, stable, no dependencies (default)
- simple_ml: VADER-based, lightweight ML, CPU-only
- full_ml: Transformer-based, heavy but accurate (may crash on Apple Silicon)

Configuration can be set via:
1. Environment variable: SENTIMENT_ANALYZER_TYPE
2. Direct parameter to factory function
"""

import logging
import os
from typing import Any, Literal

# Valid analyzer types
SentimentAnalyzerType = Literal["rule_based", "simple_ml", "full_ml"]

# Default analyzer type
DEFAULT_ANALYZER_TYPE: SentimentAnalyzerType = "rule_based"

logger = logging.getLogger(__name__)


def get_analyzer_type() -> SentimentAnalyzerType:
    """
    Get the configured sentiment analyzer type.

    Checks the environment variable SENTIMENT_ANALYZER_TYPE.
    If not set or invalid, returns the default type.

    Returns:
        The analyzer type to use
    """
    analyzer_type = os.environ.get("SENTIMENT_ANALYZER_TYPE", DEFAULT_ANALYZER_TYPE).lower()

    valid_types = ["rule_based", "simple_ml", "full_ml"]
    if analyzer_type not in valid_types:
        logger.warning(
            f"Invalid SENTIMENT_ANALYZER_TYPE '{analyzer_type}'. "
            f"Valid options: {valid_types}. Using default: {DEFAULT_ANALYZER_TYPE}"
        )
        return DEFAULT_ANALYZER_TYPE

    return analyzer_type  # type: ignore


def create_sentiment_analyzer(
    nats_url: str = "nats://localhost:4222",
    analyzer_type: SentimentAnalyzerType | None = None,
) -> Any:
    """
    Factory function to create the appropriate sentiment analyzer.

    Args:
        nats_url: NATS server URL
        analyzer_type: Type of analyzer to create. If None, uses environment variable
                      or default. Options: "rule_based", "simple_ml", "full_ml"

    Returns:
        Configured SentimentAnalyzer instance

    Examples:
        # Use environment variable or default
        analyzer = create_sentiment_analyzer()

        # Force a specific type
        analyzer = create_sentiment_analyzer(analyzer_type="simple_ml")

        # Set via environment variable
        os.environ["SENTIMENT_ANALYZER_TYPE"] = "simple_ml"
        analyzer = create_sentiment_analyzer()
    """
    # Determine which analyzer to use
    if analyzer_type is None:
        analyzer_type = get_analyzer_type()

    logger.info(f"Creating sentiment analyzer: {analyzer_type}")

    try:
        if analyzer_type == "rule_based":
            from actors.sentiment_analyzer import SentimentAnalyzer

            logger.info("✅ Using rule-based sentiment analyzer (fast, stable, no ML)")

        elif analyzer_type == "simple_ml":
            try:
                from actors.sentiment_analyzer_simple_ml import SentimentAnalyzer

                logger.info("✅ Using simple ML sentiment analyzer (VADER, CPU-only)")
            except ImportError as e:
                logger.warning(
                    f"Failed to import simple_ml analyzer: {e}. "
                    "Install vaderSentiment: pip install vaderSentiment. "
                    "Falling back to rule_based analyzer."
                )
                from actors.sentiment_analyzer import SentimentAnalyzer

        elif analyzer_type == "full_ml":
            try:
                from actors.sentiment_analyzer_ml import SentimentAnalyzer

                logger.warning(
                    "⚠️  Using full ML analyzer with transformers. "
                    "This may crash on Apple Silicon. "
                    "Consider using 'simple_ml' or 'rule_based' instead."
                )
            except ImportError as e:
                logger.warning(f"Failed to import full_ml analyzer: {e}. Falling back to rule_based analyzer.")
                from actors.sentiment_analyzer import SentimentAnalyzer
        else:
            # Should never happen due to type checking, but be defensive
            logger.error(f"Unknown analyzer type: {analyzer_type}. Using rule_based.")
            from actors.sentiment_analyzer import SentimentAnalyzer

        return SentimentAnalyzer(nats_url)

    except Exception as e:
        logger.error(f"Error creating sentiment analyzer: {e}. Falling back to rule_based.")
        from actors.sentiment_analyzer import SentimentAnalyzer

        return SentimentAnalyzer(nats_url)


def print_analyzer_info() -> None:
    """Print information about available analyzers and current configuration."""
    current_type = get_analyzer_type()

    print("\n" + "=" * 70)
    print("SENTIMENT ANALYZER CONFIGURATION")
    print("=" * 70)
    print(f"\nCurrent setting: {current_type}")
    print(f"Environment variable: SENTIMENT_ANALYZER_TYPE={os.environ.get('SENTIMENT_ANALYZER_TYPE', '(not set)')}")
    print("\nAvailable analyzers:")
    print("  • rule_based  - Fast, stable, no ML dependencies (default)")
    print("  • simple_ml   - VADER ML, lightweight, CPU-only, good accuracy")
    print("  • full_ml     - Transformers, heavy, may crash on Apple Silicon")
    print("\nTo change analyzer:")
    print("  export SENTIMENT_ANALYZER_TYPE=simple_ml")
    print("  # Then restart your application")
    print("=" * 70 + "\n")


def check_dependencies() -> dict[str, bool]:
    """
    Check which analyzer dependencies are available.

    Returns:
        Dictionary with availability status for each analyzer type
    """
    status = {
        "rule_based": True,  # Always available, no dependencies
        "simple_ml": False,
        "full_ml": False,
    }

    # Check VADER
    try:
        import vaderSentiment

        status["simple_ml"] = True
    except ImportError:
        pass

    # Check transformers and torch
    try:
        import torch
        import transformers

        status["full_ml"] = True
    except ImportError:
        pass

    return status


def print_dependency_status() -> None:
    """Print the dependency status for each analyzer type."""
    status = check_dependencies()

    print("\n" + "=" * 70)
    print("SENTIMENT ANALYZER DEPENDENCIES")
    print("=" * 70)

    for analyzer_type, available in status.items():
        status_icon = "✅" if available else "❌"
        status_text = "Available" if available else "Not installed"

        print(f"\n{status_icon} {analyzer_type}: {status_text}")

        if analyzer_type == "simple_ml" and not available:
            print("   Install with: pip install vaderSentiment")
        elif analyzer_type == "full_ml" and not available:
            print("   Install with: pip install transformers torch")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    """Command-line interface for configuration management."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sentiment Analyzer Configuration Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current configuration
  python sentiment_config.py --info

  # Check dependency status
  python sentiment_config.py --check-deps

  # Test creating an analyzer
  python sentiment_config.py --test

  # Test a specific analyzer type
  python sentiment_config.py --test --type simple_ml
        """,
    )

    parser.add_argument("--info", action="store_true", help="Show analyzer configuration information")

    parser.add_argument("--check-deps", action="store_true", help="Check dependency status for all analyzer types")

    parser.add_argument("--test", action="store_true", help="Test creating a sentiment analyzer")

    parser.add_argument(
        "--type", type=str, choices=["rule_based", "simple_ml", "full_ml"], help="Analyzer type to use for testing"
    )

    args = parser.parse_args()

    # If no arguments, show info by default
    if not any([args.info, args.check_deps, args.test]):
        args.info = True
        args.check_deps = True

    if args.info:
        print_analyzer_info()

    if args.check_deps:
        print_dependency_status()

    if args.test:
        print("\n" + "=" * 70)
        print("TESTING SENTIMENT ANALYZER CREATION")
        print("=" * 70 + "\n")

        try:
            analyzer = create_sentiment_analyzer(analyzer_type=args.type if args.type else None)
            print(f"✅ Successfully created analyzer: {type(analyzer).__name__}")
            print(f"   Module: {type(analyzer).__module__}")
            print(f"   Actor name: {analyzer.actor_name}")
        except Exception as e:
            print(f"❌ Failed to create analyzer: {e}")

        print("\n" + "=" * 70 + "\n")
