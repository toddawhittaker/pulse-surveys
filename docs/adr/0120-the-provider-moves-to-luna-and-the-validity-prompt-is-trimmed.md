# 0120 — The classifier moves to Luna, and the validity prompt is trimmed to v2

**Status:** Accepted
**Date:** 2026-09-02
**Tickets:** the Luna switch and prompt trim
**Supersedes in part:** [0118](0118-the-provider-configuration-splits-in-two.md) — its dated-snapshot paragraph; the preference stands and cannot be satisfied by this model.

## Context

Two changes ride together because they are measured together: a §9.3 eval run is
the only thing that says whether either was a good idea, and running one twice to
separate them costs about two hundred paid calls for a distinction nothing else
in the system draws. Both are about what reaches the model.

**The model.** The validity classifier ran on `gpt-5-mini-2025-08-07`. Luna —
`gpt-5.6-luna` — sits at or above it on the published intelligence index and
costs roughly thirty per cent less per run. Nothing about the change is forced;
it is a better model for less money on the one task this project currently pays
for, and the floors are re-measured against it either way.

**The prompt.** `validity.v1.md` was written as a first draft and reads like one:
its first nine lines are a title, two spec citations and a note saying the text is
provisional and that §9.3 will decide whether it is any good. None of that is an
instruction to a classifier, and all of it is sent, on every request, in front of
the student's comment. The same is true of the section symbols inside the rules,
which cite documents the model cannot read, and of a paragraph telling the model
not to return a prompt version or a model ID — dead text under the gateway's
structured-output mode, where the schema declares two fields and forbids extras,
so returning a third is not something the model can do.

Extraneous text costs accuracy on smaller models, and every token of it is paid
for on every classification. SPEC §7.4 makes a prompt versioned and ADR 0032
makes a committed one immutable, so improving one is adding a file rather than
editing a file, and that is settled. What is not settled anywhere is what belongs
in a prompt at all.

## Decision

**The real provider's model becomes `gpt-5.6-luna`**, in `.env.example` and on
the eval runner's workflow step. Luna serves the `json_schema` structured-output
mode the gateway requires — verified against the running endpoint before the value
was committed, not from documentation — so ADR 0118's constraint on which
providers can hold the real triple is met and no code path changes.

**`validity.v2.md` is added beside `validity.v1.md`, and
`app.ai.tasks.VALIDITY_PROMPT_VERSION` names it.** v1 is not edited and not
deleted. What v2 removes, and nothing else:

- the nine-line human header — title, spec citations, and the "a first draft"
  note. Documentation about the prompt, riding inside the prompt;
- every section symbol and citation inside the rules. Each rule's *reason* stays
  in plain words, because the reason is what makes a borderline judgement go the
  right way: "§3.3 refuses an insufficient comment to the student's face at submit
  time" becomes "An insufficient comment is refused to the student's face at
  submit time", which is the same fact addressed to a reader who cannot look
  anything up;
- the paragraph forbidding a returned prompt version or model ID, which the
  output schema already makes impossible.

What v2 keeps, and keeps byte-exact: the three verdict definitions with their
examples, every behavioural rule including the injection-instruction rule and its
worked example, the JSON-object instruction, and the entire closing boundary
passage. v2 was produced by slicing v1 rather than by retyping it, so the retained
regions are the same bytes rather than the same words.

**The closing passage's final sentence is load-bearing beyond the prompt.**
`mock-ai/app/rules.py` holds `MARKER_LINE` as exactly that line and extracts every
development-stack comment on it. Rewording or re-wrapping it leaves the mock
reading a boundary the prompt no longer has, and every classification on a
development stack answers the extraction-failure 500. So the line does not move.
The guard on that pair now follows `VALIDITY_PROMPT_VERSION` rather than naming
v1, because a guard pinned to an immutable file goes on passing after the tool has
moved off it — a guard aimed at the case it used to be about.

## Alternatives rejected, and why

**Editing `validity.v1.md` in place.** Cheaper and forbidden. ADR 0032 exists so
that a classification recorded against a version can be reproduced, and §7.4 rests
auditability on exactly that; editing the file turns every stored `validity.v1`
into a version naming text that no longer exists.

**Trimming further — dropping the rules' rationales, or the worked example on the
injection rule.** Tempting on the same token argument and rejected on what the
rationales are *for*. "Judge content, not length" without "many of these students
are writing on a phone in two minutes" is a rule with no way to resolve the
borderline case it exists for, and the injection example is the only place the
prompt shows what stripping an instruction looks like. The trim removes text
addressed to a *reader of the repository*; it keeps every word addressed to the
classifier.

**Keeping the do-not-return-a-version paragraph as belt and braces.** It reads as
harmless and is not free: it names two fields the model is otherwise never told
about, which is a way of suggesting them. The schema forbids extra keys and the
gateway rejects a payload carrying either, so the paragraph defends a door that
is already shut and mentions what is behind it.

**Moving the model without re-measuring the floors.** Not available. A floor is a
claim about a particular model, so the numbers are re-taken on Luna and the old
ones do not carry over.

**Changing the model and the prompt in separate tickets, each with its own eval
run.** The clean experiment, and it costs a second full run — about a hundred
paid calls — to attribute a change that nothing downstream attributes. The floors
gate the pair, not either half. Stated because it is the honest cost of taking
them together: if the numbers move, this record cannot say which change moved
them.

## Consequences

**The floors are re-measured and the old numbers are void.** They were taken
against a different model and a different prompt version, and either alone would
be enough to void them.

**The model identifier cannot be pinned, and that is a real loss rather than a
choice.** ADR 0118 argued for a dated snapshot over a floating alias, and
`gpt-5-mini-2025-08-07` was one. `gpt-5.6-luna` publishes no dated build: checked
on 2026-09-02 by listing the provider's models, by retrieving that model, and by
reading a completion's envelope — one bare identifier every time, where the
previous model's envelope resolved to its snapshot, and no `system_fingerprint`
to key on either. So the weights behind the configured name can move without
anybody editing anything, a floor breach and a model change are indistinguishable
from here, and nothing in the configuration can detect it. Both configuration
sites say so beside their entries, and `docs/tickets/e2/deferred.md`'s entry on
the three untied identifier sites records that this makes tying them necessary but
no longer sufficient. If a dated Luna build appears, pinning it is a
re-measurement.

**A stored `prompt_version` now takes two values across the table.** Rows written
before this change name `validity.v1` and resolve to the file that produced them;
rows after name `validity.v2`. That is the versioning scheme working rather than a
migration to perform, and anything comparing classifications across the boundary
has to read the version rather than assume one.

**The prompts README describes two files for one task**, with a column saying
which is rendered — and says in as many words that the column is a description of
`VALIDITY_PROMPT_VERSION` rather than a second source of truth, because a table
is a record and records drift.

**Nothing asserts what a prompt may not contain.** The trim is an argument, made
here, and no test would notice the header being added back. That is the same
state v1 shipped in — "nothing about this text is asserted by a test" was its own
line — and it is worth naming rather than implying: what the eval floors measure
is whether the prompt *works*, not what is in it.
