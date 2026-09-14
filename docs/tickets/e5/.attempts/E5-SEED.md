# E5-SEED — attempts

## 2026-09-14 — the reds confirmed, then the one-line defect

**The reds are the ones the manifest predicted**, run before anything was
changed: 4 failed, 65 passed across
`test_the_seeded_world_gives_the_hero_section_a_default_comparison_set.py` and
`test_demo_seed_script.py`. The two failures in the seed-script module both fail
in `the_seeded_course` rather than on a mapping assertion, which says the first
missing thing is the course row and not the mapping: the seeded database held no
course numbered `215` or `310` under `BIOL` at all.

**The defect is data in two lists, not one.** `scripts/seed.py` keeps who leads
what in `LEAD_FACULTY_MAPPINGS`, a tuple separate from the `LEAD_FACULTY`
entries in `ASSIGNMENTS`; its own comment says the schema lets the two disagree
and the demo seeds them agreeing. So the fix is three rows, not one: two
`DemoCourse` entries, one `DemoAssignment`, and one `LEAD_FACULTY_MAPPINGS` pair.
The test reads `lead_faculty_mapping`, so the mapping tuple is the one that turns
it green and the assignment is what keeps the two agreeing.

**The titles are the platform's.** `mock-lms/app/seed.py` publishes `BIOL 215` as
"Cell Biology" and `BIOL 310` as "Molecular Genetics", and a launch corrects a
stored title to the one the platform sends (ADR 0091). Seeding any other title
would have produced a row that silently changes the first time somebody launches
into it, which is not a thing a reader of the seed would expect. Nothing
duplicates: `_upsert_course` finds a course by `(prefix_id, lms_number)` and
creates one only when none is there.

**Two counts in comments moved with the rows**, and were checked by importing the
module rather than by counting the literals by eye: 17 courses, 8 mappings, 9
unmapped. The `BUSA 300` comment further down the file names the unmapped count
too, and it was corrected in the same commit.

**`MATH 140` was not seeded.** The mock platform publishes it and nothing needs
it here — no assignment names it and no benchmark reads it — so it keeps arriving
by launch the way it always has. The seed says so in a comment, because the next
person to read the two new biology courses will ask why the third mock course is
not there.

**The records were the larger half.** The claim that the hero's comparison set
was populated appeared as a fact in three places written from the same evidence:
`scripts/seed_benchmark_history.py`'s module docstring, ADR 0167's decision parts
2 and 3, and E5-12's attempt log. All three traced to the seeder's own self-check,
which counts the rows it wrote and never calls the service. The docstring sentence
was corrected and given the missing half; ADR 0167 got a dated amendment at the
top naming both wrong sentences rather than an edit removing them; the attempt log
was left as written with a dated note beside it. `docs/MISTAKES.md` entry 58 is
the lesson — verify a seeded world's claim through the reader the claim is about.

**The E5-12 ticket file was read and deliberately not changed.** Its scope asks
for "the same lead's courses, matched length+level", which is a correct
requirement that the build missed; it is not a false record of what was achieved.

**Gates.** Recorded in the report to the coordinator. The Compose seed run was
dropped from the brief mid-session — another build was driving that stack — so
idempotency was proved against a throwaway migrated database instead.
