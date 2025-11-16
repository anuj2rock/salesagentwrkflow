"""Application settings for the weather agent POC."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    llm_provider: Literal["huggingface", "disabled"] = Field(
        default="huggingface",
        description="Which LLM backend to use. Set to 'disabled' to force rule-based fallbacks.",
    )
    hf_token: str | None = Field(
        default=None, description="Hugging Face API token used for chat completions."
    )
    llm_model_interpreter: str = Field(
        default="CohereLabs/aya-expanse-32b:cohere",
        description="Model name for prompt interpretation.",
    )
    llm_model_narrative: str = Field(
        default="CohereLabs/aya-expanse-32b:cohere",
        description="Model name for narrative generation.",
    )
    llm_timeout_seconds: float = Field(default=30.0)
    llm_max_retries: int = Field(default=3, ge=1, le=6)

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()

