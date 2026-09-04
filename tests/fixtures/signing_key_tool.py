"""E3-01 — the operator path to a signing key, and the arithmetic a rotation needs.

Three questions meet here and none of them has a home in the fixtures that already
exist. `scripts/signing_key.py` is a **program** an operator runs against a
deployment's database, so it needs the same treatment `tests/fixtures/seed.py`
gives the demo seed: a database of its own, migrated to head, and the script
started the way a shell starts it. A rotation needs the **thumbprint of a stored
key**, because `kid` is derived rather than stored (ADR 0082) and it is the only
name an operator or a platform ever says out loud. And a retirement is only
meaningful if a signature made with the retired key can be **planted and then
offered to a verifier**, which needs a sign-and-verify pair that does not go
through anything under test.

**Why this reuses `DemoSeed` for the database rather than growing its own.** The
question "which variables could a program need to reach this container" is
answered once, in `seed_environment`, and answering it a second time here is
`docs/MISTAKES.md` entry 13 in the shape that file names. The environment that
function assembles is also exactly the shape ADR 0012 settled and the shape this
script needs: the address in `DATABASE_URL` naming the **application** role, and
the privileged identity in `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` beside it.
So a script that connects with the application role's own credential is refused
by Postgres at its first `INSERT`, and a script that reads the superuser pair
works — which is what makes "it does not weaken the rule that the application
role cannot write the table" observable from outside rather than asserted about
source code.

**Nothing here asserts anything about the subject.** A script that is absent is
reported as a run that exited 127 with the reason on stderr, exactly as
`DemoSeed.run` reports a missing seed: while E3-01 is unbuilt every test in the
modules below should be red on its own criterion rather than erroring in setup on
somebody else's. The two `require_*` helpers stop with a sentence naming the
missing deliverable, which is a failure a reader can act on rather than an
`UndefinedColumn` raised from inside somebody's seeding.

**No key material is written down, printed, or committed.** Every key here is
generated in memory for the length of one test, which is SPEC §9.1's rule and
what keeps the repository-wide sweep in
`tests/unit/test_mock_lms_service.py::test_no_private_key_material_is_committed_to_the_repository`
an equality against zero.
"""

import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

import pytest

from fixtures.client_credentials import rfc7638_thumbprint
from fixtures.repo import REPO_ROOT
from fixtures.seed import DemoSeed
from fixtures.suite_keys import base64url_of

# The script, its three subcommands, and the table they act on — all spelled by
# E3-01's work order rather than discovered. A supply path an operator is
# documented into is a command line somebody writes down, so a spelling this
# suite could negotiate is a spelling that moves under whoever already ran it.
SIGNING_KEY_SCRIPT_PATH = REPO_ROOT / "scripts" / "signing_key.py"
GENERATE = "generate"
RETIRE = "retire"
LIST = "list"

# `tool_signing_key` and its columns, spelled as E1-05 spells the first two and as
# E3-01's rotation rule spells the last two.
SIGNING_KEYS = "tool_signing_key"
PRIVATE_KEY_COLUMN = "private_key_pem"
CREATED_AT_COLUMN = "created_at"
RETIRED_AT_COLUMN = "retired_at"

# The index E1-05 put on the table and E3-01 drops. Named here because a test
# that asserts a second row is *accepted* is asserting the absence of exactly this
# object, and naming it is what turns "the insert worked" into a statement about
# the rule that used to stop it.
ONE_ROW_INDEX = "uq_tool_signing_key_one_row"

# How long one run of the operator script may take before this stops waiting.
# **This file's choice**, and a bound rather than a requirement: generating one
# RSA 2048 key and writing one row is milliseconds of work, so a run that passes
# this is a hang — most likely a script waiting on a connection it cannot open —
# and a test that reported it as a failed criterion would send the reader to the
# wrong place.
SIGNING_KEY_TIMEOUT_SECONDS = 120

# What PEM private-key armour looks like, assembled from pieces rather than
# written out, for the reason `tests/integration/test_tool_signing_key_custody.py`
# gives: the tree-wide sweep for committed key material reads every file including
# this one, and a module that is its own offender teaches everybody to add an
# exclusion.
PEM_PRIVATE_MARKER = "PRIVATE" + " KEY-----"

# RSA's size, as E1-05 fixes it and ADR 0082 records it. Asserted as a floor
# everywhere it is used, so a later ticket that raises it does not come back here.
SMALLEST_ACCEPTABLE_KEY_BITS = 2048


class SigningKeyRun(NamedTuple):
    """One execution of `scripts/signing_key.py`, as the shell sees it.

    An operator runs this command and reads its exit status, so that is what a
    test asserts against. Both streams are kept: a non-zero exit is only useful
    with the output that produced it, and the "no key material in the output"
    rule is asked of both streams together, since a traceback quoting the value
    it failed to parse arrives on the second one.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Both streams, as one text, which is what a terminal shows."""
        return f"{self.stdout}\n{self.stderr}"

    def report(self) -> str:
        """The run, rendered for a failure message, with both streams tailed."""
        return (
            f"`{' '.join(self.argv)}` exited {self.returncode}.\n"
            f"stdout:\n{self.stdout[-2000:]}\nstderr:\n{self.stderr[-2000:]}"
        )


class SigningKeyTool:
    """A migrated database of its own, and `scripts/signing_key.py` pointed at it.

    Wraps a `DemoSeed` rather than building a second database machine, so the
    database, the roles on it and the environment a program reaches it through are
    all the ones every other process-level test in this suite uses. What this adds
    is the argv, and the readings a rotation test needs off the table afterwards.
    """

    def __init__(self, demo: DemoSeed) -> None:
        self.demo = demo

    def run(self, *arguments: str, **overrides: str | None) -> SigningKeyRun:
        """Run one subcommand against this database and report what happened.

        `overrides` go into the child's environment last, so a test can ask what
        the command does under an environment that is missing something; a value
        of `None` removes the variable rather than emptying it, which is
        `DemoSeed.run`'s convention and the same distinction it draws.

        **A missing script is a run that failed, not an error raised from here.**
        A `pytest.fail` in this method would report every test in the modules
        below as an error in setup; this way each fails on its own assertion,
        naming its own criterion, with this sentence attached.
        """
        argv = (sys.executable, str(SIGNING_KEY_SCRIPT_PATH), *arguments)
        if not SIGNING_KEY_SCRIPT_PATH.is_file():
            return SigningKeyRun(
                argv=argv,
                returncode=127,
                stdout="",
                stderr=(
                    f"{SIGNING_KEY_SCRIPT_PATH} does not exist, so there was nothing to run. "
                    "E3-01's first criterion is that a key reaches a deployment 'by a documented "
                    "operator path that the development seed does not participate in', and the "
                    "work order settles that path as this script with the subcommands "
                    f"`{GENERATE}`, `{RETIRE} <kid>` and `{LIST}`. Until it exists a deployment "
                    "has no way to hold a signing key at all, which is the carried entry this "
                    "ticket closes."
                ),
            )
        child_environment = {**os.environ, **self.demo.environment}
        for name, value in overrides.items():
            if value is None:
                child_environment.pop(name, None)
            else:
                child_environment[name] = value
        try:
            # S603: the command is this interpreter and a path built from the
            # repository root, with arguments this suite composed. Nothing in it
            # comes from input.
            completed = subprocess.run(  # noqa: S603
                list(argv),
                cwd=REPO_ROOT,
                env=child_environment,
                capture_output=True,
                text=True,
                timeout=SIGNING_KEY_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"`{' '.join(argv)}` did not finish in {SIGNING_KEY_TIMEOUT_SECONDS} seconds "
                "against a database holding at most a handful of rows. That is a hang rather than "
                "a failed criterion — a script waiting on a connection it cannot open looks "
                "exactly like this."
            )
        return SigningKeyRun(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def columns(self) -> set[str]:
        """What `tool_signing_key` actually has right now, read from the catalog.

        The catalog rather than `Base.metadata`, because the metadata describes
        what today's models declare and says nothing about the database in front
        of it — and because this answers for a table holding no rows, which is the
        state every one of these tests starts in.
        """
        from sqlalchemy import text

        with self.demo.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table"
                ),
                {"table": SIGNING_KEYS},
            ).scalars()
            return set(found)

    def rows(self) -> list[dict[str, Any]]:
        """Every `tool_signing_key` row, whole, as the superuser sees them.

        Read through raw SQL rather than through the declared table, so that a
        reading taken while the rotation columns are still missing reports the
        columns that *are* there instead of failing inside a `RETURNING` clause
        the models built.
        """
        from sqlalchemy import text

        with self.demo.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM public.{SIGNING_KEYS}"))  # noqa: S608
            return [dict(row) for row in result.mappings().all()]

    def kid_of_each_row(self) -> dict[str, dict[str, Any]]:
        """Every stored row, keyed by the RFC 7638 thumbprint of the key it holds.

        The `kid` is the only name the operator script prints and the only name a
        `retire` command takes, and nothing stores it (ADR 0082), so a test that
        wants to say "that row" has to derive it exactly as everybody else does.
        """
        return {kid_of_pem(str(row[PRIVATE_KEY_COLUMN])): row for row in self.rows()}


def require_rotation_columns(present: Iterable[str], where: str) -> None:
    """Stop with a sentence unless `created_at` and `retired_at` are both there.

    Every rotation assertion in these modules is about the values in those two
    columns, and over a schema without them each one would fail somewhere further
    in — inside a raw statement, or inside the seeding helper's own `RETURNING`
    clause — which reads as a broken test rather than as the missing deliverable
    it is (`docs/MISTAKES.md` entry 22 is the shape of that confusion).
    """
    have = set(present)
    missing = [name for name in (CREATED_AT_COLUMN, RETIRED_AT_COLUMN) if name not in have]
    if missing:
        pytest.fail(
            f"`{SIGNING_KEYS}` has no {missing} ({where} reports {sorted(have)}). E3-01 widens "
            f"E1-05's one-row rule: `{ONE_ROW_INDEX}` is dropped, `{CREATED_AT_COLUMN}` arrives "
            f"with a server default and `{RETIRED_AT_COLUMN}` arrives nullable, the published key "
            f"set becomes every row with `{RETIRED_AT_COLUMN} IS NULL`, and the signing key is the "
            f"newest of those by `{CREATED_AT_COLUMN} DESC, id DESC`. Without the two columns "
            "there is nowhere to put a rotation's second key, which is the state ADR 0082 records "
            "and this ticket changes."
        )


def require_stored_key(rows: list[dict[str, Any]], where: str) -> None:
    """Stop unless there is at least one row to reason about.

    Everything a rotation test asserts about which key is published, which key
    signs and which key is refused is satisfied by a database holding no keys at
    all: the published set is empty, nothing signs, and every signature is
    refused. `docs/MISTAKES.md` entry 3 in its plainest form, and this is the
    guard that keeps the assertions from passing over an absence.
    """
    assert rows, (
        f"`{SIGNING_KEYS}` holds no rows at {where}, so every assertion that follows is about a "
        "deployment with no signing key — where the published set is empty, nothing signs, and a "
        "signature by any key at all is refused. That is a defect in the planting rather than a "
        "finding about rotation."
    )


def generated_pem() -> str:
    """A fresh RSA private key in PKCS#8 PEM, generated here and never written down.

    SPEC §9.1: keys are generated per test run rather than checked in. The same
    shape `tests/integration/test_tool_signing_key_custody.py` and
    `tests/fixtures/roster_sync.py` both use, so a row planted here looks exactly
    like the row the seed and the operator script write.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=SMALLEST_ACCEPTABLE_KEY_BITS)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def loaded_key(pem: Any, where: str) -> Any:
    """`pem` parsed as an unencrypted private key, or a failure saying what was stored.

    Parsed rather than pattern-matched, for the reason the E1-05 module gives:
    "the column holds something that begins with a PEM header" is satisfied by
    armour around anything at all, and a key nothing can load is a key that fails
    at the first client assertion and nowhere before it.
    """
    from cryptography.hazmat.primitives import serialization

    assert isinstance(pem, str) and pem.strip(), (
        f"{where} holds {pem!r} rather than a PEM private key. A row with an empty value satisfies "
        "'a key was supplied' perfectly and signs nothing."
    )
    try:
        return serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (ValueError, TypeError) as refused:
        pytest.fail(
            f"{where} does not parse as an unencrypted PEM private key: {refused}. ADR 0082 stores "
            "PKCS#8 PEM with no passphrase, because the process that reads it has nowhere to get "
            "one from — an encrypted key here is a key nothing can use."
        )


def public_jwk_of(pem: str) -> dict[str, str]:
    """The public half of a stored key, as RFC 7517's three required RSA members.

    Assembled member by member from the public numbers, which is ADR 0085's rule
    for the route and the right rule here for the same reason: `cryptography`
    will hand back a private key's members one call from the public ones, and the
    difference is a `d` beside the modulus.
    """
    numbers = loaded_key(pem, "A key this suite planted").public_key().public_numbers()
    return {"kty": "RSA", "n": base64url_of(numbers.n), "e": base64url_of(numbers.e)}


def kid_of_pem(pem: str) -> str:
    """The RFC 7638 thumbprint of a stored key — the name everything says out loud.

    Computed with the suite's own implementation of RFC 7638 rather than with
    anything the tool produces (`docs/MISTAKES.md` entry 19), and that
    implementation already has its own two-directional control next door in
    `tests/integration/test_the_tool_publishes_its_key_set.py::
    test_the_thumbprint_these_tests_compute_ignores_every_member_rfc_7638_excludes`.
    """
    return rfc7638_thumbprint(public_jwk_of(pem))


def integer_of(value: str) -> int:
    """One RSA parameter out of a JWK: base64url, big-endian, unpadded (RFC 7518 §6.3)."""
    import base64

    padded = value + "=" * (-len(value) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), "big")


def signature_by(pem: str, message: bytes) -> bytes:
    """A real RS256 signature over `message`, made with the key `pem` holds.

    A real signature rather than a corrupted one, because the case being planted
    is "this key signed something and was then retired". A mangled signature is
    refused by a verifier that does no key selection at all, and a test built on
    one would read that as retirement working.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    return key.sign(message, padding.PKCS1v15(), hashes.SHA256())


def verifies(jwk: Mapping[str, Any], signature: bytes, message: bytes) -> bool:
    """Whether `signature` over `message` checks out against the public JWK `jwk`.

    A boolean rather than a raise, because both answers are asserted: a key set
    that verifies a retired key's signature and a key set that verifies nothing at
    all are different failures and the tests below say which is which.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    try:
        public = rsa.RSAPublicNumbers(integer_of(jwk["e"]), integer_of(jwk["n"])).public_key()
    except (KeyError, TypeError, ValueError):
        return False
    try:
        public.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True


def any_key_verifies(keys: Iterable[Mapping[str, Any]], signature: bytes, message: bytes) -> bool:
    """Whether any key in a published set verifies `signature`.

    This is what a platform does with a key set it has fetched, and it is the
    operation a retirement has to make fail: a platform holding this document
    tries every key it carries before it refuses an assertion.
    """
    return any(verifies(key, signature, message) for key in keys)


def segments_by_kid(output: str, kids: Iterable[str]) -> dict[str, str]:
    """The stretch of `output` belonging to each `kid`, from its name to the next one.

    A listing prints something per key and the ticket fixes no layout, so this
    slices on the one thing that is fixed — the `kid` itself — rather than on a
    line, a column or a separator this suite would be inventing. A kid the output
    never names gets an empty segment, and the caller says what that means.
    """
    positions = sorted(
        ((output.find(kid), kid) for kid in kids if output.find(kid) >= 0), key=lambda pair: pair[0]
    )
    segments = {kid: "" for kid in kids}
    for index, (start, kid) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(output)
        segments[kid] = output[start:end]
    return segments


@pytest.fixture
def signing_key_tool(demo_databases: Callable[[], DemoSeed]) -> Callable[[], SigningKeyTool]:
    """A factory for migrated databases the operator script has never run against.

    A factory rather than one database, for the reason `demo_databases` itself
    exists: a claim about what a *second* `generate` does to rows that are already
    there cannot be posed against a database whose only writer is the thing under
    test (`docs/MISTAKES.md` entry 31). Each call is a whole `alembic upgrade
    head`, so ask for one per scenario and not per assertion.

    **The seed has not run against any of these**, and that is the point of
    criterion 1: the supply path has to work where the development seed does not,
    which is every deployment that is not a developer's laptop.
    """

    def another() -> SigningKeyTool:
        return SigningKeyTool(demo_databases())

    return another
