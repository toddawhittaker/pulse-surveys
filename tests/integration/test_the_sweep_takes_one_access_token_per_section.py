"""One client-credentials grant per section per sweep, not one per student — E3-08's boundary round, LO-M2.

R3's ruling: "One token per section per sweep: the connector/caller is hoisted to
the section walk, not built per student."

**Why it is a finding and not a preference.** A grant is a full round trip to the
platform's token endpoint carrying a `client_assertion` this tool signs — and the
platform fetches the tool's key set to verify it, so the real cost is two network
calls, some of it asymmetric cryptography, before any score moves. Built per
student, a 200-seat section spends 200 of them on a Monday morning against a
platform that is rate-limiting the tool's whole institution at once. Nothing about
the *result* changes, which is exactly why no behavioural test in this epic can
see it: every score still arrives, every ledger is still right, and the sweep is
merely 200 times more expensive than it needs to be. That is the shape of defect a
catalog or a call count catches and correctness never does.

**What is asserted and what is deliberately left open.** The number of grants per
section per sweep, and nothing else. Whether the client caches by registration, by
section or by scope, whether it holds a connector or a token, and how long either
lives are the implementer's — `tests/fixtures/lti_services.py::cached_service_token`
already shows the suite's own driver caching, and this module makes no claim about
the mechanism. What it claims is that the count does not grow with the roster,
which is the whole of R3.

**The grant is told from the AGS calls by its path**, read out of the platform's
own discovery document rather than transcribed: `Gradebook.token_path` asks the
platform where its `token_endpoint` is, so a platform that moved it does not
silently make this module count zero of everything.

**The environment.** `window_settings` states `ENVIRONMENT=development` and
`INSTITUTION_TIMEZONE=America/New_York` over `configured_env`'s documented values
(`docs/MISTAKES.md` entry 40), which is the chain every module built on
`gradebooks` rides.

**Which failure a red here is.** Expected **RED** before the hoist, on the
assertion below, with the message naming the count it found and the roster size it
found it over. `sweep_contract.run` reports what escaped the sweep rather than
letting it fly, so a sweep that raises is a named failure and not a stack trace
over an assertion that never ran.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks` and `sweep_contract` come from `tests/fixtures/grade_sweep.py`;
# `window_settings` from `tests/fixtures/survey_windows.py`;
# `committed_clock_overrides` from `tests/fixtures/clock.py`. All are reached as
# fixtures rather than imported, for the reason every module in this suite gives.

# How many students the section carries. **Two is the whole instrument**: one
# cannot tell "one grant per section" from "one grant per student", and every
# number above two costs a round trip per extra student to say the same thing. The
# assertion below is written against this constant rather than against the literal
# 2, so a reader can see that what is claimed is independence from the roster.
STUDENTS = 2

# How many course weeks have elapsed when the sweep runs. One is enough: what this
# module is about is how many times the sweep authorised itself, not what it
# computed.
ELAPSED_WEEKS = 1

# What a section's worth of authorisation is. One, and the ruling is why: the
# connector is built once for the section walk.
GRANTS_PER_SECTION = 1


def test_the_sweep_takes_one_token_for_a_section_however_many_students_it_posts_for(
    gradebooks: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """R3: the grant count is a property of the section, not of the roster.

    Two students in one section, both with a score to post, one sweep. The
    platform's token endpoint must be reached once.

    **The mutation this kills:** the connector or the caller built inside the
    per-student loop rather than hoisted to the section walk — which is the state
    LO-M2 found. It is invisible to every other test in this epic: both students'
    scores arrive, both ledgers are right, and the only difference is a round trip
    per student to a platform that rate-limits the institution.

    **Both halves are asserted, and the second is what makes the first mean
    something.** A count of one grant is also what a sweep that posted *nothing*
    would produce — indeed a sweep that grants eagerly and then finds no work does
    exactly that — so the posts are required first. Without that, this test is
    green against a sweep that authorised itself once and then did nothing at all,
    which is `docs/MISTAKES.md` entry 3 in its plainest form.

    **The near miss it must survive:** a second grant for a *different* section.
    Nothing here forbids that — the ruling is one token per section per sweep, and
    a deployment with forty sections legitimately takes forty. This section is the
    only one in the world this test builds, so its own count is the whole count,
    and a future reader widening this to two sections should expect two.

    **The wire is cleared immediately before the sweep**, so the grants counted
    are the sweep's own: `gradebooks` reaches the platform while it creates the
    line item, and those calls are not this module's subject.
    """
    book = gradebooks()
    students = sweep_contract.students(book, STUDENTS)
    for student in students:
        sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)

    token_path = book.token_path()
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )
    assert raised is None, (
        f"The sweep raised {raised!r} over this section, so it did not finish and the call count "
        "below is a count of however far it got."
    )

    # The non-vacuity guard, first: a grant count of one is also what a sweep that
    # posted nothing produces.
    assert answered[sweep_contract.posted_key] == STUDENTS, (
        f"The sweep answered {answered!r} over a section with {STUDENTS} students who each had a "
        f"score to post, and this test needs both posted. A sweep that posted fewer took fewer "
        "tokens for a reason that has nothing to do with R3, and the count below would be "
        "measuring the wrong thing."
    )

    grants = [call for call in book.wire.calls if call.path == token_path]
    assert len(grants) == GRANTS_PER_SECTION, (
        f"The sweep asked the platform's token endpoint ({token_path!r}) {len(grants)} times while "
        f"posting for {STUDENTS} students in one section. E3-08's boundary round (LO-M2) settles "
        f"one grant per section per sweep: the connector is hoisted to the section walk rather "
        "than built per student.\n\n"
        f"A count equal to the roster size ({STUDENTS}) is the defect itself — the grant built "
        "inside the per-student loop. Each one is a round trip carrying a `client_assertion` this "
        "tool signs, and the platform fetches the tool's key set to verify it, so a 200-seat "
        "section spends four hundred calls and two hundred signatures on a Monday morning against "
        "a platform rate-limiting this tool's whole institution. Nothing about the scores changes, "
        "which is why no other test in this epic can see it.\n\n"
        f"The calls the sweep made were: {[call.path for call in book.wire.calls]}"
    )
