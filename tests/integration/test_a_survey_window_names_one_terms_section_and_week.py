"""A survey window's section and its week belong to the same term — ticket E2-05.

Acceptance criterion 2, and nothing else: "A `survey_window` naming a week from
another term is refused by the composite key — attempted in a test, both
directions."

The rule is ADR 0018's, deferred by name in its own closing consequence —
"`survey_window` has one available and does not take it: nothing yet stops a
window pairing a section in one term with a week in another… Deferred to E2 with
the scheduling logic". This ticket takes it, so that consequence stops being
true the moment the migration lands (`docs/MISTAKES.md` entry 1), and the ADR is
amended in the same pull request. These tests are what make the taking real.

**A module of its own rather than an addition to
`test_term_calendar_schema.py`.** That module holds E0-06 and the three
measurements ADR 0018 rests on, all of them about `week` and
`start_letter_map`; this is a rule on a third table, landed by a different
ticket, and a red here should name E2-05 without anyone opening a file.
`test_survey_schema.py` next door holds the four tables this ticket creates, and
`survey_window` is not one of them.

**Both limbs are attempted separately, and each is isolated by the term the
window itself claims.** The mechanism is two composite foreign keys —
`(section_id, term_id) → section (id, term_id)` and `(week_id, term_id) → week
(id, term_id)` — and a test that only ever writes a disagreeing pair cannot say
which of the two refused it, so a schema carrying one of the two would pass. In
both tests below the window claims **term A**, and exactly one of its two
references belongs to term B: the limb whose row is in the other term is the
only thing that can refuse, and dropping that limb turns exactly one of these
two tests red.

**Every insert here names its section, its week and its term explicitly.** The
shared seeding walker can fill a composite key by following it, and does so for
every other caller; doing that here would make these tests depend on how the
walker resolves a column with two foreign keys, and a change there would move
what they measure. The rows are built by the walker, the window is composed by
hand.

**Nothing here names a constraint**, for the reason `test_term_calendar_schema.py`
sets out: a name in this schema is produced by `Base.metadata`'s naming
convention rather than chosen, so holding one would report a rename as a
regression. What is asserted is the criterion — the server refuses the row.
"""

from typing import Any

import pytest
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# E0-06 created this table and SPEC §8 lists it. Not this ticket's name.
SURVEY_WINDOW = "survey_window"

# The three columns a window's term rule is written over. `section_id` and
# `week_id` are E0-06's; `term_id` is what E2-05 adds, and it is the column ADR
# 0018 names in the consequence this ticket closes.
SECTION_COLUMN = "section_id"
WEEK_COLUMN = "week_id"
TERM_COLUMN = "term_id"
WINDOW_KEY_COLUMNS = (SECTION_COLUMN, WEEK_COLUMN, TERM_COLUMN)


def window_table(tables: dict[str, Any]) -> Any:
    """The declared `survey_window` table, or a failure saying it is not there."""
    table = tables.get(SURVEY_WINDOW)
    if table is None:
        pytest.fail(
            f"There is no `{SURVEY_WINDOW}` table (what is there: {sorted(tables)}). E0-06 "
            "created it in `backend/app/models/term.py` and E2-05 adds its term rule; "
            "`tests/integration/test_term_calendar_schema.py` is where a missing calendar table "
            "is diagnosed."
        )
    return table


def require_columns(table: Any, names: tuple[str, ...]) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have.

    `term_id` is the one this will report while E2-05 is unbuilt, and that is
    the intended red: the column is the whole of what the ticket adds here, and
    a message naming it is more use than an insert failing on an unknown
    keyword inside the seeding walker.
    """
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. E2-05 adds `{TERM_COLUMN}` to "
            f"`{SURVEY_WINDOW}`, non-nullable, and replaces the two plain foreign keys with the "
            "composite ones ADR 0018 prescribes. Each name is a constant at the top of this "
            "file, so a deliberate rename is a one-line change here."
        )


def one_terms_section_and_week(seed: Any) -> dict[str, Any]:
    """A section and a week that certainly sit in the same term, with that term.

    Built through one chain, which is what puts them in one term: the walker
    creates the term while it is building the section's ancestors and the week
    then finds it already there. The term row is returned beside them so a
    caller can name it in a window rather than reading it back off either.
    """
    chain: dict[str, Any] = {}
    section = seed("section", chain)
    week = seed("week", chain)
    return {"section": section, "week": week, "term": chain["term"], "chain": chain}


def write_window(seed: Any, *, section: Any, week: Any, term: Any) -> Any:
    """Insert one `survey_window` naming exactly these three rows."""
    return seed(
        SURVEY_WINDOW,
        {},
        **{
            SECTION_COLUMN: section["id"],
            WEEK_COLUMN: week["id"],
            TERM_COLUMN: term["id"],
        },
    )


def test_the_helper_builds_a_section_and_a_week_that_really_share_a_term(
    seed_rows: Any,
) -> None:
    """The control on this module's own machinery, and it is green today.

    Every test below rests on `one_terms_section_and_week` producing a section
    and a week of **one** term: the accepted case is only meaningful if they
    agree, and each refused case is only isolated to one limb if the other limb
    is satisfied. The helper gets that by sharing a chain, which is a property
    of the seeding walker rather than of anything this file wrote — so it is
    asserted rather than assumed, and asserted here where the failure says
    "the helper" instead of surfacing as a refused control three tests later.

    Green before E2-05 lands and green after: it names `section.term_id` and
    `week.term_id`, both of which E0-06 built, and no column this ticket adds.
    """
    rows = one_terms_section_and_week(seed_rows)

    term = rows["term"]["id"]
    assert rows["section"]["term_id"] == term, (
        f"The seeded section belongs to term {rows['section']['term_id']} and the helper "
        f"reports {term}. Every window written in this module names that term, so a mismatch "
        "here would make the accepted case a cross-term window and both refusals ambiguous."
    )
    assert rows["week"]["term_id"] == term, (
        f"The seeded week belongs to term {rows['week']['term_id']} and the helper reports "
        f"{term}. The two rows are seeded through one chain precisely so they land in one term; "
        "if they do not, this module is measuring two cross-term windows and calling one of "
        "them the control."
    )


def test_a_window_whose_section_and_week_share_a_term_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The ordinary window, and the control both refusals below depend on.

    A test of its own as well as a guard inside each refusal, because a schema
    that refused every window would satisfy both refusals perfectly and would
    also make E2-06 unable to write a single row (`docs/MISTAKES.md` entry 3).
    This is the failure that would name that.

    **The mutation it kills:** a composite key written against the wrong
    referenced columns, or a `term_id` that references `term` directly while the
    two limbs go on referencing `section (id)` and `week (id)` — either leaves
    the honest row refused or the dishonest row accepted, and this half catches
    the first.
    """
    require_columns(window_table(metadata_tables), WINDOW_KEY_COLUMNS)

    rows = one_terms_section_and_week(seed_rows)
    try:
        with db_session.begin_nested():
            write_window(seed_rows, section=rows["section"], week=rows["week"], term=rows["term"])
    except DatabaseError as rejected:
        pytest.fail(
            f"A survey window naming a section and a week of one term, and claiming that term, "
            f"was refused: {rejected}. That is every window E2-06 will ever open — SPEC §3.1 "
            "gives each section one window per active week — so a schema that refuses it refuses "
            "the weekly cycle, and the two refusals in this module would then be evidence of "
            "nothing."
        )


def test_a_window_whose_week_belongs_to_another_term_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 2, the week limb: `(week_id, term_id) → week (id, term_id)`.

    The window claims term A and names a section of term A, so the section limb
    is satisfied; its week belongs to term B, so no `week` row carries that id
    with term A and the week limb is the only thing that can refuse it. **The
    section limb being satisfied is the whole design of the case**: a window
    disagreeing with its term on both references would be refused by either
    limb alone, and a schema carrying only one of the two would pass it.

    **The control is a window over term A's own week**, so a refusal here cannot
    be about windows being unwritable.

    **The mutation it kills:** shipping the section limb and leaving `week_id` a
    plain foreign key. **The near miss it tolerates:** none — the two limbs are
    separated by the sibling test below, which fails on the opposite mutation.

    Why it matters beyond tidiness: SPEC §2.2 puts the week axis inside a term,
    so a window keyed to another term's week 3 opens a section's survey against
    a week its own calendar does not contain, and §3.4's participation
    denominator — "valid weeks completed ÷ weeks elapsed" — is then counted over
    two different calendars.
    """
    require_columns(window_table(metadata_tables), WINDOW_KEY_COLUMNS)

    home = one_terms_section_and_week(seed_rows)
    elsewhere = one_terms_section_and_week(seed_rows)
    assert elsewhere["term"]["id"] != home["term"]["id"], (
        "The second chain was seeded into the same term as the first, so its week is not from "
        "another term and this test would attempt an ordinary window. The walker shares only the "
        "single institution row between chains; a shared term means that has changed."
    )

    try:
        with db_session.begin_nested():
            write_window(seed_rows, section=home["section"], week=home["week"], term=home["term"])
    except DatabaseError as rejected:
        pytest.fail(
            f"The control window — a section and a week of one term — was refused: {rejected}. "
            "Until an ordinary window inserts, the refusal below says nothing about the week's "
            "term."
        )

    crossed = False
    try:
        with db_session.begin_nested():
            write_window(
                seed_rows, section=home["section"], week=elsewhere["week"], term=home["term"]
            )
    except DatabaseError:
        crossed = True

    assert crossed, (
        "A survey window was written pairing a section of one term with a week of another. ADR "
        "0018 names this as the rule `survey_window` had available and did not take, deferred to "
        "E2, and E2-05's second criterion takes it: the composite key "
        f"`({WEEK_COLUMN}, {TERM_COLUMN})` finds no week of this window's term with that id. The "
        "window's section is in the term it claims, so the section limb accepts this row — only "
        "the week limb can refuse it, which is why a schema carrying one composite key and one "
        "plain foreign key fails here and passes everywhere else."
    )


def test_a_window_whose_section_belongs_to_another_term_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 2, the section limb: `(section_id, term_id) → section (id, term_id)`.

    The mirror of the test above and the reason the criterion says "both
    directions". The window claims term A and names a week of term A, so the
    week limb is satisfied; its section belongs to term B, so the section limb
    is the only thing that can refuse it.

    **The mutation it kills:** shipping the week limb and leaving `section_id` a
    plain foreign key — and, one step further out, dropping `UNIQUE (id,
    term_id)` from `section`, which is what the section limb references and
    without which it cannot exist at all.

    A section belongs to exactly one term (SPEC §8, and E0-06 landed
    `section.term_id` to say so), so a window naming another term's section is a
    window for a section that is not running then.
    """
    require_columns(window_table(metadata_tables), WINDOW_KEY_COLUMNS)

    home = one_terms_section_and_week(seed_rows)
    elsewhere = one_terms_section_and_week(seed_rows)
    assert elsewhere["term"]["id"] != home["term"]["id"], (
        "The second chain was seeded into the same term as the first, so its section is not from "
        "another term and this test would attempt an ordinary window."
    )

    try:
        with db_session.begin_nested():
            write_window(seed_rows, section=home["section"], week=home["week"], term=home["term"])
    except DatabaseError as rejected:
        pytest.fail(
            f"The control window — a section and a week of one term — was refused: {rejected}. "
            "Until an ordinary window inserts, the refusal below says nothing about the "
            "section's term."
        )

    crossed = False
    try:
        with db_session.begin_nested():
            write_window(
                seed_rows, section=elsewhere["section"], week=home["week"], term=home["term"]
            )
    except DatabaseError:
        crossed = True

    assert crossed, (
        "A survey window was written naming a section of one term and a week of another. The "
        f"composite key `({SECTION_COLUMN}, {TERM_COLUMN})` finds no section of this window's "
        "term with that id. The window's week is in the term it claims, so the week limb accepts "
        "this row — only the section limb can refuse it."
    )


def test_a_survey_window_cannot_be_written_without_a_term(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """`survey_window.term_id` is NOT NULL, and that is what makes both limbs bite.

    **This is not a tidiness test.** A composite foreign key in Postgres is
    `MATCH SIMPLE` unless it says otherwise, and `MATCH SIMPLE` skips the check
    entirely when *any* column of the key is null. So a nullable `term_id` gives
    every writer a way to store the exact row criterion 2 refuses: leave the
    term out, and neither limb is evaluated. The two refusals above would go on
    passing, because they supply a term; nothing in this repository would say
    the door was open.

    **The control is an ordinary window**, written first through the same
    helper, so the refusal is known to be about the null rather than about
    anything else in the row.

    **The mutation it kills:** declaring `term_id` nullable — which is also the
    shape a "make the migration easier" change takes, since the table is empty
    in every environment and a non-null column needs no backfill only because
    of that.
    """
    require_columns(window_table(metadata_tables), WINDOW_KEY_COLUMNS)

    rows = one_terms_section_and_week(seed_rows)
    try:
        with db_session.begin_nested():
            write_window(seed_rows, section=rows["section"], week=rows["week"], term=rows["term"])
    except DatabaseError as rejected:
        pytest.fail(
            f"The control window was refused: {rejected}. Until an ordinary window inserts, the "
            "refusal below says nothing about the null."
        )

    without_a_term = False
    try:
        with db_session.begin_nested():
            seed_rows(
                SURVEY_WINDOW,
                {},
                **{
                    SECTION_COLUMN: rows["section"]["id"],
                    WEEK_COLUMN: rows["week"]["id"],
                    TERM_COLUMN: None,
                },
            )
    except DatabaseError:
        without_a_term = True

    assert without_a_term, (
        f"A survey window was written with `{TERM_COLUMN}` null. Postgres evaluates a composite "
        "foreign key under `MATCH SIMPLE`, which skips the check when any column of the key is "
        "null — so a nullable term column is a documented way around both of the rules criterion "
        "2 is about, and the two cross-term tests above would go on passing while every window "
        "written this way escaped them. E2-05 makes the column non-nullable, which the empty "
        "table permits without a backfill."
    )
