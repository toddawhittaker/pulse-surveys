# 0030 — A verdict is an `enum.Enum` whose value is the stored token

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-12

## Context

[SPEC §7.4](../SPEC.md) gives two of the five AI tasks a closed set of answers:
comment validity returns substantive / insufficient / nonsense, and moderation
returns clear / harmful / privacy / nonsense / threat / self-harm. E0-12's scope
says to "model both as enums, not free strings", and its first acceptance
criterion asks for "enum-typed verdicts".

So *that* it is a closed set is settled. Three things the spec does not settle
are decided here, and a reasonable engineer could choose differently on each:

- whether the closed set is an `enum.Enum`, a `enum.StrEnum`, or a
  `typing.Literal`;
- whether the value that reaches JSON, the database and an eval file is the
  member's name or a separate string;
- how `self-harm` — the one verdict in either set whose spec spelling is not a
  single word — is written.

These matter beyond style. §5.2 routes on the moderation verdict, §3.3 gates
participation credit on the validity verdict, §9.3 compares eval cases against
what a task returned, and §6.2's Care queue exists to receive two of the six.
Every one of those is a comparison, and what is being compared is decided here.

## Decision

Each closed set is a plain `enum.Enum` subclass whose members carry an explicit
lowercase string value, and that value is the token stored, serialised and
compared everywhere outside Python:

```python
class ModerationVerdict(enum.Enum):
    CLEAR = "clear"
    HARMFUL = "harmful"
    PRIVACY = "privacy"
    NONSENSE = "nonsense"
    THREAT = "threat"
    SELF_HARM = "self_harm"
```

Three parts to that:

**Plain `Enum`, not `StrEnum`.** A `StrEnum` member *is* a string, so
`verdict == "clear"` is true and type-checks. Under a plain `Enum` the same
comparison is an error mypy's `strict_equality` reports — and `app.ai.contracts`
is in the strict profile, so it is reported. That is the property being bought:
routing code must compare members, not spellings.

**The value is explicit and is the wire token.** It is not derived from the
member name, so renaming a member in Python cannot silently rewrite what is
stored, and a stored token cannot be changed without a visible edit to this file
next to every reader of it.

**`self-harm` is written `SELF_HARM = "self_harm"`.** Underscore rather than the
spec's hyphen, because the value is also a Python-adjacent identifier in eval
files and, in E0-13, a database value; a hyphen invites a spelling drift between
the two the first time somebody writes `self-harm` by hand. `THREAT` and
`SELF_HARM` are two members and may never become one, nor may one be made an
alias of the other — §6.2's queue distinguishes a threat to another person from a
student at risk, and §9.3's recall floor is measured over both.

## Alternatives rejected

**`typing.Literal["clear", "harmful", ...]`.** This is the strongest of the
alternatives and deserves the argument stated rather than dismissed. A `Literal`
is a closed set, pydantic refuses a value outside it, it needs no import to read
in a JSON file, and it is lighter to write. The test author flagged that it
refused a `Literal` on the ticket's wording and that preferring one is a
legitimate position.

Rejected on three grounds, none of which is the ticket's wording alone. A
`Literal` has no *name* to import: §5.2's routing and §9.3's eval cases would
compare against a bare string, so a typo in a caller — `"self-harm"` where the
contract says `"self_harm"` — is a comparison that quietly never matches rather
than a name that does not resolve. A `Literal` has no members to iterate, and the
admin console's drift panel (§6.1) and any eval report needs the set enumerable
at runtime. And an enum gives the set one home to change; a `Literal` spelled
into a second contract later is a second copy of the set.

**`enum.StrEnum`.** Convenient exactly where it is dangerous: it makes a verdict
interchangeable with a string, which is the property E0-12's "not free strings"
exists to remove. It would also make `strict_equality` blind to the caller that
compares against a literal spelling.

**Deriving the value from the member name**, via `auto()` and `_generate_
next_value_`. Rejected because it couples the persisted token to a Python
identifier: a rename that reads as a refactor becomes a data migration, and
nothing in the diff says so.

**Keeping the spec's hyphen as the value.** Considered seriously, since matching
the spec's own spelling has real value in an audit conversation. Rejected because
the value ends up in more machine contexts than human ones, and the hyphen is the
form most likely to be retyped inconsistently. The hyphenated spelling stays in
the spec, and in a prompt's *prose*; the value is the token, and a prompt's
returned-JSON example spells the token. See the consequence below — an earlier
version of this sentence said "in the prompt text" without that distinction,
which is a sentence a prompt author could act on and be wrong.

## Consequences

**Callers write `.value` at the boundary.** Storing a verdict in E0-13's
`classification` row and putting one in a JSON payload both spell the value
explicitly. That is the intended cost of not having a verdict be a string.

**A comparison against a bare string is a type error rather than a silent
`False`.** This only holds where mypy runs strictly. `app.ai.contracts` and
`app.services.*` are in the strict profile; a comparison in a router or a job is
checked less strictly, and this record does not claim otherwise.

**The spec's `self-harm` and the stored `self_harm` are two spellings of one
verdict**, and anyone reading a database row against §7.4's table has to know
that. It is written down here and in the enum's own docstring, which is the whole
of the mitigation.

**A prompt that shows the hyphen in its returned JSON produces a shape violation
on every self-harm classification**, and this is the sharpest edge in this
record. Verified rather than reasoned about: `"self_harm"` validates and
`"self-harm"` is refused. §7.4's table spells it with a hyphen, so an author
writing E6's moderation prompt from the spec, copying the table's wording into
the example object, produces a prompt that works for five verdicts and fails for
the sixth. The failure lands where it is least affordable — §5.2 routes self-harm
to Care immediately, §9.3 makes that recall floor the strictest gate in the
suite, and unlike §3.3's validity check, moderation has no sanctioned fail-open,
so the classification retries and then surfaces as an error rather than
defaulting to anything.

The requirement, stated for whoever writes that prompt: **a prompt's example
object spells verdicts exactly as the enum's values do, underscore and all**, and
the enum in `app/ai/contracts.py` is the authority rather than §7.4's prose.
`prompts/validity.v1.md` already does this, and the prompt directory's README
says so under "Writing one". A test asserting a prompt's examples parse against
its contract is the enforcing version of this and is not built here; it wants the
prompt-to-contract mapping that arrives with E0-13's gateway.

**Adding a verdict is a contract change with visible blast radius.** The enum is
imported by the routing in §5.2, the eval cases in §9.3 and, from E0-13, the
persisted classification. That is the point of §7.4's one-model rule: a new
member breaks the callers that do not handle it at type-check time.
