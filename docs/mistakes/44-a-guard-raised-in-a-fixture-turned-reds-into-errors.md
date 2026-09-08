# 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 5**

*This file keeps the founding incident (it carries the root cause) and the
three most recent catches. Two older catches were trimmed 2026-09-07 — E4-03's
report-view suite (2026-09-06) and E3-04's AGS enforcement module (2026-09-04)
— after dating the paragraphs from git per the ordering rule; both live in this
file's history.*

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

## A catch: E4-04's comment suite names every deliverable from a test body (2026-09-06)

E4-04's tests-first suite is eleven modules over a service module, a view, two
tables and a scheduled task, none of which exist while the reds are being
written. Almost every one of those lookups has a natural home in a fixture, and
the module import is the worst of them: `import app.services.report_comments` at
a test module's top level is a collection error, which asserts nothing, survives
the implementation landing, and reads to a hurried eye as a red suite.

The shared fixture module says the rule out loud and then keeps it —
`comment_service`, `visible_comments`, `released_comments`, `cut_batches`,
`report_comment_class`, `cut_task` and `require_report_table` are all plain
functions called as a test body's first statement, each turning an absence into a
`pytest.fail` that names the missing file, symbol or table and says which ticket
owes it. `comment_world` hands back an **unbuilt** world for the same reason, so
its own guards — a missing `question.stream`, a week nobody dated — fire in the
body too.

Counted as a catch: the red run that the whole heavy lane is measured against came
back 71 failed, every one of them a FAILED and none an ERROR, exactly matching the
manifest. Written the obvious way it would have been most of those seventy-one as
setup errors, with nothing to compare against the manifest and no way to tell a
waiting implementation from a broken checkout.

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
