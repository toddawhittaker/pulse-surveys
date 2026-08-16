# 0032 — Prompts are named `<task>.v<N>.md` and a committed prompt file is never edited

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-12

## Context

[SPEC §7.4](../SPEC.md) says "Prompts are versioned in-repo" and
[§13](../SPEC.md) places them in `app/ai/prompts/` as "versioned prompt
templates, one file per task+version". E0-12's scope repeats it and asks for the
scheme to be documented. Neither says what the scheme *is*.

The reason it needs deciding rather than defaulting: a stored `prompt_version`
(ADR 0031) is only worth recording if the text it names can still be read. §7.4's
justification for the whole single-shot boundary is that "a specific prompt
version and model ID produced a specific classification for a specific comment",
and §6.2's Care queue holds classifications where that record has to survive a
conversation with a student, a dean, or the Office of Community Standards.

The obvious layout — one `validity.md` per task, edited when the prompt changes —
looks versioned because the repository has history. It is not: the stored version
string points at a file whose contents have since changed, so the audit record is
a claim nobody can check without reconstructing which commit was deployed on the
day a classification was written.

## Decision

**Scheme:** `<task>.v<N>.md`, flat in `app/ai/prompts/`. `<task>` is the task's
word from §7.4's table, lowercase and one word. `<N>` is a whole number from 1,
counted per task rather than globally. The file's stem — `validity.v1` — is the
string a contract stores as its `prompt_version`, so the stored value resolves to
a file with no lookup table between them.

**Rule: a prompt file is immutable once committed.** Changing a prompt means
adding the next version beside it and leaving the old file alone. Both then exist
in the tree, and a classification recorded against `validity.v1` can still be
reproduced after `validity.v2` ships. Two edits are exempt because neither
changes what the model was sent: a typo in surrounding commentary the prompt does
not include, and whitespace the model never sees.

No `latest.md`, no unversioned `validity.md`, and no `current` symlink. A name
pointing at a moving target is a name whose next edit rewrites what every stored
classification claims to have come from — the same defect as no version at all,
wearing a version's clothes.

The scheme, the immutability rule and the list of prompts on disk are written in
`backend/app/ai/prompts/README.md`, because four later epics (E2, E4, E6, E7) each
add a prompt here and none of them is written yet.

## Alternatives rejected

**One file per task, versioned by git history.** The cheapest option and the one
that arrives by default. Rejected because reproducing a classification then
requires knowing which commit was deployed when it was written, which nothing
records — and because a diff to a prompt file changes the meaning of rows already
in the `classification` table, retroactively and with nothing near those rows
showing it.

**A content hash as the version** — `validity.a3f19c.md`, or storing a hash of
the prompt text. Genuinely stronger on the property that matters: a hash cannot
be wrong about what the text was, and it makes an in-place edit detectable rather
than merely forbidden. Rejected for this epic on legibility. A hash is unreadable
in a Care-queue audit conversation, gives no ordering, and makes "which prompt is
newest" a question needing a tool. The immutability rule buys most of the same
guarantee at a fraction of the cost, and if it turns out to be honoured
inconsistently, adding a stored hash beside the version is a strictly additive
change.

**Semantic versions** — `validity.v1.2.md`. Rejected because there is no
meaningful distinction between a major and a minor prompt change: every edit that
could move an output is equally a new version as far as §9.3's eval floors are
concerned, and offering two dimensions invites the argument that a small edit
does not need a new file.

**A directory per version** — `prompts/v1/validity.md`. Works, and the test
suite accepts either. Rejected because versions here are per task rather than
global, so the directory would either be per task as well — two levels of nesting
for one file — or imply a global version that does not exist.

**A database table of prompt texts.** Rejected against §7.4's plain words,
"versioned in-repo", and because it would put the text a classification cites
outside code review and outside the diff that changes it.

## Consequences

**A prompt change is an add, never an edit**, so a pull request touching a prompt
shows a new file rather than a diff of the old one. The cost is real: reviewing
"what changed in the prompt" means diffing two files by hand, and the directory
grows monotonically. That is accepted — the whole point is that the old text
stays readable.

**Nothing enforces the immutability rule.** `tests/unit/test_prompt_directory_
layout.py` asserts that every prompt path carries a version and names no moving
target; it cannot see an edit to an existing file, because a repository is
allowed to have history. A CI check that refuses a diff to an existing prompt
file is the enforcing version of this rule and is not built here — it belongs
with E2, which is where the second prompt version and the first eval floor
arrive together. Stated plainly rather than left implied: today this is a
convention with a test behind only half of it.

**Retiring a prompt is a deletion decision with a retention question attached.**
Once classifications cite `validity.v1`, deleting the file breaks their audit
trail, so it may only go when the rows citing it have gone under §4's retention
period. Nothing checks this today.

**Prompt files ship as package data.** `pyproject.toml` names
`"app.ai" = ["prompts/*.md"]`, because the Dockerfile installs a wheel and
nothing else; without it the runtime image holds the contracts and no prompt.
