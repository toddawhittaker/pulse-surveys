# 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 6**

*This file keeps the founding incident (it carries the root cause) and the
three most recent catches. Two older catches were trimmed 2026-09-07 — E4-03's
report-view suite (2026-09-06) and E3-04's AGS enforcement module (2026-09-04)
— after dating the paragraphs from git per the ordering rule; both live in this
file's history. A third was trimmed 2026-09-08 when E4-15's catch was added —
E4-04's comment suite (2026-09-06), which shared its date with the E4-01
paragraph inside the founding incident and was the removable one of the two.*

## A catch: E4-15's exit drive builds its world in a test rather than a hook (2026-09-08)

The E4 exit drive is a browser suite, not a pytest one, and the shape is the
same: its world costs a staff launch, a roster sync, a seeder run, two Monday
jobs and several `docker compose` round trips, so the natural home is
`test.beforeAll` — and the seeder the ticket owes does not exist while the reds
are being written. Written that way, the drive's pre-implementation red is a
**hook error**, every one of its eight cases is reported as not having run, and
the wall reads as "the exit spec is broken" rather than as "one named deliverable
is missing".

Instead `beforeAll` discovers placements only — shipped machinery, nothing this
ticket owes — and every write to the stack sits in the drive's first test, whose
whole subject is that the world can be built. Playwright's serial mode then skips
the remaining seven, which is the same protection a failing hook gives and a
better report: one FAILED naming `scripts/seed_exit_story.py` and the contract it
owes, seven skipped.

Counted as a catch: without the entry the world-building would have gone in the
hook, because that is where a browser suite's expensive setup belongs and every
other spec in `tests/e2e/` puts it there. The entry is what made the cost of that
choice visible on the one tree the reds are measured on.

## A catch: E4-18's section-list suite discovers nothing at setup (2026-09-07)

E4-18's world is expensive — a launch, a session, three sections and three
teaching grants — so it is a fixture, and the natural thing to put in it is the
lookup that says whether the route exists yet. `tests/fixtures/report_api.py`
next door does discover E4-07's routes through the module, and copying that shape
would have meant every one of this ticket's eleven tests reporting ERROR at setup
on the unbuilt tree, the must-be-green control among them — the one test whose
whole job is to be green and to prove the fixtures plant the grant they claim.

Instead the fixture seeds rows and writes grants and asks the application
nothing. The route is reached over HTTP at the settled path, and the guard that
names the missing deliverable is `entries_in`, a plain function each test body
calls on the response it just read; the session-module lookups in `_minted` are
in a method the test body calls too. Ten of the eleven reds are therefore
assertions about a status, a list or a header, and the eleventh passes.

Counted as a catch: without the entry the world fixture would have carried a
route discovery, and the tests-first run would have been eleven setup errors with
nothing to compare against the manifest.

## Instance: E3-01's rotation module errored at setup instead of failing (2026-09-04)

The tests-first suite for the signing-key rotation put its
require-rotation-columns guard — a `pytest.fail` naming the missing
`created_at`/`retired_at` columns — inside a shared fixture, and a second
fixture that planted two keys depended on it. On the unimplemented schema all
six non-control tests in
`tests/integration/test_the_published_key_set_carries_a_rotation.py` reported
ERROR at setup rather than FAILED, and one of them
(`test_the_refusal_tells_an_operator_what_to_do_about_it`) never reached the
assertion it existed to make — its subject, the 503 body's actionable sentence,
was reachable on the current schema and should have failed on content.

The independent red-run verification caught it by holding every red to the
manifest's own rule ("raised inside a test body ... not an import or a fixture
error"): five sibling modules honored the rule, one did not. The repair moved
the guards to plain functions called as each test body's first statement, split
so a test that plants nothing checks only what it touches.

The root cause: a fixture is the natural place to share setup, and the guard
*is* shared — but a guard that raises is an assertion, and an assertion in a
fixture reports in the wrong phase. The distinction is invisible in green and
only shows on the unbuilt tree, which is exactly the tree tests-first reds are
measured on.

**Instance, 2026-09-06 (E4-01, caught at authoring time).** The reveal-guard
suite's interface check — is the new signature there yet — was written as a
plain function, `require_the_reveal_interface`, called as each test body's
first statement rather than as a fixture, precisely so the pre-implementation
reds reported as FAILED naming the missing symbol instead of as fifteen setup
ERRORs. Counted as a catch: the entry's rule shaped the suite before any red
was run, and the red-run verification then confirmed every red behavioral.
