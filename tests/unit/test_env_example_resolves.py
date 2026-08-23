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

**A value that carries the credential to a container that must not hold it**
— E0-19's third route, and the reason this module now reads the Compose files
as well as `.env.example`. The rules in `test_compose_stack.py` follow `${...}`
references: a Compose file naming `${DB_SUPERUSER}`, directly or through
another `.env` entry, fails there. A documented entry whose value carries the
credential as a **literal** —

    ALEMBIC_DATABASE_URL=postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse

— references nothing, so the walk that follows references finds nothing to
follow and every one of those rules passes. `env_file: - .env` then hands that
line to `api`, `worker` and `beat`, because `env_file:` is all-or-nothing. In
CI it is sharper still: the workflow does `cp .env.example .env`, so the
placeholder *is* the value and the pipeline itself would run the superuser
credential in three containers.

What closes it is the comparison this module already makes for `DATABASE_URL`
— resolved values, never names — asked of every variable a Compose file
delivers to a service other than `db`. **That delivered set is computed from
the Compose files** rather than written down here: an inventory has to come
from somewhere the guarded structure cannot shrink (`docs/MISTAKES.md`
entry 35), and a hand-written list of variables to check is a list that a new
`.env.example` entry is not on.

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

import importlib.util
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from dotenv import dotenv_values

# python-dotenv's interpolation syntax, which is not Compose's — hence a second
# pattern rather than reusing `COMPOSE_INTERPOLATION` from conftest. dotenv
# reads `${NAME}` and `${NAME:-default}` only: a bare `$NAME` is left alone, and
# `$$` is not an escape. Sharing one pattern between the two readers would
# quietly assert that they agree about syntax, and they do not.
DOTENV_REFERENCE = re.compile(r"\$\{(?P<name>[^}:]+)(?::-(?P<default>[^}]*))?\}")

# The sibling test module the Compose vocabulary comes from, and the names taken
# out of it. E0-19 asks the question "what does this Compose file deliver to that
# container", which `test_compose_stack.py` already answers for three credential
# rules — `env_file:` in its three spellings, `environment:` in both of its two,
# and the difference between a blanked value and an omitted entry. A second copy
# of those readers here is `docs/MISTAKES.md` entry 3's shape: the copy is the one
# that does not get the next correction, and it goes on reporting a clean file
# over a spelling the original learned about two tickets ago.
#
# Named as data rather than written into an `import` statement, following
# `test_identity_separated_views.py`: a test module importing a sibling test
# module resolves only because of where pytest puts `tests/unit` on `sys.path`,
# so it is one conftest change away from an `ImportError` at *collection* time —
# a red with no test name in it. `compose_stack_module` loads it by path and
# turns every way that can go wrong into a named failing test.
COMPOSE_STACK_MODULE = "test_compose_stack.py"
COMPOSE_STACK_NAMES = (
    "services_of",
    "declares_env_file",
    "service_environment",
    "transitively_read",
    "CREDENTIAL_OWNING_SERVICE",
)


def compose_stack_module() -> Any:
    """`test_compose_stack.py`, loaded by path so a failure has a test's name on it."""
    path = Path(__file__).with_name(COMPOSE_STACK_MODULE)
    if not path.is_file():
        pytest.fail(
            f"{path} does not exist. It is where this repository's reading of a Compose file "
            "lives — which services inherit the whole of `.env`, what an `environment:` entry "
            "means in each of its spellings, and which single service may hold the superuser "
            "credential. If it has moved, this constant moves with it; if it has been deleted, "
            "the rule below has no notion of what a container is handed."
        )

    spec = importlib.util.spec_from_file_location("e0_19_compose_vocabulary", path)
    if spec is None or spec.loader is None:
        pytest.fail(
            f"Python could not build an import spec for {path}, so the rule below has no way to "
            "read a Compose file and would have nothing to report."
        )

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as failure:
        pytest.fail(
            f"Executing {path} raised {failure!r}. That module is a test module and is expected "
            "to import cleanly at collection; read the error first — it is a fact about that "
            "module rather than about `.env.example`."
        )

    missing = [name for name in COMPOSE_STACK_NAMES if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"{path} no longer defines {missing}. The rule below borrows its reading of a "
            "Compose file from there rather than keeping a second copy, so a renamed helper is "
            "a change to make in both places — not a reason to copy the reader back."
        )

    return module


def delivered_values(
    documents: tuple[tuple[Path, dict[str, Any]], ...],
    resolved: Mapping[str, str],
    walker: Callable[[Any], set[str]],
    exempt: str | None,
) -> dict[tuple[str, str, str], str]:
    """What each service is handed, keyed by (file, service, variable).

    The value is the text a container can end up holding for that variable: the
    literal the Compose file writes, plus the resolved `.env.example` value of
    every name that literal reads, joined by newlines so that nothing is a
    substring of the join rather than of a value. It over-approximates in one
    direction only — it can hold text a different file would have overridden,
    and it cannot miss text that is delivered.

    Three deliveries, and the difference between them is the whole rule:

      - `env_file: - .env` hands over **every documented name** with its
        documented value. Compose has no way to hand a container part of a file.
      - an `environment:` entry with a value **adds or overrides** one name.
        A bare name with no value is this case too, not a blanking: it tells
        Compose to pass the variable through from the host environment, which is
        where the real credential lives, and the documented placeholder is the
        best evidence available here of what arrives.
      - an `environment:` entry with an **empty value delivers nothing** for
        that name, spelled exactly as the entry spells it. That is what the
        blanking lines in `x-application-environment` are, and treating them as
        a delivery would report every application service as holding the
        superuser pair.

    Which file a name is delivered in is kept in the key rather than merged
    away, for the reason the rest of this suite reads the two files separately:
    merging is what `docker compose config` does, and it is what hides the
    difference between what every deployment runs and what a laptop runs.

    `exempt` is a service name skipped entirely — `db`, which is the one service
    ADR 0009 allows to hold the superuser credential. Passing `None` exempts
    nothing, which is how the control below asks what `db` receives; a reader
    that cannot find the credential arriving *there* cannot tell an absence from
    a blindness anywhere else.

    **Names are case-sensitive here, and that is a repair rather than a
    preference.** This function upper-cased every name it saw until E0-19's
    security review, on the reasonable-looking ground that `.env.example` writes
    them all in capitals. Environment variables are not case-insensitive and
    Compose does not fold them: measured, a lower-case `alembic_database_url: ''`
    withdrew the upper-case `ALEMBIC_DATABASE_URL` from this accounting while the
    container went on receiving it from `env_file:` — a blanking line that blanks
    nothing, reading here as a withheld credential. A blank now withdraws exactly
    the spelling it is written in, and an `environment:` entry is its own
    delivery under its own exact name: two variables differing only in case are
    two variables, in the container and here.

    The second map below is the one concession to case and it is not about
    delivery. `interpolated_variables` upper-cases the names it returns, by its
    own contract in `conftest.py`, so resolving a `${...}` reference has to look
    up a folded key. Delivery is accounted in the exact spelling; references are
    resolved through the folded copy. Keeping the two apart is what stops the
    folding leaking back into the accounting.
    """
    compose = compose_stack_module()
    values = {name: text or "" for name, text in resolved.items()}
    referenced = {name.upper(): text for name, text in values.items()}
    delivered: dict[tuple[str, str, str], str] = {}

    for path, document in documents:
        for service, body in compose.services_of(document).items():
            if exempt is not None and service == exempt:
                continue

            if compose.declares_env_file(body):
                for name, text in values.items():
                    delivered[(path.name, service, name)] = text

            for name, declared in compose.service_environment(body).items():
                if declared is not None and not declared.strip():
                    delivered.pop((path.name, service, name), None)
                    continue

                literal = "" if declared is None else declared
                read = compose.transitively_read(literal, walker, referenced)
                if declared is None:
                    # Passed through from the host environment: the name itself
                    # is what arrives, and the documented value stands in for it.
                    read = read | {name.upper()}
                delivered[(path.name, service, name)] = "\n".join(
                    [literal, *(referenced.get(other, "") for other in sorted(read))]
                )

    return delivered


def credential_deliveries(
    documents: tuple[tuple[Path, dict[str, Any]], ...],
    resolved: Mapping[str, str],
    walker: Callable[[Any], set[str]],
    credentials: tuple[tuple[str, str], ...],
    exempt: str | None,
) -> list[str]:
    """Deliveries whose value carries one of `credentials` as a substring, one per line.

    The same comparison the `DATABASE_URL` tests above make — against the
    resolved value, never against the variable's name — generalised to the whole
    delivered set. A name comparison misses a credential pasted in as a literal,
    which is the route this exists to close.
    """
    problems: list[str] = []
    for (file_name, service, variable), text in sorted(
        delivered_values(documents, resolved, walker, exempt).items()
    ):
        for label, secret in credentials:
            if secret and secret in text:
                problems.append(
                    f"{file_name}: `{service}` is handed {variable}, whose value carries "
                    f"{label} ({secret!r})"
                )
    return problems


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


# The five settings E0-39 makes required. Until ADR 0077 they carried defaults
# naming the development stack, so an entry here that resolved to nothing was
# invisible — the field simply fell back. Now it is the difference between a stack
# that comes up and one that refuses to, in every process that builds `Settings`,
# because CI does `cp .env.example .env` and the containers read it.
OIDC_URL_VARIABLES = (
    "OIDC_ISSUER",
    "OIDC_AUTHORIZATION_ENDPOINT",
    "OIDC_TOKEN_ENDPOINT",
    "OIDC_JWKS_URL",
)
OIDC_CLIENT_ID_VARIABLE = "OIDC_CLIENT_ID"


def test_the_identity_provider_entries_resolve_to_usable_values(
    resolved_env_example: dict[str, str | None],
) -> None:
    """The web door's five settings resolve to something a process can start with.

    The same question this module asks of `DATABASE_URL`, asked of the entries
    E0-39 turns from defaulted into required. It is worth asking separately from the
    general interpolation rule above for the reason the `DATABASE_URL` test gives:
    that rule catches a reference that resolves to nothing, and this one catches a
    *literal* that is incomplete — a scheme with no host, or an entry emptied by
    somebody moving the values into `docker-compose.yml` and taking them out of here
    on the way past.

    **What changed is the consequence, not the file.** These entries are already
    here; until ADR 0077 a missing one fell back to a default naming `mock-idp`, so
    the file could be wrong and the stack would still start — quietly pointed at the
    mock. Now every process that builds `Settings` refuses, and CI's
    `cp .env.example .env` makes this file the thing that decides it.

    **The mutation this kills:** any of the five deleted from `.env.example`, or
    left with an empty value, while `app.config` requires it.

    Nothing here asserts what the values *are*. The two horizons — a browser-facing
    `localhost` and a server-facing service name — are ADR 0075's decision and
    ADR 0077 leaves that half standing; a test pinning the strings would turn a
    change of development port into a test edit, and
    `tests/unit/test_oidc_provider_configuration.py` owns which values are refused
    where.
    """
    assert resolved_env_example, (
        ".env.example is missing or resolved to nothing, so every entry below would be reported "
        "absent and this test would be about the file rather than about these five entries."
    )

    problems: list[str] = []
    for name in OIDC_URL_VARIABLES:
        url = resolved_env_example.get(name)
        if not url:
            problems.append(f"{name} resolves to nothing")
            continue
        parts = urlsplit(url)
        missing = [
            label
            for label, value in (("scheme", parts.scheme), ("host", parts.hostname))
            if not value
        ]
        if missing:
            problems.append(f"{name} resolves to {url!r}, which has no {', no '.join(missing)}")

    client_id = resolved_env_example.get(OIDC_CLIENT_ID_VARIABLE)
    if not client_id:
        problems.append(f"{OIDC_CLIENT_ID_VARIABLE} resolves to nothing")

    assert not problems, "\n".join(
        [
            ".env.example does not resolve the identity provider configuration:",
            *problems,
            "",
            "E0-39 makes these five required — `Settings()` refuses to build without them, in "
            "`api` and in every other process that constructs one — so an entry that resolves to "
            "nothing is a stack that does not start. CI copies this file to `.env` and brings "
            "the stack up from it, which is where that would first be seen.",
        ]
    )


# ---------------------------------------------------------------------------
# What the Compose files deliver out of this file — ticket E0-19, route 3.
#
# Everything above asks whether `.env.example` resolves to working values.
# Everything below asks a different question of the same resolved values: which
# of them reach a container that ADR 0009 says must not hold the superuser
# credential. The comparison is the one this module already makes for
# `DATABASE_URL` — resolved value, never variable name — and the set it is made
# over is computed from the Compose files rather than written down.
# ---------------------------------------------------------------------------

# The sample project directory the boundary tests below pretend to live in.
# Nothing on disk; only the file *name* is read, because that is what the
# delivered set is keyed by.
SAMPLE_COMPOSE_PATH = Path("/srv/pulse/docker-compose.yml")

# The two credentials, spelled as literals rather than read from `.env.example`,
# for the boundary tests below only. The rules over the real files take them
# from the file, because the file is what CI copies to `.env`; a sample that did
# the same would be asserting against whatever the placeholder happens to be and
# would go quiet the day somebody changed it.
SAMPLE_CREDENTIALS = (
    ("the superuser role name", "pulse_admin"),
    ("the superuser password", "replace-me-admin"),
)


def superuser_credentials(resolved: dict[str, str | None]) -> tuple[tuple[str, str], ...]:
    """The two values ADR 0009 bounds, labelled, as `.env.example` resolves them."""
    return (
        ("the superuser role name (DB_SUPERUSER)", resolved.get("DB_SUPERUSER") or ""),
        (
            "the superuser password (DB_SUPERUSER_PASSWORD)",
            resolved.get("DB_SUPERUSER_PASSWORD") or "",
        ),
    )


def test_no_documented_value_carries_the_superuser_credential_to_an_application_service(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
    resolved_env_example: dict[str, str | None],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """E0-19 route 3: the credential does not reach a container as a literal.

    The rules in `test_compose_stack.py` follow `${...}` references and would
    catch `ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:...` in a Compose
    file, or one hop further out through an `.env.example` entry built from the
    pair. A documented entry that carries the credential *spelled out* refers to
    nothing, so those rules have nothing to follow and pass — while
    `env_file: - .env` hands the line to `api`, `worker` and `beat`, and CI's
    `cp .env.example .env` makes the placeholder the real value.

    The mutation this must kill is one line in `.env.example`: any documented
    entry that `env_file:` delivers, with `pulse_admin` or `replace-me-admin`
    written into its value. Two near misses say what the rule is not. Putting
    the same text in an entry that every application service *blanks* —
    `DB_CARE_PASSWORD`, say — must stay green, because a blanked variable is not
    delivered. And the check is over values rather than names, so renaming the
    variable changes nothing.

    Both files, for the reason the credential rules give: a value written in
    either is a value some container gets, and the two are never merged here.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse delivers "
            "nothing to anybody, and a rule about what is delivered reports it clean."
        )
    assert resolved_env_example, (
        ".env.example is missing or resolved to nothing, so every delivered value is the empty "
        "string and nothing can carry a credential. E0-01 ships it at the repository root."
    )

    compose = compose_stack_module()
    credentials = superuser_credentials(resolved_env_example)
    for label, value in credentials:
        assert value, (
            f".env.example does not resolve {label} to anything, so this rule has nothing to "
            "search for and would report every file clean. If the superuser identity has "
            "genuinely gone, that is an amendment to ADR 0009 and a deliberate edit here."
        )

    # Names as `.env.example` spells them. Nothing folds case on the way in:
    # `delivered_values` accounts deliveries in the exact spelling, and folding
    # here would put back the defect that function's docstring records.
    resolved = {name: text or "" for name, text in resolved_env_example.items()}
    problems = credential_deliveries(
        documents,
        resolved,
        interpolated_variables_in,
        credentials,
        exempt=compose.CREDENTIAL_OWNING_SERVICE,
    )

    assert not problems, "\n".join(
        [
            "A Compose file delivers the superuser credential to a service that must not hold "
            "it (ADR 0009):",
            *problems,
            "",
            "It does not matter which variable carries it or whether any `${...}` is involved: "
            "`env_file:` is all-or-nothing, so a documented entry with the credential written "
            "into its value reaches every service that inherits the file. CI copies this file "
            "to `.env`, so the placeholder is the value there. `db:5432` is reachable from all "
            "of those containers and its pg_hba.conf accepts that role over scram, and the role "
            "bypasses every grant and every row-level security policy. Blank the variable on "
            "the services that must not hold it, or build the value out of a role that is not "
            "the superuser.",
        ]
    )


def test_the_delivery_reader_finds_the_superuser_credential_reaching_the_database_service(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    resolved_env_example: dict[str, str | None],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """A control: the reader can see a delivery, on the one service that has one.

    **A red here means these tests are broken, not the Compose files.** The rule
    above reports absence, and a reader that finds nothing at all reports the
    same absence — a `services:` key read under the wrong name, an `env_file:`
    spelling it does not know, a resolved map that came back empty. So it is
    required to *find* the credential where the credential certainly is
    (`docs/MISTAKES.md` entry 35).

    `db` is that service, and the sharper half of the entry's rule is why this
    control is worth its lines: the role the whole scheme is built around holds
    its credential in the way least like the ordinary one. `db` receives no
    `.env` at all — it takes the pair by explicit interpolation into
    `POSTGRES_USER` and `POSTGRES_PASSWORD`, which are names `.env.example` does
    not document. A reader written to check documented names against documented
    values would find nothing here and would have been blind to exactly the
    delivery that is real.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing, so this control has no "
        "document to find anything in."
    )

    compose = compose_stack_module()
    # Names as `.env.example` spells them. Nothing folds case on the way in:
    # `delivered_values` accounts deliveries in the exact spelling, and folding
    # here would put back the defect that function's docstring records.
    resolved = {name: text or "" for name, text in resolved_env_example.items()}
    credentials = superuser_credentials(resolved_env_example)
    for label, value in credentials:
        assert value, f".env.example does not resolve {label} to anything."

    delivered = delivered_values(
        ((base_compose_path, base_compose),),
        resolved,
        interpolated_variables_in,
        exempt=None,
    )
    owner = compose.CREDENTIAL_OWNING_SERVICE
    to_owner = {
        variable: text for (_, service, variable), text in delivered.items() if service == owner
    }

    assert to_owner, (
        f"The reader says `{owner}` is handed nothing at all. It is the one service ADR 0009 "
        "allows to hold the superuser credential and the one that certainly does — so a reader "
        "that cannot see this delivery cannot tell a clean file from a file it failed to read."
    )
    for label, value in credentials:
        carrying = sorted(variable for variable, text in to_owner.items() if value in text)
        assert carrying, (
            f"The reader does not see {label} reaching `{owner}`, which receives it as "
            f"`POSTGRES_USER`/`POSTGRES_PASSWORD` by explicit interpolation. It found "
            f"{sorted(to_owner)}. A reader phrased over documented names only is blind to this "
            "delivery, because those two names are Postgres's rather than this file's."
        )


def test_the_delivery_reader_sees_what_the_env_file_hands_the_api_service(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    documented_env: dict[str, str],
    resolved_env_example: dict[str, str | None],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """A control: `env_file:` delivery is seen, and the checked set is not hand-listed.

    **A red here means these tests are broken, not the Compose files.** The
    second currency a variable arrives in, and the one the rule above is mostly
    made of: `api` names two variables in its own `environment:` block and
    receives the rest of the configuration surface through `env_file: - .env`.

    The second assertion is E0-19's criterion that the checked set is derived
    from the Compose files rather than written down. `AI_PROVIDER_BASE_URL`
    appears in no Compose file — that is asserted here rather than assumed — and
    is delivered to `api` all the same, which is a thing no hand-written list of
    interesting variables would have on it and no name-matching reader would
    find.
    """
    assert base_compose and documented_env, (
        "The base Compose file or .env.example is missing or parsed to nothing, so this control "
        "has nothing to read."
    )

    # Names as `.env.example` spells them. Nothing folds case on the way in:
    # `delivered_values` accounts deliveries in the exact spelling, and folding
    # here would put back the defect that function's docstring records.
    resolved = {name: text or "" for name, text in resolved_env_example.items()}
    delivered = delivered_values(
        ((base_compose_path, base_compose),),
        resolved,
        interpolated_variables_in,
        exempt=None,
    )
    to_api = {variable for (_, service, variable), _ in delivered.items() if service == "api"}

    assert "DATABASE_URL" in to_api, (
        f"The reader says `api` is handed {sorted(to_api)}, which does not include "
        "DATABASE_URL — the one variable `api` names in its own `environment:` block with a "
        "value in it. A reader that cannot see that cannot see any delivery."
    )

    inherited = "AI_PROVIDER_BASE_URL"
    assert inherited in documented_env, (
        f"{inherited} is no longer documented in .env.example, so it cannot stand for 'a "
        "variable delivered by env_file and named in no Compose file'. Pick another documented "
        "entry that no Compose file interpolates and put it here."
    )
    assert inherited not in interpolated_variables_in(base_compose), (
        f"{inherited} is now interpolated in docker-compose.yml, so it no longer demonstrates "
        "anything about a set computed rather than hand-listed. Pick another documented entry "
        "that no Compose file names."
    )
    assert inherited in to_api, (
        f"The reader does not see {inherited} reaching `api`. It is delivered by "
        "`env_file: - .env`, which hands over the whole file, and it is named nowhere in any "
        "Compose file — so a reader that finds it is reading the delivery, and one that misses "
        "it is reading a list of names somebody wrote down."
    )


def test_a_blanked_variable_is_not_delivered_to_the_service_that_blanks_it(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    documented_env: dict[str, str],
    resolved_env_example: dict[str, str | None],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The pair to the two controls above: a blank removes a variable from the set.

    Without this direction, a reader that reported every documented name as
    delivered to every service would satisfy both controls — and would then fail
    the rule above on `DB_SUPERUSER` itself, which is delivered by `env_file:`
    and taken back out by the anchor's blanking lines. The absence asserted here
    is meaningful precisely because the two controls above prove the reader is
    not blind, and because the name is asserted to be documented first: this is
    a variable that exists, is handed over, and is withdrawn.
    """
    assert base_compose, f"{base_compose_path} does not exist or declares nothing."
    assert "DB_SUPERUSER" in documented_env, (
        ".env.example no longer documents DB_SUPERUSER, so `env_file:` delivers nothing under "
        "that name and its absence below would mean nothing at all."
    )

    # Names as `.env.example` spells them. Nothing folds case on the way in:
    # `delivered_values` accounts deliveries in the exact spelling, and folding
    # here would put back the defect that function's docstring records.
    resolved = {name: text or "" for name, text in resolved_env_example.items()}
    delivered = delivered_values(
        ((base_compose_path, base_compose),),
        resolved,
        interpolated_variables_in,
        exempt=None,
    )

    assert ("docker-compose.yml", "api", "DB_SUPERUSER") not in delivered, (
        "The reader says `api` is handed DB_SUPERUSER. `x-application-environment` sets it to "
        "an empty string, which is what removes what `env_file:` set — if a blank counts as a "
        "delivery, every application service reads as holding the superuser credential and the "
        "rule above fails on the stack doing the right thing."
    )


def test_a_documented_value_carrying_the_credential_is_caught_when_a_service_inherits_env(
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The literal route, on a document written here rather than in the repository.

    The exact line E0-04 is going to want, and the one every reference-following
    rule in this repository passes:

        ALEMBIC_DATABASE_URL=postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse

    documented in `.env.example`, delivered to `worker` because `worker`
    declares `env_file:`. Nothing in it refers to `${DB_SUPERUSER}`, so the
    walkers in `test_compose_stack.py` have nothing to follow.

    The mutation this kills is a rule that compares variable *names* against
    `SUPERUSER_VARIABLES`, which is the shape the rest of that module uses and
    which is right there for anyone tidying this one.
    """
    documents = ((SAMPLE_COMPOSE_PATH, {"services": {"worker": {"env_file": [".env"]}}}),)
    resolved = {
        "ALEMBIC_DATABASE_URL": "postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse"
    }

    problems = credential_deliveries(
        documents, resolved, interpolated_variables_in, SAMPLE_CREDENTIALS, exempt="db"
    )

    assert problems, (
        "A documented entry with the superuser credential written into its value was not "
        "reported, although `worker` inherits the whole file. `env_file:` is all-or-nothing: "
        "the line reaches the container whatever the variable is called."
    )
    assert any(
        "ALEMBIC_DATABASE_URL" in problem for problem in problems
    ), f"The report does not name the variable that carries the credential: {problems!r}."


# The near miss for the test above — the same document with the variable blanked,
# which must stay green — is
# `test_an_exact_case_blank_withdraws_the_delivery` at the end of this module. It
# was a test of its own here until E0-19's security review found the
# case-sensitivity defect, which needed the same document under two spellings;
# keeping both would have been the identical assertion written twice, and the
# pair reads better where the spelling that defeats it is beside it.


def test_a_literal_credential_written_into_a_compose_environment_entry_is_caught(
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The same literal, written in the Compose file rather than in `.env.example`.

    A service that declares no `env_file:` at all and writes the connection out
    by hand — which is how `mock-lms` and `mock-idp` are configured today, so it
    is the local idiom rather than a hypothetical. There is no `${...}` in it,
    so the interpolation walkers see nothing, and the variable is not documented
    anywhere, so nothing compares its value either.

    The mutation this kills is a rule that only reads documented names: the
    delivered set has to include what an `environment:` block adds, not only
    what `env_file:` hands over.
    """
    documents = (
        (
            SAMPLE_COMPOSE_PATH,
            {
                "services": {
                    "worker": {
                        "environment": {
                            "ALEMBIC_DATABASE_URL": (
                                "postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse"
                            )
                        }
                    }
                }
            },
        ),
    )

    problems = credential_deliveries(
        documents, {}, interpolated_variables_in, SAMPLE_CREDENTIALS, exempt="db"
    )

    assert problems, (
        "A Compose `environment:` entry with the superuser credential written into it as a "
        "literal was not reported. Nothing in that line interpolates anything, so every "
        "reference-following rule in this repository passes it, and the container holds a "
        "working superuser connection."
    )


# The blanking line and the delivery it is meant to withdraw, spelled two ways.
# `.env.example` writes every name in capitals, and a Compose `environment:`
# block may write anything at all — Compose folds neither, and neither does the
# container.
BLANKED_VARIABLE = "ALEMBIC_DATABASE_URL"
CREDENTIAL_BEARING_VALUE = "postgresql+psycopg://pulse_admin:replace-me-admin@db:5432/pulse"


def env_file_service_blanking(spelling: str) -> tuple[tuple[Path, dict[str, Any]], ...]:
    """A one-service document: the whole of `.env`, with `spelling` blanked."""
    return (
        (
            SAMPLE_COMPOSE_PATH,
            {
                "services": {
                    "worker": {
                        "env_file": [".env"],
                        "environment": {spelling: ""},
                    }
                }
            },
        ),
    )


def test_a_lower_case_blank_does_not_withdraw_the_upper_case_delivery(
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """E0-19's security review: environment variable names are case-sensitive.

    Measured against the guard rather than read out of it. `env_file: - .env`
    delivers `ALEMBIC_DATABASE_URL`; a blanking line spelled
    `alembic_database_url: ''` beside it withdraws nothing — the container
    receives both, the upper-case one with the credential in it — and this rule
    reported the service clean, because the accounting folded the two names
    together and let the lower-case blank cancel the upper-case delivery.

    That is worse than a missed route. It is a line that *looks* like the fix
    ADR 0009 asks for, and reads as one in review, while delivering the
    credential; the blanking lines in `x-application-environment` are exactly
    this shape, so a reader that folds case cannot tell one of them from a
    typo that undoes it.

    The mutation this kills is the fold itself — `name = spelled.upper()` in
    `delivered_values`, which is what the code said before this round. The pair
    to it is the test below: an exact-case blank must still withdraw, or the
    repair would be "stop treating blanks as withdrawals", which fails the real
    stack on the anchor doing its job.
    """
    documents = env_file_service_blanking(BLANKED_VARIABLE.lower())
    resolved = {BLANKED_VARIABLE: CREDENTIAL_BEARING_VALUE}

    problems = credential_deliveries(
        documents, resolved, interpolated_variables_in, SAMPLE_CREDENTIALS, exempt="db"
    )

    assert problems, (
        f"`{BLANKED_VARIABLE.lower()}: ''` was read as withdrawing {BLANKED_VARIABLE}. They are "
        "two different variables: Compose passes both to the container, `env_file:` supplies "
        "the upper-case one with the credential in it, and the blank cancels a delivery nobody "
        "made. A blanking line that blanks nothing must not read as a withheld credential."
    )
    assert any(
        BLANKED_VARIABLE in problem for problem in problems
    ), f"The report does not name the variable that was delivered: {problems!r}."


def test_an_exact_case_blank_withdraws_the_delivery(
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The pair: a blank spelled the way the file spells it does withdraw. A control.

    **A red here means these tests are broken, not the Compose files.** The test
    above says a blank in the wrong case withdraws nothing; without this half,
    the cheapest way to satisfy it is to stop treating any blank as a
    withdrawal — which fails the real stack, where
    `x-application-environment` blanks four variables on three services and
    every one of those lines is doing exactly what ADR 0009 asks.

    Same document, same delivery, one spelling different.
    """
    documents = env_file_service_blanking(BLANKED_VARIABLE)
    resolved = {BLANKED_VARIABLE: CREDENTIAL_BEARING_VALUE}

    problems = credential_deliveries(
        documents, resolved, interpolated_variables_in, SAMPLE_CREDENTIALS, exempt="db"
    )

    assert not problems, "\n".join(
        [
            "A variable blanked under its own exact name was still reported as delivered:",
            *problems,
            "",
            "`environment:` beats `env_file:` and an empty value is what removes what the file "
            "set. If this has stopped being true, the blanking lines in the real stack are all "
            "reported as deliveries and the rule fails on the stack doing the right thing.",
        ]
    )
