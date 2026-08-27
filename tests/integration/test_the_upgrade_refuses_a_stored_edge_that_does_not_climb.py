"""The rank rule arrives on a database that already holds rows — ticket E0-11.

E0-11's first criterion puts the rule that an edge must climb SPEC §2.1's role
ranks inside E0-09's `role_assignment` trigger, and that trigger is
`AFTER INSERT OR UPDATE FOR EACH ROW`: it never examines a row that is already
stored. So every supervision edge written while E0-09's version of the function
was live crosses the new revision unexamined, and a database that was **migrated**
rather than built fresh can hold a `LEAD_FACULTY → LEAD_FACULTY` edge afterwards.
That row is SPEC §4.1 invariant 2 the moment E9 implements the union — "a Lead
Faculty assignment never grants sibling leads' courses, at any point in the
purview union computation" — while §2.1 now states as a property of the system
that "the supervision graph is therefore at most six assignments deep", which a
stored equal-rank edge makes false.

**So `upgrade()` validates what is stored and refuses.** The migration checks for
edges that do not climb and raises rather than completing, naming the offending
rows, which is the disposition for this gap: a rule that holds for every future
write and silently tolerates every past one is a rule about the trigger rather
than about the graph.

**Both revisions are named, and neither end is a step relative to head.**
`alembic downgrade -1` is a position, not a subject: the day another revision
lands on top, it undoes that one instead, and every assertion here would be about
a migration this file is not named for. That cost three red tests one ticket ago
(`docs/disputes/E0-11-02.md`, `docs/MISTAKES.md` entry 3 note 27), and the repair
was to pin the revision by name and resolve it through the script directory so a
squash or a rename fails with a message naming the ticket rather than with
Alembic's own "Can't locate revision", which reads like a broken environment.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so the
downgrade below cannot touch the session database every other integration test
reads — and there is no leftover state from an earlier run for the plant to be
confused by (`docs/MISTAKES.md` entry 12).

**Why the rows are seeded at head and only the edge is written at the old
revision.** The two assignments go in while the database is at **head**, because
that is the only schema `seed_row` can write to: it builds its insert from
`Base.metadata` and its `RETURNING` clause names every column that metadata
declares, so a database standing before any revision that added one is a database
it cannot seed. Head here is not a subject and is not a step — it is the name of
the schema today's models describe, which is what the seeding needs and the only
thing it is used for. Everything this file *asserts* is still pinned to a named
revision, for the reason the paragraph above gives.

The database is then walked back down: to `RANK_REVISION`, where the write that
the plant depends on being illegal is attempted and required to be refused
(`docs/MISTAKES.md` entry 9 — so the plant is known to depend on the older schema
rather than on nothing), and then to `SUPERVISION_REVISION`, where the edge itself
is written, because the edge is the one thing the old version accepts and the new
one does not. It is read back on a fresh connection afterwards, so a plant that
silently did not land cannot make the refusal below arrive for some other reason
(`docs/MISTAKES.md` entry 3).

**This paragraph used to say the opposite, and the correction is the point.** It
read that the rows go in "while the rank rule is installed, which keeps their
columns the ones today's models declare". That was true when E0-11 was head and
stopped being true the first time a later revision added a column to a table this
seeds — E1-10's `course.title_is_fallback`, eight revisions on, which turned both
tests here red inside their own fixture without either ticket being about the
other (`docs/disputes/E1-10-01.md`, `docs/MISTAKES.md` entry 22). The shape that
replaces it is not a fix for that column: seeding happens at head whatever the
models declare, so a revision that adds a column, or ten, cannot reach this file
again. E1-11's roster sync and E1-12's identity link were both already due to add
some.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

pytestmark = pytest.mark.integration

# E0-11's own revision — the one that adds the rank rule, and the subject of every
# assertion in this file. Named rather than reached by a step from head, for the
# reason the module docstring gives.
RANK_REVISION = "9a71c4be0d3f"

# E0-09's revision: the supervision graph and the trigger before the rank rule
# went into it. This is the version that accepted the edge planted below, which is
# what makes the plant a record of what a deployment can be holding rather than a
# row this test invented a way to write.
SUPERVISION_REVISION = "014ccb3d0fe5"

# Where the seeding happens, and **it is not a subject**. Every assertion in this
# file is about one of the two named revisions above; this name appears only in
# the two `upgrade` calls that put the database into the shape `Base.metadata`
# describes, so that `seed_row` can write to it at all. `docs/disputes/E0-11-02.md`
# forbids `head` and a relative step as the *subject* of an assertion, because a
# position moves when a revision lands on top of it — and nothing here asserts
# anything about whatever revision happens to be at head. What it needs is the
# schema today's models declare, and that is what this word means.
MODEL_SCHEMA = "head"


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`,
    marked as one for the reason that module's docstring gives: a test module
    importing a fixtures module by name works only because of where pytest puts
    `tests/` on `sys.path`, and a collection error is not a failing test.
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after "
        "it in this test can mean anything (`docs/MISTAKES.md` entry 3)."
    )
    return holder.get("row")


def survived_the_downgrade(graph: Any, seeded: list[Any], revision: str) -> None:
    """Every seeded assignment is still stored after the walk back down.

    A control on this file's own machinery rather than an assertion about the
    migration, and it exists because the machinery grew a step. The rows are
    written at `MODEL_SCHEMA` and everything after that runs against an older
    schema, so a downgrade that removed them — a data migration, a cascade off a
    dropped constraint — would leave every assertion below true of a database with
    nothing in it, which is `docs/MISTAKES.md` entry 3's shape and is exactly what
    the read-backs further down already guard against for the *edge*.

    A red here is a broken test, not a broken migration: it means the rows this
    file needs cannot survive the route it takes to the revision under test, and
    the route is what changes.
    """
    from sqlalchemy import select

    table = graph.assignments
    key = graph.assignment_key
    wanted = [row[key] for row in seeded]
    found = set(
        graph.session.execute(select(table.c[key]).where(table.c[key].in_(wanted))).scalars()
    )
    missing = [str(one) for one in wanted if one not in found]
    assert not missing, (
        f"After downgrading to {revision}, the assignments {missing} are no longer stored. They "
        f"were seeded at `{MODEL_SCHEMA}` — the only schema `seed_row` can write to, per "
        "`tests/fixtures/supervision.py` — and every step after this one is about a database that "
        "holds them. A downgrade between there and here removes rows rather than only schema, so "
        "this file's route to the revision under test has to change: seed at the oldest revision "
        "whose schema `Base.metadata` still fits, or write the rows through Core statements this "
        "module builds itself."
    )


def require_revision(config: Any, revision: str, ticket: str, what: str) -> str:
    """`revision`, after asking the script directory whether it still exists.

    Resolved rather than handed straight to `command.upgrade`, so that a constant
    left behind by a squash, a rebase or a renamed revision file fails with a
    message naming the ticket instead of with Alembic's own `Can't locate
    revision identified by '...'`. The idiom is
    `tests/integration/test_identity_grants.py`'s, adopted here for the same
    ruling.
    """
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(config).get_revision(revision)
    except Exception as failure:
        pytest.fail(
            f"`{revision}` is not a revision in this tree: {failure!r}. That is {ticket}'s own "
            f"revision — {what} — and this module pins both ends of its work to a named revision "
            "rather than to `head` and a relative step. If it has been renumbered or squashed, "
            "the constant at the top of this file is the one place to change; if the work has "
            "moved to a different revision, point it there and say so in the pull request. Do not "
            "restore `head` and `-1`, which is `docs/disputes/E0-11-02.md`."
        )
    return revision


@contextmanager
def graph_on(database: Any, build: Any) -> Iterator[Any]:
    """E0-09's graph builder on its own connection to `database`, committed and closed.

    Opened and closed around each migration step rather than held across one. An
    Alembic upgrade that alters a trigger or drops a view takes locks a session
    idle inside a transaction can block, and a migration waiting on this test's
    own connection is a hang rather than a failure — the reason
    `test_identity_grants.py` opens its catalog connections the same way.

    Committing is what makes the rows visible to the connection Alembic opens for
    itself; nothing here is rolled back by a fixture, and `empty_database` drops
    the whole database afterwards.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(database.superuser_url)
    try:
        session = Session(bind=engine)
        try:
            yield build(session)
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()


def attempt_upgrade(config: Any, revision: str) -> BaseException | None:
    """Run `alembic upgrade <revision>`; answer the failure it raised, or `None`.

    Answering rather than asserting, because both outcomes are the subject of a
    test here: the upgrade must refuse a database holding an edge that does not
    climb, and must complete over one whose edges all do.
    """
    from alembic import command

    try:
        command.upgrade(config, revision)
    except Exception as failure:
        return failure
    return None


def downgrade_to(config: Any, revision: str, from_revision: str) -> None:
    """Undo back to `revision`, failing the test if the downgrade does not complete.

    A downgrade that stops part-way is worse than one that refuses to start: the
    objects before the failing statement are gone, the ones after it are still
    there, and the revision is still stamped as applied — so the plant that
    follows would be written into a database whose state nobody has described.
    """
    from alembic import command

    try:
        command.downgrade(config, revision)
    except Exception as failure:
        pytest.fail(
            f"`alembic downgrade {revision}` did not complete from {from_revision}: {failure!r}. "
            "Both tests in this file reach the state a deployment is in before the rank rule by "
            "going back to E0-09's revision, because that is the version whose trigger accepted "
            "the edge they are about. A downgrade that fails here leaves the database part-way "
            "between two revisions and nothing after this point means anything."
        )


def failure_text(failure: BaseException) -> str:
    """What `failure` said, and what everything it was raised from said.

    Alembic re-raises the driver's error, and a `DatabaseError` carries its detail
    on the original exception rather than always in `str()` of the wrapper, so the
    whole chain is read.
    """
    parts: list[str] = []
    current: BaseException | None = failure
    while current is not None and len(parts) < 8:
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def version_stamped(database: Any) -> Any:
    """The revision Alembic records as applied, read on a connection of its own."""
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    finally:
        engine.dispose()


def revisions(config: Any) -> tuple[str, str]:
    """Both named revisions, each checked against the script directory first."""
    rank = require_revision(
        config,
        RANK_REVISION,
        "E0-11",
        "the one that adds the rule that a supervision edge climbs SPEC §2.1's role ranks",
    )
    supervision = require_revision(
        config,
        SUPERVISION_REVISION,
        "E0-09",
        "the one that creates `role_assignment` and the trigger the rank rule is added to",
    )
    return rank, supervision


def test_upgrading_over_a_stored_edge_that_does_not_climb_refuses_and_names_the_row(
    empty_database: Any, alembic_config_pointed_at: Any, supervision_graph_on: Any
) -> None:
    """The rule has to answer for rows that were stored before it existed.

    E0-09's trigger fires per row on `INSERT` and `UPDATE`, so the rank rule
    E0-11 adds to it examines exactly the writes that happen after it lands.
    Every edge written before is grandfathered in silently, and the one this test
    plants is `LEAD_FACULTY → LEAD_FACULTY` — the row E0-11's first criterion
    names first, and the row SPEC §4.1 invariant 2 forbids "at any point in the
    purview union computation". Nothing errors, nothing looks wrong, and one
    lead's courses sit inside a sibling's purview from the day E9 walks the graph.

    **What is asserted is that the upgrade refuses**, not that the edge is
    repaired. A migration that deleted the offending rows would leave somebody's
    reporting line quietly gone; a migration that completed would leave the row.
    Refusing is the disposition for this gap, and the operator is the one who
    decides which of the two the data wants — which they can only do if the
    failure names the rows, so that is asserted too.

    **Why the row's key rather than the role name.** A `DatabaseError` renders the
    statement that raised it, and the migration's own SQL spells `LEAD_FACULTY` in
    the rank map, so matching the role name would be satisfied by an anonymous
    failure that merely echoed the statement (`docs/MISTAKES.md` entry 3). A row's
    uuid cannot appear in a migration's text, so it is the one token that can only
    have come from the data.

    **The control is `test_upgrading_over_a_graph_whose_edges_all_climb_completes`**,
    which runs the identical migration step — E0-09's revision up into E0-11's —
    over a database seeded with a legal edge, and requires it to complete. Without
    it, this test passes against a migration that refuses every upgrade
    unconditionally, which is the mutation it exists to survive.

    The two assignments are seeded while the database is at `MODEL_SCHEMA` and the
    database is then walked back down through `RANK_REVISION` to
    `SUPERVISION_REVISION`; the stop at `RANK_REVISION` is where the write the
    plant depends on being illegal is required to be refused. That is machinery
    rather than subject, and the module docstring says why it has to be that way
    round.
    """
    config = alembic_config_pointed_at(empty_database)
    rank, supervision = revisions(config)

    failure = attempt_upgrade(config, MODEL_SCHEMA)
    assert failure is None, (
        f"`alembic upgrade {MODEL_SCHEMA}` did not complete against an empty database: "
        f"{failure!r}. That is the state every other test in the suite runs against, so this is a "
        "defect in a revision rather than anything this test planted — nothing has been written "
        f"yet. Revision {rank}, the subject of this file, is one of the ones it passes through."
    )

    with graph_on(empty_database, supervision_graph_on) as graph:
        key = graph.assignment_key
        parent = written(graph, lambda: graph.node("LEAD_FACULTY"), "A lead-faculty assignment")
        child = written(
            graph, lambda: graph.node("LEAD_FACULTY"), "A second lead-faculty assignment"
        )

    downgrade_to(config, rank, MODEL_SCHEMA)

    with graph_on(empty_database, supervision_graph_on) as graph:
        survived_the_downgrade(graph, [parent, child], rank)
        refused_now = graph.refusal(lambda: graph.repoint(child, parent[key]))
        assert refused_now is not None, (
            f"At revision {rank}, one lead-faculty assignment was pointed at another and the edge "
            "was stored. The plant below depends on that write being illegal *now* and legal at "
            f"revision {supervision}; if it is legal at both, this test proves nothing about a "
            "migration and `test_supervision_edges_run_up_the_role_ranks.py` is where the missing "
            "write-time rule is diagnosed (`docs/MISTAKES.md` entry 9)."
        )

    downgrade_to(config, supervision, rank)

    with graph_on(empty_database, supervision_graph_on) as graph:
        written(
            graph,
            lambda: graph.repoint(child, parent[key]),
            f"Pointing one lead-faculty assignment at another at revision {supervision}, which is "
            "the version that accepted such a row",
        )

    with graph_on(empty_database, supervision_graph_on) as graph:
        stored = graph.parent_of(child[key])
    assert stored == parent[key], (
        f"After the plant, assignment {child[key]} reports to {stored} rather than to "
        f"{parent[key]}. The edge this test exists to migrate over is not in the database, so "
        "whatever the upgrade below does, it is not doing it because of this row "
        "(`docs/MISTAKES.md` entry 3, and the note about checking the mutation landed before "
        "believing it)."
    )

    failure = attempt_upgrade(config, rank)
    assert failure is not None, (
        f"`alembic upgrade {rank}` completed over a database holding a stored "
        "`LEAD_FACULTY → LEAD_FACULTY` edge. E0-09's trigger is `AFTER INSERT OR UPDATE FOR EACH "
        "ROW`, so the rank rule never sees a row that is already there, and every deployment "
        "migrated rather than rebuilt keeps whatever it wrote before. SPEC §2.1 now states as a "
        "property of the system that 'the supervision graph is therefore at most six assignments "
        "deep', and §4.1 invariant 2 forbids the end state outright — one lead's courses inside a "
        "sibling lead's purview, with nothing in the schema and nothing in the resolver standing "
        f"between them. The edge is on assignment {child[key]}, reporting to {parent[key]}."
    )

    said = failure_text(failure)
    assert str(child[key]) in said or str(parent[key]) in said, (
        f"The upgrade refused and its report names neither assignment carrying the edge "
        f"({child[key]} reporting to {parent[key]}). What it said was:\n\n{said}\n\n"
        "The refusal has to name the offending rows, because refusing is the whole of what the "
        "migration does about them: an operator who cannot see which rows to correct cannot get "
        "the database past this revision, and the natural next move — deleting rows until the "
        "migration runs — is the one that silently shrinks somebody's purview. The role name "
        "would be the weaker assertion and is deliberately not the one made here: it is spelled "
        "in the migration's own SQL, which a database error renders, so it would match an "
        "anonymous failure (`docs/MISTAKES.md` entry 3)."
    )
    assert version_stamped(empty_database) != rank, (
        f"The upgrade raised and `alembic_version` still records {rank} as applied, so the "
        "revision was stamped over a database it refused to migrate. The next run finds nothing "
        "left to do and the edge stays, which is worse than either outcome the disposition "
        "allows: the failure has been reported and the database has been marked as though it "
        "had not."
    )


def test_upgrading_over_a_graph_whose_edges_all_climb_completes(
    empty_database: Any, alembic_config_pointed_at: Any, supervision_graph_on: Any
) -> None:
    """The control, and the half a validating migration is easiest to get wrong.

    The same migration step as the test above — down to E0-09's revision and up
    into E0-11's — over a database whose one stored edge is `LEAD_FACULTY → CHAIR`,
    the third link of SPEC §2.1's canonical chain. It has to complete. Without
    this, the test above passes against a migration that refuses every upgrade, and
    the rule "raises rather than completing" would be satisfied by a revision no
    deployment can apply at all.

    The seeding, here as above, happens while the database is at `MODEL_SCHEMA`
    and only then is it walked back down. That is machinery rather than subject and
    the module docstring says why; this test stops at no intermediate revision on
    the way, because it has no write to prove illegal there.

    **Three assertions, because "it completed" has two degenerate readings.** The
    upgrade does not raise; the revision is stamped, so a run that quietly did
    nothing is not read as success; and the legal edge is still there afterwards,
    because a migration that made itself pass by clearing `reports_to` would
    satisfy the other two and shrink every purview under it — §2.1 unions the
    purviews of everything transitively reporting to an assignment, so a dropped
    edge is a branch that stops existing with nothing to report it.

    The edge is asserted stored *before* the upgrade under test, for the same
    reason the plant is asserted in the test above: over a database with no edges
    in it, "the upgrade completed" says nothing about a migration that examines
    edges.
    """
    config = alembic_config_pointed_at(empty_database)
    rank, supervision = revisions(config)

    failure = attempt_upgrade(config, MODEL_SCHEMA)
    assert failure is None, (
        f"`alembic upgrade {MODEL_SCHEMA}` did not complete against an empty database: "
        f"{failure!r}. Nothing has been seeded at this point, so this is a revision failing on its "
        f"own, and {rank} — the subject of this file — is one of the ones it passes through."
    )

    with graph_on(empty_database, supervision_graph_on) as graph:
        key = graph.assignment_key
        chair = written(graph, lambda: graph.node("CHAIR"), "A chair assignment")
        lead = written(
            graph,
            lambda: graph.node("LEAD_FACULTY", reports_to=chair[key]),
            "A lead-faculty assignment reporting to that chair",
        )

    downgrade_to(config, supervision, MODEL_SCHEMA)

    with graph_on(empty_database, supervision_graph_on) as graph:
        survived_the_downgrade(graph, [chair, lead], supervision)
        stored = graph.parent_of(lead[key])
    assert stored == chair[key], (
        f"Before the upgrade under test, the lead reports to {stored} rather than to the chair "
        f"{chair[key]}. This database is then a database with no reporting line in it, and 'the "
        "upgrade completed' is true of one that refuses every graph containing an edge "
        "(`docs/MISTAKES.md` entry 3)."
    )

    failure = attempt_upgrade(config, rank)
    assert failure is None, (
        f"`alembic upgrade {rank}` refused a database whose only supervision edge is "
        f"`LEAD_FACULTY → CHAIR`: {failure!r}. That is the third link of SPEC §2.1's canonical "
        "chain — `INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) "
        "→ VP_ACADEMICS` — so it is the ordinary case rather than an edge case, and a validating "
        "upgrade that will not run over it cannot be deployed at all. "
        "`test_upgrading_over_a_stored_edge_that_does_not_climb_refuses_and_names_the_row` is the "
        "half this one is the control for."
    )
    assert version_stamped(empty_database) == rank, (
        f"`alembic upgrade {rank}` raised nothing and `alembic_version` records "
        f"{version_stamped(empty_database)!r}. The upgrade did not run, so 'it completed' is true "
        "of a command that did nothing, and the assertion above is satisfied by a migration that "
        "cannot be reached."
    )

    with graph_on(empty_database, supervision_graph_on) as graph:
        after = graph.parent_of(lead[key])
    assert after == chair[key], (
        f"After the upgrade, the lead reports to {after} rather than to the chair {chair[key]}. "
        "The edge climbs, so there was nothing here to correct, and a migration that repairs data "
        "instead of refusing it takes the legal edges with the illegal ones — silently, in a "
        "step an operator reads as a schema change. SPEC §2.1 computes purview by walking exactly "
        "these edges, so a cleared `reports_to` is a branch missing from somebody's view with "
        "nothing on the screen to say so."
    )
