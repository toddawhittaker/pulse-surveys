"""A small-N week's summary names themes and quotes nobody — the owner's ruling of 2026-09-09.

SPEC §4 hides raw comments below the n-threshold and §5.1 generates the summary
anyway, because "there, the summary is the only comment signal". The boundary
review found the hole between those two sentences: a summary is prose the
instructor reads, and prose that reuses a commenter's own words hands back the
comment the threshold was withholding — in a quiet week, to a reader who can put
it beside the gradebook's per-week completion ledger (ADR 0125) and narrow the
author to whoever completed that week's comment item.

**The ruling is option B, dated 2026-09-09:** below the threshold a week's summary
names themes only and may not reuse the commenters' own word strings. Above the
threshold the contract is unchanged — the raw comments are on the page anyway, so
there is nothing for a summary to disclose.

**This module is about the guard, not about the prompt.** Work-order decision D9
settles both halves and says why there are two: a prompt instruction is soft — the
model may ignore it, and a provider swap changes what "ignore" means — so the
ruling is also enforced structurally, at store time. Generating a small-N week's
summary, if the text carries any twenty-character substring (case and whitespace
normalized) of a comment it was fed, the write is refused and rolled back for that
section-week. The week retries on the next run and the absence in between is
honest. `test_the_small_n_summary_prompt_asks_for_themes_only.py` is the prompt
half.

**Twenty characters, driven at three points and not two.** D9 states the bound and
says it is tunable in the ADR that records the guard. Three overlaps are planted in
the same world, one character apart: **nineteen stores, twenty is refused,
twenty-one is refused** — so the bound sits *at* twenty rather than above it, and
an implementation comparing `> 20` or `>= 21` reds where one comparing `>= 20`
passes.

**The middle point was missing and the re-verification battery is what found it.**
The first version of this module planted nineteen and twenty-one, which straddles
the bound without standing on it: raising the guard's bound to twenty-one — the
permissive direction, which lets a twenty-character lift through — left the whole
suite green. A boundary tested at 19 and 21 is a boundary tested at neither, and
`test_a_run_of_exactly_the_bound_is_refused` is the repair.

**Both legs of the guard, not just the prose.** A summary is a paragraph *and* its
theme labels, stored in one row (E4-02), and a label is short, sits beside the
prose on the report, and is the likelier place for a phrase a model lifted. The
battery found that leg unasserted too — deleting the label check survived
everything, because the mock's themes-only branch labels by ordinal and no drive
could ever meet a fragment in a label —
so `test_a_clean_summary_with_a_quoting_theme_label_is_refused` drives it.

**Why the fed comments are written here rather than taken from
`comment_text`.** The overlaps have to be exact, and an overlap is a fact about two
strings *including the characters either side of it*: a fragment that begins after
a space matches one character further left than it looks, because the space is in
both. Every literal below is placed so that its longest common run with the fed
comment is the length this module claims — at the start of the summary, so nothing
extends it leftward, and ending mid-word or before a differing character, so
nothing extends it rightward. The arithmetic is written out beside each one.

**Marked `invariant`.** This is §4.1 item 3 enforced one layer out from the payload:
the words are withheld from the comment list and the summary is the surface that
can hand them back. A skipped guard here is the threshold silently not applying to
the one surface §5.1 guarantees a small-N week will have.

**Which failure a red is.** Everything is reached through `summary_job_contract`,
whose lookups are `pytest.fail` calls naming the deliverable, and the guard itself
is observed as rows in `weekly_summary` — so a red is an assertion about what was
stored, never an error in setup (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    A_COHORT,
    ANOTHER_COHORT,
    INSTRUCTOR_MARK,
    STREAM_MARKS,
    SUMMARY_STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    StreamAwareGateway,
    SummaryWorld,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The guard's bound, from work-order decision D9. Written out rather than imported
# from whatever constant the implementer names it in: this module's whole subject
# is that the shipped bound is twenty, and a test reading the number off the code
# it is checking agrees with it whatever it says (`docs/MISTAKES.md` entry 19).
THE_GUARD_BOUND = 20

# The tail every fed comment carries, and the two fragments the pair turns on.
#
#   "greenhouse rotations"  g-r-e-e-n-h-o-u-s-e (10) + space (11) + r-o-t-a-t-i-o-n-s (20)
#   "greenhouse rotation"   the same, one character shorter                       (19)
#
# Both are counted by hand here and both are asserted against `len` in the control
# test below, so a miscount is a named failure rather than a boundary that quietly
# sits one character off.
A_FED_TAIL = "greenhouse rotations clash with the tutorial"
AT_THE_BOUND = "greenhouse rotations"
ONE_SHORT_OF_THE_BOUND = "greenhouse rotation"

# The nonces that route an answer to a section. Tokens that appear nowhere else in
# this repository, so finding one in a prompt is evidence rather than a coincidence
# with the prompt template (`docs/MISTAKES.md` entry 3).
QUIET_SECTION = "Hv8QzRt4Nm"
OTHER_SECTION = "Bd3XwLp9Kf"
BUSY_SECTION = "Ty6MnCv2Sq"


def a_comment_from(nonce: str, tail: str = A_FED_TAIL) -> str:
    """One instructor-stream comment carrying its stream marker and a routing nonce.

    The marker is what `StreamAwareGateway` reads the stream off — every comment
    this suite plants carries one, and a prompt with neither marker or both is a
    named failure in that double rather than a wrong answer.
    """
    return f"{INSTRUCTOR_MARK} {nonce} {tail}"


# **The summaries the model is made to answer with.** Each begins with its
# fragment, so no space to its left is in the match, and each is followed by a
# character the comment does not have there, so nothing extends it to the right.
#
# **Three points, not two, and the bound is the middle one.** The first version of
# this block straddled the bound at 19 and 21 and never stood on it, which the
# re-verification battery caught: raising the guard's bound to 21 — the permissive
# direction — left the whole suite green. So the set below is nineteen, exactly
# twenty, and twenty-one, and the guard refuses **at** twenty:
#
#   A_COMPLIANT_SUMMARY    "greenhouse rotation" (19) then " clashes" against the
#                          comment's "s clash" — `s` and ` ` differ, so the run
#                          stops at 19. Under the bound: **stored**.
#   A_SUMMARY_AT_THE_BOUND "greenhouse rotations" (20) then "," against the
#                          comment's " clash" — `,` and ` ` differ, so the run is
#                          exactly 20. At the bound: **refused**. This is the case
#                          a bound of 21 lets through and the reason it exists.
#   A_QUOTING_SUMMARY      "greenhouse rotations" (20) then " were" against the
#                          comment's " clash" — the space matches, `w` and `c` do
#                          not, so the run is 21. Over the bound: **refused**.
#
# The comma in the middle one is doing real work: a space there would match the
# comment's space and carry the run to 21, which is the same case as the last one.
A_QUOTING_SUMMARY = "Greenhouse rotations were the theme students raised this week."
A_SUMMARY_AT_THE_BOUND = "Greenhouse rotations, and the timetable, came up in both comments."
A_COMPLIANT_SUMMARY = "Greenhouse rotation clashes were the theme students raised this week."

# A theme label that quotes while the prose beside it does not. The guard's second
# leg is about the labels, and nothing in this repository exercised it: the mock's
# themes-only branch labels by ordinal ("theme 1"), so the exit drive can never
# meet a fragment in a label, and every other test in this module answers prose.
# The run here is "greenhouse rotations clash" — 26 characters, comfortably over
# the bound, with the comment's own next word included so a reader can see it is a
# lift rather than a coincidence.
A_THEME_LABEL_THAT_QUOTES = "greenhouse rotations clash"
A_THEME_COUNT_WITHIN_THE_WEEK = 1

# The same violation, reachable only after normalizing case and runs of
# whitespace. Raw, it shares no twenty-character run with anything; normalized, it
# is `A_QUOTING_SUMMARY`'s.
A_QUOTING_SUMMARY_IN_ANOTHER_CASE = (
    "GREENHOUSE   ROTATIONS were the theme students raised this week."
)

# A summary about a week with nothing of the commenters' words in it, for the
# sections that must go on being written while another is refused.
AN_UNRELATED_SUMMARY = "Two students describe timetable pressure without naming a session."


def _normalized(text: str) -> str:
    """Case and whitespace normalized, as this module reads D9's rule.

    Written here so every claim this module makes about an overlap is checkable
    against one definition, and so the control below can state the lengths in the
    same currency the guard is specified in. It is deliberately *not* imported from
    the implementation: a test that normalized with the code it is checking agrees
    with whatever that code does, including doing nothing.
    """
    return " ".join(text.lower().split())


def _longest_shared_run(left: str, right: str, *, normalize: bool = True) -> int:
    """The longest run of characters the two strings share, normalized unless asked otherwise.

    A plain quadratic walk. It is the measurement every claim in this module rests
    on, so it is written out rather than reached for in a library, and the control
    test drives it against strings whose answer is known by hand. The `normalize`
    switch exists for one assertion: that the case-and-space variant is a violation
    *only* after normalizing, which is what makes it a test of the normalization
    rather than a second copy of the plain violating case.
    """
    first = _normalized(left) if normalize else left
    second = _normalized(right) if normalize else right
    best = 0
    for start in range(len(first)):
        for end in range(start + best + 1, len(first) + 1):
            if first[start:end] in second:
                best = end - start
            else:
                break
    return best


def _summaries_for(world: SummaryWorld, cohort: str) -> list[dict[str, Any]]:
    """One section's stored summaries for the instructor stream."""
    return [
        row
        for row in world.summaries(section_id=world.section_id(cohort))
        if str(row[SUMMARY_STREAM_COLUMN]) == INSTRUCTOR_STREAM
    ]


class SummaryChosenByPrompt(StreamAwareGateway):
    """A gateway that answers a different summary depending on which section is asked about.

    `StreamAwareGateway` answers one summary for every call, which cannot pose this
    module's central question: whether a refusal is scoped to the section-week that
    provoked it, or takes the walk down with it. Each section's comments carry their
    own nonce, so the answer follows the request the same way the base class makes
    the *stream* follow it.

    Everything else — reading the stream off the markers, building the contract
    objects, recording the prompts — is the base class's and is not re-implemented
    (`docs/MISTAKES.md` entry 13).
    """

    def __init__(
        self,
        api: Any,
        *,
        by_nonce: dict[str, str],
        otherwise: str,
        themes_by_nonce: dict[str, tuple[tuple[str, int], ...]] | None = None,
    ) -> None:
        super().__init__(api)
        self.__dict__["by_nonce"] = dict(by_nonce)
        self.__dict__["otherwise"] = otherwise
        # **Themes are routed the same way the summary is**, because the guard has
        # two legs and only one of them is about prose. A caller that names no
        # themes for a nonce gets the base class's default, which is one label that
        # quotes nothing — so every test that is about the prose stays about the
        # prose.
        self.__dict__["themes_by_nonce"] = dict(themes_by_nonce or {})

    def _answer(self, kwargs: dict[str, Any]) -> Any:
        prompt = str(kwargs.get("prompt", ""))
        chosen = [text for nonce, text in self.by_nonce.items() if nonce in prompt]
        if len(chosen) > 1:  # pragma: no cover - a broken test, not a red
            pytest.fail(
                f"One prompt carries {len(chosen)} of this test's section nonces, so a single call "
                "was handed two sections' comments and no answer this double gives is about one "
                "section-week."
            )
        self.__dict__["summary"] = chosen[0] if chosen else self.otherwise
        labelled = [themes for nonce, themes in self.themes_by_nonce.items() if nonce in prompt]
        if labelled:
            self.__dict__["themes"] = {stream: labelled[0] for stream in STREAM_MARKS}
        return super()._answer(kwargs)


def _a_quiet_week(world: SummaryWorld, *, cohort: str, nonce: str, respondents: int) -> None:
    """One closed week of `respondents` students, each leaving one instructor comment."""
    for index in range(respondents):
        world.respond(
            f"{nonce}-subject-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=a_comment_from(nonce),
        )


def test_the_arithmetic_this_module_rests_on_is_what_it_says_it_is() -> None:
    """The control. **A red here means this module is broken, not the guard.**

    Every claim below is a claim about the length of a shared run between two
    strings, and every one of them was counted by hand. A fragment one character
    longer or shorter than stated moves the whole boundary: the "compliant" summary
    would violate, or the violating one would not, and the pair would test the
    guard at a number nobody chose.

    So the four literals are measured here, against the definition of normalization
    this module reads D9's rule with, before any test uses them.
    """
    assert len(AT_THE_BOUND) == THE_GUARD_BOUND, (
        f"{AT_THE_BOUND!r} is {len(AT_THE_BOUND)} characters and this module needs exactly "
        f"{THE_GUARD_BOUND}."
    )
    assert len(ONE_SHORT_OF_THE_BOUND) == THE_GUARD_BOUND - 1, (
        f"{ONE_SHORT_OF_THE_BOUND!r} is {len(ONE_SHORT_OF_THE_BOUND)} characters and this module "
        f"needs exactly {THE_GUARD_BOUND - 1}."
    )

    fed = a_comment_from(QUIET_SECTION)
    quoting = _longest_shared_run(A_QUOTING_SUMMARY, fed)
    at_the_bound = _longest_shared_run(A_SUMMARY_AT_THE_BOUND, fed)
    labelled = _longest_shared_run(A_THEME_LABEL_THAT_QUOTES, fed)
    compliant = _longest_shared_run(A_COMPLIANT_SUMMARY, fed)
    normalized_only = _longest_shared_run(A_QUOTING_SUMMARY_IN_ANOTHER_CASE, fed)
    unrelated = _longest_shared_run(AN_UNRELATED_SUMMARY, fed)

    assert quoting >= THE_GUARD_BOUND, (
        f"The quoting summary shares a run of {quoting} characters with the comment it was fed, "
        f"and the guard's bound is {THE_GUARD_BOUND}. Below it, every refusal this module asserts "
        "would be a refusal of something the guard is not about."
    )
    assert at_the_bound == THE_GUARD_BOUND, (
        f"The at-the-bound summary shares a run of {at_the_bound} characters and this module's "
        f"whole reason for it is that the run is exactly {THE_GUARD_BOUND} — the one length that "
        "tells a guard refusing at the bound from one refusing above it. At 21 it is a second copy "
        f"of the quoting case; at {THE_GUARD_BOUND - 1} it is a second copy of the compliant one. "
        "The comma after the fragment is what holds it there: a space would match the comment's "
        "space and carry the run to 21."
    )
    assert labelled >= THE_GUARD_BOUND, (
        f"The quoting theme label shares only {labelled} characters with the comment it was fed, "
        "so the theme-label test would be asserting a refusal nothing was owed."
    )
    assert _longest_shared_run(AN_UNRELATED_SUMMARY, fed) < THE_GUARD_BOUND, (
        "The prose the theme-label test pairs with that label is itself a violation, so a refusal "
        "there would not be evidence about the labels at all."
    )
    assert compliant == THE_GUARD_BOUND - 1, (
        f"The compliant summary shares a run of {compliant} characters, and this module's whole "
        f"boundary claim is that it is exactly {THE_GUARD_BOUND - 1} — one short. At "
        f"{THE_GUARD_BOUND} it is a violation and the near-miss test asserts the guard fails to "
        "fire on a violation; below that, an off-by-one in the guard is invisible."
    )
    assert normalized_only >= THE_GUARD_BOUND, (
        f"The case-and-space variant shares only {normalized_only} normalized characters, so the "
        "normalization test below would be asserting a refusal nothing was owed."
    )
    raw = _longest_shared_run(A_QUOTING_SUMMARY_IN_ANOTHER_CASE, fed, normalize=False)
    assert raw < THE_GUARD_BOUND, (
        f"The case-and-space variant shares a run of {raw} characters with the fed comment "
        "*without* normalizing, at or above the bound — so a guard comparing raw text would refuse "
        "it too, and the normalization test would pass against a guard that normalizes nothing "
        "(`docs/MISTAKES.md` entry 3: a guard whose outcome a second layer also produces)."
    )
    assert normalized_only > raw, (
        f"Normalizing changes nothing about this variant ({normalized_only} against {raw}), so it "
        "is not a case-and-whitespace test at all."
    )
    # The replacement character is U+00A0 NO-BREAK SPACE, spelled as an escape
    # so the respelling is visible in the source rather than an invisible byte.
    respelled = _longest_shared_run(A_QUOTING_SUMMARY_IN_ANOTHER_CASE.replace(" ", "\u00a0"), fed)
    assert respelled == normalized_only, (
        f"The variant's normalized overlap is {normalized_only} as written and {respelled} with "
        "its spaces respelled, so the measurement depends on which space character the literal "
        "happens to carry — which would make every length claimed in this module a claim about "
        "an invisible character rather than about the guard's bound."
    )
    assert unrelated < THE_GUARD_BOUND, (
        f"The unrelated summary shares {unrelated} characters with a fed comment, at or above the "
        "bound — so the sections that are supposed to go on being written would be refused too, "
        "and the scoping assertions would measure nothing."
    )


def test_a_small_n_summary_quoting_a_comment_is_refused_and_the_other_section_is_written(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The guard, and the scope of what it rolls back.

    Two sections, both with a closed week below the threshold, both fed instructor
    comments. The model answers one of them with a summary that reuses twenty
    characters of a comment it was given and the other with prose that reuses
    nothing. The quoting section-week stores no row; the other stores its own.

    **Both halves are the test.** A guard that refused everything would satisfy the
    first assertion perfectly and is a job that stores no summary at all, which
    §5.1 says is the one signal a small-N week has. A guard that refused nothing
    would satisfy the second. Only the pair says the refusal is aimed.

    **The mutations this kills:** the guard absent (the quoting row is stored); the
    guard scoped to the whole run rather than to the section-week (the compliant
    section loses its row too); a guard that logs and stores anyway, which is the
    shape a reviewer accepts as "fail soft" and which leaves the quoted words on the
    report for the rest of the term — E4's breakdown decision 2 rules out
    regeneration, so a stored summary is permanent.

    **The near miss it must survive:** a guard that refuses the *stream* rather than
    the section-week, which is indistinguishable here because only the instructor
    stream is fed. That distinction is out of reach of this world and is named
    rather than claimed (`docs/MISTAKES.md` entry 14).
    """
    summary_job_contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; this world needs a week strictly under it "
        "holding at least two respondents."
    )

    summary_world.build(A_COHORT)
    summary_world.add_section(ANOTHER_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    _a_quiet_week(summary_world, cohort=ANOTHER_COHORT, nonce=OTHER_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_QUOTING_SUMMARY, OTHER_SECTION: AN_UNRELATED_SUMMARY},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=gateway)

    assert len(gateway.prompts) >= 2, (
        f"The walk made {len(gateway.prompts)} model calls over two closed weeks each carrying "
        "instructor comments, so at least one section was never visited and the assertions below "
        "are about a walk that did not happen."
    )

    written = _summaries_for(summary_world, ANOTHER_COHORT)
    assert written, (
        "The section whose summary reused none of its commenters' words has no stored summary "
        "either. SPEC §5.1 generates a summary even in a small-N week — 'there, the summary is the "
        "only comment signal' — so a guard that took the whole run down with one refusal costs "
        "every other section its week's only signal.\n\n"
        "This is asserted before the refusal below, because a job that stored nothing at all "
        "satisfies that refusal perfectly (`docs/MISTAKES.md` entry 3)."
    )

    refused = _summaries_for(summary_world, A_COHORT)
    assert refused == [], (
        "The summary quoting a commenter's own words was stored: "
        f"{[row[SUMMARY_TEXT_COLUMN] for row in refused]!r}.\n\n"
        f"It shares a run of {_longest_shared_run(A_QUOTING_SUMMARY, a_comment_from(QUIET_SECTION))} "
        f"normalized characters with a comment it was fed, and the guard's bound is "
        f"{THE_GUARD_BOUND}. The owner's ruling of 2026-09-09 is that below the threshold a "
        "summary names themes only and may not reuse the commenters' word strings — the prompt "
        "asks for that and the model may ignore it, which is why the write is refused rather than "
        "trusted. E4's breakdown decision 2 rules out regeneration, so a stored summary carrying "
        "somebody's words carries them for the rest of the term."
    )


def test_a_small_n_summary_one_character_short_of_the_bound_is_stored(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The boundary from the other side: nineteen characters is not twenty.

    The same world, the same section, the same fed comment — and a summary whose
    longest shared run with it is exactly one character short of the bound. It must
    be stored.

    **Without this half the guard has no upper limit anybody is holding.** A guard
    comparing against 5, or against 1, or one that refuses any shared word at all
    refuses every summary a model could write about a week's comments, and every
    other assertion in this module is satisfied by it. The cost lands where nobody
    looks: small-N weeks stop having summaries, which is the one comment signal
    §5.1 promises them, and the report shows an empty region instead.

    **The mutation this kills:** the comparison written `>= THE_GUARD_BOUND - 1`,
    or a bound tightened without the ADR that D9 says records it. Its pair is the
    test above, whose overlap is one character longer in the same world.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_COMPLIANT_SUMMARY},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=gateway)

    stored = _summaries_for(summary_world, A_COHORT)
    assert [row[SUMMARY_TEXT_COLUMN] for row in stored] == [A_COMPLIANT_SUMMARY], (
        f"The stored summaries for this quiet week are {[row[SUMMARY_TEXT_COLUMN] for row in stored]!r}"
        f" and the model answered {A_COMPLIANT_SUMMARY!r}, whose longest shared run with the "
        f"comment it was fed is {_longest_shared_run(A_COMPLIANT_SUMMARY, a_comment_from(QUIET_SECTION))}"
        f" normalized characters — one short of the bound of {THE_GUARD_BOUND}.\n\n"
        "A guard that refuses here refuses more than the ruling asks for, and what it costs is the "
        "summary itself: SPEC §5.1 makes it the only comment signal a small-N week has, so a bound "
        "set too low turns every quiet week's summary region into an empty one."
    )


def test_a_run_of_exactly_the_bound_is_refused(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The bound itself, stood on rather than straddled.

    A summary sharing a run of **exactly** twenty normalized characters with a
    comment it was fed. It must be refused: D9's rule is "any twenty-character
    substring", so twenty is inside the refusal and not outside it.

    **This test exists because the re-verification battery found its absence.** The
    pair that was here compared nineteen and twenty-one, which straddles the bound
    without ever standing on it — and a guard whose bound had drifted to
    twenty-one, the permissive direction, left the whole suite green. A boundary
    tested at 19 and 21 is a boundary tested at neither.

    **The mutation this kills:** the comparison written `> THE_GUARD_BOUND` or
    `>= THE_GUARD_BOUND + 1` — the bound moved one character in the direction that
    lets a quotation through. It is the drift nothing else in this repository
    notices, and it lets out exactly the twenty-character lift the ruling names.

    **The near miss it must survive:** the nineteen-character case above, which is
    one character shorter in the same world and must still be stored. The two
    together are what pin the bound rather than a range around it.

    **Expected green on the built tree.** The guard exists and refuses at the
    bound; the proof of this test is the mutation, not the run.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_SUMMARY_AT_THE_BOUND},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=gateway)

    stored = [row[SUMMARY_TEXT_COLUMN] for row in _summaries_for(summary_world, A_COHORT)]
    assert stored == [], (
        f"The stored summaries are {stored!r}. The answer shares a run of exactly "
        f"{_longest_shared_run(A_SUMMARY_AT_THE_BOUND, a_comment_from(QUIET_SECTION))} normalized "
        f"characters with a comment it was fed, and the bound is {THE_GUARD_BOUND}.\n\n"
        "The owner's ruling of 2026-09-09 refuses *any* twenty-character substring, so twenty is "
        "inside the refusal. A guard comparing `> 20` stores this — and nothing else in this "
        "repository notices, which is what the re-verification battery measured before this test "
        "existed."
    )


def test_a_clean_summary_with_a_quoting_theme_label_is_refused(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The other leg: a label quotes while the prose does not.

    §5.1 makes themes part of what a summary answers, and E4-02 stores them beside
    the text in the same row. A theme label is short, sits on the report next to the
    prose, and is the most natural place for a model to put a phrase it lifted —
    "greenhouse rotations clash" reads as a theme and is a commenter's own words.

    So the answer here is clean prose with a quoting label. It must be refused for
    the label alone.

    **This test exists because the battery found the leg had no killer.** Deleting
    the label check — comparing the prose and nothing else — survived: the mock's
    themes-only branch labels by ordinal ("theme 1", "theme 2"), so the exit drive's
    body-wide search can never meet a fragment in a label, and every other test in
    this module answers prose. The leg was built, reviewed and unasserted.

    **The mutation this kills:** the label leg deleted — the guard reading
    `answer.summary` and not walking `answer.themes`. Its symptom is exactly this
    world: a report whose prose says nothing and whose theme line says what a
    student wrote, in a week where §4 withheld the comment.

    **The near miss it must survive:** a refusal that came from the prose after
    all. The prose is `AN_UNRELATED_SUMMARY`, whose longest run with the fed comment
    is asserted under the bound in this module's control before any test uses it, so
    a refusal here can only be the label's.

    **What it does not reach** (`docs/MISTAKES.md` entry 14): whether the label leg
    respects the small-N scope. That scope is shared with the prose leg and is
    driven both ways by
    `test_the_guard_is_not_applied_to_a_week_at_or_above_the_threshold`; a build
    that scoped one leg and not the other would pass everything here. It is named
    rather than claimed.

    **Expected green on the built tree.** The guard covers both legs; the proof is
    the mutation.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: AN_UNRELATED_SUMMARY},
        otherwise=AN_UNRELATED_SUMMARY,
        themes_by_nonce={
            QUIET_SECTION: ((A_THEME_LABEL_THAT_QUOTES, A_THEME_COUNT_WITHIN_THE_WEEK),)
        },
    )
    summary_job_contract.run(gateway=gateway)

    stored = [row[SUMMARY_TEXT_COLUMN] for row in _summaries_for(summary_world, A_COHORT)]
    assert stored == [], (
        f"The stored summaries are {stored!r}, and the answer that produced them carried the theme "
        f"label {A_THEME_LABEL_THAT_QUOTES!r} — "
        f"{_longest_shared_run(A_THEME_LABEL_THAT_QUOTES, a_comment_from(QUIET_SECTION))} "
        f"normalized characters of a comment it was fed, against a bound of {THE_GUARD_BOUND}.\n\n"
        "The prose beside it quotes nothing, so a guard reading `summary` and not walking `themes` "
        "stores this row whole: a report whose paragraph says nothing and whose theme line says "
        "what a student wrote, in a week where SPEC §4 withheld that student's comment. A theme is "
        "shorter than a sentence and sits next to the prose, which makes it the likelier place for "
        "a lift, not the safer one."
    )


def test_the_guard_is_not_applied_to_a_week_at_or_above_the_threshold(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The scope of the ruling: above the threshold the contract is unchanged.

    The same quoting summary, over a week holding exactly the configured threshold
    of responses. It must be stored. The ruling is explicit that above the threshold
    nothing changes, and the reason is that there is nothing left to protect: the
    raw comments are on the report, under their own heading, in full. A summary that
    echoes one of them discloses nothing the reader is not already looking at.

    **The mutation this kills:** the guard applied to every week rather than to
    small-N weeks — the scope inverted, or the response count never consulted. It is
    the *safe-looking* mistake, which is why it needs a test: applying a
    confidentiality guard more widely than the rule asks reads as caution, and what
    it costs is that summaries of ordinary weeks start disappearing whenever a model
    quotes a phrase, silently, with no signal anywhere that a summary was owed.

    **The near miss it must survive:** a guard keyed on something that correlates
    with the response count in this world but is not it — the number of comments,
    say. Here they are equal, one comment per respondent, and that is stated rather
    than hidden: pulling those two apart needs a week where they differ and is
    `test_a_held_comment_does_not_change_the_response_count_the_summary_states`'s
    subject rather than this one's (`docs/MISTAKES.md` entry 14).
    """
    summary_job_contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()

    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=BUSY_SECTION, respondents=threshold)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={BUSY_SECTION: A_QUOTING_SUMMARY},
        otherwise=A_QUOTING_SUMMARY,
    )
    summary_job_contract.run(gateway=gateway)

    stored = _summaries_for(summary_world, A_COHORT)
    assert stored, (
        f"A week holding exactly the configured threshold of {threshold} responses stored no "
        "summary, and the model's answer for it reused a commenter's words.\n\n"
        "The owner's ruling of 2026-09-09 is scoped to weeks *below* the threshold, and says why: "
        "above it the raw comments are on the report already, so a summary echoing one of them "
        "discloses nothing. A guard applied to every week reads as caution and costs an ordinary "
        "week its summary whenever a model quotes a phrase — silently, with nothing on the report "
        "saying a summary was owed."
    )


def test_a_refused_week_is_written_on_the_next_run_when_the_answer_complies(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The refusal is a hold, not a verdict: the week retries and can still be written.

    D9's own sentence — "the week retries next run, absence is honest". The first
    run's answer quotes and is refused; nothing is stored. The second run, over the
    same unchanged world, gets a compliant answer and stores it.

    **This is what makes the refusal survivable.** E4's breakdown decision 2 makes
    the job generate once and never regenerate, so "has no summary yet" is the only
    state from which a week can be written at all. A guard that refused the write
    *and* left behind anything the walk reads as "this week is done" — an empty row,
    a marker, a row with null text — makes the refusal permanent, and the quiet
    week that most needs a summary is the one that never gets one.

    **The mutation this kills:** the rollback leaving a row behind, or the walk's
    "already summarized" test reading something the refused attempt wrote. Both are
    invisible on a single run, which is the whole reason this is driven twice
    (`docs/MISTAKES.md` entry 31: running it twice is the only way to see it).

    **The near miss it must survive:** a job that ignores the guard on the second
    run — which would also store, and for the wrong reason. The second answer is
    compliant, so a store here is a store the ruling permits; the refusal half is
    asserted first, in between, so a job that stored on run one is caught before
    run two happens.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    quoting = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_QUOTING_SUMMARY},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=quoting)
    assert _summaries_for(summary_world, A_COHORT) == [], (
        "The first run stored the quoting summary, so this test's second run is not a retry of a "
        "refused week — it is a second look at a week that was already written, and E4's "
        "breakdown decision 2 makes that a no-op. The refusal is asserted in full by "
        "`test_a_small_n_summary_quoting_a_comment_is_refused_and_the_other_section_is_written`."
    )

    complying = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_COMPLIANT_SUMMARY},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=complying)

    stored = [row[SUMMARY_TEXT_COLUMN] for row in _summaries_for(summary_world, A_COHORT)]
    assert stored == [A_COMPLIANT_SUMMARY], (
        f"After a refused first run and a compliant second, the week's stored summaries are "
        f"{stored!r}.\n\n"
        "An empty list is a refusal that turned into a permanent absence: the walk selects weeks "
        "with no `weekly_summary` rows (breakdown decision 2 rules out regeneration), so a rollback "
        "that left anything behind — an empty row, a marker, a null-text row — makes the week look "
        "done and it is never written again. D9's own words are that the week retries next run."
    )


def test_a_quoting_summary_is_refused_even_when_only_normalization_reveals_it(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Case and whitespace do not launder a quotation.

    The same twenty characters, upper-cased and with runs of spaces through them.
    Raw, it shares no long run with anything; normalized as D9 specifies —
    case and whitespace — it is the same quotation, and it must be refused the same
    way.

    **Why this is a test rather than a detail.** A model asked for themes and given
    a comment will very often return the phrase capitalized, at the head of a
    sentence, or re-wrapped across a line break. A guard comparing raw text catches
    the one form nobody writes and misses the forms everybody does, while looking
    exactly like a working guard on every other test in this module.

    **The mutation this kills:** the normalization dropped, or applied to one side
    of the comparison only — which is the same defect and is easier to write.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(A_COHORT)
    _a_quiet_week(summary_world, cohort=A_COHORT, nonce=QUIET_SECTION, respondents=2)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = SummaryChosenByPrompt(
        summary_contracts,
        by_nonce={QUIET_SECTION: A_QUOTING_SUMMARY_IN_ANOTHER_CASE},
        otherwise=AN_UNRELATED_SUMMARY,
    )
    summary_job_contract.run(gateway=gateway)

    stored = [row[SUMMARY_TEXT_COLUMN] for row in _summaries_for(summary_world, A_COHORT)]
    assert stored == [], (
        f"The stored summaries are {stored!r}. The answer reuses "
        f"{AT_THE_BOUND!r} from a comment it was fed, upper-cased and with runs of spaces through "
        "it — the same quotation, in the form a model most often returns it: at the head of a "
        "sentence, or re-wrapped.\n\n"
        "D9 specifies the comparison as case and whitespace normalized for exactly this reason. A "
        "guard comparing raw text catches the one spelling nobody writes and misses every spelling "
        "somebody does, while passing every other test in this module."
    )
