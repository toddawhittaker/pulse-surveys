"""E2-14 item 3 — the submit path's foreign-section denial, in the marker currency the sweep demands.

The test below is E2-08's, moved here unchanged from
`test_the_submit_path_answers_the_validity_matrix.py`, where it held
`@pytest.mark.invariant` **per test**. That is the currency
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
refuses, and it escaped that sweep only by filename: the matrix module's stem
carries no denial shape, so nothing demanded anything of it. The E2 boundary
review recorded the character of this precisely — the test **is** collected into
the isolated pass today, so this is a currency inconsistency and not lost
coverage.

**The direction taken is extract, not widen, and the alternative is recorded
rather than left implied.** The other way to make the currency consistent is to
add the two host modules' stems to `DENIAL_NAME_SHAPES`. That was rejected: those
two modules hold about twenty-five tests between them that are not §4.1 denials —
step rules, length bounds, CSRF carriers, registry shapes — and widening the
shapes would enrol every one of them in CI's isolated pass, on the strength of
their module's name. It would also put two sentences into a vocabulary that
otherwise says only what a module *denies*, which is what makes the shape list
readable as a claim rather than as a list of files. Nothing is added to
`DENIAL_NAME_SHAPES` by this ticket.

**This module's stem carries `names_nothing`, deliberately**, so the denial
sweep governs it from the day it lands: a later denial test added here inherits
the module-level marker, and a marker moved back onto a test turns that sweep
red. That inheritance is the whole reason the sweep pins the module-level form —
"a module half inside the pass reads, to every later reader, exactly like a
module inside it".

**The marker is the list form**, carrying `integration` beside `invariant`,
because the host module's `pytestmark` placed these tests in the integration
suite and dropping that would move the test rather than re-home it.

**The helpers come from the host module rather than being copied.** They sit in
this same directory, so pytest has already put `tests/integration` on `sys.path`
before this module is imported, and a copy of `a_student_in_an_open_window` would
be a second thing to keep in step with E2-07's in-band mock selectors
(`docs/MISTAKES.md` entry 13). The test's own body, name and docstring are
byte-identical to what stood in the matrix module; only its home and its imports
changed.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.submit import (
    SECTION_TABLE,
    SubmitWorld,
    a_valid_submission,
)
from test_the_submit_path_answers_the_validity_matrix import (
    a_student_in_an_open_window,
    marked,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


# ---------------------------------------------------------------------------
# Scoping. SPEC §4.1's discipline: a section the student cannot reach is
# indistinguishable from one that does not exist.
# ---------------------------------------------------------------------------


def test_a_section_the_student_is_not_enrolled_in_answers_exactly_as_an_unknown_one(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """A foreign section is refused, and the refusal says nothing about its existing.

    SPEC §4.1 item 1 is asserted from E2 because this is the first epic with a
    student-visible path "and the scoping that gives 'another section' its
    meaning". A 403 here, or a 404 whose body differs from an unknown id's, tells
    a student which section codes are real — a membership oracle over the whole
    institution, one request at a time.

    **The refusal is asserted, not the absence of a name.** The two responses are
    compared to each other, byte for byte in status and body: a test that only
    checked the foreign section's code was missing from the body would pass
    against a route that answered 403 "not enrolled".

    **The foreign section has an open window of its own**, seeded with the same
    instants, so the only difference between it and the student's own section is
    the enrollment. Without that the refusal would be equally well explained by
    the section having no survey open.

    **The mutation it kills:** the enrollment check written as a 403, and the
    enrollment check dropped entirely — which would let any signed-in student
    write into any section in the deployment.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    foreign = world.foreign_section()
    submission = a_valid_submission(comment=marked(mock_ai, "substantive"))

    not_enrolled = student.submit(submission, section=foreign)
    unknown = student.submit(submission, section={world.key_of(SECTION_TABLE): uuid4()})

    assert not_enrolled.status_code == submit_contract.not_found, (
        f"A section the student is not enrolled in was answered {not_enrolled.status_code}. "
        f"E2-08's work order settles {submit_contract.not_found}, 'with the same body a truly "
        f"unknown section id gets'. Body begins {not_enrolled.text[:400]!r}."
    )
    assert unknown.status_code == submit_contract.not_found, (
        f"An unknown section id was answered {unknown.status_code}, so the comparison below "
        f"would be against the wrong baseline. Body begins {unknown.text[:400]!r}."
    )
    assert not_enrolled.text == unknown.text, (
        "A section the student is not enrolled in is distinguishable from one that does not "
        f"exist: {not_enrolled.text[:300]!r} against {unknown.text[:300]!r}. That difference is "
        "an oracle for which sections exist, answerable by any signed-in student against every "
        "section id in the institution."
    )
    assert (
        world.responses() == []
    ), f"A submission into a section the student is not enrolled in stored {world.responses()}."
