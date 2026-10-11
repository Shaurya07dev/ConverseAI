from typing import Dict, Type
from pydantic import BaseModel, Field, create_model
import logging

logger = logging.getLogger(__name__)

# Default standard models for fallback
class HealthcareExtraction(BaseModel):
    symptoms: list[str] = Field(default=[], description="List of recognized symptoms.")
    diagnosis: str | None = Field(default=None, description="The stated diagnosis or differential diagnoses.")
    treatment_plan: str | None = Field(default=None, description="Prescribed treatments, drugs, and dosages.")
    followup_instructions: str | None = Field(default=None, description="What the patient should do next.")

class FinanceExtraction(BaseModel):
    intent: str | None = Field(default=None, description="The core intent of the call (e.g. loan inquiry, payment issue).")
    amount: str | None = Field(default=None, description="Any financial amounts mentioned.")
    resolution: str | None = Field(default=None, description="The resolution or expected outcome of the call.")
    urgency: str | None = Field(default="medium", description="Urgency of the call (low, medium, high).")

class DomainConfigManager:
    """
    Manages schemas and system prompts for different domains like Healthcare or Finance.
    Provides Pydantic models to feed into the LangGraph Structured Extractor Node.
    """
    def __init__(self):
        # Standard fallback map
        self._schema_map: Dict[str, Type[BaseModel]] = {
            "healthcare": HealthcareExtraction,
            "finance": FinanceExtraction
        }

    def get_structured_schema(self, domain: str) -> Type[BaseModel]:
        """Returns the Pydantic schema class for a given domain string."""
        domain_key = domain.lower().strip()
        if domain_key in self._schema_map:
            return self._schema_map[domain_key]
        
        logger.warning(f"Domain '{domain}' schema not found. Defaulting to empty fallback.")
        return create_model("FallbackExtraction", raw_data=(str, Field(default="", description="Miscellaneous unstructured extracted data.")))

domain_manager = DomainConfigManager()
