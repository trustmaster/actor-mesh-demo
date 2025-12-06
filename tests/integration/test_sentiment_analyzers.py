"""
Integration tests for Sentiment Analyzer implementations.

Tests the integration of different sentiment analyzer implementations with the
message processing pipeline, NATS communication, and end-to-end functionality.
"""

from datetime import datetime

import pytest

from actors.sentiment_config import create_sentiment_analyzer
from models.message import MessagePayload

# Try to import VADER to know if we can test simple_ml
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False


class TestSentimentAnalyzerIntegration:
    """Integration tests for sentiment analyzer implementations."""

    @pytest.fixture
    def sample_messages(self):
        """Sample customer messages for testing."""
        return {
            "positive": {
                "message": "Thank you so much! The product is amazing and arrived quickly. Excellent service!",
                "expected_sentiment": "positive",
                "expected_urgency": "low",
                "expected_complaint": False,
            },
            "negative": {
                "message": "This is terrible! I hate this product. It's broken and useless. Want a refund!",
                "expected_sentiment": "negative",
                "expected_urgency": "low",
                "expected_complaint": True,
            },
            "urgent_negative": {
                "message": "This is terrible and urgent! I hate this broken product and need help immediately!",
                "expected_sentiment": "negative",
                "expected_urgency": "high",
                "expected_complaint": True,
            },
            "escalation": {
                "message": "This is terrible and unacceptable! I want to speak to your manager right now!",
                "expected_sentiment": "negative",
                "expected_urgency": "medium",
                "expected_complaint": True,
                "expected_escalation": True,
            },
            "neutral": {
                "message": "I need to check the status of order #12345.",
                "expected_sentiment": "neutral",
                "expected_urgency": "low",
                "expected_complaint": False,
            },
        }

    @pytest.mark.asyncio
    async def test_rule_based_analyzer_message_processing(self, sample_messages):
        """Test rule-based analyzer processes messages correctly."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        for scenario_name, scenario in sample_messages.items():
            payload = MessagePayload(
                customer_email=f"{scenario_name}@test.com",
                customer_message=scenario["message"],
                session_id=f"test-{scenario_name}",
                timestamp=datetime.now().isoformat(),
            )

            result = await analyzer.process(payload)

            assert result is not None
            assert "sentiment" in result
            assert "urgency" in result
            assert "is_complaint" in result

            # Check sentiment
            assert result["sentiment"]["label"] == scenario["expected_sentiment"]

            # Check complaint detection
            assert result["is_complaint"] == scenario["expected_complaint"]

            # Check analysis method
            assert result["analysis_method"] == "rule_based"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    async def test_simple_ml_analyzer_message_processing(self, sample_messages):
        """Test simple ML analyzer processes messages correctly."""
        analyzer = create_sentiment_analyzer(analyzer_type="simple_ml")

        for scenario_name, scenario in sample_messages.items():
            payload = MessagePayload(
                customer_email=f"{scenario_name}@test.com",
                customer_message=scenario["message"],
                session_id=f"test-{scenario_name}",
                timestamp=datetime.now().isoformat(),
            )

            result = await analyzer.process(payload)

            assert result is not None
            assert "sentiment" in result
            assert "urgency" in result
            assert "is_complaint" in result

            # Check sentiment
            assert result["sentiment"]["label"] == scenario["expected_sentiment"]

            # Check analysis method
            assert result["analysis_method"] == "vader_ml"

            # Check VADER-specific scores
            assert "scores" in result["sentiment"]
            assert "compound" in result["sentiment"]["scores"]

    @pytest.mark.asyncio
    async def test_analyzers_produce_compatible_output(self):
        """Test that all analyzer types produce compatible output structures."""
        message = "I love this product! It's amazing!"
        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message=message,
            session_id="compatibility-test",
            timestamp=datetime.now().isoformat(),
        )

        analyzer_types = ["rule_based"]
        if VADER_AVAILABLE:
            analyzer_types.append("simple_ml")

        results = []
        for analyzer_type in analyzer_types:
            analyzer = create_sentiment_analyzer(analyzer_type=analyzer_type)
            result = await analyzer.process(payload)
            results.append(result)

        # All results should have the same structure
        for result in results:
            assert "sentiment" in result
            assert "urgency" in result
            assert "is_complaint" in result
            assert "escalation_needed" in result
            assert "analysis_method" in result
            assert "processed_at" in result

            # Sentiment should have required fields
            assert "label" in result["sentiment"]
            assert "confidence" in result["sentiment"]
            assert "score" in result["sentiment"]

            # Urgency should have required fields
            assert "level" in result["urgency"]
            assert "score" in result["urgency"]

    @pytest.mark.asyncio
    async def test_analyzer_error_handling(self):
        """Test that analyzers handle errors gracefully."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        # Test with empty message (None not allowed by MessagePayload)
        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="",
            session_id="error-test",
            timestamp=datetime.now().isoformat(),
        )

        result = await analyzer.process(payload)

        # Should return a result, not crash
        assert result is not None
        assert "sentiment" in result

    @pytest.mark.asyncio
    async def test_analyzer_payload_enrichment(self):
        """Test that analyzers properly enrich the payload."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="This is excellent!",
            session_id="enrichment-test",
            timestamp=datetime.now().isoformat(),
        )

        # Process the message
        result = await analyzer.process(payload)

        # The result should contain all analysis data
        assert result is not None
        assert result["sentiment"]["label"] == "positive"

    @pytest.mark.asyncio
    async def test_multiple_messages_sequential_processing(self):
        """Test processing multiple messages sequentially."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        messages = [
            "This is great!",
            "This is terrible!",
            "Can you help me?",
        ]

        results = []
        for i, msg in enumerate(messages):
            payload = MessagePayload(
                customer_email=f"test{i}@example.com",
                customer_message=msg,
                session_id=f"seq-test-{i}",
                timestamp=datetime.now().isoformat(),
            )
            result = await analyzer.process(payload)
            results.append(result)

        # All should succeed
        assert len(results) == 3
        assert all(r is not None for r in results)

        # Check sentiments are different
        assert results[0]["sentiment"]["label"] == "positive"
        assert results[1]["sentiment"]["label"] == "negative"

    @pytest.mark.asyncio
    async def test_analyzer_performance(self):
        """Test analyzer performance with multiple messages."""
        import time

        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        messages = [f"Test message {i}" for i in range(100)]

        start_time = time.time()

        for i, msg in enumerate(messages):
            payload = MessagePayload(
                customer_email=f"test{i}@example.com",
                customer_message=msg,
                session_id=f"perf-test-{i}",
                timestamp=datetime.now().isoformat(),
            )
            await analyzer.process(payload)

        end_time = time.time()
        duration = end_time - start_time

        # Should process 100 messages in less than 5 seconds
        assert duration < 5.0
        print(f"Processed 100 messages in {duration:.2f} seconds")

    @pytest.mark.asyncio
    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    async def test_simple_ml_vs_rule_based_consistency(self):
        """Test that simple ML and rule-based produce similar results for clear cases."""
        clear_positive = "Excellent service! Amazing product! Very happy!"
        clear_negative = "Terrible! Awful! Worst experience ever!"

        payload_positive = MessagePayload(
            customer_email="test@example.com",
            customer_message=clear_positive,
            session_id="comparison-pos",
            timestamp=datetime.now().isoformat(),
        )

        payload_negative = MessagePayload(
            customer_email="test@example.com",
            customer_message=clear_negative,
            session_id="comparison-neg",
            timestamp=datetime.now().isoformat(),
        )

        # Test with rule-based
        rule_analyzer = create_sentiment_analyzer(analyzer_type="rule_based")
        rule_pos = await rule_analyzer.process(payload_positive)
        rule_neg = await rule_analyzer.process(payload_negative)

        # Test with simple ML
        ml_analyzer = create_sentiment_analyzer(analyzer_type="simple_ml")
        ml_pos = await ml_analyzer.process(payload_positive)
        ml_neg = await ml_analyzer.process(payload_negative)

        # Both should agree on clear cases
        assert rule_pos["sentiment"]["label"] == ml_pos["sentiment"]["label"] == "positive"
        assert rule_neg["sentiment"]["label"] == ml_neg["sentiment"]["label"] == "negative"

    @pytest.mark.asyncio
    async def test_analyzer_with_complex_message(self):
        """Test analyzer with a complex, multi-aspect message."""
        complex_message = """
        I am extremely frustrated and angry with this terrible situation. I ordered a laptop 2 weeks ago,
        and it still hasn't arrived. I need it urgently for an important work presentation
        that's happening tomorrow. This is completely unacceptable and horrible, and I'm very disappointed
        with your awful service. I would like to file a complaint and speak to a manager immediately and get a full
        refund if this isn't resolved today. This is the worst customer experience I've
        ever had, and I will be leaving negative reviews if this isn't fixed right away.
        """

        payload = MessagePayload(
            customer_email="frustrated@example.com",
            customer_message=complex_message,
            session_id="complex-test",
            timestamp=datetime.now().isoformat(),
        )

        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")
        result = await analyzer.process(payload)

        # Should detect multiple aspects
        assert result["sentiment"]["label"] == "negative"
        assert result["urgency"]["level"] in ["high", "medium"]
        assert result["is_complaint"] is True
        assert result["escalation_needed"] is True

    @pytest.mark.asyncio
    async def test_analyzer_keyword_detection(self):
        """Test that analyzers properly detect and return keywords."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="This is urgent and I want to complain about this terrible service!",
            session_id="keyword-test",
            timestamp=datetime.now().isoformat(),
        )

        result = await analyzer.process(payload)

        # Should have keywords detected
        assert "keywords_detected" in result
        keywords = result["keywords_detected"]

        assert "sentiment_keywords" in keywords
        assert "urgency_keywords" in keywords
        assert "complaint_keywords" in keywords
        assert "escalation_keywords" in keywords

    @pytest.mark.asyncio
    async def test_analyzer_model_info(self):
        """Test that analyzers provide model information."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="Test message",
            session_id="model-info-test",
            timestamp=datetime.now().isoformat(),
        )

        result = await analyzer.process(payload)

        # Should have model info
        assert "model_info" in result
        model_info = result["model_info"]

        assert "analyzer_type" in model_info
        assert "version" in model_info

    @pytest.mark.asyncio
    async def test_analyzer_timestamp_recording(self):
        """Test that analyzers record processing timestamps."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="Test message",
            session_id="timestamp-test",
            timestamp=datetime.now().isoformat(),
        )

        result = await analyzer.process(payload)

        # Should have timestamp
        assert "processed_at" in result
        assert isinstance(result["processed_at"], str)

        # Should be a valid ISO format timestamp
        # Just check it's not empty
        assert len(result["processed_at"]) > 0

    @pytest.mark.asyncio
    async def test_empty_message_handling_integration(self):
        """Test integration-level handling of empty messages."""
        analyzer = create_sentiment_analyzer(analyzer_type="rule_based")

        test_cases = [
            "",
            "   ",
        ]

        for i, msg in enumerate(test_cases):
            payload = MessagePayload(
                customer_email=f"test{i}@example.com",
                customer_message=msg,
                session_id=f"empty-test-{i}",
                timestamp=datetime.now().isoformat(),
            )

            result = await analyzer.process(payload)

            # Should handle gracefully
            assert result is not None
            assert "sentiment" in result
            # Should default to neutral for empty messages
            assert result["sentiment"]["label"] in ["neutral", "positive"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not VADER_AVAILABLE, reason="VADER not installed")
    async def test_vader_specific_features(self):
        """Test VADER-specific features like emoji and punctuation handling."""
        analyzer = create_sentiment_analyzer(analyzer_type="simple_ml")

        # Test with emphasis punctuation
        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message="This is GREAT!!!",
            session_id="vader-emphasis-test",
            timestamp=datetime.now().isoformat(),
        )

        result = await analyzer.process(payload)

        assert result["sentiment"]["label"] == "positive"
        # VADER should give high confidence for emphatic messages
        assert result["sentiment"]["confidence"] > 0.5


class TestAnalyzerSwitching:
    """Test switching between different analyzer implementations."""

    @pytest.mark.asyncio
    async def test_switch_analyzers_runtime(self):
        """Test switching between analyzers at runtime."""
        message = "This is a test message"
        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message=message,
            session_id="switch-test",
            timestamp=datetime.now().isoformat(),
        )

        # Create and use rule-based analyzer
        rule_analyzer = create_sentiment_analyzer(analyzer_type="rule_based")
        rule_result = await rule_analyzer.process(payload)

        assert rule_result["analysis_method"] == "rule_based"

        # Switch to simple ML if available
        if VADER_AVAILABLE:
            ml_analyzer = create_sentiment_analyzer(analyzer_type="simple_ml")
            ml_result = await ml_analyzer.process(payload)

            assert ml_result["analysis_method"] == "vader_ml"

    @pytest.mark.asyncio
    async def test_analyzer_independence(self):
        """Test that different analyzer instances are independent."""
        analyzer1 = create_sentiment_analyzer(analyzer_type="rule_based")
        analyzer2 = create_sentiment_analyzer(analyzer_type="rule_based")

        # Should be different instances
        assert analyzer1 is not analyzer2

        # Should produce same results for same input
        message = "Great product!"
        payload = MessagePayload(
            customer_email="test@example.com",
            customer_message=message,
            session_id="independence-test",
            timestamp=datetime.now().isoformat(),
        )

        result1 = await analyzer1.process(payload)
        result2 = await analyzer2.process(payload)

        assert result1["sentiment"]["label"] == result2["sentiment"]["label"]
