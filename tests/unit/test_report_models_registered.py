"""The report models are on `Base.metadata`, and cost nothing to import — ticket E4-02.

Not an acceptance criterion of its own. Both assertions here are rules the epic
README settles once and every model-module ticket inherits, and they are the same
two `tests/unit/test_survey_models_registered.py` holds for E2-05,
`tests/unit/test_term_models_registered.py` for E0-06 and
`tests/unit/test_org_models_registered.py` for E0-05. They are here because these
are the two failures that fail without failing anything:

  - **A model module nobody imported is not on `Base.metadata`.**
    `migrations/env.py` autogenerates against that metadata, so an unregistered
    `report.py` means `alembic check` reports no drift, the missing migration is
    never missed, and the four tables exist in no deployed database. Nothing goes
    red at the time — `docs/MISTAKES.md` entry 2.
  - **A model module that reaches `Base` through `app.db` builds an engine out of
    `Settings()` at import.** That needs `AI_PROVIDER_BASE_URL` and four other
    variables which have nothing to do with a schema, so it works on a machine
    with a full `.env` and breaks in CI, where the `migration-drift` job supplies
    the database variables alone.

The integration suite cannot see either one: by the time
`tests/integration/test_report_schema.py` reflects the migrated database, a table
is either there or it is not. It would go red — but on the criterion about the
constraint it was attempting, which sends the reader to the migration rather than
to the missing import.

**Why a module of its own is the subject at all.** SPEC §13 lists no home for a
reporting model — `survey.py` holds what students submitted and `ai.py` holds the
verdicts a model returned — so the ticket adds one, and the ADR is where that is
argued. What is asserted here is only that whatever module holds them is imported
by the package: the tables are named and the module is named, and a schema
shipped in a file nothing executes is the failure either way.
"""

from pathlib import Path
from typing import Any

import pytest

# The four tables E4-02's scope names: the stored summary, the moderation record,
# and the release batch as a batch row plus a membership table. Table names, not
# ORM class names — the ticket names the tables and nothing anywhere names the
# classes.
REPORT_TABLES = ("weekly_summary", "moderation_state", "release_batch", "release_batch_member")

# Where SPEC §13 puts the package, and where E4-02's settled design puts the
# module: `backend/app/models/report.py`, beside `org.py`, `term.py`,
# `identity.py`, `survey.py` and `ai.py`. `question.stream` is added to
# `survey.py`, where the `question` model already lives, which is why nothing here
# names it.
REPORT_MODULE = "app.models.report"
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"


def test_every_report_table_is_registered_on_base_metadata(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """Importing `app.models` is enough to put all four tables on the metadata.

    Asserted through the package rather than through `app.models.report` directly,
    and that is the whole point: `env.py` imports the package, so a module that
    exists and is not imported there is invisible to autogenerate. Importing
    `report` by name here would pass against exactly the defect this exists to
    catch.

    **The mutation it kills:** adding `report.py` and not adding its import to
    `app/models/__init__.py`, which leaves `alembic check` clean, this suite's
    seeding walker unable to find the tables, and the schema shipped in a file
    nothing executes.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package. E0-04 ships it with `base.py`, and every model "
        "ticket since has added a module to it; E4-02 adds `report.py` and imports it in "
        "`__init__.py` in the same change."
    )

    base_module = import_app_module(BASE_MODULE)
    assert base_module is not None, (
        f"There is no `{BASE_MODULE}`. E0-04 ships the declarative base there, and every model "
        "module imports `Base` from it rather than from `app.db`."
    )

    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    assert metadata is not None, (
        f"`{BASE_MODULE}` exposes no `Base` with `metadata`, so there is nothing for "
        "`migrations/env.py` to autogenerate against."
    )

    registered = sorted(metadata.tables)
    missing = [name for name in REPORT_TABLES if name not in registered]
    assert not missing, (
        f"Importing `{MODELS_PACKAGE}` registers {registered}, so {missing} is on no metadata "
        f"`env.py` can see. The table may well exist in `{REPORT_MODULE}`: a module nobody imports "
        "is not on `Base.metadata`, `alembic check` then reports no drift, and the migration that "
        "was never written is never missed. Import the module in `app/models/__init__.py` in the "
        "same change that adds it."
    )


def test_importing_the_report_models_needs_no_application_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """`app.models.report` imports with the environment empty.

    The environment is emptied of everything `.env.example` documents and the
    working directory moved somewhere with no `.env`, because the failure this
    describes is invisible on a developer's machine: with a full `.env`, a model
    module that reaches `Base` through `app.db` imports perfectly and builds an
    engine on the way. CI is where it breaks, and by then the message is about a
    missing AI provider URL in a schema ticket.

    Asserting the documented set is non-empty first is not ceremony: an
    `.env.example` that failed to parse would empty the environment of nothing and
    leave this passing against the defect (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** `from app.db import Base` at the top of
    `report.py`, which every test that runs against a configured environment goes
    on passing.
    """
    assert documented_env, (
        "`.env.example` documented no variables, so nothing was cleared and this test would pass "
        "whatever `app.models.report` imports. `tests/unit/test_env_example_sync.py` says what "
        "that file is supposed to hold."
    )

    monkeypatch.chdir(tmp_path)
    for name in documented_env:
        monkeypatch.delenv(name, raising=False)

    try:
        module = import_app_module(REPORT_MODULE)
    except Exception as failure:
        pytest.fail(
            f"Importing `{REPORT_MODULE}` with no configuration in the environment raised "
            f"{failure!r}. A model module needs `Base` and nothing else: import it from "
            "`app.models.base`, never from `app.db`, which builds an engine out of `Settings()` "
            "at import time. CI's `migration-drift` job and the testcontainers fixture both supply "
            "the database variables alone, so a module that needs more than that works here and "
            "fails there."
        )

    assert module is not None, (
        f"There is no `{REPORT_MODULE}` module. E4-02 puts the stored summary, the moderation "
        "record and the two release-batch tables there (SPEC §13 gives `models/` that job, and the "
        "ticket's settled design names the file)."
    )
