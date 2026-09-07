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

So the work order gives both reads an `rng` seam: `rng: random.Random | None`,
defaulting to a system source. That is what makes "the order is random" a
deterministic assertion rather than a coin toss, and it is the only interface in
this ticket that exists for the tests — which is stated plainly rather than
dressed up, because a seam nobody names is a seam somebody deletes.

**Two properties, and they are opposite in direction:**

  - **different seeds give different orders.** This is the one that kills a
    stored order: `ORDER BY answer.id`, `ORDER BY submitted_at`, or no `ORDER BY`
    at all in a query that happens to come back sorted. None of those changes when
    the seed does.
  - **the same seed gives the same order.** Without this the first property is
    satisfied by a service that ignores the seam and shuffles from the system
    source, which is a seam that does not exist and a suite that cannot ever
    assert an order again.

**Neither property is a probability.** The first is asserted over eight distinct
seeds and requires at least two distinct orders among them, so a service that
shuffles genuinely fails it with probability `8!^-7`-ish rather than one in a
handful — and a service that ignores the seed fails it every time.

**And the multiset is asserted unchanged.** A "shuffle" that dropped or duplicated
a comment would satisfy the order assertions and change what the instructor
reads.
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
# and eight seeds all landing on one of them is not a failure mode a suite has to
# reason about. Six is also enough that a service returning "the first three" is
# visibly wrong.
COMMENTS_IN_THE_BIG_WEEK = 6

# The seeds the orders are read under. Eight distinct integers, so that "at least
# two of these orders differ" is a claim about the seam rather than about luck,
# and `A_SEED` is one of them so the determinism half and the variation half are
# talking about the same source.
SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
A_SEED = SEEDS[0]

A_COMMENT = "the tutorial exercises were pitched about right and the marking was quick"


def a_week_of(count: int, week: int) -> list[str]:
    """`count` distinct comment texts for one week.

    Distinct because an order is read as a sequence of texts: two identical
    comments make two different orders compare equal, which is the one thing that
    would make the variation assertion below unfalsifiable.
    """
    return [f"{A_COMMENT} (week {week}, response {index + 1})" for index in range(count)]


def order_of(comments: Any) -> tuple[str, ...]:
    """The texts a read answered with, in the order it answered them."""
    return tuple(str(comment.text) for comment in comments)


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
    """Held comments across three closed under-threshold weeks, crossed and cut."""
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
        f"`{contract.cut_name}` cut {cut} batches, so there is no release to shuffle and every "
        "order compared below would be the empty tuple."
    )
    return size


def read_visible(world: CommentWorld, contract: Any, *, rng: Any) -> Any:
    """The big week's comments, read with the rng the caller chose."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(BIG_WEEK),
        stream=contract.instructor_stream,
        rng=rng,
    )


def read_released(world: CommentWorld, contract: Any, *, rng: Any) -> Any:
    """The term's released comments, read with the rng the caller chose."""
    return contract.released()(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=contract.instructor_stream,
        rng=rng,
    )


def test_the_visible_weeks_order_changes_with_the_seed(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """SPEC §4's randomized display order, asserted where a stored order would show.

    Eight seeds over one week's comments. A service that ordered by anything the
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
    known traps name. **The near miss it tolerates:** *which* order any particular
    seed gives, which nothing here pins and no implementation should have to
    reproduce.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_big_week(world, contract)

    orders = {
        seed: order_of(read_visible(world, contract, rng=random.Random(seed)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography
        for seed in SEEDS
    }

    for seed, order in orders.items():
        assert len(order) == size, (
            f"Seed {seed} answered {len(order)} comments and the week holds {size}: {order}. A "
            "shuffle that changes what is in the list is not a shuffle, and the order assertions "
            "below would be comparing different sets."
        )
    multisets = {seed: tuple(sorted(order)) for seed, order in orders.items()}
    assert len(set(multisets.values())) == 1, (
        f"Different seeds returned different *sets* of comments: {multisets}. The seam decides the "
        "order and nothing else — a seed that changes which comments an instructor sees is a "
        "filter, not a shuffle."
    )

    distinct = set(orders.values())
    assert len(distinct) > 1, (
        f"All {len(SEEDS)} seeds returned the same order: {orders[A_SEED]}.\n\n"
        "SPEC §4: 'Comment display order is randomized.' An order that does not move with the "
        "random source is a stored order — the answer's key, the response's key, `submitted_at`, "
        "or the order rows happen to come back in — and every one of those is submission order, "
        "which says who answered first. E4-04's known traps put it as 'wherever ordering happens, "
        "the timestamp must not be the order key in disguise'."
    )


def test_the_visible_weeks_order_is_the_same_under_the_same_seed(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The other direction: the seam is the source, so it is reproducible.

    Without this, the variation asserted above is satisfied by a service that
    ignores `rng` entirely and shuffles from the system source — which is a seam
    that does not exist, and which would leave nothing in this suite able to
    assert an order ever again.

    **Two fresh `random.Random` instances of the same seed**, not one instance
    used twice: a service that consumed the caller's generator and a service that
    ignored it would be indistinguishable if the same object were passed both
    times, because the second call would then draw from a moved state.

    **The mutation it kills:** the `rng` parameter accepted and never used, which
    is exactly what an implementation does when it reaches for
    `random.shuffle(...)` out of habit.
    """
    contract = comment_contract
    world = comment_world
    plant_a_big_week(world, contract)

    first = order_of(read_visible(world, contract, rng=random.Random(A_SEED)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography
    second = order_of(read_visible(world, contract, rng=random.Random(A_SEED)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography

    assert first, (
        "The week returned no comments, so both orders compared here are empty and their agreement "
        "means nothing. `plant_a_big_week` asserts the week is at the threshold, so this is the "
        "read rather than the world."
    )
    assert first == second, (
        f"Two reads seeded {A_SEED} answered {first} and {second}.\n\n"
        "The `rng` parameter is the seam E4-04's work order settles so that 'the order is random' "
        "is a deterministic assertion. A service that ignores it and shuffles from the system "
        "source passes the variation test next door and makes every order in this suite "
        "unassertable — including the one an eval or a screenshot would ever pin."
    )


def test_the_released_batchs_order_changes_with_the_seed(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The same rule on the release, which is where a stored order is likeliest to survive.

    A released set is read out of `release_batch_member`, and the obvious query
    returns it in whatever order the memberships were inserted — which is the
    order the cutter found the comments in, which is the order they were
    submitted. SPEC §4 batches the release "so that timing cannot identify an
    author"; a batch whose members come back in submission order has kept the
    timing and moved it one table across.

    **The pair is the determinism test below**, for the reason the visible pair
    has one.

    **The mutation it kills:** the release read written with no `ORDER BY` and no
    shuffle, on the reasoning that the batch is already unordered — it is not, and
    a plain `SELECT` over a table with an insertion-ordered heap usually returns
    it in insertion order.
    """
    contract = comment_contract
    world = comment_world
    size = plant_a_released_term(world, contract)

    orders = {
        seed: order_of(read_released(world, contract, rng=random.Random(seed)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography
        for seed in SEEDS
    }
    for seed, order in orders.items():
        assert (
            len(order) == size
        ), f"Seed {seed} answered {len(order)} released comments and {size} were held: {order}."

    distinct = set(orders.values())
    assert len(distinct) > 1, (
        f"All {len(SEEDS)} seeds returned the released batch in the same order: {orders[A_SEED]}.\n"
        "\nSPEC §4 randomizes comment display order and batches the release so that timing cannot "
        "identify an author. A membership table read without a shuffle comes back in insertion "
        "order, which is the order the cutter walked the held comments in, which is the order they "
        "were submitted — the timing the batch exists to remove, one table across."
    )


def test_the_released_batchs_order_is_the_same_under_the_same_seed(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The release's determinism half. See the visible read's, which is the same argument.

    **The mutation it kills:** `rng` accepted by `released_comments` and passed
    nowhere, which is the asymmetry a single combined test would miss — the two
    reads are two functions, and a seam wired into one of them is a seam missing
    from the other.
    """
    contract = comment_contract
    world = comment_world
    plant_a_released_term(world, contract)

    first = order_of(read_released(world, contract, rng=random.Random(A_SEED)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography
    second = order_of(read_released(world, contract, rng=random.Random(A_SEED)))  # noqa: S311 — the rng seam under test wants determinism, not cryptography

    assert first, (
        "The release returned nothing, so both orders compared here are empty and their agreement "
        "means nothing."
    )
    assert first == second, (
        f"Two reads of the released batch seeded {A_SEED} answered {first} and {second}. The seam "
        "is the source of the order or it is not a seam."
    )
