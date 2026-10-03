# 0181 — The pytest gate runs on four runners, and a checker proves the slices were the whole suite

Supersedes in part [0104](0104-the-unit-and-integration-pass-runs-under-xdist.md):
its rejection of sharding across matrix jobs. The rest of 0104 stands — the full
pass still runs under `-n 4` with a Postgres per worker, and the invariant pass
is still serial.

## Context

On the four most recent green runs before this change (2026-10-03), `CI` took
18.9, 19.2, 24.7 and 25.4 minutes from first job to verdict. `Test · pytest +
invariants` was the whole of that: 18 to 25 minutes, while every other job had
finished by minute 10. Inside it, the §4.1 invariant pass (545 tests, serial)
took 6.3 to 8.2 minutes and then the full pass (3,906 tests, `-n 4`) took 11.3
to 16.6 minutes, one after the other on one runner. The repository is public,
so `ubuntu-latest` runners are four-core and cost nothing.

0104 rejected matrix sharding because it "needs more runners, a coverage-combining
step, and a change to the aggregate `ci` job's `needs` list for every shard",
for a split `-n 4` already gave. At the time the full pass was the only long
step; the invariant pass was 90 tests. Both numbers have grown.

## Decision

`test` stays one job id and becomes a four-leg matrix, with `fail-fast: false`:

- **`invariants`** runs the invariant pass exactly as before — serial, both
  checkers — on its own runner.
- **`suite` 1, 2 and 3** each run `pytest tests/unit tests/integration -n 4`
  with `scripts/ci/pytest_shard.py` loaded. The plugin keeps every third
  collected test starting at the leg's number, and records the whole collection
  and its slice.

A new job, **`test-shards`**, needs `test` and runs
`scripts/ci/check_test_shards.py` over the three legs' records. It fails unless
every leg collected the same non-empty suite, the slices are disjoint, their
union is the collection, and each leg's JUnit report (written by pytest, not by
the plugin) holds as many test cases as its slice. It then combines the three
coverage data files into the one `coverage` artifact the job used to upload.
It is in `ci`'s `needs`.

`e2e` also stops waiting on `fast-gate`, by the argument `test` already made for
itself: nothing it runs reads anything the fast gates produce, and once `test`
was split it was the longest chain left.

## Alternatives rejected

- **Only moving the invariant pass to its own runner.** The smallest change, and
  it saves 6 to 8 minutes; the full pass alone would still set a 12 to 17 minute
  wall clock. Taken as part of this decision rather than instead of it.
- **Running the invariant pass under xdist.** It would save about 5 minutes on
  the invariant leg, which is now the longest leg. 0104's reason still holds: the
  gate's verdict comes from the JUnit XML, and a crashed worker can truncate it.
  Left for the owner as a separate decision.
- **`pytest-split` or another sharding plugin.** A new locked dependency for
  forty lines of code that the repository can read and the checker verifies.
- **Slicing by file instead of by test.** Fewer repeated module fixtures, but
  integration files are much slower than unit files and nothing records their
  durations, so the slices would be uneven. Interleaving by test balances them
  without timing data.
- **Trusting the legs' exit codes.** A green leg proves only its own slice
  passed. Without `test-shards`, a slicing bug would read as a smaller suite
  passing, which is the failure this repository's CI rules exist to prevent.

## Consequences

- The pytest gate's wall clock is the invariant leg, about 8 to 9 minutes, and
  the full pipeline is set by it and by Playwright, at about 9 to 10 minutes.
- Each suite leg pays its own install and four testcontainers Postgres starts,
  so the pass costs more runner minutes in total than it did on one runner.
- A test that only passes when it shares a process with a particular other test
  can now fail, because its neighbours changed. That is a defect being surfaced,
  as 0104 said of `-n 4`.
- The slice count, 3, is written in three places in `ci.yml`: the matrix, the
  `PULSE_TEST_SHARD` value, and `test-shards`' `--expected` and paths. They move
  together, and the checker refuses a run where they disagree about how many
  slices there were.
- `make test` still runs the whole pass on one machine. Slicing is how CI spreads
  the same pass, not a different gate.
