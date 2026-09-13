"""Reaching E4-05's weekly-summary task, and the doubles it is driven with.

E4-05 ships the third of SPEC §7.4's tasks — "per-stream, per-node themed
summaries under the §5.1 contracts" — as a prompt, a typed contract, a gateway
call and an eval set. This module is how the suite reaches all four without any
test module holding its own copy of the arrangement (`docs/MISTAKES.md` entry 13:
one helper for a hazard several call sites face).

**The names below are the ticket's, written down rather than discovered.** E0-13
and E2-07 both found the validity task by matching a word in its name, because no
ticket had ever spelled a callable. E4-05 is different: its work order settles the
signature, the two contract classes and the six constants, so a test that went
looking would be able to agree with an implementation that had built something
else and called it something similar. They are transcribed here, once, with the
quotation each comes from — and `docs/MISTAKES.md` entry 19's rule applies to
them: **they are deliberately not derived**, so a rename in `app.ai.tasks` fails
here at a name instead of moving both sides of a comparison at once.

**Nothing here raises at fixture time** (`docs/MISTAKES.md` entry 44). Every
lookup is a callable a test invokes as the first statement of its own body, so a
deliverable that has not landed yet produces a FAILED naming it rather than an
ERROR in setup — a wall of setup errors proves nothing about the assertions the
tests exist to make, and survives the implementation landing.

**The gateway doubles are here because two modules need them and because what
they are *for* is easy to get wrong.** `RefusingGateway` fails on any attribute
access at all, which is how "an empty week makes no model call" is asserted
without naming the method a call would go through; `ScriptedGateway` answers with
whatever a test scripted and records what it was asked, which is how the
single-shot boundary (§7.4 — one call in, one validated object out) is counted.
Neither decides anything about the task: a double that answered plausibly for a
call the task should not have made would hide exactly the defect these exist to
catch.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13's placement for all three modules: "`ai/gateway.py` — provider-agnostic
# client (OpenAI-compatible base_url)", "`ai/tasks.py` — validity / moderation /
# summary / draft / draft-check calls", and the contracts beside them.
TASKS_MODULE = "app.ai.tasks"
CONTRACTS_MODULE = "app.ai.contracts"
GATEWAY_MODULE = "app.ai.gateway"

# ADR 0031 makes a recorded `prompt_version` the prompt file's path stem and ADR
# 0032 fixes the extension, so a version resolves to exactly one file here.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# ---------------------------------------------------------------------------
# The names E4-05's work order settles. **Deliberately not derived.**
# ---------------------------------------------------------------------------

# The task: "the gateway task in `tasks.py`, per-stream: the input is the week's
# comments for one stream". One call per stream, so nothing in the task crosses
# streams and the caller makes two calls for a week.
SUMMARIZE_STREAM = "summarize_stream"

# The renderer, beside `render_prompt`: it takes the stream and the comment texts
# and nothing else, which is what makes the identity boundary of acceptance
# criterion 2 structural rather than a matter of what a caller remembers to omit.
RENDER_SUMMARY_PROMPT = "render_summary_prompt"

# The six constants. The two placeholders are the prompt's own substitution
# points; the version and the timeout are what a call is made under; and the two
# empty-week values are what a week with no comments answers instead of calling a
# model at all.
SUMMARY_PROMPT_VERSION = "SUMMARY_PROMPT_VERSION"
SUMMARY_TIMEOUT_SECONDS = "SUMMARY_TIMEOUT_SECONDS"
SUMMARY_COMMENTS_PLACEHOLDER = "SUMMARY_COMMENTS_PLACEHOLDER"
SUMMARY_STREAM_PLACEHOLDER = "SUMMARY_STREAM_PLACEHOLDER"
EMPTY_WEEK_PROMPT_VERSION = "EMPTY_WEEK_PROMPT_VERSION"
EMPTY_WEEK_SUMMARY = "EMPTY_WEEK_SUMMARY"

# The two contract classes. The scope splits them: "the typed contract in
# `contracts.py`: the summary text, the themes it found, and room for the
# held-note (type only)", and "the stated response count is injected by the caller
# from data, never trusted from the model — the contract carries what the model
# must produce".
WEEKLY_SUMMARY_OUTPUT = "WeeklySummaryOutput"
WEEKLY_SUMMARY_RECORD = "WeeklySummaryRecord"
COMMENT_THEME = "CommentTheme"
COMMENT_STREAM = "CommentStream"

# The two streams SPEC §5.1 groups every comment under: "About the instructor" /
# "About the course". The tokens are the specification's vocabulary rather than
# this file's, and they are looked up against the contract's enum by name *or*
# value, so a member spelled either way is found and a stream that exists under
# neither spelling fails with a message naming both.
INSTRUCTOR_STREAM = "instructor"
COURSE_STREAM = "course"

# The one error class this ticket's refusals are asserted against, out of ADR
# 0056's four. Named rather than discovered for the reason `tests/fixtures/
# ai_tasks.py` gives: a test that discovered the class would agree with a gateway
# that had collapsed the taxonomy into one.
RESPONSE_INVALID_ERROR = "AIResponseInvalidError"


def normalised(name: str) -> str:
    """A member or field name with case, underscores, hyphens and spaces removed."""
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


class SummaryApi:
    """Every E4-05 deliverable a test needs, looked up when the test asks for it.

    Each accessor fails with the ticket's own words rather than raising, so the
    first line of a red says which deliverable is missing instead of showing a
    traceback from inside a fixture (`docs/MISTAKES.md` entry 44).
    """

    def __init__(self, import_app_module: Callable[[str], ModuleType | None]) -> None:
        self._import = import_app_module

    def module(self, name: str, quoting: str) -> ModuleType:
        """One `app.*` module, or a failure naming the deliverable that is missing."""
        found = self._import(name)
        if found is None:
            pytest.fail(f"There is no `{name}` module. E4-05's scope: {quoting}")
        return found

    def tasks(self) -> ModuleType:
        return self.module(
            TASKS_MODULE,
            "'the gateway task in `tasks.py`, per-stream: the input is the week's comments for "
            "one stream'.",
        )

    def contracts(self) -> ModuleType:
        return self.module(
            CONTRACTS_MODULE,
            "'the typed contract in `contracts.py`: the summary text, the themes it found, and "
            "room for the held-note (type only)'.",
        )

    def gateway(self) -> ModuleType:
        return self.module(
            GATEWAY_MODULE,
            "'the task round-trips against the mock AI service in CI' — the round trip goes "
            "through `app.ai.gateway`, which E0-13 shipped.",
        )

    def named(self, module: ModuleType, name: str, quoting: str) -> Any:
        """One public name out of a module, or a failure saying it is not there."""
        found = getattr(module, name, None)
        if found is None:
            pytest.fail(
                f"`{module.__name__}` exposes no `{name}` — it exposes "
                f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}. {quoting}"
            )
        return found

    def task(self) -> Any:
        """`summarize_stream`, the one callable E4-05 adds to `app.ai.tasks`."""
        return self.named(
            self.tasks(),
            SUMMARIZE_STREAM,
            "E4-05's work order settles the task's name and signature: "
            "`summarize_stream(comments, *, stream, response_count, gateway=None)`, one call per "
            "stream.",
        )

    def render(self) -> Any:
        """`render_summary_prompt`, beside E0-12's `render_prompt`."""
        return self.named(
            self.tasks(),
            RENDER_SUMMARY_PROMPT,
            "E4-05's work order settles the renderer: "
            "`render_summary_prompt(version, *, stream, comments)`, with the comments last in "
            "the message and nothing after them (`backend/app/ai/prompts/README.md`'s injection "
            "boundary).",
        )

    def constant(self, name: str) -> Any:
        """One of the six constants the work order settles."""
        return self.named(
            self.tasks(),
            name,
            f"E4-05's work order settles `{name}` in `app.ai.tasks`: the prompt version, the "
            "per-task timeout, the two prompt placeholders, and the two values an empty week "
            "answers with instead of calling a model.",
        )

    def contract(self, name: str) -> Any:
        """One of the contract classes, or a failure quoting the scope."""
        return self.named(
            self.contracts(),
            name,
            "E4-05's scope splits the contract in two: what the model must produce "
            f"(`{WEEKLY_SUMMARY_OUTPUT}`) and what the caller composes around it "
            f"(`{WEEKLY_SUMMARY_RECORD}`, carrying the response count injected from data and "
            "room for E6's held-note).",
        )

    def stream(self, token: str) -> Any:
        """The `CommentStream` member spelling `token`, matched by name or by value.

        SPEC §5.1 settles the two streams and settles no Python spelling, so the
        member is found by the specification's own word rather than by an
        identifier this file guessed at — the device `verdict_member` in
        `tests/integration/test_ai_gateway_validity_roundtrip.py` uses for §7.4's
        verdicts, for the same reason.
        """
        enum_class = self.contract(COMMENT_STREAM)
        matches = [
            member
            for member in enum_class
            if normalised(member.name) == token
            or (isinstance(member.value, str) and normalised(member.value) == token)
        ]
        if len(matches) != 1:
            pytest.fail(
                f"`{CONTRACTS_MODULE}.{COMMENT_STREAM}` offers "
                f"{[member.name for member in enum_class]} with values "
                f"{[member.value for member in enum_class]}, which does not carry exactly one "
                f"{token!r}. SPEC §5.1 groups every comment under 'About the instructor' / "
                "'About the course', and this suite needs both members to ask for a summary of "
                "one stream and to say which stream came back."
            )
        return matches[0]

    def error(self, name: str) -> type[BaseException]:
        """One of ADR 0056's failure classes, by name."""
        found = getattr(self.gateway(), name, None)
        if not (isinstance(found, type) and issubclass(found, BaseException)):
            pytest.fail(
                f"`{GATEWAY_MODULE}` exposes no exception class `{name}`. ADR 0056's table names "
                "the four the gateway raises, and E4-05's first acceptance criterion is that a "
                "persistent shape violation surfaces as one of them 'never as prose passed "
                "through'."
            )
        return found

    def prompt_path(self) -> Path:
        """The summary prompt file the application says it renders.

        Asked of the application rather than written down, which is the repair
        `tests/unit/test_mock_ai_rules.py` made after a prompt trim left a test
        pinned to a version nothing sent: ADR 0032 keeps every committed prompt on
        disk forever, so a literal path goes on passing after the tool has moved
        on.
        """
        return PROMPTS_DIR / f"{self.constant(SUMMARY_PROMPT_VERSION)}.md"


@pytest.fixture
def summary_api(import_app_module: Callable[[str], ModuleType | None]) -> SummaryApi:
    """E4-05's deliverables, looked up inside the test body rather than at setup.

    `import_app_module` drops every `app.*` module first, so a test that points a
    provider variable in its own body is pointing the module that is about to be
    imported (`docs/MISTAKES.md` entry 40).
    """
    return SummaryApi(import_app_module)


class RefusingGateway:
    """A gateway that fails on any use at all, for asserting that none was made.

    An empty week must reach no model (E4-05's scope, and SPEC §5.1's empty group
    "shows a one-line notice"), and the way to assert that without naming the
    method a call would travel through is to make *every* attribute fail. A double
    that answered a call it should never have received would let the empty-week
    path pass while quietly spending a provider request per empty stream, on every
    section, every Monday.

    Implicit special-method lookup bypasses `__getattr__`, so a truth test or a
    `repr` of this object does not trip it; only reaching for a member does.
    """

    def __init__(self) -> None:
        self.reached: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.reached.append(name)
        pytest.fail(
            f"The task reached `{name}` on the gateway for a week with no comments. E4-05's "
            "scope makes the empty week answer the contract's stated empty shape without a "
            "model call at all: zero comments in, no request out, the empty summary and no "
            "invented theme."
        )


class ScriptedGateway:
    """A gateway answering what a test scripted, recording every call it was asked.

    **It is not a stand-in for a provider.** The answers are supplied so that the
    *task's* behaviour around them can be asserted — the stream it refuses, the
    error it lets through, the response count it injects — and none of those is a
    property of the answer. What a real provider does with a real prompt is SPEC
    §9.3's question and `tests/evals/summary/` is where it is asked
    (`docs/MISTAKES.md` entry 30: a value the fixture supplies is not a value the
    suite can measure).

    Both entry points the repository already uses are answered — `run_task` and
    `run_task_with_usage`, the second being the one `tests/evals/live.py` calls —
    because which of them the task uses is not something a test may decide.
    Anything else fails naming what was reached.
    """

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def _next(self, kwargs: dict[str, Any]) -> Any:
        self.calls.append(dict(kwargs))
        if not self.answers:
            pytest.fail(
                f"The task made call {len(self.calls)} to the gateway and this double was "
                "scripted with fewer answers than that. SPEC §7.4's single-shot boundary is "
                "one call in and one validated object out, so a second call is the subject of "
                "the test rather than a gap in its script."
            )
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def run_task(self, **kwargs: Any) -> Any:
        return self._next(kwargs)

    def run_task_with_usage(self, **kwargs: Any) -> Any:
        answer = self._next(kwargs)
        return answer, _NoUsage()

    def __getattr__(self, name: str) -> Any:
        pytest.fail(
            f"The task reached `{name}` on the gateway. This double answers `run_task` and "
            "`run_task_with_usage`, which are the two entry points this repository already "
            "uses; a third is an interface question for the ticket rather than something a "
            "fixture should guess at."
        )


class _NoUsage:
    """A `TaskUsage` reporting nothing, for a call that reached no provider."""

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_tokens = 0
    requests = 0
    details: dict[str, int] = {}  # noqa: RUF012


def call_summarize(
    task: Any,
    comments: Any,
    *,
    stream: Any,
    response_count: int,
    gateway: Any = None,
) -> Any:
    """Call the task the way E4-05's work order spells it, and say so when it cannot be.

    The signature is settled — `summarize_stream(comments, *, stream, response_count,
    gateway=None)` — so this binds by name rather than trying call shapes until one
    stops raising: a helper that swallowed a `TypeError` would report a design
    nobody chose as working (`tests/fixtures/ai_tasks.py` gives the same reason at
    length).
    """
    signature = inspect.signature(task)
    offered = {"comments", "stream", "response_count", "gateway"}
    unknown = [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.name not in offered
        and parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    if unknown:
        pytest.fail(
            f"`{SUMMARIZE_STREAM}{signature}` requires {unknown}, which E4-05's settled "
            "signature does not offer: `summarize_stream(comments, *, stream, response_count, "
            "gateway=None)`. A parameter outside that is an interface question for the ticket."
        )
    return task(comments, stream=stream, response_count=response_count, gateway=gateway)
