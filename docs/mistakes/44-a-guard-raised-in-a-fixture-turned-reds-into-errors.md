# 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 4**

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

## A catch: E4-03's report-view suite asks for the view inside each test (2026-09-06)

Every test of E4-03's three aggregate read views has to read a view that does not
exist yet, and a `SELECT` against a missing relation raises `UndefinedTable` from
the driver. The obvious home for the check is a fixture — one `report_views`
fixture that confirms all three and hands back a world — and that would have made
the whole tests-first suite, four modules of it, a wall of setup ERRORs on the
unbuilt tree: nothing asserted, nothing to compare against the manifest, and a
red run that reads as a broken checkout rather than as a ticket waiting for its
implementation.

Instead `require_report_view` is a plain function called as the first statement
of each test body, `report_world` hands back an **unbuilt** world so its
`question.stream` guard fires in the body too, and the one read that could raise
on a missing grant is wrapped and turned into a `pytest.fail` naming the other
test that diagnoses grants. Every red the ticket ships with is a FAILED naming
the missing view, the missing column or the missing grant.

Counted as a catch: without the entry the suite would have been written with a
fixture-level guard, and the coordinator's red run would have had thirty errors
to sort through instead of thirty named failures.

## A catch: E3-04's enforcement module builds its gradebook in the test body (2026-09-04)

Every test in `tests/integration/test_mock_lms_ags_requires_a_token.py` needs the
same six addressed AGS routes, and building them means *creating a line item and
posting a score through the very enforcement under test*. A `@pytest.fixture`
was the obvious home and is exactly this entry's mistake: an implementation that
refused a call it should serve would have turned all forty-odd reds in the module
into setup ERRORs, proving nothing about the refusals they exist to make and
reading to a hurried eye as "the suite is red". It is a plain `gradebook(platform)`
function called as each test body's first statement instead, so the same failure
arrives as a FAILED naming the accepted call that did not work.

The same rule shaped the client side, where the deliverable is a whole module:
`tests/fixtures/ags_client.py` imports `app.lti.ags` inside the call rather than
at fixture setup, so an unbuilt tree gives nineteen failed assertions naming the
missing module rather than nineteen errors.

Counted as a catch: without the entry the module would have shipped with its
guard in a fixture, and the red-run verification would have had a wall of errors
to sort through instead of a manifest to compare against.

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
