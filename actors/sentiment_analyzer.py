#!/usr/bin/env python3
"""
Sentiment Analyzer Actor for the E-commerce Support Agent

This actor performs sentiment analysis, urgency detection, and complaint classification
using a rule-based approach for maximum compatibility and stability across all platforms.

This is the default implementation that works reliably without heavy ML dependencies.
For ML-based analysis, see sentiment_analyzer_ml.py.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from actors.base import BaseActor
from models.message import MessagePayload


class SentimentAnalyzer(BaseActor):
    """
    Rule-based sentiment analyzer for maximum compatibility.

    This analyzer uses lexicon-based approaches and pattern matching to provide
    sentiment analysis without requiring heavy ML dependencies.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        """Initialize the Simple Sentiment Analyzer actor."""
        super().__init__("sentiment_analyzer", nats_url)

        # Sentiment lexicons
        self.positive_words: Set[str] = {
            "good", "great", "excellent", "amazing", "awesome", "fantastic",
            "wonderful", "perfect", "love", "like", "happy", "pleased",
            "satisfied", "delighted", "thrilled", "glad", "appreciate",
            "thank", "thanks", "grateful", "helpful", "smooth", "easy",
            "fast", "quick", "efficient", "professional", "friendly",
            "polite", "courteous", "reliable", "trustworthy", "quality",
            "value", "recommend", "impressed", "outstanding", "superb",
            "brilliant", "marvelous", "terrific", "splendid", "nice"
        }

        self.negative_words: Set[str] = {
            "bad", "terrible", "horrible", "awful", "worst", "hate", "angry",
            "frustrated", "annoyed", "disappointed", "upset", "mad", "furious",
            "disgusted", "outraged", "appalled", "shocked", "disturbed",
            "concerned", "worried", "confused", "lost", "stuck", "broken",
            "failed", "error", "problem", "issue", "trouble", "difficulty",
            "slow", "delayed", "late", "wrong", "incorrect", "useless",
            "worthless", "waste", "money", "time", "poor", "cheap", "fake",
            "scam", "fraud", "lies", "lying", "dishonest", "rude", "unprofessional"
        }

        # Urgency indicators
        self.urgency_words: Set[str] = {
            "urgent", "emergency", "asap", "immediately", "now", "today",
            "critical", "important", "rush", "quick", "fast", "soon",
            "deadline", "time-sensitive", "expire", "expires", "expired",
            "last", "final", "closing", "ending", "limited", "running out"
        }

        # Complaint indicators
        self.complaint_words: Set[str] = {
            "complaint", "complain", "problem", "issue", "wrong", "error",
            "mistake", "broken", "defective", "damaged", "missing", "lost",
            "delayed", "late", "slow", "cancel", "refund", "return",
            "exchange", "replacement", "fix", "repair", "resolve", "solution",
            "help", "support", "service", "manager", "supervisor"
        }

        # Escalation triggers
        self.escalation_words: Set[str] = {
            "manager", "supervisor", "escalate", "lawyer", "legal", "sue",
            "court", "attorney", "corporate", "headquarters", "ceo", "president",
            "director", "complaint", "report", "review", "rating", "terrible",
            "worst", "never", "again", "boycott", "social", "media", "twitter",
            "facebook", "instagram", "news", "press", "public"
        }

        # Intensifiers
        self.intensifiers: Set[str] = {
            "very", "extremely", "really", "quite", "totally", "completely",
            "absolutely", "definitely", "certainly", "incredibly", "amazingly",
            "exceptionally", "remarkably", "particularly", "especially",
            "highly", "deeply", "truly", "genuinely", "seriously"
        }

        # Negation words
        self.negation_words: Set[str] = {
            "not", "no", "never", "nothing", "nobody", "nowhere", "neither",
            "nor", "none", "hardly", "scarcely", "barely", "seldom", "rarely",
            "without", "lack", "lacks", "lacking", "missing", "absent",
            "doesn't", "don't", "won't", "can't", "couldn't", "shouldn't",
            "wouldn't", "isn't", "aren't", "wasn't", "weren't", "haven't",
            "hasn't", "hadn't"
        }

    async def process(self, message_data: bytes) -> None:
        """Process message for sentiment analysis."""
        try:
            message = self._parse_message(message_data)
            self.logger.info(f"Processing sentiment analysis for message: {message.id}")

            # Extract message content
            content = message.payload.content.lower() if message.payload.content else ""

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
                    "escalation_keywords": escalation_result.get("keywords", [])
                },
                "analysis_method": "rule_based",
                "processed_at": datetime.utcnow().isoformat(),
                "model_info": {
                    "analyzer_type": "rule_based",
                    "version": "1.0.0",
                    "compatible_with": "all_platforms"
                }
            }

            # Enrich message payload
            await self._enrich_payload(message.payload, analysis_result)

            # Update route based on analysis
            self._update_route_based_on_analysis(message, analysis_result)

            self.logger.info(
                f"Sentiment analysis completed: {sentiment_result.get('label', 'neutral')} "
                f"(confidence: {sentiment_result.get('confidence', 0.0):.2f}, "
                f"urgency: {urgency_result.get('level', 'low')})"
            )

            # Forward to next step
            await self._route_message(message)

        except Exception as e:
            self.logger.error(f"Error in sentiment analysis: {e}")
            # Forward message with minimal analysis to prevent pipeline breakage
            try:
                message = self._parse_message(message_data)
                await self._enrich_payload(message.payload, {
                    "sentiment": {"label": "neutral", "confidence": 0.0},
                    "urgency": {"level": "low", "score": 0.0},
                    "is_complaint": False,
                    "escalation_needed": False,
                    "analysis_method": "error_fallback",
                    "error": str(e)
                })
                await self._route_message(message)
            except Exception as routing_error:
                self.logger.error(f"Failed to route message after error: {routing_error}")

    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using rule-based approach."""
        words = re.findall(r'\b\w+\b', text.lower())

        positive_score = 0
        negative_score = 0
        found_keywords = []

        # Process words with context
        for i, word in enumerate(words):
            # Check for negation in the previous 2 words
            negated = any(neg in words[max(0, i-2):i] for neg in self.negation_words)

            # Check for intensifiers in the previous 2 words
            intensified = any(intens in words[max(0, i-2):i] for intens in self.intensifiers)
            multiplier = 1.5 if intensified else 1.0

            if word in self.positive_words:
                score = multiplier
                if negated:
                    negative_score += score
                else:
                    positive_score += score
                found_keywords.append(word)

            elif word in self.negative_words:
                score = multiplier
                if negated:
                    positive_score += score
                else:
                    negative_score += score
                found_keywords.append(word)

        # Calculate final sentiment
        total_score = positive_score - negative_score
        total_words = len([w for w in words if w in self.positive_words or w in self.negative_words])

        if total_words == 0:
            return {
                "label": "neutral",
                "confidence": 0.0,
                "score": 0.0,
                "keywords": found_keywords
            }

        # Normalize confidence
        confidence = min(abs(total_score) / max(total_words, 1), 1.0)

        if total_score > 0.5:
            label = "positive"
        elif total_score < -0.5:
            label = "negative"
        else:
            label = "neutral"

        return {
            "label": label,
            "confidence": confidence,
            "score": total_score,
            "keywords": found_keywords
        }

    def _analyze_urgency(self, text: str) -> Dict[str, Any]:
        """Analyze urgency using rule-based approach."""
        words = re.findall(r'\b\w+\b', text.lower())

        urgency_score = 0
        found_keywords = []

        for word in words:
            if word in self.urgency_words:
                urgency_score += 1
                found_keywords.append(word)

        # Check for patterns indicating urgency
        urgency_patterns = [
            r'\b(today|tonight|this\s+week)\b',
            r'\b(expires?|expire)\s+(today|tomorrow|soon)\b',
            r'\b(need|want|require).{0,20}(immediately|asap|urgently)\b',
            r'\b(time\s+sensitive|time-sensitive)\b',
            r'\b(deadline|due\s+date)\b'
        ]

        for pattern in urgency_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                urgency_score += 2

        # Determine urgency level
        if urgency_score >= 3:
            level = "high"
        elif urgency_score >= 1:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "score": urgency_score,
            "keywords": found_keywords
        }

    def _analyze_complaint(self, text: str) -> Dict[str, Any]:
        """Analyze if message is a complaint."""
        words = re.findall(r'\b\w+\b', text.lower())

        complaint_score = 0
        found_keywords = []

        for word in words:
            if word in self.complaint_words:
                complaint_score += 1
                found_keywords.append(word)

        # Check for complaint patterns
        complaint_patterns = [
            r'\b(i\s+want\s+to\s+complain|file\s+a\s+complaint)\b',
            r'\b(this\s+is\s+(terrible|awful|horrible))\b',
            r'\b(not\s+satisfied|unsatisfied|disappointed)\b',
            r'\b(want\s+(refund|money\s+back|return))\b'
        ]

        for pattern in complaint_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                complaint_score += 2

        is_complaint = complaint_score >= 2

        return {
            "is_complaint": is_complaint,
            "score": complaint_score,
            "keywords": found_keywords
        }

    def _analyze_escalation(self, text: str) -> Dict[str, Any]:
        """Analyze if escalation is needed."""
        words = re.findall(r'\b\w+\b', text.lower())

        escalation_score = 0
        found_keywords = []

        for word in words:
            if word in self.escalation_words:
                escalation_score += 1
                found_keywords.append(word)

        # Check for escalation patterns
        escalation_patterns = [
            r'\b(speak\s+to\s+(your\s+)?(manager|supervisor))\b',
            r'\b(this\s+is\s+unacceptable)\b',
            r'\b(i\s+will\s+(sue|report|review))\b',
            r'\b(terrible\s+service|worst\s+experience)\b'
        ]

        for pattern in escalation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                escalation_score += 3

        escalation_needed = escalation_score >= 3

        return {
            "escalation_needed": escalation_needed,
            "score": escalation_score,
            "keywords": found_keywords
        }

    def _update_route_based_on_analysis(self, message, analysis: Dict[str, Any]) -> None:
        """Update message routing based on analysis results."""
        sentiment = analysis.get("sentiment", {})
        urgency = analysis.get("urgency", {})

        # Add escalation router for negative sentiment or high urgency
        if (sentiment.get("label") == "negative" and sentiment.get("confidence", 0) > 0.7) or \
           urgency.get("level") == "high" or \
           analysis.get("escalation_needed", False):

            if "escalation_router" not in message.route.steps:
                # Insert escalation router before response generation
                try:
                    response_idx = message.route.steps.index("response_generator")
                    message.route.steps.insert(response_idx, "escalation_router")
                except ValueError:
                    message.route.steps.append("escalation_router")

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with sentiment analysis results."""
        payload.sentiment = result

    async def start(self) -> None:
        """Start the sentiment analyzer actor."""
        self.logger.info("Starting Rule-based Sentiment Analyzer")
        await super().start()

    async def stop(self) -> None:
        """Stop the sentiment analyzer actor."""
        self.logger.info("Stopping Rule-based Sentiment Analyzer")
        await super().stop()


def create_sentiment_analyzer(nats_url: str = "nats://localhost:4222") -> SentimentAnalyzer:
    """Create and return a SentimentAnalyzer instance."""
    return SentimentAnalyzer(nats_url)


# Note: ML-based implementation available in sentiment_analyzer_ml.py

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rule-based Sentiment Analyzer Actor")
    parser.add_argument("--nats-url", default="nats://localhost:4222", help="NATS server URL")
    args = parser.parse_args()

    analyzer = SentimentAnalyzer(args.nats_url)

    try:
        asyncio.run(analyzer.start())
    except KeyboardInterrupt:
        asyncio.run(analyzer.stop())
