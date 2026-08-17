"""What the mock platform is seeded with, read off the platform — ticket E0-15.

E0-15's seed data exists to give three later tickets real input: E0-07's
section-code parser needs codes that exercise more than one start letter and
both modalities (§2.2), E3's participation formula needs a mid-term add and a
mid-term drop (§3.4), and E0-17 needs courses whose numbers SPEC §8 admits.
Everything below reads the seed the way a tool would meet it — off the launch
claims and off the roster — because a seed that exists in the mock's source and
never reaches a tool is a seed no later ticket can use.

**Nothing here names a field the ticket does not name.** Section codes are found
by §2.2's own grammar rather than by looking in a key called `section_code`, and
course numbers by §8's; where the seed carries something the ticket describes
but no specification spells — an enrollment window — the test asserts the
property (enrollments do not all begin together) and says in its own docstring
what that does not reach. The alternative is to invent a field name here, which
would decide from the test side something E0-15 left open.

**One thing E0-15 asks for that is deliberately not asserted below.** The
ticket's scope says "every seeded course needs a title", and E0-14's scope
requires at least one seeded context carrying `id` alone — no title — so that
E1's ingestion meets the empty case in a test rather than in a deployment.
`test_mock_lms_launch.py::test_a_seeded_context_carries_no_title` holds that
requirement today. A test here that every seeded course carries a title would
make those two red at once, which is a disagreement between two tickets rather
than a defect in either, and it is reported rather than resolved in a test file.

**No §4.1 invariant lives here** — the mock is a platform, not a Pulse read
path. What is asserted about the seeded people is E0-15's own security note:
"the seeded identities are obviously fake, so no test fixture ever resembles
real student data".
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

pytestmark = pytest.mark.lti

# The two claims a section identifies itself through, spelled as LTI 1.3 spells
# them. `tests/integration/test_mock_lms_launch.py` spells them too; both are
# transcriptions of one published constant rather than two copies of a choice.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
CONTEXT_CLAIM = LTI_CLAIM + "context"
RESOURCE_LINK_CLAIM = LTI_CLAIM + "resource_link"

# §2.2's section code, as a whole token: `{startLetter}{ordinal}{modality}`,
# e.g. `R3WW`, `Q2FF`. Uppercase only, and that is a deliberate narrowing rather
# than a claim that a lowercase code is illegal — a hexadecimal fragment of a
# UUID can spell `a1ff`, and context identifiers are usually UUIDs, so a
# case-insensitive scan of the platform's own strings would find section codes
# that are not there. If the seed spells its codes in lower case, the failure
# below lists every token it saw and this pattern is the one line that changes.
SECTION_CODE = re.compile(r"^(?P<letter>[A-Z])(?P<ordinal>[0-9]{1,2})(?P<modality>WW|FF)$")

# §2.2 fixes both: `WW` online, `FF` face-to-face. Criterion 5 asks for both.
MODALITIES = ("WW", "FF")

# A course number as it is written beside a prefix: `BIOL 215`, `MATH 040`,
# `ITEC 8100`. Searched inside a string rather than tokenised, because the space
# is part of how it is written.
COURSE_NUMBER = re.compile(r"\b(?P<prefix>[A-Z]{2,4})[ -]?(?P<number>[0-9]{3,4})\b")

# Letter groups that are not a course prefix, so that a term written in capitals
# — `FALL 2026` — is not read as course number 2026 and reported as outside
# SPEC §8's bands. **This suite's guard**, and the narrowest one that closes the
# case: if it ever suppresses a real prefix, that is a defect here and this
# constant is the one line that changes.
NOT_A_COURSE_PREFIX = frozenset({"AY", "FA", "FALL", "SP", "SPR", "SU", "SUM", "TERM", "WI", "WIN"})

# SPEC §8's course-number bands, **transcribed rather than derived, and
# deliberately** (`docs/MISTAKES.md` entry 19 asks that a transcription say it
# is one). The rule is a markdown table plus a sentence of prose about width —
# "a three-digit number is valid only in `000`-`799`, and a four-digit number
# only in `8000`-`9999`" — and nothing in this repository holds it in a form a
# test could read. The control test below walks every edge the table names,
# which is what stands in for reading the document.
THREE_DIGIT_BAND = (0, 799)
FOUR_DIGIT_BAND = (8000, 9999)

# Domains that cannot receive mail from anywhere. RFC 2606 and RFC 6761 reserve
# `.invalid`, `.test`, `.example` and the `example.*` second-level names for
# exactly this, and `.local` is reserved by RFC 6762. E0-15's security review
# asks that the seeded identities are obviously fake; an address that could be
# delivered to is the one way a mock's seed becomes somebody's mail.
UNROUTABLE_EMAIL_DOMAINS = (
    ".invalid",
    ".test",
    ".example",
    ".local",
    ".localhost",
    "example.com",
    "example.net",
    "example.org",
    "example.edu",
)

# How a role is recognised whichever vocabulary it is written in. NRPS 2.0's own
# example uses the short names while the launch's roles claim requires LIS
# vocabulary URIs, so both spellings arrive at the same word once the URI's
# fragment or last path segment is taken.
INSTRUCTOR_ROLE_NAMES = ("instructor", "teacher", "faculty")
STUDENT_ROLE_NAMES = ("learner", "student")

MEMBER_ID = "user_id"


def is_a_course_number_spec_8_admits(number: str) -> bool:
    """Whether SPEC §8 would store `number`, width included.

    Width is part of the rule rather than an accident of it: `0099` and `099`
    are different strings that a numeric comparison reads as one course, which
    is how one course acquires two spellings and two rows.
    """
    if not number.isdigit():
        return False
    value = int(number)
    if len(number) == 3:
        return THREE_DIGIT_BAND[0] <= value <= THREE_DIGIT_BAND[1]
    if len(number) == 4:
        return FOUR_DIGIT_BAND[0] <= value <= FOUR_DIGIT_BAND[1]
    return False


def strings_in(node: Any) -> list[str]:
    """Every string anywhere inside a decoded JSON value."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [found for value in node.values() for found in strings_in(value)]
    if isinstance(node, list):
        return [found for item in node for found in strings_in(item)]
    return []


def moments_in(
    node: Any,
    parse: Callable[[Any], datetime | None],
    path: str = "",
) -> dict[str, datetime]:
    """Every date or moment inside a decoded JSON value, keyed by where it sits.

    Discovery by *value* rather than by name, because no specification spells
    the field NRPS carries an enrollment window in and E0-15 does not either.
    What the caller gets is enough to ask whether two members' windows differ,
    without this file deciding what the field is called.

    `parse` is the `instant_of` fixture — the same comparison the AGS round trip
    uses on a score's timestamp — rather than a second reading of ISO 8601
    written here (`docs/MISTAKES.md` entry 13).
    """
    found: dict[str, datetime] = {}
    if isinstance(node, str):
        parsed = parse(node)
        if parsed is not None:
            found[path] = parsed
        return found
    if isinstance(node, dict):
        for name, value in node.items():
            found.update(moments_in(value, parse, f"{path}.{name}" if path else str(name)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.update(moments_in(item, parse, f"{path}[{index}]"))
    return found


def role_names(member: dict[str, Any]) -> set[str]:
    """A member's roles as bare lower-case words, whichever vocabulary spelled them."""
    roles = member.get("roles")
    if not isinstance(roles, list):
        return set()
    return {
        str(role).replace("#", "/").rstrip("/").rsplit("/", maxsplit=1)[-1].lower()
        for role in roles
        if isinstance(role, str) and role
    }


def published_strings(platform: Any) -> list[tuple[str, str]]:
    """Every string the platform publishes about a seeded section, and where it came from.

    Three sources, which are the three places a section names itself to a tool:
    the launch's context claim, its resource link claim, and the `context`
    object on the membership container. Nothing wider than that is scanned, so a
    section code cannot be found inside an opaque identifier that happens to
    look like one.
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so nothing about a seeded section could be read. "
        "E0-14 seeds the launches; E0-15 seeds the sections behind them."
    )
    found: list[tuple[str, str]] = []
    for context in contexts:
        launch = context.launches[0]
        for claim in (CONTEXT_CLAIM, RESOURCE_LINK_CLAIM):
            found += [
                (f"{claim} of {context.context_id}", value)
                for value in strings_in(launch.claims.get(claim))
            ]
        page = platform.membership_page(context.memberships_url)
        found += [
            (f"membership container context of {context.context_id}", value)
            for value in strings_in(page.document.get("context"))
        ]
    return found


def seeded_section_codes(platform: Any) -> dict[str, str]:
    """Every §2.2 section code the platform publishes, mapped to where it was found."""
    found: dict[str, str] = {}
    published = published_strings(platform)
    for source, value in published:
        for token in re.split(r"[^A-Za-z0-9]+", value):
            if SECTION_CODE.match(token):
                found.setdefault(token, source)
    assert found, (
        "No string the platform publishes about a seeded section matches §2.2's "
        "`{startLetter}{ordinal}{modality}` shape. It published "
        f"{sorted({value for _, value in published})}. E0-15 criterion 5 seeds sections whose "
        "codes exercise more than one start letter and both modalities 'so E0-07's parser has "
        "real input' — which means the codes have to reach a tool, not merely exist in the seed."
    )
    return found


def seeded_members(platform: Any) -> list[dict[str, Any]]:
    """Every member of every seeded roster, with a guard against emptiness."""
    members = [
        member
        for context in platform.seeded_contexts()
        for page in platform.membership_pages(context.memberships_url)
        for member in page.members
    ]
    assert members, (
        "Every seeded roster came back empty, so every assertion about the people in it would "
        "hold vacuously. E0-15 seeds 'students, instructors, and enrollments'."
    )
    return members


# ---------------------------------------------------------------------------
# The two matchers, run against what they claim to catch and what they allow.
# ---------------------------------------------------------------------------


def test_the_section_code_pattern_reads_the_examples_in_spec_2_2_and_refuses_near_misses() -> None:
    """The control on the scan below (`docs/MISTAKES.md` entry 3).

    A pattern searched against text looks like an assertion and is not one until
    it has been run against the text it is claimed to catch *and* the text it is
    claimed to allow. Both halves are here, and the second is the one that
    matters: a pattern matching too much would find two start letters and both
    modalities in a seed that has neither, and criterion 5 would read as met.

    The lower-case case is listed among the refusals on purpose, because that is
    a narrowing rather than a rule — see the comment on `SECTION_CODE`.
    """
    for code in ("R3WW", "Q2FF", "U1WW", "K16FF"):
        assert SECTION_CODE.match(code), f"§2.2 spells {code} as a section code."
    for near_miss in ("R3", "3WW", "RWW", "R3XX", "r3ww", "R123WW", "R3WWW", ""):
        assert not SECTION_CODE.match(near_miss), (
            f"{near_miss!r} is not a §2.2 section code, and a pattern that accepts it would find "
            "start letters and modalities in strings that carry neither."
        )


def test_the_course_number_bands_agree_with_the_table_in_spec_8() -> None:
    """The control on the band check, walking every edge §8's table names.

    This is what stands in for reading the document: the bands are transcribed
    into two constants above, and a transcription nobody exercises is a copy of
    a rule rather than the rule (`docs/MISTAKES.md` entry 19). `2150` is here
    because it is the number the ticket warns about: `BIOL 2150` and every other
    distinct course number written across `design/` are invalid under these
    bands, with no exception, so a seed copied from a prototype screen fails the
    test below and this control is what says the failure is real.
    """
    for admitted in ("000", "040", "099", "100", "499", "500", "599", "600", "799", "8000", "9999"):
        assert is_a_course_number_spec_8_admits(
            admitted
        ), f"SPEC §8 admits {admitted!r}: three digits run 000-799 and four digits 8000-9999."
    for refused in ("800", "999", "1000", "2150", "7999", "0099", "99", "10000", "80a0", ""):
        assert not is_a_course_number_spec_8_admits(refused), (
            f"SPEC §8 refuses {refused!r} — 'Numbers outside the bands are rejected at write time "
            "rather than stored with an absent or guessed level.'"
        )


# ---------------------------------------------------------------------------
# Criterion 5 — section codes with two start letters and both modalities.
# ---------------------------------------------------------------------------


def test_the_seeded_sections_use_more_than_one_start_letter(mock_platform: Any) -> None:
    """Criterion 5, the start-letter half.

    Catches the seed every implementer writes first: one section code copied
    across every seeded section, or a code generated with a fixed letter and a
    varying ordinal. §2.2 makes the start letter carry the section's length *and*
    its start date within the term, so a seed with one letter gives E0-07's
    parser one length and one start date to be right about, and gives E0-17 a
    demo institution in which every section runs on the same calendar.
    """
    codes = seeded_section_codes(mock_platform)
    # Every key of `codes` has already matched `SECTION_CODE`, so the start
    # letter is its first character and the modality its last two — sliced
    # rather than re-matched, which keeps this line free of a match object that
    # a reader has to check for `None`.
    letters = {code[0] for code in codes}
    assert len(letters) > 1, (
        f"Every seeded section code begins with {sorted(letters)}: {sorted(codes)}. E0-15 "
        "criterion 5 asks for at least two different start letters, because §2.2 makes the start "
        "letter carry both the length and the start date — one letter is one calendar."
    )


def test_the_seeded_sections_use_both_the_online_and_face_to_face_modalities(
    mock_platform: Any,
) -> None:
    """Criterion 5, the modality half, and it is a separate test on purpose.

    The near miss criterion 5 is written against is a seed with two start letters
    and one modality — `R3WW` and `Q2WW` — which satisfies the sentence read
    quickly and leaves `FF` untested everywhere downstream. Split into two tests
    so the runner says which half is missing without anyone opening the file.
    """
    codes = seeded_section_codes(mock_platform)
    modalities = {code[-2:] for code in codes}
    missing = [modality for modality in MODALITIES if modality not in modalities]
    assert not missing, (
        f"The seeded section codes {sorted(codes)} use only {sorted(modalities)} and carry no "
        f"{missing}. §2.2: `WW` online, `FF` face-to-face; E0-15 criterion 5 asks for both, so "
        "that E0-07's parser and everything reading its `modality` have both to be right about."
    )


def test_every_seeded_course_number_falls_inside_the_bands_spec_8_sets(
    mock_platform: Any,
) -> None:
    """E0-15's scope: course numbers picked against §8 rather than from a prototype screen.

    Catches the seed the ticket warns about in bold. Every distinct course number
    written across `design/` is invalid under §8's bands — `BIOL 2150` is four
    digits below 8000 — and a seed copied from those screens looks entirely
    convincing. It fails at write time in E0-17, one ticket later,
    against a schema rule that has nothing to do with the mock, and the failure
    reads as a schema being fussy rather than as a seed being wrong.

    The scan is over what the platform publishes about its sections, so a course
    number that never reaches a tool is not caught here — and one that never
    reaches a tool is one E0-17 cannot seed from either.
    """
    published = published_strings(mock_platform)
    candidates = [
        (source, match.group("prefix"), match.group("number"))
        for source, value in published
        for match in COURSE_NUMBER.finditer(value)
        if match.group("prefix") not in NOT_A_COURSE_PREFIX
    ]
    assert candidates, (
        "No string the platform publishes about a seeded section carries anything shaped like a "
        f"course number. It published {sorted({value for _, value in published})}. E0-15's scope: "
        "'Every seeded course needs a title and a number in SPEC §8's bands' — a number a tool "
        "never sees is one E0-17 cannot seed a course from."
    )
    outside = [
        (source, f"{prefix} {number}")
        for source, prefix, number in candidates
        if not is_a_course_number_spec_8_admits(number)
    ]
    assert not outside, (
        f"Seeded course numbers outside SPEC §8's bands: {sorted({number for _, number in outside})}"
        f" (first seen in {outside[0][0]}). Three digits are valid only in 000-799 and four only "
        "in 8000-9999, and E0-15's scope warns that every course number written across `design/` "
        "is invalid under those bands. If one of these is not a course number at all, that is a "
        "defect in `COURSE_NUMBER` or `NOT_A_COURSE_PREFIX` in this file rather than in the seed."
    )


# ---------------------------------------------------------------------------
# The seeded people, and criterion 6's adds and drops.
# ---------------------------------------------------------------------------


def test_the_seeded_roster_carries_both_an_instructor_and_a_student(
    mock_platform: Any,
) -> None:
    """E0-15's scope: the seed holds "students, instructors, and enrollments".

    Catches a roster of learners with the teaching instructor missing, which is
    what a seed built from a list of students looks like. §2.1 makes the teaching
    instructor LMS-owned data that arrives with the roster, and every instructor
    surface in the product is keyed to it, so a roster with no instructor gives
    E1 a section nobody teaches.

    Both halves are asserted, so a roster where every member is an instructor
    fails as loudly as one where none is.
    """
    members = seeded_members(mock_platform)
    roles = [role_names(member) for member in members]
    instructors = [role for role in roles if role & set(INSTRUCTOR_ROLE_NAMES)]
    students = [role for role in roles if role & set(STUDENT_ROLE_NAMES)]
    assert instructors and students, (
        f"The seeded rosters carry {len(instructors)} members in an instructor role and "
        f"{len(students)} in a student role across {len(members)} members; the roles seen are "
        f"{sorted(set().union(*roles) if roles else set())}. E0-15 seeds 'students, instructors, "
        "and enrollments', and a section with only one of the two is a section nobody teaches or "
        "nobody takes."
    )


def test_the_seeded_roster_carries_a_member_who_is_no_longer_actively_enrolled(
    mock_platform: Any,
) -> None:
    """Criterion 6, the drop half, through the one field NRPS spells for it.

    Catches the seed where every enrollment is `Active` — which is every seed
    written from a class list. SPEC §3.4: "Drops: scores stop updating", and the
    tool learns about a drop from NRPS enrollment data, so with no dropped member
    anywhere in the seed E3's drop branch has nothing to run against and its
    property tests generate a case the mock cannot produce.

    The Active half of the assertion is not ceremony: a roster reporting every
    member `Inactive` would satisfy "some member is not Active" while having no
    drop in it at all, and would look identical in the runner. Nor is the drop
    half written as "not Active" — a member carrying no status at all satisfies
    that while saying nothing about an enrollment, which is why the two values
    NRPS uses for a departed member are named.
    """
    members = seeded_members(mock_platform)
    statuses = [member.get("status") for member in members]
    assert any(status == "Active" for status in statuses), (
        f"No seeded roster member is `Active` (statuses: {sorted(set(map(str, statuses)))}). A "
        "roster in which nobody is enrolled makes the assertion below true for the wrong reason."
    )
    assert any(status in ("Inactive", "Deleted") for status in statuses), (
        f"No seeded roster member carries `Inactive` or `Deleted` — the statuses across "
        f"{len(members)} members are {sorted(set(map(str, statuses)))}. E0-15 criterion 6 seeds a "
        "mid-term drop 'giving E3 the edge cases its property tests need', and SPEC §3.4 "
        "has the tool learn about a drop from NRPS enrollment data — which it can only do if the "
        "roster carries one, as `Inactive` or `Deleted`."
    )


def test_the_seeded_roster_does_not_enrol_every_member_at_the_same_moment(
    mock_platform: Any,
    instant_of: Any,
) -> None:
    """Criterion 6, the add half, and it is the weaker of the two on purpose.

    Catches the seed every implementer writes first: every enrollment beginning
    at the term start. SPEC §3.4 makes the late add a denominator rule — "the
    denominator starts at the student's first enrolled week (from NRPS enrollment
    data)" — so a seed where every window is identical leaves that branch with
    nothing to exercise it, and E3's property tests generate a case the mock
    cannot produce.

    **What this does not reach**, stated rather than implied. NRPS 2.0 spells no
    enrollment-window field and E0-15 names none either, so the window is found
    by *value*: any member field carrying a date. That means the test asserts
    "the seeded enrollments do not all begin together" and cannot assert "one of
    them begins mid-term", because nothing on this surface says where the term
    starts. It would also be satisfied by a per-member field that carries a date
    for some unrelated reason. Both are gaps in what the ticket specifies rather
    than in what it asks for, and closing them means the ticket saying what
    carries an enrollment window.
    """
    members = seeded_members(mock_platform)
    dated = {
        str(member.get(MEMBER_ID, index)): moments_in(member, instant_of)
        for index, member in enumerate(members)
    }
    assert any(dated.values()), (
        f"No member of any seeded roster carries a date anywhere ({members[0]!r} is the first). "
        "SPEC §3.4 takes the student's first enrolled week from NRPS enrollment data and §7.3 "
        "says the roster sync is what supplies enrollment windows, so a roster carrying no dates "
        "at all carries no enrollment window for E3 to read."
    )
    varying = sorted(
        path
        for path in {name for fields in dated.values() for name in fields}
        if len({fields[path] for fields in dated.values() if path in fields}) > 1
    )
    assert varying, (
        "Every seeded member's dates are identical: "
        f"{ {name: str(value) for fields in dated.values() for name, value in fields.items()} }. "
        "E0-15 criterion 6 seeds a mid-term add, and an enrollment window that is the same for "
        "every member is a roster in which nobody joined late — which is the case SPEC §3.4's "
        "denominator rule exists for."
    )


def test_the_seeded_roster_exposes_an_email_and_every_address_is_unroutable(
    mock_platform: Any,
) -> None:
    """The scope's "email where exposed", and E0-15's security note in one test.

    Two failures, and the emptiness guard comes first because the second
    assertion is about a set that a roster with no emails at all satisfies
    (`docs/MISTAKES.md` entry 3). §7.3 has the roster sync supply "email
    addresses where exposed", so a seed exposing none leaves E1 with nothing to
    build the notification path against.

    The second is the security review item: "confirm ... that the seeded
    identities are obviously fake, so no test fixture ever resembles real student
    data". A deliverable address in a seed is one an outage, a misconfigured
    SMTP host or a copied fixture eventually mails — RFC 2606 and RFC 6761
    reserve names precisely so that a test never has to risk it.
    """
    members = seeded_members(mock_platform)
    emails = [member["email"] for member in members if isinstance(member.get("email"), str)]
    assert emails, (
        f"No member of any seeded roster carries an `email` (the first carries "
        f"{sorted(members[0])}). E0-15's scope has NRPS return 'email where exposed' and §7.3 has "
        "the roster sync use it, so a seed exposing none is a roster E1 cannot build against."
    )
    routable = sorted(
        address
        for address in emails
        if not address.split("@")[-1].lower().endswith(UNROUTABLE_EMAIL_DOMAINS)
    )
    assert not routable, (
        f"Seeded addresses that could be delivered to: {routable}. E0-15's security review asks "
        "that the seeded identities are obviously fake; RFC 2606 and RFC 6761 reserve "
        f"{list(UNROUTABLE_EMAIL_DOMAINS)} so that a fixture never has to risk mailing anyone."
    )
