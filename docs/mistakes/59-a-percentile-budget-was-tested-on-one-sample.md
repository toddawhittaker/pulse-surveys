# Entry 59. A percentile budget was tested on one sample

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** Two tests in
`tests/integration/test_the_submit_path_follows_adr_0056s_taxonomy.py` asserted
that one submission finished within SPEC §10's 2.5 seconds. They exist for entry
41: a submit that waits on a broker that is down. CI run 37166495313 measured
2.58 seconds on PR #265, a commit that changed only documentation, and the same
code had passed twice before. At the E5 exit the same test had measured 2.95
seconds once under load and then passed alone and on a rerun, and that was
carried rather than fixed. E5.1-10 (PR #269) was added to the epic to fix it.

**Root cause.** SPEC §10's 2.5 seconds is a p95, and one sample cannot test a
p95. A single slow request on a loaded runner failed the assertion while the code
was fine, so the test reported runner load, not a defect.

**Consequence.** A red CI run on a documentation commit, and a ticket added
mid-epic to repair the test. The earlier failure had been read as a flake and
carried, so the same red came back.

**Rule.** A budget the specification states as a percentile cannot be tested by
one measurement. Assert a statistic of several samples that the defect still
moves. E5.1-10 reads the median of three submissions: entry 41's wait is paid on
every submission, so all three are slow and the median is slow, and the planted
defect still failed the test at 6.0 seconds. Say in the test that the statistic
is not the percentile. A median hides a defect that slows only the first
request, so name what the chosen statistic gives up.
