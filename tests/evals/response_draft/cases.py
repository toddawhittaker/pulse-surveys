"""The response-draft eval set, and what it means for a draft to hold — E7-04.

SPEC §5.3 asks two things of the draft: it is written "from the week's actual
themes and ratings", and it addresses "criticism concretely rather than
deflecting". Decision 12 and the work order's residue A add a third for a week
with a held stream: the draft states no number of comments or students, because
that number is the participation trace §5.2 rules out.

**What a case is.** The week as the task is fed it — stored summaries with their
themes, each stream marked shown or held, and the rating distributions — never a
comment (done-when 1). `StoredSummary` and `StoredTheme` are this set's own
description of that input, not the gather's type: the gather's fields are the
implementer's, and a live runner adapts a case to them.

**Why a criticism is a pair, as in `tests/evals/summary/cases.py`.** A draft that
says "thanks for the feedback about the pace" names the topic and commits to
nothing, which is the deflection §5.3 rules out. So a criticism survives only when
one sentence names its topic *and* a concrete commitment. The deflecting exemplars
in `BREACHES` name every topic and commit to nothing, and the companion test
requires them to fail.

**No number is declared, and nothing here reaches a provider.** Whether a real
model writes good drafts is SPEC §9.3's question, with a floor set after the first
live run; this file only says, for an answer somebody supplies, whether it holds.

**Every summary and theme is invented**, and the application is imported nowhere
in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The prompt file the set is written against (ADR 0031, ADR 0032): the ticket's
# `backend/app/ai/prompts/response_draft.v1.md`. Written out, not imported, so a
# prompt bump has to be met here on purpose (`docs/MISTAKES.md` entry 19).
PROMPT_VERSION = "response_draft.v1"

INSTRUCTOR_STREAM = "instructor"
COURSE_STREAM = "course"

CRITICISM_ADDRESSED = "criticism_addressed"
HELD_STREAM_STATES_NO_COUNT = "held_stream_states_no_count"

# What a concrete commitment sounds like. Generous on purpose: the set measures
# whether a draft commits to something about the topic, not which words it uses.
COMMITMENT = (
    "i will",
    "i'll",
    "we will",
    "we'll",
    "i am going to",
    "i'm going to",
    "from next week",
    "starting next",
    "going forward",
    "i have changed",
    "i've changed",
    "i will now",
    "i plan to",
)

# Residue A's rule, written here independently of the product's guard so the eval
# does not agree with the code about what the code does: a number — digits or a
# number word — next to comment, student, response, classmate, or "of you".
NUMBER_WORD = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"a few|several|a couple of|a handful of|half|most|all)"
)
PEOPLE = r"(?:comments?|students?|responses?|classmates?|respondents?|people)"
COUNTING = re.compile(rf"\b{NUMBER_WORD}\s+(?:of\s+you|(?:\w+\s+)?{PEOPLE})\b", re.IGNORECASE)


@dataclass(frozen=True)
class StoredTheme:
    label: str
    comment_count: int | None


@dataclass(frozen=True)
class StoredSummary:
    """One stream's stored summary as the task is fed it. `held` is the report's own verdict."""

    stream: str
    held: bool
    text: str
    themes: tuple[StoredTheme, ...]


@dataclass(frozen=True)
class Criticism:
    """A theme the draft must answer: what it is about, in the words a draft might use."""

    name: str
    topic: tuple[str, ...]


@dataclass(frozen=True)
class DraftCase:
    case_id: str
    family: str
    summaries: tuple[StoredSummary, ...]
    ratings: dict[str, tuple[int, int, int, int, int]]
    must_address: tuple[Criticism, ...]
    exemplar: str
    prompt_version: str = PROMPT_VERSION

    @property
    def has_a_held_stream(self) -> bool:
        return any(summary.held for summary in self.summaries)


def sentences(text: str) -> list[str]:
    return [part.strip().lower() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def addresses(criticism: Criticism, text: str) -> bool:
    """One sentence names the criticism's topic and a commitment."""
    return any(
        any(word in sentence for word in criticism.topic)
        and any(phrase in sentence for phrase in COMMITMENT)
        for sentence in sentences(text)
    )


def states_a_count(text: str) -> list[str]:
    return [match.group(0) for match in COUNTING.finditer(text)]


def grade(case: DraftCase, text: str) -> list[str]:
    """Every way `text` fails `case`; empty when it holds."""
    failures = [
        f"does not address {criticism.name!r} concretely"
        for criticism in case.must_address
        if not addresses(criticism, text)
    ]
    if not text.strip():
        failures.append("is empty")
    if case.has_a_held_stream:
        failures += [
            f"states a count beside a held stream: {found!r}" for found in states_a_count(text)
        ]
    return failures


PACE = Criticism(
    name="the lectures move too fast",
    topic=("pace", "pacing", "speed", "too fast", "slow down", "slower", "derivation", "proof"),
)
FEEDBACK = Criticism(
    name="feedback on the lab reports arrives too late to use",
    topic=("feedback", "lab report", "marking", "marks", "turnaround"),
)
FORUM = Criticism(
    name="questions on the course forum go unanswered",
    topic=("forum", "discussion board", "questions", "unanswered"),
)

A_SHOWN_WEEK = (
    StoredSummary(
        stream=INSTRUCTOR_STREAM,
        held=False,
        text=(
            "Most comments say the Thursday proofs move too fast to follow; several ask for the "
            "derivations to be posted. Office hours are praised."
        ),
        themes=(StoredTheme("lectures move too fast", 6), StoredTheme("office hours help", 3)),
    ),
    StoredSummary(
        stream=COURSE_STREAM,
        held=False,
        text="Students say lab report feedback arrives after the next report is due.",
        themes=(StoredTheme("lab feedback arrives too late", 5),),
    ),
)

A_WEEK_WITH_A_HELD_STREAM = (
    A_SHOWN_WEEK[0],
    StoredSummary(
        stream=COURSE_STREAM,
        held=True,
        text="Two students say questions on the course forum go unanswered for days.",
        themes=(StoredTheme("forum questions go unanswered", None),),
    ),
)

RATINGS = {INSTRUCTOR_STREAM: (1, 2, 5, 8, 4), COURSE_STREAM: (2, 3, 6, 6, 3)}

CASES: tuple[DraftCase, ...] = (
    DraftCase(
        case_id="rd-ca-001",
        family=CRITICISM_ADDRESSED,
        summaries=A_SHOWN_WEEK,
        ratings=RATINGS,
        must_address=(PACE, FEEDBACK),
        exemplar=(
            "Thank you for this week's feedback. You told me the Thursday proofs move too fast, "
            "so from next week I will slow down and post every derivation after class. You also "
            "said lab report feedback comes too late; I will return marks within five days."
        ),
    ),
    DraftCase(
        case_id="rd-hs-001",
        family=HELD_STREAM_STATES_NO_COUNT,
        summaries=A_WEEK_WITH_A_HELD_STREAM,
        ratings=RATINGS,
        must_address=(PACE, FORUM),
        exemplar=(
            "Thank you for writing. The pace of the Thursday proofs came up, so I will slow down "
            "and post the derivations. Questions on the course forum have waited too long; I will "
            "answer the forum every weekday afternoon."
        ),
    ),
)

# Answers each case must fail, by case id: the deflection §5.3 rules out, and for
# the held week a draft repeating the summary prose's count.
BREACHES: dict[str, tuple[str, ...]] = {
    "rd-ca-001": (
        "Thank you for your feedback about the pace and about lab report feedback. The pace is "
        "set by the syllabus, and feedback times are department policy.",
    ),
    "rd-hs-001": (
        "Thank you for writing. Two students said forum questions go unanswered, so I will "
        "answer the forum daily, and I will slow down the pace of the proofs.",
        "Thank you for writing. 2 of you said forum questions go unanswered, so I will answer "
        "the forum daily, and I will slow down the pace of the proofs.",
    ),
}
