"""The published key set during a rotation — E3-01, criteria 2, 3 and 4.

> A key rotation needs a period in which the published key set carries both the
> retiring key and its replacement, so that assertions signed before the switch
> still verify while assertions signed after it verify too.

That sentence is the whole of this module. ADR 0085 gave the tool a JWKS route
publishing one key, because ADR 0082 stored one and forbade rotation; E3-01
widens the rule — every row with `retired_at IS NULL` is published, retirement
takes a key out of the set immediately, and the row stays behind as a record.

**What is planted, and why it is planted rather than seeded or generated.** Every
test here writes its own `tool_signing_key` rows and holds the private half of
each. The route's job is to publish the public half of *the rows that are there*,
and a key this suite did not choose could not tell that apart from a key the route
made up (`docs/MISTAKES.md` entry 30). Retirement is planted for the reason
criterion 3 spells out — "the test plants that case rather than reasoning about
it": a signature is really made with the key that is really retired, and really
offered to the key set afterwards.

**Every boundary here is asserted in both directions.** A retired key leaves the
set **and** the unretired one is still in it. A signature by either live key
verifies **and** a signature by the retired key is refused. No usable row answers
503 **and** one usable row answers 200. Only one of each pair is the finding; the
other is what keeps the finding from being a statement about an empty key set or a
broken route.

**Every guard here is called from a test body and none from a fixture**, and that
is a repair rather than a preference. The first version of this module put the
"is the table empty" and "can the schema rotate" guards into a shared fixture,
along with the planting that depends on them — so on a tree without the rotation
columns all six tests reported as an ERROR in setup instead of failing on their
own criterion, and the one test whose subject is the refusal's wording never
reached its own assertion at all. An error is not a red: it says the test could
not run, where a red says the system is wrong. The two guards are separate
functions now because they are needed in different amounts — the refusal test
plants nothing and must not be stopped by a column it never touches.

**Two things are deliberately not here.** A published key's shape, its `kid`
arithmetic, its base64url spelling and the absence of private members are
`tests/integration/test_the_tool_publishes_its_key_set.py`'s, per key, and are not
repeated. And the *signer's* choice among the published keys is
`tests/integration/test_the_signer_selects_the_newest_live_key.py`'s: what a key
set carries and what signs with it are two properties, and a route can be right
about one while the signer is wrong about the other.
"""

import json
from datetime import UTC, datetime
from typing import Any, NamedTuple

import pytest
from fixtures.signing_key_tool import (
    CREATED_AT_COLUMN,
    PRIVATE_KEY_COLUMN,
    RETIRED_AT_COLUMN,
    SIGNING_KEYS,
    any_key_verifies,
    generated_pem,
    kid_of_pem,
    public_jwk_of,
    require_rotation_columns,
    signature_by,
    verifies,
)

pytestmark = pytest.mark.integration

# The route, spelled as ADR 0085 fixes it and as
# `tests/integration/test_the_tool_publishes_its_key_set.py` spells it. A public
# URL a platform is registered with, so a spelling that can move is a spelling
# that changes under whoever already stored it.
TOOL_JWKS_PATH = "/lti/jwks"

# What the route answers where this deployment holds no *usable* key. 503, as ADR
# 0085 decided and E3-01 criterion 4 keeps: the route exists and this installation
# is not ready to serve it. Asserted as an equality, so a 500 fails — an unhandled
# exception is not a decision, and the next refactor of one could as easily answer
# 200.
NO_USABLE_KEY_STATUS = 503

# Two instants an hour apart, and one for a retirement, all aware as ADR 0019
# requires. Written out so that "the newer key" is a fact about the rows rather
# than about the order this module happened to insert them.
OLDER_CREATED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
NEWER_CREATED_AT = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
RETIRED_AT = datetime(2026, 9, 2, 11, 0, tzinfo=UTC)

# What a platform signs is an assertion; these tests sign byte strings, because
# the property under test is which key a verifier holding this document can check
# a signature with, and nothing about that is JWT-shaped.
BEFORE_THE_SWITCH = b"e3-01: signed while the retiring key was still published"
AFTER_THE_SWITCH = b"e3-01: signed by the replacement key"

# The supply path a refusal has to send an operator to. **The name, not a
# sentence**: E3-01's work order settles the path as `scripts/signing_key.py`, and
# criterion 4 asks the refusal to carry "an actionable sentence" — a body naming
# nothing runnable is one the person reading it can only escalate.
THE_SUPPLY_PATH = "signing_key"


class Rotation(NamedTuple):
    """The two private keys a rotation-in-progress has planted, oldest first."""

    older: str
    newer: str


def plant_key(rows: Any, **values: Any) -> str:
    """One `tool_signing_key` row this test chose every value of, committed.

    Committed because the route opens its own connection as the application role
    and sees nothing that has not been. The PEM is handed back so the caller holds
    the private half of what it planted, which is what lets this module make a
    signature "by that key" at all.
    """
    pem = generated_pem()
    rows.seed(SIGNING_KEYS, {}, **{PRIVATE_KEY_COLUMN: pem, **values})
    rows.commit()
    return pem


def key_set(client: Any) -> dict[str, Any]:
    """`GET /lti/jwks`, as a JWK Set, or a failure naming what answered instead."""
    response = client.get(TOOL_JWKS_PATH)
    assert response.status_code == 200, (
        f"`GET {TOOL_JWKS_PATH}` answered {response.status_code} rather than 200 with usable keys "
        f"stored. A 500 here is most likely the `SELECT` grant on `{SIGNING_KEYS}`; "
        "`tests/integration/test_the_tool_publishes_its_key_set.py` is where the route's own "
        f"failures are diagnosed. Body begins {response.text[:300]!r}."
    )
    document = response.json()
    assert isinstance(document, dict), (
        f"`GET {TOOL_JWKS_PATH}` served {document!r}, which is not a JWK Set. RFC 7517 §5 makes a "
        "key set a JSON object with a `keys` member."
    )
    keys = document.get("keys")
    assert isinstance(keys, list), (
        f"The published key set carries `keys` {keys!r} rather than a JSON array of JWK values, "
        "which is a document no platform's key-set reader accepts."
    )
    return document


def published_kids(document: dict[str, Any]) -> set[str]:
    """The `kid` of every key in a served set."""
    return {str(key.get("kid")) for key in document["keys"] if isinstance(key, dict)}


@pytest.fixture
def open_the_tool(tool_doors: Any, door_contract: Any) -> Any:
    """Build the application against this container, the way every door suite does."""

    def build() -> Any:
        return tool_doors(
            {door_contract.settings["public_base_url"]: door_contract.public_base_url}
        )

    return build


def require_an_empty_table(rows: Any, tables: dict[str, Any]) -> None:
    """Stop unless the key table starts with nothing in it.

    A row left behind by another test would make "the set carries what this test
    planted" a statement about somebody else's key (`docs/MISTAKES.md` entry 3).

    **Called from a test body and never from a fixture**, which is the rule the
    whole ticket's tests are held to: a guard that fires in setup reports as an
    ERROR, and an error is not a red. The first version of this module wired this
    and the guard below into a shared fixture, and every test in the file reported
    as an error at setup instead of failing on its own criterion — including the
    one whose subject is the refusal's wording, which never reached its own
    assertion at all.
    """
    held = rows.session.execute(tables[SIGNING_KEYS].select()).mappings().all()
    assert not held, (
        f"`{SIGNING_KEYS}` already holds {len(held)} row(s) before this test plants any. Nothing "
        "in the session database's fixtures seeds a signing key and `committed_rows` removes what "
        "a test plants, so this is a leak to chase rather than an assertion to relax — and every "
        "published-set comparison below would be about a key nobody here chose."
    )


def require_a_rotatable_table(rows: Any, tables: dict[str, Any]) -> None:
    """The empty-table guard, and the two columns a planted rotation needs.

    The second half is separate from the first because one test in this module —
    the refusal's wording — plants nothing and therefore needs no rotation
    columns; its subject is reachable on today's schema and it must get there.
    Everywhere else, a schema with no `retired_at` cannot express what is being
    planted, and without this the seeding helper raises from inside itself with
    an `UndefinedColumn` that reads as a broken test rather than as the missing
    deliverable (`docs/MISTAKES.md` entry 22).
    """
    require_an_empty_table(rows, tables)
    require_rotation_columns(tables[SIGNING_KEYS].c.keys(), "the declared table")


def a_rotation_in_progress(rows: Any, tables: dict[str, Any]) -> Rotation:
    """A rotation in progress: the retiring key and its replacement, both published.

    The state the ticket's context paragraph describes and the state the one-row
    rule made unreachable. The rows differ in `created_at` by an hour, so "the
    newer key" is a property of the rows rather than of the insert order.

    A plain function rather than a fixture, for the reason `require_an_empty_table`
    gives: the planting cannot happen on a schema without the rotation columns, so
    a fixture doing it would turn every red in this module into a setup error.
    """
    require_a_rotatable_table(rows, tables)
    older = plant_key(rows, **{CREATED_AT_COLUMN: OLDER_CREATED_AT, RETIRED_AT_COLUMN: None})
    newer = plant_key(rows, **{CREATED_AT_COLUMN: NEWER_CREATED_AT, RETIRED_AT_COLUMN: None})
    return Rotation(older=older, newer=newer)


# ---------------------------------------------------------------------------
# Criterion 2 — two keys at once, and a signature by either verifies.
# ---------------------------------------------------------------------------


def test_the_published_key_set_carries_both_keys_of_a_rotation(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """Criterion 2, first half: "the published key set can carry two keys at once".

    **The mutation this kills, and it is the state at HEAD:** a route that reads
    one row — `.one()`, `.first()`, `LIMIT 1` — and publishes a set of one. That
    route is correct under ADR 0082's one-row rule and wrong the moment a second
    row exists, and its failure is entirely at the platform: whichever key it did
    not publish signed assertions nobody can verify.

    **The near miss it must survive:** a route that publishes *some* two keys, or
    the same key twice. Both planted keys are compared by `kid`, so a set of the
    right size holding the wrong members fails here.

    **An equality, not a subset.** A published set carrying a key this deployment
    does not hold is worse than one missing a key: a platform will accept an
    assertion signed by anything in the document it stored.
    """
    rotation = a_rotation_in_progress(committed_rows, metadata_tables)

    document = key_set(open_the_tool())

    expected = {kid_of_pem(rotation.older), kid_of_pem(rotation.newer)}
    assert published_kids(document) == expected, (
        f"The tool published {sorted(published_kids(document))} where this deployment holds two "
        f"live keys, {sorted(expected)}. One key is ADR 0082's one-row read surviving the rule "
        "change, and it makes rotation impossible: whichever key is left out signed assertions "
        "that now verify nowhere. A key that is published and not stored is worse — a platform "
        f"accepts an assertion signed by anything the document it stored carries. Served: "
        f"{json.dumps(document)[:400]}"
    )


def test_a_signature_by_either_key_of_a_rotation_verifies_against_the_published_set(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """Criterion 2, second half: "a signature made with either verifies against it".

    The criterion says in as many words that both directions are asserted and not
    one, and this is why: the overlap exists so that **assertions signed before the
    switch still verify while assertions signed after it verify too**. A key set
    that verifies only the replacement fails everything already in flight; one that
    verifies only the retiring key fails everything signed from the switch onwards.
    Both failures land at the platform, hours later, as a refused signature naming
    no key.

    **Verified rather than compared.** The test above says the right `kid`s are
    published; this says the numbers under them are usable for the operation they
    exist for. A modulus written big-endian the wrong way round survives a `kid`
    comparison and fails here.

    **The near miss it must survive**, and the reason the last assertion is not
    dropped as obvious: a verifier that accepts everything. So a signature by a key
    this deployment never held is offered to the same set, through the same helper,
    and has to be refused.
    """
    rotation = a_rotation_in_progress(committed_rows, metadata_tables)

    keys = key_set(open_the_tool())["keys"]

    older_signature = signature_by(rotation.older, BEFORE_THE_SWITCH)
    assert any_key_verifies(keys, older_signature, BEFORE_THE_SWITCH), (
        "The published key set verifies nothing signed by the retiring key. That is the half of "
        "the overlap the rotation exists for: every assertion signed before the switch is refused "
        "from this moment, at the platform, with an error that names no key."
    )
    newer_signature = signature_by(rotation.newer, AFTER_THE_SWITCH)
    assert any_key_verifies(keys, newer_signature, AFTER_THE_SWITCH), (
        "The published key set verifies nothing signed by the replacement key. Then the rotation "
        "can never complete: the moment the retiring key goes, this deployment signs with a key no "
        "platform can check."
    )

    stranger = signature_by(generated_pem(), AFTER_THE_SWITCH)
    assert not any_key_verifies(keys, stranger, AFTER_THE_SWITCH), (
        "A signature by a key this deployment has never held verifies against the published set, "
        "so the two assertions above are true of a verifier that accepts everything and say "
        "nothing about either planted key."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — the retired key is refused, and the other one is not.
# ---------------------------------------------------------------------------


def test_a_retired_keys_signature_is_refused_while_the_remaining_key_still_verifies(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """Criterion 3: the case is planted — a real signature, by the key really retired.

    The signature is made **before** the retirement, with the key that is about to
    be retired, and offered to the key set **after** it. That ordering is the
    criterion's "plants that case rather than reasoning about it": a test that
    retired a key and then asserted its absence from the document would be making
    a claim about a list, and would pass over a route that had stopped publishing
    anything at all.

    **The mutations this kills:** a route that ignores `retired_at` and publishes
    every stored row, which is the shape a `SELECT *` takes and which means
    retirement changes nothing a platform can see; and a retirement written as a
    column nothing reads.

    **Both directions, and the second is what makes the first mean anything.** The
    remaining key has to go on verifying what it signed. Without that assertion,
    "the retired key's signature is refused" is satisfied by an empty key set, by a
    503, and by a route publishing a key nothing here holds — none of which is
    retirement working (`docs/MISTAKES.md` entry 3).

    **The row is not deleted**, and that is asserted too: E3-01 keeps a retired key
    as a record and takes it out of the published set. Deleting it is a different
    decision and leaves no answer to what this deployment used to sign with.
    """
    rotation = a_rotation_in_progress(committed_rows, metadata_tables)
    signed_before = signature_by(rotation.older, BEFORE_THE_SWITCH)
    still_signing = signature_by(rotation.newer, AFTER_THE_SWITCH)
    keys_before = key_set(open_the_tool())["keys"]
    assert any_key_verifies(keys_before, signed_before, BEFORE_THE_SWITCH), (
        "The key about to be retired does not verify its own signature against the set published "
        "*before* the retirement, so nothing below can be attributed to retiring it. "
        "`test_a_signature_by_either_key_of_a_rotation_verifies_against_the_published_set` owns "
        "that failure."
    )

    retired_kid = kid_of_pem(rotation.older)
    table = metadata_tables[SIGNING_KEYS]
    committed_rows.session.execute(
        table.update()
        .where(table.c[PRIVATE_KEY_COLUMN] == rotation.older)
        .values(**{RETIRED_AT_COLUMN: RETIRED_AT})
    )
    committed_rows.commit()

    document = key_set(open_the_tool())
    keys_after = document["keys"]

    assert published_kids(document) == {kid_of_pem(rotation.newer)}, (
        f"After retiring {retired_kid} the tool publishes {sorted(published_kids(document))}. The "
        "retired key leaving the set is the whole of what retirement does — the key stays in the "
        "database as a record and stops being something a platform will verify against — and a set "
        "that still carries it is the stale key living forever that this ticket names as a trap."
    )
    assert not any_key_verifies(keys_after, signed_before, BEFORE_THE_SWITCH), (
        f"A signature made by the retired key {retired_kid} still verifies against the published "
        "set. A retirement a verifier cannot see is a column nothing reads: the key goes on being "
        "accepted by every platform holding this document, which is the state a rotation exists to "
        "leave behind."
    )
    assert any_key_verifies(keys_after, still_signing, AFTER_THE_SWITCH), (
        "After the retirement the published set verifies nothing signed by the key that was *not* "
        "retired. Then the assertion above is satisfied by an empty key set rather than by "
        "retirement working, and this deployment has stopped being able to prove anything at all."
    )
    rows = committed_rows.session.execute(table.select()).mappings().all()
    assert len(rows) == 2, (
        f"`{SIGNING_KEYS}` holds {len(rows)} rows after one of two keys was retired. E3-01 keeps "
        "the row as a record; a retirement written as a `DELETE` destroys the only answer to what "
        "this deployment used to sign with, at exactly the moment somebody is about to ask."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — no usable key is still a loud refusal, and one key is not.
# ---------------------------------------------------------------------------


def test_the_route_refuses_when_every_stored_key_has_been_retired(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """Criterion 4: "a deployment with no usable key still answers 503".

    E1-06 reached that state one way — no row at all — and
    `test_the_tool_publishes_its_key_set.py` holds it. E3-01 creates a second way
    to reach it, and it is the one an operator can walk into: rows exist, and every
    one has been retired. Retiring the last key is an ordinary mistake in the
    middle of a rotation, and the row count is no longer what says whether this
    deployment can sign.

    **The mutation this kills:** a refusal keyed on `count(*) == 0` rather than on
    the *usable* rows, which answers 200 here with an empty `keys` array — the
    exact document ADR 0085 rejected, because a platform accepts an empty key set,
    stores it, and reports the registration complete. Nothing is wrong until an
    assertion is refused hours later at somebody else's service.

    **The status is an equality and a 500 fails.** A route that crashes on the
    empty result — an unguarded `.one()`, a `None` handed to a PEM loader — is also
    "the tool did not serve a key set", and reading the two as the same thing would
    lose the finding: one is a decision this deployment can monitor and the other
    is an unhandled exception whose next refactor could as easily answer 200. That
    is a real cost and it is the cost worth paying.

    **Its pair is the test below**: the same route, the same shape of database, one
    key not retired, answering 200. Without it this is satisfied by a route that
    refuses always.
    """
    require_a_rotatable_table(committed_rows, metadata_tables)
    plant_key(
        committed_rows, **{CREATED_AT_COLUMN: OLDER_CREATED_AT, RETIRED_AT_COLUMN: RETIRED_AT}
    )
    plant_key(
        committed_rows, **{CREATED_AT_COLUMN: NEWER_CREATED_AT, RETIRED_AT_COLUMN: RETIRED_AT}
    )

    response = open_the_tool().get(TOOL_JWKS_PATH)

    assert response.status_code == NO_USABLE_KEY_STATUS, (
        f"`GET {TOOL_JWKS_PATH}` answered {response.status_code} where every stored key is retired, "
        f"and this deployment's answer to no usable key is {NO_USABLE_KEY_STATUS}. A 200 is the "
        "case this test exists for: the rows are there, so a refusal keyed on the row count serves "
        "an empty key set — a valid JWK Set a platform accepts, stores, and reports as a completed "
        "registration. A 500 is not the same thing and is not accepted here. Body begins "
        f"{response.text[:300]!r}."
    )
    try:
        body = response.json()
    except ValueError:
        body = None
    assert not (isinstance(body, dict) and "keys" in body), (
        f"The refusal carries a `keys` member: {json.dumps(body)[:300]}. A platform's key-set "
        "reader looks for exactly that and stores what it finds, so a refusal shaped like a key "
        "set is the disclosure this status code was chosen to avoid."
    )


def test_the_route_serves_the_key_set_while_one_stored_key_is_unretired(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """The other direction of criterion 4, and the reason the refusal above means anything.

    One retired key and one live one — the state a completed rotation leaves — has
    to answer 200 carrying exactly the live key. Without this, the test above is
    satisfied by a route that refuses whenever any row is retired, which would take
    a deployment offline the first time an operator finished a rotation correctly.

    **The mutations this kills:** a usability check written inverted, and a check
    that refuses when *any* row is retired rather than when *every* row is. Both
    are one word away from correct and both are invisible until the first real
    rotation.
    """
    require_a_rotatable_table(committed_rows, metadata_tables)
    retired_pem = plant_key(
        committed_rows, **{CREATED_AT_COLUMN: OLDER_CREATED_AT, RETIRED_AT_COLUMN: RETIRED_AT}
    )
    live_pem = plant_key(
        committed_rows, **{CREATED_AT_COLUMN: NEWER_CREATED_AT, RETIRED_AT_COLUMN: None}
    )

    document = key_set(open_the_tool())

    assert published_kids(document) == {kid_of_pem(live_pem)}, (
        "With one retired key and one live one the tool published "
        f"{sorted(published_kids(document))} rather than the live key alone. This is the state a "
        "finished rotation leaves, so a route that refuses it takes the deployment offline at the "
        "moment an operator does the right thing — and a route that publishes the retired key "
        "beside it has not retired anything."
    )
    assert any_key_verifies(
        document["keys"], signature_by(live_pem, AFTER_THE_SWITCH), AFTER_THE_SWITCH
    ), (
        "The one published key does not verify a signature by the one live stored key, so the "
        "document names the right key and carries the wrong numbers."
    )
    assert not any_key_verifies(
        document["keys"], signature_by(retired_pem, BEFORE_THE_SWITCH), BEFORE_THE_SWITCH
    ), "The published key verifies a signature by the retired key, so the two rows hold one key."


def test_the_refusal_tells_an_operator_what_to_do_about_it(
    committed_rows: Any, metadata_tables: dict[str, Any], open_the_tool: Any
) -> None:
    """Criterion 4: 503 "with an actionable sentence", not merely a status code.

    ADR 0085 gave the body one job — say that this deployment publishes no key set
    — because in E1-06 there was nothing an operator could do about it: the seed
    was the only writer and it refuses to run outside development. E3-01 changes
    that fact, and criterion 4 changes the wording with it. A refusal naming
    nothing runnable is one the person reading it can only escalate.

    **The mutation this kills:** the E1-06 body left as it is once the supply path
    lands, which is `docs/MISTAKES.md` entry 1 in its usual shape — a record that
    goes on being true of a system that changed underneath it.

    **What is asserted is the supply path's name, not a sentence.** The wording is
    the implementer's and pinning it would settle copy from the test side; what
    cannot be left open is whether the body names the thing an operator runs.
    `scripts/signing_key.py` is settled by this ticket's work order, so naming it
    is reading a decision rather than making one.

    **This test plants nothing, so it asks only for an empty table and not for the
    rotation columns.** Its subject is reachable on today's schema — the no-key
    state is the one E1-06 already answers — so it must fail on its own assertion
    about the wording rather than on a guard about a column it never touches.
    """
    require_an_empty_table(committed_rows, metadata_tables)

    response = open_the_tool().get(TOOL_JWKS_PATH)

    assert response.status_code == NO_USABLE_KEY_STATUS, (
        f"`GET {TOOL_JWKS_PATH}` answered {response.status_code} with no key stored at all, and "
        f"this deployment's answer to that is {NO_USABLE_KEY_STATUS}. "
        "`test_the_tool_publishes_its_key_set.py` owns that failure; this test is about what the "
        f"refusal says. Body begins {response.text[:300]!r}."
    )
    assert THE_SUPPLY_PATH in response.text, (
        f"The refusal does not name {THE_SUPPLY_PATH!r}, so it tells whoever reads it nothing they "
        "can act on: this deployment publishes no key set, and the operator command that would "
        "give it one goes unmentioned. Until E3-01 there was nothing to name — the seed was the "
        "only writer and it refuses to run outside development — which is exactly the fact this "
        f"ticket changes. Body: {response.text[:400]!r}"
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the route.**
# ---------------------------------------------------------------------------


def test_the_verifier_these_tests_use_accepts_the_right_key_and_refuses_the_wrong_one() -> None:
    """The canary under every "verifies" and every "is refused" above.

    `verifies` and `any_key_verifies` are new machinery, and a detector whose only
    evidence is that the tests using it went red proves nothing
    (`docs/MISTAKES.md` entry 35). Both directions, because both are wrong in ways
    that are quiet: one answering `True` for everything would make every refusal
    above unfalsifiable, and one answering `False` for everything would make every
    acceptance a puzzle and get "corrected" by weakening whatever reported it.

    The malformed case is here because a published key set is JSON from a route
    under test: a key with a missing or unparseable member must answer `False`
    rather than raise, or a route serving a broken document takes these tests down
    with an error instead of a finding.

    The empty-set case is the sharpest of the six. Every retirement assertion above
    is a `not any_key_verifies(...)`, and an empty key set satisfies all of them —
    so this is the line that says such a pass would be about retirement rather than
    about a route that has stopped publishing.

    **A red here means these tests are broken, not the route.**
    """
    mine, yours = generated_pem(), generated_pem()
    message = b"e3-01 control"
    signature = signature_by(mine, message)

    assert verifies(public_jwk_of(mine), signature, message), (
        "The verifier refuses a signature by the very key it was handed the public half of, so "
        "every acceptance asserted in this module would be red against a correct route."
    )
    assert not verifies(public_jwk_of(yours), signature, message), (
        "The verifier accepts a signature by a different key, so every refusal asserted in this "
        "module is satisfied by a verifier that accepts everything."
    )
    assert not verifies({"kty": "RSA"}, signature, message), (
        "The verifier did not answer False for a key carrying neither `n` nor `e`. A route serving "
        "a malformed document would then raise out of these tests as an error rather than fail as "
        "a finding."
    )
    assert any_key_verifies([public_jwk_of(yours), public_jwk_of(mine)], signature, message), (
        "The set-wide verifier missed a key that is in the set, so 'a signature by either key "
        "verifies' would be red whenever the right key was not the first one tried."
    )
    assert not any_key_verifies(
        [public_jwk_of(yours)], signature, message
    ), "The set-wide verifier accepted a signature no key in the set can check."
    assert not any_key_verifies([], signature, message), (
        "The set-wide verifier accepted a signature against an empty key set, which is exactly the "
        "state the retirement assertions above must not be satisfied by."
    )
