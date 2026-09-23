"""A set name of only spaces is refused at the wire; one with spaces around it is trimmed.

E5-14.

E5-14's blank-name ruling, as the orchestrator gave it: the request schema strips
the name and refuses one that is empty after stripping (`min_length=1` on the
stripped name), so the route answers the framework's standard 422 for a
malformed body — never a 500 — and no new copy is added. Beneath it the table
now carries `CHECK (btrim(name) <> '')`, asserted in
`test_a_comparison_set_declares_one_length_and_one_level.py`; this module is the
route's half, which the table rule alone does not give: a `CHECK` violation the
translator has no sentence for surfaces as a 500.

**A pair per writing route, both directions.** The refused body is a name of
only spaces; its near-miss twin is a real name with spaces around it, which is
accepted and **stored trimmed**. A route that refused every name with a space in
it, or that stored the untrimmed name, fails the twin.

**The layer is pinned, not just the status.** A 422 is answered by the
framework's body validation and by the service's translated constraint
refusals alike; the two differ in the body. The ruling makes this one the
framework's, so the body's `detail` is required to be the framework's list of
field errors, one of them located at `name`.

**Nothing may be stored by the refusal**: the set count and, on an edit, the set
row are read back after it.

**Which failure a red is on d1e7dd8:** the blank cases answer 500 (the `CHECK`
fires and nothing translates it), so they fail on the status; the twins pass.
"""

from typing import Any

import pytest
from fixtures.named_sets import NamedSetDoor

pytestmark = pytest.mark.integration

WRITING_ROUTES = ("create", "edit")

ONLY_SPACES = "   "
PADDED_NAME = "  Nursing  "
TRIMMED_NAME = "Nursing"

# FastAPI's validation body: `{"detail": [{"loc": [...], "msg": ..., ...}, ...]}`.
DETAIL = "detail"
LOCATION = "loc"


def write(door: NamedSetDoor, route: str, body: Any) -> Any:
    """One `POST` of `body`, or one `PUT` of it over the set this session defined."""
    if route == "create":
        return door.create(body)
    return door.edit(door.world.hers.set_id, body)


@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_a_name_of_only_spaces_is_refused_as_a_malformed_body_and_stores_nothing(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """The blank name: 422 from body validation, located at `name`, and nothing stored.

    **The mutations it kills:** the request schema left unstripped or without a
    minimum length, so the `CHECK` fires in the database and the route answers
    500; and a strip applied after validation rather than before it, which
    passes `"   "` through as a three-character name.

    **Its near miss** is the twin below: a real name with spaces around it.
    """
    world = named_sets.world
    before = world.set_rows()
    hers_before = world.set_row(world.hers.set_id)

    answered = write(named_sets, route, world.a_write(name=ONLY_SPACES))

    assert answered.status_code == named_set_contract.refused_value, (
        f"A `{route}` naming the set {ONLY_SPACES!r} answered {answered.status_code} rather than "
        f"{named_set_contract.refused_value}. Body begins {answered.text[:400]!r}.\n\n"
        "E5-14's ruling: the request schema strips the name and refuses one empty after "
        "stripping, so this is the framework's standard 422 for a malformed body. A 500 is the "
        "table's `CHECK (btrim(name) <> '')` firing with nothing above it to refuse the body first."
    )
    detail = answered.json().get(DETAIL)
    field = named_set_contract.name_field
    entries = detail if isinstance(detail, list) else []
    located = [
        entry
        for entry in entries
        if isinstance(entry, dict) and field in (entry.get(LOCATION) or [])
    ]
    assert located, (
        f"The 422 carries `detail` {detail!r}, which is not the framework's list of field errors "
        f"with one located at `{named_set_contract.name_field}`. The ruling makes this refusal the "
        "request schema's, with no new copy — a one-sentence `detail` here is a translated "
        "database refusal, which is a different layer answering."
    )

    after = world.set_rows()
    assert len(after) == len(
        before
    ), f"The refused `{route}` left {len(after)} sets where there were {len(before)}."
    if route == "edit":
        assert world.set_row(world.hers.set_id) == hers_before, (
            f"The refused edit changed the set anyway.\n  before: {hers_before}\n  after:  "
            f"{world.set_row(world.hers.set_id)}"
        )


@pytest.mark.parametrize("route", WRITING_ROUTES, ids=WRITING_ROUTES)
def test_a_name_with_spaces_around_it_is_accepted_and_stored_trimmed(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """The twin: `"  Nursing  "` is a name, and it is stored as `"Nursing"`.

    Without it the refusal above is satisfied by a route refusing every name
    that carries a space (`docs/MISTAKES.md` entry 3).

    **The mutations it kills:** a validator refusing surrounding spaces instead of
    stripping them; and a strip applied to the check but not to the value stored,
    which leaves `"  Nursing  "` and `"Nursing"` as two sets a leader cannot tell
    apart in a list.
    """
    world = named_sets.world
    expected = named_set_contract.created if route == "create" else named_set_contract.list_ok

    answered = write(named_sets, route, world.a_write(name=PADDED_NAME))

    assert answered.status_code == expected, (
        f"A `{route}` naming the set {PADDED_NAME!r} answered {answered.status_code} rather than "
        f"{expected}. Body begins {answered.text[:400]!r}. The name is not blank once stripped, "
        "so the ruling accepts it."
    )
    names = [row[named_set_contract.name_field] for row in world.set_rows()]
    assert TRIMMED_NAME in names and PADDED_NAME not in names, (
        f"After the `{route}` the sets are named {names}. The ruling strips the name before it is "
        f"validated and stored, so {PADDED_NAME!r} is stored as {TRIMMED_NAME!r}."
    )
