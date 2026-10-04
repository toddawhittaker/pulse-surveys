# 44. A guard raised in a fixture turned a module's reds into setup errors

**Caught: 9**

*This file keeps the founding incident (it carries the root cause) and the
three most recent catches. Two older catches were trimmed 2026-09-07 — E4-03's
report-view suite (2026-09-06) and E3-04's AGS enforcement module (2026-09-04)
— after dating the paragraphs from git per the ordering rule; both live in this
file's history. A third was trimmed 2026-09-08 when E4-15's catch was added —
E4-04's comment suite (2026-09-06), which shared its date with the E4-01
paragraph inside the founding incident and was the removable one of the two.
E4-15's exit drive (2026-09-08) and E4-18's section-list suite (2026-09-07)
were trimmed on 2026-10-03, when the two E5.1 catches were added.*

## A catch: E5.1-03's red run was all FAILED and no ERROR (2026-10-03)

The tests-first commit for E5.1-03 (267529c) went red with 72 failures, every one
a FAILED and none an ERROR, and the builder confirmed the same count before
writing code. The entry's rule shaped the suite: the guards that a deliverable
exists were plain functions called from test bodies, so each red named what was
missing rather than failing in setup.

## A catch: E5.1-05's red run was all FAILED and no ERROR (2026-10-03)

At the red commit (9acc9dc), E5.1-05's eight test modules gave 25 failed and 46
passed, 18 unit and 7 integration reds, every one a FAILED with no ERROR. As
above, the entry is why the suite was written so that its reds report in the
test body.

## A catch: E4-20's seeder reds name the missing script instead of missing it (2026-09-09)

E4-20's two red tests run `scripts/seed_demo_story.py` as a process, and the
machinery they follow — `DemoSeed` in `tests/fixtures/seed.py` — already answers
the fixture half of this entry: when the script is absent it hands back a
*synthetic* run, exit 127 with the reason on stderr, rather than failing from
inside setup. Copying that alone would have avoided the ERROR wall and still
produced the wrong red. The refusal assertions read what the run printed, so on
the unbuilt tree each test would have failed on "the run refused and did not say
the environment was why", with the sentence that actually explains the tree —
the script does not exist — folded into a tailed stream underneath it.

Acting on the entry's rule as written, the guard is `require_the_story_seeder`, a
plain function called as the first statement of both bodies, naming the script
and the ticket that owes it. Today's red is therefore a FAILED whose message is
the deliverable, and the assertions about what a refusal says only ever run
against a refusal that exists.

Counted as a catch: without the entry the module would have inherited the shared
runner's fallback and reported two reds about the *content* of a refusal on a
tree with no script in it, which is a red that reads as a wrong assertion rather
than as a missing deliverable. The lesson the earlier catches did not carry: a
fixture that avoids raising is not the same as a body guard that names the thing,
and shared machinery which softens the absence can hide it just as well.

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
