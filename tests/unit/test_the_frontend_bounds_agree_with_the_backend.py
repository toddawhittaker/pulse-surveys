"""The frontend's two text bounds agree with the backend's.

A reason for excluding a comment, and the instructor's response, are each bounded
twice: once by the backend (a column check and a request schema) and once by the
textarea that stops the user typing past it. The two are written in different
languages, so nothing but this test keeps them equal. A frontend limit above the
backend's lets a person write what the server will then refuse; one below it
quietly shortens what the server would accept.

Each constant is read from its source file rather than copied here, and the
patterns are checked against text that must and must not match, because a pattern
that matches nothing would read as "the bounds agree" while checking nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.loop import RESPONSE_TEXT_MAX
from app.models.report import REASON_BOUND

REPO = Path(__file__).resolve().parents[2]
COMMENT_CARD = REPO / "frontend/src/components/CommentCard.tsx"
INSTRUCTOR_RESPONSE = REPO / "frontend/src/components/InstructorResponse.tsx"
OPENAPI = REPO / "frontend/src/api/openapi.json"


def exported_number(source: str, name: str) -> int | None:
    """The integer an `export const NAME = <integer>;` line assigns, or None."""
    found = re.search(rf"^export const {re.escape(name)}\s*=\s*(\d+);", source, re.MULTILINE)
    return int(found.group(1)) if found else None


def test_the_reader_finds_a_constant_and_refuses_a_missing_one() -> None:
    assert exported_number("export const LIMIT = 12;\n", "LIMIT") == 12
    # Near misses: not exported, a different name, a non-integer value.
    assert exported_number("const LIMIT = 12;\n", "LIMIT") is None
    assert exported_number("export const LIMITS = 12;\n", "LIMIT") is None
    assert exported_number("export const LIMIT = twelve;\n", "LIMIT") is None


@pytest.mark.parametrize(
    ("path", "name", "backend"),
    [
        (COMMENT_CARD, "REASON_MAX_LENGTH", REASON_BOUND),
        (INSTRUCTOR_RESPONSE, "RESPONSE_MAX_LENGTH", RESPONSE_TEXT_MAX),
    ],
    ids=["exclusion reason", "response text"],
)
def test_the_textarea_bound_is_the_backends(path: Path, name: str, backend: int) -> None:
    frontend = exported_number(path.read_text(encoding="utf-8"), name)

    assert frontend is not None, f"{name} is not an exported integer constant in {path.name}"
    assert frontend == backend


def test_the_response_bound_is_also_what_the_generated_schema_says() -> None:
    import json

    schemas = json.loads(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]

    assert schemas["ResponseWrite"]["properties"]["text"]["maxLength"] == RESPONSE_TEXT_MAX
    assert schemas["DraftCheckRequest"]["properties"]["draft"]["maxLength"] == RESPONSE_TEXT_MAX
