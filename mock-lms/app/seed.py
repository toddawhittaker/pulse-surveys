"""The people, courses and placements this platform pretends to have.

**The smallest seed that makes E0-14's seventh criterion mean something**: "a
signed launch for an arbitrary seeded user and role" needs at least two users and
at least two roles, or "arbitrary" is a word with nothing behind it. Two of each
is what is here. The larger seed set — mid-term adds and drops, a roster worth
paging — belongs to E0-15, which says in as many words that this data "belongs to
the mock platform and stays small".

Three things about the shape are deliberate rather than incidental.

**No personal data, at all.** There is no name claim, no email, no given or
family name — not invented ones either. LTI 1.3 requires none of them (`sub` is
the identifier, and SPEC §4 keys every response to it), so a platform that omits
them is conformant and is also what a platform sends when its privacy level is
anonymous. It means this service cannot leak what it does not hold, which is the
structural version of SPEC §10's rule about personally identifiable information
in logs.

**One context has a title and one has none.** E0-14's scope asks for both shapes
because LTI 1.3 makes the context claim's `title` optional while E0-05 shipped
`course.lms_title` as `NOT NULL`. Whoever writes the ingestion path in E1 needs to
meet the titleless case in a test rather than in a deployment, and the only way
that happens is if this file refuses to give every course a name.

**Every user is enrolled in every context.** The launch page offers a choice of
user and a choice of placement independently, so every combination of the two has
to be a launch that works. A user enrolled in one course and not the other would
put a dead option on the page.
"""

from dataclasses import dataclass, field

# The LIS v2 vocabularies LTI 1.3 draws role URIs from. Bare names — `Learner`,
# `Instructor` — are permitted only as a deprecated compatibility form, and SPEC
# §7.3 asks for strict core, so a mock that emitted one would teach E1's
# ingestion to read a shape no conformant platform sends.
MEMBERSHIP_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTITUTION_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#"

# What LTI 1.3 calls a section: the context claim's `type`, an array of URIs.
COURSE_SECTION_TYPE = "http://purl.imsglobal.org/vocab/lis/v2/course#CourseSection"


@dataclass(frozen=True)
class MockUser:
    """One person the platform will sign a launch for.

    `user_id` becomes the `sub` claim, and `label` is what the launch page shows
    in its selector — a description of the person's part in the fixture, never a
    name.
    """

    user_id: str
    label: str


@dataclass(frozen=True)
class MockContext:
    """One course section a launch can come from.

    `title` is `None` for the context that exercises the titleless case. It is
    left out of the claim entirely rather than sent as an empty string, because
    an absent member and an empty one are different things to a tool and the
    absent one is what a real platform sends.
    """

    context_id: str
    label: str
    title: str | None


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
    """What one user is, in one context.

    Roles are per enrollment and not per person, which is SPEC §2's rule read
    back onto the platform side: "people are not roles". Two roles are carried
    rather than one because a real platform sends several — a membership role and
    the institution role behind it — and a mock that sent exactly one would let
    E1's ingestion quietly assume a singleton array.
    """

    user_id: str
    context_id: str
    roles: tuple[str, ...]


LEARNER = MockUser(
    user_id="mock-lms-user-learner",
    label="A student enrolled in both sections",
)
INSTRUCTOR = MockUser(
    user_id="mock-lms-user-instructor",
    label="The instructor of both sections",
)

# The section code shapes come from SPEC §2.2 — `{startLetter}{ordinal}{modality}`
# — so that a label out of this platform looks like a label out of a real one.
# Nothing in E0-14 parses them; E0-07's parser is the tool's side of that.
TITLED_CONTEXT = MockContext(
    context_id="mock-lms-context-biol-215-r3ww",
    label="BIOL-215-R3WW",
    title="Cell Biology",
)
UNTITLED_CONTEXT = MockContext(
    context_id="mock-lms-context-math-140-e1ff",
    label="MATH-140-E1FF",
    title=None,
)


@dataclass(frozen=True)
class SeededPlatform:
    """Everything the platform knows, assembled once and read from every request."""

    users: tuple[MockUser, ...]
    placements: tuple[MockPlacement, ...]
    enrollments: tuple[MockEnrollment, ...] = field(default=())

    def user(self, user_id: str) -> MockUser | None:
        """The seeded user with this `sub`, or `None` — the caller decides the error."""
        return next((user for user in self.users if user.user_id == user_id), None)

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


def seeded_platform() -> SeededPlatform:
    """The seed, built fresh. Two users, two roles, two contexts, four enrollments."""
    placements = (
        MockPlacement(
            resource_link_id="mock-lms-link-biol-215-r3ww-weekly-pulse",
            title="Weekly Pulse",
            context=TITLED_CONTEXT,
        ),
        MockPlacement(
            resource_link_id="mock-lms-link-math-140-e1ff-weekly-pulse",
            title="Weekly Pulse",
            context=UNTITLED_CONTEXT,
        ),
    )
    learner_roles = (f"{MEMBERSHIP_ROLE}Learner", f"{INSTITUTION_ROLE}Student")
    instructor_roles = (f"{MEMBERSHIP_ROLE}Instructor", f"{INSTITUTION_ROLE}Instructor")
    enrollments = tuple(
        MockEnrollment(user_id=user.user_id, context_id=placement.context.context_id, roles=roles)
        for user, roles in ((LEARNER, learner_roles), (INSTRUCTOR, instructor_roles))
        for placement in placements
    )
    return SeededPlatform(
        users=(LEARNER, INSTRUCTOR),
        placements=placements,
        enrollments=enrollments,
    )
