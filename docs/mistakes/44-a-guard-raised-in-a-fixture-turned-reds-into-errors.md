# 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 1**

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
