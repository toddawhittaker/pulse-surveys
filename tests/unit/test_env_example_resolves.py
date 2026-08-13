"""`.env.example` resolves to working values when read — ticket E0-02.

E0-01's acceptance criterion 3 asks that `.env.example` and `Settings` stay in
sync, and `test_env_example_sync.py` holds that. This module holds something
the file only started needing in E0-02: that its values are *usable* once
something reads it. CI does `cp .env.example .env` and starts the stack from
it, so an entry that parses and resolves to nothing is a broken file that looks
fine.

Two families of hazard live here, and both were found on review of E0-02.

**A value that resolves to nothing.** `DATABASE_URL` is built by interpolation
from `DB_APP_USER`, `DB_APP_PASSWORD`, and `DB_NAME`, so that each password is
written once:

    DATABASE_URL=postgresql+psycopg://${DB_APP_USER}:${DB_APP_PASSWORD}@db:5432/${DB_NAME}

python-dotenv substitutes in **file order**. A variable referenced above the
line that declares it resolves to the empty string rather than failing, so
moving the credential block below `DATABASE_URL` yields
`postgresql+psycopg://:@db:5432/` — no user, no password, no database name.

The other reader does not fail with it, and that asymmetry is what makes this
worth a test rather than a comment. Measured, not reasoned about: a reordered
copy of the file through `docker compose --env-file ... config` reports

    DATABASE_URL:      postgresql+psycopg://:@db:5432/   <- lost
    POSTGRES_USER:     pulse_admin                       <- intact
    POSTGRES_PASSWORD: replace-me-admin                  <- intact
    POSTGRES_DB:       pulse                             <- intact

Compose resolves the `${DB_SUPERUSER}` references written *in the compose file*
against the whole environment, so where they sit in `.env` does not matter. Only
the nested expansion inside `.env`'s own `DATABASE_URL` value is top-down, and
only that one is lost. So the database is created with exactly the right
credentials while the application is handed a URL with none. The two readers
disagree silently, nothing in E0-02 opens a connection to notice, and it
surfaces in E0-04 as an authentication error two tickets from the edit that
caused it.

**A value that resolves to the wrong identity.** `.env.example` declares two
database roles, and only one of them may appear in `DATABASE_URL`. That rule
was prose, and repointing the URL at the superuser passed every test in this
repository and every gate in CI.

What is asserted here is the resolved outcome, never the line order and never
the variable names. An ordering assertion would pin a file layout no ticket
chose, and would go on passing against a file broken some other way — a typo'd
reference, a deleted part, a change of interpolation mechanism. Comparing names
rather than values would miss a credential pasted in as a literal. Reordering
and repointing are only today's causes.

python-dotenv is the right reader to test through: `pydantic-settings` uses it
for `env_file`, so this is literally the host path. `docker compose config`
would test the other reader, needs a daemon, and is the `docker` job's business.

**The process environment is cleared first, and that is load-bearing.**
python-dotenv falls back to `os.environ` for a name the file has not defined
yet, so a developer who happens to export `DB_APP_USER` would see a reordered
file resolve perfectly and this suite pass. That is the same trap
`configured_env` in `tests/conftest.py` guards against from the other direction.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from dotenv import dotenv_values

# python-dotenv's interpolation syntax, which is not Compose's — hence a second
# pattern rather than reusing `COMPOSE_INTERPOLATION` from conftest. dotenv
# reads `${NAME}` and `${NAME:-default}` only: a bare `$NAME` is left alone, and
# `$$` is not an escape. Sharing one pattern between the two readers would
# quietly assert that they agree about syntax, and they do not.
DOTENV_REFERENCE = re.compile(r"\$\{(?P<name>[^}:]+)(?::-(?P<default>[^}]*))?\}")


@pytest.fixture
def env_example_environment_cleared(
    monkeypatch: pytest.MonkeyPatch,
    env_example_path: Path,
    documented_env: dict[str, str],
) -> None:
    """Remove every name `.env.example` mentions from the process environment.

    Both the names it declares and the names it references, because a reference
    that resolves out of the ambient environment is exactly the false pass this
    module exists to prevent. Scanning the whole file text over-collects from
    comments; clearing a name nothing reads costs nothing.
    """
    text = env_example_path.read_text(encoding="utf-8") if env_example_path.is_file() else ""
    referenced = {match.group("name") for match in DOTENV_REFERENCE.finditer(text)}
    for name in set(documented_env) | referenced:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def raw_env_example(
    env_example_environment_cleared: None,
    env_example_path: Path,
) -> dict[str, str | None]:
    """`.env.example` parsed with interpolation off, so values are still templates."""
    return dotenv_values(env_example_path, interpolate=False)


@pytest.fixture
def resolved_env_example(
    env_example_environment_cleared: None,
    env_example_path: Path,
) -> dict[str, str | None]:
    """`.env.example` read exactly as `pydantic-settings` reads `.env`."""
    return dotenv_values(env_example_path)


def test_every_interpolation_resolves_where_it_is_used(
    raw_env_example: dict[str, str | None],
    resolved_env_example: dict[str, str | None],
) -> None:
    """An entry built from other entries resolves to the same thing they hold.

    Two ways for that to fail, and the messages tell them apart. A reference to
    a name the file never declares resolves to nothing wherever it appears. A
    reference to a name declared *later* resolves to nothing only at the point
    of use, which is why the second check compares the entry's resolved value
    against its own parts rather than checking those parts in isolation — they
    are perfectly fine by the end of the file, and that is the trap.
    """
    assert raw_env_example, (
        ".env.example parsed to nothing, so there are no interpolations to check. "
        "E0-01 ships it at the repository root (SPEC §13)."
    )

    def substitute(match: re.Match[str]) -> str:
        value = resolved_env_example.get(match.group("name"))
        return value if value else (match.group("default") or "")

    problems: list[str] = []
    for name, template in raw_env_example.items():
        if template is None:
            continue

        for match in DOTENV_REFERENCE.finditer(template):
            referenced = match.group("name")
            if match.group("default") is not None:
                continue
            if not resolved_env_example.get(referenced):
                problems.append(
                    f"{name} references ${{{referenced}}}, which .env.example never "
                    "declares with a value. It resolves to nothing everywhere it appears."
                )

        expected = DOTENV_REFERENCE.sub(substitute, template)
        actual = resolved_env_example.get(name) or ""
        if actual != expected:
            problems.append(
                f"{name} resolves to {actual!r}, but substituting the values its parts "
                f"finally hold gives {expected!r}. python-dotenv substitutes in file "
                "order, so a name referenced above the line that declares it resolves "
                "to the empty string instead of failing."
            )

    assert not problems, "\n".join([".env.example does not resolve to working values:", *problems])


def test_database_url_resolves_to_a_complete_url(
    resolved_env_example: dict[str, str | None],
) -> None:
    """`DATABASE_URL` has a user, a password, a host, and a database name.

    The entry the E0-02 credential design is built around, so it is worth
    asserting in its own right rather than only as an interpolation. This
    catches what the general check above cannot: a template whose *literal*
    parts are wrong, such as a lost `@db:5432` host, where every reference still
    resolves fine and the URL is still unusable.
    """
    url = resolved_env_example.get("DATABASE_URL")
    assert url, (
        ".env.example does not resolve DATABASE_URL to anything. CI runs the stack from "
        "`cp .env.example .env`, so this file has to hold a usable URL."
    )

    parts = urlsplit(url)
    missing = [
        label
        for label, value in (
            ("user", parts.username),
            ("password", parts.password),
            ("host", parts.hostname),
            ("database name", parts.path.lstrip("/")),
        )
        if not value
    ]

    assert not missing, (
        f"DATABASE_URL in .env.example resolves to {url!r}, which has no "
        f"{', no '.join(missing)}. Postgres would refuse the connection, but nothing in "
        "E0-02 opens one, so this reaches E0-04 as an authentication error a long way "
        "from whatever caused it."
    )


def test_database_url_does_not_connect_as_the_superuser(
    resolved_env_example: dict[str, str | None],
) -> None:
    """The application's URL names the application's role, not the administrator's.

    `.env.example` states the rule in prose — "Nothing but administration should
    ever use DB_SUPERUSER, and DATABASE_URL below must never point at it" — and
    Todd's ruling on ADR 0009 is that a superuser role is sanctioned for
    migrations and genuinely-necessary admin work, while day-to-day use stays
    security-scoped. A superuser bypasses every grant and every row-level
    security policy, which is the material SPEC §4.1's identity separation is
    built out of, so an application connecting as one makes that separation
    decorative without changing a line of it.

    Until now the rule was prose alone. Repointing `DATABASE_URL` at the
    superuser passed every test in this repository and left the `docker` job
    green, because the `db` health check authenticates as the application role
    whatever the application itself uses. The sibling rule — that the two roles
    must not share a name — is enforced mechanically in `scripts/db-init`; this
    was the odd one out.

    The comparison is against the resolved *value*, not the variable name, so
    pasting the literal `pulse_admin` into the URL fails here too.
    """
    superuser = resolved_env_example.get("DB_SUPERUSER")
    assert superuser, (
        ".env.example does not resolve DB_SUPERUSER to anything, so this test has no "
        "administrative identity to compare against and would pass whatever DATABASE_URL "
        "names. If the superuser role has genuinely gone, delete this test deliberately "
        "rather than leaving it here asserting nothing."
    )

    url = resolved_env_example.get("DATABASE_URL")
    assert url, ".env.example does not resolve DATABASE_URL to anything."

    assert urlsplit(url).username != superuser, (
        f"DATABASE_URL connects as {superuser!r}, which is the DB_SUPERUSER role. The "
        "application must connect as its own role: a superuser bypasses every grant and "
        "every row-level security policy, so the §4.1 identity separation stops being "
        "enforced by the database while still looking as though it is. Nothing else in "
        "the suite or in CI catches this — the db health check authenticates as the "
        "application role no matter what the application uses."
    )


def test_database_url_does_not_carry_the_superuser_password(
    resolved_env_example: dict[str, str | None],
) -> None:
    """The URL's password is the application role's, not the administrator's.

    Weaker than the test above and worth keeping separate for that reason. A URL
    naming the application role with the administrator's password is a
    misconfiguration rather than an escalation — Postgres refuses it — but it is
    refused at the first connection, which is E0-04, and it invites the fix of
    making the two passwords the same. That would hand the application role the
    administrator's credential for real.
    """
    superuser_password = resolved_env_example.get("DB_SUPERUSER_PASSWORD")
    assert superuser_password, (
        ".env.example does not resolve DB_SUPERUSER_PASSWORD to anything, so this test "
        "has nothing to compare against and would pass whatever DATABASE_URL carries."
    )

    url = resolved_env_example.get("DATABASE_URL")
    assert url, ".env.example does not resolve DATABASE_URL to anything."

    assert urlsplit(url).password != superuser_password, (
        "DATABASE_URL carries the DB_SUPERUSER_PASSWORD value. Whatever role it names, "
        "the credential it presents is the administrator's; the two roles hold separate "
        "passwords so that neither can be reached with the other's."
    )
