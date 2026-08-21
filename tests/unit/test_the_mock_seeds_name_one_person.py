"""The two mock seeds' own constants, pinned to each other — ticket E0-18.

E0-18's fourth acceptance criterion: "a unit test pins `mock_idp` and `mock_lms`
seed constants to each other". This is that test, and it exists because the
reference runs one way and nothing else compares the two ends.

`mock-idp/app/seed.py` publishes `LMS_INSTRUCTOR_USER_ID`, "the launch-side
identity of the two-hat person, as `mock-lms/app/seed.py` seeds it" — a claim this
provider makes about the *other* mock's seed. Rename the instructor in
`mock-lms/app/seed.py` and both mocks' suites stay green while the reference names
a user that no longer exists: the two doors then resolve to two different people,
and E0-18's own Playwright spec is where that two-character difference is
discovered.

**This is not the same assertion as
`test_the_lms_user_id_the_provider_publishes_names_a_user_the_platform_will_launch`
in `tests/integration/test_mock_idp_web_login.py`**, and neither replaces the
other. That one drives both mocks and compares the published registration document
against a launch the platform actually signs — it is about what the two services
*serve*. This one compares the two source constants directly, needs neither
service started, and fails at the line that names the constant rather than three
HTTP hops later. E0-18's criterion asks for the second by name, and the first is
already E0-16's.

**Why the constants and not the published values.** A seed that published the
right identifier while holding it under a different constant would satisfy the
integration test and leave `LMS_INSTRUCTOR_USER_ID` as a duplicated literal —
which is exactly the drift ADR 0058 made the reference a named constant to
prevent. So the two names are read out of the two modules, and the failure below
names both files.
"""

from pathlib import Path
from typing import Any

# The constant `mock-idp/app/seed.py` holds the cross-mock reference under, and the
# path through `mock-lms/app/seed.py` to the user it refers to. Both are spelled by
# the mocks themselves — E0-18's criterion names the first, and the second is the
# instructor `MockUser` the platform seeds and offers on its launch page.
PROVIDER_REFERENCE = "LMS_INSTRUCTOR_USER_ID"
PLATFORM_INSTRUCTOR = "INSTRUCTOR.user_id"


def test_the_provider_names_the_user_the_platform_seeds_as_its_instructor(
    seed_constant: Any, mock_idp_dir: Path, mock_lms_dir: Path
) -> None:
    """One human, two identities, two doors — and one constant tying them together.

    Both halves are asserted non-empty first. Two empty strings are equal, and an
    equality between them would be this test passing while saying nothing, which is
    `docs/MISTAKES.md` entry 3 in its shortest form.
    """
    referenced = seed_constant(mock_idp_dir, PROVIDER_REFERENCE)
    seeded = seed_constant(mock_lms_dir, PLATFORM_INSTRUCTOR)

    assert isinstance(referenced, str) and referenced, (
        f"`mock-idp/app/seed.py::{PROVIDER_REFERENCE}` is {referenced!r}. It is the launch-side "
        "identity of the two-hat person, and an empty one compares equal to another empty one."
    )
    assert isinstance(seeded, str) and seeded, (
        f"`mock-lms/app/seed.py::{PLATFORM_INSTRUCTOR}` is {seeded!r}. It is the `sub` every "
        "instructor launch carries, and an empty one identifies nobody."
    )
    assert referenced == seeded, (
        f"`mock-idp/app/seed.py::{PROVIDER_REFERENCE}` is {referenced!r} and "
        f"`mock-lms/app/seed.py::{PLATFORM_INSTRUCTOR}` is {seeded!r}.\n\n"
        "That reference is the only thing in either mock tying the two entry doors to one human: "
        "SPEC §2 makes a door a property of the assignment rather than of the person, and the "
        "two-hat person is the case that proves it — Care by web login, teaching by launch. With "
        "these two disagreeing the doors open for two unrelated fixtures, both suites stay green, "
        "and E0-18's browser spec is where it surfaces.\n\n"
        "If the rename was deliberate, both files change together; if a constant was renamed "
        "rather than a value, the two names at the top of this module are the one-line change."
    )


def test_the_reference_is_a_constant_rather_than_a_literal_written_twice(
    seed_constant: Any, mock_idp_dir: Path
) -> None:
    """The reference has a name, which is what makes the pin above possible at all.

    ADR 0058 and the provider's own seed say why: "If the platform's seed renames
    that user, this goes stale silently — `docs/MISTAKES.md` entry 1 — so it is
    named here, once, rather than assembled anywhere else." A value inlined at each
    use site cannot be pinned, and the test above would have nothing to read.

    **This fails differently from the test above**, and that is the reason it is
    separate: that one fails when the two seeds disagree, this one fails when the
    reference stops being a thing anybody can point at.
    """
    assert seed_constant(mock_idp_dir, PROVIDER_REFERENCE), (
        f"`mock-idp/app/seed.py` exposes no usable `{PROVIDER_REFERENCE}`. ADR 0058 makes the "
        "cross-mock reference a named constant precisely so that it can be compared against the "
        "platform's own seed; inlined at its use sites it is a literal that goes stale in silence."
    )


def test_the_two_seeds_are_read_out_of_two_different_packages(
    seed_constant: Any, mock_idp_dir: Path, mock_lms_dir: Path
) -> None:
    """The control on the reader, without which the equality above could be trivial.

    Both mocks' packages are called `app` (SPEC §13), and the meta-path resolution
    that picks between them is real machinery that can go wrong: a reader that
    resolved both names out of *one* mock would compare a module with itself and
    pass whatever the other seed said. So each side is asked for something only its
    own seed has, and a reader pointed at the wrong package fails here rather than
    reporting agreement.
    """
    assert seed_constant(mock_idp_dir, "WEB_LOGIN_ROLES"), (
        "`mock-idp/app/seed.py` exposes no `WEB_LOGIN_ROLES`, so either the provider's seed has "
        "been restructured or the reader resolved `app.seed` out of the other mock — in which "
        "case the pin above compared one module with itself."
    )
    assert seed_constant(mock_lms_dir, "INSTRUCTOR_ROLES"), (
        "`mock-lms/app/seed.py` exposes no `INSTRUCTOR_ROLES`, so either the platform's seed has "
        "been restructured or the reader resolved `app.seed` out of the other mock."
    )
