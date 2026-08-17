"""`reportsTo` connects assignments, and the graph refuses a cycle — ticket E0-09.

Every acceptance criterion except the two that are asserted elsewhere: model
registration is `tests/unit/test_role_assignment_models_registered.py`, and the
Care-from-a-claim escalation is
`tests/unit/test_care_is_not_reachable_from_a_claim.py`, which is a sweep of the
source tree rather than a question for a database. The Hypothesis properties over
generated graphs are in `tests/integration/test_supervision_graph_properties.py`.

**Why so much of this is about what is refused.** SPEC §2.1 computes purview from
this graph, so every row here is a grant of access to somebody's data. The ticket
says it plainly — "getting the edge endpoints wrong here would quietly break
purview for the whole product" — and the failures are all of the quiet kind: an
edge pointing at a person instead of an assignment produces correct answers until
somebody holds two hats; a cycle guard that looks one level up produces correct
answers until an admin builds a three-step loop; a lead scoped to a department
produces a *larger* purview, which no user complains about.

**Every refusal has a control written first, through `written` below.** A
`pytest.raises` cannot tell the rule under test from a rule that refuses the same
row for its own reasons, or from an insert path that does not work at all
(`docs/MISTAKES.md` entry 3). So the row before the one that must be refused goes
in through the same helper, in the same transaction, and a failure there stops the
test naming the write rather than the assertion that could not run.

**The builder is in `tests/conftest.py`**, not here, because the property module
asks it the same questions and E0-09's definition of done asks for a fixture
builder E9 will reuse (`docs/MISTAKES.md` entry 13). What it decides, and the one
thing it refuses to decide — what a `scope_node_id` points at, given that E0-05
built the containment hierarchy as six separate tables — is written on
`SupervisionGraph`.

**Every write in this module happens inside one uncommitted transaction.** That
is not incidental: the ticket's security review asks "whether cycle rejection can
be bypassed by writing rows in a particular order or inside a single
transaction", and a single transaction is the only way these tests write
anything. `SupervisionGraph.refusal` issues `SET CONSTRAINTS ALL IMMEDIATE`
before deciding a write was accepted, so a guard written as a deferred constraint
trigger answers at the same moment an immediate one does, and this suite does not
quietly pick between the two designs.

**Two small helpers are copied here rather than imported from `tests/
conftest.py`.** A test module importing the conftest module by name works only
because of where pytest puts `tests/` on `sys.path`, and a collection error is
not a failing test — `test_identity_schema.py` copies its constants for the same
reason. The copies are marked where they sit.

**One of those copies is `IDENTITY_NAME_FRAGMENTS`, and it is one of three in
`tests/`** — here, `test_identity_column_marker.py` (where the convention is
defined and its blind spots are written down) and `test_identity_schema.py`. E0-10
widened all three together; dispute E0-10-01 found the comment in the first of
them claiming there were two, which is how a fourth copy gets missed. Change one,
change all three.
"""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Boolean, inspect, text
from sqlalchemy.types import TypeDecorator

pytestmark = pytest.mark.integration

ASSIGNMENTS = "role_assignment"
MAPPINGS = "lead_faculty_mapping"

# Fragments a rejection message may carry to count as "a clear error"
# (criterion 2). Deliberately broad — this is not a test of anybody's prose — but
# not so broad that a unique-violation or a foreign-key error would match: the
# difference between "you have built a loop" and "duplicate key value violates
# unique constraint" is the difference between an admin fixing their data and an
# admin filing a bug.
#
# `reports_to` is deliberately **not** in this list, though it is the obvious
# word to look for. SQLAlchemy's `str(DatabaseError)` appends the statement it
# was running, and that statement is an `UPDATE role_assignment SET reports_to =
# …` — so the fragment would match every refusal of any kind, and this assertion
# would pass against a message that said nothing at all (`docs/MISTAKES.md` entry
# 3). The test reads `.orig`, the server's own message, for the same reason.
CYCLE_ERROR_FRAGMENTS = (
    "cycle",
    "circular",
    "loop",
    "ancestor",
    "self-reference",
    "supervis",
    "reporting",
)

# **This file's choice**, in the sense that no ticket spells them: the two entry
# doors of SPEC §2.1's table, and the words a schema might use for each. A door
# is read by looking for these fragments in whatever the assignment records, so
# `LTI_LAUNCH`, `launch` and `permits_launch` all answer the same.
LAUNCH_DOOR = "launch"
WEB_DOOR = "web login"
LAUNCH_FRAGMENTS = ("launch", "lti")
WEB_FRAGMENTS = ("web", "login", "oidc")
DOOR_COLUMN_FRAGMENTS = ("door", "entry", "launch", "login", "web", "lti")

# SPEC §2.1's table, which the ticket restates as "launch for every reporting
# role, web login for every role except instructor and student". `STUDENT` is
# absent because no ticket says a student holds a `role_assignment` row at all,
# and inventing one here would decide that.
DOORS_BY_ROLE = {
    "INSTRUCTOR": {LAUNCH_DOOR},
    "LEAD_FACULTY": {LAUNCH_DOOR, WEB_DOOR},
    "CHAIR": {LAUNCH_DOOR, WEB_DOOR},
    "ASSISTANT_DEAN": {LAUNCH_DOOR, WEB_DOOR},
    "DEAN": {LAUNCH_DOOR, WEB_DOOR},
    "VP_ACADEMICS": {LAUNCH_DOOR, WEB_DOOR},
    "CARE": {WEB_DOOR},
    "ADMIN": {WEB_DOOR},
}

# How a column name is recognised as holding a person, and the marker that has to
# be on one. All three are copies of the constants in
# `tests/integration/test_identity_column_marker.py`, deliberately — see the
# module docstring. **There are three copies of the fragment tuple in `tests/`**:
# there, here, and in `test_identity_schema.py`. Change one, change all three.
#
# **Widened by E0-10**, whose fourth criterion is that an identity column named
# neither "name" nor "email" is still caught. `login_id` and never a bare
# `login`, which is measured rather than chosen: `login` matches
# `role_assignment.permits_web_login` on the very table this file sweeps — a
# boolean about which doors a role opens (ADR 0026), carrying no identity — and
# would turn the sweep below red over it. Dispute E0-10-01 ran both.
IDENTITY_NAME_FRAGMENTS = (
    "name",
    "email",
    "login_id",
    "picture",
    "sourcedid",
    "phone",
    "sortable",
    "given",
    "family",
    "surname",
    "address",
    "photo",
    "avatar",
    "username",
)
MARKER_TOKEN = "identity"  # noqa: S105 — the marker convention's token, not a credential
MARKER_PREFIXES = ("identity_", "pii_")

# Column-name fragments that read as provenance — who wrote the row — rather than
# as the person the row is about. **This file's choice**: no ticket says an
# assignment carries one, and the point of the list is that a `created_by` link
# is not a second answer to "whose assignment is this".
PROVENANCE_FRAGMENTS = ("created", "updated", "modified", "_by", "actor", "author", "revoked")


def stored_type(column: Any) -> Any:
    """The type a column stores, with any `TypeDecorator` resolved away. A copy; see the docstring."""
    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    return kind


def foreign_key_columns(table: Any, target: str) -> list[str]:
    """Every column on `table` whose foreign key points at `target`. A copy; see the docstring."""
    return sorted(
        {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
    )


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    Every "and then this is refused" assertion in this module is preceded by rows
    that have to go in first. Writing them bare would end the test in a
    `DatabaseError` from inside the setup — a broken test rather than a red one,
    reported as though the assertion had run. This makes such a failure say which
    write it was and why the rest could not mean anything.
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after "
        "it in this test can mean anything, because a refusal that arrives before the row under "
        "test makes every later assertion pass for the wrong reason (`docs/MISTAKES.md` entry 3)."
    )
    return holder.get("row")


# ---------------------------------------------------------------------------
# Criterion 1 — `reports_to` points at an assignment.
# ---------------------------------------------------------------------------


def test_reports_to_is_a_foreign_key_to_another_role_assignment(
    migrated_engine: Any, supervision_graph: Any
) -> None:
    """Criterion 1: the edge's target table is `role_assignment`, in Postgres and in the model.

    **Read out of the database catalog as well as out of the model**, because the
    criterion is about what a migration is allowed to do: "a migration attempting
    to point it at `person` or an org table would fail review, and the model makes
    that impossible to do accidentally". A model-only assertion cannot see a
    migration that created the column differently, and the model half is what
    makes the mistake hard to make in the first place.

    **This is the criterion the whole ticket rests on.** An edge pointing at a
    person is not a smaller mistake: it is the same graph until somebody holds two
    assignments, at which point one person has one parent and SPEC §2.1's two-hat
    case — "a chair's lead-faculty assignment may report to their own chair
    assignment" — becomes unrepresentable. Nothing detects that; the purview it
    computes is simply wrong, and it looks like an answer.
    """
    column = supervision_graph.reports_to_column
    inspector = inspect(migrated_engine)
    assert ASSIGNMENTS in inspector.get_table_names(), (
        f"`Base.metadata` declares `{ASSIGNMENTS}` and the migrated database does not hold it, so "
        "the model and the migration disagree. `tests/unit/test_role_assignment_models_registered"
        ".py` and `alembic check` are where that is diagnosed; this test needs the table before "
        "it can read a key off it."
    )
    declared_keys = inspector.get_foreign_keys(ASSIGNMENTS)

    keys = [key for key in declared_keys if column in (key.get("constrained_columns") or [])]
    assert keys, (
        f"`{ASSIGNMENTS}.{column}` carries no foreign key in the migrated database. The keys the "
        f"table has: {declared_keys}. E0-09 criterion 1: '`reports_to` is a foreign key to "
        "`role_assignment`… Enforce the foreign key target at the database level.' Without one, "
        "the column is a uuid that any id at all fits, and the first thing to fit will be a "
        "`person.id` — which is the shape SPEC §2.1 rules out in bold: edges connect 'role "
        "assignments, not people or org nodes'."
    )

    targets = sorted({key.get("referred_table") for key in keys})
    assert targets == [ASSIGNMENTS], (
        f"`{ASSIGNMENTS}.{column}` references {targets}. It has to reference `{ASSIGNMENTS}` "
        "itself. SPEC §2.1: 'reportsTo edges connect **role assignments, not people or org "
        "nodes**' — an edge to `person` cannot express a two-hat person supervised differently "
        "under each hat, and an edge to an org node makes the supervision graph a second copy of "
        "the containment hierarchy, which is the thing §2.1 opens by saying it is not."
    )

    in_model = sorted(
        {key.column.table.name for key in supervision_graph.assignments.c[column].foreign_keys}
    )
    assert in_model == [ASSIGNMENTS], (
        f"In `Base.metadata`, `{ASSIGNMENTS}.{column}` references {in_model} rather than "
        f"`{ASSIGNMENTS}`. The database and the model have to agree, because the model is what "
        "makes the mistake hard to make: an autogenerated migration takes the target from here."
    )


def test_reports_to_refuses_the_id_of_a_person(supervision_graph: Any) -> None:
    """Criterion 1, as behaviour: a `person.id` in the edge column is refused.

    The catalog test above says the key is declared; this one says it is enforced,
    and the two fail for different reasons — a key created `NOT VALID`, or a
    column left holding a uuid after a later migration dropped its key, shows up
    only here.

    **The control is not ceremony.** A `person` id and a `role_assignment` id are
    both uuids, so a refusal proves nothing until an assignment id has been
    accepted through the same column, by the same helper, in the same transaction.
    If the *control* is what gets refused, `written` says so — and that is the
    diagnosis for an edge pointing at `person`, which is the wrong design this
    criterion exists to stop.
    """
    graph = supervision_graph
    key = graph.assignment_key

    parent = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=parent[key]),
        "An assignment reporting to another assignment",
    )

    person = graph.person()
    refused = graph.refusal(lambda: graph.assign("LEAD_FACULTY", reports_to=person))
    assert refused is not None, (
        f"An assignment was written whose `{graph.reports_to_column}` holds a `person.id`. E0-09: "
        "'a schema where it could point at a person or an org node is a defect'. The two ids are "
        "both uuids, so nothing downstream will ever notice: the purview walk finds no parent and "
        "returns a smaller answer than it should — or, once ids collide by luck, a larger one."
    )


def test_an_assignment_belongs_to_a_person_and_not_to_a_user(supervision_graph: Any) -> None:
    """Scope: an assignment carries `person_id`. Asserted because nothing else would.

    Not one of the twelve criteria, and load-bearing for all of them
    (`docs/MISTAKES.md` entry 2). SPEC §2.1 splits the LMS-owned side from the
    Pulse-owned people graph and computes purview from the second: "the LMS has no
    equivalent". An assignment keyed to `user` instead would mean a dean who has
    never launched the tool cannot be given a purview — the case
    [ADR 0024](../../docs/adr/0024-the-person-to-user-link-is-carried-by-person.md)
    makes the person-to-user link nullable for, since the admin console builds
    this graph top-down before anybody launches anything.

    A link to `user` *as well* is refused here rather than tolerated: two ways to
    say who holds an assignment is two answers that can disagree, and which one a
    purview walk reads is then a matter of which query somebody wrote. A column
    that reads as provenance rather than as the holder — `created_by_user_id` and
    the like — is exempted, since that is a different fact about the row and the
    audit log (§8) is entitled to it.
    """
    graph = supervision_graph
    to_person = graph.person_column  # fails, saying so, when there is none
    to_user = [
        name
        for name in foreign_key_columns(graph.assignments, "user")
        if not any(fragment in name.lower() for fragment in PROVENANCE_FRAGMENTS)
    ]

    assert not to_user, (
        f"`{ASSIGNMENTS}` references `user` from {to_user} as well as `person` from "
        f"`{to_person}`. SPEC §2.1 keeps the two sides apart and computes purview from the "
        "Pulse-owned people graph; ADR 0024 puts the one link between them on `person.user_id`, "
        "nullable, so that a dean who has never launched the tool still supervises chairs. A "
        "second link here is a second answer to 'who holds this assignment', and the two can "
        "disagree — silently, because each is individually plausible."
    )


# ---------------------------------------------------------------------------
# Criteria 2 and 3 — cycles, at four depths, plus the chain that must be legal.
# ---------------------------------------------------------------------------


def test_an_assignment_that_reports_to_itself_is_refused(supervision_graph: Any) -> None:
    """Depth 1, written as a single INSERT rather than as an update.

    **The insert is the point.** Postgres checks a row's foreign keys after the
    row exists, so `INSERT … (id, reports_to) VALUES (x, x)` is a legal
    self-reference needing no second statement — which means a guard written only
    as a `BEFORE UPDATE` trigger, or only in a service that edits an existing
    assignment, lets the shortest cycle in the schema through the front door. The
    id is supplied explicitly for that reason; ADR 0016 gives the column a server
    default, and a default is a default rather than a prohibition.

    The control is an ordinary assignment written through the same helper, so that
    a refusal below is known to be about the row pointing at itself rather than
    about the table refusing an explicit primary key.
    """
    graph = supervision_graph
    identifier = uuid4()

    written(
        graph,
        lambda: graph.assign("CHAIR", **{graph.assignment_key: uuid4()}),
        "An assignment inserted with an explicit primary key and no parent",
    )

    refused = graph.refusal(
        lambda: graph.assign("CHAIR", reports_to=identifier, **{graph.assignment_key: identifier})
    )
    assert refused is not None, (
        "An assignment was inserted reporting to itself, in one statement. E0-09: 'Reject "
        "assignment-level cycles at write time.' A purview walk over this row does not return a "
        "wrong answer — it does not return: every implementation of 'union the purviews of "
        "everything reporting to me' recurses until something stops it."
    )


def test_a_two_assignment_cycle_is_refused(supervision_graph: Any) -> None:
    """Criterion 2: A reports to B, B is then pointed at A, and that is rejected clearly.

    The chain is built first and has to be accepted — a guard that refused the
    *first* edge would satisfy a bare `pytest.raises` here while breaking every
    supervision line in the product.

    **"With a clear error" is asserted too**, loosely, because the criterion says
    it and because of what the failure looks like from the other end. This write
    is an admin re-pointing somebody's reporting line in the People editor (§6.3);
    "duplicate key value violates unique constraint" tells them to try a different
    name, and "you have created a reporting loop" tells them what they did.
    """
    graph = supervision_graph
    key = graph.assignment_key

    top = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    below = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=top[key]),
        "A lead-faculty assignment reporting to that chair",
    )

    refused = graph.refusal(lambda: graph.repoint(top, below[key]))
    assert refused is not None, (
        "Two assignments were stored reporting to each other. E0-09 criterion 2: 'Creating a "
        "two-assignment cycle is rejected at write time with a clear error.' Neither row is wrong "
        "on its own, which is why nothing downstream can detect this: SPEC §2.1's purview is "
        "defined as a transitive union, and over a loop that union has no fixed point."
    )

    # `.orig` is the server's own message, without the statement SQLAlchemy
    # appends — see the note on `CYCLE_ERROR_FRAGMENTS` above.
    from_the_server = str(getattr(refused, "orig", refused))
    assert any(fragment in from_the_server.lower() for fragment in CYCLE_ERROR_FRAGMENTS), (
        f"The cycle was refused, and Postgres said {from_the_server!r}. None of "
        f"{list(CYCLE_ERROR_FRAGMENTS)} appears in it, so this is either a message an admin "
        "cannot act on or a refusal that came from some other rule entirely — and the second "
        "would mean the cycle tests below are green for a reason that has nothing to do with "
        "cycles. Naming the constraint or the trigger after what it refuses is enough."
    )


def test_a_three_assignment_cycle_is_refused(supervision_graph: Any) -> None:
    """Criterion 3: the transitive case. A → B → C → A is rejected.

    This is the one that separates a real ancestor walk from the guard almost
    everybody writes first — `CHECK (reports_to <> id)`, or a trigger comparing
    the new parent against the row being written. Both pass the two tests above
    and both let this through, and a three-step loop is not exotic: it is what an
    admin produces by re-pointing a chair at an assistant dean who already reports
    to that chair's dean.
    """
    graph = supervision_graph
    key = graph.assignment_key

    top = written(graph, lambda: graph.assign("DEAN"), "A dean assignment")
    middle = written(
        graph,
        lambda: graph.assign("CHAIR", reports_to=top[key]),
        "A chair reporting to that dean",
    )
    bottom = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=middle[key]),
        "A lead reporting to that chair",
    )

    refused = graph.refusal(lambda: graph.repoint(top, bottom[key]))
    assert refused is not None, (
        "A three-assignment cycle was stored. E0-09 criterion 3: 'Creating a three-assignment "
        "cycle is also rejected — test the transitive case, not just the direct one.' A guard "
        "that compares the new parent against the row itself accepts this, and passes every "
        "shorter test in this module."
    )


def test_a_six_assignment_cycle_is_refused(supervision_graph: Any) -> None:
    """Longer than the criteria ask for, because a guard can be right at two and wrong at six.

    A depth-limited walk — three levels, five, whatever fits the reporting lines
    somebody had in mind — passes both criteria and fails here. SPEC §2.1's
    canonical chain is already five roles deep before any insertion, and the
    ticket exists to make insertions possible "without schema change", so a guard
    whose depth is a guess about org shape is a guard with a shelf life.

    The chain is read back before the loop is closed, because a schema that
    dropped some of these edges would leave this closing a shorter cycle than the
    one the test is named for.
    """
    graph = supervision_graph
    key = graph.assignment_key

    chain = [written(graph, lambda: graph.node("CHAIR"), "The root of a six-assignment chain")]
    for depth in range(5):
        parent = chain[-1][key]
        chain.append(
            written(
                graph,
                lambda parent=parent: graph.node("CHAIR", reports_to=parent),
                f"Link {depth + 2} of a six-assignment chain",
            )
        )

    assert len(graph.ancestors(chain[-1][key])) == 5, (
        f"The six-assignment chain stored {len(graph.ancestors(chain[-1][key]))} ancestors above "
        "its leaf rather than five, so the write below would be closing something other than a "
        "six-node cycle."
    )

    refused = graph.refusal(lambda: graph.repoint(chain[0], chain[-1][key]))
    assert refused is not None, (
        "A six-assignment cycle was stored. Criteria 2 and 3 name depths two and three; a guard "
        "that walks a fixed number of levels satisfies both and fails here, and the number it "
        "walks is somebody's estimate of how deep a college can nest."
    )


def test_the_canonical_supervision_chain_is_accepted(supervision_graph: Any) -> None:
    """The control for every cycle test above: SPEC §2.1's own chain must insert.

    `INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college)
    → VP_ACADEMICS`, with an assistant dean inserted between chair and dean, which
    §2.1 gives as the example of an insertion the schema takes without changing.

    Without this, the cheapest way to pass everything above is a guard that
    refuses any edge at all, or any chain deeper than two — and a schema that
    refused the reporting lines the product is built on would fail no other test
    in this module. The edges are read back at the end for the same reason the
    forest property reads them back: an edge silently dropped looks identical to
    an edge accepted.
    """
    graph = supervision_graph
    key = graph.assignment_key
    order = ("VP_ACADEMICS", "DEAN", "ASSISTANT_DEAN", "CHAIR", "LEAD_FACULTY", "INSTRUCTOR")

    parent: Any = None
    for role in order:
        row = written(
            graph,
            lambda role=role, parent=parent: graph.node(role, reports_to=parent),
            f"The {role} link of SPEC §2.1's canonical supervision chain",
        )
        parent = row[key]

    assert len(graph.ancestors(parent)) == len(order) - 1, (
        f"The canonical chain stored {len(graph.ancestors(parent))} ancestors above the instructor "
        f"rather than {len(order) - 1}. Every edge was accepted, so the ones that did not survive "
        "were dropped rather than refused — and a purview union walks exactly this path."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — a person with two hats.
# ---------------------------------------------------------------------------


def test_a_person_may_hold_two_assignments_where_one_reports_to_the_other(
    supervision_graph: Any,
) -> None:
    """Criterion 4: the person-level cycle SPEC §2.1 calls legal and expected.

    "A chair's lead-faculty assignment reporting to their own chair assignment
    must be accepted." This is the test that catches a cycle guard written over
    `person_id` rather than over the assignment id — a natural thing to write if
    you think of the graph as being about people, which passes every cycle test in
    this module and makes the commonest two-hat arrangement in the institution
    unwritable.

    The two rows are then read back as two, because "accepted" has a degenerate
    reading: a schema that merged them, or kept only one, would satisfy the write
    and lose the distinction the ticket is about.
    """
    graph = supervision_graph
    key = graph.assignment_key
    chair_of = graph.person()

    chair = written(
        graph, lambda: graph.assign("CHAIR", person=chair_of), "A chair assignment for one person"
    )
    lead = graph.refusal(
        lambda: graph.assign("LEAD_FACULTY", person=chair_of, reports_to=chair[key])
    )
    assert lead is None, (
        f"A chair's own lead-faculty assignment, reporting to their own chair assignment, was "
        f"refused: {lead}. SPEC §2.1: 'a chair's lead-faculty assignment may report to their own "
        "chair assignment — legal and expected', and 'assignment-level cycles are invalid, "
        "person-level cycles are fine'. A guard that walks `person_id` instead of the assignment "
        "id reads this as a one-step loop; every cycle test in this module stays green when it "
        "does."
    )

    held = graph.assignments_of(chair_of)
    assert len(held) == 2, (
        f"That person holds {len(held)} assignments rather than two. Both writes were accepted, so "
        "one of the rows was merged into the other or replaced it — and the two hats the ticket "
        "is about are the two rows."
    )


def test_one_persons_two_hats_are_supervised_independently(supervision_graph: Any) -> None:
    """Criterion 4's other half: two hats, two parents, and they stay apart.

    The same person leads a course and teaches a section, and the two assignments
    answer to different supervisors — the lead assignment to a chair, the
    instructor assignment to a different lead. This is what an edge between
    *people* cannot hold: one person, one parent, and one of the two reporting
    lines silently lost.

    Asserted by reading the stored edges back rather than by trusting the writes,
    because the failure being described is a schema that accepts both statements
    and keeps one of them.
    """
    graph = supervision_graph
    key = graph.assignment_key
    two_hatted = graph.person()

    chair = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    other_lead = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=graph.fresh_scope("course")),
        "Another person's lead-faculty assignment",
    )

    wearing_lead = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", person=two_hatted, reports_to=chair[key]),
        "The two-hatted person's lead-faculty assignment",
    )
    wearing_instructor = written(
        graph,
        lambda: graph.assign("INSTRUCTOR", person=two_hatted, reports_to=other_lead[key]),
        "The two-hatted person's teaching assignment",
    )

    assert wearing_lead[key] != wearing_instructor[key], (
        "One person's two assignments came back as one row, so there are not two hats to "
        "supervise differently."
    )
    assert graph.parent_of(wearing_lead[key]) == chair[key], (
        "The lead-faculty hat does not report to the chair it was given. SPEC §2.1 attaches the "
        "edge to the assignment, so each hat carries its own supervisor; a schema that attaches "
        "it to the person has one slot, and the second write wins."
    )
    assert graph.parent_of(wearing_instructor[key]) == other_lead[key], (
        "The teaching hat does not report to the lead faculty it was given, although the other "
        "hat's edge survived. That is one reporting line per person, which is the shape SPEC §2.1 "
        "rules out — and the purview it produces is wrong in the direction nobody reports: "
        "somebody sees a section they do not supervise, or stops seeing one they do."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — one lead per course.
# ---------------------------------------------------------------------------


def test_a_second_lead_faculty_mapping_for_one_course_is_refused(supervision_graph: Any) -> None:
    """Criterion 5: a course that already has a lead cannot acquire a second.

    **Two controls, because a refusal here has two innocent explanations.** The
    first mapping proves the insert path works. A second mapping, for a *different
    person* on a *different course*, proves the rule is not "one mapping in this
    table" — which would satisfy a bare `pytest.raises` while permitting exactly
    the row the criterion forbids.

    The rule is what makes SPEC §4.1 item 2 meaningful: "a Lead Faculty's grant is
    only the courses they lead". Two leads on one course means that sentence has
    two answers, and a lead sees a peer's course through a mapping they did not
    know existed.
    """
    graph = supervision_graph
    course = graph.scope("course")
    first_lead = graph.person()
    second_lead = graph.person()

    written(
        graph,
        lambda: graph.lead_mapping(person=first_lead, course=course),
        "The first lead-faculty mapping",
    )
    written(
        graph,
        lambda: graph.lead_mapping(person=second_lead, course=graph.fresh_scope("course")),
        "A second person leading a second course",
    )

    refused = graph.refusal(lambda: graph.lead_mapping(person=second_lead, course=course))
    assert refused is not None, (
        "One course was given two lead-faculty mappings. E0-09 criterion 5: 'A second "
        "lead-faculty mapping for an already-mapped course is rejected', and the scope says 'one "
        "lead per course, enforced by constraint'. SPEC §2.1 makes a lead's grant exactly their "
        "led courses, so a second mapping hands a second person the first one's purview — and "
        "§4.1 item 2 says a lead never sees a sibling lead's course, which is the invariant this "
        "row breaks."
    )


def test_one_person_may_lead_more_than_one_course(supervision_graph: Any) -> None:
    """Criterion 5's near miss: the rule is one lead per course, not one course per lead.

    SPEC §2.1 says it twice — "people and courses are not 1:1", and "a lead's
    practical span may cross prefixes and departments". A uniqueness rule written
    over the person satisfies the test above and fails here; one written over the
    person and the course together satisfies it *and* permits two leads on one
    course, which is why both directions are asserted.
    """
    graph = supervision_graph
    lead = graph.person()

    written(
        graph,
        lambda: graph.lead_mapping(person=lead, course=graph.scope("course")),
        "A person's first led course",
    )

    refused = graph.refusal(
        lambda: graph.lead_mapping(person=lead, course=graph.fresh_scope("course"))
    )
    assert refused is None, (
        f"One person was refused a second led course: {refused}. SPEC §2.1: 'people and courses "
        "are not 1:1', and 'a lead's practical span may cross prefixes and departments'. A "
        "uniqueness rule over the person makes the ordinary case — a lead with four courses — "
        "unwritable, and E9's CSV import would refuse most of a real institution's file."
    )


# ---------------------------------------------------------------------------
# Criterion 6 — the role and the kind of node it is scoped to must agree.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "wrong_kind"),
    [
        ("INSTRUCTOR", "course"),
        ("INSTRUCTOR", "department"),
        ("CHAIR", "prefix"),
        ("CHAIR", "college"),
        ("ASSISTANT_DEAN", "department"),
        ("DEAN", "department"),
        ("DEAN", "institution"),
        ("VP_ACADEMICS", "college"),
        ("ADMIN", "college"),
    ],
)
def test_an_assignment_whose_role_and_scope_kind_disagree_is_refused(
    supervision_graph: Any, role: str, wrong_kind: str
) -> None:
    """Criterion 6, one wrong pairing per case. The right pairing goes in first.

    E0-09's scope: "an assignment's `scope_node_id` must reference a node of the
    right kind for its role… Enforce it rather than trusting callers." Every one
    of these rows widens or narrows somebody's purview without being wrong on its
    face — a dean scoped to the institution is a plausible-looking row that hands
    one college's dean every college in the university, and nothing downstream can
    tell it from a VP.

    Lead faculty and Care are deliberately absent from this list; they have
    criteria of their own below, and asserting them twice would give two failures
    for one defect.

    A schema that cannot *spell* the wrong pairing — no column for that
    containment level at all — passes, and the assertion says so rather than
    leaving the case untested: unrepresentable is the strongest form of the rule
    rather than a hole in it.
    """
    graph = supervision_graph

    written(graph, lambda: graph.assign(role), f"A {role} assignment at its own grain")

    unrepresentable = not graph.can_express(wrong_kind)
    refused = (
        None
        if unrepresentable
        else graph.refusal(lambda: graph.assign(role, scope_kind=wrong_kind))
    )
    assert unrepresentable or refused is not None, (
        f"A {role} assignment was stored scoped to a {wrong_kind}. E0-09: 'Role grain constraint: "
        "an assignment's `scope_node_id` must reference a node of the right kind for its role… "
        "Enforce it rather than trusting callers.' SPEC §2.1 computes the own grant from the "
        f"role's grain, so a {role} on a {wrong_kind} node produces a purview nobody granted, and "
        "it produces it quietly — the row reads as ordinary, and the only symptom is somebody "
        "seeing more than they should."
    )


@pytest.mark.invariant
@pytest.mark.parametrize("wrong_kind", ["prefix", "department", "college", "institution"])
def test_a_lead_faculty_assignment_scoped_above_its_course_is_refused(
    supervision_graph: Any, wrong_kind: str
) -> None:
    """SPEC §4.1 item 2, at the grain this ticket owns: a lead is scoped to a course.

    §4.1: "A Lead Faculty assignment never grants sibling leads' courses, at any
    point in the purview union computation." E0-11 asserts that over the purview
    resolver; this asserts the schema fact the resolver has no way to recover
    from. A lead-faculty assignment scoped to a prefix or a department *is* a
    grant over every sibling lead's courses, however carefully the union is later
    written, because §2.1 defines the own grant as the scope restricted by role
    grain and there is nothing left to restrict.

    **Marked `invariant` and therefore unskippable**, which is the point of the
    marker: this is the row that turns a confidentiality rule into a data-entry
    accident. It is invisible to the person it happens to — a lead who suddenly
    sees more courses has no way to know they should not.
    """
    graph = supervision_graph

    written(
        graph, lambda: graph.assign("LEAD_FACULTY"), "A lead-faculty assignment scoped to a course"
    )

    unrepresentable = not graph.can_express(wrong_kind)
    refused = (
        None
        if unrepresentable
        else graph.refusal(lambda: graph.assign("LEAD_FACULTY", scope_kind=wrong_kind))
    )
    assert unrepresentable or refused is not None, (
        f"A lead-faculty assignment was stored scoped to a {wrong_kind}. SPEC §2.1: a lead's "
        "scope attachment is a **course**, and their grant is 'only the courses they lead (never "
        f"sibling leads' courses, at any point in the union)'. A lead scoped to a {wrong_kind} "
        "holds every course under it, including every other lead's — which is §4.1 item 2 broken "
        "in the schema, before any query is written, and no purview computation can undo it."
    )


# ---------------------------------------------------------------------------
# Criterion 6, the half a wrong *pairing* does not reach: an assignment names
# exactly one node, and the rule that pairs role with node names every role.
# ---------------------------------------------------------------------------

# Read out of the server's catalog rather than out of `Base.metadata`. What a
# migration left in Postgres is what refuses a row at three in the morning, and
# the model is only a claim about it — the same reason
# `test_generated_constraint_names.py` reads `pg_constraint` instead of the
# migration text.
CHECK_CONSTRAINTS = text(
    "SELECT conname, pg_get_constraintdef(oid) AS definition"
    " FROM pg_constraint WHERE conrelid = to_regclass(:table) AND contype = 'c'"
)
ROLE_ENUM_LABELS = text(
    "SELECT e.enumlabel FROM pg_attribute a JOIN pg_enum e ON e.enumtypid = a.atttypid"
    " WHERE a.attrelid = to_regclass(:table) AND a.attname = :column"
    " ORDER BY e.enumsortorder"
)
TRIGGER_NAMES = text(
    "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass(:table) AND NOT tgisinternal"
)


def scope_columns(graph: Any) -> list[str]:
    """Every column this schema uses to say which node an assignment is scoped to.

    Asked of the builder rather than spelled here, because what a scope is made
    of is the one thing E0-09 leaves open and `SupervisionGraph` is where that
    question already lives.
    """
    shape, detail = graph.scope_shape()
    if shape == "per_kind":
        return sorted(detail.values())
    if shape == "kind_and_id":
        return sorted(detail)
    return [detail]


def test_an_assignment_carrying_two_scope_columns_is_refused(supervision_graph: Any) -> None:
    """A chair scoped to its department *and* to the institution is refused.

    **The failure this catches is a widening, not an error**, which is what makes
    it worth a test of its own. Every other row this module refuses announces
    itself: a cycle hangs a walk, a bad pairing is a role somewhere it does not
    belong. This one is an ordinary-looking chair with one extra column set, and
    [ADR 0025](../../docs/adr/0025-an-assignments-scope-is-one-nullable-foreign-key-per-level.md)
    says every reader of "the node this is scoped to" must coalesce the scope
    columns — "E0-11 and E9 will write that expression, probably once, in the
    purview resolver". A coalesce takes the first non-null, so the chair holds the
    institution: SPEC §2.1's own grant, restricted by role grain, becomes the whole
    university. Nothing errors and nobody is in a position to notice.

    The criterion behind it is E0-09's role grain rule — "an assignment's
    `scope_node_id` must reference a node of the right kind for its role" —
    singular, and the tests above it only ever check that the *wrong* kind is
    refused. A row naming the right kind and one more satisfies every one of them.

    **The control is the same chair without the extra column**, written through
    the same helper in the same transaction, so a refusal below is known to be
    about the second scope column rather than about the insert path or the grain
    arm. A schema that cannot spell two scope columns at all — one id column,
    whatever names its kind — cannot widen this way, and the assertion says so
    rather than pretending to have tested it.
    """
    graph = supervision_graph
    shape, detail = graph.scope_shape()

    written(graph, lambda: graph.node("CHAIR"), "A chair assignment scoped to one department")

    two_columns = shape == "per_kind" and {"department", "institution"} <= set(detail)
    also_the_institution = (
        graph.scope_overrides("institution", graph.scope("institution")) if two_columns else {}
    )
    refused = (
        graph.refusal(
            lambda: graph.assign(
                "CHAIR",
                scope=graph.fresh_scope("department"),
                person=graph.person(),
                **also_the_institution,
            )
        )
        if two_columns
        else None
    )
    assert not two_columns or refused is not None, (
        "A chair assignment was stored holding both a department and the institution. The row is "
        "not wrong on its face and no query fails: ADR 0025 makes the scope of an assignment a "
        "coalesce over the scope columns, so the resolver E0-11 writes takes the first non-null "
        "and this chair holds every college in the university. That is SPEC §2.1's role grain — "
        "'a chair's grant is the department subtree' — widened to institution-wide by one extra "
        "column, silently. The rule that says an assignment names exactly one of "
        f"{scope_columns(graph)} is what refuses it; relaxed from 'exactly one' to 'at least "
        "one', this row is accepted and everything else in this module stays green."
    )


def test_an_assignment_carrying_no_scope_column_is_refused(supervision_graph: Any) -> None:
    """The other side of "exactly one": a chair scoped to nothing is refused too.

    E0-09 gives every role a node — "a chair scoped to a department, a dean to a
    college, a lead to a course, **Care and Admin to the institution**" — and SPEC
    §2.1 computes the own grant from that node. An assignment with no node has no
    own grant to restrict, and whether that reads as a grant over nothing or as a
    grant over everything depends on how the coalesce above is consumed, which is
    a decision E0-11 would be making by accident.

    **Two rules can refuse this row and a behavioural test cannot say which**
    (`docs/MISTAKES.md` entry 3): the count of populated scope columns, and the
    grain arm requiring the role's own column to be populated. So this one does
    not bite when a single clause is loosened — the test that does that job is the
    two-column one above, and the *stated* half is the catalog test below. What it
    catches is the whole rule going away, and the grain rule being written in the
    one direction that reads as equivalent and is not: "a department column implies
    a chair" permits an unscoped chair, and "a chair implies a department column"
    does not.
    """
    graph = supervision_graph

    written(graph, lambda: graph.node("CHAIR"), "A chair assignment scoped to a department")

    own_level = graph.scope_overrides("department", graph.scope("department"))
    cleared = dict.fromkeys(own_level, None)
    refused = graph.refusal(lambda: graph.assign("CHAIR", person=graph.person(), **cleared))
    assert refused is not None, (
        "A chair assignment was stored naming no scope node at all — every one of "
        f"{scope_columns(graph)} left null. E0-09 gives each role a node and SPEC §2.1 computes "
        "the own grant from it, so this row is an authorization decision with nothing under it. "
        "ADR 0025 states the rule as 'an assignment is scoped to exactly one node'; exactly, not "
        "at most."
    )


def test_every_role_the_database_can_hold_is_named_in_the_scope_grain_rule(
    supervision_graph: Any,
) -> None:
    """The grain rule enumerates every role, so its fallthrough arm stays unreachable.

    This is the one assertion in this module about what a constraint *says* rather
    than about what the database *does*, and the reason is that the failure has no
    row to write. E0-09's grain rule pairs each role with the node kind it may be
    scoped to; a role the rule has no arm for falls through to whatever the rule
    ends in. Ending it closed — no legal scope for an unnamed role — is the right
    direction of failure, and ADR 0025 says so: "adding a role means editing this
    constraint, and forgetting to makes the role unwritable rather than
    unrestricted."

    But a closed fallthrough is a backstop for a mistake, not a licence to rely on
    it, and it cannot be reached from a test: writing a row for a role the enum
    does not hold is not something this suite can do without adding an enum label
    at runtime. What *is* assertable is the property that makes the fallthrough
    unreachable — every label the type holds is named in the rule. That is also
    the shape of the real failure, which is not "somebody changed the `ELSE`" but
    "somebody added a ninth role and did not come back here". ADR 0028 already
    describes that migration: "a migration adding an enum label and a `CASE` arm".
    This test is what makes the second half of that sentence enforced.

    **A label deliberately given no scope is still named, not omitted.** If a role
    is meant to be unwritable, an arm saying so states it; leaving it out states
    the same thing only for as long as nobody widens the fallthrough, and that is
    a rule held in place by a reader's memory.

    **Scope of the check**, since a property is only as wide as what it reads: it
    looks at CHECK constraints on `role_assignment` that mention the role column
    and at least one scope column, and asks that between them they name every
    label. Both non-vacuity guards are asserted first, because "no label is
    missing" is true of a table with no labels and of a table with no constraints
    (`docs/MISTAKES.md` entry 3).
    """
    graph = supervision_graph
    columns = scope_columns(graph)

    labels = [
        row[0]
        for row in graph.session.execute(
            ROLE_ENUM_LABELS, {"table": ASSIGNMENTS, "column": graph.role_column}
        )
    ]
    assert labels, (
        f"`{ASSIGNMENTS}.{graph.role_column}` is not an enumerated type, so this test cannot "
        "list the roles the database is able to hold and would otherwise pass having checked "
        "nothing. That is this test needing rewriting rather than the schema being wrong: a role "
        "column constrained some other way still has a set of legal roles, and the property — "
        "every one of them named in the grain rule — is the same. Say in the pull request what "
        "enumerates them and point this query at it."
    )

    definitions = {
        row.conname: row.definition
        for row in graph.session.execute(CHECK_CONSTRAINTS, {"table": ASSIGNMENTS})
    }
    stating = {
        name: definition
        for name, definition in definitions.items()
        if graph.role_column in definition and any(column in definition for column in columns)
    }
    trigger_names = sorted(
        row[0] for row in graph.session.execute(TRIGGER_NAMES, {"table": ASSIGNMENTS})
    )
    assert stating, (
        f"No CHECK constraint on `{ASSIGNMENTS}` mentions both `{graph.role_column}` and one of "
        f"{columns}, so nothing found here states E0-09's role grain rule. The table's check "
        f"constraints are {sorted(definitions)} and its triggers are {trigger_names}. "
        "If the rule is enforced by one of those triggers instead, this test has to read "
        "`pg_proc.prosrc` for it and should be changed to — the behavioural half is the grain "
        "tests above, and this half is what says the rule exists at all rather than that today's "
        "rows happen to be refused (`docs/MISTAKES.md` entry 3)."
    )

    unnamed = [
        label
        for label in labels
        if not any(f"'{label}'" in definition for definition in stating.values())
    ]
    assert not unnamed, (
        f"{unnamed} are roles the database can hold that {sorted(stating)} never names, so the "
        "scope grain rule has nothing to say about them and they fall through to whatever it ends "
        "in. E0-09: 'an assignment's `scope_node_id` must reference a node of the right kind for "
        "its role… Enforce it rather than trusting callers' — a role the rule does not mention is "
        "a role trusting the caller. Today's fallthrough may well refuse them, which is the safe "
        "direction and is the only reason this is a missing arm rather than an open grant; the arm "
        "is what keeps it that way when somebody later reads the fallthrough as dead code. If one "
        "of these is deliberately unwritable — ADR 0028 makes that case for a student — say it in "
        "the rule rather than by leaving it out."
    )


# ---------------------------------------------------------------------------
# Criteria 7 and 8 — Care sits at the institution and outside the graph.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wrong_kind", ["college", "department", "prefix", "course", "section"])
def test_a_care_assignment_scoped_below_the_institution_is_refused(
    supervision_graph: Any, wrong_kind: str
) -> None:
    """Criterion 7: Care is the Office of Community Standards, and it is institution-wide.

    SPEC §2.1's table and §6.2 both put Care at the institution. The reason to
    enforce it rather than assume it is what a section-scoped Care row would be:
    Care is the only role that can re-identify a student (§4), so a Care
    assignment attached to a course or a section is an identity-access grant
    shaped like an ordinary teaching assignment — which is exactly the shape an
    LTI launch context would produce.
    """
    graph = supervision_graph

    written(graph, lambda: graph.assign("CARE"), "A Care assignment scoped to the institution")

    unrepresentable = not graph.can_express(wrong_kind)
    refused = (
        None
        if unrepresentable
        else graph.refusal(lambda: graph.assign("CARE", scope_kind=wrong_kind))
    )
    assert unrepresentable or refused is not None, (
        f"A Care assignment was stored scoped to a {wrong_kind}. E0-09 criterion 7: 'A `CARE` "
        "assignment scoped to anything other than the institution is rejected.' §6.2 gives Care "
        "the threat queue and the reveal action, and §4 makes that the only re-identification "
        f"path in the product; a Care row hanging off a {wrong_kind} is an identity-access grant "
        "that arrived through a context, which is precisely what this table exists to keep "
        "separate from what a launch says."
    )


def test_a_care_assignment_cannot_report_to_anything(supervision_graph: Any) -> None:
    """Criterion 8, first half: a Care assignment carries no `reports_to`.

    "It sits outside the supervision graph entirely, because it supervises nothing
    and escalates to nobody (§2.1)." An edge upward from Care puts it inside
    somebody's transitive union — §2.1 defines purview as "own grant  union  purviews of
    all assignments transitively reporting to it" — and that union is how the Care
    queue's identity access would reach a chair.

    The control is the same parent taking an edge from a reporting assignment, so
    the refusal is known to be about the Care row rather than about that parent.
    """
    graph = supervision_graph
    key = graph.assignment_key

    parent = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=parent[key]),
        "An ordinary assignment reporting to that chair",
    )

    refused = graph.refusal(lambda: graph.assign("CARE", reports_to=parent[key]))
    assert refused is not None, (
        "A Care assignment was stored with a `reports_to` edge. E0-09 criterion 8: 'A `CARE` "
        "assignment never carries a `reports_to` edge and is never the target of one.' SPEC §2.1 "
        "makes purview the transitive union of everything reporting to an assignment, so an edge "
        "from Care upward puts the one role that can re-identify a student inside a chair's "
        "purview — and §2.1 says in bold that Care is deliberately not composable with reporting "
        "roles."
    )


def test_nothing_can_report_to_a_care_assignment(supervision_graph: Any) -> None:
    """Criterion 8, second half: a Care assignment is never the target of an edge.

    The mirror of the test above, and not implied by it. An edge *into* Care gives
    the Care assignment a purview — everything below it — which is the direction
    §6.2 spends a paragraph refusing: "comment content and identity access are
    visible to no other role", and Care's "sole power is the threat queue". A Care
    row with children is a role that can both re-identify and read reports.

    The control is the same child re-pointed at an ordinary assignment, so that a
    refusal is about the target being Care rather than about the edit itself.
    """
    graph = supervision_graph
    key = graph.assignment_key

    care = written(graph, lambda: graph.assign("CARE"), "A Care assignment")
    ordinary_parent = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    child = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=ordinary_parent[key]),
        "A lead reporting to that chair",
    )
    written(
        graph,
        lambda: graph.repoint(child, ordinary_parent[key]),
        "Re-pointing that lead at the same ordinary assignment",
    )

    refused = graph.refusal(lambda: graph.repoint(child, care[key]))
    assert refused is not None, (
        "An assignment was stored reporting to a Care assignment. E0-09 criterion 8: a Care "
        "assignment 'is never the target of one'. SPEC §2.1 computes purview as the union of "
        "everything transitively reporting to an assignment, so a child here gives Care a "
        "reporting purview — the one thing §6.2 says the role does not have, and the composition "
        "§2.1 calls deliberately impossible."
    )


def scoped_to_the_institution(graph: Any) -> dict[str, Any]:
    """The column values that move an existing assignment's scope to the institution.

    Every other scope column is cleared in the same statement, because "scoped to
    the institution" is a statement about all of them: leaving the old level set
    would make the update carry two scope columns, and the test below would then
    be refused by the rule the two-column test above owns rather than by the one
    it is about (`docs/MISTAKES.md` entry 3).
    """
    shape, detail = graph.scope_shape()
    cleared = dict.fromkeys(detail.values(), None) if shape == "per_kind" else {}
    return {**cleared, **graph.scope_overrides("institution", graph.scope("institution"))}


def become_care(graph: Any, row: Any) -> None:
    """Turn one existing assignment into a legal Care assignment, in one UPDATE.

    Legal in every respect the schema can check on the row itself: the role is
    Care, the scope is the institution that criterion 7 requires, and it reports
    to nobody. The only thing that can be wrong with the result is what points at
    it from elsewhere.
    """
    table = graph.assignments
    key = graph.assignment_key
    values = {graph.role_column: graph.role_value("CARE"), **scoped_to_the_institution(graph)}
    graph.session.execute(table.update().where(table.c[key] == row[key]).values(**values))


def test_an_assignment_others_report_to_cannot_be_turned_into_a_care_assignment(
    supervision_graph: Any,
) -> None:
    """Criterion 8, second half, by the third path into the same stored state.

    The two tests above cover a Care row written *with* an edge and an edge
    pointed *at* a Care row. This is the update that arrives from the other
    direction: the row is an ordinary supervisor with people reporting to it, and
    it is the row itself that changes. Nothing new points at Care; what changes is
    what the existing edges are pointing at. A guard that inspects the edge being
    written — the natural place to put it, and enough for both tests above — never
    runs here, and the end state is the one §2.1 and §6.2 refuse: a Care
    assignment with a reporting purview under it.

    That end state is the reason this branch is worth its own test rather than
    being counted as covered. §6.2: "comment content and identity access are
    visible to no other role, including Admin and the VPAA. This separation is
    enforced in code, not just convention." SPEC §2.1 computes purview as the
    union of everything transitively reporting to an assignment, so a Care
    assignment with children is the single role that can re-identify a student
    holding oversight of a chain of sections — and it got there through an admin
    editing somebody's role in the People editor, which is the ordinary way a role
    changes.

    **The control is the same update on an assignment nothing reports to**, and it
    is what makes the refusal attributable. Flipping a chair to Care moves the
    role, the scope and the derived entry doors all at once, so a bare
    `pytest.raises` here would pass against a schema that refuses *any* such
    update — for the grain rule, for a door, for a scope column left behind. The
    two updates below differ in exactly one thing: whether anything reports to the
    row.
    """
    graph = supervision_graph
    key = graph.assignment_key

    childless = written(
        graph,
        lambda: graph.node("CHAIR"),
        "A chair assignment nothing reports to",
    )
    supervisor = written(graph, lambda: graph.node("CHAIR"), "A second chair assignment")
    written(
        graph,
        lambda: graph.node("LEAD_FACULTY", reports_to=supervisor[key]),
        "A lead reporting to that second chair",
    )

    written(
        graph,
        lambda: become_care(graph, childless),
        "Turning the chair nobody reports to into a Care assignment",
    )

    refused = graph.refusal(lambda: become_care(graph, supervisor))
    assert refused is not None, (
        "An assignment with a lead reporting to it was turned into a Care assignment. E0-09 "
        "criterion 8: a Care assignment 'is never the target of one', and its scope says Care "
        "'sits outside the supervision graph entirely'. The stored state is the same one "
        "`test_nothing_can_report_to_a_care_assignment` refuses — a Care row with children — "
        "reached by changing the parent instead of the edge, so a guard that looks only at the "
        "edge being written leaves this path open while that test stays green. What sits under it "
        "is a purview: §2.1 unions everything transitively reporting to an assignment, and §6.2 "
        "gives Care the one power in the product that re-identifies a student."
    )


def test_a_person_may_hold_both_a_care_and_an_instructor_assignment(
    supervision_graph: Any,
) -> None:
    """Criterion 9: this one is **accepted**, and the test exists so that it stays that way.

    E0-09 is unusually explicit: "do not add a constraint forbidding it… The
    residual risk is accepted, governed by the ethical obligations of the Office
    of Community Standards and by the identity-access audit log." §6.2 says the
    same from the other end and gives the detective control — a reveal inside the
    revealer's own purview is flagged in the audit log, never blocked.

    So the failure this guards against is a later ticket "tightening" the schema:
    non-composability is about capabilities, not about people, and a constraint
    over `person_id` would express the wrong one. It goes through the shared
    builder because the ticket says this fixture is reused by E0-10 and E0-18.
    """
    graph = supervision_graph
    holder: dict[str, Any] = {}

    def build() -> None:
        holder["shape"] = graph.care_and_instructor_person()

    refused = graph.refusal(build)
    assert refused is None, (
        f"A person holding both a Care assignment and an instructor assignment was refused: "
        f"{refused}. E0-09 criterion 9 makes this **accepted**, deliberately: 'A Care staffer who "
        "also teaches a section is unlikely but legitimate… do not add a constraint forbidding "
        "it.' §6.2 handles the overlap detectively, by flagging the reveal in the audit log — a "
        "preventive control here 'would cost more than it saves', and it would make a real member "
        "of staff unrepresentable."
    )

    shape = holder["shape"]
    assert len(graph.assignments_of(shape["person"])) == 2, (
        "The Care staffer who also teaches came back holding "
        f"{len(graph.assignments_of(shape['person']))} assignments rather than two. Both writes "
        "were accepted, so one row replaced the other — and E0-10 and E0-18 reuse this fixture "
        "expecting a person with exactly these two hats."
    )


# ---------------------------------------------------------------------------
# Criterion 10 — the doors an assignment permits.
# ---------------------------------------------------------------------------


def door_columns(table: Any) -> list[str]:
    """Columns that look like they record an entry door."""
    return [
        column.name
        for column in table.columns
        if any(fragment in column.name.lower() for fragment in DOOR_COLUMN_FRAGMENTS)
    ]


def doors_recorded(table: Any, row: Any) -> set[str]:
    """The doors one assignment row records, however the schema spells them.

    Three shapes are read, because criterion 10 says "assignments record which
    entry doors they permit" and spells neither a column nor a value: a boolean
    per door, a list-valued column holding both, and a single text or enum column.
    A schema that records them some fourth way produces an empty set here, and the
    failure below names what was looked for.
    """
    found: set[str] = set()
    for name in door_columns(table):
        value = row[name]
        if value is None:
            continue
        if isinstance(stored_type(table.c[name]), Boolean):
            if not value:
                continue
            spellings = [name]
        elif isinstance(value, list | tuple | set):
            spellings = [str(item) for item in value]
        else:
            spellings = [str(value)]
        for spelling in spellings:
            lowered = spelling.lower()
            if any(fragment in lowered for fragment in LAUNCH_FRAGMENTS):
                found.add(LAUNCH_DOOR)
            if any(fragment in lowered for fragment in WEB_FRAGMENTS):
                found.add(WEB_DOOR)
    return found


@pytest.mark.parametrize("role", sorted(DOORS_BY_ROLE))
def test_an_assignment_records_the_entry_doors_its_role_permits(
    supervision_graph: Any, role: str
) -> None:
    """Criterion 10, one role per case, against SPEC §2.1's table.

    "Launch for every reporting role, web login for every role except instructor
    and student." §2.1's table is authoritative where its prose and the table
    disagree, and it is what `DOORS_BY_ROLE` at the top of this file copies.

    **This is the weakest test in the module, and it says so.** The criterion
    names no column, no value and no function, and the two readings are not the
    same thing: doors *derived* from the role cannot disagree with it, while doors
    *stored* per row can, and the criterion's own wording — launch for every
    reporting role — is a rule about roles. If the doors are stored and a writer
    is expected to set them, this test is reading a value the seeding helper
    invented, and the ticket needs to say which reading it means. The failure
    message says all of that; a shape this file cannot read is reported rather
    than worked around.
    """
    graph = supervision_graph
    table = graph.assignments

    assert door_columns(table), (
        f"`{ASSIGNMENTS}` carries no column that looks like an entry door — its columns are "
        f"{[column.name for column in table.columns]}, and this file looked for the fragments "
        f"{list(DOOR_COLUMN_FRAGMENTS)}. E0-09 criterion 10: 'Assignments record which entry "
        "doors they permit: launch for every reporting role, web login for every role except "
        "instructor and student.' SPEC §2.1 makes the door 'a property of the assignment, not the "
        "person', which is what lets a person holding two assignments use whichever door fits the "
        "one they are acting under."
    )

    row = written(graph, lambda: graph.assign(role), f"A {role} assignment")
    recorded = doors_recorded(table, row)
    held = {name: row[name] for name in door_columns(table)}
    assert recorded == DOORS_BY_ROLE[role], (
        f"A {role} assignment records the doors {sorted(recorded)}; SPEC §2.1's table gives it "
        f"{sorted(DOORS_BY_ROLE[role])}. The row holds {held}. Two things this failure can mean, "
        "and they need different fixes: the doors are wrong, or the doors are stored per row with "
        "no default and this test is reading a value the seeding helper invented. The second is a "
        "question for the ticket — 'record' is left open between a value derived from the role "
        "and a value a writer sets — and it wants settling in the pull request rather than by "
        "changing this test."
    )


# ---------------------------------------------------------------------------
# Criterion 11 — the assistant dean, and sibling leads.
# ---------------------------------------------------------------------------


def test_the_assistant_dean_shape_can_be_constructed(supervision_graph: Any) -> None:
    """Criterion 11: SPEC §2.1's worked example exists as rows, even though E9 computes it.

    "The assistant dean is the worked example for why purview comes from the
    graph: own led courses  union  every supervised chair's department — a set no single
    containment node holds."

    Four things are asserted, and each is a way the shape can be built and still
    not be the example. The assistant dean is scoped to the **same node as the
    dean** (§2.1's table says so, and a schema with a uniqueness rule over the
    scope node would refuse it). The supervised chairs sit in **different
    departments**, so their union is not one subtree. A third chair reports
    **straight to the dean**, which is §2.1's stated mixture. And the assistant
    dean's own led course sits under the department they do **not** supervise —
    without that, the college node holds the whole purview and the example stops
    being the reason the graph exists.
    """
    graph = supervision_graph
    key = graph.assignment_key
    holder: dict[str, Any] = {}

    def build() -> None:
        holder["shape"] = graph.assistant_dean_shape()

    refused = graph.refusal(build)
    assert refused is None, (
        f"The assistant-dean shape could not be built: {refused}. E0-09 criterion 11: 'The "
        "assistant-dean shape from §2.1 — lead courses plus supervised chairs — can be "
        "constructed in a fixture, even though computing its purview is E9.' If the refusal is "
        "about the scope node, note that §2.1 puts the assistant dean on the same college node as "
        "the dean: 'authority comes from the supervision graph, not the scope'."
    )

    shape = holder["shape"]
    assert shape["assistant_dean"][key] != shape["dean"][key], (
        "The assistant dean and the dean came back as one assignment, so there is no supervision "
        "step between them to be the example."
    )

    supervised = {graph.parent_of(chair[key]) for chair in shape["supervised_chairs"]}
    assert supervised == {shape["assistant_dean"][key]}, (
        f"The supervised chairs report to {supervised} rather than to the assistant dean. §2.1: "
        "'some chairs in a college report through an assistant dean (CHAIR → ASSISTANT_DEAN → "
        "DEAN) while others report straight to the dean' — the mixture is the case the graph "
        "exists for, and it is why containment cannot express reporting lines."
    )
    assert len(set(shape["supervised_departments"])) == 2, (
        "The two supervised chairs chair the same department, so their departments' union is one "
        "subtree and the shape is not the example §2.1 gives."
    )
    assert graph.parent_of(shape["unsupervised_chair"][key]) == shape["dean"][key], (
        "The third chair does not report straight to the dean, so every chair in the college is "
        "under the assistant dean and the college node holds the whole purview."
    )
    assert graph.parent_of(shape["lead"][key]) == shape["unsupervised_chair"][key], (
        "The assistant dean's own lead-faculty assignment does not sit under the department they "
        "do not supervise. That is what makes the purview 'a set no single containment node "
        "holds'; with the led course inside a supervised department, the college node covers "
        "everything and E9 could compute the right answer the wrong way."
    )


def test_two_sibling_lead_assignments_under_one_chair_do_not_reach_each_other(
    supervision_graph: Any,
) -> None:
    """SPEC §4.1 item 2, as a graph fact: siblings are not ancestors.

    Two lead-faculty assignments under one chair, each on its own course. §2.1
    computes purview as "own grant  union  purviews of all assignments transitively
    reporting to it", so the only way one lead could reach the other's course is
    by one being reachable from the other — and the walk this test performs over
    the stored edges is the walk E9 will write.

    **This asserts what the schema stored, and that is its limit.** It cannot say
    that a purview computation will respect it; that is E0-11's invariant test and
    E9's union. What it can say is that a chair's two leads share a parent and
    nothing else — and the failure it is written against is a schema where an edge
    could be, or was, put between them: `reports_to` on the wrong table, an edge
    inferred from containment, or a lead scoped above its course, which is why the
    invariant test above refuses that separately.
    """
    graph = supervision_graph
    key = graph.assignment_key

    chair = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    one = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", reports_to=chair[key]),
        "The first lead reporting to that chair",
    )
    two = written(
        graph,
        lambda: graph.assign(
            "LEAD_FACULTY", scope=graph.fresh_scope("course"), reports_to=chair[key]
        ),
        "The second lead reporting to that chair",
    )

    assert graph.ancestors(one[key]) == [chair[key]], (
        f"The first lead's ancestors are {graph.ancestors(one[key])} rather than the chair alone. "
        "Anything else in that list is an assignment whose purview now contains this lead's "
        "course."
    )
    assert graph.ancestors(two[key]) == [
        chair[key]
    ], f"The second lead's ancestors are {graph.ancestors(two[key])} rather than the chair alone."
    assert two[key] not in graph.ancestors(one[key]), (
        "One sibling lead is an ancestor of the other, so §2.1's transitive union puts a peer's "
        "courses inside a lead's purview — SPEC §4.1 item 2: 'A Lead Faculty assignment never "
        "grants sibling leads' courses, at any point in the purview union computation.'"
    )
    assert one[key] not in graph.ancestors(two[key]), "The same, in the other direction."


# ---------------------------------------------------------------------------
# ADR 0022 — E0-08's marker sweep has to reach these tables.
# ---------------------------------------------------------------------------


def test_the_assignment_tables_carry_no_unmarked_identity_column(migrated_engine: Any) -> None:
    """ADR 0022's marker, on E0-09's tables specifically.

    `tests/integration/test_identity_column_marker.py` sweeps "the tables that
    hold a person: `user`, `user_identity`, `person`, and anything with a foreign
    key to one of them", and both that module and ADR 0022 state, as a fact, that
    this reaches E0-09's `role_assignment` without being edited. The claim is
    about tables that did not exist when it was written, so this is where it is
    checked rather than assumed (`docs/MISTAKES.md` entry 1) — if these tables
    reached a person by any route other than a foreign key, that sweep would pass
    while looking straight past them.

    The plausible unmarked column here is a denormalised display name: the People
    editor (§6.3) sorts by last name, and a name copied onto the assignment row is
    the obvious way to make that cheap. It would sit inside every grant an
    instructor read path holds.

    Two non-vacuity guards run first. The tables have to exist, and something in
    the database has to be marked at all — "no unmarked identity column here" is
    otherwise satisfied by a schema with no marker convention, and by a table that
    was never created.
    """
    inspector = inspect(migrated_engine)
    present = inspector.get_table_names()
    for name in (ASSIGNMENTS, MAPPINGS):
        assert name in present, (
            f"The migrated database has no `{name}` table, so this sweep would report success "
            f"having looked at nothing. It holds {sorted(present)}."
        )

    marked = {
        (table, column["name"])
        for table in present
        for column in inspector.get_columns(table)
        if any(column["name"].lower().startswith(prefix) for prefix in MARKER_PREFIXES)
        or MARKER_TOKEN in (column.get("comment") or "").lower()
        or MARKER_TOKEN in ((inspector.get_table_comment(table) or {}).get("text") or "").lower()
    }
    assert marked, (
        "Nothing in the migrated database carries the identity marker in any shape — no "
        f"`{MARKER_PREFIXES[0]}` name prefix, no column comment containing {MARKER_TOKEN!r}, no "
        "table comment containing it. E0-08 put the marker on `user_identity` and `person`, so "
        "either it has gone or this file reads for it wrongly; until something is marked, the "
        "assertion below cannot tell a marked column from an unmarked one."
    )

    reaches_person = [
        table
        for table in (ASSIGNMENTS, MAPPINGS)
        if any(
            key.get("referred_table") in ("person", "user", "user_identity")
            for key in inspector.get_foreign_keys(table)
        )
    ]
    assert sorted(reaches_person) == sorted((ASSIGNMENTS, MAPPINGS)), (
        f"Only {reaches_person} reference a person table. ADR 0022 and "
        "`test_identity_column_marker.py` both claim the marker sweep reaches E0-09's tables "
        "'without being edited', and it reaches them by following a foreign key to `person`. A "
        "table that names a person some other way — a text column, a lookup by name — is outside "
        "that sweep, and ADR 0024 already rejected matching a person by name: 'the failure is a "
        "purview computed for the wrong person — invisible, because it produces a plausible "
        "answer'."
    )

    unmarked = sorted(
        f"{table}.{column['name']}"
        for table in (ASSIGNMENTS, MAPPINGS)
        for column in inspector.get_columns(table)
        if any(fragment in column["name"].lower() for fragment in IDENTITY_NAME_FRAGMENTS)
        and (table, column["name"]) not in marked
    )
    assert not unmarked, (
        f"{unmarked} are named as a person's identity — one of "
        f"{list(IDENTITY_NAME_FRAGMENTS)} — and carry no identity marker. ADR "
        "0022: E0-10 builds its views and its grants from the marked enumeration and the §4.1 "
        "invariant suite asserts against it, so a column missing from it is one those two believe "
        "is safe to expose — and `role_assignment` is joined by every leadership read path there "
        "is. If the column is genuinely not identity — a role label that happens to be spelled "
        "`name` — say so in the pull request and take it out of the sweep here."
    )
