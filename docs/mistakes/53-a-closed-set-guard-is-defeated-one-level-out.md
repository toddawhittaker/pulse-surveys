# Entry 53. A closed-set guard is defeated one level out

**Caught: 0**

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
