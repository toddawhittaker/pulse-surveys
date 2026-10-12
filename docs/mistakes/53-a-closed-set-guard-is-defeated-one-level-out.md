# Entry 53. A closed-set guard is defeated one level out

**Caught: 7**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** The same shape on two surfaces, several instalments each.

The copy collector (E2-11) shipped with a one-level `*.ts` glob and a coverage
rule built from the collector's own enumeration — so it agreed with itself,
and a copy file in a subdirectory and a copy file spelled `.tsx` each shipped
an item-4 violation and a padlock with the suite green. The review closed
both by making the walk recursive over the whole TypeScript family and the
coverage rule a second, independent enumeration. The next level out was
already waiting: both walks used `Path.rglob`, which does not follow a
directory symlink on the pinned Python, so the two independent enumerations
agreed on missing the same files — recorded as a LOW at the E2 boundary
(`docs/tickets/e2/deferred.md`, last entry) and closed by E4-12 with
`recurse_symlinks=True` and a planted symlinked-directory control seen red.

The report API's item-7 guard (E4-07, PR #206) met the same shape three times
in one security round: the constructor token closed direct construction, the
next pass came through the figure doors, the pass after that through the
report doors — each repair closing the level the previous finding named while
the next level out stayed open, until the round attacked the class (four
layers, each with its own killer test) rather than the instance.

**Root cause.** A closed-set guard's inventory is written at the level where
the first defect appeared, and each repair inherits that level. The question
that finds the next instalment — "what encloses this set, and can the
enclosure change what the set means?" — is not asked, because the guard just
visibly caught something and feels finished.

**Consequence.** Each instalment costs a full review round or ships a silent
gap: two ungoverned copy surfaces green under the inventory, a directory
symlink that would have shipped strings with §4.1 items 4 and 5 asserted over
nothing, and three security-round rounds on one guard.

**Rule.** When you build or review a closed-set or inventory guard, attack the
whole class in the first pass: name what encloses the set (the directory above
the glob, the link kind the walk skips, the caller above the constructor, the
configuration that merges over the file) and either bring each enclosure
inside the guard or record it as a disclosed limit with an owner — in the same
change. A control's inventory must come from somewhere the guarded structure
cannot shrink, and the check that proves coverage must not be built from the
guard's own enumeration. For a compose or configuration guard, read the merged
result, not one file.

*(**Two catches, writing E5-11**, 2026-09-14. The first draft of round 1's
route sweep listed the student routes by hand and the benchmark keys by name.
This entry's question — what encloses the set — moved the inventory to the
application's route table (a student route registered tomorrow is inside the
sweep, and one the sweep cannot drive fails rather than skips) and the keys to
substring stems at every depth, with a planted-route control and near-miss keys
asserted spared. Round 2's DOM sweep took the same shape: beside the exact
legend sentences, a generic tier of stems over the whole rendered document,
attributes included, so a future member has to defeat a class rather than an
enumeration. What would have shipped: `course_benchmark_v2` under a renamed
member, or a tooltip carrying the word the legend does not, green under an
exact list.)*

*(**A catch**, writing E5-13's dispute fix, 2026-09-15. The item 1 registry
sweep had no audience model: every entry in the backend registry was read as a
student's, which was true until this ticket put a leader's refusals beside the
survey's strings. This entry's question — what encloses the set — made the
repair an exemption by key rather than by surface, with the enclosure and its
re-entry condition written on each row: the one refusal on that surface a
student can be served stays inside the sweep, and a gated refusal that later
becomes reachable leaves the tuple in the same change. What would have shipped:
a sweep scoped to "student surfaces" that let the role gate's 401 sentence, the
one a student really is answered with, name comparison sets. ADR 0177.)*

*(**A catch**, writing E5.1-03's clock-row sweep, 2026-10-03. The sweep's first
currencies were the obvious ones: imports of `ClockOverride` and raw SQL naming
`clock_override`. This entry's question added the same reference spelled one
level out, `getattr(models, "ClockOverride")` and `importlib.import_module` on
`app.models.clock`, and the docstring states what is still outside: a name
assembled at run time, a walk over every table on the metadata, and files that
are not Python.)*

*(**A catch across two tickets**, writing E7-02's and E7-08's red tests,
2026-10-11. E7-02's results payload could live in either of two schema modules,
and the existing structural sweep read only `app.schemas.student`; the test
author made it look in both, and pinned the route behind `require_student`
because the student-route inventory is derived from that dependency. E7-08's
leadership-route sweep finds routes through their dependency graph at every
depth and through included routers, with a control asserting it finds the ten
routes two other suites name. What would have shipped: a results payload in
`app.schemas.response_loop` outside the sweep, and a leadership route gated one
dependency down outside the 403 tests.)*

**Instance, 2026-10-12 (E9-01 and E9-07).** E9-01's caller sweep follows calls through an aliased module, and E9-07's test author made the roll-up schema sweep read every model reachable from a roll-up payload's fields, so the report's comment model imported into one is read all the same (`tests/unit/test_no_rollup_schema_carries_a_comment.py`). What would have shipped: a comment member reaching the roll-up through an imported model, with the sweep green.
