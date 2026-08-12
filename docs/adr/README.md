# Architecture decision records

A record of construction decisions that [`docs/SPEC.md`](../SPEC.md) does not
answer and that a reasonable engineer might have made differently.

## When to write one

Both halves have to be true: the spec is silent, **and** the choice is genuinely
contestable. Choosing a JSON library needs no record. Choosing how identity
separation is enforced in the database does.

Write it in the same pull request as the decision, not afterwards. An ADR
written later is a reconstruction, and reconstructions leave out the option that
seemed obvious at the time and turned out to be wrong.

## When not to write one

- **The spec already decides it.** Link to the spec section instead. An ADR that
  paraphrases a spec section is noise that makes the real ones harder to find.
- **The decision contradicts the spec.** An ADR is not sufficient and not the
  right instrument. Raise it, and update the spec — a record of having gone
  around the spec is not the same as the spec being right.

## Format

`NNNN-slug.md`, four sections, under a page:

1. **Context** — what forced a choice, and which spec section left it open.
2. **Decision** — what was chosen, stated plainly.
3. **Alternatives rejected** — each with the reason it lost. This is the section
   that earns the document; a list of alternatives with no reasoning is a list.
4. **Consequences** — what this costs, what it constrains later, and what has to
   be true for it to keep working.

Number sequentially, never reuse a number, never renumber. A superseded record
stays where it is with a line at the top pointing at its replacement.

## Records

| # | Decision | Status |
|---|---|---|
| [0001](0001-identity-separation-by-database-role.md) | Identity separation enforced by database role and grant | Accepted |
| [0002](0002-ci-gates-ship-tolerant.md) | CI gates ship tolerant and name the seam that enforces them | Accepted, recorded retroactively |
| [0003](0003-deferred-authz-seams-fail-closed.md) | Deferred authorization seams fail closed by raising | Accepted |
| [0004](0004-agent-roster-mechanism.md) | Agent roster mechanism: hooks, computed gating, session-scoped warmth | Accepted |
