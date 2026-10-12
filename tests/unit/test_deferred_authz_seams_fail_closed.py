"""The raw-comment seam still raises; the transitive union no longer does — E0-11, rewritten by E9-01.

E0-11 left two seams that raised `NotImplementedError` rather than answering, and
[ADR 0003](../../docs/adr/0003-deferred-authz-seams-fail-closed.md) generalised
the rule to any deferred authorization seam. This module asserted both.

**E9-01 lands the transitive union, and the three tests that asserted it raised
are gone, deliberately.** They asserted that `transitive_purview` raised, that
its message named E9, and that the module docstring explained why it raised.
E9-01's done-when 13: "`transitive_purview` no longer raises, and every test that
asserted the seam raised is rewritten in its own commit, saying in the pull
request why the old assertion is now wrong" (`docs/MISTAKES.md` entry 22). The
old assertions are wrong because the computation they guarded now exists: SPEC
§2.1's union over the supervision graph, with the lead clamp, written by E9-01
and recorded in ADR 0199. What replaces them:

  - the walk answering a `Purview`:
    `tests/integration/test_the_purview_walk_is_transitive_and_batched_by_level.py::
    test_transitive_purview_answers_a_purview_where_it_used_to_raise`;
  - §4.1 item 2 over the walk, which the raise stood in for:
    `tests/integration/test_the_purview_walk_holds_over_generated_forests.py`, marked
    `invariant`;
  - the records no longer describing a raising seam: the two tests at the foot of
    this module (done-when 14).

**The raw-comment seam is unchanged.** Its two tests stay exactly as E0-11 and
E0-41 wrote them: the parameter and the call site are E0-11's, the rule that
consumes them is E4's, and the seam answers by raising.

**These are unit tests and take no database.** The records tests read docstrings
off the imported module; nothing here opens a session.
"""

import inspect
import re
from typing import Any

import pytest

# The epic ADR 0003 and E0-11's scope name as the one that lands the raw-comment
# seam. Read out of the ticket, not out of the code.
SUPPRESSION_EPIC = "E4"

# What a docstring describing the old raising seam says. Each is a phrase the
# E0-11 records carried, grepped as the fact rather than as an identifier
# (`docs/MISTAKES.md` entry 1).
SEAM_WORDS = ("notimplementederror", "deferred", "seam", "e9")
UNION_WORDS = ("union", "transitive")


@pytest.mark.invariant
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

    **Marked `invariant` by E0-41**, and it is the assertion SPEC §4.1 item 3 has
    at this seam: "below the n-threshold, raw comments are hidden from
    instructors and students alike". A seam that starts returning `True` hides no
    comment from anybody. The `invariant` marker composes with `parametrize` —
    every one of the three cases runs in the isolated pass.

    **All three cases are asserted, and the third is the one that matters.**
    Refusing below the threshold and answering `True` above it is the partial
    implementation ADR 0003 rejects in its second alternative: it is right about
    the easy half and silent about the batching rule.
    """
    raw_comments_permitted = authz.raw_comments_permitted

    with pytest.raises(NotImplementedError):
        raw_comments_permitted(response_count=response_count, n_threshold=n_threshold)


def test_the_raw_comment_seam_names_the_epic_that_completes_it(authz: Any) -> None:
    """The pointer requirement, for the seam ADR 0003 generalises to.

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


def test_transitive_purviews_docstring_says_what_the_walk_does_rather_than_that_it_raises(
    authz: Any,
) -> None:
    """Done-when 14: the function's own record no longer describes a raising seam.

    The ticket: "Comments in `authz.py` that say 'E9 lands it' or name a ticket
    are rewritten to say what the code does." `transitive_purview` was the seam,
    so its docstring is where the old sentence lived. It must exist, and it must
    not say `NotImplementedError`, "deferred", "seam" or "E9".

    **The mutation this kills:** the raise replaced and the docstring left
    describing it — the record ADR 0003 asked for, now asserting something false
    (`docs/MISTAKES.md` entry 1).
    """
    doc = inspect.getdoc(authz.transitive_purview) or ""
    stale = [word for word in SEAM_WORDS if word in doc.lower()]
    assert doc.strip(), (
        "`transitive_purview` has no docstring. It computes SPEC §2.1's union with the lead "
        "clamp, and the next reader needs both said where the function is."
    )
    assert not stale, (
        f"`transitive_purview`'s docstring still carries {stale}, the words of the seam E9-01 "
        f"replaced. It reads: {doc[:600]!r}"
    )


def test_the_authz_module_docstring_no_longer_says_the_union_raises(authz: Any) -> None:
    """Done-when 14: the module docstring no longer explains a raise that no longer happens.

    E0-11 required the module docstring to say why the union raised and which
    epic would land it. Now a sentence that pairs the union with
    `NotImplementedError`, or says "E9 lands" anything, is a false record. A
    sentence about the raw-comment seam raising is not caught: it names no union.

    **The mutation this kills:** E0-11's paragraph left in place.
    """
    doc = authz.module.__doc__ or ""
    sentences = re.split(r"(?<=[.!?])\s+", doc)
    stale = [
        sentence.strip()
        for sentence in sentences
        if (
            any(word in sentence.lower() for word in UNION_WORDS)
            and "notimplementederror" in sentence.lower()
        )
        or "e9 lands" in sentence.lower()
    ]
    assert doc.strip(), "`app.services.authz` has no module docstring."
    assert (
        not stale
    ), f"The authz module docstring still says the union raises or that E9 lands it: {stale}."
