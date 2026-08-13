"""`.env.example` and `Settings` stay in sync — ticket E0-01, acceptance criterion 3.

"`.env.example` has one entry per `Settings` field; a test asserts the two are
in sync so a new setting cannot be added without documenting it."

Both directions are asserted: a `Settings` field with no `.env.example` entry
fails, and an `.env.example` entry that nothing reads fails. The second
direction is what stops the file from rotting into a list of variables the
application stopped reading two tickets ago.

"Nothing reads it" is not the same rule as "no `Settings` field reads it", and
this module asserted the second one until dispute E0-02-01 separated them. From
E0-02, `.env` has two readers: `Settings`, and Compose, which needs `DB_USER`,
`DB_PASSWORD`, and `DB_NAME` as discrete values because it cannot parse the
`DATABASE_URL` it builds from them. Those entries are read on both paths, so
calling them abandoned was false.

The reader is established mechanically rather than by an allowlist of names: an
entry passes if a `Settings` field reads it, or if a Compose file interpolates
it. A list of exempt names would go on vouching for `DB_NAME` after
`docker-compose.yml` stopped using it, which is the rot this direction exists to
catch, so an exemption that no longer corresponds to a reader has to expire by
itself. E0-14 and E0-16 add readers to the Compose files and need no edit here.

The mapping from a field to its environment variable is `pydantic-settings`
behaviour, not an implementation choice: the explicit alias if the field has
one, otherwise the configured `env_prefix` plus the field name. Comparison is
case-insensitive, so `case_sensitive` either way is fine.
"""

from pathlib import Path


def load_settings_class() -> type:
    """Import `Settings` inside the test, so a missing module fails one test loudly."""
    from app.config import Settings

    return Settings


def env_variable_candidates(settings_cls: type) -> dict[str, set[str]]:
    """Map each `Settings` field to the environment variable names it would read."""
    config = getattr(settings_cls, "model_config", None) or {}
    prefix = config.get("env_prefix", "") or ""

    candidates: dict[str, set[str]] = {}
    for field_name, field in settings_cls.model_fields.items():
        alias = field.validation_alias if field.validation_alias is not None else field.alias
        names: set[str] = set()
        if isinstance(alias, str):
            names.add(alias.upper())
        elif alias is not None:
            names.update(
                choice.upper()
                for choice in getattr(alias, "choices", ())
                if isinstance(choice, str)
            )
        if not names:
            names.add(f"{prefix}{field_name}".upper())
        candidates[field_name] = names
    return candidates


def test_env_example_exists_and_documents_variables(env_example_path: Path) -> None:
    """The configuration documentation the ticket requires is present and non-empty."""
    assert env_example_path.is_file(), (
        f"{env_example_path} does not exist. E0-01 requires `.env.example` at the "
        "repository root as the configuration documentation (SPEC §13)."
    )
    lines = [line.strip() for line in env_example_path.read_text(encoding="utf-8").splitlines()]
    assert any(
        "=" in line and not line.startswith("#") for line in lines
    ), f"{env_example_path} documents no variables."


def test_every_settings_field_is_documented_in_env_example(
    documented_env: dict[str, str],
) -> None:
    """A new `Settings` field with no `.env.example` entry fails here."""
    settings_cls = load_settings_class()
    documented = {name.upper() for name in documented_env}

    undocumented = sorted(
        field_name
        for field_name, names in env_variable_candidates(settings_cls).items()
        if not (names & documented)
    )

    assert not undocumented, (
        f"Settings fields with no .env.example entry: {undocumented}. Every setting is "
        "documented in .env.example, with a placeholder value only."
    )


def test_every_env_example_variable_has_a_reader(
    documented_env: dict[str, str],
    compose_read_variables: set[str],
) -> None:
    """An `.env.example` entry that neither `Settings` nor Compose reads fails here.

    A reader is established by finding one, never by naming one: either a
    `Settings` field resolves to the variable, or a Compose file interpolates it
    as `${NAME}`. Delete the `${DB_NAME:?...}` from `docker-compose.yml` and
    `DB_NAME` fails here on the next run, which is the property that a set of
    exempt names could not have had.
    """
    settings_cls = load_settings_class()
    readable: set[str] = set()
    for names in env_variable_candidates(settings_cls).values():
        readable |= names

    readable |= compose_read_variables

    undeclared = sorted(name for name in documented_env if name.upper() not in readable)

    assert not undeclared, (
        f".env.example documents variables no Settings field reads: {undeclared}. "
        "Either add the field or drop the entry — a documented variable the "
        "application ignores is worse than no documentation. If the reader is "
        "Compose rather than the application, interpolate the name in "
        "docker-compose.yml where the service that needs it is declared; being "
        "listed here is not on its own evidence that anything reads it."
    )


def test_every_documented_variable_has_a_placeholder_value(
    documented_env: dict[str, str],
) -> None:
    """Placeholders are present for every entry.

    `.env.example` is the configuration documentation, and the e2e job in
    `.github/workflows/ci.yml` runs the stack from `cp .env.example .env`. An
    entry with no value documents neither the shape of the setting nor a value
    the stack can start with.
    """
    assert documented_env, "`.env.example` documents no variables at all."

    valueless = sorted(name for name, value in documented_env.items() if not value.strip())

    assert not valueless, f".env.example entries with no placeholder value: {valueless}."
