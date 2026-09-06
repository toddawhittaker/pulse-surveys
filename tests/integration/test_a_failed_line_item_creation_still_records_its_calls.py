"""A failed line-item creation leaves its call log behind — ticket E3-05, security round.

SPEC §6.1 puts "NRPS and AGS call logs with response codes" on the admin console,
and E3-04's criterion 8 writes one `ags_call` row per HTTP call, "successes and
failures". This module is about the one place that record can be silently thrown
away: the worker task.

**The finding (MEDIUM, durability).** `create_line_item`
(`backend/app/jobs/tasks.py`) opens its own `SessionLocal`, calls
`ensure_line_item`, and commits. When the AGS attempt fails, the `AgsError`
propagates, `SessionLocal.__exit__` rolls back before the commit is reached, and
every `ags_call` row the attempt recorded goes with it. A successful creation is
durable; a failed one leaves no trace. There is no hourly backstop for creation
the way there is for the roster sync, so an operator watching §6.1's console sees
nothing — and an attacker who can provoke the failure can probe a platform's
gradebook endpoints repeatedly and stay invisible in exactly the log built to
show it.

**The fix this red is written against**: `create_line_item` catches the
`AgsError` family, commits the recorded calls, and re-raises — so the task still
fails loudly to the worker log (D4's rule is unchanged) and the row survives. The
test therefore asserts *both* that the task raised and that the row persisted, so
it stays green after the fix rather than going red on the re-raise.

**Why this is driven through the task and not the client.** E3-04's own suite
(`test_the_ags_client_is_a_conformant_service_client.py`) drives
`find_or_create_line_item` on `committed_rows`' session, which the test controls
the commit of — so it never exercises the task's own `SessionLocal` and its
rollback-on-raise. The whole point of this finding is that boundary: the task
opens a session of its own and either commits it or loses it. So this drives
`create_line_item` itself, which is what a Celery worker runs.

**The seams.** The task takes its outbound transport from
`app.services.grading.outbound_transport`, which is monkeypatched to the
in-process `ServiceWire` the same way the launch-to-gradebook tests do it
(`tests/fixtures/line_item_creation.py::reaching_the_platform`). The failure is
posed with `service_wire.failing(token_url, 500)` — the exact shape E3-04's
failing-half test proves records an `ags_call` row before the client raises. The
durable state is read back through `ags_rows`, which reads `ags_call` on
`committed_rows`' own connection after ending its read transaction, so it sees
only what another connection committed — which is the whole question here.

**The cleanup that makes a cross-session commit safe.** `create_line_item` really
commits to the container database (it is not eager and not rolled back by any
fixture), and `committed_rows`' teardown is a diff-delete that removes every row
that appeared during the test, the task's own commits included — the same
teardown the launch criterion tests rely on for the task's committed writes. No
new cleanup is needed.

**Which failure a red here is.** The failing test reds today on a `FAILED`
assertion — the `ags_call` rows are absent because the task rolled them back —
never on an error: the task's own raise is expected and caught, and every
deliverable guard (`app.services.grading`, `app.jobs.tasks.create_line_item`) is a
plain call in a test body that fails naming what it could not find
(`docs/MISTAKES.md` entry 44).

**The environment** is `configured_env`'s over the container's coordinates, laid
down by `tool_doors` inside `ags_sections` (`docs/MISTAKES.md` entry 40); the task
resolves its own `SessionLocal` against the same `DATABASE_URL`.
"""

from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_sections`, `ags_rows`, `ags_contract` come from
# `tests/fixtures/ags_client.py`; `service_wire` from
# `tests/fixtures/roster_sync.py`; `line_item_contract` from
# `tests/fixtures/line_item_creation.py`. All reached as fixtures rather than
# imported: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.

TASK_IS_OWED = (
    "E3-05's work order (D4) puts `create_line_item(section_id)` in "
    "`backend/app/jobs/tasks.py`, shaped like `sync_section_roster`: parse the UUID, open a "
    "`SessionLocal`, call `ensure_line_item`, commit. It is what a Celery worker runs, and the "
    "task's own session is where a failed attempt's `ags_call` rows are either committed or lost."
)


def creation_task(line_item_contract: Any) -> Any:
    """`app.jobs.tasks.create_line_item`, or a failure naming the deliverable that owes it."""
    return line_item_contract.named_in(
        line_item_contract.tasks(), line_item_contract.create_line_item_task, TASK_IS_OWED
    )


def token_endpoint_of(section: Any) -> str:
    """The platform's own OAuth token endpoint, where a client-credentials grant is refused."""
    document = section.platform.discovery() or {}
    url = document.get("token_endpoint")
    assert isinstance(url, str) and url, (
        f"The mock platform advertises no `token_endpoint` (it carries {sorted(document)}), so "
        "there is nothing to refuse a token at and this test could not pose its failure. "
        "`test_mock_lms_client_credentials_grant.py` is where that absence is diagnosed."
    )
    return url


def run_the_task(task: Any, section_id: Any) -> BaseException | None:
    """Run `create_line_item` for one section, answering what it raised rather than raising it.

    Answered rather than propagated so the durability assertion runs whether the
    task fails by raising or returns — and so a raise that is expected on the
    failure path is reported as itself rather than as a collection error. A Celery
    task called directly executes its body synchronously in this process, which is
    what a worker does with it.
    """
    try:
        task(str(section_id))
    except Exception as escaped:
        return escaped
    return None


def test_a_line_item_creation_that_fails_commits_the_calls_it_recorded_before_raising(
    ags_sections: Any,
    service_wire: Any,
    ags_rows: Any,
    ags_contract: Any,
    line_item_contract: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finding, posed at the task: a failed creation must not erase its own call log.

    The task's client is pointed at the in-process wire, the platform's token
    endpoint is made to answer 500, and `create_line_item` is run. The client
    records an `ags_call` row for the refused grant and raises; the task lets the
    `AgsError` propagate; and today `SessionLocal.__exit__` rolls back before the
    commit, so the row is gone.

    **The mutation this kills**: `create_line_item` reaching its `session.commit()`
    only on the success path — the natural shape, since a task that raises looks
    like a task that has nothing to commit. Its fix is to catch the `AgsError`
    family, commit, and re-raise, which is why this test asserts the raise *and*
    the row: a fix that swallowed the error to keep the row would break D4's rule
    that the failure reaches the worker log, and this would catch that too.

    **Read on a separate connection**, which is the entire question. `ags_rows`
    ends its own read transaction and reads `ags_call` on `committed_rows`'
    connection, so a row it sees is a row the task's own `SessionLocal` committed —
    not one visible only inside the transaction that wrote it. A same-session read
    would find the row every time, including today, and prove nothing about
    durability (`docs/MISTAKES.md` entry 3).

    **Its pair is the success test below**, where the same task on a working
    platform commits its rows — the direction that already works. Without it, "the
    rows persist" is asserted only in a world where the task raised, and a task
    that committed nothing in either case would be invisible to this half alone.
    """
    section = ags_sections()
    task = creation_task(line_item_contract)
    line_item_contract.reaching_the_platform(monkeypatch, service_wire)

    grant = token_endpoint_of(section)
    service_wire.failing(grant, 500)

    escaped = run_the_task(task, section.id)

    assert escaped is not None, (
        "The task returned normally for a section whose token endpoint answered 500, so no "
        "creation was attempted or the failure was swallowed. D4 lets the `AgsError` family "
        "propagate to the worker log; a failed attempt that does not fail is a different defect, "
        "and it would make the durability assertion below vacuous — a task that never tried "
        "records nothing."
    )
    persisted = ags_rows.calls_for(section.id)
    assert persisted, (
        f"After a failed `create_line_item` there are no `{ags_contract.call_table}` rows for this "
        "section on a connection that sees only committed work. The client recorded the refused "
        "grant before it raised (E3-04's failing-half test proves the row is written), but the "
        "task lets the error propagate and `SessionLocal.__exit__` rolls it back before "
        "`session.commit()` — so every failed attempt vanishes from SPEC §6.1's console. There is "
        "no hourly backstop for creation the way there is for the roster, so an attacker probing "
        "these endpoints stays invisible in the one log built to show it. The task must commit the "
        "recorded calls and re-raise."
    )
    assert [row for row in persisted if row.get(ags_contract.call_response_code_column) == 500], (
        f"The committed rows for this section are {persisted!r}, none carrying the 500 the tool "
        "met. The status is what tells an operator the credentials were refused rather than the "
        "gradebook service being down (a NULL, per ADR 0129), so a durable row with the wrong "
        "status is durable about the wrong fault."
    )
    assert all(
        urlsplit(str(row.get(ags_contract.call_url_column))).path != urlsplit(grant).path
        for row in persisted
    ), (
        f"A committed row names the token endpoint {grant!r}: {persisted!r}. §6.1's console reads "
        "this log per section, and E3-04's settled rule (decision 5) records a token refusal "
        "against the AGS url, not the platform's OAuth surface — durability must not change what "
        "the row is about."
    )


def test_a_line_item_creation_that_succeeds_commits_its_call_log(
    ags_sections: Any,
    service_wire: Any,
    ags_rows: Any,
    ags_contract: Any,
    line_item_contract: Any,
    metadata_tables: dict[str, Any],
    committed_rows: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair that already works: a successful creation's row is durable, and so is its id.

    Same task, same wire, no injected failure. `create_line_item` reaches the real
    mock, creates the line item, and commits — so afterward another connection sees
    both the `ags_call` row and the stored `section.ags_line_item_url`. This is the
    direction the finding says already works, and it is here so the failure red
    above is not the only asserted state: without it, "the rows persist" is a claim
    about a task that raised and nothing else.

    **Green today.** It rests on the same commit the launch criterion tests drive
    inline; what it adds is the read on a separate connection, which is what makes
    "committed" mean committed rather than merely written.
    """
    section = ags_sections()
    task = creation_task(line_item_contract)
    line_item_contract.reaching_the_platform(monkeypatch, service_wire)

    escaped = run_the_task(task, section.id)

    assert escaped is None, (
        f"`create_line_item` raised {escaped!r} against a working platform. The failure test "
        "above needs a direction that succeeds to be its near miss; if creation cannot succeed "
        "here, this pair says nothing about durability and the manifest's whole-launch criterion "
        "is where a broken create is diagnosed."
    )
    persisted = ags_rows.calls_for(section.id)
    assert persisted, (
        f"A successful `create_line_item` left no `{ags_contract.call_table}` rows on a connection "
        "that sees committed work. Then the task did not commit its call log even on the path that "
        "works, and the failure test above would be asserting a difference between two absences."
    )
    row = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    assert row.get(line_item_contract.line_item_column) is not None, (
        f"The section carries `{line_item_contract.line_item_column}` = "
        f"{row.get(line_item_contract.line_item_column)!r} after a successful creation committed "
        "by the task. The created line item's id is what every later post addresses (ADR 0128), "
        "and a task that recorded the call but not the id would leave E3-06 re-reading the "
        "container forever."
    )
