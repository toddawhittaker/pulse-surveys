# 0031 — Every task contract carries the prompt version and model ID, and the gateway supplies them

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-12

## Context

[SPEC §7.4](../SPEC.md) requires reproducibility in one sentence — "every
classification stores prompt version and model ID for reproducibility" — and
rests the whole single-shot argument on it: "the threat/self-harm classifier must
be auditable, meaning a specific prompt version and model ID produced a specific
classification for a specific comment."

The word in both places is **classification**. Two of §7.4's five tasks produce
one: comment validity and moderation. The other three produce a weekly summary,
a draft class response, and a list of themes a draft has not addressed. Read
strictly, the spec does not ask those three to carry anything.

E0-12 reads it more broadly. Its scope: "Every model carries the fields needed
for auditability: prompt version and model ID", and criterion 2: "Every model
requires prompt version and model ID; constructing one without them fails
validation." The test author noticed the gap and flagged it as a ticket
ambiguity rather than writing a narrower test.

There is a second question the spec does not answer at all, and it is the one
with teeth: **who fills the two fields in.** They can come from the model, in the
JSON it returns, or from the gateway, out of what it knows it sent.

## Decision

**All five task contracts carry both fields, required, inherited from one
`AiTaskOutput` base.** A weekly summary and a response draft are model output
that a human will later question — a summary that flattened a critical theme,
a draft that read as deflection — and the first question is which prompt and
which model produced it. That question has the same answer for all five tasks,
and a field that is present on three contracts and absent on two is a field
every reader has to check for.

**The gateway supplies both values; the model never reports them.** The prompt
tells the provider to return the task's output alone, and E0-13's gateway
validates against the contract with the two audit values filled in from what it
loaded and what it called. A model's own account of which prompt version and
which weights produced an answer is not an audit record — it is another
generated string, and a wrong one is indistinguishable from a right one.

**`prompt_version` is the prompt file's path stem** — `validity.v1` — so the
stored value names exactly one immutable file
([ADR 0032](0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md))
with no lookup table between them. **`model_id` is the provider's own identifier
for the model**, as the provider spells it, because §9.3's eval floors compare
runs of different models and a normalised name loses the distinction the
comparison is about.

## Alternatives rejected

**Only the two classifiers carry the pair**, which is the strict reading of
§7.4's sentence. It is defensible and it is cheaper: the summary, draft and
draft-check contracts would each lose two required fields. Rejected on three
grounds. The reproducibility argument does not actually turn on the word
"classification" — §6.1's drift panel samples model output for human spot-review,
and §5.3's response draft is the model output most likely to be argued about in
public, since it goes out under an instructor's name. §9.3 grows eval sets for
every task, and an eval case that cannot say which prompt produced it cannot be
compared against a later one. And splitting the rule means two base shapes and a
reader having to remember which is which, for a saving of two strings on three
models. If this turns out wrong, the correction is cheap in the same direction it
is cheap now: removing a required field from three contracts before they have
callers.

**A mixin applied to the two classifiers only**, keeping the pair optional
elsewhere. Rejected as the worst of both: every reader still sees an
auditability field on all five, and on three of them it may hold nothing —
`docs/MISTAKES.md` entry 2's shape, a convention that reads as a guarantee.

**Letting the model return the pair.** Rejected above. It also has a failure mode
worth naming: it works. A model asked for its own name will confidently supply
one, so the field is populated, nothing raises, and the audit record is fiction.

**Storing the pair only in E0-13's `classification` row and not on the
contract.** This is the narrowest reading and it nearly works for the two
classifiers, since that row is where §7.4 says the values live. Rejected because
§7.4 makes this same model the API response schema and the eval fixture: a
fixture on disk with no prompt version cannot be re-run against the prompt that
produced it, and there is no `classification` row behind a summary or a draft to
hold the values instead.

## Consequences

**Constructing any contract requires both values**, including in tests and eval
fixtures. Every eval case file therefore names the prompt and model it came from,
which is what makes a case comparable across a prompt change.

**E0-13's gateway assembles the object rather than handing the provider's JSON
straight to `model_validate`.** It parses what the provider returned, adds the
two values it knows, and validates the result. That is a specific instruction to
the next ticket and the reason this record exists rather than a comment.

**The contract cannot enforce this decision, and `extra="forbid"` does not close
it.** An earlier version of this record claimed it did — that a provider
volunteering a `model_id` of its own would be refused. That was never true, and
was corrected after being run rather than reasoned about:

```
ModerationOutput.model_validate(
    {"verdict": "clear", "model_id": "i-am-a-liar-3000", "prompt_version": "moderation.v1"}
)
→ model_id='i-am-a-liar-3000'
```

`extra="forbid"` refuses keys the model does not *declare*. `prompt_version` and
`model_id` are declared fields, so a provider-supplied value is not extra — it is
the field, filled in by the wrong party, and it validates and round-trips
cleanly. Which value survives then depends entirely on the order in which E0-13
merges its own values over the parsed payload, and nothing in the contract or in
this ticket's tests constrains that order.

**So this is an instruction to E0-13, not a property of the contract.** The
gateway must reject a provider payload that contains either key, *before* merging
anything into it, and treat that as the shape violation §7.4 has it retry on. Not
overwrite quietly: a model returning an audit field is a model doing something it
was told not to do, and on the moderation path the value it invented would
otherwise land in a §6.2 audit record. The prompt instruction that the model must
not return these values (`prompts/validity.v1.md` carries it) is a request, and a
request is not a control.

**The check belongs in the gateway, not in a second contract.** The obvious
alternative — a provider-side model holding only the task's output, merged into
the task contract afterwards — is the fork §7.4 forbids: two shapes for one task,
free to drift, which is exactly what makes an eval case stop being a typed object
about the thing that runs. One shape, and one gateway that refuses to be told
what produced it.

**The pair is not enough to reproduce a run on its own**, and this record does
not claim it is. Temperature, provider-side model updates behind a stable
identifier, and the comment text itself all sit outside these two fields. What
they give is the ability to say which prompt text and which named model were
asked — which is what §7.4 asks for, and no more.
