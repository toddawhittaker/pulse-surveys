"""the reveal derives its subject from the comment Care is acting on

Revision ID: b6d92c05a7f1
Revises: b2d9f0a7c341
Create Date: 2026-09-06 00:00:00.000000

E4-01's whole schema change, which is not a schema change: one `SECURITY
DEFINER` function and the three privileges that make it a door, executed from
`reveal_subject_for_answer_v001.sql`.

`docs/tickets/e1/carried-from-e0.md` records the composition this closes. Three
facts that are individually correct and jointly are not: `ActorScope` carries
`holds_care` beside the purview so Care can never be unioned into a reporting
scope; `public.section_roster` hands instructor-scoped code the `user_id` of
every enrolled student, which is that view's whole point; and
`reveal_identity(actor_person_id=…, subject_user_id=…)` checked only that the
actor held a live CARE assignment and asked nothing about where the subject came
from. §2.1 permits one person to hold a Care assignment and a teaching
assignment, so that person could take a key off her own roster, reveal it, and
leave an audit row indistinguishable from a legitimate access.

The parameter is deleted rather than validated. `reveal_identity` now names one
comment, and `public.reveal_subject_for_answer(uuid)` answers whose it is —
`answer.response_id` to `response.user_id` — while the `pulse_care` connection
that calls it holds no read of either table. That is ADR 0094's third mechanism
used again, as `f3b7d05c9e42` used it for the passback's subject, and ADR 0144
is where the choice of a function over a grant to `pulse_care` is argued.

**The Care door is three functions after this revision**, and the rule E0-10
wrote the number for is unchanged: "every additional door is a way to obtain a
name without leaving a record". This one is not. It returns a `public.user` row
id or NULL, reads no column of `public.user_identity` and no column of
`public.person`, and has no path that answers a name — the same argument
`public.record_identity_reveal` has carried since E0-26 item 1.
`tests/integration/test_identity_grants.py` holds the door's three names as an
equality, so a fourth function is a failure rather than a widening nobody sees.

**The owner is unchanged and gains two column-scoped reads.**
`pulse_reveal_definer` already owns the other two halves; a second owner would be
a second privilege surface, and every rule in that test module about what the
definer may reach measures one set. What it gains is `SELECT (id, response_id)`
on `public.answer` and `SELECT (id, user_id)` on `public.response` — the four
columns the body reads and no more, which keeps `answer.comment_text` out of the
door's owner. §6.2 gives Care the comment content through the queue E10 builds,
not through the function that turns a comment id into a key.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes a function and three
privileges.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "b6d92c05a7f1"
down_revision: str | Sequence[str] | None = "b2d9f0a7c341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBJECT_RESOLVER = "public.reveal_subject_for_answer(uuid)"

# What the downgrade takes away, named by its full signature rather than by its
# bare name, which is `f3b7d05c9e42`'s reason repeated: a `DROP FUNCTION` without
# an argument list is ambiguous the moment a second overload exists, and naming
# the signature is what makes this line say out loud which object leaves.
#
# `IF EXISTS` because a downgrade is exactly the moment somebody is already
# dealing with a database in a state nobody planned, and a rollback that stops
# halfway on an object that was never created is worse than one that says nothing
# happened.
DROP_THE_SUBJECT_RESOLVER = f"DROP FUNCTION IF EXISTS {SUBJECT_RESOLVER}"

# The two reads back, and they name **columns** for the reason `e5b83c60f7a1`
# gives: a privilege granted at column grain lives in `pg_attribute.attacl`, and
# `REVOKE SELECT ON public.answer FROM pulse_reveal_definer` does not reach it. A
# table-grain revoke here would read as correct, run without error, and leave the
# Care door's owner holding the columns the rollback was meant to take away —
# which `tests/integration/test_identity_grants.py` would then report as a
# privilege beyond what the door at that revision needs.
#
# Each names one relation and the one role, so nothing else on either table
# moves: `public.answer` and `public.response` carry `pulse_app`'s table-level
# grants from `student_read_grants_v001.sql` and
# `survey_submission_grants_v001.sql`, and a revoke naming a wider role would
# take those with it and leave a database where a student cannot submit a survey.
REVOKE_THE_DERIVATION_READS = (
    "REVOKE SELECT (id, response_id) ON public.answer FROM pulse_reveal_definer",
    "REVOKE SELECT (id, user_id) ON public.response FROM pulse_reveal_definer",
)


def upgrade() -> None:
    """Apply this revision: the door's third function, its owner's two reads, and its grant."""
    op.execute(read_sql("reveal_subject_for_answer_v001"))


def downgrade() -> None:
    """Reverse this revision: the third function is dropped and its two reads given back.

    The function goes first and the privileges after it, so that at no point does
    a callable body exist without the reads it runs on — a `pulse_care` session
    that called it in between would meet `permission denied` rather than an
    answer, and this order means there is no such moment.

    **The owner role is neither dropped nor emptied**, which is E0-10's decision
    and `e2c94b6a1f70`'s after `DROP ROLE` stopped a downgrade halfway. It belongs
    to `446183e8cc5f`, it owns the other two halves of the Care door, and the four
    grants those two run on are what makes re-identification possible at all.
    What leaves with this revision is one function, the `EXECUTE` that rode on it
    — which Postgres drops with the object — and the two column reads it needed.

    A database walked back to here has E0-26's two-function door exactly as it
    was, and `app.services.safety` will not run against it: the service names this
    function, so a downgrade past this revision is a downgrade past the
    application that calls it.
    """
    op.execute(DROP_THE_SUBJECT_RESOLVER)
    for revoke in REVOKE_THE_DERIVATION_READS:
        op.execute(revoke)
