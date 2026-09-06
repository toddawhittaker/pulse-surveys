"""The account of what Pulse told a platform about a student's participation.

SPEC §13 puts `grade_sync` here — "`models/grades.py` — grade_sync" — and §8 names
it in the table list with the sentence that settles its shape: "`grade_sync` is
**append-only, at the grain of one row per post**: each row records the score as it
was sent, the timestamp sent with it, the outcome, and the student and section it
concerns, and a failed attempt is a row too. The latest row for a
`(section_id, user_id)` pair is what identifies a retry and what the recompute
compares against."

[ADR 0124](../../../docs/adr/0124-grade-sync-is-append-only-one-row-per-post.md) is
the argument for that grain and this module does not restate it. What is worth
having beside the table is the consequence, because it is the thing a reader is
most likely to get wrong: **there is no "the" row for a student and a section.**
Every reader asks for the *latest* row, ordered by `created_at`, and a query that
returns one row against a database holding one post returns the wrong row against
a term's worth of them.

**Why the record is kept at all.** A score already posted can be lowered
afterwards: E2-08's asynchronous re-classification can flip a comment weeks after
a week's window shut, which lowers the numerator of a number a student was already
shown. E3-06 re-posts when a recomputation changes the value, and under a
last-value row that re-post would destroy the number the platform was previously
told. The question that gets asked when a grade is disputed is "what did we send,
and when", and only an append-only log can answer it.

**Append-only is a property of the database, not a convention.**
`grade_passback_grants_v001.sql` gives `pulse_app` `SELECT` and `INSERT` on this
table and neither `UPDATE` nor `DELETE`, which is the shape `classification` and
`nrps_call` already take. E3-06 posts and records on the connection every screen in
the product runs on, so anything the grant permitted would be reachable from a bug
in an unrelated service module. E13's retention purge is what will trim this table,
on its own connection and with its own rule.

**`ags_call` is not here**, and the split is deliberate. That table is at the grain
of one HTTP call and lives beside `NrpsCall` in `app.models.lti`, because §13 puts
the LTI service call logs with the registration they are made against. One post is
several calls, and neither table is derivable from the other.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey

__all__ = ["GradeSync", "GradeSyncOutcome"]


class GradeSyncOutcome(StrEnum):
    """What became of one post: it reached the platform, or it did not.

    A closed set of two, held as a Postgres enum type rather than as free text, for
    the reason `app.models.lti.LaunchDefectKind` gives: the set belongs in the
    database rather than in a convention every later reader has to remember. E11's
    job dashboard and E3-06's retry decision both branch on exactly this, and an
    open column is one a later writer can put a third state into — `pending`,
    `skipped`, `unknown` — leaving both readers with a case neither was written
    against and nothing red anywhere.

    **Two and not three, and `response_code` is why.** "Refused with a 401" and
    "never reached the platform" are both `FAILED` here, and they are told apart by
    the response code beside this column: a number is a platform that answered, and
    NULL is a call that never got there. Making that distinction a third enum member
    would put one fact in two columns that can disagree.

    **The member values are the wire strings and the labels in the database**, so
    the type is declared with `values_callable` below rather than storing the member
    names — the two spellings would otherwise differ by case alone, which is the
    kind of difference nobody notices until a query returns nothing.
    """

    POSTED = "posted"
    FAILED = "failed"


class GradeSync(UuidPrimaryKey, Base):
    """One post of one student's participation score to one section's line item.

    Append-only, one row per post, and a failed attempt is a row too (SPEC §8, ADR
    0124). The module docstring above has the reasoning; what follows is what each
    column is for.

    **`score_text` is a string and that is the whole of ADR 0052's retry identity.**
    That record has a platform accept a score whose timestamp equals the one it
    already holds as a *retry of the same delivery* rather than as a new one, and
    E3-04 leans on it after a network timeout: it re-sends the identical body,
    because the timestamp names the recomputation and not the attempt. A value the
    poster re-derives is not provably the value it retries — `61.5` and `61.50` are
    one number and two bodies — so what is stored is the characters that were sent.
    A `Numeric` column would round-trip `61.50` as `Decimal('61.50')` and a `Float`
    as `61.5`, and a retry composed from either is a new delivery the platform may
    accept twice or refuse.

    **`score_timestamp` and `created_at` are two different moments and are not
    interchangeable.** The first is the instant sent to the platform, which ADR 0052
    compares; the second is when this row was written. A schema with only one of
    them cannot express a retry at all, because a retry carries the timestamp of the
    delivery it repeats and is written at a later moment than that delivery was.

    **`ledger_text` is the comment as sent** — SPEC §3.4's per-week ledger, which
    since the 2026-09-04 ruling accompanies every posted score and is the only place
    the arithmetic behind a percentage is visible to anybody (ADR 0125). Storing the
    composed text rather than re-composing it later is the same argument
    `score_text` makes: what the record is for is saying what was sent.

    **`response_code` is nullable and NULL has exactly one meaning: the call never
    reached the platform.** That is `app.models.lti.NrpsCall`'s semantics for the
    same column, deliberately identical so E11's console reads one idea rather than
    two. A `NOT NULL` here would force the writer to invent a number — a `0`, a
    `599` — for a call that got no answer, after which "the platform refused it" and
    "we never reached the platform" are the same row.

    **No response body, and ADR 0129 is where that was decided.** A body is an
    unbounded third-party string written once per post on a table nothing purges
    until E13, and on a misconfigured platform it can quote the request that
    produced it. The code says which of a small set of things happened, which is
    what an operator acts on.

    **The index is ascending and the reason is not performance.** Postgres serves
    `ORDER BY created_at DESC LIMIT 1` from an ascending index by a backward scan at
    the same cost. What a descending index costs is visibility: a direction can only
    be written as a text expression, a text-expression index is not comparable, and
    `alembic check` then cannot see the declaration at all. E2-02 reversed
    `NrpsCall`'s index for exactly that and its docstring records the measurement.

    **Not a person table, and the question was asked carefully.** The row states
    something about a person's standing — a participation figure against a student —
    and it holds no column that identifies one: the student is a foreign key, and
    the identity behind it sits on `user_identity`, which `pulse_app` holds no
    `SELECT` on by any mechanism. That is the same answer `enrollment` and
    `response` give. Marking a column here would put every posted score in the set
    the identity-separated views may not read, which is the opposite of what §6.1's
    job dashboard needs. The columns the judgement was made against are recorded in
    `tests/integration/test_identity_column_marker.py`'s inventory, so a column
    arriving expires the judgement rather than merely failing a count.
    """

    __tablename__ = "grade_sync"
    __table_args__ = (
        # **The lookup every reader of this table performs**, and the one ADR 0124
        # names as this ticket's debt: the newest row for one student in one
        # section. E3-06 runs it per student per section on every sweep, on the
        # recompute's hot path, against a table that takes a row per post all term
        # — so it is the access path the table is laid out for.
        #
        # The two keys lead because that is the equality the lookup filters on and
        # Postgres 17 has no skip scan; `created_at` follows them because the
        # ordering runs on it. `NrpsCall`'s docstring has the measurement that
        # settled the same question there: 2,006 buffers per probe against the
        # leading column's own index alone, and 5 against the composite.
        #
        # Ascending, for the comparability reason in the class docstring. No
        # separate index on `section_id`: leading with it, this one serves every
        # lookup such an index would, so a second one is a write nobody reads —
        # which is why `mapped_column` below carries no `index=True`.
        Index("ix_grade_sync_section_id_user_id_created_at", "section_id", "user_id", "created_at"),
    )

    # Which section's gradebook the score was posted to. RESTRICT, matching every
    # other reference to `section` in this schema: losing a section should refuse
    # rather than silently take the account of what was posted for it.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # Which student the score was about. RESTRICT for the same reason and one more:
    # this row is the record of what a person was told their participation was, and
    # a cascade would erase it as a side effect of a change to a different table.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # The score exactly as it was sent, character for character. See the class
    # docstring: this is a string because ADR 0052's retry identity is byte equality
    # of a body the platform already accepted.
    score_text: Mapped[str] = mapped_column(Text, nullable=False)
    # The timestamp that went to the platform with the score, which ADR 0052 has it
    # compare. Not the moment this row was written — `created_at` below is that.
    # `AwareDateTime` refuses a naive value at the bind boundary (ADR 0019).
    score_timestamp: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    # The comment as sent: SPEC §3.4's per-week ledger of items answered against
    # items offered (ADR 0125). Stored rather than re-composed later, so the record
    # says what was sent instead of what the same code would say today.
    ledger_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Whether this post reached the platform. A closed set of two; see
    # `GradeSyncOutcome` above for why it is two and not three.
    outcome: Mapped[GradeSyncOutcome] = mapped_column(
        Enum(
            GradeSyncOutcome,
            name="grade_sync_outcome",
            values_callable=lambda enumeration: [member.value for member in enumeration],
        ),
        nullable=False,
    )
    # The HTTP status the platform answered with. NULL means no answer at all: see
    # the class docstring, and `app.models.lti.NrpsCall`, which means the same by it.
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When this row was written, defaulted to the insert moment so the writer
    # supplies nothing and no caller can record a time of its own choosing. This is
    # what "latest" is measured on, and the index above is what makes that cheap.
    created_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
