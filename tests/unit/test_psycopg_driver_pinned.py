"""The driver the connection URL names is installed and pinned — ticket E0-04.

E0-04's scope opens with it:

> Pin the `psycopg` driver package. E0-01 shipped `SQLAlchemy` and `alembic`
> without it, and both `.env.example` and the `migration-drift` job already name
> a `postgresql+psycopg://` URL — so nothing can open a connection until this
> ticket adds the driver. Raised by the E0-01 security review.

Two separate things, and each fails in its own way. A missing driver is a
`ModuleNotFoundError` the first time anything calls `create_engine`, which is
late: `.env.example` and the CI job have named `+psycopg` since E0-01, so the
URL looks settled and the failure arrives in whichever ticket first connects. A
floating version is a supply-chain matter — CLAUDE.md requires exact pins and
committed lockfiles, and `docs/adr/0005-dependency-locking.md` makes
`requirements.txt` the hash-verified closure derived from these declarations.

The dialect is read out of `.env.example` rather than written down here, so this
tests the driver the project has actually documented. If that entry changes to
`postgresql+asyncpg`, this module starts asking about asyncpg without being
edited — which is the point. What it must never do is pass because the URL it
looked at was not there.
"""

import tomllib
from pathlib import Path

# A URL with no server behind it. `create_engine` resolves and imports the DBAPI
# without connecting, so this asks "is the driver installed" and nothing else.
UNCONNECTABLE_HOST = "localhost"
PLACEHOLDER_ROLE = "nobody"
PLACEHOLDER_CREDENTIAL = "not-a-credential"
PLACEHOLDER_DATABASE = "nothing"


def declared_dependencies(pyproject_path: Path) -> list[str]:
    """Every runtime dependency `pyproject.toml` declares, as written."""
    if not pyproject_path.is_file():
        return []
    document = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = document.get("project", {}).get("dependencies", [])
    return [entry for entry in dependencies if isinstance(entry, str)]


def distribution_name(requirement: str) -> str:
    """The distribution a requirement names, without its extras or version."""
    name = requirement.split(";", 1)[0].strip()
    for separator in ("[", "=", "<", ">", "!", "~", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower()


def test_the_driver_the_documented_url_names_can_be_loaded(
    documented_env: dict[str, str],
) -> None:
    """`postgresql+psycopg://` resolves to an installed DBAPI.

    `create_engine` imports the driver as it builds the engine and never opens a
    socket, so a URL pointing at nothing is enough to answer the question. The
    dialect is taken from the documented `DATABASE_URL`, and the entry is
    required to be there first: reading a dialect out of a missing entry would
    give an empty string, and an empty dialect is a different failure with a
    less useful message.
    """
    from sqlalchemy import create_engine

    documented_url = documented_env.get("DATABASE_URL", "")
    assert "://" in documented_url, (
        ".env.example documents no DATABASE_URL, so there is no dialect to check and this "
        "test would be asking about a driver nothing names."
    )

    dialect = documented_url.split("://", 1)[0]
    engine = create_engine(
        f"{dialect}://{PLACEHOLDER_ROLE}:{PLACEHOLDER_CREDENTIAL}"
        f"@{UNCONNECTABLE_HOST}:5432/{PLACEHOLDER_DATABASE}"
    )

    assert engine.dialect.dbapi is not None, (
        f"The `{dialect}` dialect resolved without a DBAPI module, so nothing here can open "
        "a connection."
    )


def test_pyproject_pins_the_driver_exactly() -> None:
    """The driver is a declared, exactly-pinned runtime dependency.

    Runtime and not dev: the API, the worker and beat all connect, so the driver
    ships in the image rather than only in the test environment.

    Exactly pinned, because CLAUDE.md allows no floating ranges and because
    `make lock` derives the hash-verified `requirements.txt` from this list —
    a range here means the closure can move without a diff that says so.
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    dependencies = declared_dependencies(pyproject_path)

    assert dependencies, (
        f"{pyproject_path} declares no runtime dependencies, so this test has nothing to "
        "look through and would report a missing driver whatever the truth is."
    )

    driver = [entry for entry in dependencies if distribution_name(entry).startswith("psycopg")]
    assert driver, (
        f"No psycopg distribution is declared in {pyproject_path} (it declares "
        f"{sorted(distribution_name(entry) for entry in dependencies)}). `.env.example` and "
        "the `migration-drift` job have both named a `postgresql+psycopg://` URL since "
        "E0-01, so until it is declared nothing in the project can open a connection."
    )

    unpinned = [entry for entry in driver if "==" not in entry]
    assert not unpinned, (
        f"The psycopg dependency is not pinned to an exact version: {unpinned}. CLAUDE.md "
        "allows no floating ranges, and `requirements.txt` is compiled from this list — a "
        "range lets the driver that ships change without a diff that names the change."
    )
