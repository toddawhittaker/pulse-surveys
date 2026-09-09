"""What this provider answers, and the whole of why — ticket E2-07.

Every rule this service has lives in this module, and `GET /mock/rules` serves
the constants below verbatim. That is E2-07's third acceptance criterion: "the
mock's rules are served, not copied: its README/route states them, and the tests
that aim at them read the served statement". The lesson behind it is E1-07's — a
vocabulary that a test hand-copies is a vocabulary a rename breaks silently on
one side (ADR 0088's recorded consequence for `mock-lms`), so the suite reads
this document and keeps exactly one deliberate copy beside a test that diffs it.

**Two tasks, and the marker line says which.** A prompt carrying
`SUMMARY_MARKER_LINE` is asking for SPEC §7.4's weekly summary and is answered
with a summary payload derived from the week's comments; anything else is a
comment-validity request, which is what this service answered to everything
before E4-05. The rules below apply to the input of whichever task was asked
for — the student's comment, or the week's.

**The rules, in the order they are applied.**

1. **A wrong-answer marker anywhere in the input**, checked first so that a
   comment long enough to be classified normally can still drive a failure. Each
   selects one row of ADR 0056's taxonomy from the tool side:

   - `mock-ai:503` — HTTP 503. The endpoint answered and said it cannot serve;
     the gateway raises `AIProviderUnavailableError` and §3.3's floor applies.
   - `mock-ai:500` — HTTP 500. The endpoint answered *about this request*; the
     gateway raises `AIProviderRefusedError` and nothing floors. This and the row
     above are one status code apart on purpose: they are the near miss E2-08's
     tests need, and ADR 0056 spends a paragraph on why 500 is outside the floor.
   - `mock-ai:malformed` — HTTP 200, a well-formed chat completion, and a payload
     that is not the contract. The gateway re-asks once (§7.4, ADR 0053) and then
     surfaces `AIResponseInvalidError`. This service is stateless, so the re-ask
     gets the same answer, which is what makes "then the error" reachable.
   - `mock-ai:stall` — the correct answer, `STALL_SECONDS` late. A *late* answer
     rather than a broken one, which is ADR 0056's read-timeout row and the case
     SPEC §3.3 names outright. Six seconds is past the validity task's
     four-second budget and well inside the summary task's sixty, so it drives a
     timeout for a comment and a late answer for a week — a stall long enough to
     time a summary out would hold a test for a minute to prove a row ADR 0056
     already has a path for.

2. **A forced verdict**, so that an end-to-end run can drive a particular
   classification without patching the backend: `mock-ai:substantive`,
   `mock-ai:insufficient`, `mock-ai:nonsense`.

3. **The character rule**, and it is SPEC §3.3's own: a comment of fewer than
   `SUBSTANTIVE_MINIMUM_CHARACTERS` characters is `insufficient`, and anything
   else is `substantive`. §3.3's own example of a comment that must be bounced —
   `"it was okay"` — is eleven characters, so it classifies `insufficient` end to
   end, which E2-07's scope asks for by name.

4. **The summary**, which is the whole of the second task. Rules 2 and 3 belong
   to comment validity alone — a summary has no closed set of answers to force
   and no length rule to apply — so a week carrying no wrong-answer marker is
   answered here: a payload naming the stream the prompt asked about, prose
   saying how many comments arrived and how each opened, and one theme per
   comment up to `SUMMARY_THEME_LIMIT`, each claiming exactly one. It reads how
   many comments there are and never what any of them says.

5. **The small-N summary**, which is rule 4 with the openings taken out. A prompt
   carrying `SMALL_N_MARKER` in its instructions is asking about a week below
   SPEC §4's n-threshold, and the owner's ruling of 2026-09-09 is that such a
   week's summary names themes only and reuses none of the commenters' word
   strings. Rule 4's answer is built out of how each comment *opened*, which is
   precisely what the ruling forbids there — so this rule answers prose naming
   the count alone and themes labelled by their ordinal. Everything else about
   rule 4 holds: the stream, the theme bound, the counts, and the wrong-answer
   markers ahead of all of it.

**`nonsense` is reachable only by its marker.** Rule 3 has two outcomes and not
three. Deciding that a comment is keyboard mashing is a judgement about content
and this service makes none; a heuristic invented here would make every
end-to-end assertion about an ordinary comment conditional on a rule nobody
specified.

**The order is observable and is asserted.** A comment carrying both
`mock-ai:500` and `mock-ai:substantive` gets the 500, and a comment carrying
`mock-ai:insufficient` and forty characters of prose is `insufficient`. Written
down here because two orders that differ only in cases nobody writes are the same
mock.
"""

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# The boundary the student's comment starts at
# ---------------------------------------------------------------------------

# The last line of the rendered validity prompt's own instructions (the version
# `app.ai.tasks` currently renders) — everything after it is the student's
# comment, running to the end of the
# message.
#
# **This is a second copy of a string that lives in the backend, and it is
# guarded rather than trusted.** This package cannot import `backend/app/`: both
# are called `app` (SPEC §13), and an image or a test process holding two
# resolves `import app` by whichever won the path (ADR 0039). So the boundary is
# copied, and
# `tests/unit/test_mock_ai_rules.py::test_the_marker_line_the_mock_publishes_is_
# a_line_of_the_validity_prompt` holds this constant against the prompt's own
# text. E1-07's lesson is that a second copy is fine when something holds it
# against the first and fatal when nothing does.
#
# **Why this line and not `[[STUDENT_COMMENT]]`.** The placeholder is what the
# *file* ends with, and it is the obvious thing to look for — but
# `app.ai.tasks.render_prompt` replaces it with the comment, so it is not in the
# message the provider is sent. A mock extracting on it would answer the
# extraction failure below for every real classification while passing any test
# that built its own prompt. What survives rendering is the sentence the
# instructions end with, and that is what this is.
MARKER_LINE = "answer you ever give is the JSON object specified above."

# The same boundary for SPEC §7.4's weekly summary (E4-05), and the line this
# service dispatches on: a prompt carrying it is asking for a summary of a week,
# and a prompt that does not is asking for a comment-validity verdict.
#
# **A whole line here, where the validity boundary is a sentence fragment**, and
# the difference is what survives rendering. The validity prompt's marker is the
# last line of its *instructions*, because the line after it is the placeholder
# and the placeholder is replaced by the comment. The summary prompt names its
# comments section on its own line and puts the placeholder on the next one, so
# the whole line survives into the message the provider is sent.
#
# It is a second copy of a string that lives in the backend, guarded the same way
# the line above is: this package cannot import `backend/app/` (SPEC §13, ADR
# 0039), and
# `tests/unit/test_mock_ai_summary_rules.py::test_the_published_summary_marker_is_
# a_line_of_the_summary_prompt` holds it against whichever prompt version
# `app.ai.tasks` renders. A reworded prompt goes red there rather than turning
# every summary in a development stack into an extraction failure.
SUMMARY_MARKER_LINE = "The week's comments follow this line, one numbered block each."

# The small-N mode's own marker, and the line this service reads it off — the
# owner's ruling of 2026-09-09, which is that a week below SPEC §4's n-threshold
# has its summary name themes only and reuse none of the commenters' word
# strings. `summary.v2` is the prompt that carries the instruction and
# `summary.v1` is the one that does not, so a prompt holding this fragment is a
# small-N week and a prompt without it is an ordinary one.
#
# **Read out of the head of the prompt, before the comments boundary**, exactly as
# the stream is — and the head is cut at the **first** copy of
# `SUMMARY_MARKER_LINE` for that to mean anything. A student could type this
# sentence into a feedback box, and if the search ran over the whole message that
# comment would put the mock into themes-only mode for its own week.
#
# **This comment claimed more than it had until E4-15's security review.** It said
# that searching the instructions alone means nothing after the marker line can
# reach it, and that was true only of a boundary taken at the first copy; the code
# took it at the *last*, so a comment carrying the marker line pulled the comments
# ahead of it into the head. `answer_for` now cuts at the first copy and the claim
# holds.
#
# A fragment rather than a whole line, because the instruction is a wrapped
# Markdown bullet rather than a sentence on its own line. Like
# `SUMMARY_MARKER_LINE` above it is a second copy of a string that lives in the
# backend, and it is guarded the same way rather than imported (SPEC §13, ADR
# 0039).
SMALL_N_MARKER = "below the reporting threshold, so name themes"

# How the summary prompt names the stream it is asking about, and how this
# service reads it back. The prompt substitutes the stream token after this
# prefix, in its instructions — which is *before* the marker line above, so the
# stream this service answers with cannot be moved by anything a student wrote.
STREAM_LINE_PREFIX = "Stream under review:"


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

# SPEC §7.4's Output column for the comment-validity task.
SUBSTANTIVE = "substantive"
INSUFFICIENT = "insufficient"
NONSENSE = "nonsense"

# SPEC §5.1's two comment streams, which the weekly summary is produced one of at
# a time: "grouped under 'About the instructor' / 'About the course'". Transcribed
# rather than imported, like every other piece of the backend's vocabulary here,
# and this service does not choose between them — it reads which one the prompt
# asked about and answers that one.
INSTRUCTOR_STREAM = "instructor"
COURSE_STREAM = "course"
SUMMARY_STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# The three members of the weekly-summary payload: the contract minus the audit
# pair, exactly as `VERDICT_KEY` above is the validity contract minus it.
STREAM_KEY = "stream"
SUMMARY_KEY = "summary"
THEMES_KEY = "themes"
THEME_LABEL_KEY = "label"
THEME_COUNT_KEY = "comment_count"

# How the invented answer is built out of the week it was sent. Both numbers are
# arbitrary and neither decides anything: a label is the opening words of one
# comment, and at most three comments get one, so a theme is always carried by
# exactly one comment and never claims more than the week holds.
SUMMARY_LABEL_WORDS = 6
SUMMARY_THEME_LIMIT = 3

# The member the answer's payload spells the verdict under. The contract minus
# the audit pair is one field: ADR 0031 has the gateway supply `prompt_version`
# and `model_id` and reject a payload carrying either, so a provider that filled
# them in would be refused on every call.
VERDICT_KEY = "verdict"

# SPEC §3.3: "the prototype's ≥25-character heuristic ... retained solely as the
# fail-open floor". Reused here so that the spec's own `"it was okay"` example
# classifies `insufficient` through a running stack, and **as written**: a
# comment of exactly this many characters is long enough.
SUBSTANTIVE_MINIMUM_CHARACTERS = 25

# How long the stalling answer waits. It has to outlast
# `app.ai.tasks.VALIDITY_TIMEOUT_SECONDS`, which is 4.0 — a stall inside that
# budget answers in time, so nothing floors and ADR 0056's unavailable row has no
# path in this stack. Six rather than five: the margin is what keeps the
# assertion from turning on scheduling noise, and it is paid once per test that
# uses it.
STALL_SECONDS = 6.0

# The four wrong answers and the three forced verdicts, all in one `mock-ai:`
# namespace so that a marker cannot be mistaken for something a student wrote.
UNAVAILABLE_MARKER = "mock-ai:503"
REFUSED_MARKER = "mock-ai:500"
MALFORMED_MARKER = "mock-ai:malformed"
STALL_MARKER = "mock-ai:stall"
SUBSTANTIVE_MARKER = "mock-ai:substantive"
INSUFFICIENT_MARKER = "mock-ai:insufficient"
NONSENSE_MARKER = "mock-ai:nonsense"

# Every marker, keyed by what it selects. This mapping is what `/mock/rules`
# publishes and what a caller picks a behaviour out of.
MARKERS: dict[str, str] = {
    "unavailable": UNAVAILABLE_MARKER,
    "refused": REFUSED_MARKER,
    "malformed": MALFORMED_MARKER,
    "stall": STALL_MARKER,
    SUBSTANTIVE: SUBSTANTIVE_MARKER,
    INSUFFICIENT: INSUFFICIENT_MARKER,
    NONSENSE: NONSENSE_MARKER,
}

# The two statuses, named rather than written into the branches, because which
# one each marker answers is the whole of E2-07's near-miss pair.
UNAVAILABLE_STATUS = 503
REFUSED_STATUS = 500

# The malformed answer's payload: a well-formed JSON object that is not the
# comment-validity contract. It carries no verdict member at all, so it is
# refused both by a contract built with `extra="forbid"` and by one that merely
# requires its own field — unlike `{"verdict": "maybe"}`, which only the second
# would catch.
MALFORMED_PAYLOAD: dict[str, Any] = {"answer": 42}


class ExtractionError(Exception):
    """The prompt does not carry the marker line, so there is no comment to read.

    Loud, and answered as a 500 rather than absorbed. Every quiet alternative is
    wrong for every request and looks like a working stack: classifying the whole
    prompt answers `substantive` forever, and classifying the empty string
    answers `insufficient` forever. The message names the line it looked for,
    which is the one thing whoever meets this in a log needs — it says the prompt
    and this service have drifted apart.
    """


@dataclass(frozen=True)
class Answer:
    """What this service does with one request: a status, a body, and a delay."""

    status: int
    payload: dict[str, Any]
    stall_seconds: float = 0.0
    # Set only on a 200 carrying a classification: the verdict this answer
    # carries, so a reader has it without parsing the payload back out.
    verdict: str | None = None


def extract_comment(prompt: str) -> str:
    """The student's comment out of one rendered prompt.

    Everything after the **last** occurrence of `MARKER_LINE`, with the
    whitespace the prompt's own layout puts there removed.

    Last rather than first, and that is the boundary
    `backend/app/ai/prompts/README.md` rests the whole injection defence on: a
    prompt may quote its own marker earlier — in an instruction, in an example —
    and a comment may contain a copy of it, so "everything after the final
    marker" is the only reading that cannot be moved by what a student typed.

    Stripped, because the newline between the marker and the comment is the
    prompt's punctuation rather than a character the student wrote. Without it a
    24-character comment would be measured as 25 and the character rule would
    turn on prompt layout.
    """
    boundary = prompt.rfind(MARKER_LINE)
    if boundary < 0:
        raise ExtractionError(
            "This prompt carries no copy of the line the student's comment follows, so there is "
            "nothing here to classify. The line is: "
            f"{MARKER_LINE!r}. The rendered validity prompt ends its instructions with "
            "it and `mock-ai/app/rules.py` copies it; a prompt that no longer does has drifted "
            "away from this mock."
        )
    return prompt[boundary + len(MARKER_LINE) :].strip()


def verdict_answer(verdict: str, *, stall_seconds: float = 0.0) -> Answer:
    """A 200 carrying one verdict, as the payload the gateway validates."""
    return Answer(
        status=200,
        payload={VERDICT_KEY: verdict},
        stall_seconds=stall_seconds,
        verdict=verdict,
    )


def failing_answer(text: str) -> Answer | None:
    """The three markers that answer *instead of* the task, or `None` for neither.

    Rule 1 minus the stall, and the split is what a second task made worth
    making: these three are answers about the request — a status, or a body that
    is not the contract — and none of them depends on what was being asked for,
    so a task added later reaches ADR 0056's rows through this function rather
    than through a copy of these three branches. The stall stays with each task,
    because a stall is *the task's own correct answer, late*, and the two tasks
    do not have the same correct answer.
    """
    if UNAVAILABLE_MARKER in text:
        return Answer(
            status=UNAVAILABLE_STATUS,
            payload={
                "error": {
                    "type": "service_unavailable",
                    "message": (
                        f"The mock provider was asked for {UNAVAILABLE_MARKER}, so it reports "
                        "itself temporarily unable to serve this request."
                    ),
                }
            },
        )
    if REFUSED_MARKER in text:
        return Answer(
            status=REFUSED_STATUS,
            payload={
                "error": {
                    "type": "internal_error",
                    "message": (
                        f"The mock provider was asked for {REFUSED_MARKER}, so it answers about "
                        "this request rather than about its own availability."
                    ),
                }
            },
        )
    if MALFORMED_MARKER in text:
        return Answer(status=200, payload=dict(MALFORMED_PAYLOAD))
    return None


def classify(comment: str) -> Answer:
    """Apply the three published rules to one extracted comment, in order.

    The order is the module docstring's and is not an implementation detail: rule
    1 before rule 2 is what lets a comment that also names a verdict still drive
    a failure, and rule 2 before rule 3 is what lets a long comment be forced
    `insufficient`.
    """
    failing = failing_answer(comment)
    if failing is not None:
        return failing
    if STALL_MARKER in comment:
        # A correct answer that arrives late, which is what makes this a timeout
        # rather than a failure.
        return verdict_answer(SUBSTANTIVE, stall_seconds=STALL_SECONDS)

    for verdict in (SUBSTANTIVE, INSUFFICIENT, NONSENSE):
        if MARKERS[verdict] in comment:
            return verdict_answer(verdict)

    long_enough = len(comment) >= SUBSTANTIVE_MINIMUM_CHARACTERS
    return verdict_answer(SUBSTANTIVE if long_enough else INSUFFICIENT)


# ---------------------------------------------------------------------------
# The weekly summary (E4-05)
# ---------------------------------------------------------------------------


def stream_asked_about(head: str) -> str:
    """Which of SPEC §5.1's two streams this summary prompt is about.

    Read out of the prompt's *instructions* — everything before the marker line —
    so that no comment can decide it. The last occurrence wins, for the same
    reason `extract_comment` reads the last marker: a prompt is free to mention
    the prefix earlier, and the one nearest the input is the one that describes
    this call.

    A prompt naming no stream, or naming something that is not one of the two,
    is refused rather than guessed at. The quiet alternative is a development
    stack where every summary comes back about the instructor, including the
    course ones — which the tool then refuses, one stream at a time, for a reason
    that points at the prompt instead of at this service.
    """
    found: str | None = None
    for line in head.splitlines():
        stripped = line.strip()
        if stripped.startswith(STREAM_LINE_PREFIX):
            found = stripped[len(STREAM_LINE_PREFIX) :].strip().lower()
    if found not in SUMMARY_STREAMS:
        raise ExtractionError(
            "This summary prompt does not say which stream it is about, so there is nothing "
            f"here to summarize for. The line is {STREAM_LINE_PREFIX!r} followed by one of "
            f"{list(SUMMARY_STREAMS)}; this prompt carried {found!r}. The rendered summary "
            "prompt names it in its instructions and `mock-ai/app/rules.py` copies the prefix."
        )
    return found


def comment_of(block: list[str]) -> str:
    """One rendered comment block as its text, with the numbering line dropped.

    The summary prompt renders each comment as a numbered label on its own line
    followed by the comment itself, so a block of more than one line whose first
    line ends in a colon has a label to drop. A block that is one line, or whose
    first line is not a label, is taken whole — this service reads a layout, and
    guessing harder about one would be it deciding something.
    """
    lines = block[1:] if len(block) > 1 and block[0].strip().endswith(":") else block
    return "\n".join(lines).strip()


def week_comments(body: str) -> tuple[str, ...]:
    """The week's comments out of everything after the marker line, in order.

    Blank-line separated, which is how the prompt renders them. A comment holding
    a blank line of its own would be read here as two, and that is a limit of
    reading a layout rather than a defect to work around: this service counts
    blocks so that a theme cannot claim more comments than the week holds, and
    over-counting the week would be the direction that hides that.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    comments: list[str] = []
    for block in blocks:
        text = comment_of(block)
        if text:
            comments.append(text)
    return tuple(comments)


def opening_words(comment: str) -> str:
    """The first few words of one comment, as a theme label a person can recognise."""
    return " ".join(comment.split()[:SUMMARY_LABEL_WORDS])


def summarize(stream: str, comments: tuple[str, ...], *, themes_only: bool = False) -> Answer:
    """A weekly-summary payload derived from the week it was sent.

    **Derived rather than canned, and that is the whole of what it is for.** A
    constant answer is perfectly deterministic and would let every test in the
    stack pass without the week's comments ever leaving the tool. So the summary
    names how many comments arrived and how each one opened, and a theme's label
    is one comment's opening words — two different weeks are answered
    differently, and the same week twice is answered identically, which is what
    the gateway's one bounded re-ask needs to reach the same wrong answer twice.

    **`themes_only` takes the openings out, and takes nothing else with them.**
    Below SPEC §4's n-threshold the owner's ruling of 2026-09-09 is that a
    summary names themes only and reuses none of the commenters' word strings,
    and an opening *is* a commenter's words. So that branch derives its answer
    from the comment **count** instead — still derived, still different for two
    different weeks, still identical for the same week twice — and labels its
    themes by ordinal. The caller sets the flag from the prompt's own marker;
    nothing here reads a threshold.

    **It is not a summary.** Nothing here reads what a comment says, and ADR 0113
    is why nothing outside development may point at this service. The count is
    the one arithmetic it does get right: at most one theme per comment, each
    claiming exactly one, so no theme can claim more comments than the week holds.

    The wrong-answer markers reach this task through the same three branches the
    validity task uses, because E4-05's first acceptance criterion asks for the
    shape-violation path to be exercised against this service in CI. The stall is
    the correct answer late here too — and a six-second stall is inside the
    summary task's own sixty-second budget, so it drives a late summary rather
    than a timeout.
    """
    week = "\n".join(comments)
    failing = failing_answer(week)
    if failing is not None:
        return failing
    stall_seconds = STALL_SECONDS if STALL_MARKER in week else 0.0

    if themes_only:
        # **The small-N answer repeats nothing.** The ordinary answer below is
        # built out of how each comment opened, which is exactly the shape the
        # ruling of 2026-09-09 forbids below the threshold: those openings are the
        # commenters' own words, and in a quiet week a phrase carried over
        # identifies the person who wrote it. So this branch derives its labels
        # from the *count* and from nothing a student typed.
        #
        # It stays a derived answer rather than a constant one, for the reason the
        # ordinary branch gives: two different weeks are answered differently, and
        # the same week twice is answered identically. What it derives from is the
        # number of comments rather than their text.
        numbered = [f"theme {index + 1}" for index in range(len(comments))]
        summary = (
            (
                f"The {stream} stream carried {len(comments)} comment(s) this week, and the week is "
                "below the reporting threshold. This is the mock provider rather than a model, so "
                "there is no description here — and nothing above repeats what any comment said."
            )
            if comments
            else (
                f"No comments reached the mock provider for the {stream} stream, so there is "
                "nothing here to describe."
            )
        )
        return Answer(
            status=200,
            payload={
                STREAM_KEY: stream,
                SUMMARY_KEY: summary,
                THEMES_KEY: [
                    {THEME_LABEL_KEY: label, THEME_COUNT_KEY: 1}
                    for label in numbered[:SUMMARY_THEME_LIMIT]
                ],
            },
            stall_seconds=stall_seconds,
        )

    openings = [opening_words(comment) for comment in comments]
    if openings:
        summary = (
            f"The {stream} stream carried {len(comments)} comment(s) this week. This is the "
            "mock provider rather than a model, so what follows is how each comment opened "
            "rather than what any of them said: " + "; ".join(openings) + "."
        )
    else:
        summary = (
            f"No comments reached the mock provider for the {stream} stream, so there is "
            "nothing here to describe."
        )
    return Answer(
        status=200,
        payload={
            STREAM_KEY: stream,
            SUMMARY_KEY: summary,
            THEMES_KEY: [
                {THEME_LABEL_KEY: opening, THEME_COUNT_KEY: 1}
                for opening in openings[:SUMMARY_THEME_LIMIT]
            ],
        },
        stall_seconds=stall_seconds,
    )


def answer_for(prompt: str) -> Answer:
    """What this service answers to one whole rendered prompt.

    The single entry point, so that "which part of this prompt is the input, and
    which task is it for" is one question with one place to read rather than a
    branch in the HTTP handler. `app.main` reads a request body, hands the text
    over, and turns whatever comes back into a response; it decides nothing.

    **Two tasks, dispatched on the summary's own marker line.** A prompt carrying
    it is asking for SPEC §7.4's weekly summary; everything else is a
    comment-validity request, which is what this service answered to everything
    before E4-05. That order is deliberate rather than incidental: the validity
    prompt does not carry the summary marker, so it cannot be captured by the
    first branch, while a summary prompt reaching the second branch would be
    answered with a verdict — a well-formed payload for the wrong contract, which
    the tool reports as a shape violation in the prompt rather than as a mock
    that cannot tell two tasks apart.

    Raises `ExtractionError` for a prompt this service cannot read, which the
    handler answers as a 500 naming what it looked for.
    """
    if SUMMARY_MARKER_LINE in prompt:
        # **The first copy of the marker, not the last**, which is where this
        # differs from the validity path above and is not a style difference.
        # The summary prompt's own marker is the last line of its instructions and
        # the week's comments follow it, so the *first* occurrence is always the
        # template's. A student may type the marker line into a feedback box — the
        # prompt says so in as many words, "a comment may contain … another copy of
        # this marker" — and with `rfind` that copy moved the split into the comment
        # block, putting the comments before it into `head`. Everything read out of
        # `head` is then partly student text: the stream, and the small-N mode.
        # E4-15's security review found it, in the deny direction only (a comment
        # could refuse its own week's summary or answer for the wrong stream, never
        # reveal anything), and `find` closes it.
        boundary = prompt.find(SUMMARY_MARKER_LINE)
        head = prompt[:boundary]
        body = prompt[boundary + len(SUMMARY_MARKER_LINE) :]
        return summarize(
            stream_asked_about(head),
            week_comments(body),
            themes_only=SMALL_N_MARKER in head,
        )
    return classify(extract_comment(prompt))


def served_rules() -> dict[str, Any]:
    """The whole vocabulary, as `GET /mock/rules` publishes it.

    Built from the constants above rather than written out again, so that the
    served document cannot disagree with the code that applies it — which is the
    property E2-07's third criterion is really asking for. A test reads this; the
    prose in `mock-ai/README.md` is for a person and is the copy that can go
    stale, which is why nothing asserts against it.
    """
    return {
        "markers": dict(MARKERS),
        "substantive_minimum_characters": SUBSTANTIVE_MINIMUM_CHARACTERS,
        "stall_seconds": STALL_SECONDS,
        "comment_marker_line": MARKER_LINE,
        "summary_marker_line": SUMMARY_MARKER_LINE,
        "summary_small_n_marker": SMALL_N_MARKER,
        "summary_stream_line_prefix": STREAM_LINE_PREFIX,
        "verdicts": [SUBSTANTIVE, INSUFFICIENT, NONSENSE],
        "streams": list(SUMMARY_STREAMS),
        "tasks": [
            f"comment validity — a prompt with no {SUMMARY_MARKER_LINE!r} line. The comment is "
            f"everything after the last {MARKER_LINE!r}.",
            f"weekly summary — a prompt carrying {SUMMARY_MARKER_LINE!r}. The week is the "
            "blank-line-separated blocks after the first copy of it, and the stream is the token "
            f"after the last {STREAM_LINE_PREFIX!r} line before it. The first copy rather than "
            "the last, so a comment carrying the marker line cannot move the split.",
            f"weekly summary, small-N — the same, for a prompt whose instructions carry "
            f"{SMALL_N_MARKER!r}. The answer names the comment count and labels its themes by "
            "ordinal, repeating none of the week's words (the ruling of 2026-09-09).",
        ],
        "rule_order": [
            "1. A wrong-answer marker anywhere in the input decides the answer, for either "
            f"task: {UNAVAILABLE_MARKER} answers HTTP {UNAVAILABLE_STATUS}, {REFUSED_MARKER} "
            f"answers HTTP {REFUSED_STATUS}, {MALFORMED_MARKER} answers 200 with a payload the "
            f"contract refuses, and {STALL_MARKER} answers {STALL_SECONDS} seconds late — with "
            f"{SUBSTANTIVE} for a comment, and with the summary for a week.",
            f"2. A forced-verdict marker names its own verdict: {SUBSTANTIVE_MARKER}, "
            f"{INSUFFICIENT_MARKER}, {NONSENSE_MARKER}. Comment validity only; a summary has no "
            "closed set of answers to force.",
            f"3. Otherwise a comment of fewer than {SUBSTANTIVE_MINIMUM_CHARACTERS} characters is "
            f"{INSUFFICIENT} and anything else is {SUBSTANTIVE}. {NONSENSE} is reachable only by "
            "its marker.",
            "4. A week is answered with a summary derived from the comments it carried — how "
            "many arrived and how each opened — and one theme per comment up to "
            f"{SUMMARY_THEME_LIMIT}, each claiming exactly one comment. Nothing here reads what "
            "a comment says.",
        ],
    }
