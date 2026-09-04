"""ADR 0082 does not go on asserting the rule this ticket removed — E3-01, criterion 5.

> ADR 0082 is amended or superseded in this pull request.

ADR 0082 says three things E3-01 makes false: that the table holds "at most one
row, enforced by the database", that "an existing key is kept, never rotated", and
that rotation "the one-row rule forbids by design". Every one of those sentences
is what a reader of that record will believe tomorrow, and `docs/MISTAKES.md`
entry 1 is that exact failure — a record going on asserting something the change
made false. The ADR README's own rule is that a superseded record stays in place
with a line pointing at its replacement, and this is that line, asserted.

**Why a test rather than review.** The criterion is checkable, so it is checked.
The tests in this ticket would all be green with ADR 0082 left exactly as it is,
and the next person to read it would build against a one-row table.

**What is not asserted here.** Not the ADRs' contents, not their titles, and not
which of "amended" or "superseded" was chosen — those are the implementer's, and
an assertion over them would be this suite writing the record. What cannot be left
open is whether a reader arriving at ADR 0082 is sent to the record that changed
it.
"""

from pathlib import Path

import pytest
from fixtures.repo import REPO_ROOT

# The records this ticket's work order assigns. 0126 is the supply path and 0127
# is the rotation rule; the numbers are partitioned centrally, so they are facts
# rather than this module's choice. The slugs are the implementer's.
ADR_DIRECTORY = REPO_ROOT / "docs" / "adr"
CUSTODY_RECORD = "0082"
SUPPLY_RECORD = "0126"
ROTATION_RECORD = "0127"


def the_record(number: str) -> Path:
    """The one ADR file whose name begins with `number`, or a failure saying so."""
    found = sorted(ADR_DIRECTORY.glob(f"{number}-*.md"))
    if len(found) != 1:
        pytest.fail(
            f"`docs/adr/` holds {len(found)} records numbered {number} ({[p.name for p in found]}). "
            "E3-01's work order assigns 0126 to the supply path and 0127 to the rotation rule, and "
            "the ADR README forbids reusing or renumbering either. Zero means the record this "
            "ticket owes was not written."
        )
    return found[0]


def test_the_one_row_custody_record_points_at_the_record_that_changed_it() -> None:
    """Criterion 5: a reader of ADR 0082 is sent to the rule that replaced its own.

    **The mutation this kills:** both new ADRs written and ADR 0082 left untouched.
    Everything else in this ticket is green in that state, and the cost is paid by
    the next person to read the custody record — they find "at most one row,
    enforced by the database" and "an existing key is kept, never rotated" stated
    as current decisions, with nothing anywhere near them saying otherwise.

    **The near miss it must survive**, and the reason both new records are
    required to exist first: a pointer line in ADR 0082 naming a record nobody
    wrote. That reads as a complete amendment in a diff and sends its reader
    nowhere.
    """
    supply = the_record(SUPPLY_RECORD)
    rotation = the_record(ROTATION_RECORD)
    assert supply.read_text(encoding="utf-8").strip(), (
        f"`{supply.name}` is empty. It is the record that decides where a non-development "
        "deployment's signing key comes from, which is criterion 1's other half."
    )
    assert rotation.read_text(encoding="utf-8").strip(), (
        f"`{rotation.name}` is empty. It is the record that decides how many keys the set may "
        "carry, what selects the signing key and what retires one."
    )

    custody = the_record(CUSTODY_RECORD).read_text(encoding="utf-8")

    assert ROTATION_RECORD in custody, (
        f"ADR {CUSTODY_RECORD} does not mention ADR {ROTATION_RECORD}, so it goes on stating that "
        "the table holds 'at most one row, enforced by the database', that 'an existing key is "
        "kept, never rotated', and that rotation is something 'the one-row rule forbids by "
        "design' — three sentences this ticket makes false. The ADR README's rule is that a "
        "superseded record stays in place with a line pointing at its replacement, and "
        "`docs/MISTAKES.md` entry 1 is what happens when it does not."
    )
