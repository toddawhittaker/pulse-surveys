"""The supply path and the retirement step — E3-01, criteria 1 and 3.

> A key can be supplied to a deployment by a documented operator path that the
> development seed does not participate in.

ADR 0082 decided storage and left supply open, and its own consequence section
says what that costs: "a non-development deployment has no signing key… the first
deployment that needs to sign will need a supply route before it needs anything
else in this record." E3 is the epic that first registers a real platform, so the
route lands here. E3-01's work order settles its shape — `scripts/signing_key.py`
with `generate`, `retire <kid>` and `list` — and this module is that command line
driven the way an operator drives it.

**Every database here is one the seed has never run against.** That is criterion
1's whole point: the seed refuses to run outside development (ADR 0063), so a
supply path proven only against a seeded database is proven against the one place
it is not needed. `signing_key_tool` hands out migrated databases with nothing in
them.

**Why the script is run rather than imported.** It is a program an operator
invokes, and its exit status is the answer they read. A module-level import would
report a green run of nothing for a script that does its work under `if __name__
== "__main__"`, and it would put the script's own `app.*` imports into an
interpreter whose `sys.modules` already holds modules built against a different
`DATABASE_URL` — the two reasons `tests/fixtures/seed.py` gives for running the
demo seed the same way.

**The privileged credential is proven by the write succeeding, not by reading the
source.** `seed_environment` supplies the address in `DATABASE_URL` naming the
**application** role and the privileged identity in `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD` beside it, which is ADR 0012's shape and a deployment's.
A script that connected with the credential in `DATABASE_URL` would be refused by
Postgres at its first `INSERT` — the application role holds `SELECT` alone on this
table and
`tests/integration/test_the_application_role_cannot_write_a_signing_key.py`
asserts that it still does. So a `generate` that leaves a row behind is a script
that reached for the privileged pair.

**Retirement is executable here, not describable.** The ticket's second known trap
is that "a key set with two keys is a place for a stale key to live forever", so
every assertion about retiring is made by running `retire` and reading the table,
and each is a pair: the named key is retired **and** the key that was not named is
still live.

**Nothing here prints, writes or commits key material**, and two tests assert that
the script does not either. Keys are generated per run and live in memory, which
is SPEC §9.1's rule and what keeps the repository-wide sweep in
`tests/unit/test_mock_lms_service.py` an equality against zero.
"""

from typing import Any

import pytest
from fixtures.signing_key_tool import (
    CREATED_AT_COLUMN,
    GENERATE,
    LIST,
    PEM_PRIVATE_MARKER,
    PRIVATE_KEY_COLUMN,
    RETIRE,
    RETIRED_AT_COLUMN,
    SIGNING_KEYS,
    SMALLEST_ACCEPTABLE_KEY_BITS,
    kid_of_pem,
    loaded_key,
    require_rotation_columns,
    segments_by_kid,
)

pytestmark = pytest.mark.integration

# A kid no key has. A well-formed RFC 7638 thumbprint is 43 unpadded base64url
# characters, so this is shaped exactly like a real one and differs from every
# real one — which is what makes a refusal attributable to the key not being
# there rather than to the argument being malformed.
A_KID_NO_KEY_HAS = "e3-01-no-key-answers-to-this-thumbprint-xyz"

# How a listing may say that a key is retired. **A candidate list, because the
# ticket fixes no output format**, and it is the same device
# `tests/fixtures/supervision.py::require_column` uses where a name is the
# implementer's to choose: the assertion is that the listing distinguishes a
# retired key from a live one, not that it uses one particular word.
RETIREMENT_WORDS = ("retire", "revoked", "withdrawn")


def stored_kids(tool: Any) -> dict[str, dict[str, Any]]:
    """Every row this database holds, keyed by the thumbprint of the key in it."""
    return tool.kid_of_each_row()


def live(rows: dict[str, dict[str, Any]]) -> set[str]:
    """The kids of the rows that have not been retired."""
    return {kid for kid, row in rows.items() if row.get(RETIRED_AT_COLUMN) is None}


def retired(rows: dict[str, dict[str, Any]]) -> set[str]:
    """The kids of the rows that have been."""
    return {kid for kid, row in rows.items() if row.get(RETIRED_AT_COLUMN) is not None}


def two_generated_keys(tool: Any) -> tuple[str, str]:
    """Two `generate` runs against one database, and the kids they left behind.

    Shared because four tests below start from the same two-key state, and it is
    exactly the state a rotation is: the retiring key and its replacement,
    published together. It asserts only that the runs succeeded and that two
    distinct rows exist — the *rule* that a second row is permitted at all is
    `test_a_second_generate_supplies_a_second_live_key_rather_than_being_refused`'s
    subject, and a failure here sends the reader there.
    """
    for attempt in (1, 2):
        run = tool.run(GENERATE)
        assert run.succeeded, (
            f"`{GENERATE}` run {attempt} of 2 did not succeed, so this test has no rotation state "
            f"to reason about.\n{run.report()}"
        )
    require_rotation_columns(tool.columns(), "the migrated database")
    rows = stored_kids(tool)
    assert len(rows) == 2, (
        f"Two `{GENERATE}` runs left {len(rows)} rows in `{SIGNING_KEYS}` and a rotation needs "
        "two: the retiring key and its replacement, published at once, which is the overlap the "
        "one-row rule structurally forbade."
    )
    older, newer = sorted(rows, key=lambda kid: (rows[kid][CREATED_AT_COLUMN], rows[kid]["id"]))
    return older, newer


# ---------------------------------------------------------------------------
# Supplying a key where the seed does not run.
# ---------------------------------------------------------------------------


def test_the_operator_script_supplies_a_key_to_a_database_the_seed_never_touched(
    signing_key_tool: Any,
) -> None:
    """Criterion 1: a key reaches a deployment by a path the development seed is not in.

    **The mutations this kills.** No supply path at all, which is the state at
    HEAD and the carried entry this ticket closes — a deployment answers 503 at
    `/lti/jwks` forever and can be registered at no platform. A path that only
    works where the demo seed works, which is the one place it is not needed: this
    database is migrated and otherwise empty, and `scripts/seed.py` has never been
    pointed at it. And a row holding a placeholder, which "a key was supplied"
    accepts and which fails at the first client assertion, at somebody else's
    platform, with an error about a signature.

    The size is asserted as well as the parse, for the reason the E1-05 module
    gives: a 512-bit RSA key loads perfectly, signs perfectly, and is refused by
    every platform that checks — and it is what a generation call written for
    speed produces.

    **It is also what says the script used the privileged credential.** The
    environment names the application role in `DATABASE_URL` and the superuser
    pair beside it; the application role holds `SELECT` alone on this table, so a
    script connecting with the credential the address carries writes nothing at
    all and this test is red on an empty table.
    """
    tool = signing_key_tool()
    before = tool.rows()
    assert not before, (
        f"`{SIGNING_KEYS}` already holds {len(before)} row(s) in a database nothing has written "
        "to. Then a row found afterwards says nothing about the supply path, which is the whole "
        "subject here."
    )

    run = tool.run(GENERATE)

    assert run.succeeded, (
        f"`{GENERATE}` did not succeed against a migrated deployment database. Criterion 1 is that "
        "a key reaches a deployment 'by a documented operator path that the development seed does "
        f"not participate in'.\n{run.report()}"
    )
    rows = tool.rows()
    assert len(rows) == 1, (
        f"`{GENERATE}` left {len(rows)} rows in `{SIGNING_KEYS}` where it was asked for one key. "
        "Zero is the supply path not working; more than one from a single run is a command whose "
        "effect an operator cannot predict, and rotation is the one operation where that matters."
    )
    key = loaded_key(rows[0].get(PRIVATE_KEY_COLUMN), f"The generated `{SIGNING_KEYS}` row")
    assert key.key_size >= SMALLEST_ACCEPTABLE_KEY_BITS, (
        f"The supplied signing key is {key.key_size} bits and ADR 0082 fixes at least "
        f"{SMALLEST_ACCEPTABLE_KEY_BITS}. A shorter key loads and signs exactly like a long one "
        "and is refused by the platforms that check, which is a failure against a real LMS and "
        "nowhere before it."
    )


def test_a_second_generate_supplies_a_second_live_key_rather_than_being_refused(
    signing_key_tool: Any,
) -> None:
    """The rotation overlap the one-row rule forbade — E3-01's context, in one row count.

    > A key rotation needs a period in which the published key set carries both the
    > retiring key and its replacement… The current one-row rule structurally
    > forbids that overlap: there is nowhere to put the second key.

    **The mutation this kills, and it is the state at HEAD:**
    `uq_tool_signing_key_one_row` still on the table, so the second `generate` is
    refused by the database and rotation is unbuildable. It also kills the two
    plausible half-measures — an index moved onto `private_key_pem`, which permits
    any number of rows holding *different* keys and none holding the same one, and
    an index recreated as a partial unique index over the live rows, which would
    refuse this second key for exactly the reason the widening exists to remove.

    **Both rows are live**, and that is the second half rather than a detail. A
    `generate` that inserted its new key already retired would satisfy every count
    here and publish nothing new, and the failure would appear at the platform
    when the old key was retired in turn.

    **The near miss it must survive**, and why the first row is written by the
    same command: a schema that refuses *every* insert — a check nothing can
    satisfy, a grant nobody holds — leaves this test red for a reason that has
    nothing to do with the one-row rule. The first run succeeding is what
    separates them, and `test_the_operator_script_supplies_a_key_to_a_database_
    the_seed_never_touched` owns that failure.
    """
    tool = signing_key_tool()
    first = tool.run(GENERATE)
    assert first.succeeded, (
        f"The first `{GENERATE}` did not succeed, so a second one being refused would say nothing "
        f"about the one-row rule.\n{first.report()}"
    )

    second = tool.run(GENERATE)

    assert second.succeeded, (
        f"The second `{GENERATE}` was refused. If Postgres named `uq_tool_signing_key_one_row`, "
        "that is E1-05's index still on the table: E3-01 drops it, because a rotation needs the "
        "retiring key and its replacement published at once and the one-row rule leaves nowhere "
        f"to put the second.\n{second.report()}"
    )
    require_rotation_columns(tool.columns(), "the migrated database")
    rows = stored_kids(tool)
    assert len(rows) == 2, (
        f"Two `{GENERATE}` runs left {len(rows)} distinct keys in `{SIGNING_KEYS}`. One means the "
        "second run adopted, replaced or overwrote the first key rather than adding to it — and a "
        "replacement is the invisible failure ADR 0082 named: the new key signs perfectly, and "
        "nothing goes wrong until a platform that already fetched the old public half refuses an "
        "assertion hours later."
    )
    assert live(rows) == set(rows), (
        f"Of the two supplied keys, {sorted(retired(rows))} came out already retired. Both have to "
        "be in the published set for the overlap to exist at all: the retiring key still verifies "
        "what it signed before the switch, and the replacement verifies what is signed after it."
    )


def test_the_operator_script_names_the_key_it_supplied_and_prints_no_key_material(
    signing_key_tool: Any,
) -> None:
    """The command tells the operator the `kid` and nothing else about the key.

    Two halves, and each fails differently. **The kid has to be there**: it is
    derived rather than stored (ADR 0082), so it is not a value an operator can
    look up, and it is the argument `retire` takes and the name a platform
    selects a verification key by. A command that supplies a key and names it
    nothing leaves rotation undriveable by the person who has to drive it.

    **And the key must not be.** The natural way to report generating a key is to
    print it. This command runs in a terminal, in a deployment's shell history, in
    whatever logs the session, and SPEC §10 keeps values out of all three — a
    private key printed once is in a scrollback buffer and in whatever gets pasted
    when somebody asks for help.

    **The mutations this kills:** any `print(pem)` or `f"generated {pem}"` on the
    success or the failure path, and a command that prints a row id, a count or
    nothing at all in place of the thumbprint.

    **Both detectors on the material, because a key leaves by two doors.** The
    stored value itself, which catches the key this run wrote; and PEM armour of
    any kind, which catches the *other* key somebody printed — a traceback quoting
    the value it failed to parse, or a rotation that logged the one it replaced.
    """
    tool = signing_key_tool()

    run = tool.run(GENERATE)

    assert (
        run.succeeded
    ), f"`{GENERATE}` did not succeed, so there is no output to read.\n{run.report()}"
    rows = tool.rows()
    assert len(rows) == 1, (
        f"`{GENERATE}` left {len(rows)} rows, so 'the key is not in the output' would be a "
        "statement about a run that generated no key. The supply test above owns that failure."
    )
    stored = str(rows[0].get(PRIVATE_KEY_COLUMN) or "")
    assert stored, f"The generated `{SIGNING_KEYS}` row holds no key, so there is nothing to hide."

    assert kid_of_pem(stored) in run.output, (
        f"`{GENERATE}` did not name the key it supplied. Its output was:\n{run.output[-2000:]}\n"
        "The `kid` is the RFC 7638 thumbprint of the key, derived and never stored, so an operator "
        "has no other way to learn it — and it is the argument `retire` takes and the name a "
        "platform selects a verification key by."
    )
    assert stored not in run.output, (
        "The command printed the private key it generated. Its own output is what an operator "
        f"reads and what a deployment's shell history keeps:\n{run.output[-2000:]}"
    )
    assert PEM_PRIVATE_MARKER not in run.output, (
        "The command's output carries PEM private-key armour, which is either the key it wrote or "
        f"another one it handled on the way past:\n{run.output[-2000:]}"
    )


# ---------------------------------------------------------------------------
# Retirement: executable, and both directions of it.
# ---------------------------------------------------------------------------


def test_retiring_a_kid_retires_that_key_and_leaves_the_other_one_live(
    signing_key_tool: Any,
) -> None:
    """Criterion 3's retirement step, asserted on the key named and on the key not named.

    The ticket's second known trap: "a key set with two keys is a place for a
    stale key to live forever. Retirement has to be executable, not merely
    describable, or rotation ships as a way to accumulate keys." So this runs the
    command and reads the table.

    **Both directions, because each catches what the other misses.** The named key
    has to be marked, which kills a `retire` that parses its argument and does
    nothing — the shape that exits zero having matched nothing, and reads as
    success. And the key that was *not* named has to be untouched, which kills a
    `retire` that marks every row, or the newest, or the first it finds: that
    command retires the tool's whole identity while looking exactly like this one,
    and the deployment then answers 503 at `/lti/jwks` with no key to sign with.

    **The row stays**, and that is asserted rather than assumed. E3-01's rotation
    rule keeps a retired key as a record — "the row stays as a record; the key
    leaves the published set immediately" — so a `retire` implemented as a
    `DELETE` is a different decision, and one that leaves nothing to answer the
    question of what this deployment used to sign with.
    """
    tool = signing_key_tool()
    older, newer = two_generated_keys(tool)

    run = tool.run(RETIRE, newer)

    assert (
        run.succeeded
    ), f"`{RETIRE} {newer}` did not succeed against a database holding that key.\n{run.report()}"
    rows = stored_kids(tool)
    assert set(rows) == {older, newer}, (
        f"After retiring one of two keys the table holds {sorted(rows)} rather than both. E3-01 "
        "keeps a retired key as a record — it leaves the published set, it does not leave the "
        "database — so a `retire` that deletes is a different decision and destroys the only "
        "answer to what this deployment used to sign with."
    )
    assert retired(rows) == {newer}, (
        f"`{RETIRE} {newer}` left {sorted(retired(rows))} retired. Nothing means the command "
        "parsed its argument and changed no row, which exits zero and reads as success; both "
        "means it retired the tool's whole identity, and this deployment can now sign nothing at "
        "all."
    )
    assert live(rows) == {older}, (
        f"The key that was not named is {sorted(live(rows))} rather than {[older]}. A retirement "
        "that reaches a key nobody named is the failure worth more than the one above: it is "
        "silent, it looks like this test's own success, and it is found at the platform."
    )


def test_retiring_a_kid_no_key_answers_to_is_refused_and_retires_nothing(
    signing_key_tool: Any,
) -> None:
    """A `retire` that matches nothing says so, rather than exiting zero.

    The near miss for the test above and a case with its own incident behind it:
    an edit that matches nothing exits zero, and the unchanged state then reads as
    the change having been made. Here the cost is specific — an operator who
    mistypes a thumbprint believes a key has been retired, leaves the rotation
    half-done, and the stale key goes on being published and going on being
    accepted.

    **Both halves.** The command has to report failure, which is what an operator
    and any script wrapping them read; and no row may be retired, which is what
    kills a `retire` that reports failure *after* marking something.

    **The pair that makes it mean anything is the test above**: the same command,
    on the same database shape, with a kid a key does answer to, succeeds and
    marks exactly that row. Without it this would be satisfied by a `retire`
    subcommand that refuses everything.
    """
    tool = signing_key_tool()
    older, newer = two_generated_keys(tool)
    assert A_KID_NO_KEY_HAS not in {older, newer}, (
        "The kid this test asks to retire is one of the keys the database holds, so it is not "
        "posing the missing-key case at all. That is a defect in this module's constant."
    )

    run = tool.run(RETIRE, A_KID_NO_KEY_HAS)

    assert not run.succeeded, (
        f"`{RETIRE} {A_KID_NO_KEY_HAS}` exited 0 against a database that holds no such key. An "
        "operator who mistypes a thumbprint then believes a rotation completed, and the key they "
        f"meant to retire goes on being published and goes on verifying.\n{run.report()}"
    )
    rows = stored_kids(tool)
    assert live(rows) == {older, newer}, (
        f"A `{RETIRE}` naming a key nothing holds still retired {sorted(retired(rows))}. Refusing "
        "and then writing is worse than either alone: the operator reads a failure and the "
        "deployment has lost a key from its published set."
    )


def test_the_listing_names_every_key_and_tells_a_retired_one_from_a_live_one(
    signing_key_tool: Any,
) -> None:
    """`list` is how an operator sees the state a rotation is halfway through.

    Rotation is two commands with a window between them, and the window is where
    every mistake lives: which key is signing now, which one is still published,
    which one has already gone. A supply path with no way to read that state is
    one an operator drives blind, and the ticket's trap about a stale key living
    forever is exactly a state nobody can see.

    **The mutations this kills:** a listing that shows only live keys, which hides
    the record a retirement is supposed to leave; a listing that shows every key
    identically, so the half-finished rotation reads as two live keys; and a
    listing that prints the key material, which is the same disclosure the
    generate command is held to.

    **The retirement mark is a candidate list**, spelled at the top of this module,
    because the ticket fixes no output format and pinning one would settle an
    interface from the test side. What is asserted is that the two keys are told
    apart, in the stretch of output belonging to each — so a column heading or a
    banner carrying the word cannot satisfy it for a key that is still live.
    """
    tool = signing_key_tool()
    older, newer = two_generated_keys(tool)
    retire = tool.run(RETIRE, newer)
    assert retire.succeeded, (
        f"`{RETIRE} {newer}` did not succeed, so there is no retired key for the listing to "
        f"distinguish.\n{retire.report()}"
    )

    run = tool.run(LIST)

    assert run.succeeded, f"`{LIST}` did not succeed.\n{run.report()}"
    segments = segments_by_kid(run.output, (older, newer))
    named = sorted(kid for kid, segment in segments.items() if segment)
    assert named == sorted((older, newer)), (
        f"`{LIST}` named {named} of the two keys this database holds. A retired key that vanishes "
        "from the listing takes the record with it, and an operator halfway through a rotation "
        f"cannot see what state it is in. Output:\n{run.output[-2000:]}"
    )
    retired_words = [word for word in RETIREMENT_WORDS if word in segments[newer].lower()]
    assert retired_words, (
        f"`{LIST}` says nothing about {newer} being retired — its part of the output is "
        f"{segments[newer]!r}. E3-01 has `{LIST}` print each key's created and retired timestamps, "
        f"and a listing that shows a retired key exactly like a live one is a half-finished "
        "rotation reading as two live keys."
    )
    live_words = [word for word in RETIREMENT_WORDS if word in segments[older].lower()]
    assert not live_words, (
        f"`{LIST}` describes the still-live key {older} with {live_words} — its part of the output "
        f"is {segments[older]!r}. Then the mark says nothing about any key, and the assertion "
        "above passes over a listing that labels everything retired."
    )
    stored = {row[PRIVATE_KEY_COLUMN] for row in tool.rows()}
    leaked = [key for key in stored if str(key) in run.output]
    assert not leaked, (
        f"`{LIST}` printed {len(leaked)} of the private keys it was listing. The whole of the "
        "tool's LTI identity, into a terminal, a shell history and whatever logs the session."
    )
    assert (
        PEM_PRIVATE_MARKER not in run.output
    ), f"`{LIST}` output carries PEM private-key armour:\n{run.output[-2000:]}"


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the script.**
# ---------------------------------------------------------------------------


def test_the_kid_this_module_derives_identifies_the_key_and_nothing_else() -> None:
    """The canary on every `kid` assertion above, run before any of them is believed.

    `kid_of_pem` is new machinery and every test in this module addresses a row
    through it. Two ways it could be wrong and both are quiet: a value that is the
    same for every key, which would make "the command named the key it supplied"
    true of a command naming a constant; and a value that changes between two
    calls over the same key, which would make every `retire` here name a key the
    database cannot match.

    The RFC 7638 arithmetic underneath it has its own two-directional control in
    `tests/integration/test_the_tool_publishes_its_key_set.py::
    test_the_thumbprint_these_tests_compute_ignores_every_member_rfc_7638_excludes`,
    and this one is about the step above it: loading a PEM and assembling the
    three members from the public numbers.

    **A red here means these tests are broken, not the script.**
    """
    from fixtures.signing_key_tool import generated_pem

    one, another = generated_pem(), generated_pem()
    assert one != another, "Two generated keys came out identical, so this control poses nothing."

    assert kid_of_pem(one) == kid_of_pem(one), (
        "The same key produced two different thumbprints, so every `retire` in this module names a "
        "key the database cannot match and every failure here would be unreadable."
    )
    assert kid_of_pem(one) != kid_of_pem(another), (
        "Two different keys have the same thumbprint, so the value identifies nothing and 'the "
        "command named the key it supplied' would be true of a command printing a constant."
    )
    assert len(kid_of_pem(one)) == 43, (
        f"The thumbprint is {len(kid_of_pem(one))} characters. A SHA-256 digest in unpadded "
        "base64url is 43, and another length means the encoding is not the one RFC 7638 asks for "
        "and not the one a platform will compute."
    )
