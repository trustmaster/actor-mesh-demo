"""
Sentiment Analyzer Actor for the Actor Mesh Demo.

This actor analyzes customer message sentiment and urgency levels using
DistilBERT models from HuggingFace, providing input for routing decisions
and response tone adaptation.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
import platform

from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import torch

from models.message import MessagePayload
from actors.base import ProcessorActor


class SentimentAnalyzer(ProcessorActor):
    """
    Processor actor that analyzes sentiment and urgency of customer messages.

    This actor uses DistilBERT models from HuggingFace for sentiment analysis
    and combines it with rule-based urgency detection.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        """Initialize the Sentiment Analyzer actor."""
        super().__init__("sentiment_analyzer", nats_url)

        # HuggingFace model configuration
        self.sentiment_model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"
        self.base_model_name: str = "distilbert-base-uncased"

        # Model objects (loaded lazily)
        self.sentiment_pipeline: Optional[Any] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.model: Optional[AutoModelForSequenceClassification] = None

        # Device configuration for Apple Silicon compatibility
        self.device = self._get_optimal_device()

        # Model loading flag
        self._models_loaded: bool = False

        # Rule-based keywords for urgency and complaint detection
        self.urgency_keywords: set[str] = {
            "urgent",
            "emergency",
            "asap",
            "immediately",
            "now",
            "today",
            "critical",
            "important",
            "rush",
            "quick",
            "fast",
            "soon",
            "deadline",
            "time-sensitive",
            "expire",
            "expires",
        }

        self.complaint_keywords: set[str] = {
            "complaint",
            "complain",
            "problem",
            "issue",
            "wrong",
            "error",
            "mistake",
            "broken",
            "defective",
            "damaged",
            "missing",
            "lost",
            "delayed",
            "late",
            "slow",
            "cancel",
            "refund",
            "return",
        }

        self.escalation_keywords: set[str] = {
            "manager",
            "supervisor",
            "escalate",
            "lawyer",
            "legal",
            "corporate",
            "headquarters",
            "ceo",
            "president",
        }

    def _get_optimal_device(self) -> str:
        """
        Get the optimal device for PyTorch operations based on the platform.

        Returns:
            Device string for PyTorch operations
        """
        try:
            # Check for Apple Silicon MPS support (macOS with Apple Silicon)
            if torch.backends.mps.is_available() and torch.backends.mps.is_built():
                return "mps"
            # Check for CUDA support
            elif torch.cuda.is_available():
                return "cuda"
            else:
                return "cpu"
        except Exception as e:
            self.logger.warning(f"Device detection failed, falling back to CPU: {e}")
            return "cpu"

    def _get_device_id(self) -> int:
        """
        Get the device ID for HuggingFace pipeline.

        Returns:
            Device ID: 0 for GPU/MPS, -1 for CPU
        """
        if self.device == "cpu":
            return -1
        else:
            # For both CUDA and MPS, use device 0
            return 0

    def _safe_tensor_operation(self, operation_func, *args, **kwargs):
        """
        Safely execute tensor operations with fallback handling.

        This method wraps tensor operations to handle potential memory alignment
        issues on Apple Silicon and other platforms.
        """
        try:
            # Force CPU execution for problematic operations on Apple Silicon
            if self.device == "mps" and platform.machine() == "arm64":
                # Set environment variables to avoid alignment issues
                import os
                os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

            return operation_func(*args, **kwargs)
        except RuntimeError as e:
            if "alignment" in str(e).lower() or "bus error" in str(e).lower():
                self.logger.warning(f"Tensor operation failed with alignment error, retrying on CPU: {e}")
                # Retry operation on CPU
                original_device = self.device
                self.device = "cpu"
                try:
                    if hasattr(self, 'model') and self.model is not None:
                        self.model = self.model.to("cpu")
                    result = operation_func(*args, **kwargs)
                    return result
                finally:
                    self.device = original_device
            else:
                raise e

    async def _load_models(self) -> None:
        """Load HuggingFace models asynchronously."""
        """Load DistilBERT models for sentiment analysis."""
        if self._models_loaded:
            return

        try:
            self.logger.info(f"Loading DistilBERT models on device: {self.device}")

            # Load sentiment analysis pipeline with proper device selection
            device_id = self._get_device_id()
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.sentiment_model_name,
                tokenizer=self.sentiment_model_name,
                return_all_scores=True,
                device=device_id,
            )

            # Load tokenizer and model for additional processing if needed
            self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.sentiment_model_name
            )

            # Move model to appropriate device if needed
            if self.device != "cpu":
                try:
                    self.model = self.model.to(self.device)
                except Exception as e:
                    self.logger.warning(f"Failed to move model to {self.device}, falling back to CPU: {e}")
                    self.device = "cpu"
                    self.model = self.model.to("cpu")

            self._models_loaded = True
            self.logger.info("DistilBERT models loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load models: {e}")
            # Fall back to rule-based analysis
            self.sentiment_pipeline = None
            self._models_loaded = False
            raise

    async def start(self) -> None:
        """Start the actor and load models."""
        await self._load_models()
        await super().start()

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Analyze sentiment and urgency of the customer message.

        Args:
            payload: Message payload containing customer message

        Returns:
            Dictionary with sentiment analysis results
        """
        try:
            message: str = payload.customer_message

            # Ensure models are loaded
            if not self._models_loaded:
                await self._load_models()

            # Perform sentiment analysis
            sentiment_result: Dict[str, Any] = await self._analyze_sentiment(message)

            # Calculate urgency using rule-based approach
            urgency_result: Dict[str, Any] = self._calculate_urgency(message)

            # Detect if it's a complaint
            is_complaint: bool = self._detect_complaint(message)

            # Extract detected keywords for analysis
            keywords_detected: Dict[str, List[str]] = self._extract_keywords(message)

            # Create comprehensive analysis result
            analysis_result: Dict[str, Any] = {
                "sentiment": sentiment_result,
                "urgency": urgency_result,
                "is_complaint": is_complaint,
                "keywords_detected": keywords_detected,
                "analysis_method": "distilbert_hybrid" if self.sentiment_pipeline else "rule_based_fallback",
                "processed_at": asyncio.get_event_loop().time(),
                "model_info": {
                    "sentiment_model": self.sentiment_model_name,
                    "base_model": self.base_model_name,
                    "device": str(self.device),
                },
            }

            self.logger.info(
                f"Sentiment analysis completed: {sentiment_result.get('label', 'unknown')} "
                f"(score: {sentiment_result.get('score', 0.0):.2f}, "
                f"urgency: {urgency_result.get('level', 'unknown')})"
            )

            return analysis_result

        except Exception as e:
            self.logger.error(f"Error in sentiment analysis: {e}")
            # Return neutral sentiment on error
            return {
                "sentiment": {"label": "neutral", "score": 0.0, "confidence": 0.0},
                "urgency": {"level": "low", "score": 0.0},
                "is_complaint": False,
                "keywords_detected": {},
                "analysis_method": "error_fallback",
                "error": str(e),
                "processed_at": asyncio.get_event_loop().time(),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with sentiment analysis results."""
        payload.sentiment = result

    async def _analyze_sentiment(self, message: str) -> Dict[str, Any]:
        """
        Analyze sentiment using DistilBERT model.

        Args:
            message: Input message text

        Returns:
            Dictionary with sentiment analysis results
        """
        if not self.sentiment_pipeline:
            # Fallback to rule-based analysis
            return self._fallback_sentiment_analysis(message)

        try:
            # Truncate message if too long (DistilBERT max sequence length is 512)
            max_length: int = 500  # Leave some room for special tokens
            if len(message) > max_length:
                message = message[:max_length]

            # Run sentiment analysis with safe tensor operations
            results: List[Dict[str, Union[str, float]]] = self._safe_tensor_operation(
                self.sentiment_pipeline, message
            )

            # Process results (returns all scores)
            sentiment_scores: Dict[str, float] = {}
            for result in results[0]:  # First (and only) input
                label: str = result["label"].lower()  # type: ignore
                score: float = float(result["score"])  # type: ignore
                sentiment_scores[label] = score

            # Determine primary sentiment
            primary_label: str = max(sentiment_scores.keys(), key=lambda k: sentiment_scores[k])
            primary_score: float = sentiment_scores[primary_label]

            # Map POSITIVE/NEGATIVE to our standard labels
            if primary_label == "positive":
                mapped_label = "positive"
            elif primary_label == "negative":
                mapped_label = "negative"
            else:
                mapped_label = "neutral"

            # Calculate confidence based on score difference
            confidence: float = self._calculate_confidence_from_scores(sentiment_scores)

            return {
                "label": mapped_label,
                "score": primary_score if mapped_label != "neutral" else 0.0,
                "confidence": confidence,
                "raw_scores": sentiment_scores,
                "method": "distilbert",
            }

        except Exception as e:
            self.logger.warning(f"DistilBERT analysis failed, falling back to rules: {e}")
            return self._fallback_sentiment_analysis(message)

    def _fallback_sentiment_analysis(self, message: str) -> Dict[str, Any]:
        """
        Fallback rule-based sentiment analysis.

        Args:
            message: Input message text

        Returns:
            Dictionary with sentiment analysis results
        """
        # Positive and negative keywords for fallback
        positive_keywords: set[str] = {
            "excellent", "great", "amazing", "fantastic", "wonderful",
            "perfect", "love", "happy", "satisfied", "pleased",
            "thank", "appreciate", "good", "nice", "awesome",
            "brilliant", "outstanding",
        }

        negative_keywords: set[str] = {
            "terrible", "awful", "horrible", "worst", "hate",
            "angry", "furious", "disappointed", "frustrated", "annoyed",
            "upset", "disgusted", "pathetic", "useless", "garbage",
            "ridiculous", "unacceptable", "disgusting", "appalled", "outraged",
        }

        words: set[str] = set(message.lower().split())

        positive_matches: int = len(words.intersection(positive_keywords))
        negative_matches: int = len(words.intersection(negative_keywords))

        if positive_matches == 0 and negative_matches == 0:
            return {
                "label": "neutral",
                "score": 0.0,
                "confidence": 0.5,
                "method": "rule_based_fallback",
            }

        total_matches: int = positive_matches + negative_matches
        positive_ratio: float = positive_matches / total_matches if total_matches > 0 else 0

        if positive_ratio > 0.6:
            label = "positive"
            score = positive_ratio
        elif positive_ratio < 0.4:
            label = "negative"
            score = 1.0 - positive_ratio
        else:
            label = "neutral"
            score = 0.5

        confidence: float = min(total_matches / 3.0, 1.0)

        return {
            "label": label,
            "score": score,
            "confidence": confidence,
            "method": "rule_based_fallback",
        }

    def _calculate_confidence_from_scores(self, scores: Dict[str, float]) -> float:
        """
        Calculate confidence based on sentiment score distribution.

        Args:
            scores: Dictionary of sentiment scores

        Returns:
            Confidence value between 0.0 and 1.0
        """
        if len(scores) < 2:
            return 1.0

        sorted_scores: List[float] = sorted(scores.values(), reverse=True)
        top_score: float = sorted_scores[0]
        second_score: float = sorted_scores[1] if len(sorted_scores) > 1 else 0.0

        # Confidence is based on the gap between top and second scores
        confidence: float = min((top_score - second_score) * 2.0, 1.0)
        return max(confidence, 0.1)  # Minimum confidence

    def _calculate_urgency(self, message: str) -> Dict[str, Any]:
        """
        Calculate urgency score based on keywords and patterns.

        Args:
            message: Input message text

        Returns:
            Dictionary with urgency analysis results
        """
        message_lower: str = message.lower()
        words: set[str] = set(message_lower.split())

        # Check for urgency keywords
        urgency_matches: int = len(words.intersection(self.urgency_keywords))

        # Check for time-related patterns
        time_patterns: List[str] = ["today", "tomorrow", "this week", "deadline", "expire"]
        time_score: int = sum(1 for pattern in time_patterns if pattern in message_lower)

        # Check for escalation language
        escalation_score: int = len(words.intersection(self.escalation_keywords))

        # Check for caps (indicates shouting/urgency)
        caps_ratio: float = sum(1 for c in message if c.isupper()) / len(message) if len(message) > 0 else 0.0
        caps_score: float = min(caps_ratio * 3.0, 1.0)

        # Check for multiple exclamation marks
        exclamation_score: float = min(message.count("!") / 3.0, 1.0)

        # Combine scores with weights
        total_score: float = (
            urgency_matches * 0.4
            + time_score * 0.2
            + escalation_score * 0.2
            + caps_score * 0.1
            + exclamation_score * 0.1
        )

        urgency_score: float = min(total_score, 1.0)

        # Determine urgency level
        if urgency_score >= 0.7:
            level = "high"
        elif urgency_score >= 0.4:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": urgency_score,
            "components": {
                "urgency_keywords": urgency_matches,
                "time_patterns": time_score,
                "escalation_keywords": escalation_score,
                "caps_ratio": caps_ratio,
                "exclamation_marks": message.count("!"),
            },
        }

    def _detect_complaint(self, message: str) -> bool:
        """
        Detect if the message is a complaint.

        Args:
            message: Input message text

        Returns:
            True if message appears to be a complaint
        """
        words: set[str] = set(message.lower().split())
        complaint_matches: int = len(words.intersection(self.complaint_keywords))

        # Also check for negative sentiment indicators in combination with issues
        negative_indicators: set[str] = {
            "terrible", "awful", "horrible", "worst", "hate",
            "angry", "frustrated", "disappointed", "unacceptable"
        }
        negative_matches: int = len(words.intersection(negative_indicators))

        return complaint_matches > 0 or negative_matches >= 2

    def _extract_keywords(self, message: str) -> Dict[str, List[str]]:
        """
        Extract detected keywords for debugging/analysis.

        Args:
            message: Input message text

        Returns:
            Dictionary of detected keywords by category
        """
        words: set[str] = set(message.lower().split())

        detected: Dict[str, List[str]] = {
            "urgency": list(words.intersection(self.urgency_keywords)),
            "complaint": list(words.intersection(self.complaint_keywords)),
            "escalation": list(words.intersection(self.escalation_keywords)),
        }

        # Only return categories with detected keywords
        return {k: v for k, v in detected.items() if v}


# Factory function for creating the actor
def create_sentiment_analyzer(nats_url: str = "nats://localhost:4222") -> SentimentAnalyzer:
    """Create a SentimentAnalyzer actor instance."""
    return SentimentAnalyzer(nats_url)


# Main execution for standalone testing
async def main() -> None:
    """Main function for testing the sentiment analyzer."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    analyzer: SentimentAnalyzer = SentimentAnalyzer()

    try:
        await analyzer.start()
        print("Sentiment Analyzer started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await analyzer.stop()


if __name__ == "__main__":
    asyncio.run(main())
