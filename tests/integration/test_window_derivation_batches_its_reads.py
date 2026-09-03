"""E2-16 criterion 4 — window derivation reads once, not once per section.

> `derive_windows_for_all_sections` issues a bounded statement count (measured,
> not 5N+1) with behavior unchanged — same windows derived.

The epic-boundary data-model review measured the all-sections derivation at
**5N+1** round trips: three queries per section — its term, that term's weeks,
its existing windows — plus a savepoint pair each, most of them refetching the
same term's rows. At 500 sections on the hourly beat that is 2,501 statements an
hour to derive a calendar that changes when a term does.

**What is asserted is that the reads do not grow with the sections**, which is
what "batch the reads" means and is the half of the count that is a per-row loop.
The writes are left alone deliberately: the ticket keeps the per-section write
containment — "Batch the reads; keep the per-section write containment" — so a
savepoint pair per section is the design rather than the defect, and a test that
counted every statement would refuse the shape the ticket asks for.

**Measured over two derivations of different sizes, in one database.** An
absolute number would be a claim about how many reads a batched implementation
needs, which is the implementer's to choose; the criterion is that adding
sections adds none. Three sections, then nine.

**The equivalence half compares the two writers against each other**, not
against a table of instants. `derive_windows_for_section` is E2-06's per-section
writer, and what it produces is pinned against SPEC §3.1's rhythm by
`tests/integration/test_survey_windows_derive_from_the_term_calendar.py` and the
hand-written calendar in `tests/fixtures/survey_windows.py`. So it is an oracle
this ticket did not write, and comparing the batched derivation against it says
"same windows derived" without this module holding a second copy of the calendar
(`docs/MISTAKES.md` entry 19).

The statement recorder is `tests/fixtures/statements.py`; its control is the
first test here, and a red there means this module's instrument is broken rather
than the service.
"""

from typing import Any

import pytest
from fixtures.statements import reads, statements_recorded
from fixtures.survey_windows import (
    SURVEY_WINDOW_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
)
from sqlalchemy import delete, text

pytestmark = pytest.mark.integration

# The one writer this criterion is about. `scripts/seed.py` calls it as
# `derive_windows_for_all_sections(session, settings=Settings())`, which is the
# whole of its interface as any caller in the tree uses it.
DERIVE_ALL_FUNCTION = "derive_windows_for_all_sections"
DERIVE_ONE_FUNCTION = "derive_windows_for_section"

# The sections the two measured runs cover: three, then those three and six more.
# Distinct cohort letters, because a section's code is `{startLetter}1WW` here and
# E0-06 makes a start position unique within a term. Five lengths and five
# starting weeks between them, so a derivation cannot be reading one shape.
FIRST_COHORTS = ("U", "E", "V")
FURTHER_COHORTS = ("R", "Q", "F", "H", "X", "Y")

# What the recorder must see when it is shown one statement, for its own control.
A_STATEMENT = text("SELECT 1")


def derive_all(service: Any, session: Any, settings: Any) -> Any:
    """Run the all-sections derivation, or fail naming the function that is missing."""
    function = getattr(service, DERIVE_ALL_FUNCTION, None)
    if not callable(function):
        pytest.fail(
            f"`app.services.survey_windows` exposes no callable `{DERIVE_ALL_FUNCTION}`; it "
            f"exposes {sorted(name for name in vars(service) if not name.startswith('_'))}. "
            "`scripts/seed.py` imports it by that name and the hourly beat calls it, so a rename "
            "is a change to both."
        )
    return function(session, settings=settings)


def derive_one(service: Any, session: Any, section: Any, settings: Any) -> Any:
    """Run E2-06's per-section writer over one section."""
    return getattr(service, DERIVE_ONE_FUNCTION)(session, section, settings=settings)


def windows_by_cohort(calendar: Any, sections: dict[str, Any]) -> dict[str, list[tuple[Any, ...]]]:
    """Every section's derived windows as `(term week, opens_at, closes_at)`, by cohort."""
    return {
        letter: [
            (window["term_week"], window[WINDOW_OPENS_COLUMN], window[WINDOW_CLOSES_COLUMN])
            for window in calendar.windows_of(section)
        ]
        for letter, section in sections.items()
    }


def test_the_statement_recorder_sees_a_statement_it_was_shown(db_session: Any) -> None:
    """The control on this module's instrument. **A red here means the test is broken.**

    Both measurements below are counts of what the recorder saw. A recorder that
    saw nothing reports zero reads for three sections and zero for nine, and the
    equality that is this ticket's criterion passes against every implementation
    there has ever been — the emptiest version of `docs/MISTAKES.md` entry 3.

    One statement is sent and one read has to be counted.
    """
    with statements_recorded() as recorded:
        db_session.execute(A_STATEMENT)

    assert recorded, (
        "The recorder saw no statements at all while one was executed on the test session. It "
        "listens for `before_cursor_execute` on the `Engine` class; nothing at all means it is "
        "listening in the wrong place, and every count below would be zero for the same reason."
    )
    assert len(reads(recorded)) == 1, (
        f"The recorder counted {len(reads(recorded))} reads while exactly one `SELECT` was sent: "
        f"{[statement.sql for statement in recorded]}. The measurement below is a difference "
        "between two of these counts, so a reader that miscounts a lone `SELECT` cannot measure a "
        "per-section loop either."
    )


def test_deriving_over_three_times_as_many_sections_issues_no_more_reads(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Criterion 4: the read count does not grow with the number of sections.

    One term, three sections, one derivation — then six more sections and a
    second derivation over all nine. The reads the second run issues have to be
    the reads the first one issued.

    **The mutation this must kill, and it is the state of the code today:** a
    loop that reads the section's term, that term's weeks and the section's
    existing windows once per section. It is invisible at the three sections a
    test usually seeds and it is 1,500 reads an hour at 500, refetching one
    term's eighteen week rows for every section in it.

    **The near miss it must survive:** batching the *weeks* and leaving the term
    lookup per section, or the reverse. Either halves the count and leaves it
    growing with N, so the assertion is equality between the two runs rather than
    a ceiling on either.

    **Writes are not counted**, deliberately: the ticket keeps the per-section
    savepoint containment, so statements that grow with the sections are expected
    there and a total-statement bound would refuse the design the ticket asks
    for.

    **What could make this red for an honest reason:** an implementation that
    batches its reads in chunks — one read per hundred terms, say — would grow by
    one read somewhere past the ninth section. Nothing in this ticket asks for
    chunking and the whole seeded estate is one term, so equality is the
    criterion; a deliberate chunked design is a line to change here and a
    sentence in the pull request.
    """
    calendar = fall_2026.build()
    for letter in FIRST_COHORTS:
        calendar.section(letter)

    with statements_recorded() as first:
        derive_all(survey_window_service, db_session, window_settings)

    for letter in FURTHER_COHORTS:
        calendar.section(letter)

    with statements_recorded() as second:
        derive_all(survey_window_service, db_session, window_settings)

    first_reads, second_reads = reads(first), reads(second)
    assert first_reads, (
        "The first derivation issued no reads at all, so there is nothing for the second to be "
        "compared against — the derivation has to look at the sections, their term and its weeks "
        "before it can write anything. Either it did not run or the recorder is blind; the control "
        "above is where the second is diagnosed."
    )
    assert len(second_reads) == len(first_reads), (
        f"Deriving over {len(FIRST_COHORTS) + len(FURTHER_COHORTS)} sections issued "
        f"{len(second_reads)} reads where {len(FIRST_COHORTS)} sections issued {len(first_reads)} "
        f"— {len(second_reads) - len(first_reads)} more for "
        f"{len(FURTHER_COHORTS)} more sections.\n\nThe reads the second run made:\n  "
        + "\n  ".join(statement.sql for statement in second_reads)
        + "\n\nE2-16 criterion 4: the derivation was measured at 5N+1 round trips — the term, its "
        "weeks and the existing windows fetched once per section — which is 2,501 statements an "
        "hour at 500 sections, most of them refetching the same term. Batching the reads makes "
        "this count the same for three sections and for nine; the per-section savepoint writes "
        "stay, and are not counted here."
    )


def test_the_batched_derivation_writes_the_windows_the_per_section_writer_writes(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """Criterion 4's other half: same windows derived. Green today, and it stays green.

    Nine cohorts of five different lengths and five different starting weeks are
    derived twice over the same term and the same section rows: once through
    `derive_windows_for_all_sections`, then — with every window deleted — once
    per section through `derive_windows_for_section`. The two sets have to be
    identical, window for window, cohort by cohort.

    **Why the per-section writer is the oracle.** What it produces is pinned
    against SPEC §3.1's rhythm and the hand-written Fall 2026 calendar by E2-06's
    own suite, so it is an expectation this ticket did not author. A copy of the
    calendar here would be a second implementation for the batched one to agree
    with (`docs/MISTAKES.md` entry 19), and it would agree with any mistake this
    module made too.

    **The mutation this must kill:** a batched read that groups by the wrong key.
    Reading every week of every term into one map and handing each section the
    *first* term's weeks derives a full, plausible, wrong calendar for every
    section but one — no error, no empty result, and the count of windows per
    section unchanged. The cohorts here start in five different term weeks
    precisely so that an offset resolved once shows up.

    **The near miss it must survive:** a derivation that writes nothing at all
    the second time because the windows are already there. Every window is
    deleted between the two runs, and both sides are asserted non-empty.
    """
    calendar = fall_2026.build()
    sections = {letter: calendar.section(letter) for letter in (*FIRST_COHORTS, *FURTHER_COHORTS)}

    derive_all(survey_window_service, db_session, window_settings)
    batched = windows_by_cohort(calendar, sections)

    db_session.execute(delete(metadata_tables[SURVEY_WINDOW_TABLE]))
    db_session.expire_all()
    emptied = windows_by_cohort(calendar, sections)
    assert not any(emptied.values()), (
        f"Windows survived the delete between the two derivations: {emptied}. The second half has "
        "to write its own rows rather than read the first half's, or this compares a set with "
        "itself."
    )

    for section in sections.values():
        derive_one(survey_window_service, db_session, section, window_settings)
    per_section = windows_by_cohort(calendar, sections)

    assert all(per_section.values()), (
        f"The per-section writer derived no windows for at least one cohort: "
        f"{ {letter: len(windows) for letter, windows in per_section.items()} }. It is the oracle "
        "this comparison rests on, so an empty side makes the equality below meaningless — and a "
        "red here is E2-06's suite's subject rather than this ticket's."
    )
    assert batched == per_section, (
        "The two writers derived different windows over the same sections.\n"
        f"  batched:     { {letter: len(windows) for letter, windows in batched.items()} }\n"
        f"  per section: { {letter: len(windows) for letter, windows in per_section.items()} }\n"
        f"  cohorts that differ: "
        f"{sorted(letter for letter in batched if batched[letter] != per_section[letter])}\n\n"
        "E2-16 criterion 4 asks for the batched reads *and* unchanged behaviour. A batch that "
        "resolves one term's weeks and hands them to every section derives a full and plausible "
        "calendar that is wrong for every section but one — which is why the comparison is per "
        "cohort and over the instants rather than over the count."
    )
