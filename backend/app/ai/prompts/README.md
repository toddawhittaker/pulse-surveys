# Prompts

One file per AI task and version, under SPEC §7.4's task inventory. The gateway
(E0-13) loads a prompt from here by name; nothing else reads this directory.

## The naming scheme

```
<task>.v<N>.md
```

- `<task>` is the task's word from §7.4's table, lowercase, one word:
  `validity`, `moderation`, `summary`, `draft`, `draftcheck`.
- `<N>` is a whole number starting at 1, counting up per task. Versions are per
  task, not global, so `validity.v3.md` and `moderation.v1.md` sit side by side
  quite normally.
- The file's stem — `validity.v1` — is the string a classification stores as its
  `prompt_version` (`app/ai/contracts.py`). So a stored version identifies
  exactly one file, and no lookup table is needed to get from one to the other.

There is no `latest.md` and no unversioned `validity.md`, deliberately. A name
that points at a moving target is a name whose next edit rewrites what every
stored classification claims to have come from.

## The rule that makes a version mean something

**A prompt file is immutable once it is committed.** To change a prompt, add the
next version beside it and leave the old file alone. Both then exist, and a
classification recorded against `validity.v1` can still be reproduced after
`validity.v2` ships.

§7.4 is why: "every classification stores prompt version and model ID for
reproducibility", and the threat and self-harm classifier "must be auditable,
meaning a specific prompt version and model ID produced a specific classification
for a specific comment". A version string pointing at a file whose contents have
since changed reproduces nothing, and the audit record for a §6.2 safety
classification becomes a claim nobody can check.

Two edits are exempt, because neither changes what the model was sent: fixing a
typo in a comment that is not part of the prompt text, and reflowing whitespace
the model never sees. Anything that could change an output is a new version.
The reasoning, and the alternative that was rejected, are in
[ADR 0032](../../../../docs/adr/0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md).

## What is here now

| File | Task | §7.4 output | Added by |
|---|---|---|---|
| `validity.v1.md` | Comment validity | substantive / insufficient / nonsense | E0-12 |

The other four tasks — moderation, weekly summary, response draft, draft check —
have contracts in `app/ai/contracts.py` and no prompt yet. Their prompt content
belongs to E2, E4, E6 and E7 respectively, and each adds its `v1` here under the
scheme above.

## Writing one

A prompt states the task, the closed set of answers where the task has one, and
the JSON shape to return. The shape is the matching model in
`app/ai/contracts.py` and that model is the authority: the gateway validates
against it and retries on a shape violation, so a prompt that describes a
different shape produces retries rather than results.

Whether a prompt is any *good* is not settled by reading it. §9.3 answers that
with versioned eval sets and per-task precision and recall floors, and a new
version has to clear its task's floor before it ships.
