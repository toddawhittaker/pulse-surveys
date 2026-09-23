"""Defining, editing and deleting a named comparison set (SPEC §5.1, §13).

SPEC §5.1 lets leadership "define named sets" beside the computed default set;
E5-01 built the two tables that hold one and E5-04 the read that resolves one to
sections. This is the write half and the scope around it — everything
`app.api.leadership`'s seven routes do once the session has been established.

**A module of its own, because neither of the two candidates fits** (ADR 0173).
`app.services.benchmarks` resolves populations and seals figures, and nothing
in it writes; `app.services.authz` is SPEC §13's one authorization
chokepoint, and a write path living inside it would make that module the place
where writes happen as well as the place where permission is decided.

**Scope is ownership by the creator, and it is asymmetric on purpose** (ADR
0173). Every leadership session reads every set in the institution — a set's
name, its declared pair and its counts are not confidential, and §5.1's
set-definition surface is one institution-wide list that two leaders must be able
to see the same version of. Only the leader whose `person` row defined a set may
edit or delete it, and `SetSummary.editable` is that decision on the wire.
Purview over the supervision graph is E9's (E5's breakdown decision 4); nothing
here computes one.

**Every rule about what a set may be is the database's, and this module
translates.** SPEC §2.2's eight lengths are a `CHECK`, SPEC §8's five levels are
a Postgres enum type, and the rule that a member course sits at the set's
declared level is a composite foreign key with a `CHECK` over the two columns of
one row (E5-01, ADR 0164, ADR 0018). So a write here is *attempted*: the
statement runs, Postgres refuses it, and `_refusal` maps the constraint that
fired to one sentence out of `app.copy.leadership_sets`. Re-stating any of those
rules in Python would be a second copy of a rule that can disagree with the
first, and it would mean the routes' refusals proved nothing about the database.

**The membership row's `course_level` is read from the `course` table inside the
insert**, as a scalar subquery rather than as a value this module looked up
first. That is what makes the two membership refusals distinguishable while
leaving both of them the database's: a course of another level lands its real
level in the row and the `the_levels_agree` check refuses it, and a key that is
no course at all produces no level at all and the `NOT NULL` refuses it. A lookup
in Python would have to decide what to do with the empty result itself, which is
this module refusing a write rather than translating a refusal.

**Membership is replaced wholesale on an edit, never patched.** The rows are
deleted and the new ones inserted, in that order and before the set row is
updated — the membership rows hold the set's level under a composite foreign key,
so a set whose declared level changes cannot keep the children that named the old
one. It is also why `pulse_app` is granted no `UPDATE` on the membership table
(`comparison_set_write_grants_v001.sql`): nothing in this product edits a
membership row in place.

**No `audit_log` row is written for any of this, and that is a decision** (ADR
0174). What is recorded is on the row: the creator and `created_at` on a create,
`updated_at` on an edit. A delete leaves nothing behind, and
`docs/tickets/e5/deferred.md` carries that gap with its owner.

**The instants come from `app.services.clock`**, never from `datetime.now`. Every
other date in this product is the clock's, so that a development stack standing
in a seeded term stamps rows in that term rather than months away from it (ADR
0109).

**Synchronous, on the request's own session** (ADR 0013), and each write commits
once at its end: `app.db.get_session` leaves committing to the caller, so a
service that did not commit would answer 201 over a transaction the dependency
then rolled back.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Table,
    UniqueConstraint,
    func,
    insert,
    select,
    update,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.copy.leadership_sets import (
    LENGTH_NOT_A_CALENDAR_LENGTH,
    LEVEL_NOT_A_COURSE_LEVEL,
    MEMBER_NOT_A_COURSE,
    MEMBER_NOT_AT_THE_SETS_LEVEL,
    NAME_ALREADY_USED,
)
from app.models.benchmark import CALENDAR_LENGTHS, ComparisonSet, ComparisonSetMember
from app.models.org import Course, CourseLevel, Prefix
from app.schemas.comparison_sets import (
    CourseOption,
    SetDetail,
    SetOptions,
    SetPreview,
    SetSummary,
    SetWrite,
)
from app.services import clock
from app.services.benchmarks import resolve_named_set

__all__ = [
    "NotTheSetsDefinerError",
    "SetUnavailableError",
    "WriteRefusedError",
    "create_set",
    "definition_options",
    "delete_set",
    "edit_set",
    "listed_sets",
    "preview_of",
    "read_set",
]

# The two statuses the write refusals are answered with. A duplicate name is a
# conflict with a row that is already there; the other four are values this
# institution does not have, which is what 422 says.
NAME_CONFLICT_STATUS = 409
REFUSED_VALUE_STATUS = 422

# Postgres' SQLSTATEs for the two refusals that carry no constraint name. A level
# that is not one of the five is refused by the cast into the `course_level`
# enum, which names no constraint because the type is the rule; a member key that
# is no course leaves the membership row's `course_level` empty, and `NOT NULL`
# names a column rather than a constraint.
INVALID_TEXT_REPRESENTATION = "22P02"
NOT_NULL_VIOLATION = "23502"


class SetUnavailableError(Exception):
    """No set carries this id — the 404 every keyed route answers."""


class NotTheSetsDefinerError(Exception):
    """This set was defined by another leader — the 403 an edit and a delete answer."""


class WriteRefusedError(Exception):
    """The database refused a write, translated into one sentence and one status.

    Carries both because the five refusals do not share a status: a name already
    used is a conflict and the other four are values outside a closed set.
    """

    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _unique_over(table: Table, columns: tuple[str, ...]) -> str:
    """The name Postgres knows one unique constraint by, found by the columns it covers."""
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and tuple(constraint.columns.keys()) == columns:
            if constraint.name is None:  # pragma: no cover - the convention names every one
                break
            return str(constraint.name)
    raise RuntimeError(f"`{table.name}` declares no unique constraint over {list(columns)}.")


def _check_ending(table: Table, rule: str) -> str:
    """The name Postgres knows one check constraint by, found by the rule it holds."""
    for constraint in table.constraints:
        name = constraint.name
        if (
            isinstance(constraint, CheckConstraint)
            and name is not None
            and str(name).endswith(rule)
        ):
            return str(name)
    raise RuntimeError(f"`{table.name}` declares no check constraint named for `{rule}`.")


def _foreign_key_to(table: Table, target: str) -> str:
    """The name Postgres knows one foreign key by, found by the table it references."""
    for constraint in table.constraints:
        if (
            isinstance(constraint, ForeignKeyConstraint)
            and constraint.referred_table.name == target
        ):
            if constraint.name is None:  # pragma: no cover - the convention names every one
                break
            return str(constraint.name)
    raise RuntimeError(f"`{table.name}` declares no foreign key to `{target}`.")


# Which sentence each constraint's refusal is translated into.
#
# **Read off the models rather than transcribed**, because a constraint renamed
# in `app.models.benchmark` and not here would fall through to a 500 on exactly
# the request this module exists to answer politely (`docs/MISTAKES.md` entry
# 19). The three rules are named the way E5-01 names them and the lookup is what
# turns each into the name Postgres reports — the naming convention's prefix is
# applied at DDL time and is not a string worth repeating in two places.
#
# Both tables are read off the shared metadata rather than through `__table__`,
# which a declarative class types as the wider `FromClause` — a clause the three
# readers above could not walk, and one whose narrowing would be an assertion
# rather than a lookup.
_SET_TABLE = ComparisonSet.metadata.tables[ComparisonSet.__tablename__]
_MEMBER_TABLE = ComparisonSetMember.metadata.tables[ComparisonSetMember.__tablename__]

REFUSAL_BY_CONSTRAINT = {
    _check_ending(_SET_TABLE, "length_is_a_calendar_length"): (
        REFUSED_VALUE_STATUS,
        LENGTH_NOT_A_CALENDAR_LENGTH,
    ),
    _unique_over(_SET_TABLE, ("name",)): (NAME_CONFLICT_STATUS, NAME_ALREADY_USED),
    _check_ending(_MEMBER_TABLE, "the_levels_agree"): (
        REFUSED_VALUE_STATUS,
        MEMBER_NOT_AT_THE_SETS_LEVEL,
    ),
    _foreign_key_to(_MEMBER_TABLE, Course.__tablename__): (
        REFUSED_VALUE_STATUS,
        MEMBER_NOT_A_COURSE,
    ),
}


def _refusal(refused: Exception) -> WriteRefusedError:
    """Translate what Postgres refused into the one sentence naming the rule.

    **Anything this cannot name is re-raised**, and that is deliberate: a
    translator that answered 422 to every `IntegrityError` would turn a defect in
    this module — a null creator, a key collision, a constraint nobody thought
    about — into a polite refusal blaming the caller for a body that was fine.
    """
    original: Any = getattr(refused, "orig", None)
    diagnostic: Any = getattr(original, "diag", None)
    constraint = getattr(diagnostic, "constraint_name", None)
    if constraint in REFUSAL_BY_CONSTRAINT:
        status_code, detail = REFUSAL_BY_CONSTRAINT[constraint]
        return WriteRefusedError(status_code=status_code, detail=detail)
    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate == INVALID_TEXT_REPRESENTATION:
        return WriteRefusedError(status_code=REFUSED_VALUE_STATUS, detail=LEVEL_NOT_A_COURSE_LEVEL)
    column = getattr(diagnostic, "column_name", None)
    if sqlstate == NOT_NULL_VIOLATION and column == ComparisonSetMember.course_level.key:
        return WriteRefusedError(status_code=REFUSED_VALUE_STATUS, detail=MEMBER_NOT_A_COURSE)
    raise refused


def _the_set(session: Session, *, set_id: UUID) -> ComparisonSet:
    """One set by key, or the 404 every keyed route shares.

    The same refusal whether a leader defined the set or somebody else did: an
    id that is not there is not there for anybody, and a 403 for an unknown set
    would tell a caller that a set exists and belongs to another leader.
    """
    found = session.get(ComparisonSet, set_id)
    if found is None:
        raise SetUnavailableError
    return found


def _her_set(session: Session, *, set_id: UUID, person_id: UUID | None) -> ComparisonSet:
    """One set this session's person may write, or the refusal saying which rule stopped it.

    The unknown-set refusal comes first, so the two are never confused: a set
    that is not there is a 404 and somebody else's set is a 403.

    **A session naming no person writes nothing.** A leadership session always
    names one — the role is resolved from that person's assignments at the door
    (ADR 0098) — so this is the fail-closed answer to a state the doors do not
    produce, rather than a case with a meaning of its own.
    """
    found = _the_set(session, set_id=set_id)
    if person_id is None or found.created_by_person_id != person_id:
        raise NotTheSetsDefinerError
    return found


def _member_course_ids(session: Session, *, set_id: UUID) -> list[UUID]:
    """The course keys one set names, in a stable order."""
    return list(
        session.scalars(
            select(ComparisonSetMember.course_id)
            .where(ComparisonSetMember.set_id == set_id)
            .order_by(ComparisonSetMember.course_id)
        )
    )


def _summary(found: ComparisonSet, *, member_count: int, person_id: UUID | None) -> SetSummary:
    """One set as the list carries it, with `editable` saying who defined it."""
    return SetSummary(
        id=found.id,
        name=found.name,
        length_weeks=found.length_weeks,
        level=str(found.level),
        member_count=member_count,
        editable=person_id is not None and found.created_by_person_id == person_id,
    )


def _detail(session: Session, *, found: ComparisonSet, person_id: UUID | None) -> SetDetail:
    """One set on its own: the summary, its membership and its two instants."""
    members = _member_course_ids(session, set_id=found.id)
    summary = _summary(found, member_count=len(members), person_id=person_id)
    return SetDetail(
        **summary.model_dump(),
        member_course_ids=members,
        created_at=found.created_at,
        updated_at=found.updated_at,
    )


def _write_membership(
    session: Session, *, set_id: UUID, level: str, course_ids: Sequence[UUID]
) -> None:
    """Insert one membership row per course, with the course's own level read in the statement.

    **The level comes out of the `course` table inside the insert**, which is what
    leaves both membership refusals to the database — see the module docstring.

    **The list is de-duplicated, which is not a validation.** A course named twice
    is one course in the cohort; storing it twice would weight its sections twice
    in every figure the set produces and in the section count the benchmark
    minimum is measured against (SPEC §4.1 item 7). `dict.fromkeys` keeps the
    order the definer chose.
    """
    for course_id in dict.fromkeys(course_ids):
        session.execute(
            insert(ComparisonSetMember).values(
                set_id=set_id,
                set_level=level,
                course_id=course_id,
                course_level=select(Course.level).where(Course.id == course_id).scalar_subquery(),
            )
        )


def listed_sets(session: Session, *, person_id: UUID | None) -> list[SetSummary]:
    """Every set in the institution, in name order, each marked editable or not.

    **Institution-wide rather than scoped to the reader** (ADR 0173): §5.1's
    set-definition surface is one list, and a leader who could not see the sets
    another leader defined would define a second set meaning the same thing.

    **Sorted here rather than in the statement.** "Sorted by name" is a contract
    with E5-09's list and with the tests that pin it, and a database sort is done
    in the server's collation — where punctuation and case are weighed in ways
    that differ between deployments and differ again from what a client would do
    with the same list. The key falls back to the id so that two sets which
    somehow share a name still have one order rather than the row order of the
    moment.
    """
    counted = (
        select(func.count())
        .select_from(ComparisonSetMember)
        .where(ComparisonSetMember.set_id == ComparisonSet.id)
        .scalar_subquery()
    )
    rows = session.execute(select(ComparisonSet, counted)).all()
    listed = [
        _summary(found, member_count=member_count, person_id=person_id)
        for found, member_count in rows
    ]
    return sorted(listed, key=lambda entry: (entry.name, str(entry.id)))


def read_set(session: Session, *, set_id: UUID, person_id: UUID | None) -> SetDetail:
    """One set, whoever defined it. The 404 is `SetUnavailableError`."""
    return _detail(session, found=_the_set(session, set_id=set_id), person_id=person_id)


def preview_of(session: Session, *, set_id: UUID) -> SetPreview:
    """How wide a set is: its member courses, and the sections they resolve to.

    **Two counts and nothing else** — no name, no code, no statistic. SPEC §4.1
    item 7 suppresses figures computed over a comparison set below the configured
    minimums; a count of sections says how wide the cohort is and nothing about
    what anybody in it answered, which is why §5.1 allows it at definition time
    and why anything beyond it here would be a figure reaching a reader outside
    E4-07's suppression chokepoint.

    **The section count is E5-04's resolution and not a second one.**
    `resolve_named_set` answers the member courses' sections at the length the set
    declares, across every term retention still keeps; a count computed here
    would be a second answer to what a set reaches, and the first thing two such
    answers do is disagree (`docs/MISTAKES.md` entry 13).
    """
    found = _the_set(session, set_id=set_id)
    member_count = session.scalar(
        select(func.count())
        .select_from(ComparisonSetMember)
        .where(ComparisonSetMember.set_id == found.id)
    )
    return SetPreview(
        member_count=int(member_count or 0),
        section_count=len(resolve_named_set(session, set_id=found.id)),
    )


def create_set(
    session: Session, *, write: SetWrite, person_id: UUID | None, settings: Settings
) -> SetDetail:
    """Define a set, or translate what the database refused about it.

    **The creator comes from the session and never from the body.** It is also
    what every later edit and delete is scoped by, so a set created against a key
    the caller supplied would be a set defined in somebody else's name — and a
    set created against the session's `user` key rather than its `person` key
    would be a set its own definer is refused.
    """
    if person_id is None:
        raise NotTheSetsDefinerError
    stamp = clock.now(session, settings=settings)
    try:
        set_id = session.execute(
            insert(ComparisonSet)
            .values(
                name=write.name,
                length_weeks=write.length_weeks,
                level=write.level,
                created_by_person_id=person_id,
                created_at=stamp,
                updated_at=stamp,
            )
            .returning(ComparisonSet.id)
        ).scalar_one()
        _write_membership(
            session, set_id=set_id, level=write.level, course_ids=write.member_course_ids
        )
        session.commit()
    except (DataError, IntegrityError) as refused:
        session.rollback()
        raise _refusal(refused) from None
    return read_set(session, set_id=set_id, person_id=person_id)


def edit_set(
    session: Session,
    *,
    set_id: UUID,
    write: SetWrite,
    person_id: UUID | None,
    settings: Settings,
) -> SetDetail:
    """Replace a set's whole definition, for the leader who defined it.

    **Membership is deleted before the set row is updated**, and both before the
    new membership is inserted. A membership row holds the set's declared level
    under a composite foreign key, so a set changing level cannot keep children
    naming the old one — and the order is what makes a level change an ordinary
    edit rather than a foreign-key error nobody can act on.

    **A refused edit leaves the set exactly as it was**, because the delete, the
    update and the inserts are one transaction and the rollback takes all three.
    A half-applied edit would be a set resolving to nothing, which is a benchmark
    that quietly stopped comparing anything.
    """
    found = _her_set(session, set_id=set_id, person_id=person_id)
    stamp = clock.now(session, settings=settings)
    try:
        session.execute(
            sql_delete(ComparisonSetMember).where(ComparisonSetMember.set_id == found.id)
        )
        session.execute(
            update(ComparisonSet)
            .where(ComparisonSet.id == found.id)
            .values(
                name=write.name,
                length_weeks=write.length_weeks,
                level=write.level,
                updated_at=stamp,
            )
        )
        _write_membership(
            session, set_id=found.id, level=write.level, course_ids=write.member_course_ids
        )
        session.commit()
    except (DataError, IntegrityError) as refused:
        session.rollback()
        raise _refusal(refused) from None
    return read_set(session, set_id=set_id, person_id=person_id)


def delete_set(session: Session, *, set_id: UUID, person_id: UUID | None) -> None:
    """Delete a set, taking its membership rows and nothing else (ADR 0164).

    The membership rows go with the set because the database cascades them — the
    set is the aggregate root and its memberships are part of it. Every course
    stays exactly where it was: a course named by a set cannot be deleted at all,
    which is the opposite direction and is the `RESTRICT` on the other half of
    the same key.
    """
    found = _her_set(session, set_id=set_id, person_id=person_id)
    session.execute(sql_delete(ComparisonSet).where(ComparisonSet.id == found.id))
    session.commit()


def definition_options(session: Session) -> SetOptions:
    """The closed choices a set is defined out of: SPEC §2.2's lengths, §8's levels, the courses.

    **Both closed sets come from where they are held** — `CALENDAR_LENGTHS` and
    `CourseLevel` — rather than being written out again here. The levels are
    answered in the enum's declaration order, which is SPEC §8's band order, and
    not alphabetically: an order that said nothing about the bands would be an
    order E5-09 has to invent a meaning for.

    **Every course, not only the ones some set already names**, because the form
    is where a new cohort is built. Each is labelled the way the report labels a
    course — the prefix code, the LMS number, an em dash and the LMS title — so a
    definer recognises the same course under the same name on both surfaces. The
    section code and the term the report's own label carries are absent because a
    set names a course rather than a section (ADR 0164).

    Sorted here rather than in the statement, for the collation reason
    `listed_sets` gives.
    """
    rows = session.execute(
        select(Course.id, Course.lms_number, Course.lms_title, Course.level, Prefix.code).join(
            Prefix, Prefix.id == Course.prefix_id
        )
    ).all()
    offered = [
        CourseOption(
            id=course_id,
            label=f"{prefix_code} {lms_number} — {lms_title}",
            level=str(level),
        )
        for course_id, lms_number, lms_title, level, prefix_code in rows
    ]
    return SetOptions(
        lengths=list(CALENDAR_LENGTHS),
        levels=[level.value for level in CourseLevel],
        courses=sorted(offered, key=lambda option: (option.label, str(option.id))),
    )
