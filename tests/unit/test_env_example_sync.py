"""`.env.example` and `Settings` stay in sync — ticket E0-01, acceptance criterion 3.

"`.env.example` has one entry per `Settings` field; a test asserts the two are
in sync so a new setting cannot be added without documenting it."

Both directions are asserted: a `Settings` field with no `.env.example` entry
fails, and an `.env.example` entry that nothing reads fails. The second
direction is what stops the file from rotting into a list of variables the
application stopped reading two tickets ago.

`.env` has a second reader, and from E0-03 that axis has both its directions
too. A documented variable must have a reader — `Settings` or a Compose
interpolation — and, since a reviewer pass on pull request #16, **a variable a
Compose file interpolates must be documented**. That second one was missing for
three tickets, and its absence was not noticed by anyone reading this file: it
was noticed when another module cited it as a guarantee it did not provide, and
a credential reached three containers through the gap. The lesson is worth more
than the rule. A test suite that asserts one direction of a relationship reads,
from the outside, exactly like one that asserts both.

"Nothing reads it" is not the same rule as "no `Settings` field reads it", and
this module asserted the second one until dispute E0-02-01 separated them. From
E0-02, `.env` has two readers: `Settings`, and Compose, which cannot parse a URL
and so needs the database credentials as discrete values — `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD` for the role `initdb` creates, `DB_APP_USER` and
`DB_APP_PASSWORD` for the role the application connects as, and `DB_NAME`. No
`Settings` field reads any of the five, and calling them abandoned was false:
`docker-compose.yml` reads all five, and `DATABASE_URL` is interpolated from
three of them.

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

**One rule here has a named exemption, and it is the only one in this module.**
`test_every_documented_variable_has_a_placeholder_value` required a non-empty
value for every entry, and dispute E2-07-01 measured that against
`AI_PROVIDER_API_KEY`, whose *correct* documented value is the empty string: a
blank is how this codebase says "this endpoint authenticates nobody", stated in
`app/config.py`'s own validator, in `.env.example`'s prose above the entry, and in
`README.md`. E2-07 puts the development stack on exactly such an endpoint — the
in-repo mock provider — so the two assertions became the negation of each other
over one line, in all three states that line can take.

The ruling was that the sweep is the test at fault: its universal form generalises
from a file in which every entry happened to need a value, and E2-07 introduced
the first one whose blankness is a decision. The rule keeps its teeth — a *new*
valueless entry still fails, which is what it is really guarding — and the
exemption is a literal tuple rather than a condition, because the next such entry
(an SMTP password against a mail catcher, which authenticates nobody either) is
already foreseeable and belongs in a reviewed diff on that line.

An exemption of that shape is the thing `docs/MISTAKES.md` entry 35 is about: it
can go stale, and a stale exemption reports exactly what a live one reports. So
it carries two controls of its own, below the sweep — the exempted entry has to
*be* blank, and the exempted name has to still be *present*, so that the tuple
cannot go on excusing a value that has come back or hide a variable somebody
deleted.
"""

from pathlib import Path

# The entries whose documented value is deliberately the empty string, and the
# only exemption in this module. **Dispute E2-07-01**, ruled 2026-09-01: a blank
# `AI_PROVIDER_API_KEY` is not a missing placeholder, it is the documented way to
# say that the configured endpoint authenticates nobody — `app/config.py`'s
# validator, `.env.example`'s own prose and `README.md` all state it, and E2-07
# points the development stack at the in-repo mock provider, which is such an
# endpoint. A placeholder there would send a made-up bearer token to a service in
# the developer's own Compose network and would read as configuration somebody
# still has to fill in.
#
# A tuple rather than an `if name != ...`, because the next entry of this kind is
# foreseeable and because a set is a thing a reviewer can see growing. Every
# member is held against the file by the two controls below: an exemption is a
# rule that can go stale, and a stale one reports exactly what a live one reports
# (`docs/MISTAKES.md` entry 35).
DELIBERATELY_BLANK_VARIABLES = ("AI_PROVIDER_API_KEY",)


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


def test_every_variable_the_compose_files_interpolate_is_documented(
    documented_env: dict[str, str],
    compose_read_variables: set[str],
) -> None:
    """The converse of the test above, and it did not exist until it was needed.

    That one asks whether a documented variable has a reader. This one asks
    whether a reader has documentation, and nothing asserted it. The gap was
    found the way gaps like this usually are: another module cited it as a
    guarantee. `test_compose_stack.py`'s credential walk resolves a Compose
    interpolation through `.env.example` to see what it is built from, and its
    docstring said the two tests interlocked, so an indirection through an
    undocumented variable would fail here. It did not. `ALEMBIC_DATABASE_URL:
    ${SUPERUSER_DATABASE_URL:?not set}` with that name absent from
    `.env.example` and set to a superuser DSN in the operator's real `.env`
    passed all 76 tests, with the credential in three containers — the same hole
    a review pass had closed one round earlier, reopened by a different route.

    `.env.example` is documentation, not the deployed file. Absence from it says
    nothing about what is set at runtime; it says the walk is blind. So this
    test is what makes that walk sound, and the claim over there now points here
    rather than assuming it.

    It is worth having for a plainer reason too. A variable Compose requires and
    nobody documents is one an operator cannot know to set: `docker compose up`
    stops with `SUPERUSER_DATABASE_URL is not set`, and no file in the
    repository says what it is or what a value looks like.

    **`$$NAME` is not an interpolation**, and that distinction is doing real work
    rather than being a technicality. `docker-compose.yml`'s `db` health check
    passes `$$POSTGRES_DB` and `$$DB_APP_USER` — a literal `$NAME` reaching the
    container, expanded by the shell inside it out of an environment Compose has
    already built, never looked up in `.env`. `tests/fixtures/repo.py`'s walker
    consumes
    `$$` first and registers nothing, which is what keeps them out of the set
    below. At the time of writing `POSTGRES_DB` appears in the Compose files
    *only* in that escaped form and is documented nowhere, so it is a live
    canary: mishandle the escape and this test fails naming it. That makes a
    green result here mean something rather than nothing.
    """
    assert compose_read_variables, (
        "The Compose files interpolate no variables at all. Every name is then trivially "
        "documented and this test has stopped checking anything — which is precisely the "
        "shape of the hole it was written to close, so it is worth being loud about. Either "
        "a Compose file has stopped parsing, or the interpolation walker in "
        "tests/fixtures/repo.py has stopped matching."
    )

    documented = {name.upper() for name in documented_env}
    undocumented = sorted(compose_read_variables - documented)

    assert not undocumented, (
        f"The Compose files interpolate variables that .env.example does not document: "
        f"{undocumented}. Two things follow from that, and the second is the reason this "
        "test exists. An operator cannot know to set them, so the stack stops at "
        "`docker compose up` with a name and no explanation. And the credential rules in "
        "test_compose_stack.py resolve interpolations through .env.example to find what a "
        "variable is built from, so an undocumented name is a hole they cannot see into: a "
        "value assembled from ${DB_SUPERUSER_PASSWORD} in someone's real .env reads as "
        "clean. Document each one with a placeholder, or stop interpolating it. If you "
        "meant the container's own shell to expand it, escape it as `$$NAME` — Compose then "
        "never looks it up and it does not appear here."
    )


def test_every_documented_variable_has_a_placeholder_value(
    documented_env: dict[str, str],
) -> None:
    """Placeholders are present for every entry that is not deliberately blank.

    `.env.example` is the configuration documentation, and the e2e job in
    `.github/workflows/ci.yml` runs the stack from `cp .env.example .env`. An
    entry with no value documents neither the shape of the setting nor a value
    the stack can start with.

    **Except where the empty string is the value.** Dispute E2-07-01: this rule
    was written over a file in which every entry needed a value, and E2-07 added
    the first one whose correct documented value is blank — a blank
    `AI_PROVIDER_API_KEY` is how this codebase says the endpoint authenticates
    nobody. `DELIBERATELY_BLANK_VARIABLES` above is that list, and the reason the
    rule reads a tuple rather than a condition is written there.

    **What the rule still catches, which is what it is for:** a new entry added
    with nothing after the `=`. That is the accident this test was written
    against, and it is unaffected — a name has to be put in the tuple above, in a
    diff somebody reviews, before its blankness is accepted.

    The two tests below are what stop that tuple from becoming a way to hide
    things.
    """
    assert documented_env, "`.env.example` documents no variables at all."

    exempt = {name.upper() for name in DELIBERATELY_BLANK_VARIABLES}
    valueless = sorted(
        name
        for name, value in documented_env.items()
        if not value.strip() and name.upper() not in exempt
    )

    assert not valueless, (
        f".env.example entries with no placeholder value: {valueless}. Every entry documents a "
        "value the stack can start from, and CI's e2e job copies this file to `.env` unedited. If "
        "one of these is blank *on purpose* — the empty string being the documented configuration, "
        "the way it is for a provider that authenticates nobody — add it to "
        "`DELIBERATELY_BLANK_VARIABLES` in this file and say in the pull request what the blank "
        "means. Do not put a placeholder there instead: a value nobody meant to send is worse than "
        "no value."
    )


def test_every_deliberately_blank_variable_is_actually_blank(
    documented_env: dict[str, str],
) -> None:
    """The first control on the exemption: it may not excuse a value that has come back.

    **A red here means the exemption is stale, not that the file is wrong.** An
    exemption list is a rule that stops being true without anything failing:
    `AI_PROVIDER_API_KEY` acquiring a placeholder again would leave this tuple
    excusing an entry that no longer needs excusing, and the sweep above would go
    on reporting the whole file clean — the same silence a correct file produces.
    `docs/MISTAKES.md` entry 35's rule is that a guard which only ever reports
    absence has to be seen finding the thing on a subject that certainly has it,
    and this is that: each exempted name is required to be blank in the file the
    sweep reads.

    **The mutation this kills:** a value written back into an exempted entry, and
    a name added to the tuple that was never blank in the first place — which is
    how an exemption list becomes a way of switching the rule off one name at a
    time.
    """
    assert documented_env, ".env.example is missing or parsed to nothing."
    assert DELIBERATELY_BLANK_VARIABLES, (
        "`DELIBERATELY_BLANK_VARIABLES` is empty, so the sweep above has no exemption and this "
        "control has nothing to check. If the last exempted entry has genuinely gone, delete this "
        "test and the one below with it rather than leaving two that pass over an empty tuple."
    )

    carrying = {
        name: documented_env[name]
        for name in DELIBERATELY_BLANK_VARIABLES
        if name in documented_env and documented_env[name].strip()
    }

    assert not carrying, (
        f"These entries are exempted from the placeholder rule and are not blank: {carrying}. The "
        "exemption exists because the empty string is their documented value — a blank "
        "`AI_PROVIDER_API_KEY` means the endpoint authenticates nobody (dispute E2-07-01). An "
        "exempted entry that carries a value is an exemption doing nothing except making the "
        "sweep above blind to that name."
    )


def test_every_deliberately_blank_variable_is_still_documented(
    documented_env: dict[str, str],
) -> None:
    """The second control: the exemption may not hide a deleted variable.

    **A red here means a documented variable has gone, not that the exemption is
    wrong.** The control above compares values and says nothing about a name that
    is absent altogether — `name in documented_env` is what makes it silent for
    one — so deleting the `AI_PROVIDER_API_KEY` line would satisfy both the sweep
    and that control while removing the only place a deployment learns the
    variable exists.

    `test_every_settings_field_is_documented_in_env_example` would catch that
    today, because `Settings` has a field for it. This does not rely on that: the
    two rules answer different questions, and a field made optional and dropped —
    or renamed — would take that cover away without anything saying so. An
    exemption naming a variable that is not in the file is the shape worth
    refusing outright.

    **The mutation this kills:** the entry deleted rather than blanked, with the
    exemption left behind to make the deletion invisible.
    """
    assert documented_env, ".env.example is missing or parsed to nothing."

    missing = sorted(name for name in DELIBERATELY_BLANK_VARIABLES if name not in documented_env)

    assert not missing, (
        f".env.example no longer documents these exempted entries: {missing}. Blank is not the "
        "same as gone: a blank entry documents a setting and says its value is deliberately empty, "
        "and a deleted one leaves a deployment with no way to learn the variable exists. If it is "
        "genuinely gone, remove it from `DELIBERATELY_BLANK_VARIABLES` in the same change — an "
        "exemption for a name nothing documents excuses nothing and hides the deletion."
    )
