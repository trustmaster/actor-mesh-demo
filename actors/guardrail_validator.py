"""
Guardrail Validator Actor for the Actor Mesh Demo.

This actor validates generated responses for safety, policy compliance,
and appropriateness before they are sent to customers.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import litellm
from models.message import MessagePayload

from actors.base import ProcessorActor


class GuardrailValidator(ProcessorActor):
    """
    Processor actor that validates responses against safety and policy guardrails.

    Checks generated responses for:
    - Inappropriate content
    - Policy violations
    - Unauthorized promises
    - PII exposure
    - Professional tone
    """

    def __init__(self, nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo"):
        """Initialize the Guardrail Validator actor."""
        super().__init__("guardrail_validator", nats_url)

        self.model = model
        self.timeout = 20.0
        self.use_llm_validation = True

        # Rule-based guardrails
        self.forbidden_words = {
            "profanity": ["damn", "hell", "crap", "stupid", "idiot"],
            "legal_terms": ["sue", "lawsuit", "lawyer", "legal action", "court"],
            "inappropriate": ["hate", "kill", "die", "murder"],
        }

        self.unauthorized_promises = [
            "guarantee",
            "promise",
            "definitely will",
            "for sure",
            "100% certain",
            "absolutely will",
        ]

        self.pii_patterns = [
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
            r"\b\d{16}\b",  # Credit card
            r"\b\d{4}\s\d{4}\s\d{4}\s\d{4}\b",  # Credit card with spaces
            r"\b[A-Z]{2}\d{7}\b",  # Driver's license (basic pattern)
        ]

        # Company policies
        self.company_policies = {
            "return_period": 30,
            "max_refund_amount": 1000.00,
            "warranty_period": 365,
            "shipping_timeframe": "3-7 business days",
            "escalation_threshold": "supervisor discretion",
        }

        # Tone requirements
        self.required_tone_elements = {
            "politeness": ["please", "thank you", "appreciate", "understand"],
            "empathy": ["sorry", "apologize", "understand", "concern"],
            "professionalism": ["assist", "help", "resolve", "support"],
        }

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Validate the generated response against guardrails.

        Args:
            payload: Message payload with generated response

        Returns:
            Dictionary with validation results and any corrections
        """
        try:
            # Get the generated response
            response_text = payload.response
            if not response_text:
                return {
                    "validation_status": "failed",
                    "issues": [{"type": "missing_response", "message": "No response text to validate"}],
                    "approved": False,
                }

            # Perform validation checks
            validation_results = await self._validate_response(response_text, payload)

            # Determine if response is approved
            critical_issues = [issue for issue in validation_results["issues"] if issue.get("severity") == "critical"]

            validation_results["approved"] = len(critical_issues) == 0
            validation_results["needs_human_review"] = any(
                issue.get("severity") == "high" for issue in validation_results["issues"]
            )

            if not validation_results["approved"]:
                self.logger.warning(f"Response failed validation with {len(critical_issues)} critical issues")
            else:
                self.logger.info("Response passed all guardrail checks")

            return validation_results

        except Exception as e:
            self.logger.error(f"Error in guardrail validation: {e}")
            return {
                "validation_status": "error",
                "issues": [{"type": "validation_error", "message": str(e), "severity": "high"}],
                "approved": False,
                "error": str(e),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with guardrail validation results."""
        payload.guardrail_check = result

        # If response was corrected, update it
        if result.get("corrected_response"):
            payload.response = result["corrected_response"]

    async def _validate_response(self, response_text: str, payload: MessagePayload) -> Dict[str, Any]:
        """
        Perform comprehensive response validation.

        Args:
            response_text: The generated response text
            payload: Original message payload for context

        Returns:
            Validation results with issues and corrections
        """
        issues = []
        validation_status = "passed"

        # Rule-based checks
        rule_issues = self._check_rule_based_guardrails(response_text)
        issues.extend(rule_issues)

        # Content policy checks
        policy_issues = self._check_policy_compliance(response_text, payload)
        issues.extend(policy_issues)

        # Tone and professionalism checks
        tone_issues = self._check_tone_appropriateness(response_text, payload)
        issues.extend(tone_issues)

        # LLM-based validation if available
        if self.use_llm_validation:
            llm_issues = await self._check_with_llm(response_text, payload)
            if llm_issues:
                issues.extend(llm_issues)

        # Determine overall status
        if any(issue.get("severity") == "critical" for issue in issues):
            validation_status = "failed"
        elif any(issue.get("severity") == "high" for issue in issues):
            validation_status = "warning"

        # Try to generate corrected response if there are issues
        corrected_response = None
        if issues and validation_status in ["failed", "warning"]:
            corrected_response = await self._generate_corrected_response(response_text, issues, payload)

        return {
            "validation_status": validation_status,
            "issues": issues,
            "corrected_response": corrected_response,
            "validation_method": "comprehensive",
            "validated_at": asyncio.get_event_loop().time(),
        }

    def _check_rule_based_guardrails(self, response_text: str) -> List[Dict[str, Any]]:
        """Check basic rule-based guardrails."""
        issues = []
        response_lower = response_text.lower()

        # Check for forbidden words
        for category, words in self.forbidden_words.items():
            for word in words:
                if word in response_lower:
                    issues.append(
                        {
                            "type": "forbidden_content",
                            "category": category,
                            "message": f"Contains inappropriate {category}: '{word}'",
                            "severity": "critical",
                            "location": response_text.find(word),
                        }
                    )

        # Check for unauthorized promises
        for promise in self.unauthorized_promises:
            if promise.lower() in response_lower:
                issues.append(
                    {
                        "type": "unauthorized_promise",
                        "message": f"Contains unauthorized promise: '{promise}'",
                        "severity": "high",
                        "suggestion": "Use conditional language like 'we'll do our best' or 'we aim to'",
                    }
                )

        # Check for PII exposure
        for pattern in self.pii_patterns:
            matches = re.findall(pattern, response_text)
            if matches:
                issues.append(
                    {
                        "type": "pii_exposure",
                        "message": f"Potential PII detected: {len(matches)} instances",
                        "severity": "critical",
                        "matches": matches,
                    }
                )

        # Check response length
        if len(response_text) < 10:
            issues.append(
                {
                    "type": "insufficient_content",
                    "message": "Response is too short",
                    "severity": "medium",
                }
            )
        elif len(response_text) > 1000:
            issues.append(
                {
                    "type": "excessive_length",
                    "message": "Response is too long",
                    "severity": "low",
                }
            )

        return issues

    def _check_policy_compliance(self, response_text: str, payload: MessagePayload) -> List[Dict[str, Any]]:
        """Check compliance with company policies."""
        issues = []
        response_lower = response_text.lower()

        # Check for policy violations

        # Return period mentions
        return_period_pattern = r"(\d+)\s*day[s]?\s*return"
        matches = re.findall(return_period_pattern, response_lower)
        for match in matches:
            days = int(match)
            if days > self.company_policies["return_period"]:
                issues.append(
                    {
                        "type": "policy_violation",
                        "policy": "return_period",
                        "message": f"Mentions {days}-day return period, policy is {self.company_policies['return_period']} days",
                        "severity": "high",
                    }
                )

        # Refund amount mentions
        refund_pattern = r"\$(\d+(?:,\d+)*(?:\.\d{2})?)"
        matches = re.findall(refund_pattern, response_text)
        for match in matches:
            amount = float(match.replace(",", ""))
            if amount > self.company_policies["max_refund_amount"]:
                issues.append(
                    {
                        "type": "policy_violation",
                        "policy": "max_refund_amount",
                        "message": f"Mentions ${amount} refund, exceeds policy limit of ${self.company_policies['max_refund_amount']}",
                        "severity": "high",
                    }
                )

        # Shipping timeframe accuracy
        shipping_keywords = ["shipping", "delivery", "arrive", "receive"]
        if any(keyword in response_lower for keyword in shipping_keywords):
            # Look for specific timeframes that might conflict with policy
            timeframe_patterns = [
                r"(\d+)\s*day[s]?\s*(?:delivery|shipping)",
                r"(?:within|in)\s*(\d+)\s*day[s]?",
                r"next\s*day",
                r"overnight",
                r"same\s*day",
            ]

            for pattern in timeframe_patterns:
                if re.search(pattern, response_lower):
                    if "next day" in response_lower or "overnight" in response_lower or "same day" in response_lower:
                        issues.append(
                            {
                                "type": "policy_violation",
                                "policy": "shipping_timeframe",
                                "message": "Promises expedited shipping not guaranteed by policy",
                                "severity": "medium",
                            }
                        )

        return issues

    def _check_tone_appropriateness(self, response_text: str, payload: MessagePayload) -> List[Dict[str, Any]]:
        """Check if response maintains appropriate professional tone."""
        issues = []
        response_lower = response_text.lower()

        # Check for required tone elements
        tone_scores = {}
        for tone_type, keywords in self.required_tone_elements.items():
            matches = sum(1 for keyword in keywords if keyword in response_lower)
            tone_scores[tone_type] = matches

        # Validate minimum professionalism
        if tone_scores["professionalism"] == 0:
            issues.append(
                {
                    "type": "tone_issue",
                    "category": "professionalism",
                    "message": "Response lacks professional language",
                    "severity": "medium",
                    "suggestion": "Include words like 'assist', 'help', 'resolve', or 'support'",
                }
            )

        # Check for empathy in complaint scenarios
        if hasattr(payload, "sentiment") and payload.sentiment:
            is_complaint = payload.sentiment.get("is_complaint", False)
            sentiment_label = payload.sentiment.get("sentiment", {}).get("label", "neutral")

            if (is_complaint or sentiment_label == "negative") and tone_scores["empathy"] == 0:
                issues.append(
                    {
                        "type": "tone_issue",
                        "category": "empathy",
                        "message": "Response lacks empathy for customer complaint",
                        "severity": "high",
                        "suggestion": "Include apologetic or understanding language",
                    }
                )

        # Check for overly casual tone
        casual_indicators = ["yeah", "yep", "nah", "gonna", "wanna", "ok", "ur", "u"]
        casual_count = sum(1 for indicator in casual_indicators if indicator in response_lower)

        if casual_count > 0:
            issues.append(
                {
                    "type": "tone_issue",
                    "category": "formality",
                    "message": f"Response contains {casual_count} casual expressions",
                    "severity": "low",
                    "suggestion": "Use more formal language",
                }
            )

        # Check for excessive enthusiasm
        exclamation_count = response_text.count("!")
        if exclamation_count > 3:
            issues.append(
                {
                    "type": "tone_issue",
                    "category": "enthusiasm",
                    "message": f"Response contains {exclamation_count} exclamation marks",
                    "severity": "low",
                    "suggestion": "Reduce enthusiasm to maintain professionalism",
                }
            )

        return issues

    async def _check_with_llm(self, response_text: str, payload: MessagePayload) -> List[Dict[str, Any]]:
        """Use LLM to check for subtle policy violations and tone issues."""
        try:
            prompt = self._create_validation_prompt(response_text, payload)

            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Low temperature for consistent validation
                    max_tokens=300,
                ),
                timeout=self.timeout,
            )

            content = response.choices[0].message.content

            # Try to parse JSON response
            try:
                validation_result = json.loads(content)
                return self._process_llm_validation(validation_result)
            except json.JSONDecodeError:
                # Parse text response
                return self._parse_llm_text_validation(content)

        except Exception as e:
            self.logger.warning(f"LLM validation failed: {e}")
            return []

    def _create_validation_prompt(self, response_text: str, payload: MessagePayload) -> str:
        """Create prompt for LLM validation."""

        # Get context
        customer_message = payload.customer_message
        sentiment = getattr(payload, "sentiment", {})
        intent = getattr(payload, "intent", {})

        prompt = f"""
Review this customer service response for policy violations, tone issues, and appropriateness:

Customer Message: "{customer_message}"
Agent Response: "{response_text}"

Context:
- Customer Sentiment: {sentiment.get("sentiment", {}).get("label", "unknown")}
- Is Complaint: {sentiment.get("is_complaint", False)}
- Intent Category: {intent.get("intent", {}).get("category", "unknown")}

Check for:
1. Inappropriate promises or guarantees
2. Policy violations (returns, refunds, shipping)
3. Unprofessional tone or language
4. Missing empathy for complaints
5. Overly casual or formal language
6. Any concerning content

Respond with JSON:
{{
  "issues": [
    {{
      "type": "issue_type",
      "message": "Description of issue",
      "severity": "low|medium|high|critical",
      "suggestion": "How to fix"
    }}
  ],
  "overall_assessment": "safe|concerning|inappropriate",
  "confidence": 0.0-1.0
}}

Focus on customer service appropriateness and policy compliance.
"""
        return prompt

    def _process_llm_validation(self, validation_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process LLM validation results."""
        issues = []

        llm_issues = validation_result.get("issues", [])
        for issue in llm_issues:
            if isinstance(issue, dict) and "type" in issue:
                # Ensure severity is valid
                severity = issue.get("severity", "medium")
                if severity not in ["low", "medium", "high", "critical"]:
                    severity = "medium"

                processed_issue = {
                    "type": issue.get("type", "llm_validation"),
                    "message": issue.get("message", "LLM identified an issue"),
                    "severity": severity,
                    "source": "llm_validation",
                }

                if "suggestion" in issue:
                    processed_issue["suggestion"] = issue["suggestion"]

                issues.append(processed_issue)

        return issues

    def _parse_llm_text_validation(self, content: str) -> List[Dict[str, Any]]:
        """Parse non-JSON LLM validation response."""
        issues = []

        # Look for concerning indicators in text
        content_lower = content.lower()

        if "inappropriate" in content_lower or "concerning" in content_lower:
            issues.append(
                {
                    "type": "llm_validation",
                    "message": "LLM flagged response as potentially inappropriate",
                    "severity": "high",
                    "source": "llm_validation",
                }
            )
        elif "issue" in content_lower or "problem" in content_lower:
            issues.append(
                {
                    "type": "llm_validation",
                    "message": "LLM identified potential issues",
                    "severity": "medium",
                    "source": "llm_validation",
                }
            )

        return issues

    async def _generate_corrected_response(
        self, original_response: str, issues: List[Dict[str, Any]], payload: MessagePayload
    ) -> Optional[str]:
        """Generate a corrected version of the response."""
        try:
            # Only attempt correction for non-critical issues
            critical_issues = [issue for issue in issues if issue.get("severity") == "critical"]
            if critical_issues:
                return None

            # Create correction prompt
            issue_descriptions = []
            for issue in issues:
                issue_desc = f"- {issue.get('message', 'Unknown issue')}"
                if issue.get("suggestion"):
                    issue_desc += f" (Suggestion: {issue['suggestion']})"
                issue_descriptions.append(issue_desc)

            prompt = f"""
The following customer service response has some issues that need to be corrected:

Original Response: "{original_response}"

Issues to fix:
{chr(10).join(issue_descriptions)}

Please provide a corrected version that:
1. Maintains the same helpful intent and core message
2. Fixes all identified issues
3. Maintains professional customer service tone
4. Stays within company policies
5. Keeps similar length and structure

Respond with only the corrected response text, no explanation.
"""

            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500,
                ),
                timeout=self.timeout,
            )

            corrected_text = response.choices[0].message.content.strip()

            # Basic validation of corrected response
            if len(corrected_text) > 10 and len(corrected_text) < 1000:
                self.logger.info("Generated corrected response")
                return corrected_text
            else:
                return None

        except Exception as e:
            self.logger.warning(f"Failed to generate corrected response: {e}")
            return None


# Factory function for creating the actor
def create_guardrail_validator(
    nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo"
) -> GuardrailValidator:
    """Create a GuardrailValidator actor instance."""
    return GuardrailValidator(nats_url, model)


# Main execution for standalone testing
async def main():
    """Main function for testing the guardrail validator."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    validator = GuardrailValidator()

    try:
        await validator.start()
        print("Guardrail Validator started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await validator.stop()


if __name__ == "__main__":
    asyncio.run(main())
