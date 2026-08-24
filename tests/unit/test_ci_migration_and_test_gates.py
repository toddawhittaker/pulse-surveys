"""The migration and test gates stop tolerating an absent tree — ticket E0-04.

Acceptance criterion 5: "The CI `test` and `migration-drift` jobs run for real
and pass." E0-04's scope names the mechanism: "Enable the CI `migration-drift`
job and the `test` job, removing both tolerance flags."

Both jobs were written whole and then wrapped in a condition, so that a
repository with no `backend/alembic.ini` and no `tests/` would go green rather
than red — `.github/workflows/ci.yml` says so at the top of the `detect` job:
"As each E0 ticket lands, flip the matching `allow-missing` step in that job from
tolerant to enforcing." The flag is `if: needs.detect.outputs.<name> == 'true'`
on every real step, plus a step that prints a notice in its place. While it is
there, a change that deletes `alembic.ini` or breaks collection turns the gate
off instead of failing it, and the pull request still shows a green check.

The passing half of the criterion is the jobs' own business and cannot be
asserted from pytest. What can be asserted is that the tolerance is gone and
that the jobs still run something — and the two have to be asserted together,
because a job whose steps have all been deleted satisfies "no tolerance
condition" perfectly. `tests/unit/test_ci_health_gate.py` is the module that
learned that lesson; this one is separate because its subject is a different
pair of jobs and a different property.

**On duplicated machinery.** The two helpers below are cut-down cousins of the
ones in `test_ci_health_gate.py`. They are not shared, and the reason is that
sharing them would mean editing that module, whose own docstring explains at
length why it handles comments in two opposite ways on purpose. What is copied
here is the part both need and neither may drop: a `#` inside a `run:` block is
a line that ships without executing, so a commented-out `pytest` invocation must
not count as the job running one.

**A second subject arrived with E0-36 item 2, and it is the same job.** E0-04 did
not only turn the drift gate on; it required that gate to run against the role
shape a deployment has, application role included, because `alembic check`
connecting as a superuser cannot see a grant problem. That half shipped with
nothing asserting it — `docs/MISTAKES.md` entry 2 — and was demonstrated during
review: delete the "Provision the application role" step, repoint the job's
`DATABASE_URL` at the superuser, and all 86 unit tests still passed and the drift
job still passed, because a superuser can create tables. So
[ADR 0012](../../docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md)'s
stated consequence was a convention rather than a guarantee. The `env.py` half is
already guarded — reverting its `.set(username=…, password=…)` turns three
integration tests red — and the two tests at the foot of this module are the CI
job's half.
"""

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

# A shell comment and everything after it on the line, removed before a line is
# read as a command. Truncation rather than a parse: losing a command can only
# fail red, while fabricating one from text that never runs fails green.
SHELL_COMMENT = re.compile(r"#.*$")

# A shell line continuation, joined before anything reads the line.
CONTINUATION = re.compile(r"\\\s*\n\s*")

# The `detect` job's output that each gate was conditioned on, and a command the
# job must still be running once the condition is gone. The commands are the
# ones the ticket and the workflow already name — `alembic upgrade head &&
# alembic check` for the drift gate, `pytest` for the test gate — so this is not
# a new requirement, it is the non-vacuity guard for the requirement above it.
GATES = (
    pytest.param(
        "migration-drift",
        "migrations",
        ("alembic upgrade head", "alembic check"),
        id="migration-drift",
    ),
    pytest.param("test", "pytests", ("pytest",), id="test"),
)


def run_scripts(node: Any) -> list[str]:
    """Every `run:` script anywhere inside a parsed workflow fragment."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                found.append(value)
            found.extend(run_scripts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(run_scripts(item))
    return found


def executed_lines(script: str) -> list[str]:
    """The lines of a `run:` script that could execute something, continuations joined."""
    lines: list[str] = []
    for raw in CONTINUATION.sub(" ", script).splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


def conditions(node: Any) -> list[str]:
    """Every `if:` expression anywhere inside a parsed workflow fragment."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "if":
                found.append(str(value))
            found.extend(conditions(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(conditions(item))
    return found


@pytest.mark.parametrize(("job_name", "detect_output", "required_commands"), GATES)
def test_the_gate_runs_for_real_rather_than_when_the_tree_happens_to_exist(
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
    job_name: str,
    detect_output: str,
    required_commands: tuple[str, ...],
) -> None:
    """E0-04 turns both gates on, which means deleting their escape hatch.

    The two assertions are one property and cannot be separated. Requiring the
    condition to be gone, on its own, is satisfied by a job with no steps left;
    requiring the commands to be present, on its own, is satisfied by a job that
    still skips every one of them. Together they say the job runs these commands
    unconditionally, which is what "runs for real" means.

    The condition is looked for by name — `needs.detect.outputs.<name>` — rather
    than by the absence of any `if:` at all, because a job may acquire a
    condition for some other reason later and this test should not be the thing
    that stops it. What it must not have is a condition on whether the thing it
    checks exists.
    """
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what "
        "makes the §14.2 definition of done enforceable, so it existing is a precondition of "
        "this test meaning anything."
    )

    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(job_name)
    assert job, (
        f"{ci_workflow_path} declares no `{job_name}` job (it declares {sorted(jobs)}). "
        "E0-04's fifth criterion is about that job by name; if it has been renamed, rename "
        "it here too rather than leaving this test looking for something that is gone."
    )

    marker = f"detect.outputs.{detect_output}"
    tolerant = [condition for condition in conditions(job) if marker in condition]
    assert not tolerant, "\n".join(
        [
            f"The `{job_name}` job still skips itself when `detect` reports the tree is not "
            "there:",
            *(f"  if: {condition}" for condition in tolerant),
            "",
            "E0-04 enables this gate, and enabling it means removing the tolerance flag as "
            "well as writing the steps. While the condition is there, deleting "
            "`backend/alembic.ini` or breaking test collection turns the gate off instead of "
            "failing it, and the pull request still shows a green check — which is the "
            "failure mode the whole `detect` scheme was built to be temporary about.",
        ]
    )

    executed = [line for script in run_scripts(job) for line in executed_lines(script)]
    missing = [
        command for command in required_commands if not any(command in line for line in executed)
    ]
    assert not missing, "\n".join(
        [
            f"The `{job_name}` job does not run {missing}. It runs: {executed or 'nothing'}.",
            "",
            "This is the other half of the assertion above, and it is not a separate "
            "requirement: a job with its steps commented out or deleted has no tolerance "
            "condition either, so without this the test would pass most enthusiastically "
            "against a gate that had stopped checking anything.",
        ]
    )


# ---------------------------------------------------------------------------
# E0-36 item 2 — the drift job's two-role shape.
# ---------------------------------------------------------------------------

DRIFT_JOB = "migration-drift"

# The script `/docker-entrypoint-initdb.d` runs on the Compose stack. Named
# rather than described, because "the job creates an application role somehow" is
# not a checkable sentence, and because *which* script it runs is itself the
# property: a second copy of the SQL in the workflow could drift from the one the
# stack runs, which is the reason ADR 0009's provisioning goes through a file at
# all. If provisioning moves, point this constant at where it went.
PROVISIONING_SCRIPT = "scripts/db-init/01-application-role.sh"

# The variables the job's two-role shape is spelled in. All three are read out of
# the job itself rather than compared against literals here: this module should
# not be the place that decides what the CI application role is called.
CONNECTION_VARIABLE = "DATABASE_URL"
APPLICATION_ROLE_VARIABLE = "DB_APP_USER"
SUPERUSER_VARIABLES = ("DB_SUPERUSER", "POSTGRES_USER")


def environment_values(node: Any, variable: str) -> list[str]:
    """Every value given to `variable` in any `env:` mapping inside a workflow fragment.

    Anywhere in the fragment, so that a job which moves `DATABASE_URL` from a step
    to the job level — a legitimate edit — does not read as the variable having
    disappeared.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "env" and isinstance(value, dict) and variable in value:
                found.append(str(value[variable]))
            found.extend(environment_values(value, variable))
    elif isinstance(node, list):
        for item in node:
            found.extend(environment_values(item, variable))
    return found


def drift_job(ci_workflow_path: Path, ci_workflow: dict[str, Any]) -> dict[str, Any]:
    """The `migration-drift` job, or a failure naming what the workflow declares instead."""
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what makes "
        "the §14.2 definition of done enforceable, so it existing is a precondition of this "
        "test meaning anything."
    )
    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(DRIFT_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{DRIFT_JOB}` job (it declares {sorted(jobs)}). E0-04 "
        "built that job and E0-36 item 2 is about the database shape it runs against; if it has "
        "been renamed, rename it here too rather than leaving this test looking for something "
        "that is gone."
    )
    return dict(job)


def test_the_migration_drift_job_provisions_the_application_role_before_it_migrates(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-36 criterion 2, first half: deleting the provisioning step fails something.

    `services.postgres` has no `/docker-entrypoint-initdb.d`, so the application
    role exists in this job only because a step creates it. Delete that step and
    the job still passes: `alembic upgrade head` runs as the superuser named in
    `DB_SUPERUSER`, which can create anything, and `alembic check` compares models
    against a schema built under privileges no deployment grants. A grant problem
    is then invisible to the gate whose whole purpose is to see schema problems
    before deploy time.

    The order is asserted with it because provisioning a role *after* the
    migration has already run is the same as not provisioning it — the connection
    that needed the role has already been made.

    **The mutation this survives:** delete the "Provision the application role"
    step from the `migration-drift` job in `.github/workflows/ci.yml`. **The near
    miss that must stay green:** renaming that step, or moving the `psql`
    availability check out of it, while it still runs
    `./scripts/db-init/01-application-role.sh` before the migration.
    """
    job = drift_job(ci_workflow_path, ci_workflow)
    executed = [line for script in run_scripts(job) for line in executed_lines(script)]

    assert executed, (
        f"The `{DRIFT_JOB}` job runs no commands at all. Every assertion below is about the order "
        "and the identity of what it runs, and a job with nothing in it satisfies most of them "
        "vacuously."
    )

    provisioning = [index for index, line in enumerate(executed) if PROVISIONING_SCRIPT in line]
    migrating = [index for index, line in enumerate(executed) if "alembic upgrade head" in line]

    assert provisioning, "\n".join(
        [
            f"The `{DRIFT_JOB}` job never runs `{PROVISIONING_SCRIPT}`. It runs: {executed}.",
            "",
            "E0-04 requires this gate to run against the role shape a deployment has, because a "
            "drift gate that connects as a role no deployment uses cannot see a grant problem. "
            "The job's Postgres service has no `/docker-entrypoint-initdb.d`, so the application "
            "role exists only because this step creates it — running the same script the Compose "
            "stack runs at first start (ADR 0009's provisioning table, settled by ADR 0012) "
            "rather than a second copy of the SQL that could drift from it.",
            "",
            "Deleting this step leaves every unit test passing and the drift job passing, because "
            "a superuser can create tables. That is why this assertion exists rather than a "
            "comment saying the same thing.",
        ]
    )

    assert migrating, (
        f"The `{DRIFT_JOB}` job never runs `alembic upgrade head`, so there is no migration for "
        "the provisioning above to precede. "
        "`test_the_gate_runs_for_real_rather_than_when_the_tree_happens_to_exist` is where that "
        "absence is diagnosed; here it would make the ordering assertion below meaningless."
    )

    assert min(provisioning) < min(migrating), "\n".join(
        [
            f"The `{DRIFT_JOB}` job runs `{PROVISIONING_SCRIPT}` at line {min(provisioning)} of "
            f"its commands and `alembic upgrade head` at line {min(migrating)}, so the "
            "application role is created after the migration that was supposed to run under it.",
            "",
            "A role provisioned afterwards is a role the migration never used: the connection "
            "has already been made and the schema has already been built by whoever made it. The "
            "job passes either way, which is the point.",
        ]
    )


def test_the_migration_drift_job_migrates_as_the_application_role_and_not_the_superuser(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-36 criterion 2, second half: repointing `DATABASE_URL` at the superuser fails something.

    The three variables in this job are the deployed split rather than a
    convenience. `DATABASE_URL` names the application role, which cannot create a
    table; `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` are the identity
    `backend/migrations/env.py` actually connects as (ADR 0009, ADR 0012). Point
    `DATABASE_URL` at the superuser and every gate stays green while the drift
    check runs against a cluster shape no deployment has.

    **The role name is read out of the job, not spelled here.** The assertion is
    that the connection the job hands the application names the role the job
    provisioned, and that it is not either spelling of the superuser — so renaming
    the CI role is a one-place edit and this test is not a second copy of a value
    it is supposed to be holding up (`docs/MISTAKES.md` entry 19).

    **The mutation this survives:** change the `alembic` step's `DATABASE_URL` in
    `.github/workflows/ci.yml` to
    `postgresql+psycopg://postgres:postgres@localhost:5432/pulse_ci`. **The near
    miss that must stay green:** renaming the application role throughout the job
    — `DB_APP_USER` and the `DATABASE_URL` user together.
    """
    job = drift_job(ci_workflow_path, ci_workflow)

    connections = environment_values(job, CONNECTION_VARIABLE)
    application_roles = sorted(set(environment_values(job, APPLICATION_ROLE_VARIABLE)))
    superuser_names = sorted(
        {value for name in SUPERUSER_VARIABLES for value in environment_values(job, name)}
    )

    assert connections, (
        f"The `{DRIFT_JOB}` job sets no `{CONNECTION_VARIABLE}` anywhere, so nothing here says "
        "which role `alembic` connects the application as. E0-04 requires that to be the "
        "application role; an unset variable means whatever `.env` or a default supplies, which "
        "in this job is nothing at all."
    )

    assert application_roles, (
        f"The `{DRIFT_JOB}` job sets no `{APPLICATION_ROLE_VARIABLE}`, so this test cannot tell "
        f"which role `{PROVISIONING_SCRIPT}` created and the comparison below would have nothing "
        "to compare against. The provisioning step passes that variable to the script; if the "
        "role's name now comes from somewhere else, point this test at it."
    )

    assert len(application_roles) == 1, (
        f"The `{DRIFT_JOB}` job gives `{APPLICATION_ROLE_VARIABLE}` more than one value "
        f"({application_roles}), so 'the role the job provisioned' is ambiguous and this test "
        "would be choosing one of them arbitrarily."
    )

    assert superuser_names, (
        f"The `{DRIFT_JOB}` job names no superuser in any of {list(SUPERUSER_VARIABLES)}, so the "
        "'not the superuser' half of this assertion has nothing to exclude and would pass against "
        "a connection string that named it."
    )

    application_role = application_roles[0]
    wrong = [
        (url, urlsplit(url).username)
        for url in connections
        if urlsplit(url).username != application_role
    ]

    assert not wrong, "\n".join(
        [
            f"The `{DRIFT_JOB}` job connects as a role other than the one it provisioned "
            f"(`{application_role}`):",
            *(f"  {url} connects as {user!r}" for url, user in wrong),
            "",
            "E0-04 requires this gate to use the same database shape the stack deploys, "
            "application role included, because `alembic check` running as a superuser cannot see "
            "a grant problem — a superuser can create tables, so the job passes over a schema no "
            "deployment could have built. Demonstrated during review: with `DATABASE_URL` "
            "repointed at the superuser, every unit test passed and the drift job passed.",
            "",
            "ADR 0012 records this as a consequence; until this assertion existed it was a "
            "convention rather than a guarantee (`docs/MISTAKES.md` entry 2).",
        ]
    )

    superuser_connections = [
        url for url in connections if urlsplit(url).username in set(superuser_names)
    ]
    assert not superuser_connections, "\n".join(
        [
            f"The `{DRIFT_JOB}` job hands the application a connection as the superuser: "
            f"{superuser_connections}.",
            "",
            f"This says the same thing as the assertion above from the other side, and it is not "
            f"redundant: renaming `{APPLICATION_ROLE_VARIABLE}` to the superuser's own name would "
            "satisfy 'the connection names the provisioned role' exactly, and is the one edit "
            "that turns that assertion back into the thing it replaced.",
        ]
    )
