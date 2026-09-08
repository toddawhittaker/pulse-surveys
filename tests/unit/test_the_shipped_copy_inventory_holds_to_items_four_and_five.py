"""E2-11 — SPEC §4.1 items 4 and 5, asserted over the strings that actually ship.

Both items have been "enforced by review only" since E0, and each says in its own
footnote that E2 ends that. SPEC §14.3's E2 exit clause names the mechanism: "the
copy-inventory test exists and reads the survey surface's shipped strings".

The two items, in the spec's own words:

> 4. Aggregate language counts sections, never instructors; "needs attention,"
>    never "underperforming"; no ranking, no composite scores, and no
>    score-sorting anywhere.
> 5. Confidentiality copy appears exactly once per surface (survey: once per
>    screen, in the submit area), in plain words, no shield or lock iconography.

That parenthetical was "(survey: in the submit bar)" until E2-17. The ruling of
2026-09-03 read "once per surface" as once per *screen*, and the submit bar is
per section — so a student in two courses whose windows are open at the same
minute met the sentence twice. Nothing collected here changed with it: this
module counts one string in an inventory, and where that string is rendered is
`tests/e2e/student-survey-confidentiality.spec.ts`'s.

`tests/fixtures/copy_inventory.py` collects the strings from their sources of
record — the `app.copy` registry through E2-08's own reader, and the frontend copy
files by parsing each one. Nothing here holds a copy of a shipped sentence, so
rewording the survey does not redden this module (`docs/MISTAKES.md` entry 19).
The one exception is item 5's recognizer, whose subject *is* the sentence's
vocabulary, and it is written from item 5 and §4 rather than from what shipped.

**The surface model, as E4-12 leaves it.** A surface is a governed body of
shipped strings. There were three prefixes and one surface until E4-12 — the
survey, arriving as `student_survey` from the frontend and `submit` and `student`
from the backend — and there are four surfaces now:

  - `survey`, unchanged;
  - `report`, the instructor Monday report, arriving under five prefixes for one
    rendered screen. Four are frontend copy modules, one per region the epic
    built: `instructor_report_page`, `instructor_report_trend`,
    `instructor_report_stats` and `instructor_report_comments`. The fifth,
    `instructor_report`, is the registry module holding the two refusals
    `app.api.instructor` answers — the same relationship `submit` and `student`
    have to `student_survey` on the survey, since item 5 counts the screen rather
    than the source;
  - `gradebook`, the two strings Pulse ships into an LMS gradebook (SPEC §3.4's
    line item label and its per-week ledger line);
  - `unknown_address`, the fallback screen a wrong address lands on.

`GOVERNED_SURFACES` is the whole of that governance, asserted in both directions:
a key whose prefix no surface governs is red, and a governed prefix that collects
nothing is red.

**And a surface either carries item 5's line or is named as owing none.** The
survey and the report carry one, and `CONFIDENTIALITY_KEY_OF_SURFACE` says which
entry it is. The gradebook is rendered by another product and says only what a
score is made of; the unknown-address screen shows nobody's data at all. Neither
promises a student anything about identity, so item 5's "exactly once" would be
demanding a sentence with no subject — they sit in
`SURFACES_WITH_NO_CONFIDENTIALITY_LINE` with the reason written down, and the
rules require **one** line on the first pair and **none** on the second. A
surface in neither map, or in both, is red: the point of two explicit maps is
that the next surface is placed deliberately rather than defaulting into whatever
the code happens to do (ADR 0158).

**And item 5's count has exactly one named exception, which is a string rather
than a word.** `CONFIDENTIALITY_EXEMPT_KEYS` holds the report's small-N notice
with the reason it is not that surface's standing line. It is spelled as a key
because the first version of it was spelled as a gap in the recogniser's
vocabulary — unidentifiability language simply left out — and a gap cannot be
aimed at one sentence: it excused that notice and every other promise anywhere
that nobody can be identified, on every surface, with nothing in this module able
to go red for one. The words are read now and the one string is skipped by name.

**Which tests carry the marker.** The rules over shipped copy are marked
`invariant` and their docstrings name items 4 and 5. The instruments are not: the
sweep canaries, the parser controls and the synthetic-inventory controls assert
nothing about what ships, and CI's isolated §4.1 pass should fail on a rule rather
than on the thing that measures it. **A red in an unmarked test here means this
module is broken, not that the copy is** — read it that way before reading
anything else.

**Every sweep is run in both directions before it is run over the tree**
(`docs/MISTAKES.md` entry 3). A search for words that are not there is satisfied
perfectly by a search that has gone blind, so each one is given a sentence that
certainly trips it and a sentence that certainly does not, and neither is quoted
from the registry — a canary copied out of the thing being swept goes blind with
it. The collector is held to the same rule (entry 35): before its silence about
anything else counts, it must *find* a pair of known keys on each half of every
governed surface it can reach — through the backend import path and through the
frontend parse both. The canaries are counted by reading them rather than stated
here as a number, which is a number that was wrong twice while this file grew
(`docs/MISTAKES.md` entry 1).

**Honest limits, stated rather than discovered.** This reads files; it does not
render a screen.

  - A string assembled at runtime is invisible. Interpolation into one of these
    entries is visible (the text is collected whole); a sentence built by joining
    fragments in a component is not.
  - A literal written into a component rather than into a copy file is invisible
    **to this module**, and since E4-12 it is not invisible to the repository:
    `tests/unit/test_the_component_and_route_trees_ship_no_ungoverned_string.py`
    parses the component and route trees and refuses one, which is the carried
    E2-boundary entry that convention rested on until then. What that sweep does
    not reach is stated in its own docstring rather than summarised here.
  - An aria label built in a component was invisible for the same reason, and
    §4.1 item 1 names aria labels explicitly. The same sweep reads the visible
    attributes now; a label assembled from variables at runtime is still nobody's.
  - **Where the confidentiality line sits on the screen is not asserted here,
    and neither is how often it is rendered.** What this can check is that
    exactly one collected *string* on the surface is confidentiality copy. One
    string rendered once per section is two sentences on a screen and one entry
    in this inventory, which is why item 5's count is asserted in a browser as
    well: `tests/e2e/student-survey-confidentiality.spec.ts` counts it on a
    screen carrying two open surveys, and `tests/e2e/student-survey.spec.ts`
    holds the one-section reading.
  - **Iconography is checked as far as text carries it**, which is emoji and
    symbol code points inside the strings. A drawn lock in an SVG or an icon
    component is E2-10's review, not this.
  - Backend strings served from outside `app.copy` are not collected here. That a
    served refusal is one of the registry's strings is asserted where it is
    served, through `fixtures.submit.externalized_key_for`, and the registry's
    own shape is asserted in
    `tests/unit/test_the_submit_paths_copy_is_externalised.py`.
  - `tests/e2e/landing-views.spec.ts` and `tests/e2e/student-survey.spec.ts`
    deliberately hold their own copies of some sentences, as the proof that a
    refactor did not change them. They are not in this inventory and are not
    drift.

That module's `FORBIDDEN_COMPARISONS` sweep overlaps this one and stays: it is
E2-08's criterion 4 over the registry, this is E2-11's items 4 and 5 over
everything that ships, and two tickets' criteria holding each other up is
redundancy rather than duplication. Since E2-14 it stays *in two files* — the
vocabulary, the reader and the sweep's control are still in
`test_the_submit_paths_copy_is_externalised.py`, and the marked §4.1 assertion
that reads them is `test_the_shipped_copy_names_nothing_a_student_may_not_see.py`,
which was extracted so that its `invariant` marker sits at module level where the
denial-module sweep demands it. Nothing about what is swept changed.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from fixtures.copy_inventory import (
    FRONTEND_COPY_DIRECTORY,
    CopyInventoryError,
    CopyParseError,
    CopyString,
    collect_backend_copy,
    collect_frontend_copy,
    collect_shipped_copy,
    display,
    every_file_under_the_copy_directory,
    files_the_collector_did_not_read,
    frontend_copy_files,
    parse_copy_module,
    prefix_of,
)
from fixtures.submit import (
    CLASSIFIER_DOWN_KEY,
    COPY_MAPPING_NAME,
    COPY_MODULES_FUNCTION,
    COPY_PACKAGE,
    NOT_A_STUDENT_KEY,
)

# ---------------------------------------------------------------------------
# The governance map: which key prefix belongs to which surface, and where each
# surface's confidentiality line lives.
# ---------------------------------------------------------------------------

SURVEY = "survey"
REPORT = "report"
GRADEBOOK = "gradebook"
UNKNOWN_ADDRESS = "unknown_address"

# `student_survey` is E2-10's frontend copy module; `submit` and `student` are
# E2-08's and E2-09's registry modules, whose strings are the refusals and the
# bounce coaching the same screen shows. One surface, three prefixes.
#
# **The four `instructor_report_*` prefixes are one surface and not four.** E4
# shipped one copy module per region of the Monday report — the page shell, the
# trend pair, the statistics block, the comment groups — because four components
# were built by four tickets, and a reader meets all of it as one screen. Item 5
# counts per surface, so mapping them to four surfaces would demand four
# confidentiality sentences on one page, which is the opposite of what the item
# says. ADR 0158 records the reading.
#
# `gradebook` and `unknown_address` are governed for item 4's vocabulary and owe
# no line; see `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` below for each reason.
GOVERNED_SURFACES = {
    "student_survey": SURVEY,
    "submit": SURVEY,
    "student": SURVEY,
    "instructor_report_page": REPORT,
    "instructor_report_trend": REPORT,
    "instructor_report_stats": REPORT,
    "instructor_report_comments": REPORT,
    # The report surface's backend half. `app.api.instructor` answers two
    # refusals — one for a section outside the session's teaching set or absent
    # altogether, one for a course week the section has no window for — and they
    # are the report screen's words as much as the four frontend prefixes are.
    # The survey is the precedent: `student_survey` from the frontend and
    # `submit` and `student` from the registry are siblings on one surface, and
    # item 5 counts the screen rather than the source. `prefix_of` splits on the
    # first dot, so this row and `instructor_report_page` are distinct prefixes
    # rather than one shadowing the other.
    "instructor_report": REPORT,
    "gradebook": GRADEBOOK,
    "unknown_address": UNKNOWN_ADDRESS,
}

# Item 5: "Confidentiality copy appears exactly once per surface (survey: once
# per screen, in the submit area)". The string is this entry, whichever component
# renders it — E2-10 put it in `SubmitBar` and E2-17 lifted it to one placement
# per screen, and the *key* is what this module counts, so that move is invisible
# here by design.
#
# **The report's line is `instructor_report_page.comments_note`**, the standing
# sentence under the comment groups that says what an instructor is and is not
# shown about who wrote what. The comment module's small-N entry is *not* the
# report's line: it is suppression-state copy, present only in the weeks where
# comments are withheld, and a surface whose identity promise appears only in some
# weeks has no standing promise at all. That ruling is ADR 0158's.
#
# **It is recognised as confidentiality copy and exempted by name**, which is not
# the same thing as being unreadable to the recogniser and is the correction the
# security round made. `CONFIDENTIALITY_EXEMPT_KEYS` below carries the key and the
# reason.
CONFIDENTIALITY_KEY_OF_SURFACE = {
    SURVEY: "student_survey.confidentiality",
    REPORT: "instructor_report_page.comments_note",
}

# The other half of the surface model: a governed surface that owes item 5 no
# line, with the reason it owes none. Written out as a map rather than inferred
# from the absence of a row above, so that adding a surface is a decision about
# which of the two maps it belongs in — an omission would otherwise read exactly
# like a deliberate no-line surface, and the totality rule below is what makes
# that impossible.
SURFACES_WITH_NO_CONFIDENTIALITY_LINE = {
    GRADEBOOK: (
        "SPEC §3.4's line item label and per-week ledger, rendered by the LMS "
        "gradebook rather than by Pulse. Two strings naming a course activity and "
        "the arithmetic behind a score; neither tells a student what happens to "
        "their identity, and item 5's sentence would have no subject here."
    ),
    UNKNOWN_ADDRESS: (
        "The fallback screen for an address that resolves to nothing. It shows "
        "nobody's data, so there is nothing about anybody's identity to promise."
    ),
}

# The frontend canary keys. Two, because one of them is item 5's own subject and
# would go missing in exactly the case the rule is about; the heading is an
# ordinary entry whose absence means the parse, not the copy, has failed.
SURVEY_HEADING_KEY = "student_survey.heading"

# The same pair for the report surface, which E4-12 brings into the inventory.
# `instructor_report_comments.small_n.body` is the ordinary entry — it belongs to
# a different one of the report's four copy modules than the confidentiality line
# does, so between the two of them the canary reaches two of the four files.
# Presence and non-emptiness only, never the sentence (`docs/MISTAKES.md` entry
# 19): the small-N body's wording is E4-10's to change.
REPORT_SMALL_N_KEY = "instructor_report_comments.small_n.body"

# The gradebook's two strings, which reach the inventory through the backend
# registry rather than through a frontend file — SPEC §3.4's "Pulse Participation"
# line item and the `Week 1: 4 of 5 items` ledger line. The texts are pinned
# byte-for-byte by the grading and AGS suites and are deliberately not repeated
# here; what this module needs is that the inventory can *see* them.
GRADEBOOK_LABEL_KEY = "gradebook.line_item_label"
GRADEBOOK_LEDGER_KEY = "gradebook.ledger_line"

# The report API's two refusals, which reach the inventory through the registry
# the way the gradebook's strings do. `docs/tickets/e4/deferred.md`'s entry "The
# report API's two refusal sentences sit outside the copy registry" is what
# closes when they are collected under a prefix the governance map claims.
#
# The keys are named here and the sentences are not. The router's own tests, the
# component tests and `tests/e2e/instructor-report.spec.ts` each hold a
# transcription of the text — deliberately, as the proof that a refactor did not
# change it — and this module holds none, so rewording a refusal is a change to
# those files rather than to the inventory (`docs/MISTAKES.md` entry 19).
REPORT_SECTION_UNAVAILABLE_KEY = "instructor_report.section_unavailable"
REPORT_WEEK_UNAVAILABLE_KEY = "instructor_report.week_unavailable"

# The two module constants in `app.api.instructor` that carry those sentences
# today, at lines 108 and 116. Named rather than the sentences: what the rule
# below compares is two live objects, and the names are the handle it needs to
# reach one of them.
REPORT_API_MODULE = "app.api.instructor"
SECTION_UNAVAILABLE_CONSTANT = "SECTION_UNAVAILABLE"
WEEK_UNAVAILABLE_CONSTANT = "COURSE_WEEK_UNAVAILABLE"

# Which registry entry each of those constants must agree with.
REPORT_API_REFUSALS = {
    SECTION_UNAVAILABLE_CONSTANT: REPORT_SECTION_UNAVAILABLE_KEY,
    WEEK_UNAVAILABLE_CONSTANT: REPORT_WEEK_UNAVAILABLE_KEY,
}

# The report's four copy modules, by filename. E4-08, E4-09 and E4-10 each shipped
# one beside its components and E4-11 shipped the fourth, all outside the walked
# copy directory; E4-12's criterion 7 is that the collector's own list names them.
# Asserted through `frontend_copy_files` rather than through a second walk of the
# copy directory, because the currency that matters is the one the collector
# counts in (`docs/MISTAKES.md` entry 35).
REPORT_COPY_FILENAMES = (
    "instructorReportCommentCopy.ts",
    "instructorReportPageCopy.ts",
    "instructorReportStatCopy.ts",
    "instructorReportTrendCopy.ts",
)

SYNTHETIC = "a synthetic inventory built in this module"

# ---------------------------------------------------------------------------
# Item 4's vocabulary, from the item's own words and §5.6's non-goals line.
# ---------------------------------------------------------------------------

# `"needs attention," never "underperforming"`. §5.6 closes the same way: "Non-
# goals, permanently: no ranking, no composite scores, no 'underperforming.'"
# Spelled as stems so that "underperforms", "underperformer" and the hyphenated
# form are all reached.
UNDERPERFORMING_VOCABULARY = (
    "underperform",
    "under-perform",
    "under performing",
    "underachiev",
)

# "no ranking, no composite scores, and no score-sorting anywhere". The last
# clause has no single spelling, so the shapes a sorted-by-score sentence is
# written in are listed. "overall score" is here as a composite score under
# another name; if a later surface has a legitimate use for one of these, that is
# a dispute about item 4 rather than a term to quietly drop.
RANKING_VOCABULARY = (
    "ranking",
    "ranked",
    "leaderboard",
    "percentile",
    "composite score",
    "composite index",
    "overall score",
    "score-sorting",
    "sorted by score",
    "sorted by rating",
    "sort by score",
    "highest scoring",
    "lowest scoring",
    "highest rated",
    "lowest rated",
    "top performer",
    "bottom performer",
)

# "Aggregate language counts sections, never instructors."
#
# What text mechanically carries is a *count* of instructors, so that is what is
# swept: a counting word next to the plural, and the plural next to a word that
# measures it. The plural is required throughout, and deliberately: the survey's
# own questions are about "your instructor", singular, and a sweep for the word
# would refuse SPEC §3.2's first question.
#
# What it does not carry is stated rather than pretended: a sentence that counts
# instructors without saying so — "12 people need attention" over a list of
# instructors — reads as permitted here, because the noun is where the difference
# lives and this can only read the noun. That half of the clause is a review
# question, and item 4's own footnote says the vocabulary rule is what E2 asserts.
INSTRUCTORS_COUNTED = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|many|most|few|"
    r"number\s+of|count\s+of|how\s+many|total\s+of|top|bottom)\b"
    r"(?:\s+\w+){0,2}\s+instructors\b",
    re.IGNORECASE,
)
INSTRUCTORS_MEASURED = re.compile(
    r"\binstructors\b(?:\s+\w+){0,2}\s+"
    r"(?:ranked|counted|compared|sorted|scored|listed|needing\s+attention)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Item 5's vocabulary: what makes a string confidentiality copy, and what makes
# it iconography.
# ---------------------------------------------------------------------------

# Settled from item 5 ("Confidentiality copy ... in plain words") and from what
# §4 says such copy is about: responses are keyed to an LMS user id, identity is
# never displayed, comments carry no timestamps. A sentence that tells a student
# any of that carries one of these.
#
# The recognizer is deliberately wider than one phrase. Missing the shipped
# sentence would report zero on a surface that has one, and the exactly-once rule
# refuses zero as loudly as it refuses two — so an over-wide recognizer produces a
# red that names the second match, which is a legible failure, while a narrow one
# produces a red that names an absence, which reads as a missing line. If a
# shipped confidentiality sentence carries none of these words, that is a dispute
# about the recognizer, and the recognizer is what changes.
#
# **`no names` is E4-12's, and it is the instructor half of the same promise.**
# The survey tells a student their name is not attached; the report tells an
# instructor no name is there to read. The existing markers are all written from
# the student's side — "your name", "identify you" — and none of them matches a
# sentence addressed to the person doing the reading, which is why the report's
# line was invisible to this recogniser until the marker was added.
#
# **`unidentifiab` is E4-12's security round, and it replaces a blind spot with
# an exemption.** The first version of this tuple left unidentifiability language
# out of the vocabulary altogether, so that the report's small-N notice would not
# be counted as a second line. A vocabulary hole is global: it excused that one
# sentence and, with it, every other sentence anywhere that promises a reader
# nobody can be identified — a second identity promise phrased that way would have
# been counted by nothing, on any surface, forever. The words are in the
# vocabulary now, and the one sentence that must not be counted is named by key
# below. Spelled as a stem so that "unidentifiable", "unidentifiability" and
# "unidentifiably" are all reached.
CONFIDENTIALITY_MARKERS = (
    "confidential",
    "anonymous",
    "anonymity",
    "your name",
    "who wrote",
    "identify you",
    "identifies you",
    "de-identified",
    "no names",
    "unidentifiab",
)

# The keys item 5's count skips, each with the reason it is skipped. **One
# sentence at a time, by key** — never by leaving words out of the vocabulary
# above, which is the difference this round was opened about: an exemption is a
# statement about one string that a reader of this file can weigh, and a missing
# word is a hole in every rule the vocabulary feeds.
#
# The exemption is narrow in the other direction too: it is the key, not the
# prefix and not the surface. A second sentence under a different key on the same
# surface is counted, which is what makes the report's standing line still exactly
# one.
CONFIDENTIALITY_EXEMPT_KEYS = {
    REPORT_SMALL_N_KEY: (
        "Suppression-state copy: it explains why SPEC §4's threshold is hiding this week's "
        "comments and renders only in that state, so it is not the surface's standing identity "
        "promise — `instructor_report_page.comments_note` is. Argued in ADR 0158 and settled by "
        "the ruling of 2026-09-08, now in §4.1 item 5's own words: a state notice is not the "
        "item's copy."
    ),
}

# "no shield or lock iconography", as far as a string can carry one: the lock,
# shield and key code points, written as code points because ruff reads several
# of them as confusables and this repository spells such characters out rather
# than adding an ignore (the same choice
# `tests/unit/test_the_submit_paths_copy_is_externalised.py` makes for curly
# quotation marks). A key is lock iconography; a drawn lock in an SVG is not
# text and is E2-10's review.
ICONOGRAPHY_CODE_POINTS = (
    0x1F512,  # lock
    0x1F513,  # open lock
    0x1F510,  # closed lock with key
    0x1F50F,  # lock with ink pen
    0x1F511,  # key
    0x1F5DD,  # old key
    0x1F6E1,  # shield
    0x26E8,  # black cross on shield
)
ICONOGRAPHY = tuple(chr(point) for point in ICONOGRAPHY_CODE_POINTS)

# ---------------------------------------------------------------------------
# The canary sentences. Written here, never quoted from the registry: a canary
# copied out of the thing being swept goes blind with it (`docs/MISTAKES.md`
# entry 3).
# ---------------------------------------------------------------------------

AN_UNDERPERFORMING_SENTENCE = "This section is underperforming against its peers."
A_NEEDS_ATTENTION_SENTENCE = "Three sections need attention this week."
A_RANKED_SENTENCE = "Sections are ranked by their composite score, highest rated first."
AN_INSTRUCTOR_COUNT_SENTENCE = "Four instructors in this department need attention this week."
AN_INSTRUCTOR_MEASURE_SENTENCE = "Instructors are ranked by section mean."
THE_SURVEYS_OWN_QUESTION = "How was your instructor this week?"
A_PLAIN_SENTENCE = "Answer the five questions below and press submit when you are ready."
A_CONFIDENTIALITY_SENTENCE = "Your instructor sees what you wrote, never your name."
A_SECOND_CONFIDENTIALITY_SENTENCE = "Your answers are anonymous to everyone in your course."

# The `no names` marker's own pair, written here and not copied from the report
# (`docs/MISTAKES.md` entry 3: a canary taken out of the thing being swept goes
# blind with it). The first is a standing promise addressed to the reader of a
# report; the second says the same thing in words the marker must not reach,
# because it is about a threshold this week rather than about the surface.
A_READER_FACING_CONFIDENTIALITY_SENTENCE = "Listed in a shuffled order, with no names attached."

# Unidentifiability language, in two places on purpose. The first stands for the
# exempt key's own copy — suppression state, why a thin week withholds its
# comments — and the second for the same promise made as a standing sentence
# somewhere else. **The recogniser must read both**: they say the same thing, and
# it is the key rather than the wording that decides which one item 5 counts.
# Neither is quoted from the report (`docs/MISTAKES.md` entry 3).
A_SUPPRESSION_STATE_SENTENCE = (
    "Too few people answered this week, so individual voices stay unidentifiable."
)
AN_UNIDENTIFIABILITY_PROMISE = (
    "Everything below is grouped to keep an individual student unidentifiable."
)

# The credit-rule note's neighbourhood: an ordinary explanatory sentence about
# how a score is worked out, which the recogniser must leave alone. If a marker
# ever reaches a sentence of this shape, the report starts counting two lines the
# day E4-12's participation note ships beside its confidentiality line.
AN_EXPLANATORY_SENTENCE = (
    "Each posted score counts the items a student completed against the items the weeks held."
)
A_LOCKED_SENTENCE = chr(0x1F512) + " Your answers are private."
A_SHIELDED_SENTENCE = chr(0x1F6E1) + " Protected by design."

# ---------------------------------------------------------------------------
# Samples the parser is exercised on before the shipped files are read.
# ---------------------------------------------------------------------------

CURLY_APOSTROPHE = chr(0x2019)

OPEN_LITERAL = "export const SAMPLE_COPY = {"
CLOSE_LITERAL = "} as const satisfies Record<string, string>;"

# A file written the way E2-10's is: a header comment, a quote-free declaration
# above the literal, dotted keys in one flat literal, a value carried onto its own
# line, an escaped apostrophe, a typographic apostrophe, a placeholder hole the
# screen fills, a trailing comment and a comment line of its own — and, below the
# literal, the helpers a copy file exports beside its mapping. The tail is shaped
# after `studentSurvey.ts`'s own: a `keyof typeof` key type, and a substitution
# helper whose documentation carries backticks and whose body carries a regex and
# no string at all.
#
# **Both regions outside the literal are represented, and both are quote-free.**
# That is the accepted half of one rule rather than of two: the parser applies the
# same no-quote test above the literal and below it, so the sample has to show a
# passing line on each side and the refusal cases have to show a refused line on
# each side.
A_COPY_FILE = "\n".join(
    [
        "/**",
        " * A sample copy module, shaped the way the shipped ones are.",
        " */",
        "",
        "type SampleValue = string;",
        "",
        OPEN_LITERAL,
        "  'sample.heading': 'Your weekly check-in',",
        "  'sample.confidentiality':",
        "    'Your instructor sees what you wrote, never your name.',",
        "  'sample.apostrophes': 'It" + CURLY_APOSTROPHE + "s your week, and it\\'s nearly over.',",
        "  'sample.placeholder': 'Between {minimum} and {maximum} hours.', // filled on screen",
        "  // the entry below carries quotation marks of its own",
        "  'sample.quoted': 'She wrote \\'it was okay\\' and nothing else.',",
        CLOSE_LITERAL,
        "",
        "/** Every key this surface publishes. */",
        "export type SampleCopyKey = keyof typeof SAMPLE_COPY;",
        "",
        "/**",
        " * One entry with its `{placeholders}` filled in.",
        " *",
        " * The backticks above are inside a comment, so nothing reads them as a string.",
        " */",
        "export function fillCopy(",
        "  key: SampleCopyKey,",
        "  values: Readonly<Record<string, string>>,",
        "): string {",
        "  return SAMPLE_COPY[key].replace(/\\{(\\w+)\\}/g, (whole, name: string) "
        "=> values[name] ?? whole);",
        "}",
        "",
    ]
)

A_COPY_FILES_ENTRIES = {
    "sample.heading": "Your weekly check-in",
    "sample.confidentiality": "Your instructor sees what you wrote, never your name.",
    "sample.apostrophes": "It" + CURLY_APOSTROPHE + "s your week, and it's nearly over.",
    "sample.placeholder": "Between {minimum} and {maximum} hours.",
    "sample.quoted": "She wrote 'it was okay' and nothing else.",
}

# The escapes a character can hide in. `\u{1F512}` is the one that matters: a lock
# written that way reaches the iconography sweep as the ordinary characters of an
# escape sequence unless the parser decodes it, and the sweep then reports the
# surface clean over a padlock that renders.
AN_ESCAPED_FILE = "\n".join(
    [
        "export const ESCAPED_COPY = {",
        "  'escaped.brace': 'a \\u{1F512} lock',",
        "  'escaped.pair': 'a \\uD83D\\uDD12 lock',",
        "  'escaped.four': 'a \\u0041 letter',",
        "  'escaped.hex': 'a \\x41 letter',",
        "  'escaped.backslash': 'one \\\\ backslash',",
        "  'escaped.newline': 'two\\nlines',",
        "} as const;",
    ]
)

# The four spellings of one padlock and two ordinary escapes. `escaped.brace` and
# `escaped.pair` must decode to the *same* character as each other and as the
# literal one: a browser renders all three identically, so a sweep that sees only
# some of them is a sweep with a spelling-shaped hole in it.
AN_ESCAPED_FILES_ENTRIES = {
    "escaped.brace": "a " + chr(0x1F512) + " lock",
    "escaped.pair": "a " + chr(0x1F512) + " lock",
    "escaped.four": "a A letter",
    "escaped.hex": "a A letter",
    "escaped.backslash": "one \\ backslash",
    "escaped.newline": "two\nlines",
}

# Every shape the parser must refuse rather than pass over. Each one is a way a
# string could ship without the inventory ever seeing it.
REFUSED_SHAPES = {
    "a value spelled as a template literal": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': " + chr(0x60) + "Your weekly check-in" + chr(0x60) + ",",
            CLOSE_LITERAL,
        ]
    ),
    "a key that is not quoted": "\n".join(
        [OPEN_LITERAL, "  heading: 'Your weekly check-in',", CLOSE_LITERAL]
    ),
    "a key with no colon after it": "\n".join(
        [OPEN_LITERAL, "  'sample.heading' 'Your weekly check-in',", CLOSE_LITERAL]
    ),
    "a string the line never closes": "\n".join(
        [OPEN_LITERAL, "  'sample.heading': 'Your weekly check-in,", CLOSE_LITERAL]
    ),
    "a statement inside the literal": "\n".join(
        [OPEN_LITERAL, "  const weeks = 12;", CLOSE_LITERAL]
    ),
    # Above the literal. The first is the reviewer's own demonstration: under the
    # prefix-matched allowance this parser used to carry, a `type` line was
    # skipped whole and these two sentences shipped ungoverned, while the same
    # sentences below the literal were refused. One rule, both regions.
    "a quoted sentence above the literal": "\n".join(
        [
            "type Mood = 'Great week' | 'Rough week';",
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
        ]
    ),
    "a constant sentence above the literal": "\n".join(
        [
            "const EMPTY_STATE = 'Nothing is open this week.';",
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
        ]
    ),
    # The two below the literal. A copy file's helpers live there and are allowed
    # to; what is not allowed is a string, because a sentence in a helper is
    # governed by nothing. The first is the blunt case and the second is the
    # discriminating one: its `export function` line carries no quote and passes,
    # and the refusal lands on the sentence in the body rather than on the helper.
    "a constant sentence below the literal": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
            "",
            "export const EMPTY_STATE = 'Nothing is open this week.';",
        ]
    ),
    "a sentence returned by a helper below the literal": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
            "",
            "export function fallback(): string {",
            "  return 'Nothing is open this week.';",
            "}",
        ]
    ),
    "a value assembled by concatenation": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly ' +",
            "    'check-in',",
            CLOSE_LITERAL,
        ]
    ),
    "a file exporting no object literal": "\n".join(
        ["// a copy file that forgot to export anything", "type Something = string;"]
    ),
    # The two halves of a surrogate pair, each on its own. Neither is a character
    # anything renders, so decoding one into the collected text would put a thing
    # in the inventory that no reader will ever see and no sweep can match.
    "a high surrogate with no low one after it": "\n".join(
        [OPEN_LITERAL, "  'sample.heading': 'a \\uD83D lock',", CLOSE_LITERAL]
    ),
    "a low surrogate with no high one before it": "\n".join(
        [OPEN_LITERAL, "  'sample.heading': 'a \\uDD12 lock',", CLOSE_LITERAL]
    ),
    "a file exporting two object literals": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
            "",
            "export const OTHER_COPY = {",
            "  'other.heading': 'Somewhere else entirely',",
            CLOSE_LITERAL,
        ]
    ),
    "an empty object literal": "\n".join([OPEN_LITERAL, CLOSE_LITERAL]),
    "a literal that is never closed": "\n".join(
        [OPEN_LITERAL, "  'sample.heading': 'Your weekly check-in',"]
    ),
    "the same key twice": "\n".join(
        [
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            "  'sample.heading': 'Something else',",
            CLOSE_LITERAL,
        ]
    ),
    "an unclosed block comment": "\n".join(
        [
            "/* a header nobody closed",
            OPEN_LITERAL,
            "  'sample.heading': 'Your weekly check-in',",
            CLOSE_LITERAL,
        ]
    ),
}


# ---------------------------------------------------------------------------
# The readers. One of each, called by the controls and by the rules alike, so
# that what a control proves is what a rule uses (`docs/MISTAKES.md` entry 13).
# ---------------------------------------------------------------------------


def forbidden_in(text: str, vocabulary: tuple[str, ...]) -> list[str]:
    """Every member of `vocabulary` that appears in `text`, case-insensitively."""
    lowered = text.lower()
    return sorted(word for word in vocabulary if word in lowered)


def instructor_counting_in(text: str) -> list[str]:
    """Every phrase in `text` that counts or measures instructors."""
    return sorted(
        match.group(0)
        for pattern in (INSTRUCTORS_COUNTED, INSTRUCTORS_MEASURED)
        for match in pattern.finditer(text)
    )


def iconography_in(text: str) -> list[str]:
    """Every lock, key or shield character in `text`."""
    return sorted(character for character in ICONOGRAPHY if character in text)


def is_confidentiality_copy(text: str) -> bool:
    """Whether `text` tells a student what happens to their identity."""
    return bool(forbidden_in(text, CONFIDENTIALITY_MARKERS))


def surface_of(key: str) -> str | None:
    """The surface a dotted key belongs to, or `None` when no surface governs it."""
    return GOVERNED_SURFACES.get(prefix_of(key))


def ungoverned_keys(inventory: tuple[CopyString, ...]) -> list[str]:
    """Every collected key whose prefix belongs to no governed surface."""
    return sorted(string.key for string in inventory if surface_of(string.key) is None)


def prefixes_that_collect_nothing(inventory: tuple[CopyString, ...]) -> list[str]:
    """Every governed prefix that no collected string belongs to."""
    present = {prefix_of(string.key) for string in inventory}
    return sorted(prefix for prefix in GOVERNED_SURFACES if prefix not in present)


def strings_on_surface(inventory: tuple[CopyString, ...], surface: str) -> list[CopyString]:
    """Every collected string that belongs to one surface."""
    return [string for string in inventory if surface_of(string.key) == surface]


def confidentiality_strings(
    inventory: tuple[CopyString, ...],
    surface: str,
    exempt: Mapping[str, str] | None = None,
) -> list[CopyString]:
    """Every string on one surface item 5 counts as confidentiality copy.

    The recogniser reads the words; this decides what is counted, and the two are
    separate on purpose. A sentence the recogniser could not read would be
    invisible to every surface at once, which is the hole the security round
    closed; a sentence the count skips is one named string with a reason beside
    it in `CONFIDENTIALITY_EXEMPT_KEYS`.

    The exemptions are a parameter with a default so the controls can run this
    with none — which is how "removing an exemption row reds the exactly-once
    rule" is demonstrated rather than asserted in prose.
    """
    skipped = CONFIDENTIALITY_EXEMPT_KEYS if exempt is None else exempt
    return [
        string
        for string in strings_on_surface(inventory, surface)
        if string.key not in skipped and is_confidentiality_copy(string.text)
    ]


def offenders(
    inventory: tuple[CopyString, ...], vocabulary: tuple[str, ...]
) -> dict[str, tuple[str, list[str]]]:
    """Every collected string carrying a forbidden word, keyed by its dotted key."""
    return {
        string.key: (string.text, found)
        for string in inventory
        if (found := forbidden_in(string.text, vocabulary))
    }


def surfaces_placed_in_neither_map(
    governed: Mapping[str, str],
    with_a_line: Mapping[str, str],
    without_a_line: Mapping[str, str],
) -> list[str]:
    """Every governed surface that neither map claims, so nothing decides its item 5.

    Takes the three maps as arguments rather than reading the module's own, so
    that the control below can run it over planted maps and the rule can run it
    over the real ones — one reader, both directions (`docs/MISTAKES.md` entry 13).
    """
    placed = set(with_a_line) | set(without_a_line)
    return sorted({surface for surface in governed.values() if surface not in placed})


def surfaces_placed_in_both_maps(
    with_a_line: Mapping[str, str],
    without_a_line: Mapping[str, str],
) -> list[str]:
    """Every surface claimed by both maps, which is two answers to one question."""
    return sorted(set(with_a_line) & set(without_a_line))


def a_governed_inventory(*extra: CopyString) -> tuple[CopyString, ...]:
    """A synthetic inventory that satisfies every rule here, plus whatever is added.

    Built from `GOVERNED_SURFACES` rather than written out, so a surface added to
    that map is covered by these controls on the same day it is added rather than
    leaving them exercising a map that no longer describes the tree.

    **The confidentiality entries are built from
    `CONFIDENTIALITY_KEY_OF_SURFACE` for the same reason.** It held one row until
    E4-12 and a control written around that one row would have gone on proving
    the survey's case only, while the report's rows landed with no synthetic
    control under them at all.
    """
    entries = [
        CopyString(f"{prefix}.probe", A_PLAIN_SENTENCE, SYNTHETIC) for prefix in GOVERNED_SURFACES
    ]
    entries.extend(
        CopyString(key, A_CONFIDENTIALITY_SENTENCE, SYNTHETIC)
        for key in CONFIDENTIALITY_KEY_OF_SURFACE.values()
    )
    return (*entries, *extra)


def without_prefix(inventory: tuple[CopyString, ...], prefix: str) -> tuple[CopyString, ...]:
    """The same inventory with every string under one prefix removed."""
    return tuple(string for string in inventory if prefix_of(string.key) != prefix)


def without_key(inventory: tuple[CopyString, ...], key: str) -> tuple[CopyString, ...]:
    """The same inventory with one key removed."""
    return tuple(string for string in inventory if string.key != key)


def keys_declared_on_disk() -> dict[str, list[str]]:
    """Every key every module in the copy package directory declares.

    A second, independent enumeration: the package *directory* is globbed and each
    module imported by name, rather than asking `copy_modules()` what there is.
    That is the point of it — a registry whose enumeration was replaced by a
    hand-written list would answer this question and the inventory's question
    differently, and the difference is what says the inventory has been shrunk.
    """
    package = importlib.import_module(COPY_PACKAGE)
    declared: dict[str, list[str]] = {}
    for location in getattr(package, "__path__", []):
        for path in sorted(Path(location).glob("*.py")):
            if path.stem == "__init__":
                continue
            module = importlib.import_module(f"{COPY_PACKAGE}.{path.stem}")
            mapping = getattr(module, COPY_MAPPING_NAME, None)
            if not isinstance(mapping, Mapping):
                pytest.fail(
                    f"`{module.__name__}` publishes no `{COPY_MAPPING_NAME}` mapping, so this "
                    "enumeration cannot say what it ships. E2-08's convention is one module per "
                    f"surface, each defining `{COPY_MAPPING_NAME}` keyed by dotted keys."
                )
            declared[module.__name__] = sorted(str(key) for key in mapping)
    return declared


# ---------------------------------------------------------------------------
# The instrument: the parser, both directions.
# ---------------------------------------------------------------------------


def test_the_parser_reads_a_copy_file_written_the_way_the_shipped_one_is() -> None:
    """The accepted direction, before anything is judged by what this parser reads.

    A parser that refused the shipped file would redden every rule below for a
    reason that has nothing to do with the copy, and a parser that quietly read
    half of it would leave the other half unswept.

    **The accepted direction of the below-the-literal rule is in this sample.** A
    copy file exports helpers beside its mapping — a `keyof typeof` key type, a
    substitution helper — and those must pass. What must not is a string written
    among them, which is the refused direction, exercised in
    `test_the_parser_refuses_a_shape_it_cannot_read`.

    **The mutation it kills:** narrowing the parser so that one of these shapes
    stops being read — a value carried onto its own line, an escaped apostrophe, a
    typographic apostrophe, a placeholder hole, a trailing comment, or the helper
    tail. Each is legitimate content in a shipped file, and dropping any one of
    them silently shrinks the inventory or reddens the ticket for doing something
    reasonable. **A red here means this module is broken, not that the copy is.**
    """
    read = parse_copy_module(A_COPY_FILE, "a sample copy file")
    assert read == A_COPY_FILES_ENTRIES, (
        f"The parser read {read!r} from a file written the way the shipped ones are.\n"
        f"  expected: {A_COPY_FILES_ENTRIES!r}\n"
        "\n"
        "Every rule in this module is a statement about the strings this parser returned, so a "
        "parser that drops an entry, or that keeps an escape undecoded, makes those rules quieter "
        "than they read."
    )


def test_the_parser_decodes_the_escapes_a_character_can_hide_in() -> None:
    """A lock written as an escape is a lock on the screen, and must be one here.

    Item 5 forbids lock iconography, and a sweep over undecoded source text would
    report the surface clean over a padlock that renders — a rule defeated by a
    spelling. **The spelling families, and which control covers each:**

      - the literal character: `A_LOCKED_SENTENCE`, in the iconography sweep's own
        control;
      - the brace escape `\\u{1F512}`: `escaped.brace` here;
      - **the surrogate pair** `\\uD83D\\uDD12`: `escaped.pair` here. This is the
        one the fresh-context review found shipping past the sweep — each half
        decoded on its own is a lone surrogate, so the joined character never
        appeared and nothing matched the lock;
      - a half of that pair with no partner: refused, in
        `test_the_parser_refuses_a_shape_it_cannot_read`;
      - an ordinary BMP escape (`\\u0041`) and a hex escape (`\\x41`): the two
        letter entries here, which must go on decoding correctly — a repair for
        the pair that broke the plain four-digit case would be a worse bug than
        the one it fixed.

    **The mutations it kills:** dropping the `\\u`, `\\u{...}` or `\\x` branch
    from `read_escape`; and decoding surrogate halves separately, which is what
    made the sweep silent. **A red here means this module is broken, not that the
    copy is.**
    """
    read = parse_copy_module(AN_ESCAPED_FILE, "a sample copy file")
    assert read == AN_ESCAPED_FILES_ENTRIES, (
        f"The parser read {read!r}.\n"
        f"  expected: {AN_ESCAPED_FILES_ENTRIES!r}\n"
        "\n"
        "The two lock entries are what matter: an escaped lock has to arrive as the lock "
        "character however it is spelled, or item 5's iconography sweep passes over it."
    )
    unswept = [key for key in ("escaped.brace", "escaped.pair") if not iconography_in(read[key])]
    assert not unswept, (
        f"The iconography sweep sees no lock in {unswept} after parsing. A string can then carry "
        "a padlock past §4.1 item 5 by choosing a spelling: the brace form, or the surrogate pair "
        "that a browser renders identically to the literal character."
    )


@pytest.mark.parametrize("shape", sorted(REFUSED_SHAPES))
def test_the_parser_refuses_a_shape_it_cannot_read(shape: str) -> None:
    """The refused direction: every way a string could ship unseen is loud.

    A collector that skips what it cannot classify reports a clean surface over
    strings it never read (`docs/MISTAKES.md` entries 3 and 9). Each sample here
    is a real way that would arrive: a template literal, a second literal in the
    same file, a value built by concatenation, an empty mapping, a duplicate key,
    and the two that matter most because the file's helpers live there — a
    sentence written into a constant below the literal, and one returned from a
    helper below it. The second is the discriminating case: its `export function`
    line carries no quote and passes, exactly as `fillCopy` does, and the refusal
    lands on the string in the body.

    **The mutations it kills:** any `continue` added to the parser's
    classification for a line it does not recognise; and allowing every line below
    the literal, which is the obvious repair for the day the parser first refuses
    a helper and would make a sentence written among the helpers invisible to
    §4.1 items 4 and 5 forever. **A red here means this module is broken, not that
    the copy is.**
    """
    with pytest.raises(CopyParseError):
        parse_copy_module(REFUSED_SHAPES[shape], f"a sample copy file holding {shape}")


def test_the_frontend_enumeration_finds_every_copy_file_at_every_depth(tmp_path: Path) -> None:
    """The accepted direction, and the two evasions the first version admitted.

    A violation planted to prove this suite can go red is an untracked file, so an
    enumeration that asked git would not see it and the proof run would come back
    green — which reads as "the finding was wrong" rather than "the guard is
    blind". So the walk is on disk.

    **It is also recursive and reads the whole TypeScript family**, because the
    fresh-context review shipped an item 4 violation and a padlock past the first
    version twice: once in `frontend/src/copy/reports/aggregate.ts`, a
    subdirectory a one-level glob never entered, and once in a `.tsx` beside the
    survey's own copy. Both are copy in the copy directory, and the suite was 41
    green with both planted.

    **The mutation it kills:** narrowing the walk back to one level, to one
    suffix, or to `git ls-files`. **A red here means this module is broken, not
    that the copy is.**
    """
    (tmp_path / "studentSurvey.ts").write_text(A_COPY_FILE, encoding="utf-8")
    (tmp_path / "beside.tsx").write_text(A_COPY_FILE, encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "aggregate.mts").write_text(A_COPY_FILE, encoding="utf-8")
    (tmp_path / "notes.md").write_text("not a copy file", encoding="utf-8")

    found = sorted(path.name for path in frontend_copy_files(tmp_path))
    assert found == ["aggregate.mts", "beside.tsx", "studentSurvey.ts"], (
        f"The enumeration found {found} in a directory holding three copy files — one nested, one "
        "`.tsx`, one `.ts` — and one note. Each of the first three is a shipped surface's strings, "
        "and a walk that misses any of them reports a clean tree over copy it never read."
    )


def test_the_copy_file_walk_descends_a_symlinked_directory(tmp_path: Path) -> None:
    """The E2-11 security re-pass's deferred LOW, closed by E4-12 and pinned here.

    On the pinned Python, `Path.rglob` does not descend a symlinked directory
    unless it is told to. A directory symlink under `frontend/src/copy/` pointing
    at real copy files therefore shipped those strings with SPEC §4.1 items 4 and
    5 asserted over nothing, and no rule in this module went red — the same
    closed-set-defeated-one-level-out shape as the subdirectory and the `.tsx`
    that came before it, one level further out again.

    The plant is the deferral's own: a real directory outside the walked tree,
    holding a copy file, reached only through a symlink inside it. The file's
    entries are the sample module's, so a walk that finds the link and cannot
    read what is behind it fails here rather than reporting a clean tree.

    **The mutation it kills:** `recurse_symlinks=True` dropped from
    `frontend_copy_files`, which is the state this repository was in until E4-12
    and the state a future tidy-up would restore. **A red here means this module
    is broken, not that the copy is.**
    """
    walked = tmp_path / "copy"
    walked.mkdir()
    (walked / "studentSurvey.ts").write_text(A_COPY_FILE, encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "aggregate.ts").write_text(A_COPY_FILE, encoding="utf-8")
    (walked / "reports").symlink_to(elsewhere, target_is_directory=True)

    found = sorted(path.name for path in frontend_copy_files(walked))
    assert found == ["aggregate.ts", "studentSurvey.ts"], (
        f"The enumeration found {found} in a directory holding one copy file and a symlink to a "
        "directory holding another. Strings behind that link ship to a reader exactly as the "
        "others do, and a walk that stops at the link reports the surface clean over copy it "
        "never opened."
    )


def test_the_coverage_walk_descends_a_symlinked_directory(tmp_path: Path) -> None:
    """The same gap in the second enumeration, which is the half that made it silent.

    The two walks are independent on purpose: one asks what to parse, the other
    asks what was missed. Both used `rglob` without `recurse_symlinks`, so they
    shared one blind spot and **agreed** about a directory neither could see —
    which is the failure mode the coverage rule was built to prevent, arriving
    through the mechanism rather than through the suffix list.

    **The mutation it kills:** `recurse_symlinks=True` dropped from
    `every_file_under_the_copy_directory` alone, which leaves the copy-file walk
    reading a symlinked directory and the coverage rule unable to check it — the
    two enumerations disagreeing in the direction nothing reports. **A red here
    means this module is broken, not that the copy is.**
    """
    walked = tmp_path / "copy"
    walked.mkdir()
    (walked / "studentSurvey.ts").write_text(A_COPY_FILE, encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "catalogue.json").write_text('{"student_survey.heading": "hi"}', encoding="utf-8")
    (walked / "reports").symlink_to(elsewhere, target_is_directory=True)

    seen = sorted(path.name for path in every_file_under_the_copy_directory(walked))
    assert seen == ["catalogue.json", "studentSurvey.ts"], (
        f"The coverage walk enumerated {seen} in a directory holding one copy file and a symlink "
        "to a directory holding a JSON catalogue. A file the coverage walk cannot see is a file it "
        "can never report as unread."
    )

    unread = files_the_collector_did_not_read(walked)
    assert sorted(Path(name).name for name in unread) == ["catalogue.json"], (
        f"The coverage rule reported {unread} over that tree. The JSON behind the symlink is "
        "strings in the copy directory that the collector does not parse, and reaching it is the "
        "whole point of walking the link."
    )


def test_the_copy_file_walk_still_follows_a_symlinked_file(tmp_path: Path) -> None:
    """The near miss beside the fix: a symlinked *file* was never the gap.

    `is_file()` resolves a link, so a copy file reached through a file symlink was
    parsed before E4-12 and must go on being parsed after it. Pinned because the
    other repair for the directory gap — refusing symlinks in the copy tree
    outright, which the deferral offers as an alternative — would take this case
    with it, and a repair that quietly drops a working case is a worse bug than
    the one it fixes.

    **The mutation it kills:** a walk narrowed to `path.is_file() and not
    path.is_symlink()`, which is the obvious spelling of "refuse symlinks" and
    would stop reading a file that ships today. **A red here means this module is
    broken, not that the copy is.**
    """
    walked = tmp_path / "copy"
    walked.mkdir()
    real = tmp_path / "studentSurvey.ts"
    real.write_text(A_COPY_FILE, encoding="utf-8")
    (walked / "studentSurvey.ts").symlink_to(real)

    found = sorted(path.name for path in frontend_copy_files(walked))
    assert found == ["studentSurvey.ts"], (
        f"The enumeration found {found} in a directory whose only entry is a symlink to a copy "
        "file. That file's strings reach a reader, so they have to reach the inventory."
    )


def test_the_coverage_rule_accepts_a_directory_the_collector_read_whole(tmp_path: Path) -> None:
    """The accepted direction of the second enumeration.

    A coverage rule that reported every file as unread would be red over a
    compliant tree and would be deleted rather than fixed.

    **The mutation it kills:** a `display()` that answers differently on the two
    sides of the comparison, which would make every file look unread. **A red
    here means this module is broken, not that the copy is.**
    """
    (tmp_path / "studentSurvey.ts").write_text(A_COPY_FILE, encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "aggregate.tsx").write_text(A_COPY_FILE, encoding="utf-8")

    assert files_the_collector_did_not_read(tmp_path) == [], (
        "The coverage rule reported "
        f"{files_the_collector_did_not_read(tmp_path)} unread in a directory whose every file the "
        "collector parses."
    )


def test_the_coverage_rule_refuses_a_file_the_collector_cannot_read(tmp_path: Path) -> None:
    """The refused direction: a file of an unexpected suffix is red, never invisible.

    The copy directory holds copy. A `.json` catalogue or a `.md` of sample
    sentences there is a shipped surface the collector does not parse, and the
    honest answer is to say so rather than to leave it outside the inventory —
    which is what "sweep the suffixes we thought of" gives you, one level out
    (`docs/mistakes/` — a closed-set guard is defeated one level out).

    **The mutation it kills:** building the coverage rule out of the collector's
    own enumeration, so that it compares an answer with itself and agrees. That
    is the version the review defeated with two files. **A red here means this
    module is broken, not that the copy is.**
    """
    (tmp_path / "studentSurvey.ts").write_text(A_COPY_FILE, encoding="utf-8")
    (tmp_path / "catalogue.json").write_text('{"student_survey.heading": "hi"}', encoding="utf-8")
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "sentences.md").write_text("A sentence.", encoding="utf-8")

    unread = files_the_collector_did_not_read(tmp_path)
    assert sorted(Path(name).name for name in unread) == ["catalogue.json", "sentences.md"], (
        f"The coverage rule reported {unread} over a directory holding one copy file, a JSON "
        "catalogue and a Markdown sample. Both of the latter are strings in the copy directory "
        "that no rule in this module reads."
    )


def test_the_frontend_enumeration_refuses_a_directory_with_no_copy_file(tmp_path: Path) -> None:
    """The refused direction: an empty enumeration is a failure, never a pass.

    Every rule below is of the form "no collected string does X", and an inventory
    that collected nothing satisfies all of them perfectly.

    **The mutation it kills:** returning an empty list instead of refusing, which
    turns this whole module green over a tree with no frontend copy at all. **A
    red here means this module is broken, not that the copy is.**
    """
    empty = tmp_path / "copy"
    empty.mkdir()
    with pytest.raises(CopyInventoryError, match="holds no"):
        frontend_copy_files(empty)


# ---------------------------------------------------------------------------
# The instrument: item 4's sweeps, both directions.
# ---------------------------------------------------------------------------


def test_the_underperforming_sweep_sees_the_word_and_leaves_needs_attention() -> None:
    """Item 4 names both sides, so the sweep is run against both.

    **The mutation it kills:** a vocabulary that no longer matches — a stem
    shortened past the word, a case fold on the wrong side — which turns the rule
    below into a sweep that passes over any copy at all. **A red here means this
    module is broken, not that the copy is.**
    """
    assert forbidden_in(AN_UNDERPERFORMING_SENTENCE, UNDERPERFORMING_VOCABULARY), (
        f"The sweep found nothing in {AN_UNDERPERFORMING_SENTENCE!r}, which carries the one word "
        "item 4 forbids by name."
    )
    assert not forbidden_in(A_NEEDS_ATTENTION_SENTENCE, UNDERPERFORMING_VOCABULARY), (
        f"The sweep flagged {A_NEEDS_ATTENTION_SENTENCE!r}, which is the wording item 4 requires "
        "instead. A sweep that refuses the permitted case makes the rule unimplementable."
    )


def test_the_ranking_sweep_sees_a_ranked_sentence_and_leaves_a_plain_one() -> None:
    """Item 4's third clause: no ranking, no composite scores, no score-sorting.

    **The mutation it kills:** a vocabulary tuple emptied or misspelled, which
    reports every surface clean. **A red here means this module is broken, not
    that the copy is.**
    """
    found = forbidden_in(A_RANKED_SENTENCE, RANKING_VOCABULARY)
    assert found, (
        f"The sweep found nothing in {A_RANKED_SENTENCE!r}, which ranks sections, names a "
        "composite score and sorts by rating in one line."
    )
    assert not forbidden_in(
        A_PLAIN_SENTENCE, RANKING_VOCABULARY
    ), f"The sweep flagged {A_PLAIN_SENTENCE!r}, which says only what to do next."


def test_the_instructor_counting_sweep_sees_a_count_and_leaves_the_surveys_own_question() -> None:
    """Item 4's first clause, and the near miss that decides how it is written.

    "Aggregate language counts sections, never instructors." SPEC §3.2's first
    question asks a student how their instructor was, so a sweep for the word
    would refuse the survey itself. The sweep is for the plural next to a counting
    word, and both directions are run here before the tree is read.

    **The mutation it kills:** widening the pattern to the bare word, which
    reddens the shipped questions; or narrowing it to nothing, which passes over
    an attention card that counts instructors. **A red here means this module is
    broken, not that the copy is.**
    """
    assert instructor_counting_in(
        AN_INSTRUCTOR_COUNT_SENTENCE
    ), f"The sweep found nothing in {AN_INSTRUCTOR_COUNT_SENTENCE!r}, which counts instructors."
    assert instructor_counting_in(
        AN_INSTRUCTOR_MEASURE_SENTENCE
    ), f"The sweep found nothing in {AN_INSTRUCTOR_MEASURE_SENTENCE!r}, which ranks them."
    assert not instructor_counting_in(THE_SURVEYS_OWN_QUESTION), (
        f"The sweep flagged {THE_SURVEYS_OWN_QUESTION!r}, which is SPEC §3.2's own first question. "
        "Item 4 is about counting instructors, not about the word."
    )
    assert not instructor_counting_in(A_NEEDS_ATTENTION_SENTENCE), (
        f"The sweep flagged {A_NEEDS_ATTENTION_SENTENCE!r}, which counts sections — the thing item "
        "4 says aggregate language counts."
    )


# ---------------------------------------------------------------------------
# The instrument: item 5's recognizer and sweep, both directions.
# ---------------------------------------------------------------------------


def test_the_confidentiality_recogniser_sees_the_line_and_leaves_its_neighbour() -> None:
    """The recognizer decides both halves of "exactly once", so it is run both ways.

    A recognizer that matched nothing would report zero on every surface; one that
    matched everything would report two on the first surface with two strings.

    **The mutation it kills:** an emptied or misspelled marker list. **A red here
    means this module is broken, not that the copy is.**
    """
    assert is_confidentiality_copy(A_CONFIDENTIALITY_SENTENCE), (
        f"The recognizer does not read {A_CONFIDENTIALITY_SENTENCE!r} as confidentiality copy, so "
        "the rule below would report the survey's line missing."
    )
    assert is_confidentiality_copy(A_SECOND_CONFIDENTIALITY_SENTENCE), (
        f"The recognizer does not read {A_SECOND_CONFIDENTIALITY_SENTENCE!r} as confidentiality "
        "copy, so a second such sentence could ship beside the first without being counted."
    )
    assert not is_confidentiality_copy(A_PLAIN_SENTENCE), (
        f"The recognizer reads {A_PLAIN_SENTENCE!r} as confidentiality copy. A recognizer this "
        "wide counts two on any surface that says anything at all."
    )


def test_the_recogniser_reads_every_way_an_identity_promise_is_worded() -> None:
    """The words E4-12 adds, and the plain sentences that must stay outside them.

    Every marker before this ticket was written from the student's side of the
    promise — "your name", "identify you" — and the report's line is addressed to
    the person doing the reading instead. So `no names` is here, and so is
    `unidentifiab`.

    **The second one is the security round's correction, and this test is where
    the correction shows.** The first version left unidentifiability language out
    of the vocabulary so that the report's small-N notice would not be counted,
    and this test asserted that absence — which made a blind spot into a rule.
    A vocabulary hole cannot be aimed: it excused one sentence and, with it, any
    other sentence on any surface promising a reader that nobody can be
    identified. Such a sentence would have been a second identity promise counted
    by nothing, anywhere, and no test in this module could have gone red for it.
    The words are read now; the one string that must not be counted is named by
    key in `CONFIDENTIALITY_EXEMPT_KEYS`, and the controls below are what prove
    that exemption is doing the work this test used to.

    Both unidentifiability sentences are asserted to be *read*, deliberately: one
    is phrased as suppression state and one as a standing promise, they say the
    same thing, and a recogniser that told them apart by wording would be back to
    deciding item 5 by how a sentence happens to be written. None is quoted from
    the report (`docs/MISTAKES.md` entry 3).

    **The mutations it kills:** `no names` dropped from the tuple, which leaves
    the report's line uncounted and the surface reading zero; `unidentifiab`
    dropped or shortened past the word, which restores the global blind spot; and
    a recogniser widened until it reads an ordinary explanation as an identity
    promise, which reddens the report the day the credit-rule note ships beside
    its line. **A red here means this module is broken, not that the copy is.**
    """
    read = (
        A_READER_FACING_CONFIDENTIALITY_SENTENCE,
        A_SUPPRESSION_STATE_SENTENCE,
        AN_UNIDENTIFIABILITY_PROMISE,
    )
    unread = [sentence for sentence in read if not is_confidentiality_copy(sentence)]
    assert not unread, (
        f"The recognizer does not read {unread} as confidentiality copy. Each of them tells a "
        "reader that nobody can be identified from what is shown, which is what item 5's sentence "
        "is; a wording the recogniser cannot see is a second promise counted on no surface at all."
    )
    assert not is_confidentiality_copy(A_PLAIN_SENTENCE), (
        f"The recognizer reads {A_PLAIN_SENTENCE!r} as confidentiality copy. A recognizer this "
        "wide counts two on any surface that says anything at all."
    )
    assert not is_confidentiality_copy(AN_EXPLANATORY_SENTENCE), (
        f"The recognizer reads {AN_EXPLANATORY_SENTENCE!r} as confidentiality copy. Explaining how "
        "a participation score is worked out is not an identity promise, and a recogniser that "
        "counts it reddens the report the day the credit-rule note ships beside its line."
    )


def test_the_count_skips_the_named_exempt_key_and_counts_the_same_words_elsewhere() -> None:
    """The exemption is one key, not a wording and not a surface — both directions.

    This is what replaced the vocabulary hole, so this is where its reach is
    pinned. The same unidentifiability promise is planted three times: under the
    exempt key, under a second key on the same surface, and on a different surface
    entirely. Only the first is skipped.

    Without the second plant the exemption could be widened to the report surface
    or to the prefix and nothing here would notice, which is the failure the
    original design had one level up: an exemption that is broader than the string
    it was written for excuses strings nobody weighed.

    **The mutations it kills:** an exemption matched on the key's prefix or on its
    surface rather than on the key; and the skip applied inside
    `is_confidentiality_copy`, which would put the hole back into the recogniser
    that every surface's count reads. **A red here means this module is broken,
    not that the copy is.**
    """
    exempt_key = next(iter(CONFIDENTIALITY_EXEMPT_KEYS))
    beside_it = f"{prefix_of(exempt_key)}.a_second_notice"
    inventory = a_governed_inventory(
        CopyString(exempt_key, A_SUPPRESSION_STATE_SENTENCE, SYNTHETIC),
        CopyString(beside_it, AN_UNIDENTIFIABILITY_PROMISE, SYNTHETIC),
        CopyString("student_survey.a_second_notice", AN_UNIDENTIFIABILITY_PROMISE, SYNTHETIC),
    )

    assert is_confidentiality_copy(A_SUPPRESSION_STATE_SENTENCE), (
        "The recognizer does not read the exempt key's kind of sentence at all, so the exemption "
        "below skips a string nothing was counting and this control proves nothing."
    )

    counted = sorted(string.key for string in confidentiality_strings(inventory, REPORT))
    assert counted == sorted([beside_it, CONFIDENTIALITY_KEY_OF_SURFACE[REPORT]]), (
        f"On a report surface carrying its standing line, the exempt key, and a second notice in "
        f"the same words under a different key, the count read {counted}.\n"
        "\n"
        f"The exemption is {exempt_key!r} and nothing else: a second sentence beside it says the "
        "same thing under a key nobody weighed, and item 5 counts it."
    )

    elsewhere = sorted(string.key for string in confidentiality_strings(inventory, SURVEY))
    assert elsewhere == sorted(
        ["student_survey.a_second_notice", CONFIDENTIALITY_KEY_OF_SURFACE[SURVEY]]
    ), (
        f"On the survey surface, the count read {elsewhere} with an unidentifiability promise "
        "planted beside its line. The exemption belongs to one key on one surface; a promise "
        "worded that way anywhere else is a second line."
    )


def test_removing_an_exemption_row_puts_its_key_back_in_the_count() -> None:
    """The exemption is load-bearing, proven by taking it away rather than by saying so.

    `confidentiality_strings` takes the exemption map as a parameter for exactly
    this: run over the **shipped** inventory with no exemptions at all, the report
    surface must count more than one, and the extra one must be the exempt key.

    Two things follow, and both matter. The exemption is not decoration — remove
    the row and the invariant-marked exactly-once rule goes red naming that key,
    which is the mutation that rule's docstring now names. And the marker is not
    blind: it finds a real shipped string rather than only the sentences this
    module writes for itself (`docs/MISTAKES.md` entry 35, in the collector's own
    currency rather than a parallel grep).

    **If this reds because the exempt key is counted even without the exemption**,
    the shipped small-N body no longer carries unidentifiability language, and the
    answer is to delete the exemption row rather than to keep an excuse for a
    string nothing was excusing (`docs/MISTAKES.md` entry 14). **A red here means
    the exemption and the copy have come apart, not that the copy is wrong.**
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this control ran over nothing."

    exempt_key = next(iter(CONFIDENTIALITY_EXEMPT_KEYS))
    surface = surface_of(exempt_key)
    assert surface is not None, (
        f"{exempt_key!r} belongs to no governed surface, so exempting it from a per-surface count "
        "exempts it from nothing."
    )

    with_the_exemption = [string.key for string in confidentiality_strings(inventory, surface)]
    without_it = [string.key for string in confidentiality_strings(inventory, surface, exempt={})]
    assert sorted(set(without_it) - set(with_the_exemption)) == [exempt_key], (
        f"With every exemption removed, the {surface} surface counted {sorted(without_it)}; with "
        f"them it counts {sorted(with_the_exemption)}. The difference should be exactly "
        f"{[exempt_key]}.\n"
        "\n"
        "If the difference is empty, that shipped string no longer carries any word the recogniser "
        "reads: the exemption is excusing nothing and belongs deleted rather than kept. If it "
        "holds something else, a second string is being skipped by a row that does not name it."
    )


def test_the_iconography_sweep_sees_a_lock_and_a_shield_and_leaves_plain_words() -> None:
    """Item 5: "in plain words, no shield or lock iconography".

    **The mutation it kills:** an emptied code-point tuple, or one holding the
    wrong characters, which reports every surface plain. **A red here means this
    module is broken, not that the copy is.**
    """
    assert iconography_in(A_LOCKED_SENTENCE), (
        "The sweep found no lock in a sentence that begins with one, so the rule below would pass "
        "over any icon at all."
    )
    assert iconography_in(
        A_SHIELDED_SENTENCE
    ), "The sweep found no shield in a sentence that begins with one."
    assert not iconography_in(A_CONFIDENTIALITY_SENTENCE), (
        f"The sweep flagged {A_CONFIDENTIALITY_SENTENCE!r}, which is item 5's plain words and "
        "carries no icon."
    )


# ---------------------------------------------------------------------------
# The instrument: the surface model, over synthetic inventories.
# ---------------------------------------------------------------------------


def test_the_surface_check_accepts_an_inventory_whose_prefixes_are_all_governed() -> None:
    """The accepted direction of the totality pair.

    A check that refused everything would be red over a compliant tree, and the
    rule would be deleted rather than fixed.

    **The mutation it kills:** a `surface_of` that answers `None` for a governed
    prefix — a lookup on the whole key rather than on its first segment, say.
    **A red here means this module is broken, not that the copy is.**
    """
    inventory = a_governed_inventory()
    assert not ungoverned_keys(inventory), (
        f"The check reported {ungoverned_keys(inventory)} ungoverned in an inventory built out of "
        f"the governance map itself ({sorted(GOVERNED_SURFACES)})."
    )
    assert not prefixes_that_collect_nothing(inventory), (
        f"The check reported {prefixes_that_collect_nothing(inventory)} empty in an inventory "
        "carrying one string per governed prefix."
    )


def test_the_surface_check_refuses_a_key_whose_prefix_no_surface_governs() -> None:
    """Acceptance criterion 3, in test: a surface that registered nowhere is red.

    E4 added the report, the gradebook and the unknown-address screen; E9 adds
    the leadership roll-ups. Until a row for one exists in `GOVERNED_SURFACES`,
    its strings are swept by nothing and counted toward no surface's
    confidentiality line — so the inventory has to say so rather than quietly
    ignore them.

    The planted prefix is a surface that does not exist yet, deliberately.
    It was `report.` until E4-12, and the day the report became a governed
    surface a control planting a report-shaped key would have been demonstrating
    the opposite of what it says.

    **The mutation it kills:** an `ungoverned_keys` that filters unknown prefixes
    out instead of reporting them, which is exactly how an unregistered surface
    ships unnoticed. **A red here means this module is broken, not that the copy
    is.**
    """
    inventory = a_governed_inventory(
        CopyString("leadership_rollup.heading", A_PLAIN_SENTENCE, SYNTHETIC)
    )
    assert ungoverned_keys(inventory) == ["leadership_rollup.heading"], (
        f"The check reported {ungoverned_keys(inventory)} over an inventory carrying a "
        "`leadership_rollup.`-prefixed key, which no row in the governance map claims."
    )


def test_the_surface_check_refuses_a_governed_prefix_that_collects_nothing() -> None:
    """The other half of totality: an empty surface is a failure, not a pass.

    The ticket says so in as many words — "the collector proves non-emptiness per
    registered surface (an empty surface is a failure, not a pass)". A surface
    whose strings stopped being collected passes every vocabulary rule there is.

    **The mutation it kills:** a totality check written in one direction only,
    which stays green when a whole copy module drops out of the enumeration.
    **A red here means this module is broken, not that the copy is.**
    """
    for prefix in GOVERNED_SURFACES:
        inventory = without_prefix(a_governed_inventory(), prefix)
        assert prefixes_that_collect_nothing(inventory) == [prefix], (
            f"With every {prefix!r} string removed, the check reported "
            f"{prefixes_that_collect_nothing(inventory)} rather than {[prefix]}."
        )


def test_the_confidentiality_count_accepts_a_surface_with_exactly_one_line() -> None:
    """The accepted direction of item 5's pair, on every surface that carries a line.

    **Run over `CONFIDENTIALITY_KEY_OF_SURFACE` rather than over the survey**,
    because that map held one row until E4-12 and a control written around the
    one row proves the survey's case forever while a surface added later has
    nothing under it. The day the report's row landed, this control covered it
    without being edited.

    **The mutation it kills:** a counter that reads the whole inventory rather
    than one surface's strings, which counts the report's line against the survey
    now that there are two. **A red here means this module is broken, not that
    the copy is.**
    """
    assert CONFIDENTIALITY_KEY_OF_SURFACE, (
        "No surface carries a confidentiality line, so this control ran over nothing and item 5 is "
        "asserted of nobody."
    )
    for surface, expected in CONFIDENTIALITY_KEY_OF_SURFACE.items():
        found = [string.key for string in confidentiality_strings(a_governed_inventory(), surface)]
        assert found == [expected], (
            f"The counter read {found} on a synthetic {surface} surface carrying one "
            f"confidentiality line, {expected!r}."
        )


def test_the_confidentiality_count_refuses_a_surface_with_no_line() -> None:
    """The zero direction: item 5 says "exactly once", and none is not once.

    Each line-carrying surface in turn, for the reason the control above gives.

    **The mutation it kills:** an assertion written as "no more than one", which
    is green on a surface that tells a reader nothing about what happens to a
    student's identity. **A red here means this module is broken, not that the
    copy is.**
    """
    assert (
        CONFIDENTIALITY_KEY_OF_SURFACE
    ), "No surface carries a confidentiality line, so this control ran over nothing."
    for surface, key in CONFIDENTIALITY_KEY_OF_SURFACE.items():
        inventory = without_key(a_governed_inventory(), key)
        assert confidentiality_strings(inventory, surface) == [], (
            f"With {key!r} removed, the counter still read "
            f"{confidentiality_strings(inventory, surface)} on {surface}. The rule below compares "
            "against one, so a counter that cannot reach zero cannot fail in this direction."
        )


def test_the_confidentiality_count_reads_zero_on_a_surface_that_owes_no_line() -> None:
    """The accepted direction of D5's second map: a no-line surface carries none.

    The gradebook is two strings rendered by another product's UI, and the
    unknown-address screen shows nobody's data. Item 5's sentence has no subject
    on either, so what the rule requires of them is zero — and a counter that
    could not reach zero on a surface built out of plain strings would make that
    rule unsatisfiable rather than satisfied.

    **The mutation it kills:** a recogniser widened until it reads any sentence
    as confidentiality copy, which reports a line on a surface that has none and
    reddens the no-line rule against correct copy. **A red here means this module
    is broken, not that the copy is.**
    """
    assert SURFACES_WITH_NO_CONFIDENTIALITY_LINE, (
        "No surface is recorded as owing no confidentiality line, so this control ran over "
        "nothing."
    )
    inventory = a_governed_inventory()
    for surface in SURFACES_WITH_NO_CONFIDENTIALITY_LINE:
        found = [string.key for string in confidentiality_strings(inventory, surface)]
        assert found == [], (
            f"The counter read {found} on a synthetic {surface} surface whose every string is the "
            "plain sentence this module writes for the purpose."
        )


def test_the_confidentiality_count_reports_a_line_on_a_surface_that_owes_none() -> None:
    """The refused direction of the same map, which is what makes the rule non-vacuous.

    A rule of the form "these surfaces carry no confidentiality string" is
    satisfied perfectly by a counter that finds nothing anywhere
    (`docs/MISTAKES.md` entry 3). So one is planted on each no-line surface and
    the counter is required to name it. This is also the shape the real defect
    takes: a reassuring sentence added to a gradebook label or to the fallback
    screen is a promise made where nothing keeps it, and a second copy of the
    identity promise that no rule counts is how the promise starts to disagree
    with itself.

    **The mutation it kills:** the no-line rule written over a counter that reads
    only the surfaces in `CONFIDENTIALITY_KEY_OF_SURFACE`, which cannot see these
    surfaces at all. **A red here means this module is broken, not that the copy
    is.**
    """
    prefixes = [
        prefix
        for prefix, surface in GOVERNED_SURFACES.items()
        if surface in SURFACES_WITH_NO_CONFIDENTIALITY_LINE
    ]
    assert prefixes, (
        "No prefix maps to a surface that owes no confidentiality line, so this control planted "
        "nothing and proved nothing."
    )
    for prefix in prefixes:
        surface = GOVERNED_SURFACES[prefix]
        planted = f"{prefix}.reassurance"
        inventory = a_governed_inventory(
            CopyString(planted, A_SECOND_CONFIDENTIALITY_SENTENCE, SYNTHETIC)
        )
        found = [string.key for string in confidentiality_strings(inventory, surface)]
        assert found == [planted], (
            f"With a confidentiality sentence planted at {planted!r}, the counter read {found} on "
            f"the {surface} surface."
        )


def test_the_surface_split_places_every_governed_surface_in_exactly_one_map() -> None:
    """The instrument behind D5's totality rule, run over planted maps in both directions.

    The rule below asks the real maps this question, and a green over the real
    maps says nothing about whether the question can come back false — a reader
    that answered "all placed" for every input would report the tree correct
    whatever the maps held (`docs/MISTAKES.md` entry 3).

    Three planted shapes, because there are three ways to get it wrong: a surface
    in neither map, which is the one that arrives by omission when somebody adds
    a governance row and stops; a surface in both, which is two answers to one
    question; and a correct pair, which must come back clean or the rule is red
    against a tree that is right.

    **The mutation it kills:** a totality check that reads only one of the two
    maps, which cannot see a surface placed twice; and one that treats an unknown
    surface as no-line by default, which is the defaulting the two maps exist to
    stop. **A red here means this module is broken, not that the copy is.**
    """
    governed = {"a_prefix": "placed", "b_prefix": "unplaced", "c_prefix": "twice"}
    with_a_line = {"placed": "a_prefix.line", "twice": "c_prefix.line"}
    without_a_line = {"twice": "a stated reason"}

    assert surfaces_placed_in_neither_map(governed, with_a_line, without_a_line) == ["unplaced"], (
        "The reader reported "
        f"{surfaces_placed_in_neither_map(governed, with_a_line, without_a_line)} over planted maps "
        "in which exactly one governed surface is claimed by neither."
    )
    assert surfaces_placed_in_both_maps(with_a_line, without_a_line) == ["twice"], (
        f"The reader reported {surfaces_placed_in_both_maps(with_a_line, without_a_line)} over "
        "planted maps in which exactly one surface is claimed by both."
    )

    clean_without = {"unplaced": "a stated reason"}
    assert surfaces_placed_in_neither_map(governed, with_a_line, clean_without) == [], (
        "The reader reported "
        f"{surfaces_placed_in_neither_map(governed, with_a_line, clean_without)} over planted maps "
        "that place every governed surface. A reader that cannot come back clean makes the rule "
        "below unsatisfiable."
    )


def test_the_confidentiality_count_refuses_a_surface_with_two_lines() -> None:
    """The two direction: a second sentence somewhere else on the same surface.

    This is how item 5 is broken in practice — a helpful reassurance added to a
    heading or to a refusal, beside the line the submit bar already carries.

    **The mutation it kills:** an assertion written as "at least one", which is
    green however many times the surface repeats itself. **A red here means this
    module is broken, not that the copy is.**
    """
    inventory = a_governed_inventory(
        CopyString("submit.privacy_note", A_SECOND_CONFIDENTIALITY_SENTENCE, SYNTHETIC)
    )
    found = sorted(string.key for string in confidentiality_strings(inventory, SURVEY))
    assert found == ["student_survey.confidentiality", "submit.privacy_note"], (
        f"With a second confidentiality sentence on the survey surface, the counter read {found}. "
        "Both are on the same surface — one from the frontend copy file and one from the copy "
        "registry — and item 5 counts per surface, not per source."
    )


# ---------------------------------------------------------------------------
# The canaries: the collector must find what it certainly can see, before its
# silence about anything else counts (`docs/MISTAKES.md` entry 35).
# ---------------------------------------------------------------------------


def test_the_collector_finds_the_two_backend_keys_the_work_order_spells() -> None:
    """The backend half of the collector, proved on keys that certainly exist.

    `student.not_a_student` and `submit.classifier_down` are the two key names
    E2-08 settles by name, and `tests/unit/test_the_submit_paths_copy_is_
    externalised.py` requires the registry to publish both. If the collector
    cannot see them, every rule below is a statement about an inventory that is
    missing the registry.

    Presence and non-emptiness only, never the sentence: rewording a refusal must
    not redden the inventory (`docs/MISTAKES.md` entry 19).

    **The mutation it kills:** a collector that reads the wrong attribute off a
    `CopyEntry`, or that walks no modules at all. **A red here means this module
    is broken, or the registry has lost a key that E2-08 asserts is there.**
    """
    collected = {string.key: string.text for string in collect_backend_copy()}
    missing = [key for key in (NOT_A_STUDENT_KEY, CLASSIFIER_DOWN_KEY) if key not in collected]
    assert (
        not missing
    ), f"The collector read no {missing} out of `{COPY_PACKAGE}`. It read {sorted(collected)}."
    blank = [key for key in (NOT_A_STUDENT_KEY, CLASSIFIER_DOWN_KEY) if not collected[key].strip()]
    assert not blank, (
        f"The collector read {blank} as empty strings. An empty text satisfies every vocabulary "
        "rule in this module."
    )


def test_the_collector_finds_the_two_frontend_keys_the_survey_screen_ships() -> None:
    """The frontend half, proved on the survey's heading and its confidentiality line.

    E2-10 put both in `frontend/src/copy/studentSurvey.ts`. The heading is an
    ordinary entry, so its absence means the parse failed rather than that the
    copy changed; the confidentiality line is item 5's own subject, so its absence
    is the rule's business as well as the collector's.

    Presence and non-emptiness only, never the sentence itself.

    **The mutation it kills:** a parser that reads the first entry and stops, or
    one pointed at a directory that no longer holds the survey's copy. **A red
    here means this module is broken, or a key the survey screen renders has been
    renamed without this inventory being told.**
    """
    collected = {
        string.key: string.text for string in collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    }
    wanted = (SURVEY_HEADING_KEY, CONFIDENTIALITY_KEY_OF_SURFACE[SURVEY])
    missing = [key for key in wanted if key not in collected]
    assert not missing, (
        f"The parse of {display(FRONTEND_COPY_DIRECTORY)} published no {missing}. It published "
        f"{sorted(collected)}."
    )
    blank = [key for key in wanted if not collected[key].strip()]
    assert not blank, f"The parse read {blank} as empty strings."


def test_the_collector_finds_the_two_report_keys_the_monday_screen_ships() -> None:
    """The report's half of the same canary, and criterion 7 in its own currency.

    Every rule this module states about the report surface is a statement about
    strings this collector returned, and the four report copy modules shipped
    outside the walked copy directory — beside their components, where the walk
    does not look. A rule sweeping an inventory that holds none of the report's
    strings is green over a whole screen (`docs/MISTAKES.md` entry 35: require
    the guard to *find* the thing on a subject that certainly has it).

    Two keys from two different report copy modules, so a single file arriving
    while the other three stay outside is not enough to satisfy this. The
    small-N body is an ordinary entry, so its absence means the parse or the
    layout has failed; `comments_note` is item 5's own subject on this surface,
    so its absence is the rule's business as well as the collector's.

    Presence and non-emptiness only, never the sentence: E4-10 and E4-11 own
    those wordings and rewording either must not redden the inventory
    (`docs/MISTAKES.md` entry 19).

    **The mutation it kills:** a report copy module left outside
    `frontend/src/copy/`, or renamed out of the walk. **A red here means the
    report's copy is not collected, which is the state E4-12 exists to end.**
    """
    collected = {
        string.key: string.text for string in collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    }
    wanted = (REPORT_SMALL_N_KEY, CONFIDENTIALITY_KEY_OF_SURFACE[REPORT])
    missing = [key for key in wanted if key not in collected]
    assert not missing, (
        f"The parse of {display(FRONTEND_COPY_DIRECTORY)} published no {missing}.\n"
        "\n"
        "The Monday report's strings live in four copy modules. Until they are inside the walked "
        "copy directory, SPEC §4.1 items 4 and 5 are asserted over none of them and every rule "
        "below passes over the largest user-facing surface this product has."
    )
    blank = [key for key in wanted if not collected[key].strip()]
    assert not blank, (
        f"The parse read {blank} as empty strings. An empty text satisfies every vocabulary rule "
        "in this module, and an empty confidentiality line is a promise nobody makes."
    )


def test_the_collector_finds_the_two_gradebook_keys_that_ship_into_the_lms() -> None:
    """The gradebook's half, through the backend import path rather than a file parse.

    SPEC §3.4 ships two strings into somebody else's user interface: the AGS line
    item's label and the per-week ledger line in each posted score's comment. They
    are Pulse's words, written by this project, read by an instructor; that the
    surface rendering them belongs to another product is a fact about rendering
    rather than about authorship, and it is not a reason for items 4 and 5 to stop
    applying. The carried entry from E3 is closed by their being collected.

    Presence and non-emptiness only. The texts themselves are pinned byte-for-byte
    by the grading and AGS suites — that is what stops them drifting — and
    repeating either here would be a second copy of a sentence for the two to
    disagree over (`docs/MISTAKES.md` entry 19).

    **The mutation it kills:** the gradebook copy module dropped from the registry
    enumeration, or its constants left as literals in `app/lti/ags.py` and
    `app/services/grading.py` with a copy entry beside them that nothing reads.
    **A red here means the gradebook's strings are not collected, which is the
    state E4-12 exists to end.**
    """
    collected = {string.key: string.text for string in collect_backend_copy()}
    wanted = (GRADEBOOK_LABEL_KEY, GRADEBOOK_LEDGER_KEY)
    missing = [key for key in wanted if key not in collected]
    assert not missing, (
        f"The collector read no {missing} out of `{COPY_PACKAGE}`. It read {sorted(collected)}.\n"
        "\n"
        "SPEC §3.4's line item label and ledger line are strings this product writes and an "
        "instructor reads. The E3 carried entry closes when the inventory collects them or records "
        "why the gradebook is not a governed surface."
    )
    blank = [key for key in wanted if not collected[key].strip()]
    assert not blank, f"The collector read {blank} as empty strings."


def test_the_collector_finds_the_two_refusals_the_report_api_answers() -> None:
    """The report surface's backend half, through the registry's own reader.

    `docs/tickets/e4/deferred.md`, "The report API's two refusal sentences sit
    outside the copy registry": `app.api.instructor` answers a refusal to a
    section outside the session's teaching set or absent altogether, and another
    to a course week the section has no window for. Both were module constants,
    which the inventory cannot see — so the aggregate-language rule never read
    them, and neither did the confidentiality count. That entry's first clause is
    the one this canary is about: both sentences are entries in an `app.copy`
    module under a prefix the governance map claims for the report surface.

    **The two keys are on the report surface and are not its confidentiality
    line.** They say what is not there to read, not what happens to anybody's
    identity, so the surface goes on carrying exactly one line and these two are
    swept for item 4's vocabulary along with everything else.

    Presence and non-emptiness only, never the sentences. The router's own tests,
    the component tests and `tests/e2e/instructor-report.spec.ts` each transcribe
    the text as the proof that a refactor did not change it; a fourth copy here
    would be one more thing to reword (`docs/MISTAKES.md` entry 19).

    **The mutation it kills:** the report's copy module left out of the registry
    enumeration, or its entries spelled under a prefix no surface claims. **A red
    here means the report API's refusals are not collected, which is the state
    this ticket exists to end.**
    """
    collected = {string.key: string.text for string in collect_backend_copy()}
    wanted = (REPORT_SECTION_UNAVAILABLE_KEY, REPORT_WEEK_UNAVAILABLE_KEY)
    missing = [key for key in wanted if key not in collected]
    assert not missing, (
        f"The collector read no {missing} out of `{COPY_PACKAGE}`. It read {sorted(collected)}.\n"
        "\n"
        "Both sentences are answered to an instructor by `app.api.instructor`, and until they are "
        "entries in the registry the vocabulary sweeps in this module pass over them entirely."
    )
    blank = [key for key in wanted if not collected[key].strip()]
    assert not blank, (
        f"The collector read {blank} as empty strings. A refusal with no words is a 404 that "
        "explains nothing, and an empty text satisfies every vocabulary rule in this module."
    )


def test_the_report_apis_refusal_constants_say_what_the_registry_says() -> None:
    """The deferred entry's second clause, as far as two live objects can carry it.

    > **Done when:** both sentences are entries in an `app.copy` module under a
    > prefix the inventory's governance map claims for the report surface,
    > `app.api.instructor` looks them up by key rather than holding them, and the
    > items-4-and-5 vocabulary gate has been seen running over them.

    The canary above is the first clause. This is what stops the second from
    arriving as two copies of one sentence: the router's constants and the
    registry's entries are read as they are, at run time, and required to agree.
    A registry entry the router does not use is a governed string nobody serves,
    and a router constant the registry does not match is the ungoverned sentence
    this entry was opened about, wearing a copy of the right words.

    **Read, never transcribed.** Both sides of the comparison are live objects;
    nothing here holds the sentences, so rewording a refusal is one edit in the
    registry rather than an edit and a red (`docs/MISTAKES.md` entry 19).

    **The import is inside the body on purpose.** Several tests in this module
    are `invariant`-marked and run in CI's isolated §4.1 pass, which collects
    this whole file with no database; importing a router at module scope would
    put an application import into that pass for the sake of one unmarked test.
    This test is not marked for the same reason — it is the deferral's clause,
    not a §4.1 rule.

    **What this cannot say, stated rather than implied.** Equal text does not
    prove a lookup: a constant re-typed by hand is equal to the entry on the day
    it is written. What it proves is that the two cannot drift apart afterwards,
    which is the failure the entry describes. That the router reads the registry
    rather than repeating it is the settled shape of the change (the constants
    become reads of the entries, as `app/lti/ags.py` and `app/services/grading.py`
    do for the gradebook), and it is held by the diff.

    **The mutations it kills:** a registry entry added beside a router constant
    that goes on holding its own sentence, which is the shape that closes the
    entry on paper and changes nothing; and either sentence reworded on one side
    only. **A red here means the router and the registry disagree about what an
    instructor is told, or one of the two does not exist yet.**
    """
    collected = {string.key: string.text for string in collect_backend_copy()}
    missing = [key for key in REPORT_API_REFUSALS.values() if key not in collected]
    assert not missing, (
        f"The registry publishes no {missing}, so there is nothing for the router's constants to "
        f"agree with. `{REPORT_API_MODULE}` holds the sentences itself until those entries exist, "
        "which is the state `docs/tickets/e4/deferred.md` records."
    )

    router = importlib.import_module(REPORT_API_MODULE)
    absent = [name for name in REPORT_API_REFUSALS if not hasattr(router, name)]
    assert not absent, (
        f"`{REPORT_API_MODULE}` publishes no {absent}. Those constants are where the refusals live, "
        "and the settled shape of this change is that each becomes a read of its registry entry "
        "rather than disappearing. If the router now looks an entry up at the raise site instead, "
        "that is a different shape from the one this was written against and the ruling needs "
        "revisiting rather than this assertion being widened."
    )

    disagreeing = {
        name: (getattr(router, name), collected[key])
        for name, key in REPORT_API_REFUSALS.items()
        if getattr(router, name) != collected[key]
    }
    assert not disagreeing, (
        f"These constants in `{REPORT_API_MODULE}` do not say what their registry entries say: "
        f"{disagreeing}.\n"
        "\n"
        "Two copies of one refusal is the state the deferred entry was opened about: the inventory "
        "sweeps the entry, the instructor reads the constant, and nothing holds them together. The "
        "repair is for the constant to read the entry, not for the second copy to be corrected."
    )


# ---------------------------------------------------------------------------
# The rules. Every one of these is marked, and every docstring names the item it
# asserts.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_no_shipped_string_calls_a_section_underperforming() -> None:
    """SPEC §4.1 item 4, asserted from E2 as that item's footnote says it is.

    > 4. Aggregate language counts sections, never instructors; "needs attention,"
    >    never "underperforming"; no ranking, no composite scores, and no
    >    score-sorting anywhere. *(Asserted from **E2**, when the copy-inventory
    >    test first collects shipped user-facing strings; the vocabulary rule is
    >    checked globally from then on.)*

    §5.6 states the same rule from the other end: "Non-goals, permanently: no
    ranking, no composite scores, no 'underperforming.'" This is the clause the
    item spells as a word, so it is asserted as one, over every string both
    sources publish rather than over the surface that happens to be built.

    **The mutation it kills:** the word planted in any shipped sentence — a
    refusal, a bounce, a heading. **What makes it non-vacuous:** the sweep's own
    control above, and the collector's canaries; both halves of the inventory
    refuse to be empty.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    found = offenders(inventory, UNDERPERFORMING_VOCABULARY)
    assert not found, (
        f"These shipped strings call something underperforming: {found}. SPEC §4.1 item 4 is a "
        "hard visibility invariant and names this word directly: 'needs attention,' never "
        "'underperforming'."
    )


@pytest.mark.invariant
def test_no_shipped_string_ranks_sorts_or_scores_what_it_shows() -> None:
    """SPEC §4.1 item 4's third clause, over every collected string.

    > no ranking, no composite scores, and no score-sorting anywhere

    "Anywhere" is why this sweeps both sources and every prefix rather than the
    surfaces that show numbers: a ranked sentence reaches a reader through copy
    exactly as it would through a chart, and no chart test would ever see it.

    **The mutation it kills:** a leaderboard sentence, a "highest rated first"
    ordering hint, or a composite score named in any shipped string. **What makes
    it non-vacuous:** the sweep's control above, and the non-empty inventory.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    found = offenders(inventory, RANKING_VOCABULARY)
    assert not found, (
        f"These shipped strings rank, sort or score: {found}. SPEC §4.1 item 4 forbids all three "
        "anywhere, and SPEC §5.6 records the same as a permanent non-goal."
    )


@pytest.mark.invariant
def test_no_shipped_string_counts_instructors() -> None:
    """SPEC §4.1 item 4's first clause, as far as text mechanically carries it.

    > Aggregate language counts sections, never instructors

    What is asserted is the noun: no shipped string counts, ranks, sorts or lists
    *instructors*. What cannot be asserted from text is stated instead — a
    sentence that counts instructors without naming them ("12 need attention" over
    a list of people) reads as permitted here, and that half stays a review
    question.

    **The mutation it kills:** an attention line written about instructors rather
    than about sections. **The near miss that must stay green:** SPEC §3.2's own
    first question, which asks a student about their instructor and is the reason
    this sweep reads counts rather than the word. **What makes it non-vacuous:**
    the sweep's control above, run in both directions.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    found = {
        string.key: (string.text, counted)
        for string in inventory
        if (counted := instructor_counting_in(string.text))
    }
    assert not found, (
        f"These shipped strings count or measure instructors: {found}. SPEC §4.1 item 4: aggregate "
        "language counts sections, never instructors. If one of these is a false positive, that is "
        "a dispute about how the clause is checked rather than a term to drop."
    )


@pytest.mark.invariant
def test_each_line_carrying_surface_carries_exactly_one_confidentiality_line() -> None:
    """SPEC §4.1 item 5, asserted from E2 as that item's footnote says it is.

    > 5. Confidentiality copy appears exactly once per surface (survey: once per
    >    screen, in the submit area), in plain words, no shield or lock
    >    iconography. *(Asserted from **E2** via the same copy-inventory test —
    >    the survey is the first governed surface, and the inventory grows with
    >    each UI epic.)*

    Exactly once, in both directions: zero is a surface that never says what
    happens to a student's answers, and two is a surface that says it twice in two
    different sets of words, which is how a promise starts to disagree with
    itself. The count is per surface and not per source — the survey's strings
    arrive from the frontend copy file and from the copy registry both, and the
    report's arrive from four copy modules that render as one screen.

    **This rule iterates `CONFIDENTIALITY_KEY_OF_SURFACE`, not every governed
    surface**, because E4-12 governs two surfaces that owe no line and the version
    that iterated `GOVERNED_SURFACES.values()` would have demanded an identity
    promise from an LMS gradebook. Those surfaces are held to zero by the rule
    below rather than exempted; between the two, every governed surface has its
    item-5 count asserted, and the totality rule requires every surface to be in
    exactly one of the two maps so that neither rule can lose one.

    Placement is asserted as far as an inventory can carry it: the one match is
    the key the map names. Where that string sits in the DOM is the end-to-end
    specs' — E2-10's for the survey, E4-11's for the report.

    **One string is counted out, by key**: `CONFIDENTIALITY_EXEMPT_KEYS` names
    the report's small-N notice with the reason it is not the surface's standing
    line. The exemption is a named string with an argument beside it rather than
    a word left out of the recogniser, and the difference is the whole of what
    the security round changed: a missing word excuses every sentence anywhere
    that happens to be phrased that way, and nothing in this module could have
    gone red for one.

    **The mutations it kills:** a second confidentiality sentence added anywhere
    on a surface, including one phrased as unidentifiability, which the
    recogniser reads now; the one line removed; and **an exemption row deleted
    while the string it named still carries the words** — that key comes back
    into the count and this rule reds naming it, which is the direction
    `test_removing_an_exemption_row_puts_its_key_back_in_the_count` demonstrates
    against the shipped inventory. The reverse, an exemption row added to silence
    a red, is a visible line in a diff carrying a reason somebody has to write.
    **What makes it non-vacuous:** the recognizer's controls in both directions,
    the zero and two synthetic controls run over every line-carrying surface, the
    exemption's own key-not-surface control, and the collector canaries that
    require each of these keys to be collected at all.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    assert CONFIDENTIALITY_KEY_OF_SURFACE, (
        "No surface is recorded as carrying a confidentiality line, so item 5 is asserted of "
        "nothing at all."
    )

    counted = {
        surface: confidentiality_strings(inventory, surface)
        for surface in CONFIDENTIALITY_KEY_OF_SURFACE
    }
    wrong = {
        surface: sorted(string.key for string in found)
        for surface, found in counted.items()
        if len(found) != 1
    }
    assert not wrong, (
        f"These governed surfaces do not carry exactly one confidentiality string: {wrong}.\n"
        "\n"
        "SPEC §4.1 item 5: confidentiality copy appears exactly once per surface. None means the "
        "surface never says what happens to a student's answers; two means it says so twice, in "
        "two sets of words that can drift apart. The recognizer's vocabulary is in "
        "`CONFIDENTIALITY_MARKERS`, and a shipped sentence it cannot read is a dispute about the "
        "recognizer rather than a missing line."
    )

    for surface, expected in CONFIDENTIALITY_KEY_OF_SURFACE.items():
        keys = [string.key for string in counted.get(surface, [])]
        assert keys == [expected], (
            f"The {surface} surface's confidentiality copy is {keys} rather than {[expected]}. "
            "This module counts the string rather than the rendering, so the entry named in "
            "`CONFIDENTIALITY_KEY_OF_SURFACE` is the one that has to be the match."
        )


@pytest.mark.invariant
def test_no_surface_recorded_as_owing_no_confidentiality_line_carries_one() -> None:
    """SPEC §4.1 item 5 over the other half of the surface model.

    Two governed surfaces owe no line, each for a reason written down beside it:
    the gradebook is a label and an arithmetic ledger rendered inside another
    product, and the unknown-address screen shows nobody's data. Item 5's sentence
    would have no subject on either.

    **Owing none and carrying none are the same requirement here, and that is
    deliberate.** A confidentiality sentence on one of these surfaces is a promise
    made where nothing keeps it — nothing about identity is being handled, so
    there is nothing for the words to be true or false about — and it is a second
    copy of the product's identity promise that the exactly-once rule above cannot
    see, free to drift away from the one on the surface that matters. So it is
    reported rather than tolerated. If a real sentence ever trips this, the answer
    is the ruling in ADR 0158 or a dispute about it, never a quiet reword.

    **The mutations it kills:** a reassuring sentence added to the gradebook's
    label or to the fallback screen; and, more likely, a surface moved out of
    `CONFIDENTIALITY_KEY_OF_SURFACE` into the no-line map to make a red go away,
    which this rule turns back into a red rather than a pass. **What makes it
    non-vacuous:** the planted-sentence control above, which requires the counter
    to name one on each of these surfaces.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    assert SURFACES_WITH_NO_CONFIDENTIALITY_LINE, (
        "No surface is recorded as owing no confidentiality line, so this rule read nothing. "
        "Either the map has been emptied or the surface model has changed shape without this rule "
        "being told."
    )

    found = {
        surface: sorted(string.key for string in confidentiality_strings(inventory, surface))
        for surface in SURFACES_WITH_NO_CONFIDENTIALITY_LINE
    }
    carrying = {surface: keys for surface, keys in found.items() if keys}
    assert not carrying, (
        f"These surfaces owe no confidentiality line and carry one: {carrying}.\n"
        "\n"
        "Each is recorded as owing none, with the reason: "
        f"{dict(SURFACES_WITH_NO_CONFIDENTIALITY_LINE)}"
    )


@pytest.mark.invariant
def test_every_governed_surface_is_placed_in_exactly_one_of_the_two_line_maps() -> None:
    """SPEC §4.1 item 5 reaches every governed surface, or it reaches none of it.

    The two rules above divide item 5's work between them, and a surface in
    neither map is asserted by neither: its strings are still swept for item 4's
    vocabulary, so nothing looks wrong, while whether it says the confidentiality
    sentence once, twice or never is checked by nothing. That is the state a new
    surface arrives in by default — somebody adds a governance row and stops — and
    it looks exactly like a surface deliberately excused.

    So the placement is required to be explicit and singular. A surface in both
    maps is the other failure: two answers to one question, and whichever rule
    runs second decides.

    **The mutations it kills:** a governance row added with no decision about its
    confidentiality line, and a surface listed in both maps so that one rule
    demands a line the other forbids. **What makes it non-vacuous:** the planted
    three-surface control above, which requires the reader to report a surface in
    neither map and a surface in both, and to come back clean on maps that place
    everything.
    """
    assert GOVERNED_SURFACES, "The governance map is empty, so this rule read nothing."

    unplaced = surfaces_placed_in_neither_map(
        GOVERNED_SURFACES, CONFIDENTIALITY_KEY_OF_SURFACE, SURFACES_WITH_NO_CONFIDENTIALITY_LINE
    )
    assert not unplaced, (
        f"These governed surfaces are in neither line map: {unplaced}.\n"
        "\n"
        "A surface carries item 5's line — name the entry in `CONFIDENTIALITY_KEY_OF_SURFACE` — or "
        "it owes none, in which case `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` records why, in "
        "words, in the same change that adds the surface. Silence is not the third option: it "
        "reads exactly like the second one and asserts nothing."
    )

    twice = surfaces_placed_in_both_maps(
        CONFIDENTIALITY_KEY_OF_SURFACE, SURFACES_WITH_NO_CONFIDENTIALITY_LINE
    )
    assert not twice, (
        f"These surfaces are in both line maps: {twice}. One of them demands exactly one "
        "confidentiality string and the other forbids any, so the surface cannot satisfy both and "
        "the maps disagree about what was decided."
    )


@pytest.mark.invariant
def test_the_collector_reads_every_report_copy_module_the_epic_shipped() -> None:
    """E4-12's criterion 7, in the collector's own currency.

    E4-08, E4-09 and E4-10 each shipped a copy module beside its components, and
    E4-11 shipped a fourth. All four sat outside `frontend/src/copy/`, which is
    the directory this inventory walks — so the report's strings shipped with
    SPEC §4.1 items 4 and 5 held over them by review alone, which is the state
    both items' footnotes describe as ending at E2.

    **Asked of the collector rather than of a second walk** (`docs/MISTAKES.md`
    entry 35): a parallel enumeration written here could answer this question
    differently from the one the rules consume, and the answer that matters is
    the one the rules consume. The filenames are named rather than inferred
    because the ticket names them; what is *not* pinned here is where under the
    copy directory they sit, which is the implementer's.

    **The mutation it kills:** three of the four modules moved and the fourth
    left behind — the shape this arrives in, since the fourth was shipped after
    the ticket was written and is missing from the ticket's own list. **What
    makes it non-vacuous:** the walk's refusal of an empty directory, and the
    canary above that requires two report keys to be parsed out of what it finds.
    """
    read = frontend_copy_files(FRONTEND_COPY_DIRECTORY)
    assert read, f"{display(FRONTEND_COPY_DIRECTORY)} holds no copy file at all."

    names = {path.name for path in read}
    missing = sorted(name for name in REPORT_COPY_FILENAMES if name not in names)
    assert not missing, (
        f"The collector's own list of copy files does not name {missing}. It names "
        f"{sorted(names)}.\n"
        "\n"
        "A copy module outside the walked directory is a surface the inventory cannot see, and the "
        "invariant-marked rules in this module then pass over it in green. Moving the file is the "
        "repair; widening the walk to the component tree is not, because that directory holds "
        "components and this parser reads copy."
    )


@pytest.mark.invariant
def test_no_string_on_a_governed_surface_carries_lock_or_shield_iconography() -> None:
    """SPEC §4.1 item 5's closing clause, over every collected string.

    > in plain words, no shield or lock iconography

    A padlock beside a confidentiality line is the security theatre this product
    refuses: it makes a promise look like a feature. The strings are what this can
    read, so an icon spelled as a character is caught here and a drawn one is
    E2-10's review — stated in this module's docstring as a limit rather than left
    to be discovered.

    **The mutation it kills:** a lock, key or shield character planted in any
    shipped string, including one spelled as a `\\u{...}` escape. **What makes it
    non-vacuous:** the sweep's control, the parser's escape control, and the
    non-empty inventory.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    found = {
        string.key: (string.text, icons)
        for string in inventory
        if surface_of(string.key) is not None and (icons := iconography_in(string.text))
    }
    assert not found, (
        f"These shipped strings carry lock or shield iconography: {found}. SPEC §4.1 item 5 asks "
        "for plain words: the confidentiality promise is kept by the architecture, and a padlock "
        "next to it is decoration standing in for the thing itself."
    )


@pytest.mark.invariant
def test_every_collected_key_belongs_to_a_governed_surface() -> None:
    """SPEC §4.1 items 4 and 5 reach every surface, or they reach none of it.

    Both items are rules about shipped copy per surface — item 4's vocabulary
    "anywhere", item 5's line "per surface" — so a string whose prefix belongs to
    no governed surface is a string swept by nothing and counted toward nobody's
    confidentiality line. The failure is loud rather than silent for that reason:
    an inventory that ignored what it did not recognise would report a clean tree
    over a whole surface it had never heard of.

    E4's report and aggregate surfaces arrive as a row in `GOVERNED_SURFACES` and
    a copy module beside the existing ones. That is the addition the ticket asks
    for, and this is the test that requires it to be made.

    **The mutation it kills:** a copy file or a registry module landing under a
    new prefix with no governance row — which is exactly how an unregistered
    surface ships. **What makes it non-vacuous:** the synthetic control that
    plants a `report.`-prefixed key and requires it to be reported.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    stray = ungoverned_keys(inventory)
    assert not stray, (
        f"These collected keys belong to no governed surface: {stray}. The governance map holds "
        f"{sorted(GOVERNED_SURFACES)}.\n"
        "\n"
        "A prefix nothing governs is a surface that §4.1 items 4 and 5 are not being checked over: "
        "its strings are swept by neither vocabulary rule and counted toward no surface's "
        "confidentiality line. Adding the surface is one row in `GOVERNED_SURFACES`, plus its "
        "confidentiality key in `CONFIDENTIALITY_KEY_OF_SURFACE` if that surface carries the line."
    )


@pytest.mark.invariant
def test_every_governed_surface_collects_at_least_one_string() -> None:
    """The other direction: §4.1 items 4 and 5 over an empty surface assert nothing.

    The ticket states it plainly — "the collector proves non-emptiness per
    registered surface (an empty surface is a failure, not a pass)". A copy module
    that dropped out of the enumeration, a frontend file renamed out of the glob,
    a prefix that quietly changed: each leaves the vocabulary sweeps and the
    confidentiality count passing over nothing, in green.

    **The mutation it kills:** a copy module removed from what the registry
    enumerates, or a governance row for a prefix that ships nothing. **What makes
    it non-vacuous:** the synthetic control that removes each governed prefix in
    turn and requires exactly that prefix to be reported.
    """
    inventory = collect_shipped_copy()
    assert inventory, "The inventory is empty, so this rule passed over nothing."
    empty = prefixes_that_collect_nothing(inventory)
    assert not empty, (
        f"These governed prefixes collected no strings at all: {empty}.\n"
        "\n"
        "Every rule in this module is of the form 'no collected string does X', so a surface that "
        "collects nothing satisfies all of them. Either the copy for that prefix has stopped being "
        f"enumerated — `{COPY_MODULES_FUNCTION}()` for the registry, the `frontend/src/copy` glob "
        "for the frontend — or the prefix has been renamed and the governance map has not followed "
        "it."
    )


@pytest.mark.invariant
def test_the_backend_half_of_the_inventory_covers_every_module_in_the_copy_package() -> None:
    """The inventory's source is one §4.1 items 4 and 5 cannot be quietly shrunk from.

    Acceptance criterion 3. The registry's own enumeration is what the collector
    consumes; this compares it against a second, independent walk of the package
    *directory*, so that a `copy_modules()` returning a hand-written list is
    caught by the inventory rather than only by the ticket that wrote the
    enumeration. A module missing from the collected inventory is a module whose
    strings ship with items 4 and 5 asserted over nothing.

    **The mutation it kills:** a hand-written module tuple substituted for the
    package enumeration, with one module left out of it. **What makes it
    non-vacuous:** the directory walk is required to find modules and keys before
    the comparison means anything.
    """
    declared = keys_declared_on_disk()
    assert declared, (
        f"The package directory of `{COPY_PACKAGE}` holds no module publishing "
        f"`{COPY_MAPPING_NAME}`, so this comparison has nothing to compare and the inventory's "
        "backend half is unguarded."
    )

    collected = {string.key for string in collect_backend_copy()}
    missed = {
        module: [key for key in keys if key not in collected]
        for module, keys in declared.items()
        if any(key not in collected for key in keys)
    }
    assert not missed, (
        f"These modules are in the copy package directory and their keys are not in the collected "
        f"inventory: {missed}.\n"
        "\n"
        f"`{COPY_PACKAGE}.{COPY_MODULES_FUNCTION}()` is what the inventory reads through, and it "
        "enumerates the package's own modules for exactly this reason: a guard's inventory must "
        "not be shrinkable by an edit to the thing it guards. A module the enumeration misses is "
        "copy that ships with §4.1 items 4 and 5 asserted over nothing."
    )


@pytest.mark.invariant
def test_the_frontend_half_of_the_inventory_covers_every_file_in_the_copy_directory() -> None:
    """The same rule for the frontend: every file is read, or the run says so.

    Acceptance criterion 3 again, from the other side. The directory is walked
    rather than listed, so a file added to it is inventoried the day it lands and
    a file that cannot be parsed stops the run instead of dropping out of it. That
    is what makes the surface list unshrinkable: there is no list.

    **The comparison is between two independent walks**, and that is the whole of
    what this test is worth. The first version compared the collector's glob with
    the same glob and therefore agreed with itself: a copy file in a subdirectory
    and a copy file spelled `.tsx` each shipped an item 4 violation and a padlock
    with the suite 41 green. What is asserted now is that **everything** under the
    copy directory — any depth, any suffix — is a file the collector parsed.

    **The mutations it kills:** narrowing the collector's walk to one level or one
    suffix (the missed file is then reported here); and rebuilding this rule out
    of the collector's own enumeration, which is the shape that made it silent.
    **What makes it non-vacuous:** the two controls above, one for a directory
    read whole and one holding files the collector cannot read, plus the walk's
    own refusal of an empty directory.
    """
    files = every_file_under_the_copy_directory(FRONTEND_COPY_DIRECTORY)
    assert files, f"{display(FRONTEND_COPY_DIRECTORY)} holds no file to read."

    unread = files_the_collector_did_not_read(FRONTEND_COPY_DIRECTORY)
    assert not unread, (
        f"These files are under {display(FRONTEND_COPY_DIRECTORY)} and the inventory read no "
        f"string out of any of them: {unread}.\n"
        "\n"
        "That directory holds copy. A file the collector does not parse is a shipped surface's "
        "strings with §4.1 items 4 and 5 asserted over nothing — whether it is nested where the "
        "walk did not look, spelled with a suffix nobody listed, or a format this parser does not "
        "read at all.\n"
        "\n"
        "If such a file is legitimate, it does not belong in the copy directory, or the collector "
        "is taught to read it — in the change that introduces it, with a control in both "
        "directions. Widening what this rule ignores is not one of the answers."
    )
