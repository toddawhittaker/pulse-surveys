"""What a create and an edit leave behind, and what they deliberately do not — E5-06.

Criterion 4 asks for "the log row for each write … asserted by reading the audit
trail, not the return value", and work-order decision 3 settles that this ticket
writes **no** `audit_log` row and records the choice: `AuditAction` has one
member, `audit_log.subject_user_id` is `NOT NULL`, `pulse_app` holds no `INSERT`
on the table, and the only writer is a `SECURITY DEFINER` function built for the
Care identity reveal. Widening that door for a non-reveal write is a change to
the audit guarantee and belongs in its own reviewed change; SPEC §8's sentence
listing what `audit_log` includes does not name set definitions.

**So the trail this module reads is the set row's own columns**, which decision 3
names as what *is* recorded: the creator and `created_at` on a create, and
`updated_at` on an edit. The delete leaves no row and therefore no trace, and
that gap is the one `deferred.md` carries with an owner — it is not asserted
here, because there is nothing to assert and a test that pretended otherwise
would be the record going on asserting something the decision made false.

**The absence is asserted beside a write that demonstrably happened.** "No audit
row was written" is a claim worth nothing over a request that did nothing, so
each half of the audit test first requires the set row to have appeared,
changed or gone.

**`updated_at` is read against the clock service, not against the wall clock.**
ADR 0109's development clock stands months away from the real instant in this
world, so a service stamping `datetime.now(UTC)` and one asking the clock produce
two answers that cannot be confused — which is the only reason this can be
asserted at all.

**Which failure a red here is, before E5-06 lands.** Every write goes over HTTP
to a path the work order fixes, so an unbuilt application answers 404 and each
test fails on its status naming the router (`docs/MISTAKES.md` entry 44).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.named_sets import NamedSetDoor
from sqlalchemy import func, select

pytestmark = pytest.mark.integration

# SPEC §8's own spelling, and the table E0-10 built for the Care reveal.
AUDIT_LOG_TABLE = "audit_log"


def audit_rows(world: Any) -> int:
    """How many `audit_log` rows the database holds, on the seeding connection."""
    from fixtures.supervision import require_table

    world.refresh()
    table = require_table(world.tables, AUDIT_LOG_TABLE)
    return int(world.session.execute(select(func.count()).select_from(table)).scalar_one())


def test_a_created_set_records_the_person_who_defined_it_and_when(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Decision 3's record of a create: the creator key and the created instant, on the row.

    The creator is also what decision 1 scopes every edit and delete by, so this
    is the column the whole of criterion 2 rests on: a create that left it null,
    or that wrote the session's `user` key rather than its `person` key, produces
    a set nobody can edit — including the leader who just defined it.

    **The mutations this kills:** a creator column filled from the request body
    rather than from the session, which lets a caller define a set in somebody
    else's name; a null creator; and a `created_at` the service leaves to
    nothing.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    body = world.a_write()

    answered = named_sets.create(body)
    detail = named_set_contract.body_of(answered, "The created set", named_set_contract.created)

    stored = world.set_row(detail[named_set_contract.id_field])
    assert stored is not None, (
        f"The 201 answered id {detail[named_set_contract.id_field]!r} and no `comparison_set` row "
        "carries it. The answer is a claim that the row is there."
    )
    creator = world.creator_column()
    assert str(stored[creator]) == str(world.leader_person_id), (
        f"The created set records {stored[creator]!r} as its definer and this session's person is "
        f"{world.leader_person_id!r}. Decision 1 scopes every edit and delete by that column, so a "
        "set created against the wrong key is a set its own definer is refused."
    )
    assert stored[world.instant_column(named_set_contract.created_at_field)] is not None, (
        "The created set carries no `created_at`. Decision 3 makes the row's own timestamps the "
        "whole record of this write — there is no audit row behind them."
    )


def test_an_edit_moves_updated_at_to_the_clock_the_service_reads(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The work order's sentence: "`updated_at` is set by the service to `clock` time on every PUT".

    **The mutation this kills:** `datetime.now(UTC)` in place of the clock
    service. Every other date in this product comes from ADR 0109's clock, which
    is what lets a development stack stand in a seeded term; a write stamping the
    real instant puts a set's edit months away from the world it was edited in,
    and nothing else in the suite would notice.

    **The premise this rests on is checked first**: the pretended instant has to
    be far enough from the real one that the two answers cannot be confused. If
    they ever coincide, this test says so rather than passing against either.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    pretended = named_set_contract.clock_instant
    tolerance = named_set_contract.clock_tolerance
    now = datetime.now(UTC)
    assert abs(now - pretended) > tolerance, (
        f"The development clock this world stands at ({pretended}) is within {tolerance} of the "
        f"real instant ({now}), so a service stamping `datetime.now(UTC)` and one asking the clock "
        "would give the same answer and this test would pass against either. The world's instants "
        "come from SPEC §3.1's Fall 2026 calendar in `tests/fixtures/survey_windows.py`."
    )

    updated_at = world.instant_column(named_set_contract.updated_at_field)
    before = world.set_row(world.hers.set_id)[updated_at]

    answered = named_sets.edit(world.hers.set_id, world.a_write())
    assert answered.status_code == named_set_contract.list_ok, (
        f"The edit answered {answered.status_code}; nothing below is about an edit that happened. "
        f"Body begins {answered.text[:400]!r}."
    )

    after = world.set_row(world.hers.set_id)[updated_at]
    assert after != before, (
        f"`{updated_at}` is {after!r} and was {before!r} before the edit. Decision 3 makes this "
        "column the whole record that the set was edited at all."
    )
    stamped = after if after.tzinfo is not None else after.replace(tzinfo=UTC)
    assert abs(stamped - pretended) <= tolerance, (
        f"`{updated_at}` was stamped {stamped}, and the clock this application runs on stands at "
        f"{pretended} (±{tolerance} for the drift ADR 0109's `real + (pretend_now - anchored_at)` "
        f"accumulates while a test runs). The real instant is {now}, which is where a "
        "`datetime.now(UTC)` would have put it."
    )


def test_no_audit_log_row_is_written_for_a_create_an_edit_or_a_delete(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Decision 3, asserted: the audit door is not widened by this ticket.

    This is a recorded decision rather than an omission, and it is asserted so
    that changing it is deliberate. `audit_log` is append-only and its one
    writer is the Care reveal's `SECURITY DEFINER` function; a set write that
    reached it would have needed `AuditAction` widened, `subject_user_id` made
    nullable and an `INSERT` granted to `pulse_app` — three changes to the
    guarantee SPEC §4 calls traceability-for-safety, arriving as a side effect of
    a management API.

    **Why this is not an assertion about emptiness** (`docs/MISTAKES.md` entry
    3): all three writes are driven and each is required to have taken effect —
    a row appeared, a row changed, a row went — before the count is read. The
    claim is "these three writes happened and left no audit row", not "the table
    is empty".

    **The mutation this kills:** an `audit_log` insert added here because
    criterion 4's sentence asks for one, which is exactly the widening decision 3
    refuses and which would fail at the grant rather than at review.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    before = audit_rows(world)

    created = named_sets.create(world.a_write())
    detail = named_set_contract.body_of(created, "The created set", named_set_contract.created)
    new_id = detail[named_set_contract.id_field]
    assert world.set_row(new_id) is not None, "The create left no row, so it is not a write."

    edited = named_sets.edit(new_id, world.a_write())
    assert (
        edited.status_code == named_set_contract.list_ok
    ), f"The edit answered {edited.status_code}; body begins {edited.text[:400]!r}."

    removed = named_sets.remove(new_id)
    assert (
        removed.status_code == named_set_contract.no_content
    ), f"The delete answered {removed.status_code}; body begins {removed.text[:400]!r}."
    assert world.set_row(new_id) is None, "The delete left the row, so it is not a write either."

    assert audit_rows(world) == before, (
        f"The database holds {audit_rows(world)} `{AUDIT_LOG_TABLE}` rows where it held {before}, "
        "after a create, an edit and a delete. Decision 3 records that this ticket writes none: "
        "the existing machinery is the identity reveal's, and widening it for a non-reveal write "
        "is a change to the audit guarantee that belongs in its own reviewed change. If that "
        "decision has been reversed, this test is the record that has to move with it."
    )
