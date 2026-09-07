"""Comment display order is randomized — ticket E4-04, criterion 4.

SPEC §4, one line under the small-N rule:

> Comment display order is randomized; timestamps are never shown with comments.

The two halves of that sentence are one rule. A list of comments returned in
submission order *is* a timestamp: it says who answered first, and in a section
whose gradebook carries SPEC §3.4's per-week completion ledger (ADR 0125) the
first responder is often nameable. The same is true of any stored order — the
answer's key, the response's key, the student's key — because every one of them
is assigned in the order rows arrived.

E4-04's known traps put the question where this module answers it:

> **Randomization in SQL vs in Python** decides where the no-timestamp rule must
> be checked — wherever ordering happens, the timestamp must not be the order key
> in disguise.

## The seam, and why it is private

An earlier draft of this module drove an `rng` parameter on both public reads.
The security round removed it, and the reasoning is worth carrying here because
it is what these tests are shaped by: **a seed a caller can supply is a seed an
attacker can fix.** With a fixed seed, two reads of the same week produce the
same permutation, so the difference between the shuffled output and a second
shuffle of a known set re-derives the order the rows arrived in — and with no
`ORDER BY` underneath, that is heap order, which is insertion order, which is
submission order. The same fixed seed a week apart also pins a newly released
comment by its position: everything that did not move is old.

So the source is `_make_rng`, a private module-level hook, and these tests
replace it. That is a seam for the suite and not an interface for a caller, and
saying so plainly is better than a parameter nobody notices is public.

**The patch is written to tolerate the hook's arity.** It replaces `_make_rng`
with a callable accepting anything, because the work order settles the hook's
name and not its signature, and a test that pinned the signature would be
deciding something the ticket left open. What it pins is that the hook is *the*
source: a service that ignores it fails the determinism half.

**Three properties, and they point in three directions.**

  - **A different source gives a different order.** This kills a stored order:
    `ORDER BY answer.id`, `ORDER BY submitted_at`, or no `ORDER BY` at all in a
    query that comes back sorted. None of those moves when the hook does.
  - **The same source gives the same order.** Without it, the first property is
    satisfied by a service that ignores the hook and shuffles from the system
    source — a seam that does not exist, leaving nothing in this suite able to
    assert an order again.
  - **An unpatched read still shuffles.** The seam must not be the *only* thing
    that shuffles: production never patches it, and a service that shuffled only
    when handed a source would ship an unshuffled report.

**None of these is a probability.** Each is asserted over eight or twelve
readings and requires more than one distinct order among them, so a service that
shuffles genuinely fails only if every one of them lands on the same permutation
of six comments, and a service that does not shuffle fails every time.

**And the multiset is asserted unchanged.** A "shuffle" that dropped or
duplicated a comment would satisfy the order assertions and change what the
instructor reads.
"""

import random
from typing import Any

import pytest
from fixtures.report_comments import CommentWorld

pytestmark = pytest.mark.integration

# A week at or above the threshold, whose comments an instructor reads directly,
# and three held weeks whose comments are released together. Both reads shuffle,
# so both are driven here.
BIG_WEEK = 7
HELD_WEEKS = (8, 9, 10)

# How many comments the shuffled sets hold. Enough that two independent shuffles
# agreeing is not something a run meets: with `n` comments there are `n!` orders,
# and eight readings all landing on one of them is not a failure mode a suite has
# to reason about. Six is also enough that a service returning "the first three"
# is visibly wrong.
COMMENTS_IN_THE_BIG_WEEK = 6

# The seeds the patched orders are read under. Eight distinct integers, so "at
# least two of these orders differ" is a claim about the seam rather than about
# luck, and `A_SEED` is one of them so the determinism half and the variation half
# talk about the same source.
SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
A_SEED = SEEDS[0]

# How many times an unpatched read is taken. More than the patched count, because
# the unpatched half has no seam to lean on and its whole claim is that the
# production path shuffles at all.
UNPATCHED_READINGS = 12

A_COMMENT = "the tutorial exercises were pitched about right and the marking was quick"


def a_week_of(count: int, week: int) -> list[str]:
    """`count` distinct comment texts for one week.

    Distinct because an order is read as a sequence of texts: two identical
    comments make two different orders compare equal, which is the one thing that
    would make the variation assertions below unfalsifiable.
    """
    return [f"{A_COMMENT} (week {week}, response {index + 1})" for index in range(count)]


def order_of(comments: Any) -> tuple[str, ...]:
    """The texts a read answered with, in the order it answered them."""
    return tuple(str(comment.text) for comment in comments)


def require_the_hook(contract: Any) -> Any:
    """The module and its `_make_rng`, or a failure naming the deliverable that owes it.

    Checked before `monkeypatch.setattr` rather than after, because
    `setattr` on an absent attribute raises `AttributeError` — an error rather
    than a failed assertion, which is the wrong kind of red for a tests-first
    suite (`docs/MISTAKES.md` entry 44).
    """
    module = contract.service()
    hook = getattr(module, contract.rng_hook, None)
    if not callable(hook):
        pytest.fail(
            f"`{contract.service_module}` exposes no callable `{contract.rng_hook}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            f"{contract.rng_hook_is_owed}"
        )
    return module


def seeded(monkeypatch: pytest.MonkeyPatch, contract: Any, seed: int) -> None:
    """Replace the module's random source with a freshly seeded one.

    The replacement accepts any arguments, because the work order settles the
    hook's *name* and not its signature; pinning the signature here would decide
    something the ticket left open, and what this needs to pin is only that the
    hook is where the order comes from.

    A fresh `random.Random` on every call, not one instance reused: a service that
    consumed a shared generator and a service that ignored it would be
    indistinguishable if the second read drew from a moved state.
    """
    module = require_the_hook(contract)
    monkeypatch.setattr(module, contract.rng_hook, lambda *args, **kwargs: random.Random(seed))  # noqa: S311 — the rng seam under test wants determinism, not cryptography


def plant_a_big_week(world: CommentWorld, contract: Any) -> int:
    """One week at or above the threshold, holding `COMMENTS_IN_THE_BIG_WEEK` comments."""
    threshold = contract.threshold()
    size = max(COMMENTS_IN_THE_BIG_WEEK, threshold)
    world.build()
    world.close_week(BIG_WEEK)
    world.week_of_comments(
        term_week=BIG_WEEK, texts=a_week_of(size, BIG_WEEK), stream=contract.instructor_stream
    )
    planted = world.responses_in(term_week=BIG_WEEK)
    assert planted == size and planted >= threshold, (
        f"The week holds {planted} responses; this test planted {size} and the configured "
        f"threshold is {threshold}. A week under the threshold returns nothing, and every order "
        "compared below would then be the empty tuple."
    )
    return size


def plant_a_released_term(world: CommentWorld, contract: Any) -> int:
    """Held comments across three closed under-threshold weeks, crossed and cut.

    One comment per respondent, so the number of distinct people behind the held
    set is the number of comments — which is what the security round's second gate
    condition counts, and what makes this world one the cutter may release at all.
    """
    threshold = contract.threshold()
    size = max(COMMENTS_IN_THE_BIG_WEEK, threshold)
    world.build()

    planted = 0
    while planted < size:
        week = HELD_WEEKS[planted % len(HELD_WEEKS)]
        world.close_week(week)
        world.week_of_comments(
            term_week=week,
            texts=[f"{A_COMMENT} (week {week}, response {planted + 1})"],
            stream=contract.instructor_stream,
        )
        planted += 1

    for week in HELD_WEEKS:
        count = world.responses_in(term_week=week)
        assert 0 < count < threshold, (
            f"Term week {week} holds {count} responses and the configured threshold is "
            f"{threshold}; a week that is not under it holds nothing to release."
        )
    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batches over a section holding {size} comments from "
        f"{size} distinct respondents across {len(HELD_WEEKS)} under-threshold weeks — every leg "
        "of the release gate satisfied. Without a batch there is nothing to shuffle and every "
        "order compared below would be the empty tuple."
    )
    return size


def read_visible(world: CommentWorld, contract: Any) -> Any:
    """The big week's comments, through the public signature — which takes no source."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(BIG_WEEK),
        stream=contract.instructor_stream,
    )


def read_released(world: CommentWorld, contract: Any) -> Any:
    """The term's released comments, through the public signature."""
    return contract.released()(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=contract.instructor_stream,
    )


# ---------------------------------------------------------------------------
# The seam is private.
# ---------------------------------------------------------------------------


def test_neither_read_accepts_a_caller_supplied_random_source(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The security round's ruling, asserted as a refusal rather than as a name list.

    `_make_rng` exists and is the module's own; `visible_comments` and
    `released_comments` refuse an `rng=` argument outright.

    **A refusal rather than an inventory, and the two are not the same test.**
    `tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`
    asserts the whole parameter tuple, which catches a *declared* `rng`. It does
    not catch a `**kwargs` on the signature, which declares nothing and accepts
    everything — and a read that quietly took `rng` through `**kwargs` would be a
    public seed with no name in the signature at all. Calling it and requiring
    `TypeError` is what sees that one.

    **Why a caller-supplied seed is the finding and not a style question.** Fixed,
    it makes two reads of one week produce the same permutation, so diffing a
    shuffled result against a second shuffle of a known set re-derives the order
    the rows arrived in — heap order, which is insertion order, which is
    submission order, which is who answered first. Used a week apart it pins a
    newly released comment by position: everything that did not move is old.
    §4 randomizes the order precisely to remove both.

    **The control is that the ordinary call works**, made first: a read that
    raised `TypeError` for every call would satisfy both refusals below while
    saying nothing.

    **The mutation it kills:** `rng` restored to either public signature, and
    `**kwargs` added to either — which is how it would come back without a diff
    anybody reads as an interface change.
    """
    contract = comment_contract
    world = comment_world
    plant_a_big_week(world, contract)
    require_the_hook(contract)

    assert read_visible(world, contract), (
        "The ordinary read answered nothing, so the refusals asserted below could be a read that "
        "raises for every call. `plant_a_big_week` asserts the week is at the threshold, so this "
        "is the read rather than the world."
    )

    with pytest.raises(TypeError):
        contract.visible()(
            world.session,
            section_id=world.section_id(),
            week_id=world.week_id(BIG_WEEK),
            stream=contract.instructor_stream,
            rng=random.Random(A_SEED),  # noqa: S311 — the rng seam under test wants determinism, not cryptography
        )
    with pytest.raises(TypeError):
        contract.released()(
            world.session,
            section_id=world.section_id(),
            term_id=world.term_id(),
            stream=contract.instructor_stream,
            rng=random.Random(A_SEED),  # noqa: S311 — the rng seam under test wants determinism, not cryptography
        )


# ---------------------------------------------------------------------------
# The week an instructor reads directly.
# ---------------------------------------------------------------------------


def test_the_visible_weeks_order_changes_with_the_random_source(
    comment_world: CommentWorld, comment_contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SPEC §4's randomized display order, asserted where a stored order would show.

    Eight sources over one week's comments. A service that ordered by anything the
    database holds — the answer's key, the response's key, `submitted_at`, or
    nothing at all — returns one order for all eight, and this is the assertion
    that says so.

    **The multiset is asserted first**, so a "shuffle" that dropped a comment or
    returned a subset fails as what it is rather than as a variation.

    **Why the order matters as much as the timestamp does.** A list in submission
    order says who answered first. Read beside the per-week completion ledger SPEC
    §3.4 posts into the gradebook (ADR 0125), first-answered is often a nameable
    student, and the whole of §4's confidentiality rests on an instructor not
    being able to attribute a comment.

    **The mutation it kills:** `ORDER BY answer.id` — or `ORDER BY submitted_at`,
    which is the timestamp as the order key in disguise, and the shape E4-04's own
    known traps name.
    **The near miss it tolerates:** *which* order any particular source gives,
    which nothing here pins and no implementation should have to reproduce.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_big_week(world, contract)

    orders: dict[int, tuple[str, ...]] = {}
    for seed in SEEDS:
        seeded(monkeypatch, contract, seed)
        orders[seed] = order_of(read_visible(world, contract))

    for seed, order in orders.items():
        assert len(order) == size, (
            f"Source {seed} answered {len(order)} comments and the week holds {size}: {order}. A "
            "shuffle that changes what is in the list is not a shuffle, and the order assertions "
            "below would be comparing different sets."
        )
    multisets = {seed: tuple(sorted(order)) for seed, order in orders.items()}
    assert len(set(multisets.values())) == 1, (
        f"Different random sources returned different *sets* of comments: {multisets}. The seam "
        "decides the order and nothing else — a source that changes which comments an instructor "
        "sees is a filter, not a shuffle."
    )

    assert len(set(orders.values())) > 1, (
        f"All {len(SEEDS)} sources returned the same order: {orders[A_SEED]}.\n\n"
        "SPEC §4: 'Comment display order is randomized.' An order that does not move with the "
        "random source is a stored order — the answer's key, the response's key, `submitted_at`, "
        "or the order rows happen to come back in — and every one of those is submission order, "
        "which says who answered first. E4-04's known traps put it as 'wherever ordering happens, "
        "the timestamp must not be the order key in disguise'."
    )


def test_the_visible_weeks_order_is_the_same_under_the_same_random_source(
    comment_world: CommentWorld, comment_contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other direction: the hook is the source, so it is reproducible.

    Without this, the variation asserted above is satisfied by a service that
    ignores `_make_rng` entirely and shuffles from the system source — which is a
    seam that does not exist, and which would leave nothing in this suite able to
    assert an order ever again.

    **The hook is re-patched between the two reads**, so each draws from a fresh
    generator of the same seed rather than from one that has moved. A service that
    consumed a shared generator and one that ignored it would otherwise be
    indistinguishable.

    **The mutation it kills:** `_make_rng` defined and never called — which is
    exactly what an implementation does when it reaches for `random.shuffle(...)`
    out of habit and leaves the hook as decoration.
    """
    contract = comment_contract
    world = comment_world
    plant_a_big_week(world, contract)

    seeded(monkeypatch, contract, A_SEED)
    first = order_of(read_visible(world, contract))
    seeded(monkeypatch, contract, A_SEED)
    second = order_of(read_visible(world, contract))

    assert first, (
        "The week returned no comments, so both orders compared here are empty and their agreement "
        "means nothing. `plant_a_big_week` asserts the week is at the threshold, so this is the "
        "read rather than the world."
    )
    assert first == second, (
        f"Two reads under a source seeded {A_SEED} answered {first} and {second}.\n\n"
        f"`{contract.rng_hook}` is the seam E4-04's work order settles so that 'the order is "
        "random' is a deterministic assertion. A service that ignores it and shuffles from the "
        "system source passes the variation test next door and makes every order in this suite "
        "unassertable."
    )


def test_an_unpatched_visible_read_still_shuffles(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Production patches nothing, so production must shuffle by itself.

    Twelve reads with `_make_rng` untouched. This is the half the seam cannot
    prove: a service that shuffled only when a test replaced its source would be
    green on both tests above and would ship a report whose comments arrive in
    submission order.

    **Not a probability worth reasoning about.** Six comments have 720 orders, and
    twelve genuine shuffles all landing on one of them is not a run this suite
    will see; a service that does not shuffle produces one order every time.

    **The mutation it kills:** the shuffle moved inside a branch that only fires
    when the source was replaced, and — the likelier shape — the shuffle deleted
    from the production path while `_make_rng` stays defined for the tests to
    find.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_big_week(world, contract)

    readings = [order_of(read_visible(world, contract)) for _ in range(UNPATCHED_READINGS)]
    assert all(len(order) == size for order in readings), (
        f"An unpatched read answered a different number of comments than the {size} the week "
        f"holds: {[len(order) for order in readings]}."
    )
    assert len(set(readings)) > 1, (
        f"{UNPATCHED_READINGS} unpatched reads of the same week returned the same order every "
        f"time: {readings[0]}.\n\n"
        "Nothing in production replaces the module's random source, so this is the order an "
        "instructor actually sees. SPEC §4 randomizes it, and an order that never changes is "
        "whatever the query returned — heap order, which is insertion order, which is who answered "
        "first."
    )


# ---------------------------------------------------------------------------
# The released batch, where a stored order is likeliest to survive.
# ---------------------------------------------------------------------------


def test_the_released_batchs_order_changes_with_the_random_source(
    comment_world: CommentWorld, comment_contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same rule on the release, read out of a table whose natural order is the cutter's.

    A released set comes from `release_batch_member`, and the obvious query returns
    it in whatever order the memberships were inserted — the order the cutter found
    the held comments in, which is the order they were submitted. SPEC §4 batches
    the release "so that timing cannot identify an author"; a batch whose members
    come back in submission order has kept the timing and moved it one table
    across.

    **The pair is the determinism test below**, for the reason the visible pair has
    one.

    **The mutation it kills:** the release read written with no `ORDER BY` and no
    shuffle, on the reasoning that a batch is already unordered — it is not, and a
    plain `SELECT` over an insertion-ordered heap usually returns it in insertion
    order.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_released_term(world, contract)

    orders: dict[int, tuple[str, ...]] = {}
    for seed in SEEDS:
        seeded(monkeypatch, contract, seed)
        orders[seed] = order_of(read_released(world, contract))

    for seed, order in orders.items():
        assert (
            len(order) == size
        ), f"Source {seed} answered {len(order)} released comments and {size} were held: {order}."

    assert len(set(orders.values())) > 1, (
        f"All {len(SEEDS)} sources returned the released batch in the same order: "
        f"{orders[A_SEED]}.\n\nSPEC §4 randomizes comment display order and batches the release so "
        "that timing cannot identify an author. A membership table read without a shuffle comes "
        "back in insertion order, which is the order the cutter walked the held comments in, which "
        "is the order they were submitted — the timing the batch exists to remove, one table "
        "across."
    )


def test_the_released_batchs_order_is_the_same_under_the_same_random_source(
    comment_world: CommentWorld, comment_contract: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The release's determinism half. See the visible read's, which is the same argument.

    **The mutation it kills:** `_make_rng` wired into `visible_comments` and not
    into `released_comments` — the asymmetry a single combined test would miss,
    since the two reads are two functions and a seam threaded through one of them
    is a seam missing from the other.
    """
    contract = comment_contract
    world = comment_world
    plant_a_released_term(world, contract)

    seeded(monkeypatch, contract, A_SEED)
    first = order_of(read_released(world, contract))
    seeded(monkeypatch, contract, A_SEED)
    second = order_of(read_released(world, contract))

    assert first, (
        "The release returned nothing, so both orders compared here are empty and their agreement "
        "means nothing."
    )
    assert first == second, (
        f"Two reads of the released batch under a source seeded {A_SEED} answered {first} and "
        f"{second}. `{contract.rng_hook}` is the source of the order or it is not the source."
    )


def test_an_unpatched_released_read_still_shuffles(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The release's production half. See the visible read's, which is the same argument.

    **The mutation it kills:** the release read left in the membership table's own
    order on the production path while the hook stays wired for the tests — which
    is the order the cutter walked the held comments in, and so the order they were
    submitted.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_released_term(world, contract)

    readings = [order_of(read_released(world, contract)) for _ in range(UNPATCHED_READINGS)]
    assert all(len(order) == size for order in readings), (
        f"An unpatched release read answered a different number of comments than the {size} held: "
        f"{[len(order) for order in readings]}."
    )
    assert len(set(readings)) > 1, (
        f"{UNPATCHED_READINGS} unpatched reads of the released batch returned the same order every "
        f"time: {readings[0]}. Nothing in production replaces the module's random source, so this "
        "is the order an instructor actually sees."
    )
