"""The comment-validity eval set — E2-12, and SPEC §11 open question 4's answer.

§11 question 4: "the classifier replaces the 25-character prototype heuristic;
its eval set and threshold need real seeded data before E2 exits". This module is
the seeded data. Ninety-eight synthetic student comments across §7.4's three
verdicts, each a typed case whose `expected` is a `ValidityVerdict` out of
`app.ai.contracts` rather than a string (SPEC §7.4, ADR 0030), and each pinned to
`validity.v2` — the prompt file ADR 0032 makes immutable, so the set states which
text it was written against.

**The pin moved from `validity.v1` on 2026-09-02, with the provider.** The
follow-up to PR #148 switches the model to `gpt-5.6-luna` and trims the prompt to
a new immutable version; ADR 0032 makes that an added file rather than an edit, so
`validity.v1.md` is still on disk and every classification recorded against it can
still be read. What cannot survive the move is the *measurement*: the floors in
`floors.py` were taken on one model under one prompt, and neither half of that
pair still holds. They go back to the placeholder, and this set is re-measured
before either number is written again.

The cases themselves do not move. They are comments and expected verdicts, and
what a student wrote is not a function of which prompt classifies it — that is the
whole reason the set is worth carrying across a prompt change rather than
regrowing.

**Every comment is invented.** None is a real submission, none carries a real
person's name, and none names a real course, section or instructor. They are
written to be plausible rather than to be real, because §4's confidentiality
model means a real comment could not live in a repository at all.

**The two families that carry the whole point of the set.** SPEC §3.3 keeps the
prototype's ≥25-character rule "solely as the fail-open floor", and the reason a
classifier is worth paying for is that the character count is wrong in both
directions:

  - `SHORT_SUBSTANTIVE` — under 25 characters and genuinely substantive. "Lab
    ran 40 min over." is twenty characters of specific, actionable feedback, and
    the heuristic denies the student credit for it.
  - `LONG_VACUOUS` — 25 characters or more and saying nothing. "good good good
    good good good" is twenty-nine characters, and the heuristic awards credit.

Neither family is decoration. A set made only of long-substantive and
short-insufficient comments is a set the character rule scores perfectly, and
measuring a classifier against it would tell you nothing you could not get for
free — `tests/unit/test_the_validity_eval_set_carries_the_cases_the_heuristic_gets_wrong.py`
is what refuses that set.

**And four boundary cases, in two pairs.** At 24 and at 25 characters the
heuristic answers differently while the truth does not move, so each length
appears once with a substantive comment and once with a vacuous one. Their
lengths are asserted rather than trusted: a case whose length drifted by one
character would still read correctly and would stop being the case it was written
to be.

**The positive class is `substantive`, and that is a decision.** §9.3 asks for one
precision and one recall figure per task and a three-way verdict has neither
until somebody says which class the pair is about. `substantive` is the class with
the consequence attached: §3.3 gates participation credit on it, so a false
positive is credit awarded for "it was okay" and a false negative is credit
withheld from a student who wrote something real. `insufficient` and `nonsense`
differ in what a student is *told*, not in what they are *given*, and the runner
reports their counts without gating on them.
"""

from __future__ import annotations

from app.ai.contracts import ValidityVerdict
from tests.evals.declarations import EvalCase

# ADR 0031: the recorded prompt version is the prompt file's path stem, and ADR
# 0032 makes that file immutable once a classification cites it. Pinning it here
# is what makes this set comparable across a prompt change rather than silently
# re-measured under a different text.
#
# **It is a value rather than an import from `app.ai.tasks` on purpose.** A pin
# that read the application's constant would follow every prompt bump silently and
# could never disagree with it — which is the one thing it is for. Written down
# here, a bump makes
# `test_the_pinned_prompt_version_is_the_one_the_application_loads` red until
# somebody says the set has been re-measured, and that red is the conversation.
PROMPT_VERSION = "validity.v2"

# ADR 0030: a verdict's *value* is the token stored, serialised and compared
# everywhere outside Python, and an eval file is named as one of those places. The
# members are looked up by that token rather than by their Python identifiers, so
# a member rename in `app.ai.contracts` does not silently repoint this set.
SUBSTANTIVE = ValidityVerdict("substantive")
INSUFFICIENT = ValidityVerdict("insufficient")
NONSENSE = ValidityVerdict("nonsense")

POSITIVE_VERDICT = SUBSTANTIVE

# SPEC §3.3: "The prototype's ≥25-character heuristic is a placeholder only." The
# number is the spec's, not this file's, and it is here because two families of
# case are defined relative to it.
HEURISTIC_MINIMUM_CHARACTERS = 25

# Why each case is in the set. The families are the argument for the set's shape,
# so they travel with the cases rather than living in a test that reads it.
LONG_SUBSTANTIVE = "long_substantive"
SHORT_SUBSTANTIVE = "short_substantive"
LONG_VACUOUS = "long_vacuous"
SHORT_INSUFFICIENT = "short_insufficient"
NONSENSE_FAMILY = "nonsense"
BOUNDARY = "boundary"


def heuristic_verdict(comment: str) -> ValidityVerdict:
    """What SPEC §3.3's fail-open character floor would answer about `comment`.

    Transcribed from the spec rather than imported from the application: this is
    the thing the classifier has to beat, and reading it out of the code under
    test would make the comparison a comparison of one implementation against
    itself (`docs/MISTAKES.md` entry 19).
    """
    if len(comment.strip()) >= HEURISTIC_MINIMUM_CHARACTERS:
        return SUBSTANTIVE
    return INSUFFICIENT


def _case(case_id: str, comment: str, expected: ValidityVerdict, family: str) -> EvalCase:
    """One case, with the prompt version filled in from the pin above."""
    return EvalCase(
        case_id=case_id,
        comment=comment,
        expected=expected,
        prompt_version=PROMPT_VERSION,
        family=family,
    )


# ---------------------------------------------------------------------------
# Substantive, and long enough that the character floor agrees. The bulk of the
# set, and the family that says what "substantive" looks like: a specific thing
# about this week, in this course, that somebody could act on.
# ---------------------------------------------------------------------------
_LONG_SUBSTANTIVE = (
    "The pacing in week three was too fast for the lab work.",
    "The reading list was helpful but the second article assumed stats I have not taken.",
    "Office hours at 8am clash with my shift, so I could not get help on the problem set.",
    "The lecture slides skip the derivation that the homework depends on.",
    "Group work went well this week; the rubric made the split of tasks obvious.",
    "I spent most of the week on the coding assignment and barely touched the reading.",
    "The recorded lectures helped, but the audio cut out around the twenty minute mark.",
    "Feedback on the last essay came back after the next one was already due.",
    "The worked examples in class are much easier than the ones on the quiz.",
    "Please post the practice problems earlier; Sunday evening is too late to use them.",
    "The lab manual and the lecture use different notation for the same variable.",
    "I liked that we started with a real dataset instead of a toy one.",
    "The discussion board is where most of the learning happened for me this week.",
    "Two of the required readings were behind a paywall the library link did not open.",
    "The midterm review session covered material we have not reached yet.",
    "Breaking the project into weekly checkpoints made the workload manageable.",
    "The instructor answered my email the same day and the explanation was clear.",
    "I still do not understand how to choose between the two methods from Tuesday.",
    "The pace felt right this week; the extra practice set was the difference.",
    "Captions on the videos were auto-generated and got the technical terms wrong.",
    "The assignment brief and the rubric ask for different section headings.",
    "Doing the simulation before the theory made the theory land better.",
    "There was no time in class to ask questions before the tutorial ended.",
    "The homework took about six hours, which is double what the syllabus says.",
    "Clearer examples of what a good answer looks like would help me a lot.",
    "The guest speaker was interesting but did not connect to the module outcomes.",
    "I appreciated the worked solution posted after the deadline, not before.",
    "Splitting the lecture into two shorter blocks made it much easier to follow.",
    "The quiz questions were worded ambiguously in items four and seven.",
    "The weekly summary email keeps me on track more than anything else here.",
    "The three hour block on Wednesday is too long without a break.",
    "Linking each lecture to the assessment criteria made revision much easier.",
    "The textbook chapter and the lecture disagree about the second definition.",
    "I could not open the dataset; the file needs software the lab does not have.",
    "The peer review step taught me more than writing the draft did.",
    "Announcements arrive after class rather than before it, which is too late.",
    "Fewer, longer exercises would suit this material better than many short ones.",
    "The seminar discussion stayed on one question and never reached the others.",
    "Marks were released without comments, so I do not know what to fix.",
    "The optional reading turned out to be required for the tutorial task.",
)

# ---------------------------------------------------------------------------
# Substantive and under the character floor. The heuristic calls every one of
# these insufficient, and every one of them is a student being denied credit for
# feedback an instructor could act on this afternoon.
# ---------------------------------------------------------------------------
_SHORT_SUBSTANTIVE = (
    "Slides load too slowly.",
    "Lab ran 40 min over.",
    "Quiz 3 had a typo.",
    "Audio cut out at 20m.",
    "Rubric fights the brief.",
    "Week 2 reading missing.",
    "No captions on video 5.",
    "Homework due date moved.",
    "Too few worked examples.",
    "Tutorial room locked.",
    "Two deadlines same day.",
    "Rubric arrived late.",
)

# ---------------------------------------------------------------------------
# Insufficient and over the character floor. The heuristic awards credit for
# every one of these, which is the other half of why §11 question 4 exists.
# ---------------------------------------------------------------------------
_LONG_VACUOUS = (
    "It was okay I guess, yeah.",
    "good good good good good good",
    "Fine. Fine. Fine. Fine. Fine.",
    "I have nothing to say here.",
    "no comment no comment okay",
    "It was a week. It was fine.",
    "Everything was fine thanks.",
    "n/a n/a n/a n/a n/a n/a n/a",
    "Nothing much to report really.",
    "same as last week, same as always",
    "ok ok ok ok ok ok ok ok ok",
    "I really do not know what to write here.",
)

# ---------------------------------------------------------------------------
# Insufficient and short. The family the heuristic gets right, and it is here so
# that the set can tell a classifier which agrees with the heuristic everywhere
# from one which is simply right — without it, a model that answered by counting
# characters would score identically on a set of only hard cases.
# ---------------------------------------------------------------------------
_SHORT_INSUFFICIENT = (
    "it was okay",
    "fine",
    "good",
    "no comment",
    "n/a",
    "nothing",
    "ok",
    "all good thanks",
    "same as usual",
    "not much to say",
    "it was fine",
    "no notes",
)

# ---------------------------------------------------------------------------
# Nonsense: §7.4's third verdict, and the one §3.3 says reduces the validity
# rate. Lengths deliberately straddle the character floor, because "nonsense" is
# the verdict the character rule cannot express at all — it has two answers and
# this is a third.
# ---------------------------------------------------------------------------
_NONSENSE = (
    "adfasdfa",
    "asdkjhaskdjhaskjdhaskjdhaskjdh",
    ";;;;;;;;",
    "qwertyuiop asdfghjkl zxcvbnm",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "1234567890 0987654321 111111",
    "lorem ipsum dolor sit amet consectetur",
    "jkjkjkjkjkjkjkjkjkjkjkjk",
    ".....",
    "xkcd fnord blorptastic zzz",
    "hjkl",
    "!!!!!!!!!!!!!!!!!!",
    "wpeoirupwoeiruwpeoiru",
    "asdf jkl; asdf jkl; asdf",
    "🙂🙂🙂🙂",
    "zzzzzzzz zzzzzzzz zzzzzzzz",
    "blah blah blah blah blah blah",
    "poiuytrewq lkjhgfdsa mnbvcxz",
)

# ---------------------------------------------------------------------------
# The boundary, in two pairs. At 24 characters the heuristic says insufficient
# and at 25 it says substantive; the truth does not move with the count, so each
# length appears once where the truth is substantive and once where it is not.
#
# **Both members of a pair are needed and neither is redundant.** A set holding
# only the 24-character substantive comment tests a classifier that ignores
# length; adding the 25-character insufficient one tests one that ignores it in
# the other direction, and a classifier that has quietly learned the character
# rule fails exactly one of the two.
#
# The lengths are asserted in
# `tests/unit/test_the_validity_eval_set_carries_the_cases_the_heuristic_gets_wrong.py`
# rather than trusted, because a case that drifted by one character still reads
# correctly and has stopped being the case it was written to be.
# ---------------------------------------------------------------------------
_BOUNDARY: tuple[tuple[str, ValidityVerdict], ...] = (
    ("Lab 3 rubric is missing.", SUBSTANTIVE),
    ("Week 5 slides not posted.", SUBSTANTIVE),
    ("it was ok it was ok okay", INSUFFICIENT),
    ("fine fine fine fine fine.", INSUFFICIENT),
)


def _numbered(
    prefix: str, comments: tuple[str, ...], expected: ValidityVerdict, family: str
) -> tuple[EvalCase, ...]:
    """Turn one family's comments into cases with stable, readable ids."""
    return tuple(
        _case(f"{prefix}-{index:03d}", comment, expected, family)
        for index, comment in enumerate(comments, start=1)
    )


CASES: tuple[EvalCase, ...] = (
    *_numbered("ls", _LONG_SUBSTANTIVE, SUBSTANTIVE, LONG_SUBSTANTIVE),
    *_numbered("ss", _SHORT_SUBSTANTIVE, SUBSTANTIVE, SHORT_SUBSTANTIVE),
    *_numbered("lv", _LONG_VACUOUS, INSUFFICIENT, LONG_VACUOUS),
    *_numbered("si", _SHORT_INSUFFICIENT, INSUFFICIENT, SHORT_INSUFFICIENT),
    *_numbered("ns", _NONSENSE, NONSENSE, NONSENSE_FAMILY),
    *tuple(
        _case(f"bd-{index:03d}", comment, expected, BOUNDARY)
        for index, (comment, expected) in enumerate(_BOUNDARY, start=1)
    ),
)
