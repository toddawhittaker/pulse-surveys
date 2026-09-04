#!/usr/bin/env python3
"""Supply, list and retire this tool's LTI signing keys — ticket E3-01, SPEC §7.3.

An operator runs this against a deployment's database:

    python scripts/signing_key.py generate       # supply a new key, print its kid
    python scripts/signing_key.py list           # every key, live or retired
    python scripts/signing_key.py retire <kid>   # take one key out of the set

`docs/adr/0126` records why the supply path is a command rather than a
configuration variable or a key service, and `docs/adr/0127` records the rotation
rule this spells: the published key set is every row of `tool_signing_key` with
`retired_at IS NULL`, and the tool signs with the newest of those. So a rotation
is `generate`, then a wait long enough for every platform to refetch the key set,
then `retire` on the old key — and `list` is how the state in between is read.

## What it connects as, and why not the obvious thing

The address comes from `DATABASE_URL` and the identity from `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD`, which is exactly what `backend/migrations/env.py` and
`scripts/seed.py` do and for exactly the reason ADR 0012 gives. `DATABASE_URL`
names `pulse_app`, which holds `SELECT` on `tool_signing_key` and no write of any
kind (`tool_signing_key_grants_v001.sql`) — so a version of this script wired to
that credential is refused by Postgres at its first `INSERT`, and the repair that
suggests itself, granting the application role `INSERT` or `UPDATE`, is the thing
ADR 0082 exists to forbid. An application connection that could write this table
could rotate the tool's identity, invisibly, because a fresh key signs perfectly.

**No environment guard.** `scripts/seed.py` refuses to run outside development
(ADR 0063) because what it writes is a demo institution. This is the opposite
script: a deployment that is not development is the only place it is needed, and
the carried entry it closes is exactly that such a deployment had no way to hold
a key.

## Two rules this file is held to

**No key material reaches an output stream.** Not on the success path, not in a
failure, not in a traceback. This runs in a terminal, in a deployment's shell
history and in whatever logs the session, and a private key printed once is in a
scrollback buffer and in whatever gets pasted when somebody asks for help (SPEC
§10, ADR 0082). A driver's parameters are the trap rather than a `print`:
SQLAlchemy's `StatementError` quotes the statement *and its parameters*, so the
insert below never lets one reach an operator. What it prints instead is the
`kid` — the RFC 7638 thumbprint, derived and never stored, which is the only name
an operator or a platform ever says out loud, and the argument `retire` takes.

**This module must never import `app.db`.** That module builds an engine out of a
whole `Settings()` when imported, as the application role, so importing it here
would open a connection this script may not use and demand configuration
variables that say nothing about a key.
"""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.lti.registration import public_jwk
from app.models.lti import ToolSigningKey

# The repository root, from `scripts/signing_key.py`. Named rather than searched
# for, for the reason `backend/migrations/env.py` gives about `find_dotenv()`: a
# script that reads a different `.env` depending on where it was invoked from is
# the kind of thing nobody notices until two databases disagree.
REPO_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = REPO_ROOT / ".env"

# Where the database is, and who is allowed to write this table. The same three
# names `backend/migrations/env.py` and `scripts/seed.py` read, and deliberately
# no fourth of this script's own: a name only this file read could not earn an
# `.env.example` entry (ADR 0008), and `tests/unit/test_env_example_sync.py`
# would say so.
ADDRESS_VARIABLE = "DATABASE_URL"
IDENTITY_VARIABLES = ("DB_SUPERUSER", "DB_SUPERUSER_PASSWORD")

# RSA 2048 in PKCS#8 PEM, unencrypted, as ADR 0082 fixes it and the seed writes
# it. A shorter key loads and signs exactly like a long one and is refused by the
# platforms that check, which is a failure against a real LMS and nowhere before
# it. Unencrypted because the process that reads it has nowhere to get a
# passphrase from; what protects the column is the grant on it.
KEY_BITS = 2048
PUBLIC_EXPONENT = 65537

# The exit statuses this script answers with. `1` is left to an unhandled
# exception so that a crash is never mistaken for a decision; `2` is a refusal
# this file made, and `3` is a database that would not do what it was asked.
REFUSED = 2
DATABASE_REFUSED = 3

# How a listing marks a key. `live` for one in the published set, `retired` for
# one that has left it, on the line that names the key — so a half-finished
# rotation cannot read as two live keys.
LIVE_MARK = "live"
RETIRED_MARK = "retired"


class OperatorError(Exception):
    """A refusal this script decided on, with a sentence an operator can act on.

    Caught in `main`, printed to stderr, and answered with `REFUSED`. A distinct
    type rather than a bare `SystemExit` so that a refusal cannot be confused
    with a crash by anything wrapping this command.
    """


def resolved_configuration(environ: Mapping[str, str], dotenv_path: Path) -> dict[str, str]:
    """`.env` under the process environment, the way every other reader resolves it.

    The process wins over the file, which is the precedence ADR 0008 records.
    Taken as an argument rather than read from `os.environ` here so that what
    this script does is a question about a mapping rather than about the machine
    it is running on.
    """
    from_file = {
        name: value for name, value in dotenv_values(dotenv_path).items() if value is not None
    }
    return {**from_file, **environ}


def database_url(configuration: Mapping[str, str]) -> URL:
    """The database `DATABASE_URL` names, addressed as the bootstrap identity.

    No value is quoted in the failure, for the reason `app.config`,
    `backend/migrations/env.py` and `scripts/seed.py` all give at length: this
    message goes to a terminal and to whatever captured it, and two of the three
    variables carry credentials. Naming them is enough to act on and is all that
    is safe to print.
    """
    address = configuration.get(ADDRESS_VARIABLE, "").strip()
    identity = {name: configuration.get(name, "").strip() for name in IDENTITY_VARIABLES}

    missing = ([ADDRESS_VARIABLE] if not address else []) + [
        name for name, value in identity.items() if not value
    ]
    if missing:
        raise OperatorError(
            "This command cannot reach a database without these variables:\n"
            + "\n".join(f"  {name} — not set" for name in missing)
            + "\nIt connects as the bootstrap superuser identity, which is not the role "
            "DATABASE_URL points at (docs/adr/0009, docs/adr/0012): the application role holds "
            "SELECT on this table and no write at all. DATABASE_URL supplies the host, port and "
            "database; DB_SUPERUSER and DB_SUPERUSER_PASSWORD supply the identity. .env.example "
            "documents all three.\n"
            "No values are shown here on purpose: this message goes to a log."
        )

    return make_url(address).set(
        username=identity["DB_SUPERUSER"],
        password=identity["DB_SUPERUSER_PASSWORD"],
    )


def kid_of(row: ToolSigningKey) -> str:
    """The `kid` a stored key answers to — the RFC 7638 thumbprint of its public half.

    Derived through `app.lti.registration.public_jwk`, which is the same
    derivation the key set publishes and the same one the signer writes into an
    assertion header. A second implementation here would agree until one of them
    changed, and the disagreement would be an operator retiring a key by a name
    no platform knows it by (`docs/MISTAKES.md` entry 19).
    """
    return public_jwk(row.private_key_pem)["kid"]


def stored_keys(session: Session) -> list[ToolSigningKey]:
    """Every row of the table, oldest first, live and retired alike.

    Oldest first because that is the order a rotation happened in, which is the
    order an operator reads it in. Retired rows included: they are the record of
    what this deployment used to sign with, and a listing that hid them would
    leave the state a rotation is halfway through invisible.
    """
    return list(
        session.scalars(
            select(ToolSigningKey).order_by(
                ToolSigningKey.created_at.asc(), ToolSigningKey.id.asc()
            )
        )
    )


def generate(session: Session) -> str:
    """Supply one new key, live from this moment, and answer its `kid`.

    **It adds rather than replaces.** An existing key is left exactly as it is,
    live or retired, because the overlap is the whole point: a rotation needs the
    retiring key and its replacement published together, so that assertions signed
    before the switch still verify while assertions signed after it verify too.
    Replacing the row would be the invisible failure ADR 0082 names — the new key
    signs perfectly, and nothing goes wrong until a platform that already fetched
    the old public half refuses an assertion hours later.

    `created_at` is left to the server default, so the instant recorded is the
    database's rather than this process's, and `retired_at` is left NULL, which is
    what puts the key in the published set.
    """
    key = rsa.generate_private_key(public_exponent=PUBLIC_EXPONENT, key_size=KEY_BITS)
    row = ToolSigningKey(
        private_key_pem=key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
    )
    session.add(row)
    session.flush()
    return kid_of(row)


def retire(session: Session, kid: str) -> None:
    """Take the key `kid` names out of the published set, and leave the row behind.

    **Refuses when nothing answers to that name**, which is the case with the
    incident behind it: an edit that matches nothing exits zero, and the unchanged
    state then reads as the change having been made. Here that means an operator
    who mistypes a thumbprint believes a rotation completed, leaves it half done,
    and the key they meant to retire goes on being published and goes on being
    accepted.

    **Refuses a key that is already retired** rather than moving its timestamp. A
    second retirement is either the same mistyped-thumbprint mistake or a second
    operator repeating work, and rewriting the instant would destroy the only
    record of when the key actually left the set.

    **A `DELETE` would be a different decision.** The row stays as the record of
    what this deployment used to sign with, which is the thing somebody asks for
    at exactly the moment it would be gone.
    """
    for row in stored_keys(session):
        if kid_of(row) != kid:
            continue
        if row.retired_at is not None:
            raise OperatorError(
                f"The key {kid} was already retired at {row.retired_at.isoformat()}, so it is "
                "already out of the published key set. Nothing was changed: rewriting that instant "
                "would destroy the only record of when this key stopped being one a platform "
                "should verify against."
            )
        row.retired_at = datetime.now(UTC)
        return
    raise OperatorError(
        f"No stored key answers to {kid!r}, so nothing was retired. A `kid` is the RFC 7638 "
        "thumbprint of the key's public half — run `list` to see the ones this deployment holds. "
        "Exiting non-zero on purpose: a command that matched nothing and exited 0 would read as a "
        "completed rotation, and the key you meant to retire would go on being published."
    )


def listing(session: Session) -> str:
    """Every stored key, one line each, with no key material anywhere in it.

    The `kid`, when the key was supplied, and whether it is still published. The
    header names the columns and comes before the first key, so the word
    `retired` in it belongs to no key's line.

    An empty table is a sentence rather than a blank answer: a deployment with no
    key answers 503 at `/lti/jwks`, and reading nothing back is exactly the moment
    to be told that.
    """
    rows = stored_keys(session)
    if not rows:
        return (
            "This deployment holds no signing key at all, so it publishes no key set and can sign "
            "nothing. `generate` supplies one."
        )
    lines = [f"{'kid':<45}{'supplied':<28}status"]
    for row in rows:
        mark = (
            LIVE_MARK if row.retired_at is None else f"{RETIRED_MARK} {row.retired_at.isoformat()}"
        )
        lines.append(f"{kid_of(row):<45}{row.created_at.isoformat():<28}{mark}")
    return "\n".join(lines)


def run(session: Session, command: str, kid: str | None) -> str:
    """Do what `command` asks of `session` and answer what to print.

    A single place where the three subcommands meet, so that the transaction, the
    refusals and the output all behave the same way whichever one was asked for.
    """
    if command == "generate":
        return (
            f"Supplied a new signing key. kid: {generate(session)}\n"
            "It is live from now and the tool publishes it at /lti/jwks. A platform verifying an "
            "assertion signed by it needs to have refetched that document."
        )
    if command == "retire":
        if kid is None:
            # Unreachable through the parser, which makes the argument
            # mandatory for this subcommand. Kept because a caller reaching
            # `run` some other way must not fall through to the listing and be
            # told a retirement happened.
            raise OperatorError("`retire` needs the kid of the key to retire.")
        retire(session, kid)
        return (
            f"Retired {kid}. It has left the published key set and its row stays as the record of "
            "what this deployment used to sign with."
        )
    return listing(session)


def parser() -> argparse.ArgumentParser:
    """The command line, which is the interface this ticket documents an operator into."""
    built = argparse.ArgumentParser(
        prog="python scripts/signing_key.py",
        description=(
            "Supply, list and retire this tool's LTI signing keys. Connects as the bootstrap "
            "superuser identity (DB_SUPERUSER/DB_SUPERUSER_PASSWORD) at the address DATABASE_URL "
            "names. Never prints key material."
        ),
    )
    subcommands = built.add_subparsers(dest="command", required=True)
    subcommands.add_parser("generate", help="supply a new signing key and print its kid")
    subcommands.add_parser("list", help="every stored key, live or retired")
    retirement = subcommands.add_parser("retire", help="take one key out of the published set")
    retirement.add_argument("kid", help="the RFC 7638 thumbprint `list` prints for that key")
    return built


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> int:
    """Run one subcommand and answer the exit status an operator reads.

    One transaction per run, committed only where the whole subcommand
    succeeded: a `retire` that refused must leave the table exactly as it found
    it, because a refusal that had already written is worse than either outcome
    alone — the operator reads a failure and the deployment has lost a key from
    its published set.

    The three arguments default to the real thing and exist so that the behaviour
    can be asked about without starting a process in a directory with a
    particular `.env` in it.
    """
    arguments = parser().parse_args(argv)
    configuration = resolved_configuration(
        os.environ if environ is None else environ,
        DOTENV_PATH if dotenv_path is None else dotenv_path,
    )

    try:
        url = database_url(configuration)
    except OperatorError as refused:
        print(refused, file=sys.stderr)
        return REFUSED

    engine = create_engine(url)
    try:
        with Session(bind=engine) as session:
            try:
                answer = run(session, arguments.command, getattr(arguments, "kid", None))
                # Inside the guard, not after it. A commit is the second place a
                # driver error can arrive, and an uncaught one prints a traceback
                # holding whatever SQLAlchemy quoted.
                session.commit()
            except OperatorError as refused:
                session.rollback()
                print(refused, file=sys.stderr)
                return REFUSED
            except Exception as failure:
                # **The message is not printed and this is the whole reason for
                # the branch.** SQLAlchemy wraps a driver error in a
                # `StatementError` whose text quotes the statement *and its bound
                # parameters* — and on the `generate` path one of those
                # parameters is the private key. So what reaches the operator is
                # the type of the failure and what to do about it, and the value
                # stays in the process it was made in (SPEC §10).
                session.rollback()
                print(
                    f"The database refused `{arguments.command}` with "
                    f"{type(failure).__name__}. The message is withheld deliberately: a driver "
                    "error quotes the statement's bound parameters, and on this path one of them "
                    "is a private key. Check that DB_SUPERUSER names the bootstrap identity and "
                    "that the database is migrated to head.",
                    file=sys.stderr,
                )
                return DATABASE_REFUSED
    finally:
        engine.dispose()

    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
