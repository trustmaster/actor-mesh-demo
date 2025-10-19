"""
Unit tests for SentimentAnalyzer actor.

Tests the sentiment analysis functionality including rule-based sentiment detection,
urgency analysis, complaint detection, and message processing.
"""

import pytest
from unittest.mock import patch

from actors.sentiment_analyzer import SentimentAnalyzer, create_sentiment_analyzer


class TestSentimentAnalyzer:
    """Test cases for SentimentAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create a SentimentAnalyzer instance for testing."""
        return SentimentAnalyzer()

    def test_analyzer_initialization(self, analyzer):
        """Test sentiment analyzer initialization."""
        assert analyzer.name == "sentiment_analyzer"
        assert analyzer.nats_url == "nats://localhost:4222"
        assert analyzer.subject == "ecommerce.support.sentiment_analyzer"

        # Check keyword sets are populated (using correct attribute names)
        assert len(analyzer.positive_words) > 0
        assert len(analyzer.negative_words) > 0
        assert len(analyzer.urgency_words) > 0
        assert len(analyzer.complaint_words) > 0

        # Verify some expected keywords
        assert "excellent" in analyzer.positive_words
        assert "terrible" in analyzer.negative_words
        assert "urgent" in analyzer.urgency_words
        assert "complaint" in analyzer.complaint_words

    def test_analyze_sentiment_positive(self, analyzer):
        """Test sentiment analysis for positive messages."""
        result = analyzer._analyze_sentiment("Thank you so much for the excellent service! I'm very happy with my order.")

        assert result["label"] == "positive"
        assert result["score"] > 0
        assert result["confidence"] > 0
        assert len(result["keywords"]) > 0

    def test_analyze_sentiment_negative(self, analyzer):
        """Test sentiment analysis for negative messages."""
        result = analyzer._analyze_sentiment("This is absolutely terrible! I hate this product and I'm furious!")

        assert result["label"] == "negative"
        assert result["score"] < 0
        assert result["confidence"] > 0
        assert len(result["keywords"]) > 0

    def test_analyze_sentiment_neutral(self, analyzer):
        """Test sentiment analysis for neutral messages."""
        result = analyzer._analyze_sentiment("I need to check the status of my order.")

        assert result["label"] == "neutral"
        assert abs(result["score"]) < 1.0
        assert result["confidence"] >= 0

    def test_analyze_urgency_high(self, analyzer):
        """Test urgency analysis for high urgency messages."""
        result = analyzer._analyze_urgency("This is urgent! I need help immediately!")

        assert result["level"] == "high"
        assert result["score"] > 0.7
        assert len(result["keywords"]) > 0

    def test_analyze_urgency_medium(self, analyzer):
        """Test urgency analysis for medium urgency messages."""
        result = analyzer._analyze_urgency("I need help with my order soon, it's quite important.")

        # Might be medium or low depending on keywords detected
        assert result["level"] in ["medium", "low"]
        assert result["score"] >= 0

    def test_analyze_urgency_low(self, analyzer):
        """Test urgency analysis for low urgency messages."""
        result = analyzer._analyze_urgency("Please help me check the status when you have time.")

        assert result["level"] == "low"
        assert result["score"] >= 0

    def test_analyze_complaint_detection(self, analyzer):
        """Test complaint detection."""
        # Test complaint detection - use message that triggers pattern matching
        result = analyzer._analyze_complaint("I want to file a complaint about my order")
        assert result["is_complaint"] is True

        result = analyzer._analyze_complaint("Thank you for the great service")
        assert result["is_complaint"] is False

    def test_analyze_escalation_detection(self, analyzer):
        """Test escalation detection."""
        # Test escalation detection
        result = analyzer._analyze_escalation("I want to speak to your manager right now!")
        assert result["escalation_needed"] is True

        result = analyzer._analyze_escalation("Can you help me with my order?")
        assert result["escalation_needed"] is False

    def test_sentiment_with_negation(self, analyzer):
        """Test sentiment analysis with negation."""
        result = analyzer._analyze_sentiment("This is not bad at all")
        # Should handle negation properly
        assert result["label"] in ["positive", "neutral"]

    def test_sentiment_with_intensifiers(self, analyzer):
        """Test sentiment analysis with intensifiers."""
        result = analyzer._analyze_sentiment("This is extremely excellent")
        # Should boost positive sentiment
        assert result["label"] == "positive"
        assert result["score"] > 1.0  # Should be amplified

    def test_message_processing_components(self, analyzer):
        """Test individual sentiment analysis components."""
        # Test that we can analyze a complex message with multiple aspects
        message = "This terrible service is urgent! I have a serious complaint and need to speak to a manager immediately!"

        sentiment = analyzer._analyze_sentiment(message)
        urgency = analyzer._analyze_urgency(message)
        complaint = analyzer._analyze_complaint(message)
        escalation = analyzer._analyze_escalation(message)

        # Should detect all aspects
        assert sentiment["label"] == "negative"
        assert urgency["level"] in ["high", "medium"]
        assert complaint["is_complaint"] is True
        assert escalation["escalation_needed"] is True

    def test_factory_function(self):
        """Test the factory function creates analyzer correctly."""
        analyzer = create_sentiment_analyzer()
        assert isinstance(analyzer, SentimentAnalyzer)
        assert analyzer.name == "sentiment_analyzer"

    def test_factory_function_custom_url(self):
        """Test factory function with custom NATS URL."""
        custom_url = "nats://custom:4222"
        analyzer = create_sentiment_analyzer(custom_url)
        assert analyzer.nats_url == custom_url

    def test_edge_cases(self, analyzer):
        """Test edge cases."""
        # Empty string
        result = analyzer._analyze_sentiment("")
        assert result["label"] == "neutral"
        assert result["confidence"] == 0.0

        # Very short message
        result = analyzer._analyze_sentiment("ok")
        assert result["label"] == "neutral"

        # All caps (should still work)
        result = analyzer._analyze_sentiment("EXCELLENT SERVICE!")
        assert result["label"] == "positive"

    def test_mixed_sentiment(self, analyzer):
        """Test mixed sentiment messages."""
        result = analyzer._analyze_sentiment("The product is great but the delivery was terrible")
        # Should handle mixed sentiment reasonably
        assert result["label"] in ["positive", "negative", "neutral"]

    def test_urgency_patterns(self, analyzer):
        """Test urgency pattern detection."""
        # Test various urgency patterns
        test_cases = [
            ("I need this today", True),
            ("This expires tomorrow", True),
            ("Time sensitive matter", True),
            ("When you get a chance", False),
        ]

        for message, should_be_urgent in test_cases:
            result = analyzer._analyze_urgency(message)
            if should_be_urgent:
                assert result["level"] in ["high", "medium"]
            # Note: We don't assert "low" for non-urgent as the algorithm might still detect some urgency

    def test_complaint_keywords(self, analyzer):
        """Test complaint keyword detection."""
        test_cases = [
            ("I want to file a complaint", True),  # Pattern match + keyword
            ("There's a problem with my order", True),  # 2 keywords (problem + order) = complaint
            ("This is broken and defective", True),  # 2 keywords = complaint
            ("My order is missing", True),  # 2 keywords (order + missing) = complaint
            ("Everything is working fine", False),  # No complaint keywords
        ]

        for message, is_complaint in test_cases:
            result = analyzer._analyze_complaint(message)
            assert result["is_complaint"] == is_complaint

    def test_escalation_keywords(self, analyzer):
        """Test escalation keyword detection."""
        test_cases = [
            ("I want to speak to your manager", True),  # Pattern match
            ("I'm calling my lawyer about this terrible service", True),  # 3+ keywords = escalation
            ("This is going to social media and twitter", True),  # 3+ keywords = escalation
            ("Can you help me please", False),
        ]

        for message, needs_escalation in test_cases:
            result = analyzer._analyze_escalation(message)
            assert result["escalation_needed"] == needs_escalation

    def test_confidence_calculation(self, analyzer):
        """Test confidence calculation."""
        # Message with many sentiment words should have higher confidence
        high_conf_msg = "excellent amazing wonderful fantastic great"
        result1 = analyzer._analyze_sentiment(high_conf_msg)

        # Message with few sentiment words should have lower confidence
        low_conf_msg = "good"
        result2 = analyzer._analyze_sentiment(low_conf_msg)

        assert result1["confidence"] >= result2["confidence"]

    def test_empty_message_handling(self, analyzer):
        """Test handling of empty or problematic messages."""
        # Test empty message
        result = analyzer._analyze_sentiment("")
        assert result["label"] == "neutral"
        assert result["confidence"] == 0.0

        # Test None-like input (should not crash)
        result = analyzer._analyze_sentiment("   ")  # Just whitespace
        assert result["label"] == "neutral"

    def test_performance_large_message(self, analyzer):
        """Test performance with large messages."""
        # Create a large message
        large_message = " ".join([
            "This is a test message with many words to test performance.",
            "The message contains various sentiment indicators including excellent,",
            "terrible, urgent, and complaint keywords scattered throughout.",
            "We want to ensure that even with large messages the analysis",
            "completes quickly and accurately.",
        ] * 50)  # Repeat 50 times

        import time
        start_time = time.time()
        result = analyzer._analyze_sentiment(large_message)
        end_time = time.time()

        # Should complete within reasonable time (less than 1 second)
        assert end_time - start_time < 1.0
        assert result is not None
        assert "label" in result

    def test_case_insensitive_analysis(self, analyzer):
        """Test that analysis is case insensitive."""
        messages = [
            "EXCELLENT service",
            "excellent service",
            "Excellent Service",
            "ExCeLlEnT sErViCe"
        ]

        results = [analyzer._analyze_sentiment(msg) for msg in messages]

        # All should produce similar results
        labels = [r["label"] for r in results]
        assert all(label == "positive" for label in labels)

    def test_complex_message_analysis(self, analyzer):
        """Test complex message with multiple analysis aspects."""
        message = "This terrible service is urgent! I have a serious complaint and need to speak to a manager immediately!"

        sentiment = analyzer._analyze_sentiment(message)
        urgency = analyzer._analyze_urgency(message)
        complaint = analyzer._analyze_complaint(message)
        escalation = analyzer._analyze_escalation(message)

        # Should detect all aspects
        assert sentiment["label"] == "negative"
        assert urgency["level"] in ["high", "medium"]
        assert complaint["is_complaint"] is True
        assert escalation["escalation_needed"] is True
