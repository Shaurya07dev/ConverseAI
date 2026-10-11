"""
VaakSetu AI Core — LLM-Based Field Extractor

Instead of regex heuristics, this module uses the chat LLM itself
to extract structured field values from natural conversation text.

Handles:
  • Multi-field extraction ("I'm Ramesh, 45 years old, male")
  • Null/unknown detection ("Pata nahi", "I don't know")
  • Vague/partial values that need follow-up
  • Code-mixed Hinglish/Kannada inputs
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ai_core.llm import chat_model, strip_reasoning

logger = logging.getLogger(__name__)


class FieldExtractor:
    """
    LLM-powered field extraction engine.

    Given a user message and a list of required fields, uses the LLM
    to identify which fields the user has provided values for.
    """

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        """Lazy-initialize the LLM for extraction."""
        if self._llm is None:
            self._llm = chat_model(temperature=0.1)  # low temp for consistent extraction
        return self._llm

    async def extract_fields(
        self,
        user_message: str,
        required_fields: list[str],
        already_collected: dict[str, Any],
        conversation_context: str = "",
    ) -> dict[str, Any]:
        """
        Extract field values from a user message using LLM.

        Args:
            user_message: The latest user input
            required_fields: List of field names to look for
            already_collected: Fields already collected (to avoid re-extraction)
            conversation_context: Recent conversation for context

        Returns:
            Dict of newly extracted field → value pairs.
            Values can be strings or "__NULL__" for explicitly unknown answers.
        """
        missing_fields = [f for f in required_fields if f not in already_collected]

        if not missing_fields:
            return {}

        extraction_prompt = f"""You are a precise data extraction engine. Your job is to extract structured field values from a user's conversational message.

The user may speak in Hindi, English, Hinglish (mixed), Kannada, or any Indian language. Extract the values regardless of language.

FIELDS TO EXTRACT (only extract these):
{json.dumps(missing_fields, indent=2)}

USER MESSAGE: "{user_message}"

RECENT CONVERSATION CONTEXT:
{conversation_context[-500:] if conversation_context else "No prior context."}

RULES:
1. Only extract fields that the user CLEARLY provides in this message.
2. If the user says "I don't know", "pata nahi", "nahi pata", or similar for a field, set its value to "__NULL__".
3. If a field is not mentioned at all, DO NOT include it in the output.
4. Return ONLY valid JSON with field names as keys and extracted values as strings.
5. Keep values concise and clean (e.g., "Ramesh Kumar" not "mera naam Ramesh Kumar hai").
6. For numeric fields like age, extract just the number as a string.

RESPOND WITH ONLY A JSON OBJECT. No explanation, no markdown, no code blocks.
Example: {{"patient_name": "Ramesh Kumar", "age": "45", "gender": "male"}}
If nothing is extractable, return: {{}}"""

        try:
            from langchain_core.messages import HumanMessage

            llm = self._get_llm()
            response = await asyncio.to_thread(
                llm.invoke,
                [HumanMessage(content=extraction_prompt)]
            )

            content = response.content.strip()

            content = strip_reasoning(content)

            # Strip markdown code blocks if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            if content.startswith("{") and content.endswith("}"):
                extracted = json.loads(content)
            else:
                # Try to find JSON in the response
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    extracted = json.loads(content[start:end])
                else:
                    logger.warning(f"No JSON found in extraction response: {content[:100]}")
                    extracted = {}

            # Filter to only valid fields
            valid_extracted = {}
            for field, value in extracted.items():
                if field in missing_fields and value:
                    valid_extracted[field] = value

            if valid_extracted:
                logger.info(f"Extracted fields: {list(valid_extracted.keys())}")
                return valid_extracted

            heuristic = self._heuristic_extract_fields(user_message, missing_fields)
            if heuristic:
                logger.info(f"Heuristic fallback extracted fields: {list(heuristic.keys())}")
            return heuristic

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error in extraction: {e}")
            return self._heuristic_extract_fields(user_message, missing_fields)
        except Exception as e:
            logger.warning(f"Field extraction failed: {e}. Returning empty.")
            return self._heuristic_extract_fields(user_message, missing_fields)

    def _heuristic_extract_fields(
        self,
        user_message: str,
        missing_fields: list[str],
    ) -> dict[str, Any]:
        text = user_message.strip()
        lower = text.lower()
        extracted: dict[str, Any] = {}

        duration_match = re.search(
            r"\bfor\s+([a-z0-9 -]+?\s(?:hours?|days?|weeks?|months?|years?))\b",
            lower,
        )
        duration_value = duration_match.group(1).strip() if duration_match else None

        symptom_match = re.search(
            r"\b(?:have|having|had|suffering from|experiencing)\s+([a-z0-9 ,/-]+?)(?:\s+for\s+[a-z0-9 -]+?\s(?:hours?|days?|weeks?|months?|years?)|[.!?,]|$)",
            lower,
        )
        symptom_value = symptom_match.group(1).strip(" ,.-") if symptom_match else None

        med_match = re.search(
            r"\b(?:taking|on)\s+([a-z0-9 ,/-]+?)(?:\s+(?:right now|currently|today)|[.!?,]|$)",
            lower,
        )
        name_match = re.search(
            r"\b(?:my name is|i am|i'm)\s+([a-z]+(?:\s+[a-z]+){0,3})\b",
            lower,
        )
        age_match = re.search(r"\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|yo\b)?", lower)
        budget_match = re.search(r"\b(?:rs\.?|inr|\$)\s*([0-9][0-9,]*)\b", lower)
        timeline_match = re.search(
            r"\b(?:within|in|after)\s+([a-z0-9 -]+?\s(?:days?|weeks?|months?|years?))\b",
            lower,
        )
        interest_match = re.search(r"\binterested in\s+([a-z0-9 ,/-]+?)(?:[.!?,]|$)", lower)

        for field in missing_fields:
            field_lower = field.lower()

            if field_lower.endswith("name") and name_match:
                extracted[field] = name_match.group(1).strip().title()
            elif "age" in field_lower and age_match:
                extracted[field] = age_match.group(1)
            elif "gender" in field_lower or field_lower.endswith("sex"):
                if "female" in lower or "woman" in lower:
                    extracted[field] = "female"
                elif "male" in lower or "man" in lower:
                    extracted[field] = "male"
            elif "symptom" in field_lower or "complaint" in field_lower:
                if symptom_value:
                    extracted[field] = symptom_value
            elif "duration" in field_lower or "timeline" == field_lower:
                if duration_value:
                    extracted[field] = duration_value
            elif "medication" in field_lower or "medicine" in field_lower:
                if any(phrase in lower for phrase in [
                    "not taking any medication",
                    "not taking medication",
                    "no medication",
                    "no medicines",
                    "not on any medication",
                ]):
                    extracted[field] = "__NULL__"
                elif med_match:
                    extracted[field] = med_match.group(1).strip(" ,.-")
            elif "history" in field_lower:
                if "first time" in lower:
                    extracted[field] = "first time"
                elif "before" in lower or "previous" in lower or "history" in lower:
                    extracted[field] = text
            elif "budget" in field_lower and budget_match:
                extracted[field] = budget_match.group(1).replace(",", "")
            elif "timeline" in field_lower and timeline_match:
                extracted[field] = timeline_match.group(1).strip()
            elif "interest" in field_lower and interest_match:
                extracted[field] = interest_match.group(1).strip(" ,.-")

        return extracted
