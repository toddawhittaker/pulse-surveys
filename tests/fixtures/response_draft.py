"""E7-04 — the AI draft and the draft check: the door, the provider, and the week they read.

Eight test modules need the same four things, and nothing in this repository
answers them yet:

  - **The two routes, found rather than spelled.** E7-04's work order (decision
    1) settles `POST /api/instructor/sections/{section_id}/weeks/{week_id}/
    response-draft` and `.../draft-check` in `app.api.instructor`, "matching the
    path shape `api/instructor.py` already uses for a section-week; if it uses
    another key for the week, use that". So each route is the one `POST` that
    module mounts whose path ends in its segment, the section parameter is the one
    naming a section, and the week parameter is filled the way the report route's
    is filled when the two are spelled alike — see `week_value_for`.
  - **A provider the test controls**, on a real socket the application's own
    gateway opens, so that what a task *sent* and what the model *answered* are
    both in the test's hands without naming a single function inside
    `app.ai.tasks` (the ticket names none). The gateway is reached the way every
    route-level AI test here reaches it: `MOCK_AI_PROVIDER_BASE_URL`, read by
    `AIGateway(live=False)` in development (ADR 0118), set before the application
    is imported (`docs/MISTAKES.md` entry 40).
  - **One section-week holding every kind of comment the ticket names**, in the
    canonical report world (`tests/fixtures/report_api.py`), planted through the
    product's own writers: a published comment in a shown stream, an excluded one
    (excluded through E6-03's decision route), a still-flagged one, a kept one,
    and one in a stream held below the threshold — and the week's stored
    summaries with their stored themes.
  - **The provider answers, built through the task contracts.** ADR 0031: "the
    gateway supplies both values; the model never reports them", so an answer is
    the contract's own output fields and nothing else — the device
    `tests/integration/test_ai_gateway_validity_roundtrip.py::provider_payload`
    uses.

**What this file settles and what it discovers.** Settled by the ticket or the
work order, and transcribed: the two route segments, the request bodies
(`{}` and `{"draft": str}`), the answer members (`text`; `unaddressed` of
`{label, comment_count}`), the 502 status for an unusable answer, the gather's
name and signature (decision 3), `CheckTheme` and `DraftCheckOutput`, and
`ResponseDraftOutput`. Discovered, with an ambiguity failing by name rather than
being guessed: the week parameter's spelling, and which field of
`ResponseDraftOutput` carries the draft and which field of `DraftCheckOutput`
carries the themes — the ticket names those classes and none of their fields.

**Nothing here decides what a route should answer.** It plants rows, makes
requests and records what was sent; every expectation is written in the test
that makes it (`docs/MISTAKES.md` entries 19 and 30). In particular nothing here
measures a reused run for the implementation: `longest_shared_run` is this
suite's own ruler, written out, so a claim like "this draft reuses forty
characters of that comment" is checked against a definition the code under test
cannot move.

**Every guard is a plain function called from a test body** (`docs/MISTAKES.md`
entry 44). On a tree where E7-04 is unbuilt each test fails naming the missing
route, contract or function, rather than erroring in setup. The `draft_door`
fixture builds only what already exists: the report world, a launch, and a
socket.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import types
import typing
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from typing import Any

import pytest

from fixtures.instructor_decisions import EXCLUDE, KEEP, OK, DecisionDoor, a_reason
from fixtures.mock_ai import MOCK_AI_PROVIDER_BASE_URL_VARIABLE
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import (
    FULL_WEEK,
    FULL_WEEK_COMMENTS,
    INSTRUCTOR_API_MODULE,
    INSTRUCTOR_ROLE,
    PATH_PARAMETER,
    PAYLOAD_STREAM_KEY,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUMMARY_FIELD,
    SUPPRESSED_FIELD,
    ReportDoor,
    report_route,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.routing import every_route
from fixtures.submit import (
    COPY_MAPPING_NAME,
    COPY_MODULES_FUNCTION,
    COPY_PACKAGE,
    CSRF_HEADER,
    csrf_token_for,
    served_text,
    session_cookie_names,
    session_secret,
)
from fixtures.summary_job import (
    SUMMARY_MODEL_ID_COLUMN,
    SUMMARY_PROMPT_VERSION_COLUMN,
    SUMMARY_RESPONSE_COUNT_COLUMN,
    SUMMARY_SECTION_COLUMN,
    SUMMARY_STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    SUMMARY_THEMES_COLUMN,
    SUMMARY_WEEK_COLUMN,
    WEEKLY_SUMMARY_TABLE,
)

# ---------------------------------------------------------------------------
# The names E7-04's ticket and work order settle, spelled once.
# ---------------------------------------------------------------------------

# Work-order decision 1: the two routes' last segments, their bodies and answers.
DRAFT_SEGMENT = "response-draft"
CHECK_SEGMENT = "draft-check"
DRAFT = "draft"
CHECK = "check"
SEGMENT_OF = {DRAFT: DRAFT_SEGMENT, CHECK: CHECK_SEGMENT}

CHECK_DRAFT_FIELD = "draft"
DRAFT_TEXT_FIELD = "text"
UNADDRESSED_FIELD = "unaddressed"
LABEL_FIELD = "label"
COUNT_FIELD = "comment_count"

# Work-order decision 2: a model answer refused by either structural check is a
# 502 carrying one fixed sentence from `copy/`; a section not taught or a week
# not yet published is the report's own 404, byte for byte.
UNUSABLE_ANSWER_STATUS = 502
NOT_FOUND_STATUS = 404

# The ticket's "Owns" and the work order's residue B: the contract names.
CONTRACTS_MODULE = "app.ai.contracts"
RESPONSE_DRAFT_OUTPUT = "ResponseDraftOutput"
DRAFT_CHECK_OUTPUT = "DraftCheckOutput"
CHECK_THEME = "CheckTheme"
COMMENT_THEME = "CommentTheme"
WEEKLY_SUMMARY_OUTPUT = "WeeklySummaryOutput"

# Work-order decision 3: the gather, its home and its signature.
REPORTING_MODULE = "app.services.reporting"
RESPONSE_GATHER = "response_gather"
RESPONSE_GATHER_TYPE = "ResponseGather"
GATHER_KEYWORDS = ("section_id", "week_id", "for_on_behalf")

# The prompt versions a stored summary row carries. `summary.v1` is the ordinary
# prompt; `summary.v3` is the small-N prompt ADR 0188 names ("The small-N summary
# prompt is `summary.v3`"), and ADR 0188 again: "A stored ordinary-mode
# (`summary.v1`) summary of a stream that is now held is not served."
ORDINARY_SUMMARY_VERSION = "summary.v1"
SMALL_N_SUMMARY_VERSION = "summary.v3"
A_SUMMARY_MODEL_ID = "e7-04-a-stored-summary-model"

# ADR 0031's two audit fields, by normalised name. The gateway supplies them and a
# provider answer must not (`provider_payload` in the validity roundtrip module).
AUDIT_FIELD_NAMES = (
    "promptversion",
    "promptrevision",
    "promptid",
    "modelid",
    "model",
    "modelname",
)

# **This suite's choice**, used only to break a tie if `ResponseDraftOutput`
# carries more than one required text field. The ticket names the class and not
# its fields; a single required text field is read without consulting this.
DRAFT_TEXT_NAMES = ("draft", "text", "response", "body", "message", "draft_text")

DRAFT_IS_OWED = (
    "E7-04's work order (decision 1) mounts `POST /api/instructor/sections/{section_id}/weeks/"
    "{week_id}/response-draft` and `.../draft-check` in `app.api.instructor`, matching the path "
    "shape that module already uses for a section-week, both behind `csrf_verified_instructor`. "
    'Draft body `{}`; check body `{"draft": str}`. Answers: `{"text": str}` and '
    '`{"unaddressed": [{"label": str, "comment_count": int | null}]}`.'
)

# ---------------------------------------------------------------------------
# The world's planted texts. Each carries a run of forty-odd characters that is
# its own and nobody else's, so "this draft reuses that comment" is a fact about
# two strings this file wrote rather than a coincidence of common words.
# ---------------------------------------------------------------------------

# Comments, by what students can see of them (SPEC §5.2, §4).
PUBLISHED_COMMENT = (
    "E7-04 published: the Tuesday quiz review untangled the recursion examples for me"
)
# No number word anywhere in a lifted run: a draft lifting one must be refused for
# the lift alone, never for the count rule a held week also applies (residue A).
EXCLUDED_COMMENT = (
    "E7-04 excluded: the marking rubric for the lab session contradicted the handout entirely"
)
FLAGGED_COMMENT = "E7-04 flagged: the seminar leader mocked the questions people asked in week one"
KEPT_COMMENT = "E7-04 kept: the reading pack arrived late and most of the scans were unreadable"
HELD_COMMENT = "E7-04 held: the course forum went silent so nobody answered the dataset question"

# The run of each a draft lifts. Each is a slice of its comment, asserted to be
# one by `assert_the_planted_texts_are_what_this_file_says`.
PUBLISHED_RUN = "quiz review untangled the recursion examples"
EXCLUDED_RUN = "marking rubric for the lab session contradicted the handout"
FLAGGED_RUN = "seminar leader mocked the questions people asked"
KEPT_RUN = "reading pack arrived late and most of the scans"
HELD_RUN = "course forum went silent so nobody answered"

RUN_OF = {
    PUBLISHED_COMMENT: PUBLISHED_RUN,
    EXCLUDED_COMMENT: EXCLUDED_RUN,
    FLAGGED_COMMENT: FLAGGED_RUN,
    KEPT_COMMENT: KEPT_RUN,
    HELD_COMMENT: HELD_RUN,
}

# How long a run has to be before this suite calls it reuse. The guard the
# ticket reuses (`_reused_run`) refuses at twenty normalized characters (the
# owner's ruling of 2026-09-09, as the module named below pins it, standing on
# nineteen, twenty and twenty-one). Every lift planted here
# is far over that — at least `A_CLEAR_LIFT` — and every unrelated pair far
# under, so nothing in E7-04's suite stands on the bound itself: the bound is
# `tests/integration/test_a_small_n_summary_never_reuses_a_commenters_words.py`'s
# subject, and this suite's is *which comments* it is applied to.
THE_GUARD_BOUND = 20
A_CLEAR_LIFT = 40


def a_draft_lifting(run: str) -> str:
    """A draft whose only long overlap with any planted comment is `run`.

    The frame is written so that it shares nothing long with any comment here,
    which `assert_the_planted_texts_are_what_this_file_says` measures.
    """
    return f"Thank you for writing this week. I read that the {run}, and I will change it."


# The stored summaries and their themes. The counts are chosen to be findable: no
# number this world writes anywhere else is any of them, so finding one in a
# prompt is evidence and missing one is not a search that went blind.
SHOWN_SUMMARY_TEXT = (
    "E7-04 shown-stream summary: students praised the quiz review and asked for slower proofs."
)
HELD_SUMMARY_TEXT = "E7-04 held-stream summary: the course forum and the dataset were raised."
HELD_V1_SUMMARY_TEXT = "E7-04 an old ordinary-mode summary of the held stream, never served."

SHOWN_THEME_A = "E7-04 slower proofs in the Thursday lecture"
SHOWN_THEME_A_COUNT = 641
SHOWN_THEME_B = "E7-04 the quiz review helped"
SHOWN_THEME_B_COUNT = 523
HELD_THEME = "E7-04 the course forum goes unanswered"
HELD_THEME_COUNT = 857
HELD_V1_THEME = "E7-04 an old-format theme of the held stream"
HELD_V1_THEME_COUNT = 379

SHOWN_SUMMARY_RESPONSES = 9
HELD_SUMMARY_RESPONSES = 1

# A theme no summary holds.
AN_INVENTED_THEME = "E7-04 parking near the science building"

# ---------------------------------------------------------------------------
# The fix round's count rule (work order G1), as drafts. In a week with a held
# stream a draft states no number of anything except a named course structure:
# a count token is a digit run, a cardinal word from zero to ninety-nine (with
# hyphenated compounds) or "hundred", or one of both, half, couple, several, few,
# dozen, pair, handful, majority, minority — allowed only when the word right
# before it is week(s), chapter, lab, unit, module, section, page(s), question,
# assignment, quiz, exam, day(s), hour(s), minute(s), part, step, problem or
# version. Ordinals are not count tokens.
#
# Every phrasing the fix-round review found is here, by name, and so is one draft
# per token class G1 lists. Each is the clause before a frame that itself carries
# no count token.
# ---------------------------------------------------------------------------

STATES_A_COUNT = "states_a_count_of_people"


def a_draft_saying(clause: str) -> str:
    """A draft made of `clause` and a frame carrying no count token."""
    return f"Thank you for writing. {clause}, so I will post worked steps after each class."


COUNTING_CLAUSES: dict[str, str] = {
    # The review's phrasings.
    "two-of-your-classmates": "Two of your classmates asked for slower derivations",
    "digit-learners-said": "2 learners said the derivations went too fast",
    "the-7-who-responded": "The 7 who responded asked for slower derivations",
    "twenty-students": "Twenty students asked for slower derivations",
    "both-students": "Both students asked for slower derivations",
    "half-the-class": "Half the class asked for slower derivations",
    "a-few-of-you": "A few of you asked for slower derivations",
    # The residue-A pair this module began with.
    "three-of-you": "Three of you asked for slower derivations",
    "digit-students": "3 students asked for slower derivations",
    # One per remaining token class G1 lists.
    "zero": "Zero complaints were about the office hours",
    "ninety-nine": "Ninety-nine of you asked for slower derivations",
    "hyphenated-compound": "Twenty-one of you asked for slower derivations",
    "hundred": "A hundred comments asked for slower derivations",
    "several": "Several of you asked for slower derivations",
    "couple": "A couple of you asked for slower derivations",
    "dozen": "A dozen of you asked for slower derivations",
    "pair": "A pair of you asked for slower derivations",
    "handful": "A handful of you asked for slower derivations",
    "majority": "The majority of you asked for slower derivations",
    "minority": "A minority of you asked for slower derivations",
    # Not a count of people, and still refused: G1 forbids "a number of anything".
    "a-number-of-things": "You asked for slower derivations and I will add 3 worked examples",
    # A structure word before the first number does not license the second.
    "and-after-weeks": "Weeks 3 and 4 drew requests for slower derivations",
}

# The accepted twins: a number naming a course structure, an ordinal, or none.
ALLOWED_CLAUSES: dict[str, str] = {
    "in-week-3": "In week 3 we will slow the derivations down",
    "capital-week": "From Week 4 the derivations will be slower",
    "chapter-five": "Chapter five has the derivations worked out",
    "chapter-hyphenated": "Chapter twenty-one covers the derivations",
    "first-the-lab": "First, the lab notes; second, slower derivations",
    "lab-and-question": "Lab 2 and question 4 will carry worked derivations",
    "no-number": "You asked for slower derivations",
}


def count_rule() -> Any:
    """`reporting.states_a_count_of_people`, or a failure naming it (fix-round G1)."""
    found = getattr(reporting_module(), STATES_A_COUNT, None)
    if not callable(found):
        pytest.fail(
            f"`{REPORTING_MODULE}` exposes no `{STATES_A_COUNT}(text) -> bool`. The fix round's G1: "
            "'One function in `services/reporting.py` holds the rule'; G2 has the eval grader call "
            "the same function, so there is one copy of it."
        )
    return found


def assert_the_planted_texts_are_what_this_file_says() -> None:
    """The control every module calls first. **A red here means this file is wrong.**

    Each run is a slice of its own comment and at least `A_CLEAR_LIFT` long; each
    lifting draft shares at most `THE_GUARD_BOUND - 1` characters with every
    *other* planted comment, so a refusal of it can only be about the comment it
    lifts; and no stored count appears in any other planted text.
    """
    for comment, run in RUN_OF.items():
        assert run in comment, f"{run!r} is not a slice of {comment!r}."
        assert len(run) >= A_CLEAR_LIFT, f"{run!r} is {len(run)} characters, not {A_CLEAR_LIFT}."
        draft = a_draft_lifting(run)
        assert longest_shared_run(draft, comment) >= A_CLEAR_LIFT, (
            f"The draft lifting {run!r} shares only {longest_shared_run(draft, comment)} "
            "normalized characters with its own comment."
        )
        for other in (*RUN_OF, *FULL_WEEK_COMMENTS):
            if other == comment:
                continue
            shared = longest_shared_run(draft, other)
            assert shared < THE_GUARD_BOUND, (
                f"The draft lifting {run!r} shares {shared} characters with {other!r} as well, so "
                "a refusal of it could be about that comment rather than the one it lifts."
            )
    for draft in (*(a_draft_lifting(run) for run in RUN_OF.values()), A_PLAIN_DRAFT):
        counting = states_a_number(draft)
        assert not counting, (
            f"The draft {draft!r} carries {counting}, so in a week with a held stream it could be "
            "refused by the count rule (residue A) rather than for what its test is about."
        )
    numbers = (SHOWN_THEME_A_COUNT, SHOWN_THEME_B_COUNT, HELD_THEME_COUNT, HELD_V1_THEME_COUNT)
    planted = (
        *RUN_OF,
        *FULL_WEEK_COMMENTS,
        SHOWN_SUMMARY_TEXT,
        HELD_SUMMARY_TEXT,
        HELD_V1_SUMMARY_TEXT,
        SHOWN_THEME_A,
        SHOWN_THEME_B,
        HELD_THEME,
        HELD_V1_THEME,
    )
    for number in numbers:
        for text in planted:
            assert not carries_number(text, number), f"{number} appears in {text!r}."
    assert len(set(numbers)) == len(numbers), "Two stored counts are the same number."


# ---------------------------------------------------------------------------
# This suite's rulers. Written out, never imported from the code under test.
# ---------------------------------------------------------------------------


def normalized(text: str) -> str:
    """Case and runs of whitespace normalized, as the 2026-09-09 reuse rule is stated."""
    return " ".join(text.lower().split())


def longest_shared_run(left: str, right: str) -> int:
    """The longest run of characters two strings share, after normalizing both.

    The same quadratic walk `test_a_small_n_summary_never_reuses_a_commenters_words.py`
    writes out, for that module's reason: it is the measurement every claim here
    rests on, so it is this suite's and not the implementation's.
    """
    first, second = normalized(left), normalized(right)
    best = 0
    for start in range(len(first)):
        for end in range(start + best + 1, len(first) + 1):
            if first[start:end] in second:
                best = end - start
            else:
                break
    return best


# Words that state a number, for this suite's own control that a draft meant to be
# judged on something else states none. Deliberately broad — wider than any count
# rule needs — because it guards this suite's inputs, not the product's rule.
NUMBER_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "dozen",
    "half",
    "several",
    "couple",
    "few",
    # Fix-round G1's remaining count tokens, so this control stays at least as broad.
    "zero",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "both",
    "pair",
    "handful",
    "majority",
    "minority",
)


def states_a_number(text: str) -> list[str]:
    """Every digit run and number word in `text`."""
    digits = re.findall(r"\d+", text)
    words = [word for word in re.findall(r"[a-z]+", text.lower()) if word in NUMBER_WORDS]
    return digits + words


def carries_number(text: str, number: int) -> bool:
    """Whether `number` appears in `text` as a number of its own.

    Bounded by any letter or digit on either side, so `857` is not found inside a
    uuid's hex (`a857f`), a larger number (`18570`) or a decimal (`8.857`'s tail is
    bounded by `.`, which is deliberately *not* a boundary character here — a count
    rendered as `857.0` is still the count).
    """
    return re.search(rf"(?<![0-9A-Za-z]){number}(?![0-9A-Za-z])", text) is not None


def strings_in(node: Any) -> list[str]:
    """Every string anywhere inside a decoded JSON document, keys included."""
    found: list[str] = []
    if isinstance(node, str):
        found.append(node)
    elif isinstance(node, Mapping):
        for key, value in node.items():
            found.append(str(key))
            found.extend(strings_in(value))
    elif isinstance(node, list | tuple):
        for item in node:
            found.extend(strings_in(item))
    elif node is not None:
        found.append(str(node))
    return found


# ---------------------------------------------------------------------------
# The provider: an OpenAI-compatible endpoint this suite scripts.
# ---------------------------------------------------------------------------


@dataclass
class Sent:
    """One request the application's gateway made to the provider."""

    path: str
    raw: str
    payload: Any

    def text(self) -> str:
        """Every string the request carried, decoded out of its JSON, joined.

        Decoded rather than searched raw, because JSON escapes a character a
        planted text might carry and a raw search would then miss it.
        """
        return "\n".join(strings_in(self.payload)) if self.payload is not None else self.raw


def chat_completion(content: str, request: Any, model: str) -> dict[str, Any]:
    """An OpenAI-compatible completion carrying `content`, however it was asked for.

    Copied from `tests/integration/test_ai_gateway_validity_roundtrip.py`'s
    `chat_completion` rather than adapted (`docs/MISTAKES.md` entry 37): native JSON
    output is ADR 0053's route, and a tool-call answer is given only when the
    request declared a tool, so this stub does not decide which the gateway uses.
    """
    message: dict[str, Any] = {"role": "assistant", "content": content}
    finish_reason = "stop"
    tools = request.get("tools") if isinstance(request, Mapping) else None
    if isinstance(tools, list) and tools:
        names = [
            str((tool.get("function") or {}).get("name") or tool.get("name") or "")
            for tool in tools
            if isinstance(tool, Mapping)
        ]
        names = [name for name in names if name]
        if names:
            chosen = next(
                (name for name in names if any(w in name.lower() for w in ("result", "final"))),
                names[-1],
            )
            message["tool_calls"] = [
                {
                    "id": "call_e7_04_stub",
                    "type": "function",
                    "function": {"name": chosen, "arguments": content},
                }
            ]
            finish_reason = "tool_calls"
    return {
        "id": "chatcmpl-e7-04-stub",
        "object": "chat.completion",
        "created": 1_760_000_000,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class _StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence. The default writes every request to stderr."""

    def _send(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        payload: Any = None
        with contextlib.suppress(ValueError):
            payload = json.loads(raw)
        provider: ScriptedProvider = self.server.provider  # type: ignore[attr-defined]
        provider.sent.append(Sent(path=self.path, raw=raw, payload=payload))
        requested = payload.get("model") if isinstance(payload, Mapping) else None
        model = requested if isinstance(requested, str) and requested else "e7-04-stub-model"
        self._send(200, json.dumps(chat_completion(provider.answer, payload, model)))

    def do_GET(self) -> None:  # noqa: N802
        self._send(200, json.dumps({"object": "list", "data": [{"id": "e7-04-stub-model"}]}))


class _StubServer(ThreadingHTTPServer):
    daemon_threads = True
    provider: ScriptedProvider


@dataclass
class ScriptedProvider:
    """An OpenAI-compatible endpoint answering whatever the test last scripted.

    **One answer, repeated**, because a test scripts the answer for the request it
    is about to make, and the gateway's one bounded re-ask (ADR 0053) must get the
    same answer rather than a fallback this stub invented. Until a test scripts an
    answer the stub answers an empty object, which validates against no task
    contract here — so a request the test did not expect is a visible failure
    rather than a plausible success.
    """

    answer: str = "{}"
    sent: list[Sent] = field(default_factory=list)
    _server: _StubServer | None = None

    def start(self) -> None:
        server = _StubServer(("127.0.0.1", 0), _StubHandler)
        server.provider = self
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._server = server

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def base_url(self) -> str:
        if self._server is None:  # pragma: no cover - the fixture always starts it
            raise RuntimeError("the stub provider was not started")
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    def script(self, content: Mapping[str, Any]) -> None:
        """Answer every later completion request with `content`, as JSON."""
        self.answer = json.dumps(content)

    @property
    def completions(self) -> list[Sent]:
        return [entry for entry in self.sent if entry.path.endswith("/chat/completions")]

    def text_since(self, before: int) -> str:
        """Every string the completion requests after the first `before` carried."""
        return "\n".join(entry.text() for entry in self.completions[before:])


# ---------------------------------------------------------------------------
# The contracts, and answers built through them.
# ---------------------------------------------------------------------------


def contracts() -> Any:
    try:
        return import_module(CONTRACTS_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        if missing.name not in {CONTRACTS_MODULE, "app.ai", "app"}:
            raise
        pytest.fail(f"There is no `{CONTRACTS_MODULE}`. E0-12 ships it.")


def contract(name: str) -> Any:
    """One class out of `app.ai.contracts`, or a failure naming the deliverable."""
    module = contracts()
    found = getattr(module, name, None)
    if not isinstance(found, type):
        pytest.fail(
            f"`{CONTRACTS_MODULE}` exposes no `{name}`. E7-04's work order, residue B: 'Do NOT make "
            "`CommentTheme.comment_count` optional. Add a separate check-only theme type "
            "(`CheckTheme` with `comment_count: int | None`) used by `DraftCheckOutput`.' The "
            "ticket: '`ResponseDraftOutput` and `DraftCheckOutput` already exist in "
            "`backend/app/ai/contracts.py`'."
        )
    return found


def _normalised(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "")


def _bare(annotation: Any) -> Any:
    while hasattr(annotation, "__metadata__"):
        annotation = annotation.__origin__
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        arguments = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(arguments) == 1:
            return _bare(arguments[0])
    return annotation


def referenced_models(annotation: Any) -> set[type]:
    """Every class reachable from one annotation, one level down."""
    annotation = _bare(annotation)
    if isinstance(annotation, type):
        return {annotation}
    found: set[type] = set()
    for argument in typing.get_args(annotation):
        found |= referenced_models(argument)
    return found


def _is_audit(name: str) -> bool:
    return _normalised(name) in AUDIT_FIELD_NAMES


def theme_list_field() -> str:
    """The one field of `DraftCheckOutput` whose items are `CheckTheme`."""
    output, theme = contract(DRAFT_CHECK_OUTPUT), contract(CHECK_THEME)
    found = [
        name
        for name, model_field in output.model_fields.items()
        if theme in referenced_models(model_field.annotation)
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{DRAFT_CHECK_OUTPUT}` declares {len(found)} fields of `{CHECK_THEME}` ({found}); its "
            f"fields are {dict(output.model_fields)}. Residue B: '`CheckTheme` ... used by "
            "`DraftCheckOutput`' — exactly one list of them is the themes the check names."
        )
    return found[0]


def check_answer(themes: Sequence[tuple[str, int | None]]) -> dict[str, Any]:
    """A provider answer for the check: these themes, built as `CheckTheme`s.

    Built through the contract so a theme the contract would refuse is a failure
    here, before any request — a stub answer the gateway refuses on shape would
    produce a 502 for a reason unrelated to the structural check under test
    (`docs/MISTAKES.md` entry 3).
    """
    theme = contract(CHECK_THEME)
    items = [
        theme(**{LABEL_FIELD: label, COUNT_FIELD: count}).model_dump(mode="json")
        for label, count in themes
    ]
    answer: dict[str, Any] = {theme_list_field(): items}
    output = contract(DRAFT_CHECK_OUTPUT)
    for name, model_field in output.model_fields.items():
        if name in answer or _is_audit(name) or not model_field.is_required():
            continue
        pytest.fail(
            f"`{DRAFT_CHECK_OUTPUT}.{name}` is required and is neither the theme list nor an audit "
            "field, so this suite cannot build an answer without inventing its value. That is an "
            "interface question for the ticket."
        )
    return answer


def draft_text_field() -> str:
    """The one required text field of `ResponseDraftOutput` that is not an audit field."""
    output = contract(RESPONSE_DRAFT_OUTPUT)
    texts = [
        name
        for name, model_field in output.model_fields.items()
        if model_field.is_required()
        and not _is_audit(name)
        and _bare(model_field.annotation) is str
    ]
    if len(texts) > 1:
        texts = [name for name in texts if _normalised(name) in DRAFT_TEXT_NAMES]
    if len(texts) != 1:
        pytest.fail(
            f"`{RESPONSE_DRAFT_OUTPUT}` has no single required text field this suite can read as the "
            f"draft (candidates {texts}; fields {dict(output.model_fields)}). `DRAFT_TEXT_NAMES` in "
            "tests/fixtures/response_draft.py is the tie-break, and it is this suite's choice."
        )
    return texts[0]


def draft_answer(text: str) -> dict[str, Any]:
    """A provider answer for the draft: `text`, and nothing the gateway supplies."""
    answer: dict[str, Any] = {draft_text_field(): text}
    output = contract(RESPONSE_DRAFT_OUTPUT)
    for name, model_field in output.model_fields.items():
        if name in answer or _is_audit(name) or not model_field.is_required():
            continue
        pytest.fail(
            f"`{RESPONSE_DRAFT_OUTPUT}.{name}` is required and is neither the draft nor an audit "
            "field, so this suite cannot build an answer without inventing its value."
        )
    return answer


def stored_themes(themes: Sequence[tuple[str, int]]) -> list[dict[str, Any]]:
    """Themes as a summary row stores them: `CommentTheme`s, dumped to JSON.

    Built through the weekly summary's own theme contract rather than spelled as
    dicts here, so the stored shape is the writer's shape and not this file's.
    """
    theme = contract(COMMENT_THEME)
    return [
        theme(**{LABEL_FIELD: label, COUNT_FIELD: count}).model_dump(mode="json")
        for label, count in themes
    ]


# ---------------------------------------------------------------------------
# The copy registry, for the one fixed sentence.
# ---------------------------------------------------------------------------


def registered_sentences() -> dict[str, str]:
    """Every sentence every `app.copy` module registers, keyed `module:key`."""
    package = import_module(COPY_PACKAGE)
    found: dict[str, str] = {}
    for module in getattr(package, COPY_MODULES_FUNCTION)():
        mapping = getattr(module, COPY_MAPPING_NAME, None) or {}
        for key, entry in mapping.items():
            found[f"{module.__name__}:{key}"] = str(getattr(entry, "text", entry))
    return found


def registered_sentence_in(response: Any, what: str) -> str:
    """The one registered sentence a response served, by key, or a failure."""
    body = served_text(response)
    sentences = registered_sentences()
    matched = sorted(key for key, text in sentences.items() if text and text in body)
    if len(matched) != 1:
        pytest.fail(
            f"{what} served {body[:400]!r}, and {len(matched)} registered `app.copy` sentences appear "
            f"in it ({matched}). E7-04's work order, decision 2: a refused model answer returns 502 "
            "with one fixed sentence in `copy/` — the same sentence whatever triggered it."
        )
    return matched[0]


# ---------------------------------------------------------------------------
# Finding the two routes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DraftRoute:
    template: str
    section_parameter: str
    week_parameter: str


def draft_route(application: Any, task: str) -> DraftRoute:
    """The `POST` route for one task, found through the module that owns it."""
    segment = SEGMENT_OF[task]
    posts = [
        route
        for route in every_route(application)
        if "POST" in (getattr(route, "methods", None) or set())
        and getattr(getattr(route, "endpoint", None), "__module__", None) == INSTRUCTOR_API_MODULE
    ]
    found = [
        route
        for route in posts
        if str(getattr(route, "path", "")).rstrip("/").endswith(f"/{segment}")
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{INSTRUCTOR_API_MODULE}` mounts {len(found)} POST routes ending `/{segment}`; it mounts "
            f"{sorted(str(getattr(r, 'path', '?')) for r in posts)}.\n\n{DRAFT_IS_OWED}"
        )
    template = str(found[0].path)
    parameters = PATH_PARAMETER.findall(template)
    sections = [name for name in parameters if "section" in name.lower()]
    weeks = [name for name in parameters if "week" in name.lower()]
    if len(sections) != 1 or len(weeks) != 1:
        pytest.fail(
            f"The route {template!r} declares path parameters {parameters}; the work order puts one "
            f"section and one week in the path.\n\n{DRAFT_IS_OWED}"
        )
    return DraftRoute(template=template, section_parameter=sections[0], week_parameter=weeks[0])


def week_value_for(route: DraftRoute, door: ReportDoor, course_week: int) -> Any:
    """What the route's week parameter is filled with.

    The work order: `{week_id}`, "if it uses another key for the week, use that"
    — the key the report route uses. So a parameter spelled like the report's is
    filled the way the report's is filled (the course week), and one naming an id
    is filled with the week's key. Anything else is an ambiguity this names.
    """
    report = report_route(door.application)
    if route.week_parameter == report.week_parameter:
        return course_week
    if "id" in route.week_parameter.lower():
        return door.rows.week_id(course_week)
    pytest.fail(
        f"The draft route's week parameter is `{route.week_parameter}` and the report's is "
        f"`{report.week_parameter}`. The work order: `{{week_id}}`, or the report's own key."
    )


def url_for(route: DraftRoute, *, section_id: Any, week: Any) -> str:
    url = route.template
    for name, value in ((route.section_parameter, section_id), (route.week_parameter, week)):
        url = re.sub(r"\{" + re.escape(name) + r"(?::[^}/]+)?\}", str(value), url)
    return url


# ---------------------------------------------------------------------------
# The door.
# ---------------------------------------------------------------------------

MINTED: Any = object()


class DraftDoor:
    """The teaching instructor at the report door, with the draft and the check beside it."""

    def __init__(
        self, decisions: DecisionDoor, provider: ScriptedProvider, configured: Mapping[str, str]
    ) -> None:
        self.decisions = decisions
        self.door: ReportDoor = decisions.door
        self.provider = provider
        self.configured = configured
        self.planted: dict[str, Any] = {}

    @property
    def world(self) -> Any:
        return self.door.world

    @property
    def rows(self) -> Any:
        return self.door.rows

    # -- asking ---------------------------------------------------------------

    def _url(self, task: str, course_week: int, section_id: Any) -> str:
        route = draft_route(self.door.application, task)
        return url_for(
            route,
            section_id=self.rows.taught_section_id if section_id is None else section_id,
            week=week_value_for(route, self.door, course_week),
        )

    @staticmethod
    def _body(task: str, draft: str | None) -> dict[str, Any]:
        return {} if task == DRAFT else {CHECK_DRAFT_FIELD: draft}

    def ask(
        self,
        task: str,
        *,
        draft: str | None = None,
        course_week: int = FULL_WEEK,
        section_id: Any = None,
    ) -> Any:
        """One request, the session as a Bearer header (the SPA's carrier, ADR 0089)."""
        url = self._url(task, course_week, section_id)
        body = self._body(task, draft)
        with self.door.carrying_no_cookie():
            return self.door.tool.post(url, json=body, headers=self.door.credential())

    def draft(self, **kwargs: Any) -> Any:
        return self.ask(DRAFT, **kwargs)

    def check(self, draft: str, **kwargs: Any) -> Any:
        return self.ask(CHECK, draft=draft, **kwargs)

    def ask_as_a_browser(
        self, task: str, *, draft: str | None = None, csrf_token: Any = MINTED
    ) -> Any:
        """One request with the session in the cookie and no `Authorization` header.

        `tests/fixtures/instructor_decisions.py::DecisionDoor.decide_as_a_browser`'s
        invocation, copied rather than adapted (`docs/MISTAKES.md` entry 37).
        """
        secret = session_secret(self.configured)
        session_cookie, csrf_cookie = session_cookie_names()
        headers: dict[str, str] = {}
        cookies = {session_cookie: self.door.token}
        if csrf_token is not None:
            value = csrf_token_for(self.door.token, secret) if csrf_token is MINTED else csrf_token
            cookies[csrf_cookie] = value
            headers[CSRF_HEADER] = value
        url = self._url(task, FULL_WEEK, None)
        tool = self.door.tool
        tool.cookies.clear()
        try:
            for name, value in cookies.items():
                tool.cookies.set(name, value)
            return tool.post(url, json=self._body(task, draft), headers=headers)
        finally:
            tool.cookies.clear()

    def report(self, *, course_week: int = FULL_WEEK, section_id: Any = None) -> Any:
        """The report route's own answer for the same section-week, for byte comparison."""
        with self.door.carrying_no_cookie():
            return self.door.report(course_week=course_week, section_id=section_id)

    # -- planting -------------------------------------------------------------

    def plant(self, text: str, *, stream: str, verdict: str = CLEAR) -> Any:
        answer_id = self.decisions.plant_a_comment(
            course_week=FULL_WEEK, stream=stream, text=text, verdict=verdict
        )
        self.planted[text] = answer_id
        return answer_id

    def decide(self, text: str, action: str, reason: Any = None) -> None:
        """A decision through E6-03's own route, asserted to have landed."""
        answered = self.decisions.decide(self.planted[text], action, reason)
        assert answered.status_code == OK, (
            f"E6-03's decision route answered {answered.status_code} to {action!r} on {text!r}, so "
            f"the comment is not in the state this world says it is. Body {answered.text[:300]!r}."
        )

    def plant_summary(
        self,
        stream: str,
        *,
        text: str,
        themes: Sequence[tuple[str, int]],
        prompt_version: str,
        response_count: int,
    ) -> None:
        """One stored summary row for course week 1 of the taught section, committed."""
        self.world.seed(
            WEEKLY_SUMMARY_TABLE,
            {},
            **{
                SUMMARY_SECTION_COLUMN: self.rows.taught_section_id,
                SUMMARY_WEEK_COLUMN: self.rows.week_id(FULL_WEEK),
                SUMMARY_STREAM_COLUMN: stream,
                SUMMARY_TEXT_COLUMN: text,
                SUMMARY_RESPONSE_COUNT_COLUMN: response_count,
                SUMMARY_THEMES_COLUMN: stored_themes(themes),
                SUMMARY_PROMPT_VERSION_COLUMN: prompt_version,
                SUMMARY_MODEL_ID_COLUMN: A_SUMMARY_MODEL_ID,
            },
        )
        self.door.commit()

    def build_the_week(self, *, held_summary_version: str = SMALL_N_SUMMARY_VERSION) -> None:
        """Course week 1 with every comment and summary this ticket's criteria name.

        The instructor stream is the canonical world's five commenters plus four
        planted ones — shown. The course stream holds one commenter — held. Then:
        the published comment stays published; the excluded one is excluded through
        E6-03's route with a stated reason (it was never flagged, so a refusal of a
        draft lifting it cannot be about a flag); the flagged one is `harmful` and
        undecided; the kept one is `harmful` and kept, so students see it.
        """
        assert_the_planted_texts_are_what_this_file_says()
        self.plant(PUBLISHED_COMMENT, stream=INSTRUCTOR_STREAM)
        self.plant(EXCLUDED_COMMENT, stream=INSTRUCTOR_STREAM)
        self.plant(FLAGGED_COMMENT, stream=INSTRUCTOR_STREAM, verdict=HARMFUL)
        self.plant(KEPT_COMMENT, stream=INSTRUCTOR_STREAM, verdict=HARMFUL)
        self.plant(HELD_COMMENT, stream=COURSE_STREAM)
        self.decide(EXCLUDED_COMMENT, EXCLUDE, a_reason(40))
        self.decide(KEPT_COMMENT, KEEP)

        self.plant_summary(
            INSTRUCTOR_STREAM,
            text=SHOWN_SUMMARY_TEXT,
            themes=((SHOWN_THEME_A, SHOWN_THEME_A_COUNT), (SHOWN_THEME_B, SHOWN_THEME_B_COUNT)),
            prompt_version=ORDINARY_SUMMARY_VERSION,
            response_count=SHOWN_SUMMARY_RESPONSES,
        )
        if held_summary_version == SMALL_N_SUMMARY_VERSION:
            self.plant_summary(
                COURSE_STREAM,
                text=HELD_SUMMARY_TEXT,
                themes=((HELD_THEME, HELD_THEME_COUNT),),
                prompt_version=SMALL_N_SUMMARY_VERSION,
                response_count=HELD_SUMMARY_RESPONSES,
            )
        else:
            self.plant_summary(
                COURSE_STREAM,
                text=HELD_V1_SUMMARY_TEXT,
                themes=((HELD_V1_THEME, HELD_V1_THEME_COUNT),),
                prompt_version=held_summary_version,
                response_count=HELD_SUMMARY_RESPONSES,
            )

    # -- premises -------------------------------------------------------------

    def suppressed(self, body: Any, stream: str) -> Any:
        return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]][SMALL_N_MEMBER][SUPPRESSED_FIELD]

    def served_summary(self, body: Any, stream: str) -> Any:
        return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]].get(SUMMARY_FIELD)

    def assert_the_streams_are(self, *, instructor_held: bool, course_held: bool) -> Any:
        """Which stream is held, read off the report the instructor reads (decision 4)."""
        body, _ = self.door.payload(course_week=FULL_WEEK)
        for stream, held in ((INSTRUCTOR_STREAM, instructor_held), (COURSE_STREAM, course_held)):
            assert self.suppressed(body, stream) is held, (
                f"The report computes the {stream} stream of course week 1 as suppressed="
                f"{self.suppressed(body, stream)!r}; this world needs {held}. Work-order decision "
                "4: shown versus held comes from `stream_is_suppressed` as the report computes it."
            )
        return body


# A draft for the check to read, lifting nothing and counting nobody.
A_PLAIN_DRAFT = "Thank you for writing. I will post worked steps after each class."


def check_with(door: DraftDoor, themes: Sequence[tuple[str, int | None]]) -> Any:
    """Script the model to name `themes`, ask the check, and require that a call was made."""
    door.provider.script(check_answer(themes))
    before = len(door.provider.completions)
    answered = door.check(A_PLAIN_DRAFT)
    assert len(door.provider.completions) > before, (
        f"The check answered {answered.status_code} and made no model call, so its answer is not "
        f"a verdict on the scripted themes. Body {answered.text[:300]!r}."
    )
    return answered


def assert_unusable(answered: Any, what: str, why: str) -> None:
    """`answered` is decision 2's refusal of a model answer."""
    assert answered.status_code == UNUSABLE_ANSWER_STATUS, (
        f"The {what} answered {answered.status_code} to a model answer that {why}. E7-04's "
        f"work-order decision 2: a model answer refused by either structural check returns "
        f"{UNUSABLE_ANSWER_STATUS} with one fixed sentence. Body {answered.text[:400]!r}."
    )


def unaddressed_of(answered: Any) -> list[dict[str, Any]]:
    """The check's served themes, after requiring a 200 in decision 1's shape."""
    assert answered.status_code == 200, (
        f"The check answered {answered.status_code} to a model answer naming only stored themes "
        f"as stored. Body {answered.text[:400]!r}."
    )
    body = answered.json()
    assert isinstance(body, dict) and isinstance(body.get(UNADDRESSED_FIELD), list), (
        f"The check answered {body!r}; decision 1's answer is "
        '`{"unaddressed": [{"label": str, "comment_count": int | null}]}`.'
    )
    return list(body[UNADDRESSED_FIELD])


def text_of(answered: Any) -> str:
    """The draft route's served text, after requiring a 200 in decision 1's shape."""
    assert (
        answered.status_code == 200
    ), f"The draft answered {answered.status_code}. Body {answered.text[:400]!r}."
    body = answered.json()
    assert isinstance(body, dict) and isinstance(
        body.get(DRAFT_TEXT_FIELD), str
    ), f'The draft answered {body!r}; decision 1\'s answer is `{{"text": str}}`.'
    return str(body[DRAFT_TEXT_FIELD])


def what_each_task_sent(door: DraftDoor) -> dict[str, str]:
    """One draft and one check, each required to answer 200; the text each request carried.

    The model answers are the plainest usable ones — a draft lifting and counting
    nothing, and a check naming one shown theme as stored — so a 200 here depends
    on nothing but the route working, and a module asking what the *prompt*
    carried is not reddened by a refusal that is another module's subject.
    """
    sent: dict[str, str] = {}
    door.provider.script(draft_answer(A_PLAIN_DRAFT))
    before = len(door.provider.completions)
    text_of(door.draft())
    sent[DRAFT] = door.provider.text_since(before)

    door.provider.script(check_answer([(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)]))
    before = len(door.provider.completions)
    unaddressed_of(door.check(A_PLAIN_DRAFT))
    sent[CHECK] = door.provider.text_since(before)

    for task, text in sent.items():
        assert text.strip(), f"The {task} answered 200 and sent the provider nothing."
    return sent


@pytest.fixture
def draft_provider() -> Iterator[ScriptedProvider]:
    """The scripted provider on a loopback socket, torn down with the test."""
    provider = ScriptedProvider()
    provider.start()
    try:
        yield provider
    finally:
        provider.stop()


@pytest.fixture
def draft_door(
    report_door_as: Any, configured_env: dict[str, str], draft_provider: ScriptedProvider
) -> DraftDoor:
    """The teaching instructor at the report door, the tool's provider pointed at the stub.

    Builds nothing E7-04 owes: the world and the launch are E4-07's, the decision
    door E6-03's, and the routes are looked up inside each test body
    (`docs/MISTAKES.md` entry 44). The provider variable goes down through
    `report_door_as`, which sets it before the application is imported (entry 40).
    """
    door = report_door_as(
        INSTRUCTOR_ROLE, **{MOCK_AI_PROVIDER_BASE_URL_VARIABLE: draft_provider.base_url}
    )
    return DraftDoor(DecisionDoor(door, configured_env), draft_provider, configured_env)


def reporting_module() -> Any:
    try:
        return import_module(REPORTING_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        if missing.name not in {REPORTING_MODULE, "app.services", "app"}:
            raise
        pytest.fail(f"There is no `{REPORTING_MODULE}`.")


def response_gather() -> Any:
    """`reporting.response_gather`, or a failure quoting decision 3."""
    found = getattr(reporting_module(), RESPONSE_GATHER, None)
    if not callable(found):
        pytest.fail(
            f"`{REPORTING_MODULE}` exposes no `{RESPONSE_GATHER}`. E7-04's work order, decision 3: "
            "'`reporting.response_gather(session, *, section_id, week_id, for_on_behalf: bool) -> "
            "ResponseGather` — 03 reuses it with `for_on_behalf=True`'."
        )
    return found
