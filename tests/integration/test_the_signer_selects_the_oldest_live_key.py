"""Which of the published keys actually signs — E3-01 criterion 3, under ADR 0143's rule.

> `kid` is present on signed assertions and selects the key at verification.

Publishing two keys is half a rotation. The other half is that a verifier can tell
which one signed what, and that the tool and every process of it agree on which
one is signing now — ADR 0082's deciding fact, unchanged: SPEC §7.2 runs an `api`
container and a `celery` worker, both sign, and "two processes signing with two
keys means half the assertions are rejected, by a platform, with an error about a
signature rather than about custody".

**The signer is the OLDEST live key, and the newest is published for platforms to
pre-fetch.** ADR 0143, from E3-08's boundary round (LO-M3), superseding ADR 0127's
"newest signs" in part. The selection order is `created_at ASC, id ASC` among rows
with `retired_at IS NULL`.

**Why that way round, because this file used to argue the opposite and the reason
matters more than the assertion.** A key set is a document platforms *cache*. Under
newest-signs, the instant an operator generates a replacement the tool begins
signing with a key no platform has fetched yet — so every service call fails, at
every platform, until each of them happens to re-fetch, and the operator who
generated the key has no way to know when that is. The failure is remote, total
and untimed, and it is caused by the safe-sounding half of a rotation.

Under oldest-signs the two halves separate, which is the whole of ADR 0143's
rotation procedure:

  - **generate** publishes the new key and changes nothing about signing. Platforms
    re-fetch on their own schedule and quietly acquire it;
  - **retire** the old key, after that wait, and the switch happens — to a key every
    platform has already had for as long as the operator chose to wait.

So a rotation becomes two deliberate acts with a safe interval between them, rather
than one act with an unbounded outage inside it. The cost, stated because it is
real: the key doing the signing is the older one, so key material is in use for
longer than under the other rule. ADR 0143 takes that price for the outage it
removes, and `retired_at` is what bounds it.

**The assertion under test is one the tool really signed.** There is no way to ask
this question of a value this suite made up, so every test here drives E1-11's
roster sync against a registered mock platform and reads the `client_assertion`
off the wire the client sent it on — the same evidence
`tests/integration/test_the_roster_sync_is_a_conformant_service_client.py` uses
and for the same reason it gives: what the client sent says the client has no
other path, where a status code says only that one call was accepted.

**Each test moves exactly one thing.** The suite's own machinery seeds one signing
key before any of this runs; each test then plants a second row differing in one
value — newer, oldest-then-retired, or created in the same instant — and asks which
key the tool signed with. A test that changed two things at once would be satisfied
by an implementation that got either one right.

**This file replaces `test_the_signer_selects_the_newest_live_key.py`**, whose
name, arguments and assertions were all E3-01's original rule. The flip is the
ruled behaviour change ADR 0143 records, not a weakening: every assertion below
still pins a single deterministic signer, still requires the `kid` to select the
key that really signed, and still requires `retired_at` to be read. What changed is
which end of the ordering the rule takes, and every sentence arguing for the other
end has been rewritten rather than negated.

**These are the most expensive tests in the ticket**, because a real assertion
needs a real registration and a real grant. They are here rather than folded into
the key-set module because the published set and the signer are two properties: a
route can publish both keys correctly while the signer picks the retired one, and
that failure appears only at a platform.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.signing_key_tool import (
    CREATED_AT_COLUMN,
    PRIVATE_KEY_COLUMN,
    RETIRED_AT_COLUMN,
    SIGNING_KEYS,
    generated_pem,
    kid_of_pem,
    require_rotation_columns,
    require_stored_key,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# RFC 6749 §4.4's grant, spelled as the roster-sync module spells it. A
# specification constant, transcribed rather than imported, because a platform
# accepting some other spelling is one no conformant client reaches.
CLIENT_CREDENTIALS_GRANT = "client_credentials"

# How much later than the key already stored the planted key is created. An hour
# rather than a second, so that the two rows are ordered by a value no clock skew
# inside one test run can reverse.
AN_HOUR = timedelta(hours=1)


def plant_beside(rows: Any, **values: Any) -> str:
    """One more `tool_signing_key` row, committed, and the private half of it.

    Committed because the tool reads this table on its own connection as the
    application role. The PEM comes back so the test can derive the `kid` the
    assertion header has to carry — derived rather than stored (ADR 0082), so
    there is nothing to look up.
    """
    pem = generated_pem()
    rows.seed(SIGNING_KEYS, {}, **{PRIVATE_KEY_COLUMN: pem, **values})
    rows.commit()
    return pem


def the_key_already_stored(rows: Any, tables: dict[str, Any]) -> dict[str, Any]:
    """The single row the suite's own machinery seeded, with its columns.

    `tests/fixtures/roster_sync.py::stored_signing_key` writes it so that the tool
    has something to sign with at all, and every test here plants a second row
    beside it. Read rather than assumed, because the tie-break test needs its
    `created_at` exactly and the others need its `kid`.
    """
    require_rotation_columns(tables[SIGNING_KEYS].c.keys(), "the declared table")
    stored = [dict(row) for row in rows.session.execute(tables[SIGNING_KEYS].select()).mappings()]
    require_stored_key(stored, "the point where this test plants its second key")
    assert len(stored) == 1, (
        f"`{SIGNING_KEYS}` holds {len(stored)} rows before this test plants anything, and these "
        "tests move exactly one thing from a one-key state. Another row here means the fixtures "
        "seeded more than one key or a previous test leaked one, and 'the tool signed with the key "
        "this test planted' would be a claim about a set nobody chose."
    )
    return stored[0]


def signed_assertion(sync: Any, rows: Any, section: Any, wire: Any) -> tuple[str, str]:
    """One roster sync, the `client_assertion` the tool signed for it, and its audience.

    The whole sequence in one helper because three tests need the same evidence
    and differ only in what was planted before it. Nothing here asserts anything
    about *which* key signed — that is each test's own subject; what it asserts is
    that a grant happened at all, because "the assertion names the right key" is
    vacuously true of a sync that made no request.
    """
    sync.call(
        sync.sync_one_section,
        session=rows.session,
        section_id=section.id,
        http=wire.session(),
    )
    rows.commit()

    granted = [
        call
        for call in wire.to_host(section.host)
        if call.method.upper() == "POST"
        and call.form.get("grant_type") == [CLIENT_CREDENTIALS_GRANT]
    ]
    assert len(granted) == 1, (
        f"The sync posted {len(granted)} client-credentials grants to {section.host!r}; the calls "
        f"it made were {wire.to_host(section.host)}. With no grant there is no assertion, and "
        "every claim about which key signed one would be true of a client that signed nothing. "
        "`tests/integration/test_the_roster_sync_is_a_conformant_service_client.py` is where a "
        "missing or duplicated grant is diagnosed."
    )
    assertion = (granted[0].form.get("client_assertion") or [""])[0]
    assert assertion, (
        "The grant carried no `client_assertion` at all, so there is no JOSE header to read a "
        "`kid` out of and nothing signed to attribute to a key."
    )
    # The audience is the token endpoint the assertion was posted to, taken off
    # the recorded call rather than composed here: RFC 7523 §3 makes `aud` the
    # endpoint's own URL, and a verification with the wrong audience is refused
    # for a reason that has nothing to do with which key signed it.
    return str(assertion), str(granted[0].url)


def kid_in_the_header_of(assertion: str) -> str:
    """The `kid` a signed assertion names itself with, read without verifying it.

    Unverified deliberately: the question is what the tool *claimed* the signing
    key was, and verifying first would answer with whichever key happened to work.
    A platform reads this header before it has verified anything either — that is
    what the member is for.
    """
    import jwt

    header = jwt.get_unverified_header(assertion)
    kid = header.get("kid")
    assert isinstance(kid, str) and kid, (
        f"The assertion the tool signed carries a JOSE header {header!r}, with no usable `kid`. "
        "Criterion 3 puts one on every signed assertion, and it is the only thing that tells a "
        "platform holding two of this tool's keys which one to check the signature against — "
        "without it the platform either tries them all or refuses, and which of those it does is "
        "not this tool's decision to leave open."
    )
    return kid


def verified_against(assertion: str, jwk: dict[str, Any], audience: str) -> dict[str, Any] | None:
    """The claims of `assertion` if `jwk` verifies it, and `None` if it does not.

    Both answers are used: the key the header names has to verify it, and the key
    it does not name must not. A helper that raised would make the second half an
    exception-handling exercise in every caller.
    """
    import base64

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    def integer(value: str) -> int:
        padded = value + "=" * (-len(value) % 4)
        return int.from_bytes(base64.urlsafe_b64decode(padded), "big")

    try:
        public = rsa.RSAPublicNumbers(integer(jwk["e"]), integer(jwk["n"])).public_key()
        return dict(jwt.decode(assertion, public, algorithms=["RS256"], audience=audience))
    except Exception:
        return None


def published(tool: Any) -> dict[str, dict[str, Any]]:
    """The tool's own key set, fetched from `/lti/jwks` and keyed by `kid`."""
    response = tool.get("/lti/jwks")
    assert response.status_code == 200, (
        f"`GET /lti/jwks` answered {response.status_code} rather than 200, so this test has no "
        "published key set to select a key out of. "
        "`tests/integration/test_the_published_key_set_carries_a_rotation.py` is where the route's "
        f"own failures are diagnosed. Body begins {response.text[:200]!r}."
    )
    keys = response.json().get("keys")
    assert isinstance(keys, list) and keys, (
        f"The tool published {response.json()!r}, which carries no keys — so `kid` selects nothing "
        "and there is no verification for this test to be about."
    )
    return {str(key.get("kid")): key for key in keys if isinstance(key, dict)}


# ---------------------------------------------------------------------------
# The signer, moved one value at a time.
# ---------------------------------------------------------------------------


def test_generating_a_newer_key_publishes_it_and_leaves_the_older_one_signing(
    synced_section: Any,
    roster_platforms: Any,
    service_wire: Any,
    roster_sync: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """ADR 0143's first half: generate publishes, and does not switch.

    A second key is planted an hour newer than the one already stored — the state
    an operator produces by generating a replacement — and then the tool signs. The
    header must name the **older** key, and the newer one must be in the published
    set, waiting for platforms to pick up on their own schedule.

    **What this protects, and it is an outage rather than a preference.** A key set
    is a document platforms cache. A tool that begins signing with a key the moment
    it is generated is signing with a key no platform has fetched yet: every
    service call to every platform is refused until each of them re-fetches, on a
    schedule the operator neither knows nor controls. ADR 0143 separates the two
    acts so that generating is safe and retiring is the deliberate switch.

    **The mutations this kills.** A signer that reads *a* row — `.first()`, no
    `ORDER BY` — which is correct while one row exists and becomes a coin toss the
    moment a rotation starts; a signer that takes the *newest* row, which is ADR
    0127's superseded rule and which turns every `generate` into the outage above;
    and a `kid` that is a row id, a timestamp or a constant, each of which is
    stable and plausible right up until the platform computes the same key's
    thumbprint and gets something else.

    **Three assertions rather than one, because "signs", "publishes" and "selects"
    are different claims.** The older key has to be the one signing; the newer one
    has to be published anyway, which is the half that makes the rotation
    procedure work at all and which a signer-only reading would drop; and the key
    the header names has to actually verify the signature, because a header can
    carry the right `kid` over a signature made by the other key — the near miss
    `tests/fixtures/client_credentials.py::ToolKeyPair.sign` exists to produce.

    **And the key it does not name must not verify it**, which is what says the
    `kid` distinguishes anything at all.
    """
    stored = the_key_already_stored(committed_rows, metadata_tables)
    newer_pem = plant_beside(
        committed_rows,
        **{CREATED_AT_COLUMN: stored[CREATED_AT_COLUMN] + AN_HOUR, RETIRED_AT_COLUMN: None},
    )
    older_kid = kid_of_pem(str(stored[PRIVATE_KEY_COLUMN]))
    newer_kid = kid_of_pem(newer_pem)
    assert older_kid != newer_kid, "The planted key is the stored one, so nothing here is a choice."

    assertion, audience = signed_assertion(
        roster_sync, committed_rows, synced_section, service_wire
    )

    named = kid_in_the_header_of(assertion)
    assert named == older_kid, (
        f"The tool signed with the key it calls {named}, and the oldest live key is {older_kid} "
        f"(the newer stored key is {newer_kid}). ADR 0143 makes the signer the *oldest* row with "
        "`retired_at IS NULL`, ordered `created_at ASC, id ASC`.\n\n"
        f"If the tool signed with {newer_kid}, that is ADR 0127's superseded rule: generating a "
        "replacement then switches the signer immediately, to a key no platform has fetched yet, "
        "and every service call to every platform is refused until each re-fetches on a schedule "
        "nobody controls. Under ADR 0143 `generate` publishes and changes nothing; `retire` is "
        "what switches, after the operator has waited for the platforms."
    )

    keys = published(roster_platforms.tool)
    assert named in keys, (
        f"The assertion names {named} and the tool publishes {sorted(keys)}. A platform selects a "
        "verification key by exactly this member, so an assertion naming a key the key set does "
        "not carry is refused by every conformant platform without any signature being checked."
    )
    assert newer_kid in keys, (
        f"The tool publishes {sorted(keys)}, which does not carry the newly generated key "
        f"{newer_kid}. ADR 0143's rotation rests on this half: `generate` exists to get the new "
        "key into the published set *before* anything signs with it, so that the later `retire` "
        "switches to a key every platform already holds. A key that is not published until it "
        "starts signing reproduces the outage the rule was written to remove."
    )
    assert verified_against(assertion, keys[named], audience) is not None, (
        f"The key the assertion names, {named}, does not verify it. The header and the signature "
        "come from different keys, which is a document that passes every structural check and is "
        "refused at the platform — and it is what a signer that selects one key and signs with "
        "another produces."
    )
    assert verified_against(assertion, keys[newer_kid], audience) is None, (
        f"The assertion also verifies against {newer_kid}, the key it does not name. Then the two "
        "rows hold one key and this test has posed no choice at all."
    )


def test_retiring_the_oldest_key_moves_the_signer_to_the_remaining_live_key(
    synced_section: Any,
    service_wire: Any,
    roster_sync: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """ADR 0143's second half: retire performs the switch. The signer reads `retired_at`.

    The same two keys as the test above, with one value changed: the **older** key
    — the one that was signing — is retired. The signer must move to the newer key,
    which by then every platform has had since it was generated.

    This is the act an operator performs to complete a rotation, and it is the only
    one that changes who signs. Asserting it here is what makes the rule two halves
    rather than "the oldest key signs forever".

    **The mutation this kills, and no other test in this ticket kills it:** a
    signer ordered by `created_at ASC` that does not filter on `retired_at`. The
    published set is right — the key-set module proves the route filters — so a
    platform holds only the live key while the tool signs every assertion with the
    retired one. Every service call this tool makes is refused, and the published
    document looks perfect.

    **The other mutation:** a retirement enforced only at the route. Then
    "retirement removes a key from the set once nothing signs with it" is exactly
    backwards — the key leaves the set while it is still the only thing signing.

    **The near miss it must survive**, and the reason the newer key is not simply
    asserted present: a signer that always picks the *newest* key would pass this
    test and fail the one above. The pair is what pins the rule rather than either
    half of it.
    """
    stored = the_key_already_stored(committed_rows, metadata_tables)
    newer_pem = plant_beside(
        committed_rows,
        **{CREATED_AT_COLUMN: stored[CREATED_AT_COLUMN] + AN_HOUR, RETIRED_AT_COLUMN: None},
    )
    retired_kid = kid_of_pem(str(stored[PRIVATE_KEY_COLUMN]))
    live_kid = kid_of_pem(newer_pem)

    # Retire the older key — the switch itself. Its `retired_at` sits after the
    # newer key's creation, which is the order an operator produces: generate,
    # wait for the platforms, then retire.
    table = metadata_tables[SIGNING_KEYS]
    committed_rows.session.execute(
        table.update()
        .where(table.c[PRIVATE_KEY_COLUMN] == stored[PRIVATE_KEY_COLUMN])
        .values(**{RETIRED_AT_COLUMN: stored[CREATED_AT_COLUMN] + AN_HOUR + AN_HOUR})
    )
    committed_rows.commit()

    assertion, _ = signed_assertion(roster_sync, committed_rows, synced_section, service_wire)

    named = kid_in_the_header_of(assertion)
    assert named == live_kid, (
        f"The tool signed with {named}; {retired_kid} is retired and {live_kid} is not. A signer "
        "that orders by `created_at ASC` and never reads `retired_at` picks the retired key here "
        "— and the failure is silent on this side, because the published key set is correct: the "
        "platform holds the live key and the tool signs with the dead one, so every service call "
        "is refused at the platform with an error naming no key.\n\n"
        "This is also the assertion that says a rotation ever completes. Under ADR 0143 `retire` "
        "is the only act that moves the signer, so a signer that ignores it leaves the oldest key "
        "signing for the life of the deployment."
    )


def test_two_keys_created_in_the_same_instant_are_ordered_by_id(
    synced_section: Any,
    service_wire: Any,
    roster_sync: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The tie-break is the reason the ordering has two columns, so it is asserted.

    Two rows created in the same instant is not a contrived state: `created_at`
    has a server default, Postgres gives every statement in one transaction the
    same `now()`, and a supply script that wrote a key and its replacement
    together produces exactly this. Whatever the signer does here, it must do the
    same thing in the api container and in the celery worker — ADR 0082's deciding
    fact — and `created_at ASC` alone leaves the answer to whichever row the
    planner hands back first, which is stable until an index changes and then
    silently is not.

    **The mutation this kills:** the second ordering column dropped, so the choice
    between two same-instant rows is the storage layer's. It is the mutation least
    likely to be caught by anything else, because a single run of a single process
    usually answers consistently — which is what makes it ship.

    **The expected key is computed from the rows, not chosen by this test.** Both
    ids are read back and the **lesser** one is what `id ASC` means under ADR 0143,
    so this asserts the rule rather than a value; a test that planted a known
    winner would have fixed the answer before asking the question.
    """
    stored = the_key_already_stored(committed_rows, metadata_tables)
    plant_beside(
        committed_rows, **{CREATED_AT_COLUMN: stored[CREATED_AT_COLUMN], RETIRED_AT_COLUMN: None}
    )
    rows = [
        dict(row)
        for row in committed_rows.session.execute(metadata_tables[SIGNING_KEYS].select()).mappings()
    ]
    assert len({row[CREATED_AT_COLUMN] for row in rows}) == 1 and len(rows) == 2, (
        f"This test needs two rows sharing one `{CREATED_AT_COLUMN}` and there are "
        f"{len(rows)} rows carrying {sorted({str(row[CREATED_AT_COLUMN]) for row in rows})}. "
        "Without the tie there is nothing for a tie-break to decide, and the assertion below would "
        "be about the ordering's first column."
    )
    winner = min(rows, key=lambda row: row["id"])
    loser = max(rows, key=lambda row: row["id"])

    assertion, _ = signed_assertion(roster_sync, committed_rows, synced_section, service_wire)

    named = kid_in_the_header_of(assertion)
    assert named == kid_of_pem(str(winner[PRIVATE_KEY_COLUMN])), (
        f"With two keys created in the same instant the tool signed with {named}, and ADR 0143's "
        f"`{CREATED_AT_COLUMN} ASC, id ASC` selects the row with the lesser id "
        f"({winner['id']} rather than {loser['id']}). An ordering that stops at the timestamp "
        "leaves this to the storage layer, so the api container and the celery worker can sign "
        "with different keys — which is ADR 0082's deciding fact, and the half of the tool's "
        "assertions that keeps working is what makes it somebody else's incident."
    )
