"""A set name that differs from another only in case or spacing is the same name — E9-05.

> 13. **Near-duplicate names are refused.** Creating "nursing  core" when
>     "Nursing core" exists answers the governed refusal sentence (a route
>     test); renaming a set to a near-duplicate is refused the same way; a name
>     that differs in a letter is accepted. …

E9-05's interface: a unique index on `lower(btrim(regexp_replace(name, '\\s+',
' ', 'g')))`, `uq_comparison_set_normalized_name`, mapped by the service's
constraint translation to the same 409 and the same sentence as the existing
`UNIQUE (name)` — `NAME_ALREADY_USED`, reworded to "Another comparison set
already uses this name, or the same name with different capitals or spacing,
and a set is named once."

**Both layers are asserted.** The route answers the sentence; and the database
refuses the near-duplicate row when it is inserted directly, so a check made only
in Python is red (`docs/MISTAKES.md` entry 13: one rule, every place that asks).
Every refusal sits beside an accepted twin that differs in one letter
(`docs/MISTAKES.md` entry 3), and a set renamed to a variant of *its own* name is
accepted — the index compares a row with the others, never with itself.

**Which failure a red is, before E9-05 lands:** the near-duplicates are created
or renamed with 201 or 200 and each refusal test FAILS on its status; the
sentence test FAILS on the old wording; the database test FAILS on the insert
being accepted.
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    assert_refused_for_the_data,
    refusal_of,
    write_set,
)
from fixtures.named_sets import NAME_ALREADY_USED, NamedSetDoor, refusal_sentence

pytestmark = pytest.mark.integration

THE_NAME = "Nursing core"

# The interface's reworded sentence, transcribed here as the route test's pin.
REWORDED = (
    "Another comparison set already uses this name, or the same name with different capitals or "
    "spacing, and a set is named once."
)

# Each differs from `THE_NAME` only in case or in spacing, which the normalized
# name (trimmed, inner whitespace collapsed to one space, case-folded) erases.
NEAR_DUPLICATES = (
    pytest.param("nursing  core", id="lower-case-and-a-double-space"),
    pytest.param("NURSING CORE", id="capitals"),
    pytest.param("Nursing\tcore", id="a-tab-for-the-space"),
    pytest.param("Nursing   Core", id="three-spaces-and-a-capital"),
)

# One letter away: a different name, which must be accepted.
ONE_LETTER_AWAY = "Nursing cores"


def create_the_name(door: NamedSetDoor) -> None:
    """`THE_NAME`, created through the route, and required to be (the premise of every test)."""
    answered = door.create(door.world.a_write(name=THE_NAME))
    assert answered.status_code == 201, (
        f"Creating a set named {THE_NAME!r} answered {answered.status_code}: "
        f"{answered.text[:400]!r}. A broken world, not a red: every refusal below is about this "
        "name being taken."
    )


def stored_names(door: NamedSetDoor, contract: Any) -> list[str]:
    return [row[contract.name_field] for row in door.world.set_rows()]


def test_the_name_refusal_sentence_names_capitals_and_spacing() -> None:
    """The reworded `NAME_ALREADY_USED`, read out of `app.copy`.

    **The mutation this kills:** the old sentence kept, which tells a reader who
    typed "nursing  core" that the name is taken while showing her a list in
    which no set carries it.
    """
    assert refusal_sentence(NAME_ALREADY_USED) == REWORDED, (
        f"`{NAME_ALREADY_USED}` reads {refusal_sentence(NAME_ALREADY_USED)!r}; E9-05's interface "
        f"rewords it to {REWORDED!r}."
    )


@pytest.mark.parametrize("variant", NEAR_DUPLICATES)
def test_creating_a_near_duplicate_name_is_refused_with_the_governed_sentence(
    named_sets: NamedSetDoor, named_set_contract: Any, variant: str
) -> None:
    """A create naming `variant` while `THE_NAME` exists: 409 and the sentence, nothing stored.

    **The mutations this kill:** the index over `lower(name)` alone (the
    spacing variants pass); over `btrim(name)` without collapsing inner spaces
    (the double space passes); the index created and the service's translation
    not taught its name (a 500, not a 409). **The near miss:**
    `test_a_name_one_letter_away_is_accepted`.
    """
    create_the_name(named_sets)
    before = stored_names(named_sets, named_set_contract)

    answered = named_sets.create(named_sets.world.a_write(name=variant))

    assert answered.status_code == named_set_contract.duplicate_name, (
        f"Creating a set named {variant!r} while {THE_NAME!r} exists answered "
        f"{answered.status_code}: {answered.text[:400]!r}. The two differ only in case or spacing "
        "and are one name (E9-05 done-when 13)."
    )
    assert named_set_contract.detail_of(answered) == refusal_sentence(NAME_ALREADY_USED)
    assert (
        stored_names(named_sets, named_set_contract) == before
    ), f"The refused create stored a row: {stored_names(named_sets, named_set_contract)}."


@pytest.mark.parametrize("variant", NEAR_DUPLICATES)
def test_renaming_a_set_to_a_near_duplicate_name_is_refused_the_same_way(
    named_sets: NamedSetDoor, named_set_contract: Any, variant: str
) -> None:
    """An edit renaming this leader's set to `variant`: the same 409 and sentence, the set unmoved.

    **The mutation this kills:** the normalized check made in the create path
    only.
    """
    create_the_name(named_sets)
    world = named_sets.world
    hers = world.hers
    assert hers is not None
    before = world.set_row(hers.set_id)

    answered = named_sets.edit(hers.set_id, world.a_write(name=variant))

    assert answered.status_code == named_set_contract.duplicate_name, (
        f"Renaming a set to {variant!r} while {THE_NAME!r} exists answered "
        f"{answered.status_code}: {answered.text[:400]!r}."
    )
    assert named_set_contract.detail_of(answered) == refusal_sentence(NAME_ALREADY_USED)
    assert world.set_row(hers.set_id) == before, "The refused rename changed the set anyway."


def test_a_name_one_letter_away_is_accepted(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The accepted twin: "Nursing cores" is another name, created 201.

    **The mutation this kills:** a normalization that strips more than case and
    spacing (a trailing `s`, punctuation), or an index over a prefix.
    """
    create_the_name(named_sets)

    answered = named_sets.create(named_sets.world.a_write(name=ONE_LETTER_AWAY))

    assert answered.status_code == named_set_contract.created, (
        f"Creating {ONE_LETTER_AWAY!r} beside {THE_NAME!r} answered {answered.status_code}: "
        f"{answered.text[:400]!r}. They differ in a letter and are two names."
    )


def test_a_set_renamed_to_a_variant_of_its_own_name_is_accepted(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Renaming a set to its own name in other capitals is not a collision with itself.

    **The mutation this kills:** a check written as "does any row carry this
    normalized name" without excluding the row being edited, which refuses a
    leader fixing the capitals of her own set's name.
    """
    world = named_sets.world
    hers = world.hers
    assert hers is not None

    answered = named_sets.edit(hers.set_id, world.a_write(name=hers.name.upper()))

    assert answered.status_code == named_set_contract.list_ok, (
        f"Renaming a set to {hers.name.upper()!r}, its own name in capitals, answered "
        f"{answered.status_code}: {answered.text[:400]!r}."
    )


def test_the_database_refuses_a_near_duplicate_row_inserted_directly(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The index, not the route: an insert of "nursing  core" beside "Nursing core" is refused.

    **The control:** "Nursing cores" inserts beside it in the same transaction.

    **The mutation this kills:** the rule held in the service or the route only
    (a `SELECT` before the insert), which every other writer — the seed, a
    script, a race — walks past. **Expected red before E9-05 lands:** the
    near-duplicate is accepted.
    """
    first = refusal_of(
        db_session, lambda: write_set(seed_rows, length=6, level="UG", name=THE_NAME)
    )
    assert first is None, f"The first set named {THE_NAME!r} was refused: {first}."
    twin = refusal_of(
        db_session, lambda: write_set(seed_rows, length=6, level="UG", name=ONE_LETTER_AWAY)
    )
    assert twin is None, f"{ONE_LETTER_AWAY!r} was refused beside {THE_NAME!r}: {twin}."

    near = refusal_of(
        db_session, lambda: write_set(seed_rows, length=6, level="UG", name="nursing  core")
    )
    assert_refused_for_the_data(
        near,
        f"A set named 'nursing  core' beside {THE_NAME!r}",
        "E9-05's unique index on the normalized name refuses a name that differs only in case or "
        "spacing, at the database, for every writer.",
    )
