"""A purview is six sets of org nodes, and Care is not one of them — ticket E0-11.

E0-11's scope: "The resolver returns Care as a *separate* capability rather than
as an element of the purview set, so that no union operation can ever pick it
up." That sentence is a claim about the **shape** of the value, and this module is
where the shape is asserted; whether a resolver actually keeps the two apart is
`tests/integration/test_a_resolved_scope_holds_care_beside_the_purview.py`, over
a person who holds both hats.

Both halves are needed and neither implies the other. A resolver that returns the
right answer today, over a value that has somewhere to put Care, is one union
away from carrying it — and §2 is explicit that this is the composition to
prevent: "**Care is deliberately not composable** with reporting roles — its sole
power is the threat queue, kept isolated so safety re-identification never rides
alongside routine oversight access."

**Why the union is asserted here at all, given that the transitive union is
deferred.** `Purview.union` is the operation §2.1's definition is written in —
"own grant ∪ purviews of all assignments transitively reporting to it" — and E9
is the ticket that walks the graph, not the ticket that decides what joining two
purviews means. A union that dropped a level would be invisible in E0: a purview
with `section_ids` and no `course_ids` still renders, still scopes a query, and
still looks like an answer.

**What is not asserted here, and where it is.** That a Care assignment produces no
purview to union in the first place — `own_grant` on one raises rather than
returning the institution — needs a database and is next door. The two are the
same rule from two ends: nothing can pick Care up out of a purview, and there is
no Care purview to pick up.
"""

import dataclasses
from typing import Any
from uuid import uuid4

import pytest

# The six containment levels SPEC §2.1 draws, outermost first, spelled as the
# fields E0-11 settled. **Deliberately written out rather than read off the
# dataclass** (`docs/MISTAKES.md` entry 19): a test that took its expectation from
# `dataclasses.fields(Purview)` would be comparing the class against itself, and a
# seventh field could be added with this file green.
PURVIEW_LEVELS = (
    "institution_ids",
    "college_ids",
    "department_ids",
    "prefix_ids",
    "course_ids",
    "section_ids",
)

# What an actor scope carries beside the purview. Same provenance as above: the
# ticket's own list, transcribed, not derived.
ACTOR_SCOPE_FIELDS = ("person_id", "purview", "holds_care", "n_threshold")

# Fragments that would read as a capability rather than as a place. A purview is
# a set of nodes; anything here appearing as one of its fields is a power stored
# where a union will find it.
CAPABILITY_FRAGMENTS = ("care", "reveal", "identity", "admin", "permit", "can_")


def levels(purview: Any) -> dict[str, Any]:
    """Every containment level of one purview, by name."""
    return {name: getattr(purview, name) for name in PURVIEW_LEVELS}


def purview_of(authz: Any, **populated: Any) -> Any:
    """One `Purview`, with every level supplied so no default decides anything."""
    values = {name: frozenset(populated.get(name, ())) for name in PURVIEW_LEVELS}
    return authz.Purview(**values)


def test_a_purview_carries_exactly_the_six_containment_levels(authz: Any) -> None:
    """SPEC §2.1's hierarchy, and nothing else in the same value.

    "Institution → College → Department → Prefix → Course → Section." A purview is
    a set of nodes at each of those levels and is not a place to keep anything
    else, which is the property every other assertion in this file rests on: a
    union over six sets of ids cannot widen a capability, because there is no
    capability in it to widen.

    A seventh field is the failure. It need not be called `care` to be one —
    `can_reveal`, `is_admin`, an entry-door flag — and each arrives for a good
    local reason, since the purview is the value already being passed to every
    read path.
    """
    Purview = authz.Purview

    assert dataclasses.is_dataclass(Purview), (
        f"`Purview` is {Purview!r} rather than a dataclass, so this test cannot list its fields. "
        "E0-11 settles it as a frozen dataclass of six frozensets; if it is genuinely something "
        "else, say so in the pull request — the property below is the same one either way."
    )

    declared = tuple(field.name for field in dataclasses.fields(Purview))
    assert declared == PURVIEW_LEVELS, (
        f"`Purview` carries {declared}; SPEC §2.1's containment hierarchy is {PURVIEW_LEVELS}. A "
        "missing level is a scope that cannot be expressed — a chair's grant is a department "
        "*subtree*, and a purview with no `prefix_ids` cannot say which prefixes are in it. An "
        "extra one is worse: whatever it holds is carried through every union, and §2 keeps Care "
        "out of purviews precisely so that no union can pick it up."
    )


def test_a_purview_holds_nothing_that_reads_as_a_capability(authz: Any) -> None:
    """The same rule stated as what may not appear, so a rename does not slip past.

    The test above compares against the exact six and would catch this too; this
    one exists because its failure message is the one the next reader needs. A
    field called `holds_care` on `Purview` is not a naming preference — §2 makes
    Care non-composable, §6.2 gives it identity access and no reporting access,
    and a union that carries it hands the one role that can re-identify a student
    to whoever the union was computed for.
    """
    fields = [field.name.lower() for field in dataclasses.fields(authz.Purview)]

    capabilities = sorted(
        name for name in fields if any(fragment in name for fragment in CAPABILITY_FRAGMENTS)
    )
    assert not capabilities, (
        f"`Purview` carries {capabilities}. E0-11: 'The resolver returns Care as a *separate* "
        "capability rather than as an element of the purview set, so that no union operation can "
        "ever pick it up.' SPEC §2: 'Care is deliberately not composable with reporting roles — "
        "its sole power is the threat queue, kept isolated so safety re-identification never "
        "rides alongside routine oversight access.'"
    )


def test_a_purview_unions_every_level(authz: Any) -> None:
    """§2.1's `∪`, level by level, with nothing dropped and nothing invented.

    Six levels are populated on each side with ids the other does not hold, so a
    union that forgot a level, or that returned one operand, fails on exactly the
    level it lost rather than on a whole-value comparison nobody can read.

    **The failure this describes is silent in both directions.** A union that
    drops `course_ids` narrows a purview — nobody reports seeing too little in a
    product with no data in it yet — and one that widens hands somebody a node
    nobody granted. §4.1 item 6 forbids only one of those absolutely, which is
    why the assertion is equality rather than containment.
    """
    Purview = authz.Purview
    mine = {name: frozenset({uuid4()}) for name in PURVIEW_LEVELS}
    yours = {name: frozenset({uuid4()}) for name in PURVIEW_LEVELS}

    first = Purview(**mine)
    second = Purview(**yours)
    joined = first.union(second)

    assert isinstance(joined, Purview), (
        f"`Purview.union` answered {joined!r}, which is not a `Purview`. §2.1 defines purview as "
        "a union of purviews, so the result has to be one — anything else cannot be unioned again "
        "with the next assignment in the walk."
    )
    expected = {name: mine[name] | yours[name] for name in PURVIEW_LEVELS}
    assert levels(joined) == expected, (
        f"Unioning two purviews produced {levels(joined)} rather than {expected}. Every level "
        "differs on both sides, so a level that came back wrong was either dropped or taken from "
        "one operand — and a purview missing a level still renders, still scopes a query, and "
        "still looks like an answer."
    )
    assert levels(first) == mine and levels(second) == yours, (
        "Unioning two purviews changed one of them. A purview is handed to every read path in a "
        "request, so an in-place union widens scopes the caller never asked about, in an order "
        "nothing records."
    )


def test_a_purview_cannot_be_widened_in_place(authz: Any) -> None:
    """A scope handed to a caller is not a scope the caller can edit.

    E0-11 makes this module "the single chokepoint every entry point passes
    through". A mutable purview means a router, a Celery task or E9's MCP server
    can add a node to the scope it was given and then read with it, and nothing in
    the chokepoint is involved in the decision. §4.1 item 6 — "no view may ever
    widen a student's visibility relative to these rules" — is a rule about views,
    and this is the value they are all handed.
    """
    purview = purview_of(authz, course_ids={uuid4()})

    with pytest.raises(AttributeError):
        purview.course_ids = frozenset({uuid4()})


def test_an_actor_scope_carries_care_as_a_capability_beside_the_purview(authz: Any) -> None:
    """E0-11's scope, as the shape of what a resolver returns.

    "Ticket E0-10's Care service asks this module whether the actor holds Care;
    that is the only supported way to ask." So the answer has to be somewhere a
    caller can read it, and the whole design is that it is *beside* the purview
    rather than in it: `holds_care` is a boolean about the actor, and the purview
    is a set of nodes, and no operation defined on the second can reach the first.

    `n_threshold` is asserted here for the same reason it exists on the scope at
    all — §4 makes suppression a property of the request, and a caller that has to
    fetch the threshold separately is a caller that can forget to.
    """
    ActorScope = authz.ActorScope

    assert dataclasses.is_dataclass(ActorScope), (
        f"`ActorScope` is {ActorScope!r} rather than a dataclass, so this test cannot list its "
        "fields."
    )

    declared = tuple(field.name for field in dataclasses.fields(ActorScope))
    assert declared == ACTOR_SCOPE_FIELDS, (
        f"`ActorScope` carries {declared} rather than {ACTOR_SCOPE_FIELDS}. Each of the four is a "
        "separate requirement: the person the scope was resolved for, the purview §2.1 defines, "
        "Care as a capability of its own (E0-11: 'so that no union operation can ever pick it "
        "up'), and §4's n-threshold, which E4's suppression rules read from here."
    )
