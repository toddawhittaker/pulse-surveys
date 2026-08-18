"""The people this provider can sign in, and the assignments that let it.

**Small on purpose**, like the platform's seed: eight people, one per web-login
role plus the person E0-16's scope asks for by name. The full demo institution is
E0-17's and lives in Pulse's own database; nothing here is a substitute for it,
and nothing here is written into Pulse by this service.

Three things about the shape are deliberate rather than incidental.

**A person is not a role, and a door is a property of the assignment.** SPEC §2:
"People are not roles. A person holds one or more *role assignments*, each scoped
to a node in the org hierarchy", and "Entry doors are a property of the
assignment, not the person. A person holding two assignments uses whichever door
fits the one they are acting under." So a person here is a subject with a tuple
of assignments, and whether they may use this door is computed from those
assignments rather than stored on the person. That is what makes the two-hat
person below fall out of the model instead of being a special case.

**The web door admits every role except instructor and student.** §2's table
gives Lead Faculty, Chair, Assistant Dean, Dean and the VP of Academics both
doors, Care and Admin the web door only, and the instructor and the student the
launch door only. `WEB_LOGIN_ROLES` is written as that sentence — the whole set
minus the two — rather than as a list, so a role added later is admitted unless
somebody says otherwise, which is the direction §2 phrases the rule in.

**A session states roles and never a scope.** Every assignment below carries the
node it is scoped to, in words, and none of it reaches an `id_token`: purview is
computed by Pulse from its own supervision graph (§2.1), and a provider that
shipped one would have invented a scope nothing granted. The scope strings are
published in the seed document (`/mock/registration`) because a later ticket
seeding the same institution needs to know what this provider thinks these people
are, and they are prose for that reader rather than identifiers for a resolver.
See `docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md`.
"""

from dataclasses import dataclass
from enum import StrEnum

# Where mail to a seeded person goes, which is nowhere: RFC 2606 reserves
# `.invalid` precisely so a fixture never has to risk being delivered. The same
# choice `mock-lms/app/seed.py` makes, for the same reason.
MAIL_DOMAIN = "mock-idp.invalid"


class Role(StrEnum):
    """The roles SPEC §2 defines, spelled as this project spells them.

    The values match the labels E0-09's `role_assignment.role` enumerates, so a
    session issued here and a row in Pulse's database say the same word about the
    same person. A `StrEnum` rather than a set of strings: a role that is not one
    of these cannot be constructed, which is a mypy failure at the line that
    writes it rather than a vocabulary only this mock has.
    """

    VP_ACADEMICS = "VP_ACADEMICS"
    DEAN = "DEAN"
    ASSISTANT_DEAN = "ASSISTANT_DEAN"
    CHAIR = "CHAIR"
    LEAD_FACULTY = "LEAD_FACULTY"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"
    CARE = "CARE"
    ADMIN = "ADMIN"


# SPEC §2: "Every role except instructor and student can *also* enter by web
# login; Care and Admin are web login only ..., and students enter by launch
# only." Written as the complement rather than as a list, because that is how the
# spec phrases it and because a list would have to be edited twice — once for the
# role and once for its door — where this has to be edited once.
LAUNCH_ONLY_ROLES = frozenset({Role.INSTRUCTOR, Role.STUDENT})
WEB_LOGIN_ROLES = frozenset(Role) - LAUNCH_ONLY_ROLES


@dataclass(frozen=True)
class Assignment:
    """One role assignment: what a person is, and where.

    `scope` is the containment node in words — "the College of Sciences", "BIOL
    215" — and it is documentation. Nothing computes with it, nothing puts it in
    a token, and Pulse's own purview comes from its supervision graph (§2.1).
    """

    role: Role
    scope: str

    @property
    def opens_the_web_door(self) -> bool:
        """Whether this assignment lets its holder in through web login (§2)."""
        return self.role in WEB_LOGIN_ROLES


@dataclass(frozen=True)
class MockPerson:
    """One person this provider knows, and every assignment they hold.

    `subject` becomes the `sub` claim, and it is what the login form posts.
    `label` is what the form shows a human: a description of the person's part in
    the fixture, never a name — Pulse owns person names (§2.1, "Pulse-owned —
    people graph: person records (name, category)"), so an identity provider
    inventing one would be inventing the half of the record Pulse is responsible
    for. `email` is the one personal field here and is unroutable by
    construction.

    `lms_user_id` is the launch-side identity of the same human, where there is
    one. It is `None` for everybody but the two-hat person, and for her it names
    the user `mock-lms/app/seed.py` seeds as the instructor of every section —
    which is the whole content of "the doors are a property of the assignment":
    the same person, two identities, two doors, one of which this provider will
    not open.
    """

    subject: str
    label: str
    email: str
    assignments: tuple[Assignment, ...]
    lms_user_id: str | None = None

    @property
    def web_login_roles(self) -> tuple[Role, ...]:
        """The roles this person may act under *here*, in seeded order.

        Deduplicated, because two assignments in one role are legal — a lead
        faculty leads two courses — and a session stating a role twice is a shape
        a client has to think about for no reason.
        """
        found: list[Role] = []
        for assignment in self.assignments:
            if assignment.opens_the_web_door and assignment.role not in found:
                found.append(assignment.role)
        return tuple(found)

    @property
    def launch_only_roles(self) -> tuple[Role, ...]:
        """The roles this person holds that enter by LTI launch only (§2)."""
        found: list[Role] = []
        for assignment in self.assignments:
            if not assignment.opens_the_web_door and assignment.role not in found:
                found.append(assignment.role)
        return tuple(found)

    @property
    def may_use_web_login(self) -> bool:
        """Whether this door is one of this person's, at all.

        One predicate, two readers: the login form offers exactly the people it
        answers `True` for, and the login handler refuses exactly the people it
        answers `False` for. Two copies of that rule could disagree, and the
        disagreement would be a door that offers an identity it then refuses —
        or, in the direction that matters, refuses to offer one it will sign in
        anyway (`docs/MISTAKES.md` entry 13).
        """
        return bool(self.web_login_roles)


@dataclass(frozen=True)
class SeededDirectory:
    """Everybody this provider knows, assembled once and read from every request."""

    people: tuple[MockPerson, ...]

    def person(self, subject: str) -> MockPerson | None:
        """The seeded person with this `sub`, or `None` — the caller decides the error."""
        return next((person for person in self.people if person.subject == subject), None)

    def web_login_people(self) -> tuple[MockPerson, ...]:
        """The people the login form may offer: those holding a web-door assignment."""
        return tuple(person for person in self.people if person.may_use_web_login)


def person(
    slug: str,
    label: str,
    assignments: tuple[Assignment, ...],
    lms_user_id: str | None = None,
) -> MockPerson:
    """One seeded person, with an address nobody receives.

    The subject and the address are both built from `slug`, so a `sub` seen in a
    session, a log or a database row says which seeded person it is without a
    lookup, and so that no hand-written identifier can typo one person into two.
    """
    return MockPerson(
        subject=f"mock-idp-user-{slug}",
        label=label,
        email=f"{slug}@{MAIL_DOMAIN}",
        assignments=assignments,
        lms_user_id=lms_user_id,
    )


# The containment nodes these assignments hang off, named once. They are the
# worked examples SPEC §2.1 uses — a college, a department that groups prefixes,
# a course — so that a reader comparing this seed with the spec is comparing the
# same institution. E0-17 seeds a demo institution into Pulse's own database; if
# these ever need to be the same rows, that is the ticket that decides it.
INSTITUTION = "the institution"
COLLEGE = "the College of Sciences"
DEPARTMENT = "the Mathematics department"
COURSE = "BIOL 215"
SECTION = "BIOL-215-R3WW"

# The launch-side identity of the two-hat person, as `mock-lms/app/seed.py` seeds
# it. A reference across the two mocks, and the only one either of them holds: it
# is what lets E0-18 drive the same human through both doors and see one identity
# with two assignments rather than two unrelated fixtures. If the platform's seed
# renames that user, this goes stale silently — `docs/MISTAKES.md` entry 1 — so
# it is named here, once, rather than assembled anywhere else.
LMS_INSTRUCTOR_USER_ID = "mock-lms-user-instructor"


def seeded_directory() -> SeededDirectory:
    """The seed, built fresh: one person per web-login role, and the two-hat person.

    The order is the order the login form offers them in, and it runs down §2.1's
    supervision chain — VP, dean, assistant dean, chair, lead faculty — before the
    two roles that sit outside the graph entirely. Nothing depends on the order;
    it is here so that a form offering eight people reads like the org chart
    rather than like a set.

    **The assistant dean is seeded although E0-16's scope does not list her.**
    §2's table gives that role the web door like every other leadership role, and
    §2.1 makes her the worked example for why purview comes from the supervision
    graph rather than from containment — her own led courses together with every
    supervised chair's department, "a set no single containment node holds". A door that
    could not admit the one role the purview model is written around would be a
    gap E9 discovers rather than E0.

    **The last person is the one the ticket asks for by name.** She holds a Care
    assignment and an instructor assignment: "unlikely in practice but legitimate,
    and it is the case that proves the doors are a property of the assignment
    rather than the person". Her session states `CARE` and nothing else, because
    her instructor assignment does not open this door — not because anything here
    filters it out afterwards.
    """
    return SeededDirectory(
        people=(
            person(
                "vpaa",
                "The VP of Academics",
                (Assignment(Role.VP_ACADEMICS, INSTITUTION),),
            ),
            person(
                "dean",
                f"The dean of {COLLEGE}",
                (Assignment(Role.DEAN, COLLEGE),),
            ),
            person(
                "assistant-dean",
                f"An assistant dean in {COLLEGE}",
                (Assignment(Role.ASSISTANT_DEAN, COLLEGE),),
            ),
            person(
                "chair",
                f"The chair of {DEPARTMENT}",
                (Assignment(Role.CHAIR, DEPARTMENT),),
            ),
            person(
                "lead-faculty",
                f"The lead faculty for {COURSE}",
                (Assignment(Role.LEAD_FACULTY, COURSE),),
            ),
            person(
                "admin",
                "An administrator of the Pulse console",
                (Assignment(Role.ADMIN, INSTITUTION),),
            ),
            person(
                "care",
                "The Office of Community Standards",
                (Assignment(Role.CARE, INSTITUTION),),
            ),
            person(
                "care-who-teaches",
                "Care, and teaching a section by the other door",
                (
                    Assignment(Role.CARE, INSTITUTION),
                    Assignment(Role.INSTRUCTOR, SECTION),
                ),
                lms_user_id=LMS_INSTRUCTOR_USER_ID,
            ),
        )
    )
