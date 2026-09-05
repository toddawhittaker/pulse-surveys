"""The `/dev` passback trigger, driven over HTTP against a real gradebook — ticket E3-07.

Criterion 1: "With the development clock set past a window's close, the `/dev`
trigger runs a passback and the mock's gradebook changes — driven in a browser
once and scripted so it stays true." This module is the scripted half. The
browser drive is done by hand once and recorded in the pull request; nothing here
replaces it, and nothing there replaces this.

**Why the trigger exists at all.** The weekly beat fires on real time while the
formula counts weeks off the development clock (ADR 0109), so a developer who
sets the pretend now past a window's close sees nothing happen until the real
schedule comes round on Monday at 02:20. That is the same gap E2-04 and E2-13 hit
with survey windows and the answer is the same: a `/dev` control.

**This module holds the accepted directions; the refusals live next door.**
`tests/unit/test_dev_passback_trigger_exposure.py` asserts every direction that
must be refused — every method outside development, every method but POST inside
it, a cross-site `Origin`, the literal `null` one — with no database and no
gradebook, because a refusal needs neither. The two modules are a pair: a gate
that only ever refuses cannot be told from a control that never worked, and a
control that only ever runs cannot be told from one with no gate. Each names the
other, and a change that turns one green by breaking the feature turns the other
red.

**Two refusals are asserted here as well, and they are a different claim.** That
a refused call answers 403 or 404 is next door's; that it **writes nothing** — no
`grade_sync` row, no `ags_call` row, no score at the platform — is here, because
only a suite with a gradebook can tell "refused" from "ran and had nothing to
do". Each of those tests proves the world was postable by running E3-06's sweep
directly afterwards and requiring it to post: without that, "nothing was written"
is satisfied by a section with no elapsed week, which is `docs/MISTAKES.md` entry
3 in its plainest form.

**What the platform received is read back, never recomputed.** The comparison is
between what `participation_scores` answered and what `GET /mock/posted-scores`
says the platform holds (ADR 0047). Nothing here composes a percentage or a
ledger: a test holding its own rendering of the thing under test is
`docs/MISTAKES.md` entry 19, and E3-03's answer is the only expectation this
module has.

**The environment.** `window_settings` states `ENVIRONMENT=development` and
`INSTITUTION_TIMEZONE=America/New_York` over `configured_env`'s documented values
(`docs/MISTAKES.md` entry 40), which is the chain every E3-06 module rides;
development is required twice over, since it is the only environment where the
clock override applies at all (ADR 0109 part 4) and what makes the mock
platform's cleartext gradebook address storable (ADR 0081).

**Which failure a red here is.** Before E3-07 lands, `declared_passback_path` is
a plain call in each test body that reports `app.api.dev` exposing no
`DEV_PASSBACK_PATH` as a FAILED naming the deliverable (`docs/MISTAKES.md` entry
44). Once the constant exists and the route does not, the reds are assertions: a
404 where a 303 belongs, and a console page carrying no passback button.

**The control comes first and it must be green today. A red in that section means
these tests are broken, not the code.**
"""

import json
from typing import Any

import pytest
from fixtures.dev_console import (
    CROSS_SITE_ORIGIN,
    CROSS_SITE_REFUSED,
    DEV_CONSOLE_PATH,
    ORIGIN_HEADER,
    PASSBACK_RUN_TESTID,
    declared_passback_path,
    read_console,
    redirected_to_the_console,
    same_origin_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`; `line_item_contract` from
# `tests/fixtures/line_item_creation.py`; `dev_console_tool` from
# `tests/fixtures/dev_console.py`. All are reached as fixtures rather than
# imported, for the reason every module in this suite gives: an import of a
# fixtures module by name depends on where pytest put `tests/` on `sys.path`, and
# an import error is not a red.

# How many course weeks have elapsed when the trigger is pulled. One is enough:
# what this module is about is whether the trigger runs the sweep at all, and
# what the sweep computes over how many weeks is E3-06's six modules' subject.
ELAPSED_WEEKS = 1

# What a deployment's `ENVIRONMENT` is called here, and the setting name the tool
# is built with in the one test that builds it outside development.
PRODUCTION = "production"
ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The liveness route, used as the control that an application answering 404 is a
# closed gate rather than an application serving nothing.
HEALTHZ_PATH = "/healthz"


def a_gradebook_with_a_score_to_post(
    gradebooks: Any,
    sweep_contract: Any,
    committed_clock_overrides: Any,
) -> tuple[Any, Any]:
    """One section with a line item, one student who answered, and the clock past week 1's close.

    The state criterion 1 describes — "with the development clock set past a
    window's close" — and the state in which a correct sweep has exactly one score
    to post. Every value here is this suite's input; nothing about what the
    formula answers is decided here (`docs/MISTAKES.md` entry 30).
    """
    book = gradebooks()
    (student,) = sweep_contract.students(book, 1)
    sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)
    return book, student


def posted_for(book: Any, student: Any, sweep_contract: Any) -> list[dict[str, Any]]:
    """Every score body the platform recorded for one student, in arrival order."""
    return [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == student.subject
    ]


def nothing_was_written(book: Any, grade_sync_rows: Any, what: str) -> None:
    """No score at the platform, no `grade_sync` row, no `ags_call` row.

    Three witnesses because they fail differently: a sweep that ran and posted
    leaves a score at the platform, one that tried and failed leaves an
    `ags_call` row and a `grade_sync` row saying so, and one that computed and
    declined to post leaves neither but is not what a refusal looks like either.
    """
    assert book.posted() == [], (
        f"{what} and the platform holds {book.posted()} against this section's line item. The "
        "request was refused, so nothing should have reached a gradebook at all."
    )
    assert grade_sync_rows.all_rows() == [], (
        f"{what} and `grade_sync` holds {grade_sync_rows.all_rows()}. A row is Pulse's own account "
        "of what it told a platform about a student's standing; a refused request produced one, so "
        "something ran past the gate."
    )
    assert grade_sync_rows.calls() == [], (
        f"{what} and `ags_call` holds {grade_sync_rows.calls()}. SPEC §6.1 puts a row there per "
        "HTTP call this tool made to a platform service, so a row means the refusal happened after "
        "the wire rather than before it."
    )


def and_yet_the_sweep_posts(book: Any, sweep_contract: Any, window_settings: Any) -> None:
    """The world had a score to post — run E3-06's sweep directly and require it to.

    The non-vacuity guard for every "nothing was written" assertion above
    (`docs/MISTAKES.md` entry 3): a section with no elapsed week, no line item or
    no answers writes nothing whatever the gate does, and a refusal test built
    over one would pass against a trigger with no gate at all. Run *after* the
    absence is asserted, so the rows it leaves are its own.
    """
    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )
    assert raised is None, (
        f"E3-06's sweep raised {raised!r} over this section, so the refusal asserted above cannot "
        "be told from a world that had nothing to post."
    )
    assert answered[sweep_contract.posted_key] == 1, (
        f"E3-06's sweep answered {answered!r} over this section, and this test needs it to post "
        "exactly one score. The absence asserted above is only evidence that the gate refused if a "
        "run that was not refused would have written something."
    )


# ---------------------------------------------------------------------------
# The control on the console reader, before anything is believed of it.
# ---------------------------------------------------------------------------


def test_the_console_reader_finds_a_button_the_form_around_it_and_a_void_input() -> None:
    """The control on the console assertion below (`docs/MISTAKES.md` entry 3).

    `ConsolePage` reports which `data-testid`s a page carries and which `<form>`
    encloses each of them. A reader that found no testids would make the console
    test fail for the wrong reason; a reader that attributed every element to the
    first form on the page would make it *pass* while the passback button sat in
    the clock's form, posting a pretend now. The second is the dangerous half, so
    two forms are planted and each button must come back under its own.

    Three properties, and each is a way this reader could be quietly wrong:

      - it reads attributes off the element carrying the testid;
      - it attributes a button to the form it is actually inside, and reports
        `None` for an element outside every form;
      - it does not leave a form open across a void element. `<input>` has no end
        tag, so a reader that pushed every tag onto its stack would never pop it
        and would go on attributing the rest of the document to a form that ended
        paragraphs ago — the defect the clock console's own reader was written
        around, transcribed rather than rediscovered.

    Needs no implementation and is green now. If it is red, nothing else in this
    module means what it says.
    """
    markup = (
        '<form class="clock" method="post" action="/dev/clock">'
        '<input data-testid="clock-pretend-now" name="pretend_now" type="datetime-local">'
        '<button data-testid="clock-set">set</button>'
        "</form>"
        '<form class="clock" method="post" action="/dev/passback">'
        '<button data-testid="passback-run">run a passback now</button>'
        "</form>"
        '<a data-testid="outside-every-form" href="/dev">back</a>'
    )

    page = read_console(markup)

    assert page.testids["clock-set"].get("data-testid") == "clock-set", (
        f"The reader read the clock button's attributes as {page.testids.get('clock-set')}. Every "
        "assertion below is made through this mapping."
    )
    assert (page.form_of("passback-run") or {}).get("action") == "/dev/passback", (
        f"The reader put the passback button in the form {page.form_of('passback-run')}. It is "
        "inside the second form on this page, and a reader that answered the first would report a "
        "button that posts a pretend now as one that runs a passback."
    )
    assert (page.form_of("clock-set") or {}).get("action") == "/dev/clock", (
        f"The reader put the clock button in the form {page.form_of('clock-set')}. A reader that "
        "left the first form open across its own `<input>` — which has no end tag — would go on "
        "attributing every later element to it, including the passback button, and the assertion "
        "above would pass for the wrong reason."
    )
    assert page.form_of("outside-every-form") is None, (
        f"The reader put an anchor that is inside no form at all in {page.form_of('outside-every-form')}"
        ". An element outside every form has no enclosing one, and a reader that answered the last "
        "form it saw would report a stray button as part of a control."
    )
    assert (
        len(page.forms) == 2
    ), f"The reader found {len(page.forms)} forms on a page with two: {page.forms}."


# ---------------------------------------------------------------------------
# The console offers the control, and the control runs.
# ---------------------------------------------------------------------------


def test_the_console_offers_a_passback_button_in_a_form_posting_to_the_trigger(
    dev_console_tool: Any,
    window_settings: Any,
) -> None:
    """Criterion 1's browser half, scripted: the page carries the button the drive clicks.

    A route with no way to reach it from the page is a control a developer cannot
    use, which is the whole point of the ticket — the epic's behaviour is "not
    drivable in a browser at all" without it. So the console must carry an element
    with `data-testid="passback-run"`, and that element must sit inside a form
    whose `action` is the trigger's own path and whose method is POST.

    **The mutations this kill**: a trigger route added with no console section, so
    the only way to run it is `curl`; a button rendered outside any form, which
    does nothing when clicked; and a form posting to `/dev/clock` — the section
    above it on the page — which would move a developer's clock every time they
    asked for a passback.

    **What is pinned and what is not.** The testid, the action and the method are
    E3-07's work order (D2, D6) and are asserted exactly. The button's wording is
    the implementer's and is not asserted here at all; so is the copy beside it,
    including the two rewound-clock sentences the ticket asks for, which are prose
    a test should not freeze.
    """
    declared = declared_passback_path()
    client = dev_console_tool()

    answered = client.get(DEV_CONSOLE_PATH)
    assert answered.status_code == 200, (
        f"`GET {DEV_CONSOLE_PATH}` answered {answered.status_code} in development. The console is "
        "served here and nowhere else; a 404 is the gate closed on the direction it must stay "
        f"open. Body begins {answered.text[:300]!r}."
    )
    page = read_console(answered.text)

    assert PASSBACK_RUN_TESTID in page.testids, (
        f"The console carries no element with `data-testid={PASSBACK_RUN_TESTID!r}`; it carries "
        f"{sorted(page.testids)}. E3-07 adds a Passback section to `{DEV_CONSOLE_PATH}` with one "
        "button, and without it the trigger is a route nobody can reach from the page it belongs "
        "to."
    )
    enclosing = page.form_of(PASSBACK_RUN_TESTID)
    assert enclosing is not None, (
        f"The `{PASSBACK_RUN_TESTID}` button sits inside no `<form>`; the page's forms are "
        f"{page.forms}. A button outside a form does nothing when a developer clicks it."
    )
    assert enclosing.get("action") == declared, (
        f"The form around the `{PASSBACK_RUN_TESTID}` button posts to "
        f"{enclosing.get('action')!r} and the trigger is at {declared!r}. The clock controls are "
        f"the neighbouring section on this page, so a form left pointing at `/dev/clock` moves the "
        "developer's clock every time they ask for a passback."
    )
    assert (enclosing.get("method") or "").lower() == "post", (
        f"The form around the `{PASSBACK_RUN_TESTID}` button declares "
        f"method {enclosing.get('method')!r}. The trigger answers POST and answers 404 to every "
        "other method (E3-07's work order, D4), so a form defaulting to GET is a button that "
        "always fails — and a state-changing GET is exactly what the origin check cannot protect."
    )


def test_a_same_origin_post_runs_the_passback_and_the_platform_holds_the_computed_score(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    line_item_contract: Any,
    dev_console_tool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 1, end to end: the clock is past a close, the trigger is pulled, the gradebook moves.

    One section with a line item, one student who answered week 1 in full, the
    development clock a minute past that week's window closing, and a POST to the
    trigger carrying this application's own `Origin` — the header a browser sends
    when the developer clicks the button on `/dev`. Afterwards the platform must
    hold that student's score, and it must be the score `participation_scores`
    computes rather than any number this module worked out.

    **The mutations this kill**: a trigger that redirects without running
    anything, which is indistinguishable from a working one in a browser until
    somebody opens the gradebook; a trigger that runs the sweep and commits, or
    that opens no session at all; and a trigger wired to some other computation,
    caught because both the percentage and the ledger are compared against E3-03's
    own answer.

    **The `grade_sync` row is asserted beside the wire**, because ADR 0124 has the
    row record what was sent and ADR 0052's retry re-sends it: a run that posted
    and recorded nothing leaves the next sweep about to post the same score again
    as if it were new.

    **The transport seam is substituted after the tool is built.** Neither the
    mock platform's address nor the tool's resolves over a network in this
    process, so `app.services.grading.outbound_transport` is pointed at the wire —
    and `import_app_module` gives the freshly built tool the modules in
    `sys.modules`, so a substitution made before the build could be made on a
    different module object and the trigger would reach nothing
    (`tests/fixtures/line_item_creation.py` gives the same reason for
    `run_tasks_inline`).
    """
    declared = declared_passback_path()
    book, student = a_gradebook_with_a_score_to_post(
        gradebooks, sweep_contract, committed_clock_overrides
    )
    expected = sweep_contract.computed(book.world, student, settings=window_settings)

    client = dev_console_tool()
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)

    answered = client.post(declared, headers={ORIGIN_HEADER: same_origin_of(client)})
    redirected_to_the_console(answered, f"`POST {declared}` with a same-origin `{ORIGIN_HEADER}`")

    bodies = posted_for(book, student, sweep_contract)
    assert len(bodies) == 1, (
        f"The platform recorded {len(bodies)} scores for this student after the trigger was "
        f"pulled: {bodies}. None means the trigger answered {answered.status_code} and ran nothing "
        "— which is what a redirect with no sweep behind it looks like from a browser — and more "
        "than one means it swept twice."
    )
    delivered = bodies[0]
    assert delivered.get(sweep_contract.given_member) == json.loads(expected.percentage), (
        f"The platform received {delivered.get(sweep_contract.given_member)!r} and "
        f"`participation_scores` computed {expected.percentage!r}. The comparison is against the "
        "formula's own string put through the one decode the platform cannot avoid, never against "
        "a number this test worked out, so a value the trigger re-derived from the completed and "
        "total counts is caught while both spellings of the same number pass."
    )
    assert delivered.get(sweep_contract.comment_member) == expected.ledger, (
        f"The platform received the comment {delivered.get(sweep_contract.comment_member)!r} and "
        f"the formula produced the ledger {expected.ledger!r}. SPEC §3.4 puts the per-week ledger "
        "in the AGS comment, and since v1 ships no view of the participation score it is the only "
        "place the arithmetic behind a posted percentage is visible to anyone (ADR 0125)."
    )

    rows = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(rows) == 1, (
        f"There are {len(rows)} `grade_sync` rows for this student after one trigger: {rows}. ADR "
        "0124 makes every attempt a row, and the next sweep compares what it computes against the "
        "latest one — a post that left no row is a post the weekly beat is about to make again."
    )
    assert rows[0][sweep_contract.score_text_column] == expected.percentage, (
        f"The row records {rows[0][sweep_contract.score_text_column]!r} and the formula computed "
        f"{expected.percentage!r}. ADR 0124 stores the exact string that was sent, because ADR "
        "0052's retry identity is byte equality of a body the platform already accepted."
    )


def test_a_post_with_no_origin_header_at_all_is_accepted(
    gradebooks: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    line_item_contract: Any,
    dev_console_tool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other accepted direction: a caller that is not a browser is not a forgery vector.

    D4 allows a request with no `Origin` header deliberately. Every current
    browser sends the header on a cross-site POST, so the requests that arrive
    without one are the non-browser callers — `curl` in a terminal, a script, a
    Makefile target — and none of them can be tricked into making a request on
    somebody else's behalf, which is the whole thing a same-origin check defends
    against.

    **The mutation this kills**: an origin check written as "refuse unless the
    header is present and matches", which is the shape a reviewer asks for and
    which locks every non-browser caller out of the one control this ticket adds.
    Its pair is `test_the_literal_null_origin_is_refused_inside_development` in
    `tests/unit/test_dev_passback_trigger_exposure.py`: `null` is a *mismatch* and
    absence is not, and a build that treats them alike fails one of the two
    whichever way it errs.

    The score is required to have reached the platform rather than the redirect
    alone being read, because a redirect is what a handler that refused silently
    would also produce; what the score *is* is the test above's subject.
    """
    declared = declared_passback_path()
    book, student = a_gradebook_with_a_score_to_post(
        gradebooks, sweep_contract, committed_clock_overrides
    )

    client = dev_console_tool()
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)

    answered = client.post(declared)
    redirected_to_the_console(answered, f"`POST {declared}` with no `{ORIGIN_HEADER}` header")

    assert posted_for(book, student, sweep_contract), (
        f"`POST {declared}` with no `{ORIGIN_HEADER}` header redirected to the console and the "
        "platform holds no score for this student. A request with no origin header is not a "
        "cross-site request — it is a caller that is not a browser at all — and refusing it locks "
        "every script and every terminal out of the control while looking, from the browser, "
        "exactly like a working one."
    )


# ---------------------------------------------------------------------------
# A refused call writes nothing. The statuses are next door's; the rows are here.
# ---------------------------------------------------------------------------


def test_a_cross_site_post_is_refused_and_writes_nothing(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    line_item_contract: Any,
    dev_console_tool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cross-site POST reaches no gradebook — asserted against the platform and both tables.

    The status is asserted next door, without a database. What can only be
    asserted here is that the refusal happened **before** anything ran: no score
    at the platform, no `grade_sync` row, no `ags_call` row. A gate that answered
    403 after starting the sweep would leave a gradebook changed and a student's
    grade posted from a request nobody made deliberately, and every status
    assertion in this project would still be green.

    **The mutation this kills**: the origin check written inside the handler after
    the sweep call rather than in the route wrapper before it — which is what an
    implementation that reads the header out of `Request` in the endpoint body
    tends to produce when the call order is edited later.

    **The non-vacuity guard is the last thing this test does**: E3-06's sweep is
    run directly and required to post exactly one score, so "nothing was written"
    is known to be the gate's doing rather than a section with nothing to say.
    """
    declared = declared_passback_path()
    book, student = a_gradebook_with_a_score_to_post(
        gradebooks, sweep_contract, committed_clock_overrides
    )

    client = dev_console_tool()
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)

    answered = client.post(declared, headers={ORIGIN_HEADER: CROSS_SITE_ORIGIN})

    assert answered.status_code == CROSS_SITE_REFUSED, (
        f"`POST {declared}` from {CROSS_SITE_ORIGIN} answered {answered.status_code} in "
        f"development, and E3-07 settles {CROSS_SITE_REFUSED}. The row assertions below are about "
        "what a refusal leaves behind, and they say nothing if the request was not refused. Body "
        f"begins {answered.text[:300]!r}."
    )
    nothing_was_written(
        book, grade_sync_rows, f"`POST {declared}` was refused {CROSS_SITE_REFUSED}"
    )
    and_yet_the_sweep_posts(book, sweep_contract, window_settings)


def test_a_post_outside_development_writes_nothing(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    line_item_contract: Any,
    tool_doors: Any,
    door_contract: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 2's refusing half, against a gradebook: a deployment posts nothing on demand.

    The unit module asserts that every method answers 404 outside development.
    What it cannot assert is that the 404 came *before* the sweep: a handler that
    ran the passback and then answered 404 would satisfy every status assertion
    ever written about this route while posting grades to a real LMS for anybody
    who asked. So the same section, the same elapsed week and the same postable
    score are set up here, the trigger is pulled on an application built as a
    deployment, and all three witnesses must be empty.

    **What this test is worth alone, which is little.** An unregistered path
    answers 404 and writes nothing, so once `DEV_PASSBACK_PATH` exists this test
    would pass against a build that registered no route at all — the guard at the
    top of the body is what keeps *that* state a FAILED rather than a green, and
    the assertion below means something only in the pair with
    `test_a_same_origin_post_runs_the_passback_and_the_platform_holds_the_computed_score`
    above and with the route-table control in
    `tests/unit/test_dev_passback_trigger_exposure.py`, which is what says the
    door was ever hung. The mutation it exists to kill is a later one: the
    environment gate dropped from a route that by then certainly works.

    The tool here is built through `tool_doors` directly rather than through
    `dev_console_tool`, and the difference is the point: E0-39 refuses
    `.env.example`'s mock identity provider anywhere `ENVIRONMENT` is not
    `development`, so a deployment's tool keeps `deployed_identity_provider`'s
    addresses. Nothing in this test reads the console page, which is the only
    thing that needs a provider mounted.

    A cross-site `Origin` is sent rather than none, because that is the request an
    attacker actually makes and because it is the one an inverted gate order
    answers differently — the status half of which is next door's
    `test_a_cross_site_post_outside_development_answers_404_rather_than_403`.
    """
    declared = declared_passback_path()
    book, student = a_gradebook_with_a_score_to_post(
        gradebooks, sweep_contract, committed_clock_overrides
    )

    client = tool_doors(
        {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            ENVIRONMENT_VARIABLE: PRODUCTION,
        }
    )
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` did not answer 200 on the application built with "
        f"`{ENVIRONMENT_VARIABLE}` set to {PRODUCTION!r}, so it is serving nothing and the 404 "
        "below would be the 404 of an application with no routes."
    )
    assert client.get(DEV_CONSOLE_PATH).status_code == 404, (
        f"`GET {DEV_CONSOLE_PATH}` did not answer 404 on the application this test built as a "
        f"deployment. The console is gated on `{ENVIRONMENT_VARIABLE} == 'development'` and its "
        "refusal is asserted in `tests/unit/test_dev_console_exposure.py`, so a different answer "
        "here means this build is not the deployment it was asked for — `gradebooks` has already "
        "built one tool in development inside this test, and two applications built in one test "
        "share their `app.*` modules. Until that is resolved the trigger's own 404 below would be "
        "measured against a development build and would mean nothing."
    )

    answered = client.post(declared, headers={ORIGIN_HEADER: CROSS_SITE_ORIGIN})

    assert answered.status_code == 404, (
        f"`POST {declared}` answered {answered.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{PRODUCTION!r}. Outside development the trigger is indistinguishable from a path nobody "
        f"registered; a {CROSS_SITE_REFUSED} discloses that the route is there and that its origin "
        f"check is running. Body begins {answered.text[:300]!r}."
    )
    nothing_was_written(
        book, grade_sync_rows, f"`POST {declared}` answered 404 outside development"
    )
    and_yet_the_sweep_posts(book, sweep_contract, window_settings)
