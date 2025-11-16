"""Unit tests for the LLM client helpers."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_client import parse_json_from_content


def test_parse_json_from_content_plain_payload() -> None:
    payload = '{"city": "Austin"}'

    result = parse_json_from_content(payload)

    assert result == {"city": "Austin"}


def test_parse_json_from_content_code_fence_payload() -> None:
    payload = """```json
{
  \"city\": \"Austin\"
}
```"""

    result = parse_json_from_content(payload)

    assert result == {"city": "Austin"}


def test_parse_json_from_content_invalid_payload() -> None:
    with pytest.raises(ValueError):
        parse_json_from_content("no json here")
