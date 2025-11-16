"""Lightweight client for calling third-party LLM APIs."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

import httpx

from ..config import Settings, get_settings


logger = logging.getLogger(__name__)


class LLMClient:
    """Encapsulates chat-completions calls to the configured provider."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return (
            self._settings.llm_provider == "huggingface"
            and bool(self._settings.hf_token)
        )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Invoke the configured provider and return the decoded JSON response."""

        if not self.is_configured:
            raise RuntimeError("LLM provider is disabled or missing configuration")

        headers = {
            "Authorization": f"Bearer {self._settings.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }

        backoff = 1.0
        last_error: Exception | None = None
        for attempt in range(self._settings.llm_max_retries):
            try:
                logger.info(
                    "calling Hugging Face router",
                    extra={"model": model, "attempt": attempt + 1},
                )
                async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
                    response = await client.post(
                        "https://router.huggingface.co/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json()
                if not data.get("choices"):
                    raise ValueError("LLM response missing choices")
                logger.info(
                    "LLM call succeeded",
                    extra={
                        "model": model,
                        "attempt": attempt + 1,
                        "prompt_tokens": data.get("usage", {}).get("prompt_tokens"),
                        "completion_tokens": data.get("usage", {}).get("completion_tokens"),
                    },
                )
                return data
            except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - network dependent
                last_error = exc
                logger.warning(
                    "LLM call failed",
                    extra={"model": model, "attempt": attempt + 1},
                    exc_info=True,
                )
                # Retry on transient errors
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {
                    408,
                    429,
                    500,
                    502,
                    503,
                }:
                    break
                if attempt == self._settings.llm_max_retries - 1:
                    break
                await asyncio.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"LLM call failed: {last_error}")


def extract_message_content(response: Dict[str, Any]) -> str:
    """Return the assistant message text from a Hugging Face response."""

    choice = response["choices"][0]
    message = choice.get("message")
    if not message:
        raise ValueError("LLM response missing message")
    content = message.get("content")
    if not content:
        raise ValueError("LLM response missing content")
    if isinstance(content, list):
        # router may return structured segments; concatenate into a string
        return "".join(part.get("text", "") for part in content)
    return str(content)


def parse_json_from_content(content: str) -> Dict[str, Any]:
    """Parse JSON content emitted by the model and raise on errors."""

    def _strip_code_fences(text: str) -> str:
        trimmed = text.strip()
        if trimmed.startswith("````"):
            return trimmed  # malformed fence; fall back to generic parsing
        if trimmed.startswith("```") and trimmed.endswith("```"):
            inner = trimmed[3:-3].strip()
            if "\n" in inner:
                first_line, rest = inner.split("\n", 1)
                if "{" not in first_line and "[" not in first_line:
                    inner = rest
            trimmed = inner.strip()
        elif trimmed.startswith("`") and trimmed.endswith("`"):
            trimmed = trimmed[1:-1].strip()
        return trimmed

    def _extract_first_json_blob(text: str) -> str:
        start_idx: int | None = None
        stack: List[str] = []
        in_string = False
        escape = False

        pairs = {"{": "}", "[": "]"}

        for idx, char in enumerate(text):
            if start_idx is None:
                if char in pairs:
                    start_idx = idx
                    stack.append(pairs[char])
                continue

            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue

            if char in pairs:
                stack.append(pairs[char])
                continue

            if char in ("}", "]"):
                if not stack:
                    break
                expected = stack.pop()
                if char != expected:
                    break
                if not stack and start_idx is not None:
                    return text[start_idx : idx + 1]

        raise ValueError("Model response was not valid JSON")

    stripped = _strip_code_fences(content)
    try:
        json_blob = _extract_first_json_blob(stripped)
        return json.loads(json_blob)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on model output
        raise ValueError("Model response was not valid JSON") from exc

