# Entry 60. An import rebound a module's name, and the linter was silent

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E5.1-05 (PR #265) made a week's report open at 06:00 on the
Monday after it closes. The commit that built the rule imported `time` from
`datetime` in `backend/app/services/reporting.py`. That module already had
`import time`, which the summary walk uses for `time.monotonic()`, and the new
import replaced it. ruff did not flag it. The ticket's own suites passed. The
wider run over the report, submit, student, grade, benchmark and published
modules failed one test,
`test_the_summary_job_never_logs_a_comment_a_summary_or_a_student`. The fix
(1c0f7ca) imports the class as `time_of_day`.

**Root cause.** Rebinding a name with a second import is legal Python, and here
the linter did not report it. The ticket's tests exercised the new rule and not
the older code in the same file that used the old binding.

**Consequence.** Caught before merge by the wider run. Had it shipped, the
Monday summary walk would have failed where it calls `time.monotonic()`.

**Rule.** When you import a name from a module, check that the name is not
already bound in the file, above all to a module. Import the second one under
its own name. A clean linter run is not proof that no name was shadowed. Run the
suites of every caller in the file you changed, not only the ticket's own.
