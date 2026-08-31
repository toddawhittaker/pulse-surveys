"""What a refused provisioning write says out loud — E1 boundary fix, R6.

`app.services.provisioning` logs when it refuses a write, through
`_log_a_refused_write`, and until this module nothing exercised that line under
`caplog`: PR #105's body promised the assertion and it was never written, the E1
boundary review found the gap, and `docs/tickets/e1/deferred.md` (E1-10, item 6)
records it with the done-when this file satisfies — "a test drives a refused
provisioning write under `caplog` and scans every record for planted claim
values, the same canary shape as the launch-view scans".

**The code is clean today. This is the guard, not the fix.** That is exactly
why it is worth having and exactly why it is easy to get wrong: a scan that
finds nothing is indistinguishable from a scan that is looking at nothing, so
this module makes two claims about itself before it makes any about the code.
The refusal has to have actually happened — asserted as the recorded
`context_collision`, not inferred — and at least one record has to have been
captured from the provisioning logger, or there was no log line to scan and the
silence means nothing (`docs/MISTAKES.md` entry 3). The scan itself is proved
against a planted leak by the control at the foot of this file, which is entry
9's rule: never cite a guard that has not been run against the case it is
supposed to catch.

**Why a refusal path rather than the happy one.** A refusal is where values get
printed. It is the branch with something to explain, it is reached by input the
tool did not choose, and every one of those values came out of a token somebody
else signed. SPEC §10 keeps student PII out of logs; a context identifier, a
course title and a subject are the launch's own, and a refusal that repeats them
writes them into whatever ships the logs.

**The collision is driven at the writer rather than through the door**, for the
reason `tests/integration/test_a_launch_may_not_repoint_another_contexts_
section.py` gives: it needs two contexts that parse to one identity, and the
mock platform mints one context per launch page. The claims are a real launch's,
minted by the registered platform, with the members this file plants rewritten.
"""

import logging
from typing import Any

import pytest

# `invariant` joins the list rather than replacing it: every test here is a SPEC
# §4.1 denial, and CLAUDE.md makes that pass unskippable — but
# `scripts/ci/check_invariants.py` enforces it only over tests already carrying
# the marker, so a denial module without one is not reported skipped, it is not
# reported at all. Held at module level so the module's *next* denial test
# inherits it; the rule is
# `tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# The logger the writer's refusal line is expected under: the module's own
# dotted name, which is how `app.lti.launch` names its door logger
# (`LAUNCH_LOGGER_NAME` in the launch-door suite) and the convention every
# logger in this project follows. **If the writer logs under some other name,
# this constant is the one line that changes** — and the failure below says so,
# rather than passing quietly over a scan of nothing.
PROVISIONING_LOGGER = "app.services.provisioning"

# The values planted in the refused launch's claims. Each is a token nothing
# else in this system produces, so a match is proof of provenance rather than a
# coincidence, and each is plain lowercase, digits and hyphens so that no
# quoting, escaping or `repr()` on the way into a log line can hide it
# (`docs/MISTAKES.md` entry 3).
CANARY_CONTEXT_ID = "e1-r6-canary-context-4b19"
CANARY_TITLE = "e1-r6-canary-title-7ad2"
CANARY_ROSTER_HOST = "e1-r6-canary-roster-9ce4.invalid"
CANARY_ROSTER_ADDRESS = f"https://{CANARY_ROSTER_HOST}/contexts/copied/memberships"
CANARY_SUBJECT = "e1-r6-canary-subject-2f60"

# What is scanned for. The roster address is looked for by its host rather than
# whole, so a line that printed a truncated or re-parsed form of it is still
# caught; `.invalid` is RFC 2606's, so nothing here resolves.
PLANTED_IN_THE_CLAIMS = (
    CANARY_CONTEXT_ID,
    CANARY_TITLE,
    CANARY_ROSTER_HOST,
    CANARY_SUBJECT,
)

# The claim the subject arrives in, spelled as LTI 1.3 and OIDC Core spell it.
SUBJECT_CLAIM = "sub"


def provision(provisioning: Any, session: Any, claims: Any) -> BaseException | None:
    """Run the writer over one launch's claims, answering an escaped exception rather than raising.

    A copy of the helper in `tests/integration/test_a_launch_may_not_repoint_
    another_contexts_section.py`, marked as one: a test module importing another
    test module is not something this suite does, and E1-10's rule — that a
    provisioning refusal "NEVER fails the launch or the person's landing" — makes
    an escaped exception a real outcome to report rather than something to raise
    through and lose the log scan over.
    """
    try:
        provisioning.call(provisioning.provision, session=session, claims=claims)
    except Exception as escaped:
        return escaped
    return None


def records_from_the_writer(caplog: pytest.LogCaptureFixture) -> list[Any]:
    """Every captured record the provisioning module (or a child of it) emitted."""
    return [
        record
        for record in caplog.records
        if record.name == PROVISIONING_LOGGER or record.name.startswith(f"{PROVISIONING_LOGGER}.")
    ]


def what_the_writer_said(records: list[Any]) -> str:
    """Every captured record rendered the way a log ships it.

    Formatted rather than read off `record.msg`, deliberately, and it is the
    difference between scanning the line and scanning the *template*: `%s`
    arguments are interpolated by the formatter, and an exception attached with
    `exc_info=True` contributes its whole traceback — which is precisely how a
    library's message, carrying whatever it was handed, reaches a log without
    anybody writing it into a format string.
    """
    formatter = logging.Formatter("%(message)s")
    return "\n".join(formatter.format(record) for record in records)


def assert_the_writer_named_nothing_from_the_launch(
    caplog: pytest.LogCaptureFixture, *, what: str
) -> None:
    """No record from the writer carries any planted claim value.

    The non-emptiness guard is first and is not ceremony: with no captured
    record there is no log line, and "none of the canaries is in it" is a
    statement about an empty string.
    """
    records = records_from_the_writer(caplog)
    assert records, (
        f"No log record at all was captured from `{PROVISIONING_LOGGER}` while {what}. E1-10's "
        "writer logs a line when it refuses to write — `_log_a_refused_write` — and this test "
        "exists to scan that line, so without one it asserts nothing. Either the refusal is no "
        "longer logged, which is a change to what an operator can see, or the logger is named "
        f"something other than {PROVISIONING_LOGGER!r}, in which case the constant at the top of "
        f"this file is the one line that changes. Captured from every logger: "
        f"{sorted({record.name for record in caplog.records})}"
    )
    said = what_the_writer_said(records)
    leaked = sorted(value for value in PLANTED_IN_THE_CLAIMS if value in said)
    assert not leaked, (
        f"The log from `{PROVISIONING_LOGGER}` carries {leaked} while {what}. Every one of those "
        "values was planted in the refused launch's own claims — its context identifier, the "
        "title the platform sent, the roster address it advertised, and the subject it named — "
        "and each came out of a token this tool did not sign. SPEC §10 keeps that material out "
        f"of logs, which is where it ends up shipped. What was logged:\n\n{said}"
    )


@pytest.fixture
def a_bound_section(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioning: Any,
    rows_on: Any,
    db_session: Any,
) -> dict[str, Any]:
    """One provisioned section, bound to the context that discovered it.

    The state a collision needs, built the same way `bound_section` in
    `tests/integration/test_a_launch_may_not_repoint_another_contexts_section.py`
    builds it — a copy, and marked as one, because a test module may not import
    another and this file needs the same starting point for a different subject.

    **A red here is not a red about logging**: it means the ordinary path
    stopped provisioning, and `tests/integration/test_launch_time_provisioning.py`
    is where that is diagnosed.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    launch_ground(provisioning_contract.label_of(claims))
    rows = rows_on(db_session)

    escaped = provision(provisioning, db_session, claims)
    assert escaped is None, (
        f"Provisioning the first launch raised {escaped!r}. This module starts from one section "
        "that exists and is bound; until that works, nothing here is about a refused write."
    )
    assert rows.sections(), (
        "The first launch created no section, so the second one has nothing to collide with and "
        "the write below would be an ordinary one that was never refused."
    )
    return {"claims": claims, "rows": rows, "session": db_session}


def test_a_refused_write_says_nothing_the_launch_told_it(
    a_bound_section: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The refusal line names the refusal, and none of the launch's own values.

    A second launch arrives from a different context carrying a label that parses
    to the bound section's identity — a copied course, which is ordinary LMS
    behaviour and needs no privilege — and everything a refusal might reach for
    is a canary: the context identifier, the title, the roster address and the
    subject.

    **The mutation this must kill:** a refusal line that reports what it refused.
    `logger.warning("refusing %s: %s", context_id, exc)` is the natural way to
    write it and the natural thing to want while debugging, and every value in it
    came out of a token somebody else signed. SPEC §10 keeps that material out of
    the logs.

    **The near miss it must survive, and the reason the haystack is formatted
    rather than read:** a line whose *template* is constant and whose arguments
    carry the values, or a constant message with `exc_info=True` attached — the
    library's own message, carrying whatever it was handed, arriving in the
    record's traceback. Both are invisible to a scan of `record.msg` and both are
    caught here.

    **Two controls, and neither is decoration.** The refusal has to have
    happened, so the `context_collision` record is required — over a launch that
    was quietly accepted there is no refusal line and the scan is vacuous. And at
    least one record has to have been captured from the writer's logger, which
    `assert_the_writer_named_nothing_from_the_launch` requires before it scans.
    The scan's own ability to *find* a value is proved separately, by
    `test_the_scan_catches_a_claim_value_planted_in_the_writers_log` below.
    """
    claims = a_bound_section["claims"]
    rows = a_bound_section["rows"]
    copied = dict(
        provisioning_contract.with_memberships_url(
            provisioning_contract.with_context_title(
                provisioning_contract.with_context_id(claims, CANARY_CONTEXT_ID),
                CANARY_TITLE,
            ),
            CANARY_ROSTER_ADDRESS,
        )
    )
    copied[SUBJECT_CLAIM] = CANARY_SUBJECT
    assert provisioning_contract.context_id_of(claims) != CANARY_CONTEXT_ID, (
        "The bound section already carries the canary context id, so the second launch is the "
        "bound context and nothing would be refused."
    )
    caplog.set_level(logging.DEBUG, logger=PROVISIONING_LOGGER)
    caplog.clear()

    escaped = provision(provisioning, a_bound_section["session"], copied)

    assert escaped is None, (
        f"The refusal escaped as {escaped!r} rather than being recorded. E1-10's work order: a "
        "provisioning refusal never fails the launch, and the record is the visibility."
    )
    recorded = [str(getattr(row["kind"], "value", row["kind"])) for row in rows.defects()]
    assert recorded == [provisioning_contract.context_collision], (
        f"The refused launch recorded the defects {recorded}; it should have recorded exactly "
        f"[{provisioning_contract.context_collision!r}]. Without a refusal there is no refusal "
        "line, and every assertion this test makes about what was logged would be about a write "
        "that was never refused (`docs/MISTAKES.md` entry 3)."
    )
    assert_the_writer_named_nothing_from_the_launch(
        caplog, what="a launch from another context was refused for colliding with a bound section"
    )


def test_the_scan_catches_a_claim_value_planted_in_the_writers_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The control, and the test above is worth nothing without it.

    A line carrying a planted claim value is logged on the real logger, and the
    scan has to refuse it. **Dies if the scan is satisfied by emptiness** — an
    empty record list, a haystack built from a template nobody interpolated,
    a value list that has quietly stopped holding anything — which is the failure
    mode of every leak scan that has gone blind (`docs/MISTAKES.md` entry 9:
    never cite a guard without running it against the case it is supposed to
    catch).

    It needs no implementation beyond this module's own helpers, so it is green
    today; if it is not, the scan above means nothing whatever it reports.
    """
    caplog.set_level(logging.DEBUG, logger=PROVISIONING_LOGGER)
    caplog.clear()
    logging.getLogger(PROVISIONING_LOGGER).warning(
        "context_collision (this line deliberately carries a planted context id: %s)",
        CANARY_CONTEXT_ID,
    )

    with pytest.raises(AssertionError):
        assert_the_writer_named_nothing_from_the_launch(caplog, what="a planted leak was logged")
