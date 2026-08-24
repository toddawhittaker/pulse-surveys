# Entry 15. A property test's generator excluded the case its own docstring named

**Caught: 4**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(In E0-15's tests, and about a stated scope rather than a strategy —
this entry's last sentence is the one that applied: "a stated bound is a scope, and
an unstated one is a false claim of totality". Two tests carry a bound they cannot
remove, and stating both is what got one of them lifted. "No member is dropped" has
no total on the NRPS surface to check against, so it is checked against the users the
launch page will sign a launch for, which is a lower bound and says so. The mid-term
add was the second: with no enrollment-window field named anywhere, the test could
only look for a member value that parsed as a date and assert that the dates were not
all equal. Writing that bound down is what sent it to Todd as a question rather than
leaving it as a weak green test, and the ruling added the field — so the assertion is
now over a named `start`, within one section. **Both bounds have since moved, and
stating them is what moved them.** The enrollment field arrived from the first
ruling, and a reviewer then measured that "not all together" was satisfied by an
early add — so the assertion is now the shape of a late arrival: one member later
than every other, over a cohort of at least two. And the lower bound on "no member is
dropped" was measured too weak to keep alone; the claim now rests on the seed's own
numbering, with the lower bound kept beside it because the two fail for different
reasons. What is left is stated for the same reason as before: E0-15 asks that the
added member's `start` fall after its *section's* start date, and no section start
date is published on this surface at all — the section's calendar is derived
tool-side from its code and the term's start-letter map.)*

*(The rank rule changed what both supervision generators can produce,
and the docstrings describing them were written against the old space. Cycles no
longer run to length eight but to six, because six ranks is the longest chain that
can exist; the forest no longer draws every role at every position but a strictly
lower role than its parent; and the top rank is excluded from the forest for the
grain reason in entry 13. Each of those is a narrowing that a reader would have
gone on believing was not there, so the "what these generators do not reach" lists
were rewritten against what the generators now actually draw rather than amended
at the edges.)*

**What happened.** E0-07's parsing suite carries a property for the definition of
done's "parsing is total: no exception type that escapes as a 500". Its docstring
listed the leaks it refuses and put `ValueError` out of `int()` first. It
generated `st.text(max_size=12)`.

The string that produces that `ValueError` is a start letter, more than four
thousand digits and a modality suffix: CPython caps integer-from-string
conversion at `sys.get_int_max_str_digits()`, 4300 by default, and
`parse_section_code("R" + "9" * 4301 + "WW")` raises `builtins.ValueError`
rather than the service's own error. Section codes come from the LMS roster feed,
so it is reachable input, and nothing shortens the value on the way in — a
`String(16)` column is not enforced in Python, and the derived columns are
`NOT NULL`, so the parse always runs before any row exists. The suite was green.
`/security-review` found it.

**Root cause.** The bound on the generator and the claim in the docstring were
written at different moments and never read against each other. Twelve characters
is a reasonable size for a section code, which is exactly why it looked like a
detail rather than a decision: it silently redefined "arbitrary text" as "text
short enough to be a section code", and the counterexample lives on the other
side of that line. A property test states its claim in the docstring and its
scope in the strategy, and only the second one runs.

It is entry 3's family — a test that passed for a reason unrelated to what it
asserted — but the mechanism is its own and worth naming separately: not an
absence that something else satisfied, and not a pattern that matched nothing. An
input space narrowed to where the assertion happens to hold.

**Consequence.** A guarantee about untrusted input, asserted by a test named for
it, over a space that could not contain the failure. Had it shipped, the first
malformed roster value of that shape would have been a 500 on the sync, with the
suite still reporting the case as covered. The repair was not simply a larger
`max_size` either: `st.text()` will not assemble that string by chance in three
hundred examples, so widening the bound would have put the counterexample inside
the declared space and left it just as unreachable — the same defect behind a
bigger number.

**Rule.** For every property, read the strategy against the docstring and ask
which named case the generator cannot produce. If the claim is about a boundary —
a limit in the standard library, a column width, a protocol maximum — generate
*around that boundary explicitly*, drawing from a band that straddles it, rather
than trusting a wide range to wander into it. Where a bound stays, say in the
docstring what it does not reach; a stated bound is a scope, and an unstated one
is a false claim of totality.

**Entry 28 is this entry's sibling and not a duplicate of it.** Here a claim
exists and the generator narrowed under it, so the two can be read against each
other in one file. There no claim exists at all: a shared driver that speaks a
protocol correctly makes the malformed half of every guard unreachable, and there
is nothing to compare it with.

---
