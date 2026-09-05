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

**What this module does not claim, said plainly.** E3-04's client already refuses
a hostile line-item id and raises
(`test_a_line_item_answered_by_the_container_is_judged_before_it_is_addressed` in
`test_the_ags_client_is_a_conformant_service_client.py`, which tells the judgment
apart from the transport by the raise's `__cause__`). So the refusing half here
would also be green against a writer whose own re-judgment was deleted: the layer
below refuses first. That is a limit of this test and not a weakness in the
criterion — what E3-05 owes and what is asserted here is the **outcome on the
column**, which no other module asserts and which the two failure modes worth
fearing both break: a writer that stored the container's address, an empty
string, or the raw member it could not judge.

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

from typing import Any

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
