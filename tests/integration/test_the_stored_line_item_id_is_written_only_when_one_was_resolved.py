"""What `section.ags_line_item_url` is allowed to end up holding — ticket E3-05.

E3-02 created the column and wrote nothing to it; E3-05 is its writer, and the
whole of what that column is for is that every later post can address the line
item without re-reading a container (ADR 0128, and ADR 0052's retry identity
rests on it). So there are exactly two honest states after a creation run: the
address of a line item the platform really serves, or the NULL that was already
there.

**The forbidden state is a stored value that is not a resolved line item.** Work
order decision D3: the fetched id is judged with
`refuse_invalid_fetched_address(settings.environment, column=…, address=…,
resolve=…)`, and "a `RegistrationAddressError` stores nothing, logs at error, and
returns — the next qualifying launch retries." The address in question is one the
*platform* chose at run time, which is the half of the fetched-address rules no
stored column can pose, and the one E1-11's security round found being defeated
one level out.

**Both directions are in one test, on one section, one platform and one
environment.** The refusing half alone is satisfied by a writer that stores
nothing ever — which is the state at HEAD — and the accepting half alone is
satisfied by a writer that stores whatever it is handed. Neither is evidence
about this ticket without the other (`docs/MISTAKES.md` entry 2).

**Two tests, and the second exists because a mutation battery measured the first
one's limit.** E3-04's client already refuses a hostile line-item id and raises
(`test_a_line_item_answered_by_the_container_is_judged_before_it_is_addressed` in
`test_the_ags_client_is_a_conformant_service_client.py`, which tells the judgment
apart from the transport by the raise's `__cause__`). So the first test below —
which drives the real client — is green whether or not `ensure_line_item` does any
judging of its own: the layer beneath refuses first, and the battery confirmed it,
with **both** the deletion of the local re-judgment and the reordering of the store
in front of it surviving. On today's tree nothing distinguished D3's re-judgment
from dead code.

The second test closes that by pinning the layer. It substitutes the client seam —
`app.services.grading.find_or_create_line_item`, the name D3 has the writer call —
for a stand-in that hands back a line item whose `id` the address rules refuse. The
client cannot refuse anything, because the client is not running; the only code
left that can is the writer's own judgment. That the substitution really took is
asserted rather than assumed: the stand-in records its calls and is required to
have been called, so a writer that reached the client by some other route fails
here instead of passing on the real client's refusal (`docs/MISTAKES.md` entry 3).

Both tests are kept. They are not two copies of one rule: the first says the
outcome on the column is right when the whole stack runs, and the second says
which layer produced it.

**Driven under a deployment's `ENVIRONMENT`.** Every rule the address chokepoint
applies is switched off under the development name (ADR 0081), so a refusal test
in development asserts nothing at all; the platform is reached over `https` for
the reason the roster's own refusal suite gives, so that exactly one rule can be
what refuses the hostile value. Resolution is stubbed — **no test in this
repository performs real DNS** — and the stub is
`tests/fixtures/roster_sync.py::StubResolver`.

**Which failure a red is.** Before E3-05 lands, this is expected red on
`pytest.fail` naming `app.services.grading` as a module that does not exist. The
guard is a plain call in the test body (`docs/MISTAKES.md` entry 44).
"""

import logging
import math
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_sections`, `ags_contract` come from `tests/fixtures/ags_client.py`;
# `service_wire`, `roster_contract`, `deployment_settings` and `resolving` from
# `tests/fixtures/roster_sync.py`; `line_item_contract` from
# `tests/fixtures/line_item_creation.py`; `committed_rows` from
# `tests/fixtures/authz_data.py`. All are reached as fixtures rather than
# imported, for the reason every module in this suite gives.

# Where a hostile line-item id points. `127.0.0.1` is the classic fetched-address
# SSRF, and port 9 is the discard port so a request that did escape reaches
# nothing. The same two values `test_the_ags_client_is_a_conformant_service_client.py`
# uses, spelled here rather than imported across test modules.
LOOPBACK_LINE_ITEM = "http://127.0.0.1:9/lineitems/1/lineitem?type_id=1"

# A line-item address the same rules accept under the same deployment name, for the
# accepting half of the substituted-client pair. A globally routable IPv4 literal
# over `https`: a literal because the rules judge one without a lookup, and not
# from a documentation range — `203.0.113.0/24` and `192.0.2.0/24` read like public
# addresses and report `is_global` false, so either would be refused and the pair
# would assert nothing. The same value
# `test_a_launch_stores_the_gradebook_address_it_was_given.py` accepts on the
# neighbouring column, so the two modules can be read side by side.
AN_ACCEPTABLE_LINE_ITEM = "https://93.184.216.34/lineitems/1/lineitem?type_id=1"

# The name D3 has `ensure_line_item` call into E3-04's client with. Substituting it
# is what makes the writer's own judgment the only thing left that can refuse an
# address, which is the whole instrument of the second test.
CLIENT_SEAM = "find_or_create_line_item"

# A sentinel for "the transport was called with no `timeout` keyword at all", which
# is a distinct failing state from `timeout=None` and one the recorder has to be
# able to tell from a real value of `None`.
TIMEOUT_NOT_PASSED = object()


def is_a_bounded_timeout(value: Any) -> bool:
    """Whether `value` is a `requests` timeout that will actually make a stalled dial give up.

    `requests` accepts a single number or a `(connect, read)` pair, and both have
    to be finite and positive to bound anything: `None` waits forever, `0` is
    rejected, and a `nan`/`inf` never elapses. A missing keyword — `TIMEOUT_NOT_PASSED`
    — is the state the finding is about and is unbounded by definition.
    """
    if value is TIMEOUT_NOT_PASSED or value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return math.isfinite(value) and value > 0
    if isinstance(value, tuple) and value:
        return all(
            isinstance(part, int | float)
            and not isinstance(part, bool)
            and math.isfinite(part)
            and part > 0
            for part in value
        )
    return False


def recording_the_timeouts(base: Any) -> list[tuple[str, Any]]:
    """Replace `base.request` with a recorder, and hand back the list it appends to.

    Every outbound call the AGS client makes over this session is captured as
    `(url, timeout)`, whether the client calls `.request(...)` directly — which is
    what the transport uses at `ags.py:739` — or `.get`/`.post`, which route
    through the same `self.request` on the instance. The base session is the wire's
    own, so each request still reaches the in-process platform and the flow runs to
    completion; the recorder only reads the `timeout` the client set on its way
    past.
    """
    recorded: list[tuple[str, Any]] = []
    original = base.request

    def recording(method: str, url: str, **keywords: Any) -> Any:
        recorded.append((url, keywords.get("timeout", TIMEOUT_NOT_PASSED)))
        return original(method, url, **keywords)

    base.request = recording  # type: ignore[method-assign]
    return recorded


WORKER_IS_OWED = (
    "E3-05's work order (D3) puts `ensure_line_item(session, section_id, *, http=None, "
    "settings=None, resolve=None)` there: it locks the section row, re-checks both gradebook "
    "columns under the lock, calls E3-04's find-or-create, judges the answered `id` with "
    "`refuse_invalid_fetched_address`, and — only then — writes `ags_line_item_url` under "
    "`guard_write(table='section', sanction=SANCTION)`. It is the only writer of that column."
)


def worker(line_item_contract: Any) -> Any:
    """`ensure_line_item`, or a failure naming the deliverable that owes it."""
    return line_item_contract.named_in(
        line_item_contract.grading(), line_item_contract.ensure_line_item, WORKER_IS_OWED
    )


def run(worker_callable: Any, session: Any, section_id: Any, **seams: Any) -> BaseException | None:
    """Call the worker, answering what escaped rather than raising it.

    Whether a refused address leaves this function by a raise or by a return is
    deliberately not asserted, the way E3-04's own driver does not assert it: D4
    lets the `AgsError` family propagate to the worker's log, and which of the two
    shapes the refusal takes is the implementer's. What is asserted is the column,
    which is the same either way — and answering the exception rather than letting
    it fly means a refusal that escaped is reported as itself rather than as a
    column that mysteriously stayed NULL.
    """
    try:
        worker_callable(session, section_id, **seams)
    except Exception as escaped:
        return escaped
    return None


class ASubstitutedClient:
    """A stand-in for E3-04's find-or-create that answers one line item and records the call.

    Two jobs, and the second is what keeps the test from proving nothing. It hands
    back an AGS line-item document built by `ags_contract.line_item_document`, so
    the shape is E3-04's own rather than this file's invention. And it **counts its
    calls**, because a substitution that silently missed — a writer reaching the
    client through a module alias, say, so the patched name is never read — would
    leave the real client running, the real client would refuse the hostile address
    exactly as it does today, and the test would pass having pinned nothing
    (`docs/MISTAKES.md` entry 3, and the reason this test exists at all).
    """

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *arguments: Any, **keywords: Any) -> dict[str, Any]:
        self.calls.append((arguments, keywords))
        return dict(self.document)


def errors_under(caplog: pytest.LogCaptureFixture, logger: str) -> list[Any]:
    """Every error-level record one logger wrote, its children included."""
    return [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and (record.name == logger or record.name.startswith(f"{logger}."))
    ]


def pulse_items(section: Any, resource_id: str) -> list[dict[str, Any]]:
    """Every line item the section's own context holds carrying `resource_id`.

    Walked to the last page, for the reason E3-04's suite gives about the same
    read: a claim about a container is not a claim about its first page.
    """
    launch = section.context.launches[0]
    return [
        item
        for page in section.platform.line_item_pages(launch)
        for item in page
        if str(item.get("resourceId")) == resource_id
    ]


def test_a_fetched_line_item_id_the_address_rules_refuse_is_not_stored_and_one_they_accept_is(
    ags_sections: Any,
    service_wire: Any,
    ags_contract: Any,
    roster_contract: Any,
    line_item_contract: Any,
    deployment_settings: Any,
    resolving: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The column holds a resolved line item or it holds nothing. Both halves, one section.

    **The refusing half.** The container answers a line item carrying SPEC §3.4's
    own `resourceId` — so a correct client selects it, and the container read is
    entirely legitimate — whose `id` is a loopback address. A run that ends with
    that string in `section.ags_line_item_url` has stored, permanently, an address
    the tool will fetch with its own Bearer token on every later posting run, with
    nobody present; and the column is the one place E3-06 looks. Nothing is stored,
    and nothing was dialled.

    **The accepting half**, on the same section, the same platform and the same
    deployment name, with the planted container taken away so the real one answers.
    The column then holds the id of a line item the platform actually serves — read
    back off the platform's own container rather than off what the writer returned,
    because a writer agreeing with itself is not evidence (`docs/MISTAKES.md` entry
    19).

    **The mutation this kills**: a writer that assigns the answered member before
    judging it, or that repairs it — `docs/MISTAKES.md` entry 29's shape, a value
    repaired before the check that should have refused it. And the quieter one: a
    writer that stores the *container's* address when it cannot resolve a line item,
    which leaves a column that looks populated and posts every student's grade to a
    collection.

    **What it deliberately does not claim** is which layer refused; see the module
    docstring. The outcome on the column is this ticket's, and it is what is
    asserted.

    **The precondition of the accepting half is asserted before it is read**: the
    real container is required to hold exactly one Pulse line item afterwards, so a
    run where the creation silently failed reports that rather than reporting an
    empty column as a refusal.
    """
    section = ags_sections(roster_contract.https_platform_issuer)
    resolver = resolving({section.host: (roster_contract.a_global_address,)})
    ensure = worker(line_item_contract)
    service_wire.answering(
        str(section.container),
        [ags_contract.line_item_document(LOOPBACK_LINE_ITEM)],
        content_type=ags_contract.container_media_type,
    )

    run(
        ensure,
        committed_rows.session,
        section.id,
        http=service_wire.session(),
        settings=deployment_settings,
        resolve=resolver,
    )
    committed_rows.commit()

    refused = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    assert refused.get(line_item_contract.line_item_column) is None, (
        f"The section carries `{line_item_contract.line_item_column}` = "
        f"{refused.get(line_item_contract.line_item_column)!r} after the container answered a "
        f"line item whose `{ags_contract.line_item_id_member}` is {LOOPBACK_LINE_ITEM!r}. That is "
        "an address the platform chose at run time, and this column is fetched with the tool's "
        "own credentials on a schedule with nobody present — a stored value here is a standing "
        "request this container makes to whatever is listening beside it."
    )
    dialled = [call for call in service_wire.calls if call.host == "127.0.0.1"]
    assert not dialled, (
        f"Something dialled {[call.url for call in dialled]}, which only the answered line item's "
        f"`{ags_contract.line_item_id_member}` named. The address was refused *after* it was "
        "fetched, which is a refusal that arrives one round trip too late."
    )

    service_wire.recovering(str(section.container))

    escaped = run(
        ensure,
        committed_rows.session,
        section.id,
        http=service_wire.session(),
        settings=deployment_settings,
        resolve=resolver,
    )
    committed_rows.commit()

    assert escaped is None, (
        f"With the platform's own container answering, the same section under the same deployment "
        f"raised {escaped!r}. The refusal above would then hold of a writer that refuses every "
        "address there is, which is a writer that never records a line item — and every section "
        "in every institution would stay ungraded with nothing going red but this."
    )
    created = pulse_items(section, ags_contract.resource_id)
    assert len(created) == 1, (
        f"The section's own container holds {len(created)} line items carrying "
        f"{ags_contract.resource_id!r} after a run against the real platform: {created}. With "
        "none, the accepting half below is about a column that was never going to be written and "
        "this test's refusing half is evidence about nothing."
    )
    accepted = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    assert accepted.get(line_item_contract.line_item_column) == created[0].get(
        ags_contract.line_item_id_member
    ), (
        f"The section carries `{line_item_contract.line_item_column}` = "
        f"{accepted.get(line_item_contract.line_item_column)!r} and the line item the platform "
        f"holds is {created[0].get(ags_contract.line_item_id_member)!r}. A column that does not "
        "name the platform's own line item is a score posted somewhere else, or — where it holds "
        "the container's address — every student's grade posted to a collection."
    )


def test_the_writer_judges_the_line_item_id_itself_when_the_client_hands_one_over(
    ags_sections: Any,
    service_wire: Any,
    ags_contract: Any,
    roster_contract: Any,
    line_item_contract: Any,
    deployment_settings: Any,
    resolving: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D3's own re-judgment, pinned to the layer that makes it — a battery survivor closed.

    The test above is green whether or not `ensure_line_item` judges anything,
    because E3-04's client refuses a hostile line-item id first and raises. A
    mutation battery measured exactly that: **both** the deletion of the local
    re-judgment **and** moving the store in front of it survived the whole suite.
    That is the disclosed limit in this ticket's manifest, row 12, and this test is
    what closes it.

    **The instrument.** The client seam is substituted, so
    `app.services.grading.find_or_create_line_item` hands back a line item of this
    test's choosing and reaches no platform at all. With the client not running,
    the only code that can refuse an address is the writer's own — D3:
    "take the document's `id` member, judge it with `refuse_invalid_fetched_address(
    settings.environment, column=AGS_LINE_ITEM_ADDRESS_COLUMN, address=identifier,
    resolve=resolve)` … a `RegistrationAddressError` stores nothing, logs at error,
    returns". Every assertion below is therefore about that judgment and nothing
    else, which is what "pinning the layer" means here.

    **The two mutations this kills**, and neither is killed anywhere else:

      - **the re-judgment deleted.** The stand-in answers a loopback `id`, nothing
        refuses it, and the column ends up holding an address this container will
        fetch with the tool's own Bearer token on every later posting run.
      - **the store moved in front of the judgment.** The refusal still happens and
        still logs, and the column has already been written by the time it does —
        which is `docs/MISTAKES.md` entry 29's shape exactly, a value kept before
        the check that should have refused it, and invisible to any test that only
        reads the log.

    **That the substitution took is asserted, not assumed.** A writer that reached
    the client by another route — a module alias, a late import — would leave the
    real client running and the real client refuses this address anyway, so the
    column assertion would be green and this test would have pinned nothing. The
    stand-in counts its calls and is required to have been called once.

    **The refusing half runs first, and the ordering is forced rather than
    chosen.** The accepting half stores an id, and a section carrying one is one
    D3 returns early for — so the pair can only be posed in this order on one
    section. The accepting half is still what makes the refusal mean something: it
    is the same substitution, the same section and the same deployment name, with
    one address changed, and without it every assertion above holds of a writer
    that stores nothing whatever it is handed.
    """
    section = ags_sections(roster_contract.https_platform_issuer)
    resolver = resolving({section.host: (roster_contract.a_global_address,)})
    ensure = worker(line_item_contract)
    grading = line_item_contract.grading()
    line_item_contract.named_in(
        grading,
        CLIENT_SEAM,
        "E3-05's work order (D3) has `ensure_line_item` call E3-04's "
        "`app.lti.ags.find_or_create_line_item(session, section_id, http=…, settings=…, "
        "resolve=…)`. Substituting that name on this module is the only way to ask which layer "
        "refuses a line-item address, since the client refuses one on its own.",
    )
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=line_item_contract.grading_logger)

    refusing = ASubstitutedClient(ags_contract.line_item_document(LOOPBACK_LINE_ITEM))
    monkeypatch.setattr(grading, CLIENT_SEAM, refusing)

    escaped = run(
        ensure,
        committed_rows.session,
        section.id,
        http=service_wire.session(),
        settings=deployment_settings,
        resolve=resolver,
    )
    committed_rows.commit()

    assert len(refusing.calls) == 1, (
        f"The substituted client was called {len(refusing.calls)} times. The writer either did "
        "not reach the client at all, or reached it by a route this substitution does not "
        f"cover — and in the second case E3-04's real client ran, refused "
        f"{LOOPBACK_LINE_ITEM!r} on its own, and everything below would be green while pinning "
        f"nothing. D3 has the writer call `{CLIENT_SEAM}` on its own module, which is what "
        "makes the substitution reach it."
    )
    refused = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    stored = refused.get(line_item_contract.line_item_column)
    assert stored is None, (
        f"The section carries `{line_item_contract.line_item_column}` = {stored!r} after a "
        f"client that answered a line item whose `{ags_contract.line_item_id_member}` is "
        f"{LOOPBACK_LINE_ITEM!r}. Nothing "
        "beneath this writer refused it — the client is substituted — so a fetched address the "
        "rules refuse is now the standing target of every posting run for this section.\n\n"
        "Three things this can be, in the order worth checking. The writer does not judge the "
        "address it is handed at all. It judges but stores first, which still logs and is still "
        "wrong (`docs/MISTAKES.md` entry 29 — a value kept before the check that should have "
        "refused it). Or it judges under a column constant that is in `FETCHED_COLUMNS` and not "
        "in `LOOPBACK_REFUSED_COLUMNS`, in which case the judgment is running and loopback is "
        "simply not among the things it refuses on this column — "
        "`tests/unit/test_registration_address_constraints.py` is where that membership is "
        "pinned, and E3-04's client refuses this same address on the same document."
    )
    assert errors_under(caplog, line_item_contract.grading_logger), (
        "No error-level record arrived under "
        f"`{line_item_contract.grading_logger}` when the address was refused. D3: the refusal "
        "'stores nothing, logs at error, returns'. Without the record a section silently stops "
        "acquiring a line item and §6.3's console has nothing to show for it — and the column "
        "assertion above is equally true of a writer that never ran."
    )
    assert escaped is None, (
        f"The refusal escaped as {escaped!r}. D3 has this path log and return: the next "
        "qualifying launch retries, and a raise out of the worker turns a platform's bad "
        "answer into a task failure an operator has to read a traceback to understand."
    )

    caplog.clear()
    accepting = ASubstitutedClient(ags_contract.line_item_document(AN_ACCEPTABLE_LINE_ITEM))
    monkeypatch.setattr(grading, CLIENT_SEAM, accepting)

    escaped = run(
        ensure,
        committed_rows.session,
        section.id,
        http=service_wire.session(),
        settings=deployment_settings,
        resolve=resolver,
    )
    committed_rows.commit()

    assert escaped is None, (
        f"With an acceptable line-item address the same call raised {escaped!r}. The refusal "
        "above would then hold of a writer that refuses every address there is, which is a "
        "writer that never records a line item at all."
    )
    assert len(accepting.calls) == 1, (
        f"The substituted client was called {len(accepting.calls)} times on the accepting half, "
        "so this direction is not the one it claims to be."
    )
    accepted = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    kept = accepted.get(line_item_contract.line_item_column)
    assert kept == AN_ACCEPTABLE_LINE_ITEM, (
        f"The section carries `{line_item_contract.line_item_column}` = {kept!r} and the client "
        f"answered {AN_ACCEPTABLE_LINE_ITEM!r}, which the registration-address rules accept "
        "under this deployment name. A writer that refuses an address a real platform would "
        "advertise leaves the section with no line item and no score ever posted, and the "
        "refusal above would be evidence about a writer that is simply inert."
    )
    logged = errors_under(caplog, line_item_contract.grading_logger)
    written = [record.getMessage() for record in logged]
    assert not written, (
        "An acceptable line-item address was stored and an error-level record was written "
        f"anyway: {written}. Then the error record asserted on the refusing half says nothing "
        "about a refusal — it is written on every run."
    )


def test_the_writer_dials_the_platform_under_a_bounded_transport_timeout(
    ags_sections: Any,
    service_wire: Any,
    ags_contract: Any,
    line_item_contract: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The transport `ensure_line_item` reaches AGS over carries a finite timeout — security round.

    **The finding (MEDIUM, bounded transport).** `ensure_line_item` holds
    `SELECT … FOR UPDATE` on the section row across up to four outbound HTTP calls,
    and the AGS transport dials with no `timeout`. A platform that completes the TCP
    handshake and then never answers holds the row lock, the database connection
    and the worker slot forever. There is one default queue, so a worker wedged
    here also stops `reclassify_floored_comments`, and §3.3's floored safety
    verdicts never arrive — a stalled gradebook write becomes a safety outage.

    **The lock is not the bug and must not move.** It serializes two workers racing
    to create one section's line item, and narrowing it to exclude the HTTP would
    let both create one. The fix is a bounded timeout on the transport, so a dial
    that stalls gives up and releases everything on its own.

    **The pin.** The transport handed to the client is the wire's own session with
    its `request` wrapped to record the `timeout` of every outbound call (see
    `recording_the_timeouts`). The writer is driven to a successful creation so the
    flow actually reaches the AGS calls at `ags.py:739`, and every call that is not
    to the platform's OAuth token endpoint is required to carry a finite, positive
    timeout. Today none do — the transport is dialled with no `timeout` keyword —
    so this reds on a `FAILED` naming the unbounded call.

    **The mutation this kills**: `self.transport.request(...)` with no `timeout=`,
    which is `docs/MISTAKES.md` entry 41's own subject arriving on the AGS side —
    a client library's default (`None`, wait forever) on a path that holds a lock,
    a connection and a worker while it waits. The argument-capture pin is
    deterministic; a genuinely stalled in-process server would be a stronger proof
    but a slower and flakier one, and the finding accepts the capture.

    **The token-acquisition path is the neighbouring risk, and this test does not
    force it.** `self.connector.get_access_token` dials the OAuth endpoint, and
    whether it shares this transport is not something the test can see from here;
    calls to the token endpoint are therefore excluded from the hard assertion and
    left to the implementer to bound, exactly as the finding directs. Where the
    connector *does* use this session, its timeout is captured too and reported in
    the failure message, so a reviewer can see whether it was bounded — but a
    green here does not claim it was.

    **The control comes first.** The AGS calls are required to be non-empty before
    their timeouts are judged: a run that never reached the transport would satisfy
    "every AGS call is bounded" vacuously, which is `docs/MISTAKES.md` entry 3.
    """
    section = ags_sections()
    ensure = worker(line_item_contract)
    base = service_wire.session()
    recorded = recording_the_timeouts(base)

    escaped = run(ensure, committed_rows.session, section.id, http=base)
    committed_rows.commit()

    assert escaped is None, (
        f"Driving `ensure_line_item` against a working platform raised {escaped!r}, so the flow "
        "did not reach the AGS transport and there is nothing here to have timed. This is a "
        "control on the test, not the finding."
    )
    stored = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    assert stored.get(line_item_contract.line_item_column) is not None, (
        "The creation did not store a line-item id, so the writer did not run to completion and "
        "may not have made the AGS calls this test is timing."
    )
    assert recorded, (
        "The client made no outbound call at all over the transport this test handed it. Then "
        "either the writer did not reach the client or it built a transport of its own — and a "
        "timeout on a session nothing dials over bounds nothing (`docs/MISTAKES.md` entry 3)."
    )

    token_endpoint = (section.platform.discovery() or {}).get("token_endpoint")
    token_path = urlsplit(token_endpoint).path if isinstance(token_endpoint, str) else None
    ags_calls = [(url, timeout) for url, timeout in recorded if urlsplit(url).path != token_path]
    token_calls = [(url, timeout) for url, timeout in recorded if urlsplit(url).path == token_path]

    assert ags_calls, (
        f"Every recorded call was to the token endpoint {token_endpoint!r}: {recorded!r}. The "
        "finding is about the AGS transport at `ags.py:739`, so the flow has to reach at least one "
        "line-item call for this test to say anything — a successful creation reads the container "
        "and posts to it, both over this transport."
    )
    unbounded = [(url, timeout) for url, timeout in ags_calls if not is_a_bounded_timeout(timeout)]
    assert not unbounded, (
        f"These AGS calls were dialled with no bounded timeout: {unbounded!r} (a value of "
        f"`{TIMEOUT_NOT_PASSED!r}` means no `timeout` keyword was passed at all). "
        "`ensure_line_item` holds `SELECT … FOR UPDATE` on the section across these calls, so a "
        "platform that completes the handshake and never answers holds the row lock, the database "
        "connection and the worker slot forever — and on the single default queue that also stalls "
        "`reclassify_floored_comments`, so §3.3's floored safety verdicts stop arriving. The lock "
        "is correct and must stay; the transport has to carry a finite timeout.\n\n"
        f"For the reviewer, the token-endpoint calls captured over this same transport were "
        f"{token_calls!r}; those are the neighbouring `get_access_token` risk the finding leaves "
        "to the implementer to bound, and this assertion does not force them."
    )
