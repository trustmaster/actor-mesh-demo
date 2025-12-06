"""
Unit tests for Simple ML (VADER) Sentiment Analyzer.

Tests the VADER-based sentiment analysis functionality including ML sentiment detection,
urgency analysis, complaint detection, and message processing.
"""

from unittest.mock import patch

import pytest

# Try to import VADER, mark tests as skipped if not available
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

from actors.sentiment_analyzer_simple_ml import SentimentAnalyzer, create_sentiment_analyzer


class TestSimpleMLSentimentAnalyzer:
    """Test cases for Simple ML SentimentAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create a Simple ML SentimentAnalyzer instance for testing."""
        return SentimentAnalyzer()

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyzer_initialization(self, analyzer):
        """Test sentiment analyzer initialization."""
        assert analyzer.name == "sentiment_analyzer"
        assert analyzer.nats_url == "nats://localhost:4222"
        assert analyzer.ml_available is True

        # Check keyword sets are populated
        assert len(analyzer.urgency_keywords) > 0
        assert len(analyzer.complaint_keywords) > 0
        assert len(analyzer.escalation_keywords) > 0

        # Verify some expected keywords
        assert "urgent" in analyzer.urgency_keywords
        assert "complaint" in analyzer.complaint_keywords
        assert "manager" in analyzer.escalation_keywords

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_vader_initialization(self, analyzer):
        """Test VADER analyzer is initialized."""
        assert analyzer.vader is not None
        assert isinstance(analyzer.vader, SentimentIntensityAnalyzer)

    def test_analyzer_initialization_without_vader(self):
        """Test analyzer works without VADER installed."""
        with patch("actors.sentiment_analyzer_simple_ml.VADER_AVAILABLE", False):
            analyzer = SentimentAnalyzer()
            assert analyzer.ml_available is False
            assert analyzer.vader is None

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_sentiment_positive(self, analyzer):
        """Test sentiment analysis for positive messages."""
        result = analyzer._analyze_sentiment("Thank you so much! The product is amazing and works perfectly.")

        assert result["label"] == "positive"
        assert result["confidence"] > 0.5
        assert "compound" in result["scores"]
        assert result["scores"]["compound"] > 0.05
        assert isinstance(result["keywords"], list)

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_sentiment_negative(self, analyzer):
        """Test sentiment analysis for negative messages."""
        result = analyzer._analyze_sentiment("This is absolutely terrible! I hate this product and it's broken!")

        assert result["label"] == "negative"
        assert result["confidence"] > 0.5
        assert "compound" in result["scores"]
        assert result["scores"]["compound"] < -0.05
        assert isinstance(result["keywords"], list)

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_sentiment_neutral(self, analyzer):
        """Test sentiment analysis for neutral messages."""
        result = analyzer._analyze_sentiment("I need to check the status of my order.")

        assert result["label"] in ["neutral", "positive"]  # VADER might lean slightly positive
        assert "compound" in result["scores"]
        assert abs(result["scores"]["compound"]) <= 0.5

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_sentiment_with_scores(self, analyzer):
        """Test that sentiment analysis returns all VADER scores."""
        result = analyzer._analyze_sentiment("Excellent service!")

        assert "scores" in result
        scores = result["scores"]
        assert "compound" in scores
        assert "positive" in scores
        assert "negative" in scores
        assert "neutral" in scores

        # Scores should be in valid ranges
        assert -1.0 <= scores["compound"] <= 1.0
        assert 0.0 <= scores["positive"] <= 1.0
        assert 0.0 <= scores["negative"] <= 1.0
        assert 0.0 <= scores["neutral"] <= 1.0

    def test_fallback_sentiment_analysis(self, analyzer):
        """Test fallback sentiment analysis when VADER fails."""
        result = analyzer._fallback_sentiment_analysis("This is great!")

        assert "label" in result
        assert "confidence" in result
        assert "score" in result
        assert result["label"] in ["positive", "negative", "neutral"]

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_urgency_high(self, analyzer):
        """Test urgency analysis for high urgency messages."""
        result = analyzer._analyze_urgency("This is urgent! I need help immediately!")

        assert result["level"] in ["high", "medium"]  # Should detect urgency
        assert result["score"] > 0
        assert len(result["keywords"]) > 0
        assert any(kw in ["urgent", "immediately"] for kw in result["keywords"])

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_urgency_medium(self, analyzer):
        """Test urgency analysis for medium urgency messages."""
        result = analyzer._analyze_urgency("I need this soon, it's quite important.")

        assert result["level"] in ["medium", "low"]
        assert result["score"] >= 0

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_urgency_low(self, analyzer):
        """Test urgency analysis for low urgency messages."""
        result = analyzer._analyze_urgency("Please help me when you have time.")

        assert result["level"] == "low"
        assert result["score"] >= 0

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_complaint_detection(self, analyzer):
        """Test complaint detection."""
        # Test complaint detection with explicit pattern
        result = analyzer._analyze_complaint("I want to file a complaint about my order")
        assert result["is_complaint"] is True
        assert result["score"] > 0

        # Test non-complaint message
        result = analyzer._analyze_complaint("Thank you for the excellent service")
        assert result["is_complaint"] is False

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_analyze_escalation_detection(self, analyzer):
        """Test escalation detection."""
        # Test escalation detection
        result = analyzer._analyze_escalation("I want to speak to your manager right now!")
        assert result["escalation_needed"] is True
        assert result["score"] > 0

        # Test non-escalation message
        result = analyzer._analyze_escalation("Can you help me with my order?")
        assert result["escalation_needed"] is False

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_complex_message_analysis(self, analyzer):
        """Test complex message with multiple analysis aspects."""
        message = """
        I am extremely frustrated! I ordered a laptop 2 weeks ago and it still
        hasn't arrived. I need it urgently for work. This is unacceptable.
        I want a refund immediately or I will escalate this to a manager.
        """

        sentiment = analyzer._analyze_sentiment(message)
        urgency = analyzer._analyze_urgency(message)
        complaint = analyzer._analyze_complaint(message)
        escalation = analyzer._analyze_escalation(message)

        # Should detect all aspects
        assert sentiment["label"] == "negative"
        assert sentiment["confidence"] > 0.5
        assert urgency["level"] in ["high", "medium"]
        assert complaint["is_complaint"] is True
        assert escalation["escalation_needed"] is True

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_sentiment_keyword_extraction(self, analyzer):
        """Test sentiment keyword extraction."""
        result = analyzer._analyze_sentiment("This is terrible and awful!")

        assert "keywords" in result
        assert isinstance(result["keywords"], list)
        # Should extract negative keywords
        assert any(kw in ["terrible", "awful"] for kw in result["keywords"])

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_factory_function(self):
        """Test the factory function creates analyzer correctly."""
        analyzer = create_sentiment_analyzer()
        assert isinstance(analyzer, SentimentAnalyzer)
        assert analyzer.name == "sentiment_analyzer"

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_factory_function_custom_url(self):
        """Test factory function with custom NATS URL."""
        custom_url = "nats://custom:4222"
        analyzer = create_sentiment_analyzer(custom_url)
        assert analyzer.nats_url == custom_url

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_edge_cases(self, analyzer):
        """Test edge cases."""
        # Empty string
        result = analyzer._analyze_sentiment("")
        assert result["label"] == "neutral"

        # Very short message
        result = analyzer._analyze_sentiment("ok")
        assert result["label"] in ["neutral", "positive"]

        # All caps (should still work)
        result = analyzer._analyze_sentiment("EXCELLENT SERVICE!")
        assert result["label"] == "positive"

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_mixed_sentiment(self, analyzer):
        """Test mixed sentiment messages."""
        result = analyzer._analyze_sentiment("The product is great but the delivery was terrible")
        # Should handle mixed sentiment - VADER is good at this
        assert result["label"] in ["positive", "negative", "neutral"]
        assert "compound" in result["scores"]

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_urgency_patterns(self, analyzer):
        """Test urgency pattern detection."""
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

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_complaint_patterns(self, analyzer):
        """Test complaint pattern detection."""
        test_cases = [
            ("I want to file a complaint", True),
            ("This is terrible and I'm not satisfied", True),
            ("I want a refund immediately and I'm frustrated", True),  # Need more complaint keywords
            ("Everything is working fine", False),
        ]

        for message, is_complaint in test_cases:
            result = analyzer._analyze_complaint(message)
            assert result["is_complaint"] == is_complaint

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_escalation_patterns(self, analyzer):
        """Test escalation pattern detection."""
        test_cases = [
            ("I want to speak to your manager", True),
            ("This is unacceptable, I will sue", True),
            ("Can you help me please", False),
        ]

        for message, needs_escalation in test_cases:
            result = analyzer._analyze_escalation(message)
            assert result["escalation_needed"] == needs_escalation

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_confidence_ranges(self, analyzer):
        """Test confidence scores are in valid ranges."""
        messages = [
            "Excellent service!",
            "This is terrible!",
            "Order status?",
        ]

        for msg in messages:
            result = analyzer._analyze_sentiment(msg)
            assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_vader_punctuation_emphasis(self, analyzer):
        """Test that VADER handles punctuation emphasis."""
        # VADER is good at understanding emphasis
        result1 = analyzer._analyze_sentiment("I love this")
        result2 = analyzer._analyze_sentiment("I love this!")
        result3 = analyzer._analyze_sentiment("I LOVE THIS!!!")

        # More emphasis should increase sentiment
        assert result3["scores"]["compound"] >= result2["scores"]["compound"]

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_vader_emoji_support(self, analyzer):
        """Test that VADER handles emojis (VADER has emoji support)."""
        result = analyzer._analyze_sentiment("This is great! 😊")
        # Should still work and be positive
        assert result["label"] == "positive"

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_case_insensitive_analysis(self, analyzer):
        """Test that analysis is case insensitive."""
        messages = [
            "EXCELLENT service",
            "excellent service",
            "Excellent Service",
        ]

        results = [analyzer._analyze_sentiment(msg) for msg in messages]
        labels = [r["label"] for r in results]

        # All should be positive
        assert all(label == "positive" for label in labels)

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_performance_large_message(self, analyzer):
        """Test performance with large messages."""
        # Create a large message
        large_message = " ".join(
            [
                "This is a test message with many words to test performance.",
                "The message contains various sentiment indicators.",
            ]
            * 100
        )

        import time

        start_time = time.time()
        result = analyzer._analyze_sentiment(large_message)
        end_time = time.time()

        # VADER should be very fast (< 0.1 seconds even for large messages)
        assert end_time - start_time < 0.5
        assert result is not None
        assert "label" in result

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_vader_negation_handling(self, analyzer):
        """Test that VADER handles negation correctly."""
        # VADER is specifically good at negation
        positive_result = analyzer._analyze_sentiment("This is good")
        negated_result = analyzer._analyze_sentiment("This is not bad")

        # Both should be positive or neutral
        assert positive_result["label"] == "positive"
        # "not bad" should be neutral or slightly positive
        assert negated_result["label"] in ["neutral", "positive"]

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_vader_degree_modifiers(self, analyzer):
        """Test that VADER handles degree modifiers."""
        # VADER handles degree modifiers well
        result1 = analyzer._analyze_sentiment("This is good")
        result2 = analyzer._analyze_sentiment("This is very good")
        result3 = analyzer._analyze_sentiment("This is extremely good")

        # More intense modifiers should increase sentiment
        assert result2["scores"]["compound"] > result1["scores"]["compound"]
        assert result3["scores"]["compound"] >= result2["scores"]["compound"]

    def test_fallback_handles_errors(self, analyzer):
        """Test fallback works when VADER has issues."""
        # Temporarily disable VADER
        original_vader = analyzer.vader
        analyzer.vader = None

        result = analyzer._analyze_sentiment("This is a test")

        # Should use fallback
        assert result is not None
        assert "label" in result

        # Restore VADER
        analyzer.vader = original_vader

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_empty_message_handling(self, analyzer):
        """Test handling of empty messages."""
        result = analyzer._analyze_sentiment("")
        assert result["label"] == "neutral"

        result = analyzer._analyze_sentiment("   ")
        assert result["label"] in ["neutral", "positive"]

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_urgency_keyword_detection(self, analyzer):
        """Test urgency keyword detection."""
        message = "This is urgent and I need it immediately today!"
        result = analyzer._analyze_urgency(message)

        assert "keywords" in result
        assert len(result["keywords"]) >= 2
        urgency_words = {"urgent", "immediately", "today"}
        assert any(kw in urgency_words for kw in result["keywords"])

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_complaint_keyword_detection(self, analyzer):
        """Test complaint keyword detection."""
        message = "I have a complaint about the broken product, this is unacceptable"
        result = analyzer._analyze_complaint(message)

        assert "keywords" in result
        assert len(result["keywords"]) > 0
        assert result["is_complaint"] is True

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_escalation_keyword_detection(self, analyzer):
        """Test escalation keyword detection."""
        message = "I want to speak to the manager right now, this is unacceptable"
        result = analyzer._analyze_escalation(message)

        assert "keywords" in result
        assert "manager" in result["keywords"]
        assert result["escalation_needed"] is True

    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    def test_sentiment_scores_structure(self, analyzer):
        """Test that sentiment result has proper structure."""
        result = analyzer._analyze_sentiment("Test message")

        # Check all required fields
        assert "label" in result
        assert "confidence" in result
        assert "score" in result
        assert "scores" in result
        assert "keywords" in result

        # Check scores structure
        scores = result["scores"]
        assert "compound" in scores
        assert "positive" in scores
        assert "negative" in scores
        assert "neutral" in scores
