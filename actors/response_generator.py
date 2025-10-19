"""
Response Generator Actor for the Actor Mesh Demo.

This actor generates customer-facing responses using LLM based on the enriched
message context, intent analysis, and customer data.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import litellm
from models.message import MessagePayload

from actors.base import ProcessorActor


class ResponseGenerator(ProcessorActor):
    """
    Processor actor that generates customer responses using LLM.

    Takes enriched message payload with sentiment, intent, and context data
    and generates appropriate customer-facing responses.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo"):
        """Initialize the Response Generator actor."""
        super().__init__("response_generator", nats_url)

        self.model = model
        self.max_retries = 2
        self.timeout = 45.0

        # Response templates for different scenarios
        self.response_templates = {
            "order_inquiry": {
                "positive": "Thank you for your kind words! I appreciate your patience and I'm glad to help you with your order inquiry. Let me track that for you right away.",
                "neutral": "I can help you check on your order status.",
                "negative": "I understand you're concerned about your order, and I'm here to help resolve this.",
            },
            "delivery_issue": {
                "positive": "I appreciate you reaching out! I'm glad to help you track your delivery and resolve any issues.",
                "neutral": "Let me look into your delivery status for you.",
                "negative": "I sincerely apologize for the delivery issues you're experiencing. Let me fix this right away.",
            },
            "product_complaint": {
                "positive": "Thank you for contacting us! I appreciate your business and I'm glad to help with any product concerns you have.",
                "neutral": "I can assist you with your product issue.",
                "negative": "I'm very sorry about the problems with your product. This isn't the experience we want for our customers.",
            },
            "return_request": {
                "positive": "Thank you for being such a valued customer! I appreciate your business and I'm glad to help you with your return request.",
                "neutral": "I can process your return request for you.",
                "negative": "I understand you need to return this item, and I'll make sure we handle this smoothly for you.",
            },
            "billing_question": {
                "positive": "Thank you for reaching out! I appreciate your business and I'm glad to help clarify any billing questions you have.",
                "neutral": "I can help explain your billing details.",
                "negative": "I apologize for any confusion about your billing. Let me get this sorted out for you immediately.",
            },
            "escalation_request": {
                "positive": "Thank you for your feedback! I appreciate you giving us the opportunity to help, and I'm glad to arrange for you to speak with a supervisor.",
                "neutral": "I can connect you with a manager to discuss your concerns.",
                "negative": "I completely understand your frustration and will escalate this to a supervisor right away.",
            },
            "general_inquiry": {
                "positive": "Thank you for contacting us! I appreciate your business and I'm glad to help you with your inquiry.",
                "neutral": "I'm here to help you with your inquiry.",
                "negative": "I apologize for any inconvenience. Let me help resolve your concern right away.",
            },
        }

        # Company policies and information
        self.company_info = {
            "name": "TechMart",
            "return_policy": "30-day return policy for most items",
            "shipping_policy": "Free shipping on orders over $50",
            "contact_info": "Available 24/7 via chat, phone, or email",
            "warranty": "1-year manufacturer warranty on electronics",
        }

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Generate customer response based on enriched message data.

        Args:
            payload: Message payload with sentiment, intent, and context data

        Returns:
            Dictionary with generated response and metadata
        """
        try:
            # Extract analysis data
            sentiment = payload.sentiment or {}
            intent = payload.intent or {}
            context = payload.context or {}

            # Generate response using LLM
            llm_response = await self._generate_with_llm(payload, sentiment, intent, context)

            if llm_response:
                response_result = {
                    "response_text": llm_response["text"],
                    "tone": llm_response.get("tone", "professional"),
                    "confidence": llm_response.get("confidence", 0.8),
                    "action_items": llm_response.get("action_items", []),
                    "escalation_needed": llm_response.get("escalation_needed", False),
                    "generation_method": "llm",
                    "model_used": self.model,
                    "generated_at": asyncio.get_event_loop().time(),
                }
            else:
                # Fallback to template-based response
                response_result = await self._generate_with_template(payload, sentiment, intent, context)

            self.logger.info(f"Generated response with {response_result['generation_method']} method")
            return response_result

        except Exception as e:
            self.logger.error(f"Error generating response: {e}")

            # Return fallback response
            return {
                "response_text": "Thank you for contacting us. We're looking into your request and will get back to you shortly.",
                "tone": "professional",
                "confidence": 0.3,
                "action_items": ["manual_review"],
                "escalation_needed": True,
                "generation_method": "fallback",
                "error": str(e),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with generated response."""
        payload.response = result["response_text"]

    async def _generate_with_llm(
        self, payload: MessagePayload, sentiment: Dict, intent: Dict, context: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Generate response using LLM.

        Args:
            payload: Original message payload
            sentiment: Sentiment analysis results
            intent: Intent analysis results
            context: Customer context data

        Returns:
            Generated response data or None if LLM fails
        """
        try:
            # Create comprehensive prompt
            prompt = self._create_response_prompt(payload, sentiment, intent, context)

            # Call LLM
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,  # Balanced creativity and consistency
                    max_tokens=800,
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
                # Extract text response
                return {"text": content.strip(), "confidence": 0.7}

        except asyncio.TimeoutError:
            self.logger.warning("LLM request timed out")
            return None
        except Exception as e:
            self.logger.warning(f"LLM response generation failed: {e}")
            return None

    def _create_response_prompt(self, payload: MessagePayload, sentiment: Dict, intent: Dict, context: Dict) -> str:
        """Create comprehensive prompt for response generation."""

        # Extract key information
        customer_message = payload.customer_message
        customer_email = payload.customer_email

        sentiment_label = sentiment.get("sentiment", {}).get("label", "neutral")
        urgency_level = sentiment.get("urgency", {}).get("level", "low")
        is_complaint = sentiment.get("is_complaint", False)

        intent_category = intent.get("intent", {}).get("category", "general_inquiry")
        entities = intent.get("entities", [])

        customer_context = context.get("customer_context", {})
        customer_summary = customer_context.get("summary", {})

        # Build context information
        context_info = []

        if customer_summary.get("customer_tier"):
            context_info.append(f"Customer Tier: {customer_summary['customer_tier']}")

        if customer_summary.get("total_orders"):
            context_info.append(f"Total Orders: {customer_summary['total_orders']}")

        if customer_summary.get("recent_complaints", 0) > 0:
            context_info.append(f"Recent Complaints: {customer_summary['recent_complaints']}")

        if customer_summary.get("risk_factors"):
            context_info.append(f"Risk Factors: {', '.join(customer_summary['risk_factors'])}")

        # Build entity information
        entity_info = []
        for entity in entities:
            if isinstance(entity, dict):
                entity_type = entity.get("type", "")
                entity_value = entity.get("value", "")
                entity_info.append(f"{entity_type}: {entity_value}")

        prompt = f"""
You are a professional customer service agent for {self.company_info["name"]}. Generate a helpful, empathetic response to the customer's message.

Customer Message: "{customer_message}"
Customer Email: {customer_email}

Analysis Results:
- Sentiment: {sentiment_label} (Urgency: {urgency_level})
- Intent Category: {intent_category}
- Is Complaint: {is_complaint}
- Extracted Entities: {", ".join(entity_info) if entity_info else "None"}

Customer Context:
{chr(10).join(["- " + info for info in context_info]) if context_info else "- No additional context available"}

Guidelines:
1. Match the tone to the customer's sentiment ({sentiment_label})
2. Address their specific intent ({intent_category})
3. Be more empathetic and apologetic for complaints
4. Use extracted entities (order numbers, etc.) when relevant
5. Consider customer tier and history in your response
6. Suggest specific next steps or actions
7. Escalate to human agent if needed for complex issues

Company Policies:
- Return Policy: {self.company_info["return_policy"]}
- Shipping: {self.company_info["shipping_policy"]}
- Warranty: {self.company_info["warranty"]}

Please respond with a JSON object containing:
{{
  "text": "Your professional customer service response",
  "tone": "professional|empathetic|apologetic|friendly",
  "confidence": 0.0-1.0,
  "action_items": ["specific_action_1", "specific_action_2"],
  "escalation_needed": true/false,
  "reasoning": "Brief explanation of your approach"
}}

Focus on being helpful, professional, and resolving the customer's issue effectively.
"""
        return prompt

    def _validate_llm_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean up LLM response."""
        # Ensure required fields
        if "text" not in response or not response["text"].strip():
            return None

        # Validate tone
        valid_tones = ["professional", "empathetic", "apologetic", "friendly"]
        if "tone" not in response or response["tone"] not in valid_tones:
            response["tone"] = "professional"

        # Validate confidence
        if "confidence" not in response or not (0 <= response.get("confidence", 0) <= 1):
            response["confidence"] = 0.8

        # Ensure action_items is a list
        if "action_items" not in response or not isinstance(response["action_items"], list):
            response["action_items"] = []

        # Ensure escalation_needed is boolean
        if "escalation_needed" not in response:
            response["escalation_needed"] = False

        return response

    async def _generate_with_template(
        self, payload: MessagePayload, sentiment: Dict, intent: Dict, context: Dict
    ) -> Dict[str, Any]:
        """
        Fallback template-based response generation.

        Args:
            payload: Original message payload
            sentiment: Sentiment analysis results
            intent: Intent analysis results
            context: Customer context data

        Returns:
            Template-based response data
        """
        # Determine response template
        intent_category = intent.get("intent", {}).get("category", "general_inquiry")
        sentiment_label = sentiment.get("sentiment", {}).get("label", "neutral")

        # Get base template - default to general_inquiry if intent not found
        templates = self.response_templates.get(intent_category, self.response_templates["general_inquiry"])
        template_text = templates.get(sentiment_label, templates.get("neutral", "Thank you for contacting us. We're here to help!"))

        # Customize based on context
        customer_summary = context.get("customer_context", {}).get("summary", {})
        customer_tier = customer_summary.get("customer_tier", "standard")

        # Enhance for VIP customers
        if customer_tier == "vip":
            template_text = f"As one of our valued VIP customers, {template_text.lower()}"
        elif customer_tier == "premium":
            template_text = f"As a premium customer, {template_text.lower()}"

        # Add specific actions based on intent
        action_items = self._determine_action_items(intent_category, sentiment, context)

        # Determine if escalation is needed
        urgency_level = sentiment.get("urgency", {}).get("level", "low")
        recent_complaints = customer_summary.get("recent_complaints", 0)
        escalation_needed = (
            urgency_level == "high"
            or recent_complaints > 2
            or intent_category == "escalation_request"
            or sentiment.get("is_complaint", False)
            and sentiment_label == "negative"
        )

        return {
            "response_text": template_text,
            "tone": self._determine_tone(sentiment_label, intent_category),
            "confidence": 0.6,
            "action_items": action_items,
            "escalation_needed": escalation_needed,
            "generation_method": "template",
        }

    def _determine_action_items(self, intent_category: str, sentiment: Dict, context: Dict) -> List[str]:
        """Determine appropriate action items based on intent and context."""
        actions = []

        if intent_category == "order_inquiry":
            actions.extend(["check_order_status", "provide_tracking_info"])
        elif intent_category == "delivery_issue":
            actions.extend(["track_package", "contact_carrier", "expedite_if_needed"])
        elif intent_category == "product_complaint":
            actions.extend(["investigate_product_issue", "offer_replacement_or_refund"])
        elif intent_category == "return_request":
            actions.extend(["generate_return_label", "process_return"])
        elif intent_category == "billing_question":
            actions.extend(["review_billing_details", "explain_charges"])
        elif intent_category == "cancellation_request":
            actions.extend(["check_cancellation_eligibility", "process_cancellation"])
        elif intent_category == "escalation_request":
            actions.extend(["escalate_to_supervisor", "schedule_callback"])

        # Add urgency-based actions
        urgency_level = sentiment.get("urgency", {}).get("level", "low")
        if urgency_level == "high":
            actions.insert(0, "prioritize_request")

        # Add context-based actions
        customer_context = context.get("customer_context", {})
        risk_factors = customer_context.get("summary", {}).get("risk_factors", [])

        if "multiple_recent_complaints" in risk_factors:
            actions.append("review_customer_history")

        if "delivery_issues" in risk_factors:
            actions.append("check_delivery_patterns")

        return actions

    def _determine_tone(self, sentiment_label: str, intent_category: str) -> str:
        """Determine appropriate response tone."""
        if sentiment_label == "negative" or intent_category in ["product_complaint", "delivery_issue"]:
            return "empathetic"
        elif intent_category == "escalation_request":
            return "apologetic"
        elif sentiment_label == "positive":
            return "friendly"
        else:
            return "professional"


# Factory function for creating the actor
def create_response_generator(
    nats_url: str = "nats://localhost:4222", model: str = "gpt-3.5-turbo"
) -> ResponseGenerator:
    """Create a ResponseGenerator actor instance."""
    return ResponseGenerator(nats_url, model)


# Main execution for standalone testing
async def main():
    """Main function for testing the response generator."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    generator = ResponseGenerator()

    try:
        await generator.start()
        print("Response Generator started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await generator.stop()


if __name__ == "__main__":
    asyncio.run(main())
