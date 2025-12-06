#!/usr/bin/env python3
"""
Simple ML-based Sentiment Analyzer Actor for the E-commerce Support Agent

This actor performs sentiment analysis, urgency detection, and complaint classification
using VADER Sentiment Analysis - a lightweight, CPU-based ML approach that works
reliably across all platforms including Apple Silicon.

VADER (Valence Aware Dictionary and sEntiment Reasoner) is specifically attuned to
sentiments expressed in social media and works well for customer support messages.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    print("⚠️  vaderSentiment not installed. Run: pip install vaderSentiment")

from actors.base import BaseActor
from models.message import MessagePayload


class SentimentAnalyzer(BaseActor):
    """
    Lightweight ML-based sentiment analyzer using VADER.

    This analyzer uses VADER (Valence Aware Dictionary and sEntiment Reasoner),
    a lexicon and rule-based sentiment analysis tool that is specifically attuned
    to sentiments expressed in social media and customer messages.

    VADER advantages:
    - No GPU required (CPU-only)
    - Fast processing (~1-2ms per message)
    - Low memory footprint (~10MB)
    - No model loading time
    - Works on all platforms including Apple Silicon
    - Good accuracy for social media/customer support text
    """

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        """Initialize the Simple ML Sentiment Analyzer actor."""
        super().__init__("sentiment_analyzer", nats_url)

        # Initialize VADER analyzer
        if VADER_AVAILABLE:
            self.vader = SentimentIntensityAnalyzer()
            self.ml_available = True
        else:
            self.vader = None
            self.ml_available = False
            self.logger.warning("VADER not available. Install with: pip install vaderSentiment")

        # Urgency indicators
        self.urgency_keywords: Set[str] = {
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
            "expired",
            "last",
            "final",
            "closing",
            "ending",
            "limited",
            "running out",
            "yesterday",
            "overdue",
            "late",
            "delayed",
            "missing",
        }

        # Complaint indicators
        self.complaint_keywords: Set[str] = {
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
            "exchange",
            "replacement",
            "fix",
            "repair",
            "resolve",
            "solution",
            "manager",
            "supervisor",
            "order",
            "upset",
            "frustrated",
            "annoyed",
            "disappointed",
            "angry",
            "furious",
            "unacceptable",
            "terrible",
            "awful",
            "horrible",
        }

        # Escalation triggers
        self.escalation_keywords: Set[str] = {
            "manager",
            "supervisor",
            "escalate",
            "lawyer",
            "legal",
            "sue",
            "court",
            "attorney",
            "corporate",
            "headquarters",
            "ceo",
            "president",
            "director",
            "complaint",
            "report",
            "review",
            "rating",
            "terrible",
            "worst",
            "never",
            "again",
            "boycott",
            "social",
            "media",
            "twitter",
            "facebook",
            "instagram",
            "news",
            "press",
            "public",
        }

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """Process message for sentiment analysis."""
        try:
            self.logger.info(f"Processing sentiment analysis for customer: {payload.customer_email}")

            # Extract message content
            content = payload.customer_message if payload.customer_message else ""

            # Perform analysis
            sentiment_result = self._analyze_sentiment(content)
            urgency_result = self._analyze_urgency(content)
            complaint_result = self._analyze_complaint(content)
            escalation_result = self._analyze_escalation(content)

            # Create analysis result
            analysis_result: Dict[str, Any] = {
                "sentiment": sentiment_result,
                "urgency": urgency_result,
                "is_complaint": complaint_result["is_complaint"],
                "escalation_needed": escalation_result["escalation_needed"],
                "keywords_detected": {
                    "sentiment_keywords": sentiment_result.get("keywords", []),
                    "urgency_keywords": urgency_result.get("keywords", []),
                    "complaint_keywords": complaint_result.get("keywords", []),
                    "escalation_keywords": escalation_result.get("keywords", []),
                },
                "analysis_method": "vader_ml" if self.ml_available else "rule_based_fallback",
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "model_info": {
                    "analyzer_type": "vader_sentiment",
                    "version": "1.0.0",
                    "ml_engine": "VADER" if self.ml_available else "fallback",
                    "device": "cpu",
                    "compatible_with": "all_platforms",
                },
            }

            self.logger.info(
                f"Sentiment analysis completed: {sentiment_result.get('label', 'neutral')} "
                f"(confidence: {sentiment_result.get('confidence', 0.0):.2f}, "
                f"urgency: {urgency_result.get('level', 'low')})"
            )

            return analysis_result

        except Exception as e:
            self.logger.error(f"Error in sentiment analysis: {e}")
            # Return minimal analysis to prevent pipeline breakage
            return {
                "sentiment": {"label": "neutral", "confidence": 0.0},
                "urgency": {"level": "low", "score": 0.0},
                "is_complaint": False,
                "escalation_needed": False,
                "analysis_method": "error_fallback",
                "error": str(e),
            }

    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment using VADER.

        VADER returns a dictionary with scores:
        - compound: normalized, weighted composite score (-1 to +1)
        - pos: positive sentiment score (0 to 1)
        - neg: negative sentiment score (0 to 1)
        - neu: neutral sentiment score (0 to 1)
        """
        if not self.ml_available or not self.vader:
            return self._fallback_sentiment_analysis(text)

        try:
            # Get VADER scores
            scores = self.vader.polarity_scores(text)

            # Extract compound score (most useful single metric)
            compound = scores["compound"]
            pos_score = scores["pos"]
            neg_score = scores["neg"]
            neu_score = scores["neu"]

            # Determine sentiment label using VADER's recommended thresholds
            if compound >= 0.05:
                label = "positive"
                confidence = min(compound, 1.0)  # compound is already 0-1 for positive
            elif compound <= -0.05:
                label = "negative"
                confidence = min(abs(compound), 1.0)  # absolute value for confidence
            else:
                label = "neutral"
                confidence = neu_score

            # Extract keywords (words that likely contributed to sentiment)
            keywords = self._extract_sentiment_keywords(text, label)

            return {
                "label": label,
                "confidence": confidence,
                "score": compound,
                "scores": {"compound": compound, "positive": pos_score, "negative": neg_score, "neutral": neu_score},
                "keywords": keywords,
            }

        except Exception as e:
            self.logger.error(f"VADER analysis failed: {e}, falling back to rule-based")
            return self._fallback_sentiment_analysis(text)

    def _fallback_sentiment_analysis(self, text: str) -> Dict[str, Any]:
        """Simple fallback sentiment analysis if VADER is not available."""
        positive_words = {"good", "great", "excellent", "amazing", "love", "happy", "pleased", "thank"}
        negative_words = {"bad", "terrible", "horrible", "awful", "hate", "angry", "frustrated", "upset"}

        words = set(text.lower().split())
        pos_count = len(words & positive_words)
        neg_count = len(words & negative_words)

        if pos_count > neg_count:
            label = "positive"
            confidence = min(pos_count / max(len(words), 1), 1.0)
        elif neg_count > pos_count:
            label = "negative"
            confidence = min(neg_count / max(len(words), 1), 1.0)
        else:
            label = "neutral"
            confidence = 0.5

        return {
            "label": label,
            "confidence": confidence,
            "score": (pos_count - neg_count) / max(len(words), 1),
            "keywords": [],
        }

    def _extract_sentiment_keywords(self, text: str, sentiment_label: str) -> List[str]:
        """Extract words that likely contributed to the sentiment."""
        positive_indicators = {
            "good",
            "great",
            "excellent",
            "amazing",
            "awesome",
            "fantastic",
            "wonderful",
            "perfect",
            "love",
            "like",
            "happy",
            "pleased",
            "satisfied",
            "delighted",
            "thrilled",
            "appreciate",
            "thank",
        }

        negative_indicators = {
            "bad",
            "terrible",
            "horrible",
            "awful",
            "worst",
            "hate",
            "angry",
            "frustrated",
            "annoyed",
            "disappointed",
            "upset",
            "broken",
            "failed",
            "error",
            "problem",
            "issue",
            "wrong",
            "useless",
        }

        words = re.findall(r"\b\w+\b", text.lower())
        keywords = []

        if sentiment_label == "positive":
            keywords = [w for w in words if w in positive_indicators]
        elif sentiment_label == "negative":
            keywords = [w for w in words if w in negative_indicators]

        return keywords[:10]  # Limit to 10 keywords

    def _analyze_urgency(self, text: str) -> Dict[str, Any]:
        """Analyze urgency using keyword matching and pattern detection."""
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        urgency_score = 0
        found_keywords = []

        # Check for urgency keywords
        for word in words:
            if word in self.urgency_keywords:
                urgency_score += 1
                found_keywords.append(word)

        # Check for urgency patterns
        urgency_patterns = [
            r"\b(today|tonight|this\s+week)\b",
            r"\b(expires?|expire)\s+(today|tomorrow|soon)\b",
            r"\b(need|want|require).{0,20}(immediately|asap|urgently)\b",
            r"\b(time\s+sensitive|time-sensitive)\b",
            r"\b(deadline|due\s+date)\b",
            r"\b(supposed\s+to\s+(arrive|come|be\s+here))\s+(yesterday|today)\b",
            r"\b(should\s+have\s+(arrived|come|been\s+here))\b",
        ]

        for pattern in urgency_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                urgency_score += 2

        # Determine urgency level
        if urgency_score >= 3:
            level = "high"
        elif urgency_score >= 1:
            level = "medium"
        else:
            level = "low"

        return {"level": level, "score": urgency_score, "keywords": found_keywords}

    def _analyze_complaint(self, text: str) -> Dict[str, Any]:
        """Analyze if message is a complaint."""
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        complaint_score = 0
        found_keywords = []

        # Check for explicit complaint patterns (higher weight)
        complaint_patterns = [
            r"\b(i\s+want\s+to\s+complain|file\s+a\s+complaint)\b",
            r"\b(this\s+is\s+(terrible|awful|horrible))\b",
            r"\b(not\s+satisfied|unsatisfied|disappointed)\b",
            r"\b(want\s+(refund|money\s+back|return))\b",
            r"\b(something\s+is\s+wrong|there\s+is\s+a\s+problem)\b",
            r"\b(very\s+(frustrated|angry|upset))\b",
        ]

        for pattern in complaint_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                complaint_score += 3

        # Check for positive context that should reduce complaint threshold
        positive_patterns = [
            r"\b(thank\s+you|thanks|grateful|appreciate)\b",
            r"\b(excellent|wonderful|great|amazing|fantastic)\b",
            r"\b(happy|pleased|satisfied|love)\b",
        ]

        has_positive_context = any(re.search(p, text_lower, re.IGNORECASE) for p in positive_patterns)

        # Check individual complaint keywords
        for word in words:
            if word in self.complaint_keywords:
                complaint_score += 1
                found_keywords.append(word)

        # Adjust threshold based on context
        threshold = 4 if has_positive_context else 2
        is_complaint = complaint_score >= threshold

        return {"is_complaint": is_complaint, "score": complaint_score, "keywords": found_keywords}

    def _analyze_escalation(self, text: str) -> Dict[str, Any]:
        """Analyze if escalation is needed."""
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        escalation_score = 0
        found_keywords = []

        # Check for escalation keywords
        for word in words:
            if word in self.escalation_keywords:
                escalation_score += 1
                found_keywords.append(word)

        # Check for escalation patterns
        escalation_patterns = [
            r"\b(speak\s+to\s+(your\s+)?(manager|supervisor))\b",
            r"\b(this\s+is\s+unacceptable)\b",
            r"\b(i\s+will\s+(sue|report|review))\b",
            r"\b(terrible\s+service|worst\s+experience)\b",
        ]

        for pattern in escalation_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                escalation_score += 3

        escalation_needed = escalation_score >= 3

        return {"escalation_needed": escalation_needed, "score": escalation_score, "keywords": found_keywords}

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with sentiment analysis results."""
        payload.sentiment = result

    async def start(self) -> None:
        """Start the sentiment analyzer actor."""
        ml_status = "VADER ML" if self.ml_available else "Rule-based fallback"
        self.logger.info(f"Starting Simple ML Sentiment Analyzer ({ml_status})")
        await super().start()

    async def stop(self) -> None:
        """Stop the sentiment analyzer actor."""
        self.logger.info("Stopping Simple ML Sentiment Analyzer")
        await super().stop()


def create_sentiment_analyzer(nats_url: str = "nats://localhost:4222") -> SentimentAnalyzer:
    """Create and return a SentimentAnalyzer instance."""
    return SentimentAnalyzer(nats_url)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simple ML Sentiment Analyzer Actor")
    parser.add_argument("--nats-url", default="nats://localhost:4222", help="NATS server URL")
    args = parser.parse_args()

    analyzer = SentimentAnalyzer(args.nats_url)

    async def run_actor():
        await analyzer.start()
        try:
            # Keep the actor running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await analyzer.stop()

    try:
        asyncio.run(run_actor())
    except KeyboardInterrupt:
        pass
