"""The weekly-summary eval set, and what it means for a summary to hold — E4-05.

SPEC §5.1 states four things about an AI summary, and this module turns them into
cases that can be graded: summaries "preserve clearly critical themes (never
sanded off), state the response count they draw from, exclude flagged-held content
... and are generated **even in small-N weeks** — there, the summary is the only
comment signal". E4-05's scope asks for exactly four families out of that
sentence: criticism preserved through paraphrase, a small-N week's two comments
still summarized, an empty week producing the contract's empty shape, and a mixed
week where both praise and a specific complaint survive.

**Why the check is not a keyword match, and why that is the whole difficulty.**
The ticket's own trap list says it: "a summary eval that a keyword match satisfies
is the green that hides the defect". A summary that says "students commented on
the pace of the lectures and were largely positive" contains every word a
criticism about pacing contains, and has sanded the criticism off — which is the
failure §5.1 exists to forbid. So a signal here is a **pair**: what was talked
about, and what was said about it. It survives only when one span of the answer —
one sentence of the summary, or one theme label — names both. The sycophantic
variants in `breach.py` include outputs that name every topic and no judgement,
and `tests/unit/test_the_summary_eval_cases_can_go_red.py` requires those to
fail; without that pair this whole file would be the defect it is written against.

**Nothing here is a measurement, and no number is declared.** The checks answer
"does this answer hold §5.1's contract for this case" for an answer somebody
supplies. What a real model actually produces is the question SPEC §9.3 asks with
a provider and a floor, and E4-05 defers the floor deliberately: the registry's
summary slot is `DEFERRED`, the first real-provider run sets the numbers, and the
ADR records the staging. A number written here before that run would be a floor
nobody measured (`tests/evals/declarations.py` on the three states).

**It reaches no provider, and it is not in the registry.** `evaluate()` walks
`registry.TASKS` and nothing else, and the summary slot there carries no cases —
so the set below cannot be graded by a live run, which matters on this pull
request in particular: its diff touches `backend/app/ai/`, so CI's eval job runs
live on it and a set wired into that walk would spend a provider call per case.

**Every comment is invented.** None is a real submission, none carries a real
person's name, and none names a real course, section or instructor — §4's
confidentiality model means a real comment could not live in a repository at all.

**The application is imported nowhere in this module.** The answers the checks
read are built by `faithful_answers`, which is handed the contracts module by its
caller; the annotations name `WeeklySummaryOutput` under `TYPE_CHECKING`, which is
where SPEC §9.3's "a contract change breaks its evals at type-check time" bites
for this file. Importing it at module scope instead would make the eval package
unimportable on a tree where the contract had not landed, and turn every red in
the companion test module into a collection error (`docs/MISTAKES.md` entry 44).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotations only, checked by mypy
    from app.ai.contracts import WeeklySummaryOutput

# ADR 0031 makes the recorded prompt version the prompt file's path stem, and ADR
# 0032 makes that file immutable once anything cites it.
#
# **It is written down rather than imported from `app.ai.tasks`, on purpose**, and
# `tests/evals/validity/cases.py` gives the reason for its own pin: a value read
# out of the application follows every prompt bump silently and can never disagree
# with it, which is the one thing it is for. Written here, a bump makes
# `test_the_summary_sets_pinned_prompt_version_is_the_one_the_application_renders`
# red until somebody says the set has been re-measured (`docs/MISTAKES.md` entry
# 19).
PROMPT_VERSION = "summary.v1"

# SPEC §5.1's two streams, as the tokens this set states them in. The contract's
# enum is matched against these by name or by value rather than the other way
# round, so a member renamed in Python does not silently repoint a case.
INSTRUCTOR_STREAM = "instructor"
COURSE_STREAM = "course"

# Why each case is in the set. E4-05's scope names all four, and the families
# travel with the cases rather than living in a test that reads them.
CRITICISM_PRESERVED = "criticism_preserved"
SMALL_N = "small_n"
EMPTY_WEEK = "empty_week"
MIXED_WEEK = "mixed_week"

# What a signal is: criticism that may never be sanded off, or praise that must
# not be dropped when a complaint is reported.
CRITICISM = "criticism"
PRAISE = "praise"


@dataclass(frozen=True)
class Signal:
    """One thing a week's comments say, and what it takes for it to have survived.

    `topic` is what was talked about and `judgement` is what was said about it,
    and both are lists of the paraphrases a faithful summary might reasonably
    choose — the point of the set is that the model rewrites in its own words, so
    a case that demanded one wording would measure obedience rather than fidelity.

    **They are two fields rather than one list on purpose.** A single list is a
    keyword match, and a fluent summary that names every topic while reporting the
    week as a success passes one. Requiring the pair inside a single span — one
    sentence, or one theme label — is what makes "the criticism was preserved"
    different from "the subject was mentioned".

    `carried_by` is how many of the case's comments say it. It is what a theme's
    `comment_count` can be read against; it is deliberately not asserted as an
    equality, because how a model groups five comments into themes is not
    something this ticket settles, and a case that demanded a particular grouping
    would be encoding a decision the ticket leaves open.
    """

    kind: str
    name: str
    topic: tuple[str, ...]
    judgement: tuple[str, ...]
    carried_by: int


@dataclass(frozen=True)
class SummaryCase:
    """One week of one stream's comments, and what §5.1 requires of its summary."""

    case_id: str
    stream: str
    comments: tuple[str, ...]
    signals: tuple[Signal, ...]
    family: str
    prompt_version: str = PROMPT_VERSION


# ---------------------------------------------------------------------------
# The cases.
# ---------------------------------------------------------------------------

CRITICISM_PRESERVED_CASE = SummaryCase(
    case_id="sm-cp-001",
    stream=INSTRUCTOR_STREAM,
    comments=(
        "The proofs on Thursday went by too quickly for me to write anything down.",
        "I could not follow the second half of the class because two steps were skipped.",
        "Office hours were genuinely helpful once I got there.",
        "Please slow down on the derivations, or post them afterwards.",
        "The worked example at the start of the week was clear.",
        "Three of us stopped taking notes on Thursday because of the speed.",
    ),
    signals=(
        Signal(
            kind=CRITICISM,
            name="the lectures move too fast to follow",
            topic=(
                "lecture",
                "lectures",
                "class",
                "proof",
                "proofs",
                "derivation",
                "derivations",
                "pace",
                "pacing",
                "speed",
                "notes",
            ),
            judgement=(
                "too fast",
                "too quickly",
                "rushed",
                "hard to follow",
                "difficult to follow",
                "could not follow",
                "cannot follow",
                "skipped",
                "slow down",
                "stopped taking notes",
                "no time",
            ),
            carried_by=4,
        ),
    ),
    family=CRITICISM_PRESERVED,
)

SMALL_N_CASE = SummaryCase(
    case_id="sm-sn-001",
    stream=COURSE_STREAM,
    comments=(
        "The reading list points at a chapter the library does not hold.",
        "The lab handout and the slides use different notation for the same quantity.",
    ),
    signals=(
        Signal(
            kind=CRITICISM,
            name="the assigned reading cannot be obtained",
            topic=("reading", "readings", "reading list", "chapter", "library", "text"),
            judgement=(
                "does not hold",
                "does not have",
                "not available",
                "unavailable",
                "cannot be obtained",
                "cannot get",
                "cannot access",
                "no copy",
                "missing",
            ),
            carried_by=1,
        ),
        Signal(
            kind=CRITICISM,
            name="the notation disagrees between the handout and the slides",
            topic=("notation", "handout", "slides", "symbols"),
            judgement=(
                "different notation",
                "do not match",
                "does not match",
                "inconsistent",
                "conflicting",
                "disagree",
                "two different",
            ),
            carried_by=1,
        ),
    ),
    family=SMALL_N,
)

EMPTY_WEEK_CASE = SummaryCase(
    case_id="sm-ew-001",
    stream=INSTRUCTOR_STREAM,
    comments=(),
    signals=(),
    family=EMPTY_WEEK,
)

MIXED_WEEK_CASE = SummaryCase(
    case_id="sm-mx-001",
    stream=COURSE_STREAM,
    comments=(
        "The weekly quizzes are a good way to check I understood the reading.",
        "The group project brief was posted after the groups had already been formed.",
        "Breaking the videos into short pieces works well for me.",
        "The project brief still has no marking criteria in it.",
        "The videos and the quizzes together are the best part of the course.",
    ),
    signals=(
        Signal(
            kind=PRAISE,
            name="the short videos and the weekly quizzes work",
            topic=("video", "videos", "quiz", "quizzes"),
            judgement=(
                "work well",
                "works well",
                "helpful",
                "useful",
                "valued",
                "appreciated",
                "praised",
                "liked",
                "best part",
                "good way",
            ),
            carried_by=3,
        ),
        Signal(
            kind=CRITICISM,
            name="the project brief arrived late and without marking criteria",
            topic=("project", "brief", "criteria", "marking criteria", "rubric"),
            judgement=(
                "late",
                "too late",
                "after",
                "missing",
                "no marking criteria",
                "without",
                "incomplete",
                "not yet",
            ),
            carried_by=2,
        ),
    ),
    family=MIXED_WEEK,
)

CASES: tuple[SummaryCase, ...] = (
    CRITICISM_PRESERVED_CASE,
    SMALL_N_CASE,
    EMPTY_WEEK_CASE,
    MIXED_WEEK_CASE,
)


# ---------------------------------------------------------------------------
# Reading one answer.
# ---------------------------------------------------------------------------


def mentions(text: str, terms: tuple[str, ...]) -> str | None:
    """The first of `terms` that `text` uses as a word, or `None`.

    Word-bounded rather than a bare substring, because "class" inside "classroom"
    and "late" inside "related" are the way a matcher goes blind in the permissive
    direction — and a permissive matcher here reports a criticism as preserved
    when the summary merely rhymed with it.
    """
    lowered = text.lower()
    for term in terms:
        if re.search(rf"(?<![a-z]){re.escape(term.lower())}(?![a-z])", lowered):
            return term
    return None


def spans(output: WeeklySummaryOutput) -> tuple[str, ...]:
    """The pieces of an answer a signal may survive inside: sentences, and theme labels.

    A sentence rather than the whole summary, because "the pace was criticised"
    and "the pace was praised" both put every topic word in the same paragraph as
    every judgement word once the paragraph is long enough. A theme label counts
    as a span of its own — §5.1's themes are short and are exactly where a
    criticism is meant to be named.
    """
    text = getattr(output, "summary", "") or ""
    sentences = [piece.strip() for piece in re.split(r"(?<=[.!?])\s+|\n+", text) if piece.strip()]
    labels = [str(getattr(theme, "label", "")) for theme in getattr(output, "themes", ())]
    return tuple(sentences) + tuple(label for label in labels if label.strip())


def stream_token(output: WeeklySummaryOutput) -> str:
    """The stream an answer claims, as the token it is spelled with outside Python."""
    stream = getattr(output, "stream", None)
    value = getattr(stream, "value", stream)
    return str(value).lower()


def surviving_signal(case: SummaryCase, signal: Signal, output: WeeklySummaryOutput) -> str | None:
    """The span that carries `signal`, or `None` if nothing in the answer does."""
    del case
    for span in spans(output):
        topic = mentions(span, signal.topic)
        judgement = mentions(span, signal.judgement)
        if topic is not None and judgement is not None:
            return span
    return None


# ---------------------------------------------------------------------------
# The checks. Each answers with the defects it found, in plain English.
# ---------------------------------------------------------------------------


def sanded_signals(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """§5.1's first contract: clearly critical themes are preserved, never sanded off."""
    found: list[str] = []
    for signal in case.signals:
        if surviving_signal(case, signal, output) is None:
            found.append(
                f"{signal.name!r} ({signal.kind}, carried by {signal.carried_by} of "
                f"{len(case.comments)} comments) is in no sentence of the summary and in no "
                "theme label: nothing in the answer names both what the comments were about "
                f"({list(signal.topic)}) and what they said about it ({list(signal.judgement)})"
            )
    return tuple(found)


def invented_themes(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """E4-05 criterion 4: an empty week produces the empty shape, never an invented theme."""
    themes = tuple(getattr(output, "themes", ()))
    if case.comments or not themes:
        return ()
    labels = [str(getattr(theme, "label", theme)) for theme in themes]
    return (
        f"the week has no comments and the answer carries {len(themes)} theme(s) {labels}. "
        "A theme over nothing is invented, and E4-05's fourth criterion is that a zero-comment "
        "week answers the contract's stated empty shape.",
    )


def overclaimed_themes(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """A theme may not claim more comments than the week holds.

    The one arithmetic property the ticket settles without settling how themes are
    grouped: "carry themes with per-theme comment counts now". How many themes a
    week produces, and which comment lands in which, is left open on purpose — so
    this checks the bound rather than a grouping, and a case that demanded a
    particular split would be making that decision for the implementer.
    """
    found: list[str] = []
    for theme in getattr(output, "themes", ()):
        count = getattr(theme, "comment_count", 0)
        if isinstance(count, int) and count > len(case.comments):
            found.append(
                f"the theme {str(getattr(theme, 'label', theme))!r} claims {count} comments and "
                f"the week holds {len(case.comments)}"
            )
    return tuple(found)


def wrong_stream(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """The answer is about the stream that was asked for.

    §5.1 groups every comment under "About the instructor" / "About the course",
    and E4-05 makes the task one call per stream so that a cross-stream bleed — a
    course complaint summarized into the instructor stream — is prevented
    structurally rather than noticed later.
    """
    answered = stream_token(output)
    if answered == case.stream:
        return ()
    return (f"the answer is about the {answered!r} stream and the case asked for {case.stream!r}",)


def absent_summary(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """There is a summary at all — which is the whole of what a small-N week is owed.

    §5.1: summaries "are generated **even in small-N weeks** — there, the summary
    is the only comment signal". A week of two comments that came back with themes
    and no prose would satisfy every other check in this module.
    """
    del case
    text = getattr(output, "summary", "") or ""
    if text.strip():
        return ()
    return ("the answer carries no summary text at all",)


CHECKS = (sanded_signals, invented_themes, overclaimed_themes, wrong_stream, absent_summary)


def defects(case: SummaryCase, output: WeeklySummaryOutput) -> tuple[str, ...]:
    """Everything about `output` that fails §5.1's contract for `case`.

    An empty tuple is the case holding. The checks are composed rather than
    reduced to a boolean so that a red says which contract was broken, and so that
    a demonstration can require an answer to fail *for the reason it was built to
    fail for* rather than for any reason at all.
    """
    return tuple(defect for check in CHECKS for defect in check(case, output))


# ---------------------------------------------------------------------------
# Answers that hold the contract, as the control every check must pass.
# ---------------------------------------------------------------------------


def stream_member(contracts: Any, token: str) -> Any:
    """The `CommentStream` member spelling `token`, by name or by value."""
    enum_class = getattr(contracts, "CommentStream", None)
    if enum_class is None:
        raise LookupError(
            "`app.ai.contracts` exposes no `CommentStream`, so an eval answer cannot say which "
            "stream it is about. SPEC §5.1 groups every comment under 'About the instructor' / "
            "'About the course'."
        )
    for member in enum_class:
        spellings = {member.name.lower().replace("_", "")}
        if isinstance(member.value, str):
            spellings.add(member.value.lower().replace("_", ""))
        if token in spellings:
            return member
    raise LookupError(
        f"`CommentStream` carries no member spelling {token!r}; it offers "
        f"{[member.name for member in enum_class]}."
    )


def contract_class(contracts: Any, name: str) -> Any:
    """One contract class out of the module the caller handed over, or a named refusal."""
    found = getattr(contracts, name, None)
    if found is None:
        raise LookupError(
            f"`app.ai.contracts` exposes no `{name}`. E4-05's scope: 'the typed contract in "
            "`contracts.py`: the summary text, the themes it found, and room for the held-note "
            "(type only) that E6's moderation will make real'."
        )
    return found


def build_answer(
    contracts: Any, case: SummaryCase, summary: str, themes: tuple[tuple[str, int], ...]
) -> Any:
    """One answer, built out of the contract classes the caller handed over.

    Public because `breach.py` builds its answers the same way: two builders would
    be two shapes, and a variant that failed because it was constructed differently
    would demonstrate the constructor rather than the check.
    """
    theme_model = contract_class(contracts, "CommentTheme")
    output_model = contract_class(contracts, "WeeklySummaryOutput")
    return output_model(
        stream=stream_member(contracts, case.stream),
        summary=summary,
        themes=tuple(theme_model(label=label, comment_count=count) for label, count in themes),
        prompt_version=case.prompt_version,
        model_id="e4-05-eval-control",
    )


def faithful_answers(contracts: Any) -> dict[str, Any]:
    """One answer per case that holds §5.1's contract, as the checks' control.

    **These are the control, not a measurement** (`docs/MISTAKES.md` entry 30). A
    check that only ever ran against answers built to fail would be satisfied by a
    checker that failed everything, and a demonstration built on one would prove
    nothing at all. What a real model produces is not knowable from this file, and
    this ticket does not claim it: the floor waits for the first live run.

    They are written as a model would write them — paraphrased, not quoting the
    comments — because a control that copied the comment text back would pass a
    checker that compared strings, and the whole subject here is a check that
    survives paraphrase.
    """
    return {
        CRITICISM_PRESERVED_CASE.case_id: build_answer(
            contracts,
            CRITICISM_PRESERVED_CASE,
            "Most of the week's comments are about pace: several students say the Thursday "
            "class moved too quickly to follow and ask for the derivations to be slowed down "
            "or posted. One comment says office hours helped, and one found the opening "
            "worked example clear.",
            (("Thursday class moved too quickly", 4), ("office hours helped", 1)),
        ),
        SMALL_N_CASE.case_id: build_answer(
            contracts,
            SMALL_N_CASE,
            "Two students commented. One says the library does not hold the chapter the "
            "reading list points at. The other says the handout and the slides use different "
            "notation for the same quantity.",
            (("assigned chapter unavailable", 1), ("handout and slides use different notation", 1)),
        ),
        EMPTY_WEEK_CASE.case_id: build_answer(
            contracts,
            EMPTY_WEEK_CASE,
            "No comments were submitted this week.",
            (),
        ),
        MIXED_WEEK_CASE.case_id: build_answer(
            contracts,
            MIXED_WEEK_CASE,
            "Students say the short videos and the weekly quizzes work well together and call "
            "them the best part of the course. Two comments are about the group project "
            "brief: it arrived after the groups were formed and still has no marking criteria.",
            (
                ("short videos and quizzes work well", 3),
                ("project brief late and missing marking criteria", 2),
            ),
        ),
    }
