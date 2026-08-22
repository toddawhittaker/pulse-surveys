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
course numbers by §8's. The one member that *is* named is named by the ticket:
enrollment windows ride on `https://mock-lms.invalid/spec/nrps/enrollment`
(ADR 0048). An earlier draft of this module had to find that window by looking
for any member value that parsed as a date, and the difference is worth stating
rather than quietly enjoying — a test that discovers a field by the shape of its
value is satisfied by a field carrying a date for an unrelated reason, and this
one cannot be.

**One member carries no window, and that is a criterion rather than a gap**
(E0-28 item 1). E0-15 requires the extension on every member, which is the case
no mainstream platform actually presents: NRPS 2.0 carries no dates, so a
platform supplying them supplies a vendor extension and most supply nothing. A
seed where every member has one lets E1 write `member[EXTENSION]["start"]` and
pass every test here. So exactly one seeded member — a student in
`NURS-8100-Q2FF`, a section away from the add-and-drop assertions, `Active`, and
not one of the two users the launch page signs launches for — is served with the
extension key **absent**. Three tests hold that shape: the count, the absence of
the key itself rather than a null value, and the placement. The rule E0-15
states is not withdrawn; a single case is added beside it.

**On titles, and what asserting them cost.** E0-15's scope says "every seeded
course needs a title"; E0-14's asked this mock to seed one context carrying `id`
alone, so that E1's ingestion met a titleless course in a test rather than in a
deployment. Both could not hold in one seed. Todd ruled for E0-15 on 2026-08-17,
`test_mock_lms_launch.py::test_a_seeded_context_carries_no_title` was deleted in
its own commit, and the assertion below is the requirement that replaced it —
so it is worth knowing here that what went with that deletion is the only
fixture in the repository exercising the empty-title path, and E1 has to mint
one itself before it can test its fallback against `course.lms_title`'s
`NOT NULL`.

**No §4.1 invariant lives here** — the mock is a platform, not a Pulse read
path. What is asserted about the seeded people is E0-15's own security note:
"the seeded identities are obviously fake, so no test fixture ever resembles
real student data".
"""

import re
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

# Where an enrollment window rides. **E0-15's spelling and namespace, not this
# suite's** (ADR 0048): NRPS 2.0 defines no date on a member at all, so a
# platform supplying one supplies it as a vendor extension, and E1 learns from
# the namespace that enrollment dates are per-platform rather than core.
ENROLLMENT_EXTENSION = "https://mock-lms.invalid/spec/nrps/enrollment"

# How many seeded members carry no enrollment window at all. **E0-28 item 1's
# number, and it is exactly one** — the ticket amends E0-15's "every member"
# criterion by adding a single case rather than withdrawing the rule. One,
# rather than "at least one", because both directions are the criterion: no
# seeded roster shows E1 the platform that supplies no dates unless one member
# lacks the extension, and E3's denominator loses its input if the rest do.
MEMBERS_WITHOUT_AN_ENROLLMENT_WINDOW = 1

# The section E0-28 item 1 puts that member in, written as the three tokens the
# platform publishes about it rather than as one string. **The ticket's choice,
# not this suite's**: the member sits in `NURS-8100-Q2FF` so that it is a section
# away from the add-and-drop assertions below, which read one section's windows
# against each other and would be answered differently by a member carrying
# none. Tokenised because the seed is free to spell the section
# `NURS-8100-Q2FF`, `NURS 8100 Q2FF`, or inside a course title, and none of those
# is a decision this suite should pin — what the ticket names is which course,
# which number and which section code.
WINDOWLESS_SECTION_TOKENS = ("NURS", "8100", "Q2FF")

# An RFC 3339 timestamp that carries an offset. The ticket's requirement is the
# offset — "never a bare date" — because E0-06 made the calendar timezone-aware
# throughout and a naive stamp hands E1 a value it has to guess a zone for.
#
# Strict about the offset and deliberately loose about the separator: RFC 3339
# fixes `+HH:MM` with the colon, so a compact `+0000` is refused, while `T`, `t`
# and a space are all read as the same choice about how to spell a separator,
# which is not what the ticket is about. Note what a bare `2026-09-08` would do
# without this check: `datetime.fromisoformat` parses it happily, at midnight, in
# no zone — so the value that fails the requirement is exactly the one that looks
# like it passed.
OFFSET_BEARING = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


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


def enrollment_of(member: dict[str, Any]) -> dict[str, Any] | None:
    """A member's enrollment window, or `None` where it carries none.

    `None` covers three different members — one with no extension key, one whose
    key is `null`, and one whose key holds something that is not an object — and
    E0-28 item 1 makes the first of those the seeded case and the other two
    wrong. So a test about *which* of them the platform serves asks the member
    directly rather than through this; see
    `test_the_windowless_member_carries_no_enrollment_extension_key_at_all`.
    """
    window = member.get(ENROLLMENT_EXTENSION)
    return window if isinstance(window, dict) else None


def windowless_members(rosters: list[tuple[Any, list[dict[str, Any]]]]) -> list[tuple[Any, Any]]:
    """Every seeded member carrying no enrollment window, with the section it is in.

    Kept as pairs because E0-28 item 1 is as much about *where* the member is as
    about what it lacks: "in a section away from the add-and-drop assertions" is
    half the criterion, and a member found without its context cannot answer it.
    """
    return [
        (context, member)
        for context, members in rosters
        for member in members
        if enrollment_of(member) is None
    ]


def the_windowless_member(platform: Any) -> tuple[Any, dict[str, Any]]:
    """The one seeded member with no enrollment window, or a failure saying what was found.

    Fails rather than answering the first of several, because every assertion
    that reads this member is about a member the ticket describes in the
    singular — and two of them would mean the tests below were describing
    whichever one the walk happened to reach first.
    """
    found = windowless_members(seeded_rosters(platform))
    assert len(found) == MEMBERS_WITHOUT_AN_ENROLLMENT_WINDOW, (
        f"{len(found)} seeded members carry no enrollment window and E0-28 item 1 seeds exactly "
        f"{MEMBERS_WITHOUT_AN_ENROLLMENT_WINDOW} — the ones found are "
        f"{[(context.context_id, member.get(MEMBER_ID)) for context, member in found]}. With none, "
        "no seeded roster shows E1 the platform that supplies no enrollment dates at all, which is "
        "every mainstream platform; with more than one, the seed has stopped being a single "
        "deliberate case beside the rule E0-15 states."
    )
    return found[0]


def tokens_published_about(platform: Any, context: Any) -> set[str]:
    """Every alphanumeric token the platform publishes about one section, upper-cased.

    The three places a section names itself to a tool — the launch's context
    claim, its resource link claim, and the `context` object on the membership
    container — split on everything that is not a letter or a digit. Tokens
    rather than a substring search, so `NURS-8100-Q2FF`, `NURS 8100 Q2FF` and a
    title carrying the same three words all answer the same question, and so
    that `Q2FF` cannot be found inside a longer opaque identifier.
    """
    strings = [
        value
        for claim in (CONTEXT_CLAIM, RESOURCE_LINK_CLAIM)
        for value in strings_in(context.launches[0].claims.get(claim))
    ]
    page = platform.membership_page(context.memberships_url)
    strings += strings_in(page.document.get("context"))
    return {
        token.upper() for value in strings for token in re.split(r"[^A-Za-z0-9]+", value) if token
    }


def carries_an_offset(value: Any) -> bool:
    """Whether `value` is an RFC 3339 timestamp that says which zone it is in."""
    return isinstance(value, str) and bool(OFFSET_BEARING.match(value.strip()))


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


def seeded_rosters(platform: Any) -> list[tuple[Any, list[dict[str, Any]]]]:
    """Every seeded context paired with the members of its roster, walked to the last page.

    Kept per-context rather than flattened, because one of the questions below is
    about a *section*: a member who enrolled after their classmates is only late
    relative to the section they are in, and across the whole institution two
    sections that start in different weeks would answer the question by
    themselves.
    """
    rosters = [
        (
            context,
            [
                member
                for page in platform.membership_pages(context.memberships_url)
                for member in page.members
            ],
        )
        for context in platform.seeded_contexts()
    ]
    assert any(members for _, members in rosters), (
        "Every seeded roster came back empty, so every assertion about the people in them would "
        "hold vacuously. E0-15 seeds 'students, instructors, and enrollments'."
    )
    return rosters


def seeded_members(platform: Any) -> list[dict[str, Any]]:
    """Every member of every seeded roster, with a guard against emptiness."""
    return [member for _, members in seeded_rosters(platform) for member in members]


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
# The seeded courses: their codes, their numbers, and their titles.
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


def test_every_seeded_context_carries_a_title(mock_platform: Any) -> None:
    """E0-15's criterion, and the requirement that replaced E0-14's opposite one.

    The mutation is one seeded context left with `id` alone — which is not
    hypothetical: it is what this mock was required to do until 2026-08-17, so it
    is a mutation that has already shipped once and would look, in a diff, like a
    ticket being honoured. `course.lms_title` is `NOT NULL` (E0-05), so E0-17
    seeding from this platform and E1 ingesting a launch from it both fail on the
    first titleless course, at a schema rule with nothing to say about a mock.

    Asserted over *every* seeded context, which is the whole difference between
    this and `test_a_seeded_context_carries_a_title` in E0-14's suite: an `any`
    test is satisfied by a seed where nine sections in ten are nameless.

    A title of whitespace is refused with one that is absent, because
    `course.lms_title` being `NOT NULL` is not the same as it being useful, and
    `" "` is what a serialiser writes when the seed row has an empty string in it.
    """
    untitled = []
    for context in mock_platform.seeded_contexts():
        claim = context.launches[0].claims.get(CONTEXT_CLAIM)
        title = claim.get("title") if isinstance(claim, dict) else None
        if not (isinstance(title, str) and title.strip()):
            untitled.append((context.context_id, claim))
    assert not untitled, (
        f"{len(untitled)} seeded context(s) carry no usable `title` — the first is "
        f"{untitled[0][1]!r}. E0-15: 'Every seeded context carries a `title`', which replaced "
        "E0-14's requirement that one context carry `id` alone (withdrawn 2026-08-17). "
        "`course.lms_title` is `NOT NULL`, so a nameless course fails at write time in E0-17 "
        "against a schema rule that has nothing to say about this mock."
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


def test_the_offset_check_reads_an_rfc_3339_stamp_and_refuses_a_bare_date() -> None:
    """The control on the check below, and the near miss is the whole reason for it.

    `2026-09-08` is a valid date, parses with `datetime.fromisoformat` without
    complaint, and is what an implementer writes for an enrollment that begins on
    a day. It is also the exact value E0-15 forbids — "an RFC 3339 timestamp with
    an offset, never a bare date" — so a check that merely parsed the value would
    accept the thing the requirement exists to refuse, and would look like it had
    asserted something (`docs/MISTAKES.md` entry 3).

    **Three of these cases exist to make two services agree.** A reviewer found
    that this repository held two answers to "is this an RFC 3339 timestamp": the
    AGS Score service refused a lower-case `z` and accepted ISO 8601's basic
    (`20260908T000000Z`) and comma-fraction (`…00,5Z`) forms, while the matcher
    here gave the opposite answer on all three — and nothing compared them. This
    one is right: RFC 3339 §5.6 notes that `T` and `Z` "may alternatively be
    lower case", and the same section fixes the extended spelling and writes
    `time-secfrac = "." 1*DIGIT`, so the comma is ISO's and not RFC 3339's. The
    three cases are pinned here and asserted against the Score service in
    `test_mock_lms_ags_line_items_and_scores.py`, so the two surfaces now agree
    by assertion rather than by coincidence.
    """
    for stamped in (
        "2026-09-08T00:00:00-04:00",
        "2026-09-08T00:00:00Z",
        "2026-09-08T09:30:00.500+00:00",
        "2026-09-08 00:00:00+00:00",
        "2026-09-08t00:00:00z",
    ):
        assert carries_an_offset(stamped), f"{stamped!r} is RFC 3339 and says which zone it is in."
    for naive in (
        "2026-09-08",
        "2026-09-08T00:00:00",
        "2026-09-08T00:00:00+0000",
        "20260908T000000Z",
        "2026-09-08T00:00:00,5Z",
        "September 8, 2026",
        "",
        None,
    ):
        assert not carries_an_offset(naive), (
            f"{naive!r} does not carry an offset, and E0-15 requires one: E0-06 made the calendar "
            "timezone-aware throughout, so a stamp without a zone is a value E1 has to guess at."
        )


def test_every_roster_member_but_one_carries_an_enrollment_start_with_an_offset(
    mock_platform: Any,
) -> None:
    """Criterion 6's first half, as E0-28 item 1 amends it: every member but exactly one.

    **Both directions are the criterion, which is why this test counts rather
    than checks for absence.** E0-15 requires the extension on every member and
    E0-28 item 1 adds one deliberate exception; a seed answering "none of them
    carry it" satisfies "not every member carries it" perfectly, and leaves E3
    with no denominator anywhere. So the windowless members are required to
    number exactly one, and every other member is required to carry an
    offset-bearing `start`.

    Three mutations. The first is the extension dropped altogether, or dropped
    from the instructors: SPEC §3.4 starts a late add's denominator at the
    student's first enrolled week "from NRPS enrollment data". The second is the
    exception spreading — a second member losing its window is the seed drifting
    away from the single case the ticket sanctions, and every add-and-drop
    assertion in this file quietly loses an input.

    The third is the near miss on the value: `"start": "2026-09-08"`. It is a
    date, it parses, it reads correctly in a response body, and it is what the
    requirement was written against — E0-06 made the calendar timezone-aware
    throughout, so a naive stamp is a value E1 has to pick a zone for, and
    whichever it picks is right for half the year.
    """
    rosters = seeded_rosters(mock_platform)
    members = [member for _, members in rosters for member in members]
    windowless = windowless_members(rosters)
    assert len(windowless) == MEMBERS_WITHOUT_AN_ENROLLMENT_WINDOW, (
        f"{len(windowless)} of {len(members)} roster members carry no `{ENROLLMENT_EXTENSION}` "
        f"object: {[(context.context_id, member.get(MEMBER_ID)) for context, member in windowless]}"
        f". E0-28 item 1 seeds exactly {MEMBERS_WITHOUT_AN_ENROLLMENT_WINDOW} such member — one, so "
        "E1 meets the platform that supplies no enrollment dates in a test, and only one, because "
        "E0-15's rule that the rest carry the extension is not reopened and SPEC §3.4 takes a late "
        "add's denominator from it."
    )
    exception = {id(member) for _, member in windowless}
    naive = [
        (member.get(MEMBER_ID), (enrollment_of(member) or {}).get("start"))
        for member in members
        if id(member) not in exception
        and not carries_an_offset((enrollment_of(member) or {}).get("start"))
    ]
    assert not naive, (
        f"{len(naive)} enrollment windows carry a `start` that is missing or has no offset: "
        f"{naive}. E0-15: '`start` is required on every member and is an RFC 3339 timestamp with "
        "an offset, never a bare date.' A bare date parses perfectly and lands at midnight in "
        "whatever zone the reader assumes, which is the failure the requirement is written "
        "against rather than a stricter spelling of it."
    )


def test_the_windowless_member_carries_no_enrollment_extension_key_at_all(
    mock_platform: Any,
) -> None:
    """E0-28 item 1: absent, not `null`, and not an object with a `null` `start`.

    **The three shapes are three different facts to a tool**, and only one of
    them is what a platform supplying no enrollment dates actually serves.
    `{"…/enrollment": null}` and `{"…/enrollment": {"start": null}}` are both a
    platform that *has* this extension and is telling you something about this
    member with it; an absent key is a platform that does not have it. E1 will
    write a `PlatformProfile` adapter (§7.3) that asks whether the extension is
    there at all, and a seed serving a null-valued key hands that adapter a
    member it reads as "this platform supplies windows and this student has
    none", which is the wrong branch.

    So this is asserted against the member's own keys rather than through
    `enrollment_of`, which cannot tell the three apart — and the near miss is
    exactly the tidy thing an implementer writes when the seed's `opened_at`
    becomes `str | None` and the serialiser keeps emitting the member.
    """
    context, member = the_windowless_member(mock_platform)
    assert ENROLLMENT_EXTENSION not in member, (
        f"The member with no enrollment window ({member.get(MEMBER_ID)} in {context.context_id}) "
        f"carries `{ENROLLMENT_EXTENSION}` = {member.get(ENROLLMENT_EXTENSION)!r}. E0-28 item 1 "
        "omits the key entirely, because an extension present and empty says 'this platform "
        "supplies enrollment windows and this student has none' while an absent one says 'this "
        "platform supplies none at all' — and those send a roster sync down different branches. "
        f"The member's keys are {sorted(member)}."
    )


def test_the_windowless_member_is_an_active_student_away_from_the_add_and_drop_section(
    mock_platform: Any,
) -> None:
    """E0-28 item 1's placement, which is half of what the item asks for.

    "In a section away from the add-and-drop assertions" is a requirement about
    the *seed*, and it is checkable: the member sits in `NURS-8100-Q2FF`, which
    is not the section whose windows
    `test_a_seeded_section_holds_one_member_who_enrolled_after_a_cohort` and
    `test_the_enrollment_window_ends_the_dropped_member_and_nobody_else` read
    against each other. Put the windowless member in that section instead and
    those two tests are reading a section with a member whose `start` is
    unknown — they would still pass, on one fewer input, which is the quiet
    version of this going wrong.

    Two more mutations, and both are seeds that read as reasonable. Making the
    windowless member the *dropped* one folds two edge cases into one person, so
    a tool that mishandles either is only ever seen failing once, and it puts a
    member with a `status` of `Inactive` and no window in front of E3 — a state
    the ticket does not ask for. Making it one of the two users the launch page
    signs launches for puts it in front of every other suite in this repository:
    E0-14's launch tests, the roster walk's lower bound and E3's future passback
    fixtures all reach for those users by name, and none of them is about a
    member with no enrollment window.

    The section is named by the tokens it publishes rather than by a string, for
    the reason `WINDOWLESS_SECTION_TOKENS` gives. If the seed has renamed the
    section, this test goes red and the message says so rather than leaving the
    next reader to wonder whether a defect was found.
    """
    context, member = the_windowless_member(mock_platform)

    published = tokens_published_about(mock_platform, context)
    missing = [token for token in WINDOWLESS_SECTION_TOKENS if token not in published]
    assert not missing, (
        f"The member with no enrollment window ({member.get(MEMBER_ID)}) is in context "
        f"{context.context_id}, which publishes {sorted(published)} and does not name {missing}. "
        "E0-28 item 1 places it in `NURS-8100-Q2FF`, a section away from the add-and-drop "
        "assertions in this file — those read one section's enrollment windows against each "
        "other, and a member carrying none is an input they silently lose."
    )
    assert member.get("status") == "Active", (
        f"The member with no enrollment window carries `status` {member.get('status')!r}. E0-28 "
        "item 1 makes it `Active`: a member that is both departed and windowless folds two edge "
        "cases into one person, so E3 never meets either on its own, and this file's `end` "
        "correspondence has a departed member it cannot read a window from."
    )
    assert str(member.get(MEMBER_ID)) not in context.subjects, (
        f"The member with no enrollment window is {member.get(MEMBER_ID)}, which is one of the "
        f"users the launch page signs launches for in {context.context_id} ({sorted(context.subjects)}"
        "). Those two users are reached by name from E0-14's launch suite, from the roster walk's "
        "lower bound and from every AGS fixture that posts a score, none of which is about a "
        "member with no enrollment window."
    )


def test_the_enrollment_window_ends_the_dropped_member_and_nobody_else(
    mock_platform: Any,
    instant_of: Any,
) -> None:
    """Criterion 6's second half: `end` is `null` until somebody drops.

    Two mutations, in opposite directions, and each looks reasonable on its own.
    A seed that writes the section's end date into every window makes every
    student look like a drop, so E3 stops updating scores for a whole section at
    the moment it syncs. A seed that leaves `end` null on everybody — including
    the member whose `status` says they have gone — leaves the drop visible in
    one field and invisible in the other, and E1 has to choose which to believe.

    So the correspondence is asserted in both directions rather than "somebody
    has an end": the members with an `end` are exactly the members NRPS reports
    as no longer active. Both sets are required non-empty first, because two
    empty sets correspond perfectly (`docs/MISTAKES.md` entry 3).

    **The key has to be present, not merely null**, and that assertion was
    missing until a reviewer proved it: this test read `.get("end") is not None`,
    which cannot tell `null` from absent, so emitting `{"start": …}` with no
    `end` key at all left every test in this suite green. ADR 0048 spends a
    paragraph on why present-and-null is the requirement — a tool meeting an
    absent key cannot tell "still enrolled" from "this platform supplies no end
    date", and those want different behaviour from a sync that has to decide
    whether a student has gone.

    **Amended for E0-28 item 1**, and the amendment is narrow on purpose. One
    seeded member now carries no enrollment extension at all, so the `end` rule
    is asked of the members that carry a window rather than of every member —
    `"end" not in (enrollment_of(member) or {})` was true of the windowless one
    and would have failed this test inside its own reading of the seed
    (`docs/MISTAKES.md` entry 22: a new rule making an earlier ticket's test
    unrunnable, with the repair on the far side of the test wall). What is *not*
    weakened: a member carrying a window and no `end` key still fails, which is
    the mutation this assertion exists for, and the windowless member is required
    elsewhere to be exactly one and to be `Active`.
    """
    members = seeded_members(mock_platform)
    windowed = [
        (member.get(MEMBER_ID), enrollment_of(member))
        for member in members
        if enrollment_of(member) is not None
    ]
    assert windowed, (
        "No seeded member carries an enrollment window at all, so every assertion below is about "
        "an empty set. E0-28 item 1 exempts exactly one member; the rest carry the extension "
        "E0-15 requires."
    )
    keyless = [name for name, window in windowed if "end" not in (window or {})]
    assert not keyless, (
        f"{len(keyless)} enrollment windows carry no `end` key at all — {keyless[:5]}. ADR 0048 "
        "makes `end` present and `null` for a member still enrolled: an absent key reads as "
        "'this platform does not supply end dates', which is a different fact from 'this student "
        "is still enrolled' and sends a sync down a different branch."
    )
    ended = {
        str(member.get(MEMBER_ID))
        for member in members
        if (enrollment_of(member) or {}).get("end") is not None
    }
    departed = {
        str(member.get(MEMBER_ID))
        for member in members
        if member.get("status") in ("Inactive", "Deleted")
    }
    assert ended and departed, (
        f"{len(ended)} members carry an enrollment `end` and {len(departed)} are reported "
        "`Inactive` or `Deleted`. E0-15 seeds one mid-term drop, and with either set empty the "
        "correspondence below is satisfied by a seed that has no drop in it at all."
    )
    assert ended == departed, (
        f"The members carrying an enrollment `end` are {sorted(ended)} and the members NRPS "
        f"reports as no longer active are {sorted(departed)}. E0-15: '`end` is `null` for a "
        "member still enrolled and a timestamp for one who dropped' — the two fields describe one "
        "fact, and a tool meeting them disagreeing has to pick one to believe."
    )
    backwards = []
    for member in members:
        window = enrollment_of(member) or {}
        opened, closed = instant_of(window.get("start")), instant_of(window.get("end"))
        if opened is not None and closed is not None and closed <= opened:
            backwards.append((member.get(MEMBER_ID), window))
    assert not backwards, (
        f"An enrollment window ends at or before it begins: {backwards}. A drop happens after an "
        "enrollment, so this is a seed with the two values swapped — which reads correctly in a "
        "response body and gives E3 a negative number of enrolled weeks."
    )


def test_a_seeded_section_holds_one_member_who_enrolled_after_a_cohort(
    mock_platform: Any,
    instant_of: Any,
) -> None:
    """Criterion 6's mid-term add, in the shape a late add actually has.

    **What this test used to assert, and why that was not enough.** It required
    some section to hold more than one distinct `start`, which a reviewer proved
    is satisfied by the opposite of a late add: setting the seed's late enrollment
    to a month *before* the section's other enrollments open left every test in
    this suite green, and so does a section with two cohorts that simply began in
    different weeks. "Not all the same" is a property of two very different
    seeds, and only one of them is the case §3.4's denominator rule is about.

    So the shape is asserted instead: in some section, exactly one member's
    `start` is strictly later than every other member's, and at least two other
    members in that section share one common `start`. That is what "the class
    began, and then somebody joined" looks like from the roster.

      - an *early* add is caught, because the outlier is then the earliest and
        the maximum is shared by the cohort;
      - two cohorts are caught, because the later cohort holds the maximum
        several times over;
      - a seed where every window in a section opens together is caught, which is
        the mutation the first version of this test was written for.

    The cohort is required to be **at least two members** rather than "everybody
    else", deliberately: a section's teaching instructor may reasonably be
    enrolled before their students, and a rule that demanded every other member
    agree would fail on that without a late add being anywhere in question.

    **What this still does not reach.** E0-15 says the added member's `start`
    falls after *its section's start date*, and no section start date is
    published anywhere on this surface — a section's dates are derived tool-side
    from its code and the term's start-letter map (§2.2), which live in Pulse's
    database and not in the platform. "After the cohort every other member
    belongs to" is the closest this surface comes, and it is not the same claim:
    a section where the cohort itself enrolled late is invisible here. Nor does
    it assert *which* member is the late one, since naming them would be this
    test carrying a copy of the seed.
    """
    opened: dict[str, list[Any]] = {}
    for context, members in seeded_rosters(mock_platform):
        starts = [instant_of((enrollment_of(member) or {}).get("start")) for member in members]
        opened[context.context_id] = [start for start in starts if start is not None]

    late = []
    for name, starts in opened.items():
        if len(starts) < 3:
            continue
        latest = max(starts)
        others = [start for start in starts if start != latest]
        cohort = max((others.count(start) for start in set(others)), default=0)
        if starts.count(latest) == 1 and cohort >= 2:
            late.append(name)

    assert late, (
        "No seeded section holds one member who enrolled after a cohort of their classmates: "
        + "; ".join(
            f"{name} opened at {sorted(str(start) for start in starts)}"
            for name, starts in sorted(opened.items())
        )
        + ". E0-15 criterion 6 seeds a mid-term add 'giving E3 the edge cases its property tests "
        "need'. A section whose enrollments all open together has nobody joining late; one whose "
        "outlier is *earlier* than the rest is an early add, which is not the case §3.4's "
        "denominator rule is about; and one holding two cohorts is two start dates rather than "
        "one late arrival."
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
