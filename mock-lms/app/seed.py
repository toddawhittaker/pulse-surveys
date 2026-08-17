"""The people, courses and placements this platform pretends to have.

**Small on purpose.** E0-15: "this seed data belongs to the mock platform and
stays small". It is three sections in one term, each with a roster of its own —
enough that a roster pages, that one student joins late and one drops, and that
both modalities and more than one start letter reach a tool. The full demo
institution is
E0-17's, and it is seeded into Pulse's own database rather than into this
platform.

Six things about the shape are deliberate rather than incidental.

**Every course carries a title, and a number SPEC §8 admits.** `course.lms_title`
is `NOT NULL` (E0-05), so a titleless course is a row Pulse cannot store, and §8
refuses a course number outside its bands at write time — three digits only in
`000`-`799`, four only in `8000`-`9999`. The numbers below were picked against
that table. **Not** from `design/`: every distinct course number written across
those screens is invalid under the bands, `BIOL 2150` among them, so a seed
copied from a prototype would fail in E0-17 against a rule that has nothing to
say about this mock. E0-14 required one context to carry `id` alone so that E1
met the empty-title case in a test; Todd withdrew that on 2026-08-17 and E0-15's
"every seeded course needs a title" replaced it.

**Section codes are §2.2's `{startLetter}{ordinal}{modality}`, and they vary.**
More than one start letter and both modalities, because the start letter carries
the section's length *and* its start date within the term — one letter is one
calendar, and E0-07's parser would have one answer to be right about. Nothing
here parses them; that is the tool's side.

**No names, and email is the one personal field.** There is no `name`, no
`given_name`, no `family_name` — not invented ones either. E0-15's scope asks
NRPS for "email where exposed" and §7.3 has the roster sync use it, so the
addresses are here; every one of them is at a domain RFC 2606 and RFC 6761
reserve so that nothing can ever be delivered to it. See
`docs/adr/0050-the-mock-roster-exposes-an-address-and-no-name.md`.

**A person is not a role.** Roles, enrollment status and the enrollment window
all sit on the enrollment rather than on the person, which is SPEC §2's rule read
back onto the platform side. Two roles are carried rather than one because a real
platform sends several, and a mock that sent exactly one would let E1's ingestion
quietly assume a singleton array.

**The launch page offers the users enrolled everywhere, and that is computed.**
`launch_users()` answers the users enrolled in every seeded context, because the
page offers a user and a placement independently and every combination of the two
has to be a launch that works. E0-14 held that as a convention — "every user is
enrolled in every context" — which stopped being true the moment this seed grew a
student who takes one course.

**One enrollment window ends, and it is the same person the roster reports as
gone.** SPEC §3.4 has the tool learn about a drop from NRPS enrollment data, and
a seed where `status` and `end` disagree is one E1 has to pick a side in.
"""

from dataclasses import dataclass, field
from typing import Literal

# The LIS v2 vocabularies LTI 1.3 draws role URIs from. Bare names — `Learner`,
# `Instructor` — are permitted only as a deprecated compatibility form, and SPEC
# §7.3 asks for strict core, so a mock that emitted one would teach E1's
# ingestion to read a shape no conformant platform sends.
MEMBERSHIP_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTITUTION_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#"

# What LTI 1.3 calls a section: the context claim's `type`, an array of URIs.
COURSE_SECTION_TYPE = "http://purl.imsglobal.org/vocab/lis/v2/course#CourseSection"

# The three values NRPS 2.0 gives a membership `status`, as a type rather than as
# a convention: a status is one of three strings, and a `Literal` is what makes
# `"dropped"` a mypy failure at the line that writes it rather than a vocabulary
# only this mock has, discovered by E1 against a real platform.
MembershipStatus = Literal["Active", "Inactive", "Deleted"]

# Where mail to a seeded person goes, which is nowhere. RFC 2606 reserves
# `.invalid` precisely so a fixture never has to risk being delivered.
STUDENT_MAIL_DOMAIN = "students.mock-lms.invalid"
FACULTY_MAIL_DOMAIN = "faculty.mock-lms.invalid"

# Fall 2026 in the institution's default timezone (§3.1, `America/New_York`),
# which is on eastern daylight time for every date below. Written as a fixed
# offset rather than computed, because these are seed constants and a mock that
# resolved a zone at import would answer differently in March.
EASTERN_DAYLIGHT = "-04:00"

# The three 12-week start letters SPEC §2.2 seeds for Fall 2026 are U, R and Q,
# starting 8/17, 9/7 and 9/28. E is a 6-week letter; §2.2 fixes no date for it,
# so it takes the term's own start here. **The platform publishes none of these
# dates.** A section's calendar is derived tool-side from its code and the term's
# start-letter map, both of which live in Pulse's database rather than on a
# platform, so these appear only as the moment an enrollment opens.
R_SECTIONS_OPEN = f"2026-09-07T00:00:00{EASTERN_DAYLIGHT}"
E_SECTIONS_OPEN = f"2026-08-17T00:00:00{EASTERN_DAYLIGHT}"
Q_SECTIONS_OPEN = f"2026-09-28T00:00:00{EASTERN_DAYLIGHT}"

# The mid-term add and the mid-term drop E0-15 asks for, both in the 12-week
# `R3WW` section: one student enrolls three weeks after their classmates, and one
# leaves six weeks in. They are the only two enrollments in the seed that differ
# from their section's, which is what lets a test say the correspondence between
# `status` and `end` holds for exactly one person.
LATE_ADD_OPENS = f"2026-09-28T00:00:00{EASTERN_DAYLIGHT}"
DROP_CLOSES = f"2026-10-19T00:00:00{EASTERN_DAYLIGHT}"


@dataclass(frozen=True)
class MockUser:
    """One person the platform knows.

    `user_id` becomes the `sub` claim of a launch and the `user_id` of an NRPS
    member — SPEC §4 keys every response to it. `label` is what the launch page
    shows in its selector: a description of the person's part in the fixture,
    never a name. `email` is the one personal field this platform holds, and it
    is unroutable by construction.
    """

    user_id: str
    label: str
    email: str


@dataclass(frozen=True)
class MockContext:
    """One course section a launch can come from.

    `label` is the section as a human writes it — `BIOL-215-R3WW`, carrying the
    course number §8 bands and the section code §2.2 spells — and `title` is the
    course's name. Both are published; neither is parsed here.
    """

    context_id: str
    label: str
    title: str


@dataclass(frozen=True)
class MockPlacement:
    """One resource link — where in a course this tool was placed.

    Its `resource_link_id` is what makes two launches from the same placement the
    same placement, and it is what the launch page passes as `lti_message_hint`
    so the authorization request can say which placement it is for.
    """

    resource_link_id: str
    title: str
    context: MockContext


@dataclass(frozen=True)
class MockEnrollment:
    """What one user is, in one context, and for how long.

    Roles are per enrollment and not per person, which is SPEC §2's rule read
    back onto the platform side: "people are not roles". Two roles are carried
    rather than one because a real platform sends several — a membership role and
    the institution role behind it — and a mock that sent exactly one would let
    E1's ingestion quietly assume a singleton array.

    `opened_at` and `closed_at` are the enrollment window SPEC §3.4 takes a late
    add's denominator from. `closed_at` is `None` for a member still enrolled;
    where it is set, `status` says the same thing in NRPS's own vocabulary, and
    the two are written together here so they cannot drift.
    """

    user_id: str
    context_id: str
    roles: tuple[str, ...]
    status: MembershipStatus
    opened_at: str
    closed_at: str | None = None


LEARNER_ROLES = (f"{MEMBERSHIP_ROLE}Learner", f"{INSTITUTION_ROLE}Student")
INSTRUCTOR_ROLES = (f"{MEMBERSHIP_ROLE}Instructor", f"{INSTITUTION_ROLE}Instructor")

# The two people the launch page offers, enrolled in every section so that every
# combination of the page's two selectors is a launch that works.
LEARNER = MockUser(
    user_id="mock-lms-user-learner",
    label="A student enrolled in every section",
    email=f"learner@{STUDENT_MAIL_DOMAIN}",
)
INSTRUCTOR = MockUser(
    user_id="mock-lms-user-instructor",
    label="The instructor of every section",
    email=f"instructor@{FACULTY_MAIL_DOMAIN}",
)

# The three sections. Course numbers are read off SPEC §8's table: `215` and
# `140` are undergraduate three-digit numbers inside `000`-`799`, and `8100` is a
# doctoral four-digit number inside `8000`-`9999`. Section codes are §2.2's:
# more than one start letter, both modalities, `WW` online and `FF` face-to-face.
CELL_BIOLOGY = MockContext(
    context_id="mock-lms-context-biol-215-r3ww",
    label="BIOL-215-R3WW",
    title="Cell Biology",
)
COLLEGE_ALGEBRA = MockContext(
    context_id="mock-lms-context-math-140-e1ff",
    label="MATH-140-E1FF",
    title="College Algebra",
)
NURSING_INQUIRY = MockContext(
    context_id="mock-lms-context-nurs-8100-q2ff",
    label="NURS-8100-Q2FF",
    title="Doctoral Practice Inquiry",
)


@dataclass(frozen=True)
class SeededPlatform:
    """Everything the platform knows, assembled once and read from every request."""

    users: tuple[MockUser, ...]
    contexts: tuple[MockContext, ...]
    placements: tuple[MockPlacement, ...]
    enrollments: tuple[MockEnrollment, ...] = field(default=())

    def user(self, user_id: str) -> MockUser | None:
        """The seeded user with this `sub`, or `None` — the caller decides the error."""
        return next((user for user in self.users if user.user_id == user_id), None)

    def context(self, context_id: str) -> MockContext | None:
        """The seeded section with this context ID, or `None`."""
        return next(
            (context for context in self.contexts if context.context_id == context_id),
            None,
        )

    def placement(self, resource_link_id: str) -> MockPlacement | None:
        """The seeded placement with this resource link ID, or `None`."""
        return next(
            (
                placement
                for placement in self.placements
                if placement.resource_link_id == resource_link_id
            ),
            None,
        )

    def roles(self, user_id: str, context_id: str) -> tuple[str, ...] | None:
        """What `user_id` is in `context_id`, or `None` when they are not enrolled.

        `None` rather than an empty tuple, and the difference is the point: LTI
        1.3 permits a launch with no roles, so an empty array is a legitimate
        answer and cannot double as "no such enrollment".
        """
        for enrollment in self.enrollments:
            if enrollment.user_id == user_id and enrollment.context_id == context_id:
                return enrollment.roles
        return None

    def enrollments_in(self, context_id: str) -> tuple[MockEnrollment, ...]:
        """One section's roster, in seeded order.

        Seeded order rather than sorted, because it is the order the pages of a
        membership container divide, and a roster that reordered itself between
        two requests would page members into two places at once.
        """
        return tuple(
            enrollment for enrollment in self.enrollments if enrollment.context_id == context_id
        )

    def launch_users(self) -> tuple[MockUser, ...]:
        """The users the launch page may offer: those enrolled in every context.

        Computed rather than listed. The page offers a user and a placement
        independently, so every combination has to be a launch that works — a
        user enrolled in one section and not another would put a dead option on
        the page, and a `400` at the end of it reads as a broken platform.
        """
        context_ids = [context.context_id for context in self.contexts]
        return tuple(
            user
            for user in self.users
            if all(self.roles(user.user_id, context_id) is not None for context_id in context_ids)
        )


def student(context: MockContext, ordinal: int) -> MockUser:
    """One student who takes exactly this section, with an address nobody receives.

    Generated rather than written out, because a hand-written identifier per
    student is one more chance to typo one person into two. The identifier
    carries the section so that a member seen in a response says which roster it
    came from without a lookup.

    **The zero-padded ordinal is load-bearing, and renumbering the seed means
    changing a test.** It is contiguous from 01 within a section, and E0-15's
    scope says so in as many words, because it is the only ground truth on this
    surface for the definition of done's "no member is dropped" — an NRPS
    container carries no total, so nothing in a roster can say whether the roster
    is short. A test assembles one section's ordinals and requires them to run
    without a gap. That replaced a weaker check against the two users the launch
    page offers, which sit at the head of every roster and so survived a page
    slice that lost a member per boundary.
    """
    slug = f"{context.label.lower()}-student-{ordinal:02d}"
    return MockUser(
        user_id=f"mock-lms-user-{slug}",
        label=f"A student in {context.label}",
        email=f"{slug}@{STUDENT_MAIL_DOMAIN}",
    )


def enrolled(
    user: MockUser,
    context: MockContext,
    roles: tuple[str, ...],
    opened_at: str,
    *,
    status: MembershipStatus = "Active",
    closed_at: str | None = None,
) -> MockEnrollment:
    """One enrollment, with its window."""
    return MockEnrollment(
        user_id=user.user_id,
        context_id=context.context_id,
        roles=roles,
        status=status,
        opened_at=opened_at,
        closed_at=closed_at,
    )


def seeded_platform() -> SeededPlatform:
    """The seed, built fresh: the sections, the people in them, and their enrollments.

    The three roster sizes are chosen against the page size in `app.nrps`, and
    each is a case rather than a number picked to look plausible:

      - `BIOL-215-R3WW` holds twelve, which is two full pages and a short one;
      - `MATH-140-E1FF` holds seven, which is one full page and a short one;
      - `NURS-8100-Q2FF` holds five, which is exactly one page and no more — the
        boundary where a platform that advertises a next page whenever the page
        it just served was full serves an empty one.
    """
    contexts = (CELL_BIOLOGY, COLLEGE_ALGEBRA, NURSING_INQUIRY)
    placements = tuple(
        MockPlacement(
            resource_link_id=f"mock-lms-link-{context.label.lower()}-weekly-pulse",
            title="Weekly Pulse",
            context=context,
        )
        for context in contexts
    )

    # How many students each section holds beyond the two the launch page offers,
    # and when its enrollments open.
    sections = (
        (CELL_BIOLOGY, 10, R_SECTIONS_OPEN),
        (COLLEGE_ALGEBRA, 5, E_SECTIONS_OPEN),
        (NURSING_INQUIRY, 3, Q_SECTIONS_OPEN),
    )

    users: list[MockUser] = [INSTRUCTOR, LEARNER]
    enrollments: list[MockEnrollment] = []
    for context, class_size, opens in sections:
        enrollments.append(enrolled(INSTRUCTOR, context, INSTRUCTOR_ROLES, opens))
        enrollments.append(enrolled(LEARNER, context, LEARNER_ROLES, opens))
        for ordinal in range(1, class_size + 1):
            person = student(context, ordinal)
            users.append(person)
            enrollments.append(enrolled(person, context, LEARNER_ROLES, opens))

    return SeededPlatform(
        users=tuple(users),
        contexts=contexts,
        placements=placements,
        enrollments=tuple(with_the_add_and_the_drop(enrollments)),
    )


def with_the_add_and_the_drop(enrollments: list[MockEnrollment]) -> list[MockEnrollment]:
    """Replace two of `BIOL-215-R3WW`'s enrollments with a late add and a drop.

    Applied as a rewrite over a uniform class rather than written into the loop
    above, so that "which two people differ, and how" is one function a reader
    can check against SPEC §3.4 — the late add's denominator starts at their
    first enrolled week, and a drop stops scores updating.

    Both are `BIOL-215-R3WW`'s, because criterion 6 is asserted **within a
    section**: across the institution, two sections that simply start in
    different weeks look exactly like a late add and are not one.
    """
    late_add = student(CELL_BIOLOGY, 4).user_id
    dropped = student(CELL_BIOLOGY, 7).user_id
    rewritten: list[MockEnrollment] = []
    for enrollment in enrollments:
        if enrollment.context_id != CELL_BIOLOGY.context_id:
            rewritten.append(enrollment)
        elif enrollment.user_id == late_add:
            rewritten.append(
                MockEnrollment(
                    user_id=enrollment.user_id,
                    context_id=enrollment.context_id,
                    roles=enrollment.roles,
                    status="Active",
                    opened_at=LATE_ADD_OPENS,
                )
            )
        elif enrollment.user_id == dropped:
            rewritten.append(
                MockEnrollment(
                    user_id=enrollment.user_id,
                    context_id=enrollment.context_id,
                    roles=enrollment.roles,
                    status="Inactive",
                    opened_at=enrollment.opened_at,
                    closed_at=DROP_CLOSES,
                )
            )
        else:
            rewritten.append(enrollment)
    return rewritten
