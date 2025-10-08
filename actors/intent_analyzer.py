"""
Intent Analyzer Actor for the Actor Mesh Demo.

This actor analyzes customer message intent and extracts entities using LLM,
providing structured understanding of customer requests for routing decisions.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import litellm
from models.message import MessagePayload

from actors.base import ProcessorActor


class IntentAnalyzer(ProcessorActor):
    """
    Processor actor that analyzes intent and extracts entities from customer messages.

    Uses LLM (via LiteLLM) to understand customer intent and extract relevant entities
    like order numbers, product names, dates, etc.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo"):
        """Initialize the Intent Analyzer actor."""
        super().__init__("intent_analyzer", nats_url)

        self.model = model
        self.max_retries = 2
        self.timeout = 30.0

        # Predefined intent categories for e-commerce support
        self.intent_categories = {
            "order_inquiry": "Customer asking about order status, tracking, or details",
            "delivery_issue": "Problems with delivery timing, address, or carrier",
            "product_complaint": "Issues with product quality, defects, or functionality",
            "billing_question": "Questions about charges, refunds, or payment",
            "return_request": "Customer wants to return or exchange products",
            "cancellation_request": "Customer wants to cancel an order",
            "account_issue": "Problems with customer account, login, or profile",
            "general_inquiry": "General questions about policies, services, or company",
            "compliment": "Positive feedback or praise",
            "escalation_request": "Customer wants to speak to manager or supervisor",
        }

        # Entity types to extract
        self.entity_types = [
            "order_number",
            "tracking_number",
            "product_name",
            "date",
            "amount",
            "email_address",
            "phone_number",
            "address",
            "payment_method",
        ]

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Analyze intent and extract entities from the customer message.

        Args:
            payload: Message payload containing customer message

        Returns:
            Dictionary with intent analysis results
        """
        try:
            message = payload.customer_message

            # First try LLM analysis
            llm_result = await self._analyze_with_llm(message)

            if llm_result:
                # Enhance with rule-based extraction as backup
                rule_entities = self._extract_entities_rule_based(message)

                # Merge entities (LLM takes priority, rule-based fills gaps)
                merged_entities = self._merge_entities(llm_result.get("entities", {}), rule_entities)

                result = {
                    "intent": llm_result.get("intent", {}),
                    "entities": merged_entities,
                    "confidence": llm_result.get("confidence", 0.0),
                    "analysis_method": "llm_enhanced",
                    "model_used": self.model,
                    "processed_at": asyncio.get_event_loop().time(),
                }

                self.logger.info(
                    f"Intent analysis completed: {result['intent'].get('category', 'unknown')} "
                    f"(confidence: {result['confidence']:.2f})"
                )

                return result
            else:
                # Fallback to rule-based analysis
                return await self._analyze_with_rules(message)

        except Exception as e:
            self.logger.error(f"Error in intent analysis: {e}")

            # Return fallback analysis
            return {
                "intent": {
                    "category": "general_inquiry",
                    "description": "Unable to determine specific intent",
                    "confidence": 0.1,
                },
                "entities": self._extract_entities_rule_based(payload.customer_message),
                "confidence": 0.1,
                "analysis_method": "fallback",
                "error": str(e),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with intent analysis results."""
        payload.intent = result

    async def _analyze_with_llm(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Analyze message using LLM for intent and entity extraction.

        Args:
            message: Customer message text

        Returns:
            Analysis result or None if LLM analysis fails
        """
        try:
            # Create structured prompt for intent analysis
            prompt = self._create_analysis_prompt(message)

            # Call LLM
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,  # Low temperature for consistent analysis
                    max_tokens=500,
                ),
                timeout=self.timeout,
            )

            # Extract and parse response
            content = response.choices[0].message.content

            # Try to parse JSON response
            try:
                parsed_result = json.loads(content)
                return self._validate_llm_response(parsed_result)
            except json.JSONDecodeError:
                # If not JSON, try to extract structured info
                return self._parse_text_response(content)

        except asyncio.TimeoutError:
            self.logger.warning("LLM request timed out")
            return None
        except Exception as e:
            self.logger.warning(f"LLM analysis failed: {e}")
            return None

    def _create_analysis_prompt(self, message: str) -> str:
        """Create structured prompt for LLM intent analysis."""
        intent_list = "\n".join([f"- {cat}: {desc}" for cat, desc in self.intent_categories.items()])
        entity_list = "\n".join([f"- {entity}" for entity in self.entity_types])

        prompt = f"""
Analyze the following customer support message and provide a structured response:

Customer Message: "{message}"

Please analyze this message and respond with a JSON object containing:

1. Intent Analysis:
   - category: One of these predefined categories
{intent_list}
   - description: Brief explanation of what the customer wants
   - confidence: Float between 0.0-1.0 indicating confidence in classification

2. Entity Extraction:
   - Extract any of these entity types found in the message:
{entity_list}
   - For each entity found, provide: {{"type": "entity_type", "value": "extracted_value", "confidence": 0.0-1.0}}

3. Overall confidence score (0.0-1.0)

Response format:
{{
  "intent": {{
    "category": "intent_category",
    "description": "what customer wants",
    "confidence": 0.85
  }},
  "entities": [
    {{"type": "order_number", "value": "ORD-12345", "confidence": 0.9}},
    {{"type": "product_name", "value": "wireless headphones", "confidence": 0.8}}
  ],
  "confidence": 0.8
}}

Focus on accuracy and only extract entities you're confident about.
"""
        return prompt

    def _validate_llm_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and clean up LLM response."""
        # Ensure required fields exist
        if "intent" not in response:
            return None

        intent = response["intent"]
        if "category" not in intent or intent["category"] not in self.intent_categories:
            # Try to map to closest category
            category = self._map_to_valid_category(intent.get("category", ""))
            intent["category"] = category

        # Validate confidence scores
        if "confidence" not in intent or not (0 <= intent["confidence"] <= 1):
            intent["confidence"] = 0.5

        # Clean up entities
        entities = response.get("entities", [])
        cleaned_entities = []

        for entity in entities:
            if isinstance(entity, dict) and "type" in entity and "value" in entity:
                if entity["type"] in self.entity_types:
                    # Ensure confidence is valid
                    if "confidence" not in entity or not (0 <= entity["confidence"] <= 1):
                        entity["confidence"] = 0.7
                    cleaned_entities.append(entity)

        response["entities"] = cleaned_entities

        # Validate overall confidence
        if "confidence" not in response or not (0 <= response["confidence"] <= 1):
            response["confidence"] = 0.6

        return response

    def _map_to_valid_category(self, category: str) -> str:
        """Map invalid category to closest valid one."""
        category_lower = category.lower()

        # Simple keyword mapping
        mappings = {
            "order": "order_inquiry",
            "delivery": "delivery_issue",
            "shipping": "delivery_issue",
            "product": "product_complaint",
            "defect": "product_complaint",
            "broken": "product_complaint",
            "return": "return_request",
            "refund": "return_request",
            "cancel": "cancellation_request",
            "billing": "billing_question",
            "payment": "billing_question",
            "account": "account_issue",
            "login": "account_issue",
            "manager": "escalation_request",
            "supervisor": "escalation_request",
            "compliment": "compliment",
            "thank": "compliment",
        }

        for keyword, intent_cat in mappings.items():
            if keyword in category_lower:
                return intent_cat

        return "general_inquiry"

    def _parse_text_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse non-JSON text response from LLM."""
        # Try to extract intent and entities from text
        result = {
            "intent": {"category": "general_inquiry", "description": "", "confidence": 0.5},
            "entities": [],
            "confidence": 0.5,
        }

        # Look for intent category mentions
        content_lower = content.lower()
        for category in self.intent_categories.keys():
            if category.replace("_", " ") in content_lower:
                result["intent"]["category"] = category
                break

        # Try to extract order numbers, tracking numbers, etc.
        entities = self._extract_entities_rule_based(content)
        result["entities"] = [
            {"type": ent_type, "value": value, "confidence": 0.7}
            for ent_type, values in entities.items()
            for value in values
        ]

        return result

    async def _analyze_with_rules(self, message: str) -> Dict[str, Any]:
        """Fallback rule-based intent analysis."""
        message_lower = message.lower()

        # Intent classification based on keywords
        intent_category = "general_inquiry"
        confidence = 0.3

        # Check for specific intents
        if any(word in message_lower for word in ["order", "tracking", "status", "shipped"]):
            intent_category = "order_inquiry"
            confidence = 0.7
        elif any(word in message_lower for word in ["delivery", "deliver", "shipping", "carrier"]):
            intent_category = "delivery_issue"
            confidence = 0.7
        elif any(word in message_lower for word in ["broken", "defective", "damaged", "wrong"]):
            intent_category = "product_complaint"
            confidence = 0.7
        elif any(word in message_lower for word in ["return", "exchange", "send back"]):
            intent_category = "return_request"
            confidence = 0.7
        elif any(word in message_lower for word in ["cancel", "cancellation"]):
            intent_category = "cancellation_request"
            confidence = 0.7
        elif any(word in message_lower for word in ["refund", "money back", "charge", "billing"]):
            intent_category = "billing_question"
            confidence = 0.7
        elif any(word in message_lower for word in ["manager", "supervisor", "escalate"]):
            intent_category = "escalation_request"
            confidence = 0.8
        elif any(word in message_lower for word in ["thank", "great", "excellent", "love"]):
            intent_category = "compliment"
            confidence = 0.6

        # Extract entities
        entities = self._extract_entities_rule_based(message)
        entity_list = [
            {"type": ent_type, "value": value, "confidence": 0.8}
            for ent_type, values in entities.items()
            for value in values
        ]

        return {
            "intent": {
                "category": intent_category,
                "description": self.intent_categories[intent_category],
                "confidence": confidence,
            },
            "entities": entity_list,
            "confidence": confidence,
            "analysis_method": "rule_based",
        }

    def _extract_entities_rule_based(self, message: str) -> Dict[str, List[str]]:
        """Extract entities using regex patterns."""
        entities = {}

        # Order numbers (ORD-XXXXXXXX, #12345, etc.)
        order_patterns = [r"ORD-[A-Z0-9]{6,10}", r"order\s*#?(\d{6,10})", r"#(\d{6,10})"]
        order_numbers = []
        for pattern in order_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            order_numbers.extend(matches)
        if order_numbers:
            entities["order_number"] = list(set(order_numbers))

        # Tracking numbers (TRK followed by alphanumeric)
        tracking_pattern = r"TRK[A-Z0-9]{6,12}"
        tracking_numbers = re.findall(tracking_pattern, message, re.IGNORECASE)
        if tracking_numbers:
            entities["tracking_number"] = list(set(tracking_numbers))

        # Email addresses
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        emails = re.findall(email_pattern, message)
        if emails:
            entities["email_address"] = list(set(emails))

        # Phone numbers (various formats)
        phone_patterns = [
            r"\b\d{3}-\d{3}-\d{4}\b",
            r"\(\d{3}\)\s*\d{3}-\d{4}",
            r"\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",
        ]
        phone_numbers = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, message)
            phone_numbers.extend(matches)
        if phone_numbers:
            entities["phone_number"] = list(set(phone_numbers))

        # Monetary amounts
        amount_pattern = r"\$\d+\.?\d*"
        amounts = re.findall(amount_pattern, message)
        if amounts:
            entities["amount"] = list(set(amounts))

        # Dates (MM/DD/YYYY, MM-DD-YYYY, etc.)
        date_patterns = [r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", r"\d{4}-\d{2}-\d{2}"]
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, message)
            dates.extend(matches)
        if dates:
            entities["date"] = list(set(dates))

        return entities

    def _merge_entities(self, llm_entities: List[Dict], rule_entities: Dict[str, List[str]]) -> List[Dict]:
        """Merge LLM and rule-based entity extraction results."""
        merged = list(llm_entities)  # Start with LLM results

        # Convert rule entities to standard format
        llm_values = {(e["type"], e["value"].lower()) for e in llm_entities}

        # Add rule-based entities that weren't found by LLM
        for entity_type, values in rule_entities.items():
            for value in values:
                if (entity_type, value.lower()) not in llm_values:
                    merged.append({"type": entity_type, "value": value, "confidence": 0.8, "source": "rule_based"})

        return merged


# Factory function for creating the actor
def create_intent_analyzer(nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo") -> IntentAnalyzer:
    """Create an IntentAnalyzer actor instance."""
    return IntentAnalyzer(nats_url, model)


# Main execution for standalone testing
async def main():
    """Main function for testing the intent analyzer."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    analyzer = IntentAnalyzer()

    try:
        await analyzer.start()
        print("Intent Analyzer started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await analyzer.stop()


if __name__ == "__main__":
    asyncio.run(main())
