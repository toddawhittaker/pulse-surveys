# 0054 — A fail-open classification names the floor in its prompt version and model ID

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-13

## Context

SPEC §3.3 gives the validity check the one sanctioned fail-open in this codebase:

> Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor
> applies and the submission is accepted, then classified async (fail open, never
> block a student on an outage).

So on an outage the character heuristic decides, and what it decides is a
`CommentValidityOutput` like any other — E2's submit path has one shape to read,
and §3.3 gates participation on the verdict whichever produced it.

Every one of those objects carries a prompt version and a model ID, required, and
every one of them is stored on a `classification` row. §7.4 says what the pair is
for: "every classification stores prompt version and model ID for
reproducibility", and the single-shot boundary rests on "a specific prompt version
and model ID produced a specific classification for a specific comment".

A floor result has neither. No prompt was rendered and no model was asked. The
question this record answers is what the two fields hold when the thing they name
did not happen — and it matters because E0-13's definition of done sends the
security review after exactly this distinction: "the fail-open path failing *open*
in the intended sense — accepting the submission — rather than open in the sense
of skipping a safety classification silently."

The two are indistinguishable from the caller. Only the record can tell them
apart.

## Decision

**A floored classification records `character-floor` as its prompt version and
`no-model` as its model ID.** Both are constants in `app/ai/tasks.py`, and
neither is a value a real run can produce:

- `character-floor` is not a path stem under `app/ai/prompts/`. ADR 0031 makes a
  stored `prompt_version` "the prompt file's path stem … so the stored value
  names exactly one immutable file with no lookup table between them", so a
  reader resolving this one against that directory finds nothing — which is the
  true answer.
- `no-model` names no model, and §9.3's eval comparisons are between model IDs,
  so a floor row falls out of those comparisons rather than distorting one.

Both fields stay `NOT NULL` and both stay required on the contract. The floor
fills them with a description of itself rather than with nothing.

## Alternatives rejected

**The prompt version and model ID that a real call *would* have used.** The
cheapest to write, and it produces a record that says a model classified a
comment it was never sent. Rejected on §7.4 directly, and on what it costs E2:
the async re-classification §3.3 promises has to find the comments a model has
not actually judged, and if every row already looks classified there is nothing
to find. The same shape on the moderation path (§6.2) would be a safety
classification that never ran, filed as one that did.

**A nullable prompt version and model ID, empty on a floor row.** Rejected in
E0-12 already, for the whole contract: ADR 0031 records that "an optional one
gives every reader of the model an auditability field and every record written
through it permission to carry nothing, which is the shape that reads as a
guarantee and is not one". Making them nullable for one case is that shape
arriving through the side door — and every reader of a `classification` row would
have to branch on null.

**A separate boolean column, `fail_open`, beside a real-looking pair.** Two
places to look and one of them optional. It also leaves the pair itself a
falsehood: a row saying `validity.v1` / `gpt-4o-2024-11-20` with a flag beside it
saying "except not really" is worse than a row that simply says what happened,
and anything reading only the pair — an export, an eval fixture, §6.1's drift
panel — reads the falsehood.

**A fourth verdict, `unknown`, so the floor reports its own uncertainty.**
Rejected by the contract before it reaches here: `CommentValidityOutput`'s
docstring already refuses it, because "a stored `unknown` would be a
classification that never happened", and §3.3's participation gating has no
branch for a fourth value.

## Consequences

**A reader can tell the two apart with no schema knowledge**, which is what
`test_a_timed_out_classification_is_not_recorded_as_one_the_model_produced`
asserts — and it asserts a *difference* rather than these particular strings, so
the shape is pinned and the spelling stays this record's to change.

**These two strings are now load-bearing in a way a rename would break quietly.**
E2's async re-classification finds the floor rows by them, and §6.1's drift panel
will group by them. A change to either is a data migration over rows already
stored.

**Amended 2026-08-18: a marker is only a marker if nobody else can write it.**
E0-13's second review pass measured a provider answering `"model": "no-model"` —
the model half of this pair, in the endpoint's own response envelope — and the
gateway recording it verbatim. The row was then indistinguishable from a floored
one, so the very query this record exists to serve ("which verdicts did the
character floor decide") selected rows a model had answered. The model marker
therefore lives in `app/ai/gateway.py` as `NOT_A_MODEL`, because the gateway is
the module that can make it unforgeable: `_reported_model` refuses a
provider-reported name that claims it, along with one that is empty, longer than
`MODEL_ID_LIMIT`, or carries control characters. `app/ai/tasks.py` imports the
constant rather than spelling it again.

The *prompt* half needs no such guard and deliberately has none: a provider never
supplies a prompt version at all — `_payload_model` does not declare the field, so
an answer carrying it is refused as a shape violation (ADR 0031). The asymmetry is
worth stating, because it is the reason one marker moved modules and the other did
not.

**A stored prompt version no longer always names a file.** Anything resolving one
against `app/ai/prompts/` has to tolerate a miss, and the miss means "no model was
asked". That is a real cost of this decision, and the alternative was a pair that
lies.

**The floor's verdict is `substantive` or `insufficient` and never `nonsense`.**
Not part of this decision but recorded beside it, because the two land in the same
row: length cannot tell keyboard mashing from a terse real answer, and calling a
short comment `nonsense` during an outage would reduce a section's validity rate
(§3.3) over something the student did not do.
