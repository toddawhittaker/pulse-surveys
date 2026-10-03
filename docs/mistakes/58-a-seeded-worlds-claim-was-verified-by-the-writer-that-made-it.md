# Entry 58. A seeded world's claim was verified by the writer that made it

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E5-12 built the prior-term benchmark world so that the demo's
headline section, `BIOL-310-R7FF`, would have a comparison set a developer could
see on a screen. The mock platform gained three twelve-week undergraduate sections
of the hero's own course, `scripts/seed_benchmark_history.py` filled them with a
term of survey answers, and the seeder ended by recounting what it had written —
distinct sections and distinct students per cohort week, narrowed to the section
codes it had been handed — and exiting non-zero unless the counts cleared SPEC
§11's two minimums. The drive was done twice against a throwaway database, the
self-check printed that both minimums were cleared and the thin cohort suppressed,
and the seeder's own docstring, ADR 0167 and the ticket record all said the hero's
comparison set now had something in it.

It had nothing in it. SPEC §5.1 draws a section's **default** comparison set from
its course's Lead Faculty's courses, filtered to matching length and level, and
`scripts/seed.py` mapped no Lead Faculty to `BIOL 310` — it did not hold the
course at all, because a launch provisions it. So
`app.services.benchmarks.resolve_default_set` answered an empty list for the hero
section, and would have gone on answering an empty list however many matching
sections any seeder filled. Every count in the world was right and the one reader
the world exists for resolved nothing.

The fix is data: `scripts/seed.py` seeds both biology courses and maps a lead to
`BIOL 310`, and `BIOL 215` keeps no lead so the suppressed direction stays
demonstrable. What made the defect survive four green gates is not the data.

**Root cause.** The claim under verification was a claim about a *reader* — "this
section resolves a comparison set" — and every check made of it was a query
written by the *writer*, over the rows the writer had just written, narrowed by
the section codes the writer already knew. A recount by section code cannot
observe a filter it does not apply. The service applies three narrowings and the
recount applied one, so the two agreed on everything except the narrowing that was
missing from the world, which is exactly the one nobody thought to count. The
rejected alternative in ADR 0167 had argued, correctly, against letting the
self-check read E5-03's view because a check that reads the thing under
construction agrees with it — and then the recount that replaced it made the
opposite version of the same mistake, agreeing with the seeder instead.

**Consequence.** Nothing shipped: the demo world is development data and the
defect was found while E5's later tickets were being built. Its cost was in
records. Three of them — the seeder's module docstring, ADR 0167's decision, and
the ticket's account of the drive — stated a populated comparison set as an
accomplished fact, and each was written from the self-check's output. Downstream
tickets planned against those records. Had it not been found, the first person to
open the benchmark screen on a freshly seeded stack would have seen no comparison
line at all, on the one section the whole epic is demonstrated with, and the
obvious suspects would have been the benchmark service and the suppression rule
rather than a missing row in the seed.

**Rule.** Verify a seeded world's claim through the reader the claim is about, not
through the writer that made it. A seeder's self-check answers "did I write what I
meant to write"; it never answers "can the thing this world exists for read it",
and those two questions come apart exactly where a filter the seeder does not
model does the excluding.

Three halves worth keeping separate:

- **Name the reader before the rows.** If the claim is "the hero's comparison set
  is populated", the sentence contains a function — `resolve_default_set` — and
  the check calls it. If a claim about a world does not name a reader, it is a
  claim about rows, and it should be written down as one.
- **A recount is not a weaker version of the read, it is a different query.** The
  service's narrowings are the subject; a check that reproduces some of them by
  hand asserts the ones it reproduced and is silent about the rest, while looking
  like coverage. Count the narrowings the reader applies and say which of them
  your check exercises.
- **Necessary is not sufficient, and records must say which they are.** "These
  sections match the hero's length and level" was true; "and so they are its
  comparison set" was the false half, glued to the true one in the same sentence
  in three records at once. When a world is built by several files, no one file's
  docstring is entitled to state the result — say what this file contributes, and
  point at what else has to hold.
