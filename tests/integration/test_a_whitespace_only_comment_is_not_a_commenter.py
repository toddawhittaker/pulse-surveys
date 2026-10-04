"""A comment of nothing but whitespace does not count toward the threshold — E5.1-12, Part B item 5.

SPEC §4 counts the n-threshold in distinct students *commenting* in one stream in
one week, and §4.1 item 3 hides a stream's raw comments below it. A student whose
answer is spaces and line breaks has said nothing, and counting them as a
commenter lets four real authors be shown as if they were five — the reader then
knows the four visible comments are the whole stream, which is the narrowing the
threshold exists to prevent (`docs/MISTAKES.md` entry 50: a threshold crossed by
a count of something else).

**The whitespace answer is planted straight into `answer`**, past the write path's
strip, because the write path is the layer that would otherwise make it
unreachable: a guard is a guard only once something has been thrown at it
(`tests/fixtures/report_comments.py::CommentWorld.comment_text_under_another_kind`
gives the same argument for the view's kind predicate). It is classified like a
real comment, so the only thing that distinguishes it from the four beside it is
its text, and a green names the count's treatment of blank text rather than a
missing classification.

**The rule the view's blank-text predicate has to hold is "blank exactly when
Python's `str.strip()` would leave nothing"**, because the write path drops a
comment on that test and the view is its read-side twin. The last test in this
module checks the view file's pattern against every character `str.strip()`
removes, under the database's own collation and under `COLLATE "C"`, so the rule
does not quietly depend on which locale a database was created with.

**Marked `invariant`**: §4.1 item 3, in the isolated pass where a skip fails CI.
"""

import re
from typing import Any

import pytest
from fixtures.repo import BACKEND_DIR
from fixtures.report_comments import CommentWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Two term weeks inside cohort `F`'s run (term weeks 7 to 12), both closed in 2020
# by `CommentWorld.close_week`, so neither turns on the date CI runs.
THIN_WEEK = 7
CONTROL_WEEK = 8

# Spaces, a tab and line breaks: what a textarea holds when somebody presses keys
# and writes nothing. Not empty — an empty string is a different row, and E2-05
# stores a blank optional comment as no row at all.
ONLY_WHITESPACE = "   \t\n  \n "

# What Python's `str.strip()` removes but PostgreSQL's `[:space:]` keeps under
# `en_US.utf8` (docs/disputes/E5.1-12-01.md): U+001C to U+001F, the next-line
# character, the no-break space, the figure space and the narrow no-break space.
ONLY_PYTHON_WHITESPACE = "\u001c\u001d\u001e\u001f\u0085\u00a0\u2007\u202f"

# Spaces outside ASCII that Python's `str.strip()` removes and that PostgreSQL's
# `[:space:]` covers under `en_US.utf8` but not under `COLLATE "C"`: the Ogham
# space mark, the em space, the line and paragraph separators, the medium
# mathematical space and the ideographic space. Written as escapes, never as the
# characters themselves (ruff RUF001).
ONLY_UNICODE_SPACES = "\u1680\u2003\u2028\u2029\u205f\u3000"

# The view file whose blank-text pattern the last test reads. The pattern is read
# out of the file rather than copied here, so the test follows whatever the file
# says; what it is checked *against* is built from Python, never from the file.
REPORT_COMMENT_VIEW_FILE = BACKEND_DIR / "app" / "views_sql" / "report_comment_v003.sql"

# Every character Python's `str.strip()` removes, built from Python itself. NUL is
# left out because PostgreSQL text cannot hold it (and `chr(0)` keeps it anyway).
PYTHON_WHITESPACE = [code for code in range(0x110000) if chr(code).strip() == "" and code]

# Characters that are real text and must count as something written: a letter, an
# accented letter, and the zero-width space, which looks blank but which Python's
# `str.strip()` keeps \u2014 so the write path keeps it and the view must too.
REAL_CHARACTERS = {"a": ord("a"), "e-acute": 0x00E9, "zero-width-space": 0x200B}

# The ideographic space: one of the characters `[:space:]` misses under `C`.
IDEOGRAPHIC_SPACE = 0x3000

A_LABEL = "the lab instructions changed between the handout and the session"


def plant(
    world: CommentWorld,
    *,
    term_week: int,
    real: int,
    blank: int,
    stream: str,
    blank_text: str = ONLY_WHITESPACE,
) -> None:
    """`real` students with a real comment and `blank` with `blank_text` only, in one stream."""
    world.close_week(term_week)
    for index in range(real):
        world.submit(
            term_week=term_week, comments={stream: f"{A_LABEL} (week {term_week}, {index + 1})"}
        )
    for _ in range(blank):
        world.submit(term_week=term_week, comments={stream: blank_text})


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(ONLY_WHITESPACE, id="ascii-whitespace"),
        pytest.param(ONLY_PYTHON_WHITESPACE, id="python-strip-only-characters"),
        pytest.param(ONLY_UNICODE_SPACES, id="unicode-spaces"),
    ],
)
def test_four_real_commenters_and_one_whitespace_answer_leave_the_stream_suppressed(
    comment_world: CommentWorld, comment_contract: Any, answer: str
) -> None:
    """Threshold minus one real commenters plus one whitespace-only answer: suppressed, nothing shown.

    At SPEC §4's default of five, four students wrote something about the
    instructor and a fifth submitted only whitespace. The stream holds four
    commenters, below five, so `stream_is_suppressed` answers true and
    `visible_comments` returns nothing.

    **The control, in the same world:** a second week with the threshold's number
    of real commenters is shown — `visible_comments` returns all of them and
    `stream_is_suppressed` answers false. So an empty answer for the thin week is
    the threshold holding, not a read that answers nothing. And the raw count of
    non-null comment answers in the thin week is read back and required to *reach*
    the threshold, so the whitespace answer is certainly the one that decides it.

    **The mutation that must turn this red:** the blank-text exclusion removed from
    the distinct-commenter count — in `backend/app/services/report_comments.py`'s
    `_commenters_by_stream_week` (ADR 0182), or in the `report_comment` view it
    reads, whichever of the two holds a `btrim(comment_text) <> ''`-shaped
    predicate at HEAD. The count then reaches five, the stream is shown, and its
    four real comments (and the blank one) come back. **The near miss that stays
    green:** the same predicate written as `comment_text ~ '\\S'`, which excludes
    the same row.

    **Three blank answers.** The ASCII case (spaces, a tab, line breaks) kills
    "the one-argument `btrim`" put back into the view. The second case is made
    only of the characters Python's `str.strip()` removes and PostgreSQL's
    `[:space:]` keeps under `en_US.utf8` (U+001C to U+001F, U+0085, U+00A0,
    U+2007, U+202F); it kills "v003's character class reverts to `[^[:space:]]`".
    The third is spaces outside ASCII (U+1680, U+2003, U+2028, U+2029, U+205F,
    U+3000) that `[:space:]` covers under `en_US.utf8` and misses under
    `COLLATE "C"`. On this project's database image, whose collation is
    `en_US.utf8`, no mutation of the class turns the third case red; it is here
    so the end-to-end read is shown to hold for them, and the last test in this
    module is the one that can fail on them. All three are green at the head
    this was written against. Each planted answer is first required to satisfy
    `answer.strip() == ""`, so the test proves the write path would have treated
    it as blank.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; nothing is below it."
    stream = contract.instructor_stream
    world.build()
    assert answer.strip() == "", (
        "The planted answer must be blank to the write path's `str.strip()`, or this test "
        "plants a comment the write path would have kept."
    )
    plant(world, term_week=THIN_WEEK, real=threshold - 1, blank=1, stream=stream, blank_text=answer)
    plant(world, term_week=CONTROL_WEEK, real=threshold, blank=0, stream=stream)

    raw_thin = world.commenters_in(term_week=THIN_WEEK, stream=stream)
    raw_control = world.commenters_in(term_week=CONTROL_WEEK, stream=stream)
    assert (raw_thin, raw_control) == (threshold, threshold), (
        f"The thin week holds {raw_thin} students with a non-null comment and the control week "
        f"{raw_control}; this test planted {threshold} in each ({threshold - 1} real plus one "
        f"whitespace-only, and {threshold} real). Counted without regard to the text, the thin week "
        "reaches the threshold — that is what makes the whitespace answer the deciding one."
    )

    def ask(term_week: int) -> tuple[Any, Any]:
        arguments = {
            "section_id": world.section_id(),
            "week_id": world.week_id(term_week),
            "stream": stream,
        }
        return (
            contract.is_suppressed()(world.session, **arguments),
            tuple(contract.visible()(world.session, **arguments)),
        )

    control_suppressed, control_shown = ask(CONTROL_WEEK)
    assert control_suppressed is False and len(control_shown) == threshold, (
        f"The control week, with {threshold} real commenters, answered suppressed="
        f"{control_suppressed!r} and {len(control_shown)} comments. It is at the threshold and "
        "SPEC §4 shows it; until it is shown, the thin week's emptiness below is what this read "
        "gives every week."
    )

    thin_suppressed, thin_shown = ask(THIN_WEEK)
    assert thin_suppressed is True, (
        f"`{contract.suppressed_name}` answered {thin_suppressed!r} for a week with "
        f"{threshold - 1} real commenters and one whitespace-only answer. A student who wrote "
        "nothing is not a commenter; counting them crosses SPEC §4's threshold with four authors."
    )
    assert thin_shown == (), (
        f"The thin week's stream showed {[comment.text for comment in thin_shown]!r}. "
        f"{threshold - 1} real authors are below the threshold of {threshold}, and the reader of "
        "these comments would know they are the stream's whole content."
    )


def the_views_pattern_literal() -> str:
    """The one regular-expression literal in the v003 view file, quotes included, as written.

    SQL comments are removed first, so a pattern quoted in the file's prose is not
    mistaken for the predicate. Exactly one `~ '...'` literal must remain; any
    other number means the file has changed shape and this reader has to be
    rewritten, which is a failure that says so rather than a guess.
    """
    if not REPORT_COMMENT_VIEW_FILE.is_file():
        pytest.fail(
            f"`{REPORT_COMMENT_VIEW_FILE.relative_to(BACKEND_DIR.parent)}` does not exist. The "
            "dispute E5.1-12-01 ruling puts the comment view's blank-text predicate there."
        )
    source = REPORT_COMMENT_VIEW_FILE.read_text(encoding="utf-8")
    without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    without_comments = re.sub(r"--[^\n]*", "", without_comments)
    literals = re.findall(r"~\s*([Ee]?'(?:[^']|'')*')", without_comments)
    if len(literals) != 1:
        pytest.fail(
            f"The view file holds {len(literals)} regular-expression literals outside comments "
            f"({literals!r}); this test reads exactly one, the blank-text predicate. If the "
            "predicate is now written another way, this reader changes with it."
        )
    return literals[0]


@pytest.mark.parametrize(
    "collation",
    [
        pytest.param("", id="database-default-collation"),
        pytest.param('COLLATE "C"', id="c-collation"),
    ],
)
def test_the_views_blank_text_pattern_treats_every_python_whitespace_character_as_blank(
    db_session: Any, collation: str
) -> None:
    """Every character Python's `str.strip()` removes is blank to the view; real characters are not.

    The write path drops a comment whose `str.strip()` is empty, and the view's
    blank-text predicate is its read-side twin (dispute E5.1-12-01's ruling), so
    the two must agree character by character. This asks PostgreSQL directly:
    for each code point in Python's whitespace set (built in this test from
    Python, never from the file), does a one-character text match the view's
    pattern? Every answer must be no. And for a letter, an accented letter and
    the zero-width space (which Python keeps), every answer must be yes, so a
    pattern that matches nothing at all cannot pass.

    **Under both the database's default collation and `COLLATE "C"`.** A
    `[:space:]` class means a different set of characters depending on the
    collation of the text it reads, and a database created under `C` or an ICU
    locale would read the same view file differently. The predicate has to hold
    under `C` too, so the rule does not depend on how a database was created.

    **What this reproduces of the view, and what it does not** (`docs/MISTAKES.md`
    entry 37). The literal is copied into the query exactly as the file writes
    it, quotes and any `E` prefix included, so PostgreSQL's string parser
    handles it the same way it does when the view is created. The text it is
    matched against is `chr(code)` rather than a stored `comment_text`; both are
    `text` under the database default collation, and the `COLLATE "C"` case
    states its collation on the text, as a column under a `C` database would
    carry it.

    **A guard that the `C` case is a real condition.** Under `COLLATE "C"` the
    test first requires that `[^[:space:]]` alone counts the ideographic space as
    text. If that were not so, the `C` case would be the default case again and a
    green would say nothing about collation.

    **The mutation it kills:** the class goes back to `[^[:space:]...]` (a
    `[:space:]` class plus extra escapes). Under `C`, `[:space:]` misses fifteen
    characters Python strips — U+1680, U+2000 to U+2006, U+2008 to U+200A,
    U+2028, U+2029, U+205F and U+3000 — so the `c-collation` case is RED at the
    head this was written against and turns green when the class becomes an
    explicit list of every character `str.strip()` removes. The
    `database-default-collation` case is green at that head and stays green.
    """
    from sqlalchemy import text

    literal = the_views_pattern_literal()

    if collation:
        guard = db_session.execute(
            text(f"SELECT (chr(:code) {collation}) ~ '[^[:space:]]'"),
            {"code": IDEOGRAPHIC_SPACE},
        ).scalar_one()
        assert guard is True, (
            f"Under {collation}, PostgreSQL's `[^[:space:]]` treats U+3000 as blank, so this "
            "collation covers the same spaces as the database default and this case tests "
            "nothing the other does not."
        )

    # The literal is the repository's own file, copied as written; nothing here
    # comes from outside the repository.
    predicate = f"(chr(code) {collation}) ~ {literal}"
    matching = text(
        f"SELECT code FROM unnest(CAST(:codes AS integer[])) AS code WHERE {predicate}"  # noqa: S608
    )

    counted_as_text = sorted(
        row[0] for row in db_session.execute(matching, {"codes": PYTHON_WHITESPACE})
    )
    real_codes = list(REAL_CHARACTERS.values())
    real_as_text = {row[0] for row in db_session.execute(matching, {"codes": real_codes})}

    missed_real = [name for name, code in REAL_CHARACTERS.items() if code not in real_as_text]
    assert not missed_real, (
        f"The view's pattern {literal} treats {missed_real} as blank. Each is real text that "
        "Python's `str.strip()` keeps, so the write path stores it and the view must count its "
        "author. A pattern that refuses these refuses real comments."
    )
    assert not counted_as_text, (
        f"With {collation or 'the database default collation'}, the view's pattern {literal} "
        f"counts {[f'U+{code:04X}' for code in counted_as_text]} as real text. Python's "
        "`str.strip()` removes every one of them, so the write path would have dropped a comment "
        "made only of them, and the view counts its author as a commenter — which can cross "
        "SPEC §4's threshold with one author fewer than it names."
    )
