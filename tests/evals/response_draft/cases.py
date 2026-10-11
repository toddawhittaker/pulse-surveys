"""The response-draft eval set, and what it means for a draft to hold — E7-04.

SPEC §5.3 asks two things of the draft: it is written "from the week's actual
themes and ratings", and it addresses "criticism concretely rather than
deflecting". Decision 12, residue A and the fix round's G1 add a third for a week
with a held stream: the draft states no number of anything except one naming a
course structure ("week 3", "chapter five").

**What a case is.** The week as the task is fed it — stored summaries with their
themes, each stream marked shown or held, and the rating distributions — never a
comment (done-when 1). `StoredSummary` and `StoredTheme` are this set's own
description of that input, not the gather's type: the gather's fields are the
implementer's, and a live runner adapts a case to them.

**Quoting is not graded here.** A case's input holds no comment, so there is
nothing a draft could quote; the refusal of a draft reusing a hidden comment's words
is asserted in `tests/integration/test_a_draft_quoting_a_hidden_comment_is_refused.py`.

**A criticism is addressed only by a sentence that names the problem and an
action** (fix-round G3): the case's problem-naming phrase ("too fast", "late",
"unanswered") *and* an action verb from a fixed list, in one sentence that also
commits ("I will"). A draft that says "thanks for the feedback about the pace" names
the topic and commits to nothing; one that says "I will consider your feedback"
commits to nothing concrete; one that mentions the problem in passing names no
action. Each is a breach the companion test requires to fail.

**An on-behalf draft commits differently** (E7-10 done-when 4, work-order
decision 2). Its author is a named leadership role (`author_role`, the value
`response_draft.v3`'s `{{AUTHOR_ROLE}}` slot takes), not the instructor, so it
answers a criticism with what the course will do or a step it has honestly taken
("I have asked …"), and a sentence promising an action in the first person
("I will slow down") is a breach: it is the instructor's promise, made by someone
who cannot keep it.

**E7-10 adds three families**: on behalf, a stream with no summary (null), and a
week with no themes. Each has a breach that fails its grader.

**The count is graded by the product's own function** (fix-round G2:
`app.services.reporting.states_a_count_of_people`), so there is one copy of the
rule. It is imported when a held case is graded, not at module scope, so this
package imports on any tree (`docs/MISTAKES.md` entry 44).

**No number is declared, and nothing here reaches a provider.** The floor and the
registry slot are carried to E7-09's hand-off for E10's floors pull request.

**Every summary and theme is invented.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The prompt file the set is written against (ADR 0031, ADR 0032). E7-10 replaces
# v1 and v2 with `response_draft.v3.md`, which takes the author's role (work-order
# decision 2). Written out, not imported, so a bump has to be met here on purpose
# (`docs/MISTAKES.md` entry 19); `tests/unit/test_the_draft_eval_cases_can_go_red.py`
# fails when it and `app.ai.tasks.RESPONSE_DRAFT_PROMPT_VERSION` differ.
PROMPT_VERSION = "response_draft.v3"

INSTRUCTOR_STREAM = "instructor"
COURSE_STREAM = "course"

CRITICISM_ADDRESSED = "criticism_addressed"
HELD_STREAM_STATES_NO_COUNT = "held_stream_states_no_count"
# E7-10 done-when 4's three new families.
ON_BEHALF_VOICE = "on_behalf_voice"
A_STREAM_WITH_NO_SUMMARY = "a_stream_with_no_summary"
A_WEEK_WITH_NO_THEMES = "a_week_with_no_themes"

# Work-order decision 2's `{{AUTHOR_ROLE}}` values, transcribed.
THE_INSTRUCTOR = "the course's instructor"
THE_LEAD = "the course's Lead Faculty"
THE_CHAIR = "the department chair"

# Fix-round G3's fixed list of action verbs, matched as whole words with an
# optional -s, -ed or -ing (so "posting", "returned" count).
ACTION_VERBS = (
    "post",
    "return",
    "answer",
    "slow",
    "move",
    "add",
    "change",
    "schedule",
    "grade",
    "reply",
    "record",
    "share",
    "split",
    "extend",
    "publish",
)

# A commitment, so a sentence that describes the problem with one of the verbs
# ("the proofs move too fast") is not read as an answer to it.
COMMITMENT = ("i will", "i'll", "we will", "we'll", "i am going to", "i'm going to")

# An on-behalf draft's commitment (work-order decision 2): the writer is not the
# instructor, so it may say what the course will do, or name a step it has taken
# honestly ("I have asked …"). The instructor's "I will" is not required of it.
ON_BEHALF_COMMITMENT = ("the course will", "i have asked", "i've asked")

# The instructor's own first-person promise. In an on-behalf draft, a sentence
# making one with an action verb ("I will slow down") is a promise in the
# instructor's voice that the writer cannot keep (done-when 4). **This set's
# reading, not the ticket's:** "we will" is left out, because a lead may speak for
# the course team; the ticket and decision 2 name only the first person.
INSTRUCTORS_PROMISE = ("i will", "i'll", "i am going to", "i'm going to")


@dataclass(frozen=True)
class StoredTheme:
    label: str
    comment_count: int | None


@dataclass(frozen=True)
class StoredSummary:
    """One stream's stored summary as the task is fed it. `held` is the report's own verdict.

    `text` is `None` for a stream with no summary to feed — none written, or one
    withheld by the gather's filter (done-when 4's null-summary family) — and then
    the stream carries no themes either.
    """

    stream: str
    held: bool
    text: str | None
    themes: tuple[StoredTheme, ...]


@dataclass(frozen=True)
class Criticism:
    """A theme the draft must answer, and the phrases that name its problem."""

    name: str
    problem: tuple[str, ...]


@dataclass(frozen=True)
class DraftCase:
    case_id: str
    family: str
    summaries: tuple[StoredSummary, ...]
    ratings: dict[str, tuple[int, int, int, int, int]]
    must_address: tuple[Criticism, ...]
    exemplar: str
    prompt_version: str = PROMPT_VERSION
    # The `{{AUTHOR_ROLE}}` the draft is written under (work-order decision 2).
    author_role: str = THE_INSTRUCTOR

    @property
    def has_a_held_stream(self) -> bool:
        return any(summary.held for summary in self.summaries)

    @property
    def on_behalf(self) -> bool:
        return self.author_role != THE_INSTRUCTOR


def sentences(text: str) -> list[str]:
    return [part.strip().lower() for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if part.strip()]


def acts(sentence: str) -> bool:
    """The sentence carries one of G3's action verbs, as a word of its own."""
    words = re.findall(r"[a-z]+", sentence)
    return any(
        re.fullmatch(rf"{verb}(?:s|es|ed|d|ing)?", word) for word in words for verb in ACTION_VERBS
    )


def addresses(criticism: Criticism, text: str, *, on_behalf: bool = False) -> bool:
    """One sentence names the problem, commits, and names an action.

    The commitment an on-behalf draft makes is `ON_BEHALF_COMMITMENT`'s, never
    the instructor's "I will" (work-order decision 2).
    """
    commitment = ON_BEHALF_COMMITMENT if on_behalf else COMMITMENT
    return any(
        any(phrase in sentence for phrase in criticism.problem)
        and any(phrase in sentence for phrase in commitment)
        and acts(sentence)
        for sentence in sentences(text)
    )


def promises_in_the_instructors_voice(text: str) -> bool:
    """A sentence promising, in the first person, one of G3's actions — the instructor's to keep."""
    return any(
        any(phrase in sentence for phrase in INSTRUCTORS_PROMISE) and acts(sentence)
        for sentence in sentences(text)
    )


def states_a_count(text: str) -> bool:
    """The product's held-week count rule — the one copy of it (fix-round G2)."""
    from app.services.reporting import states_a_count_of_people

    return bool(states_a_count_of_people(text))


def grade(case: DraftCase, text: str) -> list[str]:
    """Every way `text` fails `case`; empty when it holds."""
    failures = [
        f"does not address {criticism.name!r} concretely"
        for criticism in case.must_address
        if not addresses(criticism, text, on_behalf=case.on_behalf)
    ]
    if not text.strip():
        failures.append("is empty")
    if case.has_a_held_stream and states_a_count(text):
        failures.append("states a number beside a held stream")
    if case.on_behalf and promises_in_the_instructors_voice(text):
        failures.append(
            f"promises an action in the instructor's voice, written as {case.author_role}"
        )
    return failures


PACE = Criticism(
    name="the lectures move too fast",
    problem=("too fast", "too quickly", "rushed", "hard to follow"),
)
FEEDBACK = Criticism(
    name="feedback on the lab reports arrives too late to use",
    problem=("late", "after the next report"),
)
FORUM = Criticism(
    name="questions on the course forum go unanswered",
    problem=("unanswered", "too long", "no reply"),
)
WORKLOAD = Criticism(
    name="the problem sets take far longer than the hours advertised",
    problem=("too long", "longer than", "too much"),
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

# G4: a held stream carrying several themes, one of whose summaries states a count.
A_WEEK_WITH_A_HELD_STREAM_OF_SEVERAL_THEMES = (
    A_SHOWN_WEEK[0],
    StoredSummary(
        stream=COURSE_STREAM,
        held=True,
        text=(
            "Three students say forum questions go unanswered, and two say the problem sets take "
            "far longer than the hours the syllabus gives."
        ),
        themes=(
            StoredTheme("forum questions go unanswered", None),
            StoredTheme("problem sets take too long", None),
        ),
    ),
)

# E7-10 done-when 4: a stream with no summary to feed. The course stream is held
# and its summary is null — never written, or withheld by the gather's filter —
# so it carries no themes; the held stream still forbids a count.
A_WEEK_WITH_A_STREAM_WITH_NO_SUMMARY = (
    A_SHOWN_WEEK[0],
    StoredSummary(stream=COURSE_STREAM, held=True, text=None, themes=()),
)

# E7-10 done-when 4: a week with no themes. Both streams have a summary and
# neither names a theme; the course stream is held.
A_WEEK_WITHOUT_THEMES = (
    StoredSummary(
        stream=INSTRUCTOR_STREAM,
        held=False,
        text="Comments this week were short and raised no particular problem.",
        themes=(),
    ),
    StoredSummary(
        stream=COURSE_STREAM,
        held=True,
        text="Students in this stream wrote briefly and raised nothing specific.",
        themes=(),
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
            "said lab report feedback comes too late, so I will return marks within five days."
        ),
    ),
    # G4: the second criticism case, whose breach mentions a problem only in passing.
    DraftCase(
        case_id="rd-ca-002",
        family=CRITICISM_ADDRESSED,
        summaries=A_SHOWN_WEEK,
        ratings=RATINGS,
        must_address=(FEEDBACK,),
        exemplar=(
            "Thank you for writing. Lab report feedback has been arriving too late to use, so I "
            "will return every report within a week of the deadline."
        ),
    ),
    DraftCase(
        case_id="rd-hs-001",
        family=HELD_STREAM_STATES_NO_COUNT,
        summaries=A_WEEK_WITH_A_HELD_STREAM,
        ratings=RATINGS,
        must_address=(PACE, FORUM),
        exemplar=(
            "Thank you for writing. You said the Thursday proofs move too fast, so I will slow "
            "down and post the derivations. Questions on the course forum have gone unanswered "
            "too long, so I will answer the forum every weekday afternoon."
        ),
    ),
    # G4: the second held-stream case, the held stream carrying several themes.
    DraftCase(
        case_id="rd-hs-002",
        family=HELD_STREAM_STATES_NO_COUNT,
        summaries=A_WEEK_WITH_A_HELD_STREAM_OF_SEVERAL_THEMES,
        ratings=RATINGS,
        must_address=(FORUM, WORKLOAD),
        exemplar=(
            "Thank you for writing. Forum questions have gone unanswered, so I will answer the "
            "forum every weekday. The problem sets take longer than the syllabus says, so I will "
            "split each set and extend its deadline from week 4 on."
        ),
    ),
    # E7-10: the on-behalf family. A lead in a shown week, and a chair in a week
    # with a held stream; each commits as the course or as a step taken, never as
    # the instructor.
    DraftCase(
        case_id="rd-ob-001",
        family=ON_BEHALF_VOICE,
        summaries=A_SHOWN_WEEK,
        ratings=RATINGS,
        must_address=(PACE,),
        author_role=THE_LEAD,
        exemplar=(
            "Thank you for writing this week. The Thursday proofs move too fast, so I have asked "
            "your instructor to slow down and post every derivation after class."
        ),
    ),
    DraftCase(
        case_id="rd-ob-002",
        family=ON_BEHALF_VOICE,
        summaries=A_WEEK_WITH_A_HELD_STREAM,
        ratings=RATINGS,
        must_address=(FORUM,),
        author_role=THE_CHAIR,
        exemplar=(
            "Thank you for writing. Questions on the course forum have gone unanswered, so the "
            "course will answer the forum every weekday afternoon."
        ),
    ),
    # E7-10: a stream with no summary (held), beside a shown one.
    DraftCase(
        case_id="rd-ns-001",
        family=A_STREAM_WITH_NO_SUMMARY,
        summaries=A_WEEK_WITH_A_STREAM_WITH_NO_SUMMARY,
        ratings=RATINGS,
        must_address=(PACE,),
        exemplar=(
            "Thank you for writing. You said the Thursday proofs move too fast, so I will slow "
            "down and post the derivations after class."
        ),
    ),
    # E7-10: a week with no themes at all, its course stream held.
    DraftCase(
        case_id="rd-nt-001",
        family=A_WEEK_WITH_NO_THEMES,
        summaries=A_WEEK_WITHOUT_THEMES,
        ratings=RATINGS,
        must_address=(),
        exemplar=(
            "Thank you for completing the survey this week. I will keep posting the derivations "
            "after each class."
        ),
    ),
)


def _held_breach(clause: str) -> str:
    return (
        f"Thank you for writing. {clause} that forum questions go unanswered, so I will answer "
        "the forum daily, and I will slow down because the proofs move too fast."
    )


# Answers each case must fail, by case id: the deflections §5.3 rules out, the
# in-passing mention, and in the held weeks every count phrasing the fix-round
# review found plus "a few of you" (G2).
BREACHES: dict[str, tuple[str, ...]] = {
    "rd-ca-001": (
        "Thank you for your feedback about the pace and about lab report feedback. The pace is "
        "set by the syllabus, and feedback times are department policy.",
        "I will consider your feedback about the pace and the lab report marks.",
    ),
    "rd-ca-002": (
        "Thank you for writing, and yes, the lab feedback was late this week. I will see you on "
        "Tuesday.",
    ),
    "rd-hs-001": tuple(
        _held_breach(clause)
        for clause in (
            "Two students said",
            "2 of you said",
            "Two of your classmates said",
            "2 learners said",
            "The 7 who responded said",
            "Twenty students said",
            "Both students said",
            "Half the class said",
            "A few of you said",
        )
    ),
    "rd-hs-002": (
        "Thank you for writing. Three of you said forum questions go unanswered, so I will "
        "answer the forum every weekday. The problem sets take longer than the syllabus says, "
        "so I will split each set.",
    ),
    # E7-10. The lead's breach addresses the criticism as a lead does and then
    # promises, in the first person, what only the instructor can do: it fails on
    # the voice alone. The other three are held weeks, so each fails on its count
    # alone (`test_each_held_week_breach_fails_on_its_count_alone`).
    "rd-ob-001": (
        "Thank you for writing this week. The Thursday proofs move too fast, so I have asked "
        "your instructor to post every derivation, and I will slow down the Thursday lectures "
        "myself.",
    ),
    "rd-ob-002": (
        "Thank you for writing. Two of you said questions on the course forum have gone "
        "unanswered, so the course will answer the forum every weekday afternoon.",
    ),
    "rd-ns-001": (
        "Thank you for writing. Two of you said the Thursday proofs move too fast, so I will "
        "slow down and post the derivations after class.",
    ),
    "rd-nt-001": (
        "Thank you to the three of you who wrote this week. I will keep posting the derivations "
        "after each class.",
    ),
}
