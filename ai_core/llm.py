"""
VaakSetu AI Core — Chat LLM factory

Every chat-LLM call in the project goes through here, so switching
provider/model is an .env change (LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY).
"""

import re

from ai_core.config import (
    LLM_PROVIDER,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_API_KEY,
    LLM_TEMPERATURE,
)


def _check_provider() -> None:
    if LLM_PROVIDER != "openai":
        raise ValueError(
            f"LLM_PROVIDER={LLM_PROVIDER!r} is not supported; use 'openai' (any OpenAI-compatible endpoint)"
        )


def chat_model(temperature: float = LLM_TEMPERATURE, max_tokens: int = 1024):
    """LangChain chat model for the configured endpoint."""
    _check_provider()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
    )


def chat_client():
    """Raw async OpenAI client for the configured endpoint."""
    _check_provider()
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def strip_reasoning(text: str) -> str:
    """Drop <think>...</think> blocks that reasoning models prepend to answers."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
