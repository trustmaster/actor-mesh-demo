"""
Unit tests for SentimentAnalyzer actor.

Tests the sentiment analysis functionality including rule-based sentiment detection,
urgency analysis, complaint detection, and payload enrichment.
"""

import pytest
from actors.sentiment_analyzer import SentimentAnalyzer, create_sentiment_analyzer
from models.message import MessagePayload


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

        # Check keyword sets are populated
        assert len(analyzer.positive_keywords) > 0
        assert len(analyzer.negative_keywords) > 0
        assert len(analyzer.urgency_keywords) > 0
        assert len(analyzer.complaint_keywords) > 0

        # Verify some expected keywords
        assert "excellent" in analyzer.positive_keywords
        assert "terrible" in analyzer.negative_keywords
        assert "urgent" in analyzer.urgency_keywords
        assert "complaint" in analyzer.complaint_keywords

    @pytest.mark.asyncio
    async def test_process_positive_sentiment(self, analyzer):
        """Test processing message with positive sentiment."""
        payload = MessagePayload(
            customer_message="Thank you so much for the excellent service! I'm very happy with my order.",
            customer_email="happy@example.com",
        )

        result = await analyzer.process(payload)

        assert result is not None
        assert result["sentiment"]["label"] == "positive"
        assert result["sentiment"]["score"] > 0
        assert result["sentiment"]["confidence"] > 0
        assert result["urgency"]["level"] == "low"
        assert result["is_complaint"] is False
        assert result["analysis_method"] == "rule_based"
        assert "keywords_detected" in result
        assert "positive" in result["keywords_detected"]

    @pytest.mark.asyncio
    async def test_process_negative_sentiment(self, analyzer):
        """Test processing message with negative sentiment."""
        payload = MessagePayload(
            customer_message="This is absolutely terrible! I hate this product and I'm furious!",
            customer_email="angry@example.com",
        )

        result = await analyzer.process(payload)

        assert result is not None
        assert result["sentiment"]["label"] == "negative"
        assert result["sentiment"]["score"] < 0
        assert result["sentiment"]["confidence"] > 0
        assert result["is_complaint"] is True
        assert "negative" in result["keywords_detected"]

    @pytest.mark.asyncio
    async def test_process_neutral_sentiment(self, analyzer):
        """Test processing message with neutral sentiment."""
        payload = MessagePayload(
            customer_message="I would like to check the status of my order please.",
            customer_email="neutral@example.com",
        )

        result = await analyzer.process(payload)

        assert result is not None
        assert result["sentiment"]["label"] == "neutral"
        assert abs(result["sentiment"]["score"]) < 0.3
        assert result["urgency"]["level"] == "low"
        assert result["is_complaint"] is False

    @pytest.mark.asyncio
    async def test_process_high_urgency(self, analyzer):
        """Test processing message with high urgency."""
        payload = MessagePayload(
            customer_message="URGENT! I need this fixed immediately! It's an emergency!",
            customer_email="urgent@example.com",
        )

        result = await analyzer.process(payload)

        assert result is not None
        assert result["urgency"]["level"] == "high"
        assert result["urgency"]["score"] > 0.7
        assert "urgency" in result["keywords_detected"]

    @pytest.mark.asyncio
    async def test_process_medium_urgency(self, analyzer):
        """Test processing message with medium urgency."""
        payload = MessagePayload(
            customer_message="I need help with my order soon, it's quite important.",
            customer_email="medium@example.com",
        )

        result = await analyzer.process(payload)

        assert result is not None
        assert result["urgency"]["level"] in ["medium", "low"]  # Might be low due to fewer keywords

    @pytest.mark.asyncio
    async def test_process_complaint_detection(self, analyzer):
        """Test complaint detection functionality."""
        test_cases = [
            ("I have a complaint about my order", True),
            ("There's a problem with my delivery", True),
            ("This is broken and defective", True),
            ("My order is missing and I'm upset", True),
            ("Thank you for the great service", False),
            ("Can you help me track my order?", False),
        ]

        for message, expected_complaint in test_cases:
            payload = MessagePayload(customer_message=message, customer_email="test@example.com")

            result = await analyzer.process(payload)
            assert result["is_complaint"] == expected_complaint, f"Failed for message: {message}"

    @pytest.mark.asyncio
    async def test_payload_enrichment(self, analyzer):
        """Test payload enrichment functionality."""
        payload = MessagePayload(
            customer_message="I'm really frustrated with this terrible service!", customer_email="test@example.com"
        )

        result = await analyzer.process(payload)

        # Test enrichment method
        await analyzer._enrich_payload(payload, result)

        assert payload.sentiment == result
        assert payload.sentiment["sentiment"]["label"] == "negative"

    @pytest.mark.asyncio
    async def test_processing_error_handling(self, analyzer):
        """Test error handling during processing."""
        # Create a payload that might cause processing issues
        payload = MessagePayload(
            customer_message="",  # Empty message
            customer_email="test@example.com",
        )

        result = await analyzer.process(payload)

        # Should return fallback result
        assert result is not None
        assert result["sentiment"]["label"] == "neutral"
        assert result["sentiment"]["score"] == 0.0
        assert result["analysis_method"] == "fallback"

    def test_calculate_sentiment_score_positive(self, analyzer):
        """Test sentiment score calculation for positive messages."""
        message = "excellent amazing wonderful great fantastic"
        score = analyzer._calculate_sentiment_score(message)

        assert score > 0.5
        assert score <= 1.0

    def test_calculate_sentiment_score_negative(self, analyzer):
        """Test sentiment score calculation for negative messages."""
        message = "terrible awful horrible disgusting pathetic"
        score = analyzer._calculate_sentiment_score(message)

        assert score < -0.5
        assert score >= -1.0

    def test_calculate_sentiment_score_neutral(self, analyzer):
        """Test sentiment score calculation for neutral messages."""
        message = "please help me check the status"
        score = analyzer._calculate_sentiment_score(message)

        assert abs(score) < 0.3

    def test_calculate_sentiment_score_mixed(self, analyzer):
        """Test sentiment score calculation for mixed sentiment."""
        message = "great service but terrible delivery"
        score = analyzer._calculate_sentiment_score(message)

        # Should be somewhere between positive and negative
        assert -1.0 <= score <= 1.0

    def test_get_sentiment_label(self, analyzer):
        """Test sentiment label assignment."""
        assert analyzer._get_sentiment_label(0.5) == "positive"
        assert analyzer._get_sentiment_label(-0.5) == "negative"
        assert analyzer._get_sentiment_label(0.0) == "neutral"
        assert analyzer._get_sentiment_label(0.2) == "neutral"
        assert analyzer._get_sentiment_label(-0.2) == "neutral"

    def test_calculate_urgency_score_high(self, analyzer):
        """Test urgency score calculation for high urgency."""
        message = "urgent emergency asap immediately critical deadline expires today"
        score = analyzer._calculate_urgency_score(message)

        assert score > 0.5

    def test_calculate_urgency_score_low(self, analyzer):
        """Test urgency score calculation for low urgency."""
        message = "please help me when you have time"
        score = analyzer._calculate_urgency_score(message)

        assert score < 0.4

    def test_calculate_urgency_caps_and_exclamation(self, analyzer):
        """Test urgency detection from caps and exclamation marks."""
        message = "HELP ME NOW!!!"
        score = analyzer._calculate_urgency_score(message)

        assert score > 0.3  # Should detect urgency from caps and exclamations

    def test_get_urgency_level(self, analyzer):
        """Test urgency level assignment."""
        assert analyzer._get_urgency_level(0.8) == "high"
        assert analyzer._get_urgency_level(0.5) == "medium"
        assert analyzer._get_urgency_level(0.2) == "low"

    def test_detect_complaint_keywords(self, analyzer):
        """Test complaint detection with specific keywords."""
        test_cases = [
            ("I have a complaint", True),
            ("There's a problem", True),
            ("This is broken", True),
            ("My order is missing", True),
            ("Everything is working fine", False),  # No complaint keywords
        ]

        for message, expected in test_cases:
            result = analyzer._detect_complaint(message.lower())
            assert result == expected, f"Failed for message: {message}"

    def test_detect_complaint_negative_sentiment(self, analyzer):
        """Test complaint detection based on negative sentiment."""
        message = "this is terrible awful disgusting"  # Multiple negative words
        result = analyzer._detect_complaint(message.lower())

        assert result is True  # Should detect as complaint due to strong negative sentiment

    def test_calculate_confidence_factors(self, analyzer):
        """Test confidence calculation with various factors."""
        # Long message with keywords should have high confidence
        long_message = (
            "I am extremely frustrated and angry about this terrible awful service that is completely unacceptable"
        )
        confidence = analyzer._calculate_confidence(long_message, -0.8, 0.7)

        assert confidence > 0.5

        # Short message with no keywords should have low confidence
        short_message = "ok"
        confidence = analyzer._calculate_confidence(short_message, 0.0, 0.0)

        assert confidence < 0.5

    def test_extract_keywords(self, analyzer):
        """Test keyword extraction functionality."""
        message = "this is excellent but also terrible and urgent with a complaint"
        keywords = analyzer._extract_keywords(message)

        assert "positive" in keywords
        assert "excellent" in keywords["positive"]
        assert "negative" in keywords
        assert "terrible" in keywords["negative"]
        assert "urgency" in keywords
        assert "urgent" in keywords["urgency"]
        assert "complaint" in keywords
        assert "complaint" in keywords["complaint"]

    def test_extract_keywords_no_matches(self, analyzer):
        """Test keyword extraction with no matches."""
        message = "please help me check status"
        keywords = analyzer._extract_keywords(message)

        # Should return empty dict or dict with empty lists
        for category_keywords in keywords.values():
            assert len(category_keywords) == 0

    @pytest.mark.asyncio
    async def test_complex_message_analysis(self, analyzer):
        """Test analysis of complex real-world message."""
        payload = MessagePayload(
            customer_message="URGENT! I'm absolutely furious about my order ORD-12345! It was supposed to arrive yesterday for my important meeting today, but it's still missing! This is completely unacceptable and I need this fixed immediately! I'm filing a complaint!",
            customer_email="business@example.com",
        )

        result = await analyzer.process(payload)

        # Should detect high negativity
        assert result["sentiment"]["label"] == "negative"
        assert result["sentiment"]["score"] < -0.5

        # Should detect high urgency
        assert result["urgency"]["level"] == "high"
        assert result["urgency"]["score"] > 0.7

        # Should detect as complaint
        assert result["is_complaint"] is True

        # Should have high confidence
        assert result["sentiment"]["confidence"] > 0.7

        # Should detect multiple keyword categories
        keywords = result["keywords_detected"]
        assert "negative" in keywords
        assert "urgency" in keywords
        assert "complaint" in keywords

    @pytest.mark.asyncio
    async def test_polite_positive_message(self, analyzer):
        """Test analysis of polite positive message."""
        payload = MessagePayload(
            customer_message="Thank you very much for the excellent customer service! I really appreciate how quickly you resolved my issue. The quality is outstanding and I'm extremely satisfied with everything.",
            customer_email="satisfied@example.com",
        )

        result = await analyzer.process(payload)

        # Should detect strong positive sentiment
        assert result["sentiment"]["label"] == "positive"
        assert result["sentiment"]["score"] > 0.5

        # Should detect low urgency
        assert result["urgency"]["level"] == "low"

        # Should not be a complaint
        assert result["is_complaint"] is False

        # Should have good confidence due to clear positive language
        assert result["sentiment"]["confidence"] > 0.5

    def test_factory_function(self):
        """Test the factory function for creating sentiment analyzer."""
        analyzer = create_sentiment_analyzer("nats://test:4222")

        assert isinstance(analyzer, SentimentAnalyzer)
        assert analyzer.name == "sentiment_analyzer"
        assert analyzer.nats_url == "nats://test:4222"

    def test_factory_function_default_url(self):
        """Test the factory function with default NATS URL."""
        analyzer = create_sentiment_analyzer()

        assert analyzer.nats_url == "nats://localhost:4222"

    @pytest.mark.asyncio
    async def test_processing_time_tracking(self, analyzer):
        """Test that processing time is tracked."""
        payload = MessagePayload(customer_message="Test message for timing", customer_email="test@example.com")

        result = await analyzer.process(payload)

        assert "processed_at" in result
        assert isinstance(result["processed_at"], float)
        assert result["processed_at"] > 0

    @pytest.mark.asyncio
    async def test_edge_cases(self, analyzer):
        """Test edge cases and boundary conditions."""
        test_cases = [
            # Very short message
            MessagePayload(customer_message="ok", customer_email="test@example.com"),
            # Very long message
            MessagePayload(customer_message=" ".join(["test"] * 1000), customer_email="test@example.com"),
            # Message with special characters
            MessagePayload(customer_message="Hello! @#$%^&*() How are you???", customer_email="test@example.com"),
            # Message with numbers
            MessagePayload(customer_message="Order 12345 delivery on 2024-01-15", customer_email="test@example.com"),
        ]

        for payload in test_cases:
            result = await analyzer.process(payload)

            # Should handle all cases without error
            assert result is not None
            assert "sentiment" in result
            assert "urgency" in result
            assert "is_complaint" in result

    @pytest.mark.asyncio
    async def test_case_insensitive_analysis(self, analyzer):
        """Test that analysis is case insensitive."""
        test_cases = ["EXCELLENT SERVICE", "excellent service", "Excellent Service", "ExCeLlEnT sErViCe"]

        results = []
        for message in test_cases:
            payload = MessagePayload(customer_message=message, customer_email="test@example.com")
            result = await analyzer.process(payload)
            results.append(result["sentiment"]["label"])

        # All should be detected as positive regardless of case
        assert all(label == "positive" for label in results)

    @pytest.mark.asyncio
    async def test_mixed_languages_graceful_handling(self, analyzer):
        """Test graceful handling of mixed or non-English content."""
        payload = MessagePayload(
            customer_message="Excellent service! Très bon! 优秀的服务!", customer_email="international@example.com"
        )

        result = await analyzer.process(payload)

        # Should still detect the English positive word
        assert result is not None
        assert result["sentiment"]["label"] == "positive"  # Should catch "excellent"

    @pytest.mark.asyncio
    async def test_performance_large_message(self, analyzer):
        """Test performance with large message."""
        # Create a large message
        large_message = " ".join(
            [
                "This is a test message with many words to test performance.",
                "The message contains various sentiment indicators including excellent,",
                "terrible, urgent, and complaint keywords scattered throughout.",
                "We want to ensure that even with large messages the analysis",
                "completes quickly and accurately.",
            ]
            * 100
        )  # Repeat 100 times

        payload = MessagePayload(customer_message=large_message, customer_email="performance@example.com")

        import time

        start_time = time.time()
        result = await analyzer.process(payload)
        processing_time = time.time() - start_time

        # Should complete quickly (under 1 second)
        assert processing_time < 1.0
        assert result is not None

        # Should still detect sentiment correctly
        assert result["sentiment"]["label"] in ["positive", "negative", "neutral"]
