# Entry 13. A hazard was written down and worked around in only one of the two places facing it

**Caught: 20**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*14 instances recorded; the 3 most recent are below. The earlier 11 are in this file's git history and in the pull requests they cite.*

*(In E0-16's second review pass, and the hazard is a duplicated
request parameter. RFC 6749 §3.1 forbids one, the provider refused one, and the
rule ran over **one collection at a time**: `form_body` read the body and never
looked at the query string, so a name sent once in each was two singletons rather
than one duplicate. Measured: a token request with a valid body and
`?code=bogus&grant_type=bogus` on the URL answered 200 with an `id_token`, and a
login with `?sub=<one person>` and `sub=<another>` in the body issued a code. The
rule now runs over the query and the body together, and values still come from
the body alone, because honouring a query parameter would add the second place
rather than close it. The same hazard was open at a third place, in the opposite
direction and found in the same pass: the registered redirect URI was not checked
for a query already carrying `code` or `state`, so a provider that refuses
duplicates inbound would have **emitted** one — `?state=preset&code=…&state=…` —
and a client comparing the first `state` would compare against a value it never
generated. Refusing a shape on the way in says nothing about producing it on the
way out, and that is the direction this entry is easiest to miss in.)*

*(In E0-16, an hour after the fifteenth and found because of it.
A review pass over the finished provider found that a `code_verifier` carrying a
character outside ASCII crashed the comparison rather than being refused by it —
RFC 7636 computes the challenge over ASCII octets, so `.encode("ascii")` raises
and the container answers 500. The fix was one check. This entry is why the next
question was "what else faces the same hazard", and the answer was the
`code_challenge`, which is the *other* half of the same comparison and was
crashing `secrets.compare_digest` at the token endpoint from a value the
authorization endpoint had accepted an hour earlier. Both were reproduced before
and after. The repair is one function, `pkce_shape_problem`, called at both ends,
because RFC 7636 gives the two parameters one ABNF production and two copies of
it could disagree about the one thing they exist to be compared against.)*

*(Writing E0-33's tests. Its item 3 wants the view *set* compared
with what the migrations wrote, which is the direction
`test_identity_separated_views.py` does not have — it asks whether every view in
the catalog is created by a file under `views_sql/`, and never whether every view
a file creates is in the catalog. Writing that second direction in the new catalog
module meant a second copy of the `CREATE VIEW` regex, and that regex is not
incidental: its word boundary is the subject of an incident under entry 3, where
a sweep for a view's bare *name* was satisfied by the `GRANT` beside it. So the
name extractor was factored out of `creates_view`, which is now one line over it,
the new test went into that module beside it, and the `DROP VIEW` sweep the new
direction needs was added to the same self-test that already runs the create
sweep against what it must catch and what it must allow. **A regex whose
correctness took an incident to establish is the last thing to copy.**)*

**What happened.** In E0-06's test module, `timestamp_columns` discovers timestamp
columns by reflecting from Postgres, and its docstring said why: "a column whose
type is a `TypeDecorator` — the natural place for the criterion 4 guard to live —
is not an instance of `DateTime` and would be missed." The row-seeding helper in
the same file dispatched `isinstance` against the **declared** column type and
got no such accommodation. When the implementation did what the docstring
predicted, both criterion-4 tests died inside the fixture on
`survey_window.closes_at`, before either reached an assertion. It took a dispute
round to settle ([`docs/disputes/E0-06-01.md`](../disputes/E0-06-01.md)).

A second, in E0-09, three tickets later, and it cost another dispute round
([`docs/disputes/E0-09-01.md`](../disputes/E0-09-01.md)). The E0-09 seeding helper
pins two column values so that a freely invented one cannot trip a rule from an
earlier ticket. The section code is drawn fresh per call, because E0-06 made
`(course, term, code)` unique; the course number one line above it was the
constant `"150"`, because SPEC §8 bands the number — and E0-05 also made
`(prefix, number)` unique. So the second course any test seeded under one prefix
was refused, and the three tests that need a sibling lead died inside the fixture
before any assertion ran. The two entries sit in the same dictionary, four lines
apart, and one of them already had the answer.

**Root cause.** Meeting a hazard at the call site where it first bit, instead of
asking which other call sites ask the same question. The write-up made it look
handled: the file named the hazard, in prose, one screen above the code that fell
to it. In the E0-09 case it was narrower still — the two values face *two* rules
each, a format rule and a uniqueness rule, and satisfying the format rule with a
constant is what violates the uniqueness one. Checking the entry against one rule
and stopping is the same shape as checking one call site and stopping.

**Consequence.** Two tests that could not pass against any implementation the
criterion admits, reported as a defect in the implementation. A round of the
loop, and — the expensive shape — an implementer under pressure to satisfy a
fixture rather than a criterion. Two of the four implementations tried in
response would have satisfied the helper *by removing the guard*, and one of them
is what the schema would have shipped.

**Rule.** When you work around a quirk of a type, a parser or an API, grep for
every place that asks the same question and route them through one helper, in the
same change. A docstring explaining the quirk is not a fix for the code that does
not call the fix. And when a test fails inside its own fixture, suspect the
fixture first — the message this one printed said exactly that, and was right.

**A fixture value has to satisfy every rule the column carries, not the one you
pinned it for.** Ask what makes the row *unique* as well as what makes it
well-formed, and prefer a generator over a literal wherever a second row of the
same kind is a shape any test might want. The `"150"` course number still sits in
the private copies of that dictionary in `test_identity_schema.py`,
`test_section_date_derivation.py` and `test_term_calendar_schema.py`; it is
latent there rather than active, because none of them seeds two courses under one
prefix yet.

---
