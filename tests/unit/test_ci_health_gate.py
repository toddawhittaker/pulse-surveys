"""The CI health gate: which services it names, and where — E0-03, E0-14, E0-16, E2-07.

E0-03's acceptance criterion 5: "The CI `docker` job waits on all three services
and passes." The passing half is the job's own business and cannot be asserted
from pytest. The *waiting on each of them* half can, and it is worth a test of
its own because of what `scripts/ci/wait_for_health.sh` does with its arguments:
it fails a service that declares no HEALTHCHECK, fails one that reports
unhealthy, and says nothing whatever about a service nobody named. So the
argument list is not a detail of the job — it is the whole of what criterion 1
("`docker compose up -d` reaches healthy on ...") is checked by. Leave `worker`
off it and the job goes green with a worker that crash-looped, and E0-03's first
criterion is then asserted nowhere at all.

**The list grows with the stack, and this module is where it grows.** E0-14 adds
`mock-lms`, whose own first criterion — "`docker compose up -d` brings `mock-lms`
to healthy alongside the existing services" — is checked by exactly the same
mechanism and by nothing else. E0-16 adds `mock-idp` and its first criterion is
the same sentence about the other entry door, so it joins the list for the same
reason. E2-07 adds `mock-ai`, the third external dependency's stand-in, and its
fourth criterion is that CI's e2e job runs against it — which is exactly this
argument list, in a second job. A ticket that adds a service with a health check
and does not add it here has shipped a service the gate never looks at.

**Two jobs ask this question now, and they ask it about different things.** The
`docker` job is about the images and the stack; the `e2e` job is about a browser
driving that stack, and `mock-ai` is the service whose absence it would feel
first — a Playwright submit against a stack with no provider waits four seconds
and takes the fail-open path, which is a passing spec measuring nothing. So the
same list is required of both, and the second test below says so about the job
E2-07's criterion 4 names.

E0-02 reached `db` and `redis` through `api`'s `depends_on` conditions rather
than by naming them, and `test_compose_stack.py` holds those conditions for that
reason. Nothing equivalent is available here: `api` does not depend on `worker`
or `beat`, and it must not — the API has to come up whether or not the job
runtime does.

The second question this module asks is *where* the job waits, and it is a
different question from what the wait names. `docker-compose.override.yml`
mounts the checkout into `worker` and `beat`, so a merged `docker compose up`
runs the working tree rather than the wheel in the image, and a packaging
regression in `app/jobs` passes every merged gate while failing in every real
deployment. The `docker` job therefore has a pass that starts the stack on the
base file alone — and a pass that starts a stack without waiting on it verifies
nothing, so the start and the wait are asserted together, about the same stack,
rather than separately about the same job.

This module is separate from `test_compose_stack.py` because its subject is the
workflow rather than the Compose file, and separate from the image-pin module
because that one is about two files agreeing about a third thing. It reads
`ci_workflow` from `tests/fixtures/repo.py`, parsed rather than grepped, for the
reason given there.

One test below reads the file as text instead, and that is deliberate rather
than a lapse: a parser throws comments away, and a comment is exactly what that
test is about. It reads it through `flattened`, which collapses whitespace and
comment markers, because the text a comment holds and the text a comment *looks
like* are two different strings — the first version of that test searched for
the second and found nothing.

**So this module handles comments in two opposite ways on purpose, and they
must not be unified.** `flattened` keeps comment text and joins it up, because
its subject is a stale comment. `executed_lines` throws comment text away,
because its subject is what the job runs, and a `#` inside a `run:` block is a
line that ships without executing. The two `#` characters are at different
layers: one is YAML's, discarded by the parser before either function sees it,
and one is the shell's, sitting inside a string the parser hands over intact.
Reviewer pass 3 found the second layer unguarded — three commented-out lines and
an `echo "temporarily disabled"` left this module green with CI verifying
nothing — one round after a commit message had congratulated the first layer's
defence.
"""

import re
from pathlib import Path
from typing import Any

# The job E0-03's criterion names. Named here rather than discovered, because
# the criterion names it: if the job is renamed, this test should fail and say
# so rather than quietly find nothing to check.
DOCKER_JOB = "docker"

# The job E2-07's fourth criterion names: "CI's e2e job runs against it".
E2E_JOB = "e2e"

# Every service a first acceptance criterion requires to reach healthy: `api`,
# `worker` and `beat` from E0-03, `mock-lms` from E0-14, `mock-idp` from E0-16,
# and `mock-ai` from E2-07. Listed rather than derived from the Compose file, and
# the difference matters — a rule of "wait on whatever the file declares" would
# silently accept a service that lost its health check, because
# `wait_for_health.sh` would stop being given it at the same moment it stopped
# being able to answer.
REQUIRED_SERVICES = ("api", "worker", "beat", "mock-lms", "mock-idp", "mock-ai")

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

# A compose invocation that starts a stack, and the files it was given. Only
# `up` counts: a `build`, `down`, `ps` or `logs` run against the base file
# creates nothing that could be waited on, and treating one as a stack start
# would fail a job for a command that never brought anything up.
COMPOSE_UP = re.compile(r"docker\s+compose\b(?P<flags>[^\n;|&]*?)\bup\b")

# `-f FILE`, `--file FILE`, and the `=` spellings of both.
COMPOSE_FILE_FLAG = re.compile(r"(?:^|\s)(?:-f|--file)[=\s]+(?P<path>\S+)")

# The base Compose file, as the workflow spells it.
BASE_COMPOSE_FILE = "docker-compose.yml"

# A shell comment and everything after it on the line, removed before anything
# below reads the line as a command.
#
# This is the hole reviewer pass 3 walked through, and it is worth stating
# exactly because the defence written one round earlier was aimed one layer too
# high. That round was pleased with itself for reading parsed `run:` values
# rather than raw file text, so that a *YAML* comment mentioning
# `docker compose up` could not fabricate an event. It could not — and then
# every line of the `run:` block itself was read as a command, so a *shell*
# comment could. Commenting out the three lines of the base-file-only pass and
# leaving `echo "temporarily disabled"` behind kept this whole module green
# while CI verified nothing, which is both the exact regression the test exists
# to prevent and exactly how it would arrive in real life.
#
# The direction matters and is the reason this is a truncation rather than
# something cleverer: removing text can only *lose* an event, and a lost event
# fails red. Fabricating one from text that never runs fails green. A command
# carrying a `#` inside quotes is truncated and so counted wrongly — in the safe
# direction.
SHELL_COMMENT = re.compile(r"#.*$")

# Lines that only print. `echo "docker compose -f docker-compose.yml up -d"`
# starts nothing, and an `echo` is what a disabled step leaves behind.
PRINTING_COMMANDS = ("echo", "printf")


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


def executed_lines(script: str) -> list[str]:
    """The lines of a `run:` script that are commands, in the order they run.

    Continuations are joined, comments are cut, and lines that only print are
    dropped. What is left is not a shell parse and does not pretend to be — it
    is the set of lines that could execute something, which is the question
    every scan below is really asking.
    """
    lines: list[str] = []
    for raw in CONTINUATION.sub(" ", script).splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if not line or line.split()[0] in PRINTING_COMMANDS:
            continue
        lines.append(line)
    return lines


def wait_arguments(text: str) -> list[list[str]]:
    """The service names passed to each `wait_for_health.sh` call in `text`."""
    invocations: list[list[str]] = []
    for match in INVOCATION.finditer(text):
        words = match.group("arguments").split()
        invocations.append([word for word in words if "=" not in word and not word.startswith("-")])
    return invocations


def health_wait_invocations(node: Any) -> list[list[str]]:
    """The service names passed to each executed `wait_for_health.sh` call in `node`.

    Executed, not written: a commented-out wait is not a wait. It reaches the
    same `executed_lines` the base-file test uses, so the two cannot end up
    disagreeing about what counts as a command — which is the disagreement that
    let a commented-out step keep a collection non-empty and prop up the
    "found any at all" guard below.
    """
    invocations: list[list[str]] = []
    for script in run_scripts(node):
        for line in executed_lines(script):
            invocations.extend(wait_arguments(line))
    return invocations


def compose_files_named(flags: str) -> set[str]:
    """The Compose files a `docker compose` invocation was given, if any.

    Leading `./` is stripped so `-f ./docker-compose.yml` and
    `-f docker-compose.yml` are the same file, which they are.
    """
    return {m.group("path").removeprefix("./") for m in COMPOSE_FILE_FLAG.finditer(flags)}


def script_events(script: str) -> list[tuple[str, set[str]]]:
    """Stack starts and health waits within one `run:` script, in order.

    `("up", {files})` for a compose invocation that starts a stack, with the
    Compose files it named — an empty set meaning it named none and so got the
    merged default. `("wait", {services})` for each health wait. Within a single
    line the start is recorded first, which is the only order it could have
    executed in.

    One script at a time, which is a narrowing from the previous version and the
    answer to reviewer pass 3's structural objection. Reading the whole job as
    one stream bought the ability to split a start and its wait across two
    steps, nothing in this repository does that, and the generality was a
    second surface for exactly the fabrication bug that round found. A pass that
    starts a stack and then waits on it is one self-contained script here, and
    saying so in the machinery costs a loud failure if anyone splits it — which
    is a failure that gets read, unlike the alternative.
    """
    events: list[tuple[str, set[str]]] = []
    for line in executed_lines(script):
        for match in COMPOSE_UP.finditer(line):
            events.append(("up", compose_files_named(match.group("flags"))))
        for arguments in wait_arguments(line):
            events.append(("wait", set(arguments)))
    return events


def test_the_docker_job_waits_on_every_service_a_criterion_names(
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
    having watched a fraction of it.

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
            "service the stack brings up:",
            *reported,
            "",
            "E0-03, E0-14 and E0-16 each have a first criterion that `docker compose up -d` "
            "reaches healthy, and this argument list is the only thing that checks any of "
            "them: a service nobody names is a service the gate never looks at, and the job "
            "goes green with it crash-looping. Restore the full list — "
            f"`{WAIT_SCRIPT} {' '.join(REQUIRED_SERVICES)}` — at every wait in the job, the "
            "one after the restart loop included.",
        ]
    )


def test_the_e2e_job_waits_on_every_service_a_criterion_names(
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
) -> None:
    """E2-07's fourth criterion, for the half of it that is not about secrets.

    "CI's e2e job runs against it" — and the only thing that makes that true is
    the stack this job brings up and waits on. `wait_for_health.sh` says nothing
    whatever about a service nobody named, so a `mock-ai` left off this list is a
    Playwright run against a stack whose provider may be crash-looping, and every
    submit in it takes the four-second fail-open path and passes.

    That is the failure worth naming: the specs stay green. A stack with no
    classifier does not break a browser test, it makes one meaningless — the
    "bounced with immediate feedback" exit clause E2-07's context paragraph
    describes is never actually exercised against a verdict.

    **The same list as the `docker` job**, because a service that has to be
    healthy for one is healthy for the other, and two lists that could disagree
    are two things to keep in step (`docs/MISTAKES.md` entry 13). This is a
    separate *test* rather than a parametrisation because the two jobs fail for
    different reasons and a red should say which.

    **The mutation this kills:** `mock-ai` added to the `docker` job's waits and
    not to this one, which is the natural half-edit — the `docker` job is where
    three of the five names went in.

    The "found any at all" assertion is not ceremony: this test compares a
    required set against what it collected, and an empty collection satisfies a
    subset check trivially.
    """
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what makes "
        "the §14.2 definition of done enforceable."
    )

    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(E2E_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{E2E_JOB}` job (it declares {sorted(jobs)}). E2-07's "
        "fourth criterion names that job; if it has been renamed, rename it here too rather than "
        "leaving this test looking for something that is gone."
    )

    invocations = health_wait_invocations(job)
    assert invocations, (
        f"The `{E2E_JOB}` job calls `{WAIT_SCRIPT}` nowhere, so it starts a stack and drives a "
        "browser at it without ever asking whether the stack came up."
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
            f"A `{WAIT_SCRIPT}` call in the `{E2E_JOB}` job does not wait on every service the "
            "stack brings up:",
            *reported,
            "",
            "E2-07's fourth criterion is that this job runs against the mock provider. A service "
            "nobody names is a service the gate never looks at — and a Playwright submit against "
            "a stack with no classifier waits four seconds, takes the fail-open path, and passes.",
        ]
    )


def test_the_docker_job_waits_on_every_service_after_starting_the_base_file_alone(
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
) -> None:
    """The base-file-only pass exists *and* is verified, in one assertion.

    Why the pass exists: `docker-compose.override.yml` mounts the checkout into
    `worker` and `beat`, so every merged `docker compose up` runs the working
    tree rather than the wheel installed in the image. A packaging regression in
    `app/jobs` — a module left out of the distribution, an import that only
    resolves from the source tree — therefore passes every merged gate and fails
    in every real deployment. The implementer proved that rather than asserting
    it: an image whose task returned `STALE-IMAGE-BUILT-AT-T0` answered `pong`
    through the merged round trip and went green, while the base-file-only pass
    returned the stale value.

    **Why both halves are one assertion.** The test above collects every wait in
    the job and requires each to name every service, and that is exactly the guard
    that missed this: a step with no wait at all contributes nothing to a
    collection, and the job's other waits keep it non-empty, so the pass could be
    cut back to `up -d` with nothing looking at it and the suite stayed green. It
    is `docs/MISTAKES.md` entry 2 one level up — asking whether the collection is
    empty overall rather than whether the step that matters contributed to it. So
    the two halves cannot be asserted apart: a start with no wait verifies
    nothing, and a wait after a merged start says nothing about packaging. Each
    is satisfied by the other's absence.

    **What counts as "the base file alone".** The files named by the invocation
    must be exactly `{docker-compose.yml}` — the presence of that flag is not
    enough on its own, because a second `-f` puts the override back and makes the
    pass merged again while still containing the marker. Equality answers both
    halves of the question the flag raises, which is why it is written that way
    rather than as a membership test or as the absence of the override's name.

    **The unit is one `run:` script, and the window inside it runs until the
    next stack start.** So the pass may put its `down -v`, its `up -d` and its
    wait in any order that works, and may be followed by anything; what it may
    not do is start the base-file stack and leave the waiting to a later step.
    That is a narrowing, made in reviewer pass 3, and it costs the ability to
    split the pass across two steps — nothing here does, and the failure if
    anyone tries is a red with this docstring attached rather than a silence.

    **What is not recognised, and why that is safe.** `docker compose up --wait`
    waits natively and does not count, because `wait_for_health.sh` is what this
    repository standardised on and is stricter — it fails a service that
    declares no health check at all. `COMPOSE_FILE` in the environment is not
    read; nothing sets it. A stack started from a Makefile target or a wrapper
    script would not be seen either.

    Every one of those fails *red*: an idiom this test cannot see is an idiom it
    cannot find, so the base-file-only pass appears missing and the job fails
    loudly with the list of what it did find.

    **The opposite direction is the dangerous one, and it is not closed.** An
    event fabricated from text that never executes fails green and silently.
    `executed_lines` closes the two spellings that have actually occurred — a
    shell comment, and a line that only prints — and it does not close the
    class. A start inside `if false; then ... fi`, one inside a heredoc body,
    and one in a step carrying a `if:` condition that is false all still count
    as executed here, because this is a line scanner and not a shell. Chasing
    those with more parsing is deliberately not the plan: each would add
    machinery whose own blind spots are the same shape. What holds instead is
    the rule for anyone extending this — be reluctant to *add* events, relaxed
    about missing them — and the fact that a disabled step is visible in review
    in a way a missing assertion is not.
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
        "If it has been renamed, rename it here too rather than leaving this test looking "
        "for something that is gone."
    )

    per_script = [script_events(script) for script in run_scripts(job)]
    starts = [files for events in per_script for kind, files in events if kind == "up"]
    assert starts, (
        f"The `{DOCKER_JOB}` job runs no command that brings a stack up. Either it has "
        "changed shape, or every such command has been commented out — the second is what "
        "this assertion is really for, since a job whose steps are all disabled would "
        "otherwise leave nothing for the rule below to disagree with."
    )

    required = set(REQUIRED_SERVICES)
    verified: list[list[str]] = []
    unverified: list[list[str]] = []
    for events in per_script:
        for index, (kind, files) in enumerate(events):
            if kind != "up" or files != {BASE_COMPOSE_FILE}:
                continue
            waited: set[str] = set()
            for later_kind, payload in events[index + 1 :]:
                if later_kind == "up":
                    break
                waited |= payload
            (verified if required <= waited else unverified).append(sorted(waited))

    described = [sorted(files) or ["(no -f flag: the merged default)"] for files in starts]

    assert verified, "\n".join(
        [
            f"The `{DOCKER_JOB}` job never starts the stack on `{BASE_COMPOSE_FILE}` alone "
            f"and then waits on {list(REQUIRED_SERVICES)}.",
            f"  stack starts in this job, by the files each named: {described}",
            f"  base-file-only starts whose wait was short: {unverified or 'none'}",
            "",
            "The override mounts the checkout into `worker` and `beat`, so a merged `up` "
            "runs the working tree and not the wheel in the image: a packaging regression "
            "in `app/jobs` passes every merged gate and fails in every real deployment. The "
            "base-file-only pass is the only thing that runs what actually ships — and only "
            "if something waits on every service afterwards. A pass that starts a stack and "
            "never looks at it verifies nothing while looking exactly like verification.",
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
