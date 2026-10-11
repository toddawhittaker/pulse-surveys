"""A comment card's flag is typed by the closed held-note type — E6-09, done-when 14.

> `CommentFlag` becomes `HeldNoteType | None`.

E6-03 made `HeldNoteType` (`app.ai.contracts`) the closed vocabulary of a held
comment's class — harmful or privacy, nothing else. The card's `flag` member says
the same thing about the same comments, so it is typed by that one type rather
than by a second spelling of its members that can drift from it (`docs/MISTAKES.md`
entry 13: two places answering one question).

**A schema check, not a wire check.** On the wire a `Literal` of the two tokens
and the enum serialize identically, so a payload test cannot tell them apart;
what this asserts is the declaration the ticket names.

**Which failure a red is, before E6-09 lands.** `CommentFlag`'s members are not
`{HeldNoteType, None}`: the equality fails naming what it is.
"""

import typing
from importlib import import_module
from typing import Any

import pytest

REPORT_SCHEMA_MODULE = "app.schemas.report"
CONTRACTS_MODULE = "app.ai.contracts"
COMMENT_FLAG = "CommentFlag"
HELD_NOTE_TYPE = "HeldNoteType"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Importing the schema reaches `app.*` (`docs/MISTAKES.md` entry 40)."""


def named(module_name: str, name: str) -> Any:
    found = getattr(import_module(module_name), name, None)
    if found is None:
        pytest.fail(f"`{module_name}` exposes no `{name}`; E6-09 done-when 14 names it there.")
    return found


def test_comment_flag_is_the_held_note_type_or_none() -> None:
    """`CommentFlag`'s members are exactly `HeldNoteType` and `None`.

    **The mutation this kills:** `CommentFlag` left as its own `Literal` of the
    two tokens (or any type other than the contract's enum), so a third held-note
    class added to `HeldNoteType` would not reach the card. **The near miss:**
    `HeldNoteType` without `None` — a card for a comment with no flag has to say so.
    """
    flag = named(REPORT_SCHEMA_MODULE, COMMENT_FLAG)
    held_note_type = named(CONTRACTS_MODULE, HELD_NOTE_TYPE)
    declared = getattr(flag, "__value__", flag)
    members = set(typing.get_args(declared))
    assert members == {held_note_type, type(None)}, (
        f"`{COMMENT_FLAG}` is {declared!r}, whose members are {members}; E6-09 done-when 14 makes "
        f"it `{HELD_NOTE_TYPE} | None`, the closed type E6-03 put in `{CONTRACTS_MODULE}`."
    )
