"""The path classification that decides whether the eval floors run — ticket E2-12.

`docs/MISTAKES.md` entry 36: **a probe that decides whether a gate runs is itself
a gate.** The gate this one decides is SPEC §9.3's, and the notice in
`.github/workflows/ci.yml` today says what is at stake — the eval job holds "the
threat and self-harm recall floor", which `CLAUDE.md` calls a hard gate whose
lowering is a safety decision. A classification that answers "no AI surface" over
a diff that changed the prompt does not skip that job. The job runs, its live
steps switch themselves off by their own `if:`, and the job reports **success**
(ADR 0002's second amendment). Nothing anywhere is red or skipped.

E2-12's scope names the path set and argues the trade:

> the path set is `backend/app/ai/`, `tests/evals/`, *and the files that carry
> the model identifier*: `backend/app/config.py` (`ai_model_name`) and
> `.env.example`. Over-firing on an unrelated config edit costs one eval run;
> under-firing on a model bump is §9.3's gate not running, which is the worse
> trade by the ADR 0002 incident record.

(The field that quotation calls `ai_model_name` is `ai_provider_model_name` since
the configuration split of 2026-09-02, and there is a second one beside it for
the mock. The quotation is left as the ticket wrote it, and the path set it names
is unaffected — both fields live in `backend/app/config.py`.)

So the cases below are asymmetric on purpose. Every path the ticket names is
required to answer **yes**, because a missing yes is the gate not running. The
noes are the cost half, and they include the near misses a prefix comparison gets
wrong — `backend/app/ai_helpers.py` is not under `backend/app/ai/`, and
`.env.example.local` is not `.env.example`. The ticket says "under" for the two
directories and "equals" for the two files, and those are two different rules.

**One control runs first and it is not a formality.** The existing `inert`
classification is asked about a path it has always called inert, through the
invocation it has always used. E2-12 adds a second question to the same script,
and a script that answered the new question at the cost of the old one would pass
every case below while switching off pytest, the §4.1 invariant suite, both image
builds, Playwright and the audit — `docs/MISTAKES.md` entry 22, a new rule making
an earlier ticket's guarantee unrunnable, caught here rather than on somebody's
next pull request.

**The invocation is this module's guess, and it is the implementer's to move.**
E2-12 says the script "grows an `ai_surface` classification" and does not say how
it is asked for. The contract is written down once, at the top of this file, in
the same shape and for the same reason as
`tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`'s:
change `AI_SURFACE_ARGUMENTS` and `ai_surface()` and every assertion here
follows. What is not negotiable is the answers, which come from the ticket.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The script E0-38 built and E2-12 grows. Named here rather than discovered
# because `.github/workflows/ci.yml` invokes it by this path.
CLASSIFIER = REPO_ROOT / "scripts" / "ci" / "classify_changed_paths.py"

# ---------------------------------------------------------------------------
# The contract, which is the one thing in this module that is a guess.
#
#   python3 scripts/ci/classify_changed_paths.py --classification ai-surface -- <path>...
#     exit 0 — no changed path is an AI surface; the eval steps may stay off
#     exit 1 — at least one is; the eval steps must run
#     any other exit — an error, reported here rather than read as an answer
#
# **The polarity is E0-38's, kept rather than chosen.** That script's existing
# contract is exit 0 for "the expensive gates may short-circuit" and exit 1 for
# "run everything", and every failure route in the workflow emits the answer that
# runs everything. Keeping one meaning for one exit code across both questions is
# what lets the `changed` job map them with the same `case` statement — and a
# second question whose 0 meant the opposite would be a trap nobody could read off
# the shell.
#
# **`--` before the paths, and it is load-bearing.** E0-38's security review found
# that argparse answers before the script's own logic runs, so a repository file
# named `-h` exited 0 — the "may short-circuit" answer — and switched off six
# gates with the required check green (`docs/MISTAKES.md` entry 38). The same
# hazard applies to this question, and two of the cases below are paths that begin
# with a dash.
# ---------------------------------------------------------------------------
AI_SURFACE_ARGUMENTS = ("--classification", "ai-surface")

# The invocation the existing question uses, unchanged: no flag at all.
INERT_ARGUMENTS: tuple[str, ...] = ()

MAY_SKIP_EXIT = 0
MUST_RUN_EXIT = 1

AN_AI_SURFACE = "an AI surface"
NOT_AN_AI_SURFACE = "not an AI surface"
INERT = "inert"
NOT_INERT = "not inert"

CLASSIFIER_TIMEOUT_SECONDS = 60

# Paths E2-12's scope names, one case each. Every one of these must answer yes,
# and a no is SPEC §9.3's gate not running on the change that most needs it.
AI_SURFACE_PATHS: tuple[tuple[str, str], ...] = (
    ("the gateway that makes every model call", "backend/app/ai/gateway.py"),
    ("the task module the eval runner calls", "backend/app/ai/tasks.py"),
    ("the typed contracts the eval cases are built from", "backend/app/ai/contracts.py"),
    # The single sharpest case in the table. SPEC §9.3's gate is "prompt or model
    # changes", and this is the prompt. E0-38 already refuses to call it
    # documentation despite the `.md`; this is the other half of the same
    # sentence, and a classification that skipped the evals on a prompt edit
    # would skip them on the only diff they exist for.
    (
        "the prompt, which is Markdown and is not documentation",
        "backend/app/ai/prompts/validity.v1.md",
    ),
    (
        "a prompt in a subdirectory, since the rule is 'under', not 'in'",
        "backend/app/ai/prompts/v2/moderation.md",
    ),
    ("the eval runner itself", "tests/evals/runner.py"),
    ("an eval set", "tests/evals/validity/cases.py"),
    # A floor is the thing `.claude/review-fixtures/eval-floor-lowered.diff` is
    # about. A pull request that lowers one and does not re-run the evals is the
    # whole shape that review pass exists to catch.
    ("a floor declaration", "tests/evals/validity/floors.py"),
    ("the settings module that carries the model identifier", "backend/app/config.py"),
    ("the documented configuration surface, which names the model", ".env.example"),
)

# Paths that are not the AI surface. This half is the cost argument rather than
# the correctness one — the ticket says over-firing costs one eval run — but it is
# the half that keeps the design's promise that hundreds of live calls per merge
# is what this arrangement refuses.
NOT_AI_SURFACE_PATHS: tuple[tuple[str, str], ...] = (
    ("a documentation file", "docs/MISTAKES.md"),
    ("the authorization chokepoint", "backend/app/services/authz.py"),
    ("an API router", "backend/app/api/routes.py"),
    ("a unit test that is not an eval", "tests/unit/test_ai_contracts.py"),
    ("frontend source", "frontend/src/main.tsx"),
    ("the readme", "README.md"),
    # The near misses. `startswith("backend/app/ai")` answers yes to the first,
    # `startswith(".env.example")` to the third, and E2-12's scope says "under
    # `backend/app/ai/`" and "equals `.env.example`" — two different rules, and a
    # single prefix comparison collapses them into one.
    ("a module whose name starts with the AI package's", "backend/app/ai_helpers.py"),
    ("a directory whose name starts with the eval tree's", "tests/evals_archive/old.py"),
    ("a file whose name starts with the documented configuration's", ".env.example.local"),
    ("the real dotenv, which is gitignored and is not the documented surface", ".env"),
    ("a backup beside the settings module", "backend/app/config.py.bak"),
)


def run_classifier(arguments: tuple[str, ...], paths: tuple[str, ...]) -> int:
    """Run the classifier and hand back its exit status, or fail saying why it could not.

    A missing script is a failure here rather than an answer. Every "must run"
    assertion below is satisfied by a non-zero exit, and a script that does not
    exist exits non-zero for a reason that has nothing to do with AI paths — which
    would make half this module pass over a ticket nobody had started
    (`docs/MISTAKES.md` entry 3).
    """
    if not CLASSIFIER.is_file():
        pytest.fail(
            f"{CLASSIFIER.relative_to(REPO_ROOT)} does not exist, so nothing classifies a "
            "diff. E0-38 built it and E2-12 grows it with a second classification."
        )
    try:
        # S603: the executable is this interpreter and the arguments are a script
        # from this repository plus literal paths written in this file.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(CLASSIFIER), *arguments, "--", *paths],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLASSIFIER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"the classification ran for more than {CLASSIFIER_TIMEOUT_SECONDS}s over "
            f"{list(paths)}. It is a cheap step whose whole point is to be cheaper than the "
            "gates it decides about."
        )
    return completed.returncode


def answer(arguments: tuple[str, ...], paths: tuple[str, ...], names: tuple[str, str]) -> str:
    """Map an exit status onto one of the two answers, or fail on anything else."""
    status = run_classifier(arguments, paths)
    if status == MAY_SKIP_EXIT:
        return names[0]
    if status == MUST_RUN_EXIT:
        return names[1]
    pytest.fail(
        f"`{CLASSIFIER.name} {' '.join(arguments)} -- {' '.join(paths) or '(nothing)'}` "
        f"exited {status}, and the contract this module assumes names only "
        f"{MAY_SKIP_EXIT} and {MUST_RUN_EXIT}.\n"
        "\n"
        f"That is what a script which does not yet understand `{AI_SURFACE_ARGUMENTS[0]}` "
        "does: argparse rejects the unknown option and exits 2. E2-12 says the classifier "
        "'grows an `ai_surface` classification' and does not say how it is asked for, so "
        "the invocation is this module's guess — AI_SURFACE_ARGUMENTS and `ai_surface()` "
        "at the top of this file are the two lines that change if it is spelled another "
        "way.\n"
        "\n"
        "Reported rather than read as an answer. In the workflow any unexpected exit must "
        "send the run down the everything-runs path, and that tolerance is right there and "
        "wrong here: it would let a classifier that crashes on every input satisfy every "
        "'must run' case in this module."
    )


def ai_surface(paths: tuple[str, ...]) -> str:
    """Whether the classifier calls this diff an AI surface."""
    return answer(AI_SURFACE_ARGUMENTS, paths, (NOT_AN_AI_SURFACE, AN_AI_SURFACE))


def inert(paths: tuple[str, ...]) -> str:
    """The existing question, asked exactly as E0-38's workflow asks it."""
    return answer(INERT_ARGUMENTS, paths, (INERT, NOT_INERT))


def test_the_existing_inert_classification_still_answers_as_it_did() -> None:
    """The control, and it runs first: adding a question must not cost the old answer.

    E0-38's classification switches off pytest, the §4.1 invariant suite, both
    image builds, Playwright, the evals and the supply-chain audit on a
    documentation-only diff, and it is asked with no flag at all. A script that
    grew a `--classification` option and made it required, or that changed what a
    bare invocation means, would break that on every pull request in the
    repository while satisfying every AI-surface case below.

    Both answers are exercised, because a classifier that had stopped answering
    the old question at all would give one of them by accident.

    **The mutation this kills:** make the new option required, or change the
    default classification. **The near miss that must stay green:** any spelling
    of the new option that leaves the bare invocation alone.
    """
    assert inert(("docs/MISTAKES.md",)) == INERT, (
        "a documentation-only diff stopped classifying inert once the AI-surface question "
        "was added. E0-38's saving is gone, and every documentation pull request runs the "
        "full fifteen minutes again."
    )
    assert inert(("backend/app/services/authz.py",)) == NOT_INERT, (
        "a Python file classified inert. That switches off pytest and the §4.1 invariant "
        "suite on a change to the authorization chokepoint."
    )


def test_every_path_the_ticket_names_is_an_ai_surface() -> None:
    """The half where a wrong answer is SPEC §9.3's gate not running.

    Each of these is a path E2-12's scope names, and a `no` on any one of them is
    a pull request that changes the prompt, the model identifier, the gateway or
    the eval set itself and never measures a floor — with the `evals` job green,
    because its live steps switch themselves off and the job reports success.

    The prompt file is the one to read twice. It is Markdown, it is not
    documentation, and SPEC §9.3's gate is "prompt or model changes" — a rule
    written on suffixes gets every other case here right and that one
    catastrophically wrong, which is the same trap E0-38 already carries a case
    for in the other classification.

    **The mutation this kills:** a set that names `backend/app/ai/` and forgets
    the two files that carry the model identifier, which is the natural reading of
    "the AI code" and is the half E2-12's scope spends a paragraph arguing for.
    **The near miss that must stay green:** any spelling of the rule — a prefix
    table, a glob set, a `Path.is_relative_to` — since this judges the answer.
    """
    misread = [
        (why, path) for why, path in AI_SURFACE_PATHS if ai_surface((path,)) != AN_AI_SURFACE
    ]

    assert not misread, "\n".join(
        [
            "these paths are the AI surface and were classified as not:",
            *(f"  {path} — {why}" for why, path in misread),
            "",
            "A classification that answers no over a diff that has the thing does not skip "
            "the `evals` job. The job runs, its live steps switch themselves off by their "
            "own `if:`, the notice step runs in their place, and the job reports success — "
            "ADR 0002's second amendment, and `docs/MISTAKES.md` entry 36.",
            "",
            "E2-12: 'under-firing on a model bump is §9.3's gate not running, which is the "
            "worse trade by the ADR 0002 incident record.'",
        ]
    )


def test_a_path_outside_the_ai_surface_does_not_fire_the_gate() -> None:
    """The cost half, and the near misses that separate "under" from "starts with".

    E2-12's scope spells two different rules — *under* `backend/app/ai/` and
    `tests/evals/`, *equal to* `backend/app/config.py` and `.env.example` — and a
    single prefix comparison collapses them. `backend/app/ai_helpers.py` and
    `.env.example.local` are what that collapse looks like, and both are files
    somebody will plausibly create.

    Getting this wrong is not dangerous, which is exactly why it needs a test:
    over-firing costs a few minutes and a few cents per pull request, nothing goes
    red, and the design's promise that "hundreds of live calls per merge is
    exactly what this design refuses" erodes with nothing saying so.

    Dash-named paths are deliberately **not** in this table; they are their own
    test below, because their safe answer is the opposite one.

    **The mutation this kills:** `path.startswith("backend/app/ai")`, and the same
    shape for the other three entries. **The near miss that must stay green:**
    widening the set deliberately later, since nothing here says these paths stay
    outside it forever.
    """
    misread = [
        (why, path)
        for why, path in NOT_AI_SURFACE_PATHS
        if ai_surface((path,)) != NOT_AN_AI_SURFACE
    ]

    assert not misread, "\n".join(
        [
            "these paths are not the AI surface and were classified as it:",
            *(f"  {path} — {why}" for why, path in misread),
            "",
            "E2-12 names two rules and they are not the same one: *under* "
            "`backend/app/ai/` and `tests/evals/`, and *equal to* `backend/app/config.py` "
            "and `.env.example`. A prefix comparison satisfies the yes-table above and "
            "fires the paid gate on files that have nothing to do with a model.",
        ]
    )


def test_a_dash_named_path_is_read_as_a_path_and_not_as_an_option() -> None:
    """`docs/MISTAKES.md` entry 38, asked of the new question.

    E0-38's security review found that a repository root file named `-h` made
    argparse exit 0 before the script's logic ran — the "may short-circuit"
    answer — switching off six gates with the required check green. The workflow
    passes `--` and the script refuses leading-dash arguments as well, and both
    halves are deliberate.

    **The expected answer here is the opposite of the table above, and that is
    the whole reason this is its own test.** A path the script refuses is a path
    it could not classify, and every route out of a classification it could not
    make has to land on "run the gate" — exit 1, which E0-38's existing
    leading-dash cases already fix as the answer for these arguments. The
    dangerous answer is exit 0, and exit 0 is exactly what argparse produces when
    it recognises `-h` before the script's own logic runs.

    The second and third assertions are the near misses that make this more than
    a copy of E0-38's case. A dash-named file sitting *beside* a prompt edit is
    the shape with teeth: if argparse answers first the run exits 0, and SPEC
    §9.3's floors do not fire on a prompt change.

    **The mutation this kills:** drop the `--`, or stop refusing leading-dash
    arguments, in the new code path. **The near miss that must stay green:** an
    ordinary path that merely contains a dash.
    """
    assert ai_surface(("-h",)) == AN_AI_SURFACE, (
        "a path named `-h` produced the answer that lets the eval steps stay off. That is "
        "argparse answering before the classification did: it recognises `-h`, prints help "
        "and exits 0 — the 'may skip' status — so the script's own logic never ran "
        "(`docs/MISTAKES.md` entry 38)."
    )
    assert ai_surface(("-h", "backend/app/ai/prompts/validity.v1.md")) == AN_AI_SURFACE, (
        "a diff holding a dash-named file and a prompt edit was not classified as an AI "
        "surface. If argparse answered first, the exit status is `-h`'s and not the "
        "classification's — and SPEC §9.3's floors did not run on a prompt change."
    )
    assert ai_surface(("--classification", "backend/app/ai/gateway.py")) == AN_AI_SURFACE, (
        "a path spelled like this classification's own option consumed an argument instead "
        "of being read as a path, so the gateway edit beside it went unseen."
    )
    assert ai_surface(("docs/some-file-with-dashes.md",)) == NOT_AN_AI_SURFACE, (
        "an ordinary path containing dashes was refused or misread, so the protection above "
        "is wider than the hazard and every pull request now pays for an eval run."
    )


def test_a_mixed_diff_is_an_ai_surface() -> None:
    """One AI path is the whole answer, whatever it sits beside and in whichever order.

    Real pull requests are mixed. `CLAUDE.md` requires an ADR in the same pull
    request as the decision it records, so a gateway change arrives beside a
    document as a matter of process — and E2-12's own pull request touches
    `tests/evals/`, `.github/workflows/ci.yml` and a ticket at once.

    Both orders, because a rule written as a fold can be sensitive to which path
    it meets first and nothing about a diff fixes that order.

    **The mutation this kills:** decide on the first path and return, or take the
    majority.
    """
    misread = [
        list(paths)
        for paths in (
            ("docs/MISTAKES.md", "backend/app/ai/prompts/validity.v1.md"),
            ("backend/app/ai/prompts/validity.v1.md", "docs/MISTAKES.md"),
            ("README.md", "frontend/src/main.tsx", "backend/app/config.py"),
        )
        if ai_surface(paths) != AN_AI_SURFACE
    ]

    assert not misread, "\n".join(
        [
            "these diffs hold an AI path beside something else and did not fire the gate:",
            *(f"  {paths}" for paths in misread),
        ]
    )


def test_an_empty_diff_is_an_ai_surface() -> None:
    """The edge, decided toward running the gate — the same direction E0-38 took.

    An empty path list is not "nothing changed". It is far more often the diff
    computation failing: a base ref that is not there, a shallow clone with no
    merge base, a comparison against the wrong SHA. In each of those "nothing
    changed" is false, and the change may be the model bump.

    The cost of deciding it this way is one eval run on a genuinely empty diff,
    which is rare and cheap. The cost of the other way is SPEC §9.3's floors not
    running on a change nobody could see, with the required check green.

    **The mutation this kills:** `if not paths: return False`, which reads as a
    harmless base case and is the same one E0-38 had to argue about.
    """
    assert ai_surface(()) == AN_AI_SURFACE, (
        "an empty diff was classified as not an AI surface, so a run that computed no "
        "changed paths would skip SPEC §9.3's floors. An empty list is most often a broken "
        "path computation rather than an empty change, and E0-38's classification takes the "
        "same direction for the same reason."
    )
