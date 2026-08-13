"""The CI health gate names every service it is supposed to wait on — ticket E0-03.

Acceptance criterion 5: "The CI `docker` job waits on all three services and
passes." The passing half is the job's own business and cannot be asserted from
pytest. The *waiting on all three* half can, and it is worth a test of its own
because of what `scripts/ci/wait_for_health.sh` does with its arguments: it
fails a service that declares no HEALTHCHECK, fails one that reports unhealthy,
and says nothing whatever about a service nobody named. So the argument list is
not a detail of the job — it is the whole of what criterion 1 ("`docker compose
up -d` reaches healthy on `api`, `worker`, and `beat`") is checked by. Leave
`worker` off it and the job goes green with a worker that crash-looped, and
E0-03's first criterion is then asserted nowhere at all.

E0-02 reached `db` and `redis` through `api`'s `depends_on` conditions rather
than by naming them, and `test_compose_stack.py` holds those conditions for that
reason. Nothing equivalent is available here: `api` does not depend on `worker`
or `beat`, and it must not — the API has to come up whether or not the job
runtime does.

This module is separate from `test_compose_stack.py` because its subject is the
workflow rather than the Compose file, and separate from the image-pin module
because that one is about two files agreeing about a third thing. It reads
`ci_workflow` from `tests/conftest.py`, parsed rather than grepped, for the
reason given there.

One test below reads the file as text instead, and that is deliberate rather
than a lapse: a parser throws comments away, and a comment is exactly what that
test is about. It reads it through `flattened`, which collapses whitespace and
comment markers, because the text a comment holds and the text a comment *looks
like* are two different strings — the first version of that test searched for
the second and found nothing.
"""

import re
from pathlib import Path
from typing import Any

# The job E0-03's criterion names. Named here rather than discovered, because
# the criterion names it: if the job is renamed, this test should fail and say
# so rather than quietly find nothing to check.
DOCKER_JOB = "docker"

# The three services criterion 1 requires to reach healthy.
REQUIRED_SERVICES = ("api", "worker", "beat")

WAIT_SCRIPT = "scripts/ci/wait_for_health.sh"

# Everything after the script name up to the end of the command. Stopping at
# `|`, `&`, `;` and the newline keeps a following command out of the argument
# list; option-looking words and `NAME=value` prefixes are dropped below, since
# neither is a service name.
INVOCATION = re.compile(r"wait_for_health\.sh(?P<arguments>[^\n;|&]*)")

# A shell line continuation, joined before the pattern above is applied. Without
# this, `wait_for_health.sh api \` + `worker beat` on the next line reads as a
# call that waits on `api` alone, and the test fails a job that is doing exactly
# what E0-03 asks. It is the same defect as the one below — a pattern that stops
# at a line break while the text it is looking for crosses one — in the
# direction that produces a false failure rather than a false pass.
CONTINUATION = re.compile(r"\\\s*\n\s*")

# The note E0-02 left in the `docker` job, in the words it used: "`worker` and
# `beat` join the argument list in E0-03." This ticket is that work.
#
# Matched against `flattened`, never against the raw file. The comment wraps at
# 80 columns, so between `join the` and `argument list` the file holds a
# newline, six spaces and a `#`. This pattern with a literal space in it matched
# nothing, and the test went green against the exact comment it exists to catch
# — `docs/MISTAKES.md` entry 3, inside the test written for entry 1.
DEFERRAL_NOTE = re.compile(r"joins? the argument list", re.IGNORECASE)

# Proof that `flattened` still holds the region this file is about. A negative
# text assertion — "this phrase is absent" — passes just as readily when the
# search is looking at nothing, so the flattening is checked against a string
# that is certainly in the workflow before its silence is believed.
FLATTENING_CANARY = "wait_for_health.sh"


def run_scripts(node: Any) -> list[str]:
    """Every `run:` script anywhere inside a parsed workflow fragment.

    Structural rather than positional, so it finds the script whether the step
    that holds it moves, gains a `working-directory`, or is wrapped in a matrix.
    """
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


def flattened(text: str) -> str:
    """`text` with every run of whitespace and `#` collapsed to a single space.

    So that a phrase can be looked for without knowing where the file happens to
    wrap. A YAML comment that runs past 80 columns continues on the next line
    behind another `#`, which puts a newline, an indent and a comment marker in
    the middle of an English sentence; a pattern written with the spaces the
    sentence appears to have then matches nothing, and an assertion that
    something is *absent* passes.

    Collapsing `#` along with whitespace is what makes the sentence whole again.
    It also runs the workflow's YAML and its prose together, which is harmless
    here — the phrase being searched for is prose, and no arrangement of YAML
    keys spells it.
    """
    return re.sub(r"[\s#]+", " ", text)


def health_wait_invocations(node: Any) -> list[list[str]]:
    """The service names passed to each `wait_for_health.sh` call in `node`."""
    invocations: list[list[str]] = []
    for script in run_scripts(node):
        for match in INVOCATION.finditer(CONTINUATION.sub(" ", script)):
            arguments = [
                word
                for word in match.group("arguments").split()
                if "=" not in word and not word.startswith("-")
            ]
            invocations.append(arguments)
    return invocations


def test_the_docker_job_waits_on_api_worker_and_beat(
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
) -> None:
    """Criterion 5, and with it the only check criterion 1 has.

    *Every* invocation in the job, not just the first. The `docker` job tears
    the stack down with `down -v` and brings it back twice, waiting each time,
    and that loop is the check that the stack comes up on a machine that has
    never run it before — which is exactly the case a worker whose image lacks a
    dependency, or a beat whose schedule file cannot be created, fails. A second
    wait that names only `api` would report that a clean start works while
    having watched one third of it.

    The "found any at all" assertion is not ceremony. This test compares the
    required names against what it collected, and an empty collection satisfies
    a subset check trivially — so a job that stopped calling the script, or a
    workflow whose shape changed under the parser, would turn this into a test
    that passes having read nothing.
    """
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what "
        "makes the §14.2 definition of done enforceable, so it existing is a precondition "
        "of this test meaning anything."
    )

    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(DOCKER_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{DOCKER_JOB}` job (it declares {sorted(jobs)}). "
        "E0-03's fifth criterion is about that job by name; if it has been renamed, rename "
        "it here too rather than leaving this test looking for something that is gone."
    )

    invocations = health_wait_invocations(job)
    assert invocations, (
        f"The `{DOCKER_JOB}` job calls `{WAIT_SCRIPT}` nowhere. That script is what turns "
        "'the containers started' into 'the containers work' — it fails a service with no "
        "HEALTHCHECK and a service reporting unhealthy — so without it the build gate "
        "asserts that Compose accepted the file."
    )

    required = set(REQUIRED_SERVICES)
    incomplete = [
        (arguments, sorted(required - set(arguments)))
        for arguments in invocations
        if required - set(arguments)
    ]

    reported = [f"  waits on {waited}, missing {missing}" for waited, missing in incomplete]

    assert not incomplete, "\n".join(
        [
            f"A `{WAIT_SCRIPT}` call in the `{DOCKER_JOB}` job does not wait on every "
            "service E0-03 brings up:",
            *reported,
            "",
            "E0-03 criterion 1 is that `docker compose up -d` reaches healthy on api, "
            "worker and beat, and this argument list is the only thing that checks it: a "
            "service nobody names is a service the gate never looks at, and the job goes "
            "green with it crash-looping. Restore the full list — "
            f"`{WAIT_SCRIPT} {' '.join(REQUIRED_SERVICES)}` — at every wait in the job, the "
            "one after the restart loop included.",
        ]
    )


def test_the_workflow_no_longer_defers_the_health_wait_to_this_ticket(
    ci_workflow_path: Path,
) -> None:
    """The comment beside the health wait stops describing E0-03 as future work.

    E0-02 wrote, above the wait: "`worker` and `beat` join the argument list in
    E0-03." True when it was written, false the moment this ticket lands, and
    invisible to every other test in this suite because YAML parsers discard
    comments — which is why this one reads the file as text.

    `docs/MISTAKES.md` entry 1 is nine instances of exactly this, and its rule is
    to ask what else in the repository asserts something about the thing you
    changed. A comment that promises a later ticket will do what has now been
    done sends the next reader looking for work that is finished, and it is
    cheaper to read than the argument list underneath it.

    **The first version of this test passed against that comment**, because the
    comment wraps at 80 columns and the pattern was written with a plain space
    where the file has a newline, an indent and a `#`. Reading it, it looked
    right. Hence `flattened` above, and hence the canary below: an assertion that
    a phrase is absent is satisfied by a search that is looking at nothing, so
    the search is made to find something first.

    This asserts the absence of one phrase rather than the presence of a correct
    comment, because what the replacement should say is the implementer's to
    write. It will not catch a differently-worded false claim; it catches this
    one, which is the one that is there.
    """
    assert ci_workflow_path.is_file(), (
        f"{ci_workflow_path} does not exist. The CI pipeline is what makes the §14.2 "
        "definition of done enforceable."
    )
    text = flattened(ci_workflow_path.read_text(encoding="utf-8"))
    assert FLATTENING_CANARY in text, (
        f"`{FLATTENING_CANARY}` does not appear in {ci_workflow_path} once comment markers "
        "and line breaks are collapsed. Either the health gate is spelled some other way "
        "now — in which case the comment this test looks for is about something that no "
        "longer exists and the test needs rewriting — or the flattening above has eaten the "
        "text. Both make the search below silent, and a silent search passes."
    )

    assert DEFERRAL_NOTE.search(text) is None, (
        f"{ci_workflow_path} still carries the E0-02 note that `worker` and `beat` join the "
        "health wait's argument list in E0-03. This ticket is E0-03, so that comment now "
        "describes finished work as pending. Rewrite it to say what the wait covers and why "
        "— the api reaches db and redis through its depends_on conditions, while worker and "
        "beat have to be named — or delete it."
    )
