"""Neither the AGS call log nor the client's own log stream carries a student's figures — §4.1.

Two denials, extracted from
`tests/integration/test_the_ags_client_is_a_conformant_service_client.py` by
E3-08's boundary round (IC-M3) so that they sit inside CI's isolated §4.1 pass.
They are E3-04's criterion 8 forbidden state and its criterion 10, and the round
found them outside the pass that exists to guarantee denials are actually run.

**Why extracted rather than the whole module marked.** The module they came from
is 2,387 lines and asserts the client's whole conformance — media types, retries,
address judgment, timestamps. `scripts/ci/check_invariants.py` runs the §4.1 pass
in isolation precisely so that a confidentiality denial cannot be skipped or
collected empty without CI noticing, and a pass that dragged two thousand lines of
protocol conformance along with it would be neither lean nor obviously about
§4.1. Marking the whole module would also make every future test added there an
invariant by default, which is a claim nobody would be making deliberately.

**What each denies, and they are different surfaces.**

  - **The `ags_call` row.** SPEC §6.1 puts that table on an operator's console at
    the grain of one HTTP call. E3-04's settled decision 5 keeps it to `url`,
    `response_code`, `called_at` and `section_id` — "no score, no ledger, no user
    id in the row". A row that grew a `detail` or `note` column holding the posted
    percentage is a per-student record of academic standing on a screen §4 gives
    nobody the right to read.
  - **The log stream.** The same three values arriving somewhere nobody reviews: a
    worker's log, kept longer than any table, shipped to whatever aggregator a
    deployment runs, and read by whoever is on call. SPEC §4 makes
    re-identification reachable only through the Care queue and only with an audit
    row; a log line reaches it with neither.

**Both are asserted over the values rather than over the column or field names**
(`docs/MISTAKES.md` entry 2 — prefer asserting the forbidden state). A check made
against a list of allowed column names passes a column called `note`, and that is
exactly the shape a well-meaning "record why it failed" change takes.

**Each has its own non-vacuity guard, and they are the load-bearing half.** An
empty table satisfies every absence assertion about rows; an empty capture
satisfies every absence assertion about logs. So each test requires its subject to
have written *something* first, and reports a silent client as a broken test
rather than as a safe one (`docs/MISTAKES.md` entry 3).

**The originals are deleted in the same change.** Two copies of one denial is
`docs/MISTAKES.md` entry 13 — a rule maintained in one of the two places facing
it — and the copy outside the isolated pass would be the one that kept passing
while the marked one was skipped.
"""

import logging
from typing import Any

import pytest

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# `ags_client`, `ags_sections`, `ags_rows` and `ags_contract` come from
# `tests/fixtures/ags_client.py`; `service_wire` from
# `tests/fixtures/roster_sync.py`; `committed_rows` from the shared fixtures.


def drive(
    ags_client: Any,
    function: Any,
    section: Any,
    rows: Any,
    wire: Any,
    *,
    line_item: Any = None,
    grade: Any = None,
) -> tuple[Any, BaseException | None]:
    """Call one client entry point, answering what it returned and what escaped it.

    The conformance module's own driver, narrowed to the two roles these two tests
    need. Its two reasons are kept because both bear on what is asserted here:
    whether the client raises or returns on a refusal is settled nowhere and is
    asserted nowhere, so it is caught rather than allowed to fly; and the commit is
    attempted whichever way the call exited, because the `ags_call` row a *failure*
    writes is the row this module reads and a rollback would throw it away.
    """
    available: dict[str, Any] = {
        "session": rows.session,
        "section_id": section.id,
        "http": wire.session(),
    }
    if line_item is not None:
        available["line_item"] = line_item
    if grade is not None:
        available["user_id"] = grade.user_id
        available["score"] = grade.score
        available["ledger"] = grade.ledger
        available["timestamp"] = grade.timestamp

    answered: Any = None
    raised: BaseException | None = None
    try:
        answered = ags_client.call(function, **available)
    except Exception as failure:
        raised = failure
    try:
        rows.commit()
    except Exception:  # pragma: no cover - a broken transaction, not a branch
        rows.session.rollback()
    return answered, raised


def token_endpoint(platform: Any) -> str:
    """Where this platform issues access tokens, for the leg that makes a post fail."""
    document = platform.discovery() or {}
    url = document.get("token_endpoint")
    assert isinstance(url, str) and url, (
        f"The platform's discovery document advertises no `token_endpoint` (it carries "
        f"{sorted(document)}), so there is no endpoint for this test to fail and it could not pose "
        "its question."
    )
    return url


def forbidden_values(grade: Any) -> dict[str, str]:
    """The three strings neither surface may carry, each with the reason.

    Taken from the grade the caller handed the client, never composed here: what
    must not leak is the exact value this run passed in and the exact subject it
    passed it for.
    """
    return {
        "the score the caller handed over": grade.score,
        "a ledger line": grade.ledger.splitlines()[0],
        "the LMS user id": grade.user_id,
    }


def test_no_ags_call_row_carries_a_score_a_ledger_line_or_an_lms_user_id(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
) -> None:
    """E3-04 criterion 8's forbidden state, asserted over the values rather than the columns.

    "`ags_call` rows are written for successes and for failures, and carry no score
    value." Settled decision 5 widens that to what the row may hold at all: `url`,
    `response_code`, `called_at`, `section_id` — "no score, no ledger, no user id
    in the row".

    **The mutation this kills:** a value column added to the log — `detail`,
    `note`, `body`, `error` — holding what was being posted when the call was
    made. It is the natural shape of a "record why it failed" change, it passes
    every check made against a list of allowed column names, and it puts a
    per-student statement of academic standing on the §6.1 console.

    **Every value of every row is searched**, not a named subset, so a column this
    module has never heard of is covered the day it is added.

    **The guard first.** The rows are required to be non-empty, because a table
    with nothing in it satisfies every absence assertion below and would report a
    client that writes nothing as one that writes safely.
    """
    section = ags_sections()
    answered, raised = drive(
        ags_client, ags_client.find_or_create_line_item, section, committed_rows, service_wire
    )
    assert raised is None, f"Finding or creating the line item raised {raised!r}."

    grade = ags_contract.grade(section.subjects[0])
    _posted, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=answered,
        grade=grade,
    )
    assert raised is None, f"Posting the score raised {raised!r}."

    recorded = ags_rows.calls_for(section.id)
    assert recorded, (
        f"The client wrote no `{ags_contract.call_table}` row for this section, so every absence "
        "below is an absence in an empty table."
    )
    for row in recorded:
        rendered = " ".join(str(value) for value in row.values())
        for what, value in forbidden_values(grade).items():
            assert value not in rendered, (
                f"An `{ags_contract.call_table}` row carries {what} ({value!r}): {row!r}. Settled "
                "decision 5 keeps this log to the URL, the status, the instant and the section — a "
                "call log that grew a value column is a per-student record of standing on a table "
                "§6.1 puts on an operator's console."
            )


def test_nothing_the_client_logs_carries_a_score_a_ledger_line_or_an_lms_user_id(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E3-04 criterion 10, over what the code logs while it both succeeds and fails.

    "No log line emitted by this code contains a score, a ledger line, or an LMS
    user id, asserted by a test over what the code logs rather than by reading it."
    SPEC §4.1's model is about read paths, and this is the same value arriving
    somewhere nobody reviews: a worker's log stream, kept longer than any table and
    read by whoever is on call.

    **Both a success and a failure, because they log different things.** The line a
    failing post writes is where the body it was trying to send ends up — "posting
    %r failed" is the natural sentence and it carries the score, the ledger and the
    student's `sub` in one go. The failure here is a refused token, which is the one
    an operator will actually meet.

    **The whole record is searched, not `record.msg`.** `ags_contract.logged_text`
    renders the format arguments in, which is where a value hides from a check made
    against the template alone: `logger.info("posted %s", score)` has a template
    with no score in it and a rendered message that carries one. Any formatted
    exception text is folded in as well.

    **The guard first, and it is the one assertion here about *presence*.**
    Something must have been logged **by the client's own logger**, or the absence
    is an absence in an empty capture and would report a silent client as a safe
    one. Two states look alike there and need different fixes: a client that logs
    nothing at all, and one that logs under a name this suite is not watching.

    **The forbidden values are then searched over the *whole* capture**, not over
    the client's own records. A value that reached a log stream reached it whoever
    emitted it, and a filter is exactly how "we do not log that" survives the line
    that hands the value to somebody who does (`docs/MISTAKES.md` entry 2 — assert
    the forbidden state). The presence guard above is what keeps that from being an
    absence in an empty capture.
    """
    section = ags_sections()
    grade = ags_contract.grade(section.subjects[0])

    with caplog.at_level(logging.DEBUG):
        answered, raised = drive(
            ags_client, ags_client.find_or_create_line_item, section, committed_rows, service_wire
        )
        assert raised is None, f"Finding or creating the line item raised {raised!r}."
        _posted, raised = drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=answered,
            grade=grade,
        )
        assert raised is None, f"Posting the score raised {raised!r}."

        # The failing leg. A refused token is the failure an operator actually
        # meets, and the line a failing post writes is where the body it was trying
        # to send ends up.
        service_wire.failing(token_endpoint(section.platform), 500)
        drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=answered,
            grade=grade,
        )

    from_client = [
        record for record in caplog.records if str(record.name).startswith(ags_contract.module)
    ]
    assert from_client, (
        f"No log record came from a logger named `{ags_contract.module}` across a successful "
        "find-or-create, a successful post and a post whose token was refused. Two things look "
        "like this and they are different: the client logs nothing at all — which SPEC §6.1's "
        "'AGS call logs' does not ask for, but a silent failing passback is worse than a loud one "
        "— or it logs under a logger this suite is not looking for, which is a name to settle in "
        "the pull request rather than something to guess at here. Loggers that did record "
        f"something: {sorted({record.name for record in caplog.records})}."
    )

    written = ags_contract.logged_text(caplog.records)
    for what, value in forbidden_values(grade).items():
        assert value not in written, (
            f"A log record emitted while the client ran carries {what} ({value!r}). What was "
            f"logged was:\n{written[:2000]}\n\nA worker's log stream is read by whoever is on call "
            "and kept longer than any table in this system; a participation figure against an LMS "
            "user id there is a statement about a named person's standing, outside every read path "
            "§4.1 governs."
        )
