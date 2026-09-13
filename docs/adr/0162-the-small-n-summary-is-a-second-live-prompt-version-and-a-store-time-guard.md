# 0162 — The small-N summary is a second live prompt version and a store-time guard that refuses and retries

## Context

The owner ruled on 2026-09-09, on a channel the E4 boundary review found: below
SPEC §4's n-threshold a week's summary names themes only and may not reuse the
commenters' own word strings. SPEC §5.1 carries the rule and
[ADR 0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)'s
2026-09-09 amendment carries the channel and the residual. What is left is
construction, and none of it is settled by either record.

Three questions, each with a defensible other answer:

1. **How the mode reaches the model.** The summary prompt has to say something
   different below the threshold, and `render_summary_prompt(version, *, stream,
   comments)` is a settled three-parameter signature asserted as an equality —
   E4-05's second acceptance criterion, whose whole point is that a caller holding
   identity has nowhere to put it.
2. **What happens when the model ignores it.** A prompt instruction is soft. The
   E4 breakdown's decision 2 rules out regeneration, so a stored summary is
   permanent for the term, and a quoted phrase stored on Monday is a quoted phrase
   an instructor reads for eleven more weeks.
3. **What counts as reuse.** "Do not quote" is not a comparison a program can
   make, and every bound costs something in one direction or the other.

## Decision

**A second live prompt version.** `summary.v2.md` is `summary.v1.md`'s text plus
the themes-only rule; `summarize_stream` gains `small_n: bool = False` and renders
v2 when it is set. Both versions stay live and the mode selects between them,
which is a departure from `prompts/README.md`'s ordinary reading — add the next
version and leave the old alone, the old one then being history. Here v1 is what
an at-or-above-threshold week renders and v2 is what a small-N week renders. The
version is the one parameter `render_summary_prompt` leaves free, so the mode
rides on it rather than on a fourth argument; and the stored `prompt_version` then
says which mode wrote each row, with no second column and no inference.

**A structural guard at store time, which refuses and lets the week retry.**
`app.services.reporting.refuse_a_summary_reusing_a_comment` runs below the
threshold only, over the answer's prose **and every theme label**, against the
comments that call was fed. A shared run at or above `SUMMARY_REUSE_BOUND`
characters, case and whitespace normalized, raises `SmallNSummaryReuseError`; the
walk rolls back that section-week and counts it among the ones left for the next
run. Nothing is stored, so the week is still "awaiting a summary" and the next run
asks again.

**`SUMMARY_REUSE_BOUND` is twenty characters**, compared after lower-casing and
collapsing runs of whitespace, over a window of exactly that length — any longer
run contains one.

**Theme labels are in scope with the prose.** Both cross the wire to the
instructor: `_payload` puts the summary in `streams.<token>.summary` and E4-10
renders each theme's label beside its count. A label is also the shortest and most
quotable part of an answer, which makes it the likeliest place for a lifted phrase
to survive an instruction the prose obeyed.

## Alternatives rejected

**Redact the offending run and store the rest.** The obvious repair, and it puts a
sentence in front of an instructor that neither the model wrote nor the week
supports — silently. It is the same objection `summarize_stream` already records
for refusing an over-claimed theme count rather than clamping it: "a count clamped
to something plausible would put a figure in front of an instructor that neither
the model gave nor the week supports, and it would do it silently". A redaction is
worse than a clamp, because prose with a hole in it reads as prose.

**Store it anyway and log the violation.** The shape a reviewer accepts as failing
soft, and the one this decision is most against. Decision 2 of the E4 breakdown
rules out regeneration, so "store and log" means the quoted words stay on the
report for the rest of the term while a warning nobody is watching scrolls past in
a worker log. The whole ruling would then hold only where the model happened to
comply.

**Refuse and mark the week done.** Cheaper than a retry and it makes the refusal
permanent: the quiet week that most needs a summary — §5.1 makes it the only
comment signal such a week has — becomes the week that never gets one, on the
strength of one bad answer. The retry costs one provider call a week.

**Fail the whole run rather than the section-week.** One institution's Monday lost
to one model's answer. The walk already commits per section-week for exactly this
reason.

**Ask the model again immediately, in the same run.** Tempting and it is a loop
with no bound in a job that already has no cap (ADR 0154). The schedule is the
retry, which is the same answer §3.3's re-classification sweep gives.

**A single `summary.v2` carrying both modes behind a placeholder.** Cleaner as a
file and unreachable: rendering it in one mode or the other needs the renderer to
be told which, and the renderer's parameter list is settled at three and asserted
as an equality. Widening it for this would spend E4-05's identity boundary on a
convenience.

**A bound of ten, or five, or "any shared phrase".** Ordinary paraphrase trips
them. A summary of a week about a laboratory session contains "the laboratory
session" whatever it does; at ten characters, "the seminar" is a violation. What a
too-low bound costs is not visible as a failure — it is quiet weeks whose summary
region is empty, week after week, with the retry firing every Monday and nothing
on the report saying a summary was owed.

**A bound of forty, or a whole sentence.** The other direction, and it is what the
exit drive's absence check was written against before this ruling: a forty-
character prefix leaves three or four words of a comment free to cross, which is
enough to match against the release weeks later. Twenty characters is about three
or four ordinary words — long enough that reproducing it is a quotation rather
than a shared subject, short enough that a lifted phrase does not fit under it.

**Comparing raw text.** A model asked for themes and given a comment returns the
phrase capitalized at the head of a sentence, or re-wrapped across a line break,
far more often than byte for byte. A raw comparison catches the one spelling
nobody writes and misses every spelling somebody does, while looking exactly like
a working guard.

## Consequences

- **The bound is tunable and moving it is a change to what this system promises.**
  It is a named constant in one module, argued here, and a pull request that moves
  it says which direction it is spending: down costs quiet weeks their summaries,
  up lets longer phrases cross. `tests/integration/test_a_small_n_summary_never_reuses_a_commenters_words.py`
  drives it from both sides, one character apart, so neither direction moves
  silently.
- **A week can be refused for ever, and nothing surfaces that.** If a provider
  keeps answering with the same quotation, the week retries weekly and stays
  empty. What an operator sees is a `failed` count from the walk and a warning
  naming the section, the week and the bound. That is the same visibility a
  provider outage gets and no more; a per-week alarm is E6's or §6.1's to build if
  it is wanted, and this record does not claim one exists.

  > **Amended 2026-09-09 by this ticket's security review: the trigger is not only
  > the provider's.** The paragraph above reads as a statement about model
  > flakiness, and the more reachable case is a **student**. A commenter in a quiet
  > week who writes a phrase the summary will inevitably contain — a distinctive
  > twenty-character run naming the week's own subject, or, more simply, a sentence
  > lifted from the prompt's instructions — makes every answer about that week
  > share a run with a comment it was fed. The guard then refuses on every retry,
  > for ever, with no cap and nothing on the report saying a summary was owed. One
  > student can take their own week's summary away from their instructor, and can
  > do it on purpose.
  >
  > **In development it is deterministic rather than merely possible.** `mock-ai`'s
  > themes-only prose contains "below the reporting threshold" — twenty-nine
  > characters normalized, comfortably over the bound — so a comment carrying that
  > phrase refuses its own week's summary on the development stack every time.
  >
  > **Nothing is built for it here, and the reason is the direction.** The failure
  > is denial: a week loses a summary, and no comment is ever disclosed by it. A
  > cap — store the answer after N refusals, or relax the bound — spends the ruling
  > to buy back a summary, which is the trade this record already refuses under
  > "store it anyway and log the violation". Detecting the planted phrase means
  > deciding what a student may write, which is §3.3's question and not this one's.
  > So the residual is accepted, named, and left: **visibility for a
  > permanently-refused week lands with the job observability surface** (§6.1's
  > console, which already reads this walk's `written`/`failed` answer), and that
  > is where "this section-week has been failing since October" belongs rather than
  > in a cap inside the guard.
- **The refusal is not an `AIGatewayError` and is caught beside one.** The provider
  answered, in time, in shape; what failed is compliance. The two are logged in
  different sentences on purpose — a run of refusals is a prompt or a model not
  honouring the ruling, which is a different thing to act on than a provider that
  is down.
- **Nothing the guard raises or logs carries a comment, a summary or a theme
  label.** `_reused_run` answers a *length*, deliberately, because the caller puts
  it in a job log and SPEC §10 keeps student words out of one. It is the same rule
  `summarize_stream` already states for its own refusals.
- **The eval set is pinned to `summary.v1` and is unaffected**, because the summary
  eval task is a deferred slot (`tests/evals/registry.py` gives it `cases=()`) and
  its cases are graded offline against constructed answers rather than rendered
  prompts. When that slot acquires a live floor, the small-N family will need its
  own pin at `summary.v2`, and this sentence is the note that says so.
- **`mock-ai` gained a branch and the development stack exercises the ruled
  behaviour.** It dispatches on a fragment of the v2 instruction read out of the
  prompt's *head*, before the comments boundary, so nothing a student typed can
  put the mock into themes-only mode for its own week — the protection
  `stream_asked_about` already has, for the same reason.

  > **Corrected 2026-09-09 by this ticket's security review: that was true of the
  > boundary the code should have taken and not of the one it took.** `answer_for`
  > cut the head at `rfind(SUMMARY_MARKER_LINE)` — the *last* copy of the marker —
  > and the summary prompt tells the model in as many words that a comment may
  > contain "another copy of this marker". A student who wrote one pulled every
  > comment ahead of it into the head, so both things read out of the head became
  > partly student text: the small-N mode, and the stream. Measured both ways
  > against the same input; before the change it flipped the mode and answered a
  > `course` prompt for the `instructor` stream, and after it does neither. The
  > boundary is `find` now, which is always the template's own copy. The direction
  > was deny-only — a comment could refuse its own week's summary or send the
  > answer to the wrong heading, never reveal anything — and it reached the mock
  > alone, which ADR 0113 keeps out of every deployment.
- **The guard is scoped to small-N weeks and applying it more widely would be a
  change, not a tightening.** Above the threshold the raw comments are on the
  report under their own heading, so a summary echoing one discloses nothing; a
  guard applied to every week would take ordinary weeks' summaries away whenever a
  model quoted a phrase, which reads as caution and is a loss.
