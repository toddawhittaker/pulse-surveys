# Entry 50. A threshold that exists to protect people was crossed by a count of something else

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E4-04 built SPEC §4's cumulative release: comments held back
from a week too small to show are released later, in one batch, once the term has
accumulated enough of them. §4 names the trigger in one sentence — cumulative
comment volume against the configured n-threshold — and the first implementation
wrote exactly that, a `count(*)` of held comment answers compared against
`Settings.n_threshold`.

The threshold is not denominated in comment answers. Everywhere else in the
product it is a count of **responses**, which is what makes the small-N promise a
promise about people: below it an instructor sees nothing, at or above it any one
comment could have come from any of at least that many respondents. SPEC §3.2
gives every response two comment items, so the two units differ by a factor of two
before anybody writes an unusual survey — and the held set spans several weeks, so
a term's worth of one determined student's comments crosses a threshold meant to
guarantee a room full of them. A volume-only gate can therefore release a batch
whose whole author set is three people, or one.

The security round found it. The fix keeps §4's literal count and adds two legs
that have to hold with it: the distinct people behind the unreleased held comments
must reach the threshold, and those comments must span at least two distinct
under-threshold closed weeks. The respondent leg is the effective floor and
subsumes the other two, and all three are written out anyway so that each stays
visible the day another's denominator changes. ADR 0152 records the reading, and
the departure from §4's literal words went to the owner as an open question rather
than into a spec edit made in passing.

**Root cause.** The comparison was transcribed from the specification's sentence
rather than derived from the guarantee the specification is making. Both sides of
`>=` were numbers about comments, so nothing in the code, the tests or the review
of the arithmetic looked wrong; the unit mismatch lives in the gap between what
the number counts and what the threshold promises, and that gap is stated in a
different section of the spec from the sentence being implemented.

**Consequence.** Caught before merge, so nothing shipped. Had it shipped, the
failure would have been silent and unrecoverable in the direction that matters: a
release is permanent, a released comment cannot be un-shown (ADR 0146), and the
instructor reading the batch would have had a candidate set far smaller than the
one §4 promises with no signal that anything was unusual.

**Rule.** A threshold is a promise about a candidate set — "whoever wrote this is
one of at least *n* people" — so the number compared against it has to be a count
of the things the promise is about. Before writing the comparison, say the unit of
each side out loud: a count of answers, of rows, of events, is not a count of
people, and a design that gives one person several of them makes the two diverge
by a factor nobody states.

Two halves worth keeping separate:

- **The unit lives with the guarantee, not with the sentence being implemented.**
  Read the section that says what the threshold protects, not only the section
  that says when it fires.
- **Where the specification names the wrong unit, hold the conservative side.**
  Release strictly less than the literal words require, never more; write the
  literal condition out as its own leg so the departure is visible in the code;
  and put the choice to the owner as an open question, because narrowing a rule
  the spec states is a decision the spec has to catch up with.
