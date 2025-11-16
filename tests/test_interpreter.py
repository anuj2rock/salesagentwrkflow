"""Unit tests for the rule-based prompt interpreter."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.interpreter import RuleBasedPromptInterpreter


def test_extract_location_ignores_timeframe_next_week() -> None:
    interpreter = RuleBasedPromptInterpreter()

    location = interpreter._extract_location("rain in Austin next week")

    assert location == "Austin"


def test_extract_location_ignores_timeframe_tomorrow() -> None:
    interpreter = RuleBasedPromptInterpreter()

    location = interpreter._extract_location("temp in Paris tomorrow")

    assert location == "Paris"


def test_extract_location_trims_duplicate_prepositions() -> None:
    interpreter = RuleBasedPromptInterpreter()

    location = interpreter._extract_location("forecast in in New York next week")

    assert location == "New York"
