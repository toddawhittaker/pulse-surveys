"""The two seams E0-11 leaves for later raise instead of answering — ticket E0-11.

E0-11's acceptance criterion: "The deferred transitive union is a named,
documented seam that raises `NotImplementedError` — not a silent empty set that
would read as 'no access' and look like it works. The module docstring explains
why it raises, per [ADR 0003]; without that, the next contributor 'fixes' it."

[ADR 0003](../../docs/adr/0003-deferred-authz-seams-fail-closed.md) generalises
that to **any** deferred authorization seam, so the n-threshold suppression rule
is held to it as well: the parameter and the call site are E0-11's, and the rule
that consumes them is E4's.

**Why a raise is the assertion rather than a value.** The alternative ADR 0003
spends most of its length rejecting is returning an empty `Purview`, and the
reason is that an empty purview is a legitimate state — a lead faculty member
with no reports has one — so nothing about it looks wrong. Callers would work,
tests would pass, and a dean would silently see nothing; the likely repair is
somebody diagnosing "the dean sees no data" as a scoping problem and widening
access somewhere else to compensate. So these tests assert that no value comes
back at all, for arguments that would each be perfectly ordinary if the
computation existed.

**Both seams are asserted on two things, and they are different claims.** That
the call raises, and that what it raises points at the epic that lands it. A bare
`NotImplementedError` is fail-closed and unmaintainable: it is exactly the shape a
future contributor deletes, having no way to tell a deliberate seam from an
oversight. The pointer is what makes it a seam.

**These are unit tests and take no database on purpose.** The union must refuse
before it reads anything, so a session is never opened; `None` is passed where one
belongs, and the raise has to arrive anyway. A seam that connects first, walks a
graph, and only then declines is a seam that can be reached by half.
"""

from typing import Any
from uuid import uuid4

import pytest

# The epics ADR 0003 and E0-11's scope name as the ones that land each seam. Read
# out of the ticket, not out of the code: SPEC §14.3 defers "transitive purview
# union over the assignment DAG… property tests over generated graphs — all E9",
# and §4's small-N suppression rules are E4's. A message that names some other
# epic is either a wrong pointer or a seam somebody moved without saying so.
UNION_EPIC = "E9"
SUPPRESSION_EPIC = "E4"

# What the module docstring has to carry for ADR 0003's last consequence to hold:
# "The stub is a place a future contributor may be tempted to 'fix' by returning
# something. The module docstring required by E0-11 has to say why it raises, or
# this decision has a short life." Three fragments — the epic, the fact that it
# raises, and what is missing — because each on its own is satisfied by prose
# that leaves the reader no better off.
DOCSTRING_RAISES_FRAGMENTS = ("raise", "notimplementederror")
DOCSTRING_SUBJECT_FRAGMENTS = ("union", "purview")


def test_the_deferred_transitive_union_raises_rather_than_returning_a_purview(
    authz: Any,
) -> None:
    """The criterion, and the one value ADR 0003 refuses above all others.

    An empty `Purview` here reads as "this assignment supervises nothing", which
    is a state the product genuinely has. A partial one — the own grant alone,
    with nothing from the supervised assignments — reads as a missing roster sync.
    Both are answers a caller can act on, and both are wrong in the direction that
    nobody reports: a dean seeing less than they should looks like a data problem,
    and the repair somebody reaches for is to widen access somewhere else.

    **The mutation this exists to survive** is `return Purview(frozenset(), ...)`
    in place of the raise — the change that makes E0-18's leadership landing
    views stop crashing, which is precisely the pressure ADR 0003 was written
    under.
    """
    transitive_purview = authz.transitive_purview

    try:
        answered = transitive_purview(None, assignment_id=uuid4())
    except NotImplementedError:
        return

    pytest.fail(
        f"`transitive_purview` answered with {answered!r} instead of raising. SPEC §2.1 defines "
        "purview as 'own grant ∪ purviews of all assignments transitively reporting to it', and "
        "E0-11 does not build it: 'Leave a clearly named unimplemented seam rather than a partial "
        "union.' ADR 0003 rejects every value that could stand in for one — an empty set reads as "
        "'supervises nothing', which is a real state; the own grant alone reads as a missing "
        "roster sync; the institution is the one direction §4.1 forbids absolutely."
    )


def test_the_deferred_transitive_union_names_the_epic_that_completes_it(authz: Any) -> None:
    """A raise nobody can date is a raise somebody deletes.

    ADR 0003's consequence: "E9 must add user-facing handling when it lands the
    real computation… This is a check for E9, recorded here so it is not
    discovered in production." A `NotImplementedError()` with an empty message
    satisfies the test above and tells the next reader nothing about whether it is
    a decision or an oversight — and E0-18's smoke tests are required to *not*
    traverse this seam, which is a rule nobody can follow if the error does not
    say what it is.
    """
    with pytest.raises(NotImplementedError) as refused:
        authz.transitive_purview(None, assignment_id=uuid4())

    message = str(refused.value)
    assert UNION_EPIC in message, (
        f"The deferred union raised {message!r}, which does not name {UNION_EPIC}. E0-11: 'a "
        "named, documented seam'; ADR 0003: it 'raises `NotImplementedError`, named and "
        "documented, pointing at E9'. The pointer is the whole difference between a seam and a "
        "gap — SPEC §14.3 puts the DAG union and its Hypothesis properties in E9, and a caller "
        "meeting this in a stack trace has no other way to learn that."
    )


def test_the_module_docstring_says_why_the_union_raises_and_which_epic_lands_it(
    authz: Any,
) -> None:
    """E0-11's definition of done: "add the module docstring that tells a future reader why".

    ADR 0003 ends on this and says why it is load-bearing rather than
    housekeeping: "The stub is a place a future contributor may be tempted to
    'fix' by returning something. The module docstring required by E0-11 has to
    say why it raises, or this decision has a short life." The person who deletes
    a fail-closed seam is not being careless — they are reading a function that
    obviously does not work and making it work, and the docstring is the only
    thing in their way.

    Three fragments rather than one, because each alone passes against prose that
    leaves the reader no better off: a docstring naming E9 and nothing else reads
    as a to-do, and one describing a union without saying it raises does not
    explain the exception anybody is here about.
    """
    docstring = authz.module.__doc__ or ""
    lowered = docstring.lower()

    assert docstring.strip(), (
        "`app.services.authz` has no module docstring. E0-11's definition of done: 'Docs apply, "
        "briefly. `CLAUDE.md` already states the chokepoint rule; add the module docstring that "
        "tells a future reader why the union is deliberately absent and which epic completes it.'"
    )
    assert UNION_EPIC in docstring, (
        f"The module docstring never names {UNION_EPIC}, so a reader who has just met "
        "`NotImplementedError` cannot find out when it stops being raised. SPEC §14.3 puts the "
        f"transitive union in that epic. What it says: {docstring.strip()[:400]!r}"
    )
    assert any(fragment in lowered for fragment in DOCSTRING_RAISES_FRAGMENTS), (
        f"The module docstring names {UNION_EPIC} but says nothing about raising, so it reads as "
        "a note about future work rather than as an explanation of the exception a caller has "
        "just been handed. ADR 0003 asks it to 'say why it raises'."
    )
    assert any(fragment in lowered for fragment in DOCSTRING_SUBJECT_FRAGMENTS), (
        "The module docstring explains a raise without naming what is missing. The absent thing "
        "is SPEC §2.1's purview union over the supervision graph, and a reader who cannot tell "
        "*which* computation is deferred cannot tell whether the one they need is."
    )


@pytest.mark.parametrize(
    ("response_count", "n_threshold"),
    [
        pytest.param(1, 5, id="below-the-threshold"),
        pytest.param(5, 5, id="exactly-at-the-threshold"),
        pytest.param(40, 5, id="far-above-the-threshold"),
    ],
)
def test_the_raw_comment_seam_raises_rather_than_answering(
    authz: Any, response_count: int, n_threshold: int
) -> None:
    """ADR 0003 generalised: "any deferred authorization seam fails closed by raising".

    E0-11's scope carries the interface and not the rule — "The n-threshold guard
    *interface* — the parameter and the call site — with the threshold read from
    `Settings`. The suppression rules that use it are E4." SPEC §4 and §4.1 item 3
    are what E4 will implement here: below the threshold, raw comments are hidden
    from instructors and students alike, and comments from under-threshold weeks
    surface later, batched, so that timing cannot identify an author.

    **All three cases are asserted, and the third is the one that matters.**
    Refusing below the threshold and answering `True` above it is the partial
    implementation ADR 0003 rejects in its second alternative: it is right about
    the easy half and silent about the batching rule, which is the half that
    decides whether a comment from a two-response week can be identified by when
    it appeared. A seam that answers a caller at all is a seam a caller will
    build on.
    """
    raw_comments_permitted = authz.raw_comments_permitted

    with pytest.raises(NotImplementedError):
        raw_comments_permitted(response_count=response_count, n_threshold=n_threshold)


def test_the_raw_comment_seam_names_the_epic_that_completes_it(authz: Any) -> None:
    """The same pointer requirement, for the seam ADR 0003 generalises to.

    §4's small-N handling is not a simple comparison — "Comments from
    under-threshold weeks are not discarded — they feed the summary, and they
    surface as raw text once the section's cumulative comment volume for the term
    crosses the threshold, batched so that timing cannot identify an author" — so
    the next reader's most likely reaction to a bare raise is to write the
    comparison they can see and move on. The epic in the message is what tells
    them there is a rule they have not read.
    """
    with pytest.raises(NotImplementedError) as refused:
        authz.raw_comments_permitted(response_count=1, n_threshold=5)

    message = str(refused.value)
    assert SUPPRESSION_EPIC in message, (
        f"The n-threshold seam raised {message!r}, which does not name {SUPPRESSION_EPIC}. E0-11 "
        "ships the parameter and the call site; the suppression rules that consume them are E4's, "
        "and §4's rule is a batching rule rather than the comparison a reader would infer from "
        "the signature."
    )
