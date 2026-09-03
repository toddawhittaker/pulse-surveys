"""E2-16 criterion 1 — the two E2 schema revisions round-trip without losing or inventing.

> On a database with rows in every E2 table, `alembic downgrade d2f6a913c47e`
> then `alembic upgrade head` restores byte-identical `survey_window`,
> `response`, `answer`, `classification.answer_id`, and `response.is_valid`
> values — proven by a test that seeds, round-trips, and compares.

The epic-boundary data-model review measured both halves of that on a throwaway
database, and they fail differently, so they are two journeys here rather than
one.

**`3f6907349751` strands the database.** Its `downgrade()` drops
`survey_window.term_id` unpreserved and drops `response`, `answer`, `question`
and `question_set` whole; its `upgrade()` re-adds `term_id` `NOT NULL` with no
backfill. With windows stored — 188 of them on dev — the re-upgrade aborts with a
`NotNullViolation` and the version is left at `d2f6a913c47e`, below every
revision E2 added. That is `test_a_downgrade_and_re_upgrade_restores_every_stored_survey_row`,
and today it fails on the upgrade step rather than on a comparison.

**`f1a3c7d02b64` corrupts silently.** Its `downgrade()` drops
`classification.answer_id` and `response.is_valid` unpreserved; its `upgrade()`
backfills `is_valid = true` for every row and leaves `answer_id` null. So a
response a model judged invalid comes back reading valid — §3.4 counts it — and a
floored verdict comes back naming no comment, which the sweep in
`app/services/validity.py` can never find again and no `UPDATE` can ever repair
(ADR 0055 withholds it). That is
`test_a_downgrade_and_re_upgrade_keeps_each_verdicts_comment_and_each_submissions_validity`,
and it fails on the values rather than on a step.

**The second journey stops below `f1a3c7d02b64` and no lower**, deliberately. A
single walk to `d2f6a913c47e` would meet the strand first, and the silent
corruption — the more dangerous of the two, because nothing reports it — would be
invisible behind a migration that refused to run. Each test walks to the parent
of the revision it is about, resolved from that revision's own `down_revision`.

**Every comparison is per row, keyed by the row's own primary key, and over
whole rows.** A restore that keeps every value and puts them back on the wrong
rows leaves a set comparison satisfied, and it is worse than losing them: two
responses swap their validity, two verdicts swap the comments they name. Values
that differ in every position are seeded for the same reason.

**The control that makes a journey mean anything is asserted in the middle**: at
the older revision, the columns and tables the revision adds really are gone. A
downgrade that quietly did nothing would preserve everything perfectly and prove
nothing at all (`docs/MISTAKES.md` entry 3).

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).

**Seeding happens at head and the database is walked back down afterwards**, for
the reason `seed_row`'s own docstring gives: its insert and its `RETURNING`
clause are built from `Base.metadata`, so seeding into a database standing before
a revision that added a column fails inside the fixture
(`docs/disputes/E1-10-01.md`). `head` appears here only as the name of the schema
today's models describe, and is the subject of nothing.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    rows_by_key,
    session_on,
    the_revision_below,
)
from fixtures.mock_ai import INSUFFICIENT, SUBSTANTIVE
from fixtures.supervision import seed_row

pytestmark = pytest.mark.integration

# The two revisions under test. Alembic knows each by the bare identifier; the
# files are `backend/migrations/versions/20260901_<id>_*.py`.
SURVEY_SCHEMA_REVISION = "3f6907349751"
SUBMISSION_VALIDITY_REVISION = "f1a3c7d02b64"

# What each one is, for the failure message when a constant here has gone stale.
SURVEY_SCHEMA_IS = "E2-05's revision — SPEC §8's four survey tables and the window's term rule"
SUBMISSION_VALIDITY_IS = "E2-08's revision — `response.is_valid` and `classification.answer_id`"

# The tables `3f6907349751` creates and its downgrade drops whole. `question_set`
# and `question` are in the list because `answer` references them: a restore that
# brought answers back without the questions they name could not have inserted
# them at all, and one that recreated the questions under new keys would leave
# every answer pointing at a row nobody submitted against.
TABLES_DROPPED_WHOLE = ("question_set", "question", "response", "answer")

SURVEY_WINDOW = "survey_window"
CLASSIFICATION = "classification"
RESPONSE = "response"

# The three columns the two revisions add and their downgrades take away.
WINDOW_TERM_COLUMN = "term_id"
IS_VALID_COLUMN = "is_valid"
ANSWER_ID_COLUMN = "answer_id"

# Instants written by this module, distinct in every position, so that a value
# which came back is a value that was kept rather than one re-derived. Aware, as
# ADR 0019 requires of everything stored in these columns.
FIRST_WINDOW = (
    datetime(2026, 9, 4, 22, 0, tzinfo=UTC),
    datetime(2026, 9, 7, 3, 59, 59, tzinfo=UTC),
)
SECOND_WINDOW = (
    datetime(2026, 10, 30, 22, 0, tzinfo=UTC),
    datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC),
)
FIRST_SUBMISSION = datetime(2026, 9, 5, 14, 30, tzinfo=UTC)
SECOND_SUBMISSION = datetime(2026, 10, 31, 9, 15, tzinfo=UTC)

# Two comments that differ in every word, for the same reason.
FIRST_COMMENT = "the pacing in week 3 was too fast and the reading load doubled"
SECOND_COMMENT = "labs are well run but the rubric arrives after the deadline"

# The two `is_valid` values, one of each. **Both directions are seeded because
# the measured defect is a backfill**: `f1a3c7d02b64`'s upgrade writes
# `is_valid = true` for every row, so a test seeding only invalid submissions
# catches it and a test seeding only valid ones does not — and the mirror-image
# repair, a restore that wrote `false` everywhere, would pass the first and fail
# the second. Seeding both makes the assertion about the stored value rather than
# about either constant.
VALIDITIES = (True, False)


def a_terms_section_and_week(session: Any, tables: dict[str, Any]) -> dict[str, Any]:
    """A section and a week of one term, with that term, built through one chain.

    Sharing a chain is what puts them in one term: the walker creates the term
    while building the section's ancestors and the week then finds it already
    there. Every window and response written below names all three explicitly, so
    the rows this module compares do not depend on how the walker resolves a
    column with two foreign keys.
    """
    chain: dict[str, Any] = {}
    section = seed_row(session, tables, "section", chain)
    week = seed_row(session, tables, "week", chain)
    return {"section": section, "week": week, "term": chain["term"], "chain": chain}


def seed_a_window_a_response_and_an_answer(
    session: Any,
    tables: dict[str, Any],
    *,
    window: tuple[datetime, datetime],
    submitted_at: datetime,
    is_valid: bool,
    comment: str,
) -> dict[str, Any]:
    """One term's worth of everything `3f6907349751` creates or touches.

    A window, a response and the response's one comment answer, all naming the
    same section and week of one term. The `answer` row names its comment
    explicitly: `answer`'s check constraint requires exactly one of its three
    value columns to be non-null, and the seeding walker leaves every nullable
    column alone, so a row it composed on its own would be refused inside this
    fixture (`docs/MISTAKES.md` entry 13's closing sentence).
    """
    rows = a_terms_section_and_week(session, tables)
    chain = rows["chain"]
    opens_at, closes_at = window

    survey_window = seed_row(
        session,
        tables,
        SURVEY_WINDOW,
        {},
        **{
            "section_id": rows["section"]["id"],
            "week_id": rows["week"]["id"],
            WINDOW_TERM_COLUMN: rows["term"]["id"],
            "opens_at": opens_at,
            "closes_at": closes_at,
        },
    )
    response = seed_row(
        session,
        tables,
        RESPONSE,
        chain,
        **{
            "section_id": rows["section"]["id"],
            "week_id": rows["week"]["id"],
            "first_submitted_at": submitted_at,
            "last_submitted_at": submitted_at,
            IS_VALID_COLUMN: is_valid,
        },
    )
    answer = seed_row(
        session,
        tables,
        "answer",
        chain,
        **{"response_id": response["id"], "comment_text": comment},
    )
    return {"window": survey_window, "response": response, "answer": answer}


def stored(database: Any, tables: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """Every row of each named table, whole and keyed, as one mapping per table."""
    return {name: rows_by_key(database, tables, name) for name in names}


def assert_seeded_something(before: dict[str, Any], names: tuple[str, ...]) -> None:
    """Stop unless every table under comparison holds at least two rows.

    Without this, every assertion in this module is satisfied by a database in
    which nothing was ever seeded — two empty mappings compare equal, and a
    downgrade that dropped every row would then read as a perfect round trip
    (`docs/MISTAKES.md` entry 3). Two rather than one, because a swap between two
    rows is one of the two failures being asserted against and one row cannot
    exhibit it.
    """
    thin = {name: len(before[name]) for name in names if len(before[name]) < 2}
    assert not thin, (
        f"These tables hold fewer than two rows before the journey: {thin}. The comparison after "
        "the round trip is an equality between mappings, so an empty one is satisfied by a "
        "downgrade that took every row with it — and a single row cannot show two rows' values "
        "coming back on each other. This is a defect in this module's seeding rather than in the "
        "migrations."
    )


def assert_rows_are_unchanged(
    after: dict[str, Any], before: dict[str, Any], name: str, what: str
) -> None:
    """Every row of `name` is still there, still carrying exactly what it was seeded with.

    The three failures are separated because they need different fixes: rows that
    are gone, rows whose values changed, and rows that appeared from somewhere.
    """
    missing = sorted(str(key) for key in before if key not in after)
    assert not missing, (
        f"After {what}, {len(missing)} `{name}` row(s) are no longer in the database at all: "
        f"{missing}. The downgrade under test removes a column or a table; it does not own these "
        "rows, and a round trip that discards them is the loudest version of the finding this "
        "module is about."
    )
    changed = {
        key: {
            column: (before[key][column], after[key][column])
            for column in before[key]
            if column in after[key] and after[key][column] != before[key][column]
        }
        for key in before
    }
    changed = {key: difference for key, difference in changed.items() if difference}
    assert not changed, (
        f"After {what}, {len(changed)} `{name}` row(s) came back carrying values they were not "
        f"seeded with — each as `column: (seeded, stored)`:\n  {changed}\n"
        "A value the upgrade invented reads as a successful migration and is indistinguishable "
        "afterwards from one a person entered. The comparison is per row and by key, so a pair of "
        "rows whose values came back on each other fails here too — which is the failure worth "
        "more than the loss, because nothing anywhere raises."
    )
    appeared = sorted(str(key) for key in after if key not in before)
    assert not appeared, (
        f"After {what}, `{name}` holds {len(appeared)} row(s) nothing seeded: {appeared}. A "
        "restore that inserted rather than restored leaves duplicates of everything it kept, and "
        "the second trip is where an operator finds out."
    )


def test_a_downgrade_and_re_upgrade_restores_every_stored_survey_row(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 1 for `3f6907349751`: windows, responses and answers survive the trip.

    Two sections in two terms are seeded at head, each with a window, a response
    and the response's comment answer; the database is walked down to the
    revision below E2-05's and back up; and every row has to come back carrying
    what it was seeded with.

    **The mutation this must kill, and it is the state of the code today:** a
    downgrade that drops `survey_window.term_id` and the four tables keeping
    nothing, beside an upgrade that re-adds `term_id` `NOT NULL` with no
    backfill. With a window stored, the re-upgrade aborts on that one statement
    and the database is left stranded below every revision E2 added — so this
    test fails today on the upgrade step, with Alembic's own error, rather than
    on a comparison.

    **The near miss it must survive:** a preserve-and-restore that keeps the
    windows and re-derives their term from "the only term in the database". Two
    terms are seeded precisely so that a re-derivation has something to get
    wrong, and the comparison is keyed so that two windows restored onto each
    other's rows fail here rather than passing as the right set.

    **The control that makes the trip mean anything** is asserted in the middle:
    at the revision below, the four tables and the term column really are gone. A
    downgrade that quietly did nothing would preserve everything and prove
    nothing.
    """
    config = alembic_config_pointed_at(empty_database)
    revision = require_revision(config, SURVEY_SCHEMA_REVISION, SURVEY_SCHEMA_IS)
    below = the_revision_below(config, revision)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    with session_on(empty_database) as session:
        seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=FIRST_WINDOW,
            submitted_at=FIRST_SUBMISSION,
            is_valid=VALIDITIES[0],
            comment=FIRST_COMMENT,
        )
        seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=SECOND_WINDOW,
            submitted_at=SECOND_SUBMISSION,
            is_valid=VALIDITIES[1],
            comment=SECOND_COMMENT,
        )

    compared = (*TABLES_DROPPED_WHOLE, SURVEY_WINDOW)
    before = stored(empty_database, metadata_tables, compared)
    assert_seeded_something(before, compared)

    migrate(config, "downgrade", below, f"undoing revision {revision}")

    standing = {name: columns_the_database_reports(empty_database, name) for name in compared}
    still_there = sorted(name for name in TABLES_DROPPED_WHOLE if standing[name])
    assert not still_there, (
        f"After downgrading to {below} — the revision below {revision} — the tables {still_there} "
        "still exist. That revision creates them and its downgrade drops them, so a downgrade "
        "that leaves them is not undoing it, and 'the rows survived the round trip' would be true "
        "of a migration pair that did nothing in either direction. If a downgrade deliberately "
        "keeps a table now, that is a change to what a downgrade means and belongs in the pull "
        "request."
    )
    assert WINDOW_TERM_COLUMN not in standing[SURVEY_WINDOW], (
        f"After downgrading to {below}, `{SURVEY_WINDOW}` still carries `{WINDOW_TERM_COLUMN}`. "
        f"Revision {revision} is what adds it, so the comparison below would be measuring a "
        f"column that was never taken away. The table reports: {sorted(standing[SURVEY_WINDOW])}"
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying revision {revision} and what follows it")

    after = stored(empty_database, metadata_tables, compared)
    what = f"a downgrade to {below} and an upgrade back to the models' schema"
    for name in compared:
        assert_rows_are_unchanged(after[name], before[name], name, what)


def test_a_downgrade_and_re_upgrade_keeps_each_verdicts_comment_and_each_submissions_validity(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 1 for `f1a3c7d02b64`: the two columns come back holding what they held.

    Two responses are seeded, one valid and one not, each with a comment answer;
    two classifications are seeded, one naming a comment and one naming none —
    the bounce shape, which stores no answer by the 2026-09-03 ruling. The
    database is walked down to the revision below E2-08's and back up.

    **This journey stops below `f1a3c7d02b64` and no lower, deliberately.** A
    walk to `d2f6a913c47e` would meet `3f6907349751`'s strand first and never
    reach this subject; the sibling test above is where that is diagnosed.

    **The mutation this must kill, and it is the state of the code today:** a
    downgrade that drops the two columns keeping nothing, beside an upgrade that
    backfills `is_valid = true` for every row and leaves `answer_id` null. Both
    are silent. A nonsense-judged submission comes back reading valid and is
    counted by §3.4's participation numerator; a floored verdict comes back
    naming no comment, and the re-classification sweep filters on
    `answer_id IS NOT NULL` in both legs, so nothing will ever find it again —
    and `classification` takes no `UPDATE` (ADR 0055), so nothing can repair it
    either.

    **The near misses it must survive.** A restore that writes one constant into
    every `is_valid` passes any test seeding a single validity, which is why both
    are seeded. A restore that stamps every classification with some answer, or
    that nulls them all, passes any test seeding one classification, which is why
    a verdict naming a comment and a bounce naming none are both here — and the
    bounce's null has to come back as a null, not as a repair.

    **The control** is the same as the sibling's, in the middle: at the revision
    below, neither column exists.
    """
    config = alembic_config_pointed_at(empty_database)
    revision = require_revision(config, SUBMISSION_VALIDITY_REVISION, SUBMISSION_VALIDITY_IS)
    below = the_revision_below(config, revision)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    with session_on(empty_database) as session:
        judged = seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=FIRST_WINDOW,
            submitted_at=FIRST_SUBMISSION,
            is_valid=VALIDITIES[0],
            comment=FIRST_COMMENT,
        )
        seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=SECOND_WINDOW,
            submitted_at=SECOND_SUBMISSION,
            is_valid=VALIDITIES[1],
            comment=SECOND_COMMENT,
        )
        # A verdict about a stored comment, and a bounce. The verdict vocabulary
        # is §7.4's Output column for the comment-validity task, transcribed in
        # `tests/fixtures/mock_ai.py` rather than read off `app.ai.contracts`;
        # the seeding walker cannot invent one, because `classification` carries
        # a check constraint over exactly that closed set.
        seed_row(
            session,
            metadata_tables,
            CLASSIFICATION,
            {},
            **{ANSWER_ID_COLUMN: judged["answer"]["id"], "verdict": SUBSTANTIVE},
        )
        seed_row(
            session,
            metadata_tables,
            CLASSIFICATION,
            {},
            **{ANSWER_ID_COLUMN: None, "verdict": INSUFFICIENT},
        )

    compared = (RESPONSE, CLASSIFICATION)
    before = stored(empty_database, metadata_tables, compared)
    assert_seeded_something(before, compared)
    seeded_answers = {row[ANSWER_ID_COLUMN] for row in before[CLASSIFICATION].values()}
    assert len(seeded_answers) == 2 and None in seeded_answers, (
        f"The two seeded classifications carry {seeded_answers} between them. One has to name a "
        "comment and one has to name none: a restore that stamps every row with an answer and one "
        "that nulls every row are both caught only by having both shapes here."
    )
    seeded_validities = {row[IS_VALID_COLUMN] for row in before[RESPONSE].values()}
    assert seeded_validities == set(VALIDITIES), (
        f"The seeded responses carry {seeded_validities} between them rather than "
        f"{set(VALIDITIES)}. The measured defect is a backfill that writes one value everywhere, "
        "and a test seeding one value cannot tell that from a restore."
    )

    migrate(config, "downgrade", below, f"undoing revision {revision}")

    standing = {name: columns_the_database_reports(empty_database, name) for name in compared}
    assert IS_VALID_COLUMN not in standing[RESPONSE], (
        f"After downgrading to {below} — the revision below {revision} — `{RESPONSE}` still "
        f"carries `{IS_VALID_COLUMN}`. That revision adds it, so a downgrade that leaves it means "
        "the comparison below is about a column nothing removed. The table reports: "
        f"{sorted(standing[RESPONSE])}"
    )
    assert ANSWER_ID_COLUMN not in standing[CLASSIFICATION], (
        f"After downgrading to {below}, `{CLASSIFICATION}` still carries `{ANSWER_ID_COLUMN}`. "
        f"Revision {revision} is what adds it (ADR 0055's promised reference), so the comparison "
        f"below would be measuring a column that was never taken away. The table reports: "
        f"{sorted(standing[CLASSIFICATION])}"
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying revision {revision}")

    after = stored(empty_database, metadata_tables, compared)
    what = f"a downgrade to {below} and an upgrade back to the models' schema"
    for name in compared:
        assert_rows_are_unchanged(after[name], before[name], name, what)


def test_the_survey_rows_survive_the_round_trip_being_made_twice(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """Preserving is not a one-shot: an operator who goes down and up twice keeps everything.

    The same journey as the first test, made a second time from the state the
    first one left. Its pair is that test — one trip has to work before two can
    mean anything — and it is here because a scratch-table preserve has failure
    modes a single trip cannot see.

    **The mutation this must kill:** a preserve step that assumes it starts from
    nothing. A `CREATE TABLE` that raises because the scratch table is still
    there from last time; a restore that leaves stale rows behind, so the second
    preserve writes a second copy of every row and the restore matches the wrong
    one; a preserve that skips because it found the table already populated. None
    of them is visible on a first round trip, and a downgrade is exactly the
    operation somebody repeats — that is what it is for.

    **The near miss it must survive:** the second trip restoring from the first
    trip's leftovers. The values are the same either way, so this asserts the
    same keyed mapping rather than "some row is present"; a stale row carrying
    another row's values fails here for the reason a swap does above.
    """
    config = alembic_config_pointed_at(empty_database)
    revision = require_revision(config, SURVEY_SCHEMA_REVISION, SURVEY_SCHEMA_IS)
    below = the_revision_below(config, revision)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    with session_on(empty_database) as session:
        seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=FIRST_WINDOW,
            submitted_at=FIRST_SUBMISSION,
            is_valid=VALIDITIES[0],
            comment=FIRST_COMMENT,
        )
        seed_a_window_a_response_and_an_answer(
            session,
            metadata_tables,
            window=SECOND_WINDOW,
            submitted_at=SECOND_SUBMISSION,
            is_valid=VALIDITIES[1],
            comment=SECOND_COMMENT,
        )

    compared = (*TABLES_DROPPED_WHOLE, SURVEY_WINDOW)
    before = stored(empty_database, metadata_tables, compared)
    assert_seeded_something(before, compared)

    for attempt in (1, 2):
        migrate(config, "downgrade", below, f"undoing revision {revision}, trip {attempt}")
        migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying revision {revision}, trip {attempt}")

    after = stored(empty_database, metadata_tables, compared)
    what = f"two downgrades to {below} and two upgrades back"
    for name in compared:
        assert_rows_are_unchanged(after[name], before[name], name, what)
