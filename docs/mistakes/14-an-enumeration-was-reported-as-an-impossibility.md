# Entry 14. An enumeration was reported as an impossibility

**Caught: 3**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(In E0-11, and it decided how an objection was argued rather than
whether to file one. `docs/disputes/E0-11-01.md` claims that no rule can accept the
`CHAIR → CHAIR` edge E0-09's properties require and refuse the one E0-11's matrix
requires refused. The tempting way to support that is a list of implementations
tried, and this entry forbids it — so the objection says plainly "one
implementation, and then I stopped", and the argument is from the **construction of
the two rows**: both are built by the same `graph.node` helper, each with its own
new person and its own new department, so they are identical in every column any
rule could read. That is an argument from the mechanism, which is what this entry
asks for in place of a longer list, and it is checkable by a fresh arbitrator
without running anything.)*

**What happened.** In E0-06, the guard that refuses a naive datetime has to sit
on the column type, and the test module's fixture could not seed a decorated
type. Four implementations were tried and measured — a `TypeDecorator`, a
`DateTime` subclass, a hybrid of the two, and putting the guard in a service —
and the objection filed in `docs/disputes/E0-06-01.md` generalised from them:
"no implementation that satisfies criterion 4 can get past `invented_value`."

That is false. A type subclassing psycopg's `_PGTimeStamp` survives
`adapt_type`, so the `isinstance` check passes *and* the guard runs, and the
module passes 18 for 18 with no fixture change. The arbitrator found it by
reading `adapt_type` and running it — the same method the objection had used for
its own four options and abandoned at the moment it generalised.

**Root cause.** Treating a search that stopped as a search that finished. Each
of the four options was measured honestly; the sentence joining them was not
measured at all, because there was nothing to run — which is exactly why it went
in unchecked while the four claims around it were verified.

**Consequence.** A false universal in a durable record. The dispute file is read
by a fresh arbitrator with no context, and had it been believed, the ruling would
have rested on it. The correct position was available and narrower — the only
implementation the fixture admitted was built on a private, driver-specific class
— and it won the dispute on its own. The overclaim added nothing and cost the
record a correction.

**Rule.** Do not write "no X can" from a list of the X you tried. Say what you
tried and what it did, and let the boundary of the search be visible: "four
shapes, all measured, all fail" is honest and is usually enough to decide. If a
universal is genuinely load-bearing, it needs an argument from the mechanism —
here, from what `adapt_type` does — not a longer list.

---
