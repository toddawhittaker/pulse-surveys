"""The comment card's three new members — E6-03, criterion 5.

Work order decision 6: `CommentView` (in `app.schemas.report`) gains **exactly**
`answer_id: UUID`, `flag: Literal["harmful", "privacy"] | None` and
`decided_by_you: bool`, and nothing else — no date, time, week, author or decider
(criterion 5; ADRs 0153 and 0162 name the channel a date on a card opens).

These are the schema's own declarations, asked of the classes. What a payload
actually carries is asserted over HTTP in
`tests/integration/test_the_report_payload_repeats_nothing_beyond_the_comment_service.py`;
this is the cheap line that names a widened or loosened declaration before any
world is built.

The week report's participation note this module once also asserted was dropped
by the owner's ruling 6 (a per-week held count beside a released comment's flag
pins that comment to its week, ADR 0153's channel). That the report carries no
such note is asserted in
`tests/integration/test_the_week_report_carries_no_held_count.py`.

**The flag is a closed set, and the tokens are written out** (`docs/MISTAKES.md`
entry 19) as ADR 0030 stores them, read from `tests/fixtures/moderation.py`: a
`flag` that could carry `threat` or `self_harm` is a card that tells an instructor
a Care-class comment exists.

**Which failure a red is, before E6-03 lands:** an assertion naming the missing
member — never an import error at collection (`docs/MISTAKES.md` entry 44).
"""

from importlib import import_module
from typing import Any
from uuid import UUID, uuid4

import pytest
from fixtures.moderation import CLEAR, HARMFUL, NONSENSE, PRIVACY, SELF_HARM, THREAT
from pydantic import TypeAdapter, ValidationError

SCHEMA_MODULE = "app.schemas.report"
COMMENT_VIEW = "CommentView"

# What E4-07 shipped on a card and E4-07's ceiling tolerates (`tests/fixtures/report_api.py`),
# and the three E6-03 adds.
E4_CARD_FIELDS = frozenset({"text", "status"})
E4_TOLERATED = frozenset({"stream"})
E6_03_CARD_FIELDS = frozenset({"answer_id", "flag", "decided_by_you"})


def schema_class(name: str) -> Any:
    module = import_module(SCHEMA_MODULE)
    found = getattr(module, name, None)
    if not isinstance(found, type):
        pytest.fail(
            f"`{SCHEMA_MODULE}` exposes no class `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}. E6-03's work "
            "order (decision 6) settles the name."
        )
    return found


def field_annotation(model: Any, name: str) -> Any:
    fields = getattr(model, "model_fields", {})
    if name not in fields:
        pytest.fail(f"`{model.__name__}` declares no `{name}`; it declares {sorted(fields)}.")
    return fields[name].annotation


def test_the_card_declares_the_three_new_members_and_nothing_else_new() -> None:
    """Criterion 5 at the declaration: E4's members, the three, and nothing beside them.

    **The mutations this kills:** any of the three left off; and a fourth member
    added "for the page" — a `decided_at`, a `decided_by`, a `week` — which is the
    leak criterion 5 exists to stop and which ADR 0153 names for the week.
    """
    declared = set(getattr(schema_class(COMMENT_VIEW), "model_fields", {}))
    missing = (E4_CARD_FIELDS | E6_03_CARD_FIELDS) - declared
    assert not missing, f"`{COMMENT_VIEW}` declares {sorted(declared)} and lacks {sorted(missing)}."
    beyond = declared - (E4_CARD_FIELDS | E4_TOLERATED | E6_03_CARD_FIELDS)
    assert not beyond, (
        f"`{COMMENT_VIEW}` declares {sorted(beyond)} beyond E4's card and E6-03's three members. "
        "Work order decision 6: the card gains exactly `answer_id`, `flag` and `decided_by_you` — no "
        "date, time, week, author or decider."
    )


def test_the_handle_is_a_uuid_and_decided_by_you_a_bool() -> None:
    """Decision 6's two plain types.

    **The mutations this kill:** `answer_id` typed as a string the route could fill
    with anything (a response id, a composite), and `decided_by_you` typed so it can
    carry the decider (`str | None`).
    """
    model = schema_class(COMMENT_VIEW)
    handle = TypeAdapter(field_annotation(model, "answer_id"))
    an_id = uuid4()
    assert handle.validate_python(an_id) == an_id
    with pytest.raises(ValidationError):
        handle.validate_python("not a uuid")
    assert field_annotation(model, "decided_by_you") is bool, (
        f"`decided_by_you` is annotated {field_annotation(model, 'decided_by_you')!r}; decision 6 "
        "settles `bool`, which can say whether the reader decided and cannot say who did."
    )
    assert isinstance(handle.validate_python(str(an_id)), UUID)


@pytest.mark.parametrize("token", [HARMFUL, PRIVACY])
def test_the_flag_takes_each_flagging_class(token: str) -> None:
    """Decision 6: `flag` is `harmful` or `privacy` — the classes that put a chip on a card.

    **The mutation this kills:** a flag type missing one of the two (a privacy
    comment rendered without its chip, which §5.2 shows the instructor above
    small-N).
    """
    flag = TypeAdapter(field_annotation(schema_class(COMMENT_VIEW), "flag"))
    assert flag.validate_python(token) == token
    assert flag.validate_python(None) is None, "`flag` refuses `None`, the unflagged card."


@pytest.mark.parametrize("token", [THREAT, SELF_HARM, CLEAR, NONSENSE, ""])
def test_the_flag_refuses_every_other_verdict(token: str) -> None:
    """Decision 6's closed set: no Care-class class, and no quiet one, can be carried.

    **The mutations this kill:** `flag: str | None` or `flag: ModerationVerdict |
    None` — either of which lets a card say `threat` or `self_harm` to an
    instructor, which SPEC §6.2 forbids in every instructor view; and a flag that
    carries `clear` or `nonsense` on every card, which is a category label on
    comments the AI did not flag.
    """
    flag = TypeAdapter(field_annotation(schema_class(COMMENT_VIEW), "flag"))
    with pytest.raises(ValidationError):
        flag.validate_python(token)
