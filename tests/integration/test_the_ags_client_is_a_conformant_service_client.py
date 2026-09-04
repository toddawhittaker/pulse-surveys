"""The AGS client posts a grade the way a conformant tool does — E3-04, criteria 1 to 10.

The epic's pinch point, asserted from the client's side of the wire. E3-04 builds
`app.lti.ags` on the roster sync's conformance shape — the transport as a
constructor argument, a client-credentials token per scope, the registration
resolved from the section's own deployment, the no-redirect session and the pinned
resolution adapter — and this module drives it against the real mock platform.

**Where the evidence comes from, and why it is three places.**

  - **The wire** (`service_wire`) records every request as it left the client: its
    method, its URL, its `Authorization` header and its body. That is what says the
    client has *one* path and it is this one, which a status code cannot say — and
    it is the only place the naive scores address and the address never dialled can
    be seen at all.
  - **`GET /mock/posted-scores`** is what the platform received, verbatim (ADR
    0047). A conformant `Result` carries no timestamp and no progress members, so
    the fields criteria 3 and 9 are about cannot come back through the protocol.
    Nothing in `backend/` may know that route exists; only a test.
  - **`ags_call`** is what an operator will see (SPEC §6.1). Criterion 8 is about
    the rows, and the rows are read from the database rather than from anything the
    client returned.

**Criterion 3 is a comparison, never an inspection.** "The string that arrives at
the platform is the string the caller supplied, asserted by comparing the two rather
than by inspecting either alone." So the ledger this suite hands over is compared
with the ledger the platform stored, and the score is compared in two ways that fail
differently: the stored value re-rendered as JSON must equal the caller's string, and
the request body on the wire must carry that string as a numeric token. The second is
the byte-exact half — `61.50` and `61.5` are one float and two strings, and only the
wire can tell them apart.

**What this module does not assert, and it is a boundary rather than a gap.** The
end-to-end tie between the ledger the *grading service* computes and the ledger that
reaches the platform belongs to E3-06's criterion 4; this ticket proves only faithful
carriage, because the client and the formula share nothing (criterion 3 says so in as
many words). And where a line item's maximum is not 100, whether the client rescales
`scoreGiven` is asserted nowhere here: ADR 0051 settles that the *maximum* sent is
the line item's own and settles nothing about the value, so pinning one would be this
module deciding it.

**Every red in this module is an assertion, not an import.** `app.lti.ags` and
`app.lti.platforms` do not exist on the tree these tests were written against, and
`tests/fixtures/ags_client.py` imports them inside the call rather than in a fixture
so that each test fails naming the deliverable it is about — `docs/MISTAKES.md` entry
44, which is that a tests-first suite's red must be a FAILED and never an ERROR.

**The controls come first and they must be green.** The wire, the stored gradebook
address and the composed container are machinery, and machinery whose only evidence
is that the tests using it went red proves nothing (`docs/MISTAKES.md` entry 35). **A
red in the control section means these tests are broken, not the client.**
"""

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_client`, `ags_section`, `ags_sections`, `ags_rows` and `ags_contract` come
# from `tests/fixtures/ags_client.py`; `service_wire`, `roster_contract`,
# `deployment_settings` and `resolving` from `tests/fixtures/roster_sync.py`. All are
# reached as fixtures rather than imported, for the reason every module in this suite
# gives: an import of a fixtures module by name depends on where pytest put `tests/`
# on `sys.path`, and an import error is not a red.

# Where a hostile address points. `127.0.0.1` is the classic fetched-address SSRF —
# ADR 0081 rule 3 refuses loopback only on the browser-facing column, on the argument
# that "that string is never resolved in this container", which is precisely untrue
# of an address this client fetches with the tool's Bearer token attached. Port 9 is
# the discard port, so a request that did escape reaches nothing.
LOOPBACK_CONTAINER = "http://127.0.0.1:9/lineitems"
LOOPBACK_LINE_ITEM = "http://127.0.0.1:9/lineitems/1/lineitem?type_id=1"

# A label the platform holds for a line item Pulse created and somebody renamed. The
# whole point of settled decision 7 is that this is *not* what the client matches on.
A_RENAMED_LABEL = "Weekly Pulse Check (renamed by the instructor)"

# AGS 2.0's own query parameter on the Result container, which selects one student's
# result. **The specification's name, not this suite's**: the mock's `read_results`
# declares it and `MockPlatform.results(line_item, user_id=…)` sends it, and a tool
# reading one student's grade has to send exactly this string. It is named here
# because the re-read below is asserted to be filtered *on the wire* and unfiltered
# *in the call log*, which is a statement about this parameter in two places.
RESULT_USER_FILTER = "user_id"

# Two spellings of one percentage, and the pair is criterion 3's whole instrument.
# **Written here rather than read off `ags_contract`** because a parametrisation needs
# its values at collection time and a fixture cannot supply them there — the same
# reason `tests/unit/test_registration_address_constraints.py` writes its environment
# names out. `A_FLOAT_STABLE_SCORE` is `tests/fixtures/ags_client.py`'s own default,
# and a control below holds the two against `json` itself.
#
# The second one is why the pair exists. `str(float("61.5"))` is `"61.5"`, so against
# the first row alone a client that parsed the caller's string into a float and
# re-serialised it sends byte-identical output and the mutation is invisible — a
# fixture value that made the property unobservable, which is `docs/MISTAKES.md` entry
# 30's shape. `61.50` is the same quantity, is an RFC 8259 number so nothing refuses
# it for an unrelated reason, and does not survive the round trip.
A_FLOAT_STABLE_SCORE = "61.5"
A_FLOAT_UNSTABLE_SCORE = "61.50"
BYTE_EXACT_SCORES = (A_FLOAT_STABLE_SCORE, A_FLOAT_UNSTABLE_SCORE)

# The maximum a line item that is not out of 100 carries. **This suite's choice**, and
# the one property it needs is that it differs from `PULSE_SCORE_MAXIMUM`: a client
# that sent a constant 100 is refused by the mock (ADR 0051), which is what makes
# "reads the maximum" and "assumes the maximum" two different observable behaviours.
A_DIFFERENT_MAXIMUM = 50


# ---------------------------------------------------------------------------
# Driving the client.
# ---------------------------------------------------------------------------


def drive(
    ags_client: Any,
    function: Any,
    section: Any,
    rows: Any,
    wire: Any,
    *,
    settings: Any = None,
    resolve: Any = None,
    profile: Any = None,
    line_item: Any = None,
    grade: Any = None,
    http: Any = None,
) -> tuple[Any, BaseException | None]:
    """Call one of the client's entry points, answering what it returned and what it raised.

    Whether the client raises or returns on a refusal is deliberately not asserted
    anywhere in this module, the way it is not in E1-11's: ADR 0090's consequences
    leave that to the writer. What is asserted is the call it made or did not make,
    the row it left, and the value that reached the platform.

    **The commit is attempted whichever way the call exited**, and that is the one
    thing here that is not a copy of the roster suite's driver. Criterion 8 requires
    a row for a *failure*, and a helper that rolled the session back on the raise
    path would throw that row away and report a client which records failures as one
    that does not — a test failing for the harness's reason, which is the shape this
    whole file is written against. A commit that itself fails falls back to a
    rollback, because a session left in a broken transaction poisons every read after
    it.

    Each role is offered only where the test supplies one, so a client that does not
    take `resolve` or `profile` is driven exactly as it would be without them, and a
    client that renamed a parameter is caught by `AgsClient.call`'s own failure
    naming it rather than by thirty tests going quietly wrong.
    """
    available: dict[str, Any] = {
        "session": rows.session,
        "section_id": section.id,
        "http": wire.session() if http is None else http,
    }
    for role, value in (
        ("settings", settings),
        ("resolve", resolve),
        ("profile", profile),
        ("line_item", line_item),
    ):
        if value is not None:
            available[role] = value
    if grade is not None:
        available["user_id"] = grade.user_id
        available["score"] = grade.score
        available["ledger"] = grade.ledger
        available["timestamp"] = grade.timestamp

    answered: Any = None
    raised: BaseException | None = None
    try:
        answered = ags_client.call(function, **available)
    except Exception as failure:
        raised = failure
    try:
        rows.commit()
    except Exception:  # pragma: no cover - a broken transaction, not a branch
        rows.session.rollback()
    return answered, raised


def refused_by_the_judgment(
    raised: BaseException | None, address: str, ags_contract: Any, whose: str
) -> None:
    """Require that `raised` is the client refusing `address`, not the transport failing on it.

    **The discriminator, and the two loopback tests rest on it entirely.** Both paths
    end the same way from the outside — nothing is dialled, a failure row is written,
    the call raises — because the client mounts a pinned-resolution transport that
    fails closed on a host it never pinned. So an assertion that the hostile host was
    never reached is satisfied by a build with the address judgment deleted: the
    transport refuses instead, one layer lower, and the test reports a rule that is
    not there as working (`docs/MISTAKES.md` entry 3).

    `__cause__` is where the two differ and it is the client's settled contract: a
    judgment refusal is raised **from** `RegistrationAddressError`, a transport
    refusal **from** `requests.ConnectionError`. Both halves are asserted — the cause
    is the judgment's error, and it is *not* the transport's — because a build that
    raised from neither would satisfy a one-sided check by carrying no cause at all.

    The error itself is required to come from the client's own module rather than
    being whatever escaped, which is the same "typed error" requirement the conflict
    path keeps: a caller has to be able to branch on it.
    """
    import requests

    assert raised is not None, (
        f"The client was given {whose} gradebook address {address!r} and returned normally. A "
        "refused address means no line item was found or created, so a caller that cannot tell "
        "that from success will go on to post a grade against nothing."
    )
    assert type(raised).__module__ == ags_contract.module, (
        f"The client raised {type(raised).__module__}.{type(raised).__name__}, which is not defined "
        f"in `{ags_contract.module}`. The refusal has to be a typed error a caller can branch on — "
        "an exception that escaped from a library is indistinguishable from every other failure "
        "fetching a container can have."
    )
    cause = raised.__cause__
    assert not isinstance(cause, requests.ConnectionError), (
        f"The client raised {type(raised).__name__} from a "
        f"{type(cause).__name__} — the transport's own refusal. That is the masking this assertion "
        "exists for: the pinned-resolution transport fails closed on a host it never pinned, so "
        f"{address!r} is not dialled whether or not the address was ever judged, and every other "
        "assertion in this test holds either way. A refusal that reached the transport is a "
        "refusal the address rules did not make."
    )
    assert isinstance(cause, ags_contract.address_error()), (
        f"The client raised {type(raised).__name__} from {cause!r}, and a refused address is "
        "raised from `app.models.lti.RegistrationAddressError`. Without that cause this test "
        "cannot say which layer refused, and the address judgment can be deleted with the whole "
        "module still green — which is what the mutation battery measured."
    )


def calls_to(wire: Any, url: str, method: str | None = None) -> list[Any]:
    """Every request the client made to `url`'s path, optionally of one method."""
    path = urlsplit(url).path
    return [
        call
        for call in wire.calls
        if call.path == path and (method is None or call.method.upper() == method.upper())
    ]


def ags_calls(wire: Any, platform: Any) -> list[Any]:
    """Every request the client made that was not to the token endpoint.

    The split is criterion 8's grain: `ags_call` is one row per AGS HTTP call, and a
    client-credentials grant is not one — it is how the call is authorised, and its
    own failure is recorded against the AGS URL rather than as a call of its own
    (which is the roster's rule, unchanged).
    """
    token_url = (platform.discovery() or {}).get("token_endpoint")
    assert isinstance(token_url, str) and token_url, (
        "The platform advertises no `token_endpoint`, so this cannot tell a grant apart from a "
        "service call and the row count below would be about both. "
        "`test_mock_lms_client_credentials_grant.py` is where that absence is diagnosed."
    )
    token_path = urlsplit(token_url).path
    return [call for call in wire.calls if call.path != token_path]


def token_endpoint(platform: Any) -> str:
    document = platform.discovery() or {}
    url = document.get("token_endpoint")
    assert isinstance(url, str) and url, (
        f"The platform's discovery document advertises no `token_endpoint` (it carries "
        f"{sorted(document)}), so there is no endpoint for this test to fail and it could not pose "
        "its question."
    )
    return url


def stored_line_item(platform: Any, launch_context: Any, **overrides: Any) -> dict[str, Any]:
    """One line item created on the platform out of band, for the section to point at.

    Created through the driver's own credentialed helper rather than by the client,
    because these tests are about what the client does with a line item that is
    *already there* — the first branch of settled decision 7, and the one a section
    is in on every run after the first.
    """
    return platform.create_line_item(launch_context.launches[0], **overrides)


def container_line_items(platform: Any, section: Any) -> list[dict[str, Any]]:
    """Every line item the section's context holds, walked to the last page.

    Walked rather than read one page deep: settled decision 7's "a second Pulse
    Participation column can never appear" is a claim about the whole container, and
    a first-page read of a container that pages at five would satisfy it while the
    duplicate sat on page two (`docs/MISTAKES.md` entry 3 with a bound instead of a
    zero).
    """
    return [item for page in platform.line_item_pages(section.context.launches[0]) for item in page]


def pulse_line_items(platform: Any, section: Any, resource_id: str) -> list[dict[str, Any]]:
    """Every line item in the container carrying `resource_id`."""
    return [
        item
        for item in container_line_items(platform, section)
        if str(item.get("resourceId")) == resource_id
    ]


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the client.**
# ---------------------------------------------------------------------------


def test_the_wire_carries_an_authenticated_ags_call_and_refuses_an_unmounted_host(
    ags_section: Any, service_wire: Any, ags_contract: Any
) -> None:
    """The transport under every assertion in this module, exercised both ways.

    A `requests.Session` that answered nothing would make every "the client called
    this" assertion unfalsifiable and every "it did not call that" assertion
    trivially true. So it is required to *fetch* — the section's own stored container
    address, through the real mock, carrying a token the platform's own endpoint
    issued for the line-item read-only scope — and to *refuse* a host nothing
    mounted, which is what stands between "the client dialled somewhere it should
    not" and a silent pass.

    The credential is presented because E3-04 puts the mock's AGS routes behind one:
    a bare GET here would answer 401 and this control would report the wire as broken
    when it is the enforcement working.

    **A red here means these tests are broken, not the client.**
    """
    session = service_wire.session()
    answered = session.get(
        str(ags_section.container),
        headers={
            "accept": ags_contract.container_media_type,
            "authorization": (
                f"Bearer {ags_section.platform.ags_token(ags_contract.line_item_readonly_scope)}"
            ),
        },
    )
    assert answered.status_code == 200, (
        f"The wire answered {answered.status_code} for the section's own stored container address "
        f"{ags_section.container!r}, carrying a token this platform's own endpoint issued for "
        f"{ags_contract.line_item_readonly_scope!r}. Body begins {answered.text[:300]!r}."
    )
    assert isinstance(answered.json(), list), (
        f"The wire carried back {answered.text[:300]!r}, which is not an AGS line-item container. "
        "AGS 2.0 serves an array, and every assertion in this module about what the client found "
        "rests on the mock's real container reaching it through this transport."
    )
    assert service_wire.to_host(ags_section.host), (
        "The wire recorded no call to the platform's host, so its record is empty and every "
        "assertion in this module that reads it would be satisfied by a client that made no "
        "request at all."
    )

    with pytest.raises(Exception, match="no application is mounted"):
        session.get("http://a-platform-nobody-registered.invalid/lineitems")


def test_the_section_stores_the_gradebook_address_the_launch_advertised(
    ags_section: Any, ags_contract: Any
) -> None:
    """The row every run in this module starts from, checked against the platform's claim.

    E3-02 stores the AGS endpoint claim's `lineitems` member on the section, and the
    whole of this ticket is what the client does with it. A section whose column held
    something else — a roster address, an empty string, the claim of a different
    context — would send every client run somewhere this module never meant, and the
    refusal tests would pass for the wrong reason.

    The comparison is against the claim the platform actually signs into a launch,
    read through the launch rather than composed here, so nothing about the mock's
    paths is written down.

    **A red here means these tests are broken, not the client.**
    """
    claimed = ags_section.platform.line_items_url(ags_section.context.launches[0])
    assert ags_section.container == claimed, (
        f"The section holds `{ags_contract.container_column}` {ags_section.container!r} and the "
        f"launch's AGS endpoint claim advertises {claimed!r}. E3-02 stores the claim's `lineitems` "
        "member, and a column holding anything else points this client at a gradebook that is not "
        "the section's."
    )
    assert ags_section.container != str(ags_section.synced.address), (
        f"The section's gradebook address and its roster address are both "
        f"{ags_section.container!r}. Two claims, two columns and one value means whichever of them "
        "this fixture wrote is answering for both, and a client reading the wrong one would look "
        "correct here."
    )


def test_the_container_this_suite_composes_is_the_shape_the_mock_serves(
    ags_section: Any, service_wire: Any, ags_contract: Any
) -> None:
    """The planted container is checked against the real one before anything reads it.

    One test below installs a line-item container this suite wrote, because no mock
    platform can be asked to advertise a line item whose `id` points at loopback —
    the address the *platform* chooses at run time is exactly the half of the
    fetched-address rules a stored column cannot pose. That is a licence to drift
    into a document no platform sends, so the composed one is compared against the
    real container's own member names here.

    **A red here means these tests are broken, not the client.**
    """
    ags_section.platform.create_line_item(ags_section.context.launches[0])
    real = service_wire.session().get(
        str(ags_section.container),
        headers={
            "accept": ags_contract.container_media_type,
            "authorization": (
                f"Bearer {ags_section.platform.ags_token(ags_contract.line_item_readonly_scope)}"
            ),
        },
    )
    assert real.status_code == 200, (
        f"The real container answered {real.status_code}, so there is nothing to compare a "
        f"composed line item against. Body begins {real.text[:300]!r}."
    )
    served = ags_section.platform.line_items_of(real)
    assert served, (
        f"The container served no line items after one was created through it: {real.text[:300]!r}. "
        "A comparison against an empty set would accept any composed document at all."
    )

    composed = ags_contract.line_item_document(LOOPBACK_LINE_ITEM)
    unknown = sorted(set(composed) - set().union(*(set(item) for item in served)))
    assert not unknown, (
        f"The composed line item carries {unknown}, which no line item the mock serves carries — "
        f"the mock's carry {sorted(set().union(*(set(item) for item in served)))}. A composed "
        "container that has drifted from the real document teaches this ticket a shape no platform "
        "sends."
    )
    for member in (
        ags_contract.line_item_id_member,
        ags_contract.resource_id_member,
        ags_contract.score_maximum_member,
    ):
        assert member in composed, (
            f"The composed line item omits `{member}`, which is one of the three the client reads: "
            "the id it addresses, the resource id it matches on, and the maximum it posts against."
        )


# ---------------------------------------------------------------------------
# Criterion 1, and settled decision 7 — find or create, matched by id then by
# `resourceId`, never by label.
# ---------------------------------------------------------------------------


def test_a_stored_line_item_id_is_read_and_the_container_is_never_walked(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Settled decision 7's first branch: the id Pulse stored is the first thing tried.

    "GET the stored id if the section holds one." A client that walked the container
    every time would be correct and would cost a paged read per section per posting
    run, and — worse — would re-match by `resourceId` on every run, which is the
    fallback rather than the rule.

    **The mutation this kills:** the stored id ignored, so find-or-create always
    walks. Every other test in this group stays green under it, because they all
    describe containers the walk finds the right answer in.

    **Both halves.** The stored id is required to have been *fetched* — a client that
    returned the stored string without asking the platform whether it still exists
    has not found a line item, it has repeated one back — and the container is
    required not to have been read at all, which is the half that says the walk did
    not happen.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, (
        f"Finding the section's line item raised {raised!r}. The section holds the id of a line "
        "item this platform is serving, which is the ordinary state of every section after its "
        "first posting run."
    )

    reads = calls_to(service_wire, identifier, "GET")
    assert reads, (
        f"The client made no `GET` of the stored line item id {identifier!r}. The calls it made "
        f"were {service_wire.calls}. Settled decision 7 reads the stored id first, and a client "
        "that answered with the string it was given has not established the line item still "
        "exists."
    )
    walked = calls_to(service_wire, section.container)
    assert not walked, (
        f"The client read the line-item container at {section.container!r} although the section "
        "holds an id the platform serves. The walk is the fallback for a stored id that is gone, "
        "not the rule — a client that always walks pays a paged read per section per run and "
        "matches on `resourceId` where it should have matched on the id."
    )
    assert (
        str(ags_contract.member(answered, ags_contract.line_item_id_member, "Find-or-create"))
        == identifier
    ), (
        f"Find-or-create answered a line item whose id is not the stored {identifier!r}. The "
        "client persists nothing itself (E3-05 spends that grant), so what it answers is the only "
        "thing its caller has to post against."
    )


def test_a_stored_id_the_platform_no_longer_serves_is_re_found_by_resource_id_not_by_label(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Settled decision 7's second branch, over the case matching by label gets wrong.

    "On 404/absent, walk the container's pages and match `resourceId ==
    'pulse-participation'`… A renamed line item (label changed, `resourceId` intact)
    is re-found." An instructor renaming a gradebook column is an ordinary thing to
    do, and a client matching on the label meets it as "no Pulse line item here" and
    creates a second one — a duplicate column per section per run, which is the
    failure settled decision 7 exists to make impossible.

    **The mutations this kills**, and neither is visible to any other test here:

      - the fallback matching on `label` rather than on `resourceId`. The line item
        below carries the settled resource id and a label nobody would guess, so a
        label match finds nothing and creates.
      - the 404 on the stored id treated as fatal. The section holds an id the
        platform will not serve, which is what a line item deleted in the LMS since
        Pulse stored it looks like, and a client that raised there would stop posting
        for that section for the rest of the term.

    **The 404 is planted on the wire rather than on the platform**, and it has to be:
    the mock serves no delete, so there is no way to ask it for a line item it once
    had and no longer has. What it stands for is the platform's answer, and the
    container still lists the line item throughout — which is exactly the state a
    deleted-and-restored, or a re-keyed, gradebook is in.

    **The pair is the assertion that nothing was created.** "Re-found" and "created
    again" both end with a line item carrying the resource id, and only the count and
    the id tell them apart.
    """
    section = ags_sections()
    created = section.platform.create_line_item(
        section.context.launches[0],
        label=A_RENAMED_LABEL,
        resourceId=ags_contract.resource_id,
    )
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)
    service_wire.failing(identifier, 404)

    answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, (
        f"The stored id answered 404 and find-or-create raised {raised!r}. Settled decision 7 "
        "makes that the case the container walk exists for: a line item deleted or re-keyed in the "
        "LMS is a state to recover from, not a section to stop posting for."
    )
    assert (
        str(ags_contract.member(answered, ags_contract.line_item_id_member, "Find-or-create"))
        == identifier
    ), (
        f"Find-or-create answered a line item whose id is not {identifier!r}, the one the container "
        f"lists carrying `{ags_contract.resource_id_member}` {ags_contract.resource_id!r} under the "
        f"label {A_RENAMED_LABEL!r}. Matching on the label finds nothing here, which is the whole "
        "point of the row."
    )
    matching = pulse_line_items(section.platform, section, ags_contract.resource_id)
    assert len(matching) == 1, (
        f"The container holds {len(matching)} line items carrying "
        f"`{ags_contract.resource_id_member}` {ags_contract.resource_id!r}: "
        f"{[item.get('id') for item in matching]}. The renamed one was already there, so a second "
        "means the client matched on the label, found nothing and created a duplicate gradebook "
        "column — which is the failure settled decision 7 exists to make impossible."
    )


def test_a_container_holding_no_pulse_line_item_gets_one_created_with_the_settled_members(
    ags_client: Any,
    ags_section: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Settled decision 7's third branch, and the three members it fixes.

    "None found → POST a new line item carrying that `resourceId`, label 'Pulse
    Participation', `scoreMaximum` 100."

    **The mutations this kill.** A create that omits `resourceId` — which is the
    member every later run matches on, so a line item created without one is one the
    next run cannot find and duplicates. A create that sends the label as the
    identity, which the test above already refuses from the other side. And a
    `scoreMaximum` other than 100, which SPEC §3.4 makes the default a percentage is
    posted against; the score post is refused outright by this platform when the two
    disagree (ADR 0051), so a wrong maximum here is a gradebook column that can never
    be written to.

    The container is read back through the platform rather than from what the client
    answered: a client that returned a well-formed line item it never stored would
    satisfy every assertion made against its return value.

    **The guard first.** The container is required to hold no Pulse line item before
    the run, because "exactly one afterwards" is satisfied by a client that created
    nothing when one was already there.
    """
    before = pulse_line_items(ags_section.platform, ags_section, ags_contract.resource_id)
    assert not before, (
        f"The container already holds {len(before)} line item(s) carrying "
        f"`{ags_contract.resource_id_member}` {ags_contract.resource_id!r} before the client ran, "
        "so this test cannot tell a create from a find. E0-15 seeds no line items."
    )

    _answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        ags_section,
        committed_rows,
        service_wire,
    )
    assert raised is None, f"Creating the section's line item raised {raised!r}."

    matching = pulse_line_items(ags_section.platform, ags_section, ags_contract.resource_id)
    assert len(matching) == 1, (
        f"The container holds {len(matching)} line items carrying "
        f"`{ags_contract.resource_id_member}` {ags_contract.resource_id!r} after one run: "
        f"{[item.get('id') for item in matching]}. The whole container was walked, so this is not "
        "a page boundary."
    )
    created = matching[0]
    assert created.get(ags_contract.label_member) == ags_contract.label, (
        f"The created line item is labelled {created.get(ags_contract.label_member)!r}. SPEC §3.4 "
        f"names the column {ags_contract.label!r}, and it is the string an instructor reads in "
        "their own gradebook."
    )
    assert created.get(ags_contract.score_maximum_member) == ags_contract.score_maximum, (
        f"The created line item is out of {created.get(ags_contract.score_maximum_member)!r} and "
        f"§3.4's default is {ags_contract.score_maximum}. This platform refuses a score whose "
        "maximum disagrees with the line item's (ADR 0051), so a column created out of anything "
        "else is one no participation score can ever be posted to."
    )


def test_a_second_run_never_creates_a_second_pulse_participation_line_item(
    ags_client: Any,
    ags_section: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Settled decision 7's own requirement, driven rather than reasoned about.

    "A second 'Pulse Participation' column can never appear." The second run is the
    one that matters and it is the harder case than it looks: **the client persists
    nothing** (settled decision 3 — the app role holds no `UPDATE` on
    `ags_line_item_url`, and E3-05 is the ticket that spends it), so the section
    still holds no stored id on run two and the container walk is the only thing
    standing between one column and two.

    **The mutation this kills:** a find-or-create that creates unconditionally, or
    one whose container match is written so that it only ever matches what a *stored*
    id pointed at. Both leave every other test in this group green — run one creates
    correctly under either.

    Two assertions, because they fail differently: exactly one line item carries the
    resource id, and exactly one `POST` was made to the container across both runs. A
    client that created a second and a client that created a second and deleted it
    are the same on the first count and different on the second, and only the second
    says the platform was never asked to make one.
    """
    for run in (1, 2):
        _answered, raised = drive(
            ags_client,
            ags_client.find_or_create_line_item,
            ags_section,
            committed_rows,
            service_wire,
        )
        assert raised is None, f"Run {run} of find-or-create raised {raised!r}."

    matching = pulse_line_items(ags_section.platform, ags_section, ags_contract.resource_id)
    assert len(matching) == 1, (
        f"After two runs the container holds {len(matching)} line items carrying "
        f"`{ags_contract.resource_id_member}` {ags_contract.resource_id!r}: "
        f"{[item.get('id') for item in matching]}. Since the client stores nothing on the section, "
        "the second run had to find the first run's line item in the container — and a duplicate "
        "here is a second gradebook column per section per posting run."
    )
    created = calls_to(service_wire, ags_section.container, "POST")
    assert len(created) == 1, (
        f"The client posted {len(created)} line items to the container across two runs. Even where "
        "a duplicate would be invisible in the container — a platform that deduplicated, or one "
        "that answered the same id twice — asking the platform to create a second column is the "
        "behaviour this criterion forbids."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — the scores address is composed from the id **as a URL**.
# ---------------------------------------------------------------------------


def test_the_scores_address_is_composed_from_the_line_item_id_as_a_url(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 2, on an id that carries a query — which every id this platform mints does.

    "The scores address is composed from the line item's id **as a URL**, not by
    string concatenation. Every id the mock mints carries a query string precisely so
    that `id + '/scores'` cannot be green-and-wrong."

    The line item's id is `…/lineitem?type_id=n`, so the naive concatenation produces
    `…/lineitem?type_id=n/scores`: a request to the **line item itself** carrying a
    nonsense query. It is well formed, it is answerable, and it posts no score
    anywhere.

    **The mutation this kills:** `f"{identifier}/scores"`, which is what an
    implementer writes from AGS 2.0's own worked examples, every one of which shows a
    bare path.

    **Both directions, and the second is what makes the first mean anything.** The
    composed address is required to have been posted to *and* to have recorded a
    score; the naive address is required never to have been dialled, and is then
    driven by hand with a working credential and required to be refused — so "the
    client did not call it" is a statement about the client rather than about a URL
    that would have worked either way.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    scores_url = section.platform.scores_url(created)
    naive = f"{identifier.rstrip('/')}/scores"
    assert naive != scores_url, (
        f"Concatenating `/scores` onto {identifier!r} produces the same URL as inserting it "
        f"({naive!r}), so this line item id carries no query and the naive assembly cannot be wrong "
        "here. E0-28 item 3 mints an id that makes the two differ; without one this test asserts "
        "nothing."
    )

    grade = ags_contract.grade(section.subjects[0])
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )
    assert raised is None, f"Posting the score raised {raised!r}."

    posted = calls_to(service_wire, scores_url, "POST")
    assert posted, (
        f"The client posted no score to {scores_url!r}. It called "
        f"{[f'{call.method} {call.url}' for call in service_wire.calls]}. AGS 2.0 derives the Score "
        "service from the line item's own id by inserting a path segment before the query, which "
        "is what `urlsplit`/`urlunsplit` do and what string concatenation does not."
    )
    assert ags_contract.scores_posted(section.platform, identifier), (
        f"The client posted to {scores_url!r} and the platform recorded no score against "
        f"{identifier!r}. A request to the right URL that lands nothing is a passback that reads as "
        "having worked from the client's side alone."
    )
    assert not [call for call in service_wire.calls if call.url == naive], (
        f"The client posted to the naively concatenated {naive!r}. That URL addresses the line item "
        "itself with the query `type_id=n/scores`, so it is well formed, answerable and posts no "
        "score — the failure mode this criterion exists for, and one no assertion about a 2xx can "
        "see."
    )

    refused = section.platform.ags_post(
        naive,
        {"userId": grade.user_id, "timestamp": grade.timestamp},
        "application/vnd.ims.lis.v1.score+json",
        scope=ags_contract.score_scope,
    )
    assert 400 <= refused.status_code < 500, (
        f"Posting a score by hand to the naively concatenated {naive!r}, with a working "
        f"score-scope credential, answered {refused.status_code}. If that URL works then the "
        "assertion above is satisfied by a client that composes either way, and the criterion "
        f"cannot be posed against this platform at all. Body begins {refused.text[:300]!r}."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — the score string and the ledger arrive byte for byte.
# ---------------------------------------------------------------------------


def test_the_two_score_spellings_this_suite_drives_differ_after_a_float_round_trip(
    ags_contract: Any,
) -> None:
    """The premise the parametrisation below rests on, checked against `json` itself.

    The byte-exact test is driven over two spellings of one quantity, and the whole
    value of the pair is that **one of them survives a float round trip and the other
    does not**. `61.5` decodes and re-renders as `61.5`, so against it a client that
    parsed the caller's string into a float and re-serialised it is byte-identical to
    one that carried the string — the mutation is a no-op and the test cannot see it,
    which is `docs/MISTAKES.md` entry 30's shape arriving through a fixture value
    rather than through a fixture. `61.50` decodes to the same float and re-renders as
    `61.5`, so the same client is caught.

    Both are RFC 8259 numbers, so neither is a malformed body the platform would
    refuse for an unrelated reason.

    If a later change made both rows float-stable, the parametrisation would be two
    copies of one case and the mutation battery would find the survivor again. This is
    the assertion that says so first, by name.

    **A red here means these tests are broken, not the client.**
    """
    assert json.dumps(json.loads(A_FLOAT_STABLE_SCORE)) == A_FLOAT_STABLE_SCORE, (
        f"{A_FLOAT_STABLE_SCORE!r} does not survive a JSON round trip unchanged, so the row this "
        "suite drives as the ordinary case is not the ordinary case."
    )
    assert json.dumps(json.loads(A_FLOAT_UNSTABLE_SCORE)) != A_FLOAT_UNSTABLE_SCORE, (
        f"{A_FLOAT_UNSTABLE_SCORE!r} survives a JSON round trip unchanged, so a client that parsed "
        "the caller's string and re-serialised it would send exactly these bytes and the "
        "byte-exact test would be green against the very mutation the pair exists to catch."
    )
    assert json.loads(A_FLOAT_STABLE_SCORE) == json.loads(A_FLOAT_UNSTABLE_SCORE), (
        f"{A_FLOAT_STABLE_SCORE!r} and {A_FLOAT_UNSTABLE_SCORE!r} denote different numbers, so the "
        "pair differs in more than its spelling and a failure could not be attributed to the "
        "spelling."
    )
    assert ags_contract.a_score == A_FLOAT_STABLE_SCORE, (
        f"This module drives {A_FLOAT_STABLE_SCORE!r} as the ordinary spelling and "
        f"`tests/fixtures/ags_client.py` hands every other test {ags_contract.a_score!r}. The two "
        "are one value written twice — the parametrisation needs its copy at collection time — so a "
        "divergence means the comment above them has stopped being true and one half of this "
        "suite is measuring a number the other half never sends (`docs/MISTAKES.md` entry 1)."
    )


@pytest.mark.parametrize("score", BYTE_EXACT_SCORES)
def test_the_score_string_and_the_ledger_arrive_at_the_platform_byte_for_byte(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    score: str,
) -> None:
    """Criterion 3, asserted by comparing what was handed with what arrived.

    "The posted score carries the AGS comment member, holding the ledger string it
    was handed, byte-exact. The client does not compose, reformat, truncate or
    re-wrap it — the string that arrives at the platform is the string the caller
    supplied, asserted by comparing the two rather than by inspecting either alone."
    The same rule holds the percentage, and for ADR 0052's reason: a value the poster
    re-derives is not provably the value it is retrying.

    **The two comparisons fail differently, and both are needed.**

      - The **ledger** is a JSON string, so the round trip through the platform's
        decoder is lossless and `GET /mock/posted-scores` gives back exactly what was
        sent. Equality against the string this test handed over is therefore already
        byte-exact, newlines included.
      - The **score** is a JSON number, and `json.loads` is where its spelling is
        lost: the platform stores the body it decoded, so the stored value can no
        longer say whether `61.5` or `61.50` was on the wire. What the stored value
        *can* say is which number arrived, so it is compared against the caller's
        string put through the same one decode — which catches `0.615`, `62` and
        every other re-derivation. The **bytes** are then read off the request as it
        left the client, and that is the byte-exact half.

    **Two spellings of one quantity, and that is what the mutation battery cost.**
    Driven over `61.5` alone this test survived a client that parsed the caller's
    string into a float and re-serialised it — `str(float("61.5"))` is `"61.5"`, so
    the mutation was a no-op and the wire assertion could not see it. That is
    `docs/MISTAKES.md` entry 30's shape arriving through a *fixture value*: the
    fixture supplied a number that made the property under test unobservable. `61.50`
    is the same quantity spelled so that the round trip changes it, so the same
    client is red on the second row. The premise is checked by
    `test_the_two_score_spellings_this_suite_drives_differ_after_a_float_round_trip`,
    so a later change that made both rows float-stable is a red naming the pair
    rather than a mutation surviving again.

    **The mutations these kill:** a comment composed from the score rather than
    carried; a ledger joined with commas, truncated to its first line, or re-wrapped;
    a percentage re-derived from the completed and total counts; a score parsed to a
    float and re-serialised, or run through a formatter that pads or rounds.

    Nothing is compared against a literal in this file. The strings come from the
    caller's own value object, which is also what was handed to the client
    (`docs/MISTAKES.md` entry 19); the two spellings are parametrised because a
    parametrisation needs its values at collection time and a fixture cannot supply
    them there.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    grade = ags_contract.grade(section.subjects[0], score=score)
    assert "\n" in grade.ledger and grade.ledger.count("\n") >= 2, (
        f"The ledger this test hands over is {grade.ledger!r}, which is one line — so a carriage "
        "that took the first line, joined with a comma or re-wrapped would be invisible and this "
        "test would assert nothing about faithfulness."
    )

    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )
    assert raised is None, f"Posting the score raised {raised!r}."

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert len(stored) == 1, (
        f"The platform recorded {len(stored)} scores against {identifier!r} after one post: "
        f"{stored!r}. Criterion 3 compares one body with one set of strings."
    )
    arrived = stored[0]

    assert arrived.get(ags_contract.comment_member) == grade.ledger, (
        f"The caller handed the client the ledger {grade.ledger!r} and the platform received "
        f"{arrived.get(ags_contract.comment_member)!r} in the AGS `{ags_contract.comment_member}` "
        "member. SPEC §3.4 puts the per-week ledger there and this ticket's job is to carry it — "
        "since v1 ships no view of the participation score, that comment is the only place the "
        "arithmetic behind a posted percentage is visible to anyone."
    )
    assert arrived.get(ags_contract.given_member) == json.loads(grade.score), (
        f"The caller handed the client the score string {grade.score!r} and the platform received "
        f"{arrived.get(ags_contract.given_member)!r}. The comparison is against the caller's own "
        "string put through the one decode the platform cannot avoid — never against a number this "
        "test worked out — so it catches a value re-derived from the completed and total counts "
        "while staying true of both spellings. ADR 0052 rests the retry identity on the value "
        "being the one that was handed over: a value the poster re-derives is not provably the "
        "value it is retrying."
    )
    assert arrived.get(ags_contract.timestamp_member) == grade.timestamp, (
        f"The caller handed the timestamp {grade.timestamp!r} and the platform received "
        f"{arrived.get(ags_contract.timestamp_member)!r}. The timestamp names the recomputation "
        "rather than the attempt (ADR 0052), so a client that stamped its own clock makes every "
        "retry a new score — and a client that re-rendered `+00:00` as `Z` has changed the bytes "
        "of the thing this platform records verbatim."
    )

    posted = calls_to(service_wire, section.platform.scores_url(created), "POST")
    assert posted, "The client made no `POST` to the scores address, so there is no body to read."
    body = posted[-1].body
    text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    assert re.search(
        rf'"{ags_contract.given_member}"\s*:\s*{re.escape(grade.score)}(?![0-9])', text
    ), (
        f"The request body the client sent carries no `{ags_contract.given_member}` written as "
        f"{grade.score!r} — the body is {text[:400]!r}. This is the byte-exact half, and the "
        f"{A_FLOAT_UNSTABLE_SCORE!r} row is the one that can see it: both spellings decode to one "
        "float, so the stored value cannot tell them apart and only what went on the wire can. The "
        "trailing lookahead is part of the assertion — a client that padded "
        f"{A_FLOAT_STABLE_SCORE!r} to {A_FLOAT_UNSTABLE_SCORE!r} must not match either."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the line item's own maximum, and the equal-timestamp retry.
# ---------------------------------------------------------------------------


def test_the_post_carries_the_line_items_own_maximum_and_a_disagreeing_one_is_refused(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 4's first half, over a line item that is not out of 100.

    ADR 0051: "post against the line item's own maximum, and never rely on a platform
    to scale". This platform refuses a `scoreMaximum` that differs from the line
    item's rather than rescaling, so a client that sent a constant is refused
    outright — which is what makes "reads the maximum" and "assumes 100" two
    observable behaviours instead of one.

    **The mutation this kills:** `"scoreMaximum": 100` written into the post, which is
    right for every line item this client creates and wrong for every line item it
    finds. §3.4's default is 100 and a default is not a guarantee: an instructor can
    change a column's points in every LMS in the sector.

    **What this deliberately does not assert**, and it is a boundary rather than a
    gap (`docs/MISTAKES.md` entry 14): whether `scoreGiven` is rescaled when the
    maximum is not 100. ADR 0051 settles the maximum and settles nothing about the
    value, so pinning one here would be this test deciding it. Only the maximum sent
    is compared, and it is compared against the platform's own line-item document
    rather than against the number this file seeded with.

    **The pair is inside the test.** A post carrying 100 against the same line item is
    driven by hand and required to be refused 422, so "the client sent 50" is a
    statement about the client rather than about a platform that would have taken
    either.
    """
    section = ags_sections()
    created = section.platform.create_line_item(
        section.context.launches[0],
        resourceId=ags_contract.resource_id,
        scoreMaximum=A_DIFFERENT_MAXIMUM,
    )
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    held = section.platform.ags_get(identifier, scope=ags_contract.line_item_readonly_scope).json()
    maximum = held.get(ags_contract.score_maximum_member)
    assert maximum != ags_contract.score_maximum, (
        f"The line item this test seeded is out of {maximum!r}, which is §3.4's own default — so a "
        "client that assumed the default would be right here and the mutation this test exists for "
        "would be invisible."
    )

    grade = ags_contract.grade(section.subjects[0])
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )
    assert raised is None, (
        f"Posting against a line item out of {maximum!r} raised {raised!r}. ADR 0051 has the tool "
        "read the line item and post out of its maximum; a column an instructor re-pointed is an "
        "ordinary state, not a fault."
    )

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert stored, (
        f"The platform recorded no score against {identifier!r}, so either nothing was posted or "
        "the post was refused — and this platform refuses exactly the mismatch this test is about."
    )
    assert stored[-1].get(ags_contract.maximum_sent_member) == maximum, (
        f"The client sent `{ags_contract.maximum_sent_member}` "
        f"{stored[-1].get(ags_contract.maximum_sent_member)!r} and the line item is out of "
        f"{maximum!r}, read back from the platform's own document. ADR 0051 refuses the mismatch "
        "rather than rescaling, so a client holding a constant here stops posting for every "
        "section whose column was re-pointed."
    )

    mismatched = section.platform.post_score(
        created,
        {
            ags_contract.user_member: section.subjects[0],
            ags_contract.timestamp_member: ags_contract.a_later_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: 10,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert mismatched.status_code == 422, (
        f"Posting `{ags_contract.maximum_sent_member}` {ags_contract.score_maximum} against a line "
        f"item out of {maximum!r} answered {mismatched.status_code} rather than 422. ADR 0051 is "
        "the record that this platform refuses rather than rescales, and without that refusal the "
        "assertion above is satisfied by a client that sends whatever it likes. Body begins "
        f"{mismatched.text[:300]!r}."
    )


def test_a_repeat_at_an_equal_timestamp_is_accepted_as_a_retry_rather_than_doubled(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 4's second half, asserted against the platform's own log.

    ADR 0052: a score whose timestamp equals the one held is **accepted** — "a
    passback that times out on the network re-sends an identical body, timestamp
    included, and a platform answering 409 to that has told the tool its retry failed
    while the score is sitting in the log". The tool's side of that is the whole
    subject here: the client treats a 2xx as posted, and the identical body is
    identical.

    **The mutations this kills.** A client that stamps its own clock on each attempt,
    which makes the retry a *new* score and defeats ADR 0052's identity entirely —
    invisible to a status check, since a later timestamp is also accepted. And a
    client that treats the second call as an error because it already posted.

    **Two entries, not one**, and the count is the assertion: ADR 0052's own
    consequence is that "a repeat at one instant lands twice in the log… that is the
    record doing its job: it is what shows a retry happened". A store that collapsed
    them would have thrown away the one thing E3's retry handling needs to prove, and
    a client whose second attempt never reached the platform is indistinguishable
    from one whose attempt was collapsed unless the entries are counted.

    The two bodies are compared with each other as well as counted, because "two
    entries" is satisfied by two *different* scores at one instant.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    grade = ags_contract.grade(section.subjects[0])
    for attempt in (1, 2):
        _answered, raised = drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=created,
            grade=grade,
        )
        assert raised is None, (
            f"Attempt {attempt} raised {raised!r}. ADR 0052 makes an identical repeat at an equal "
            "timestamp an accepted retry, so a client that met a refusal here has not met this "
            "platform's behaviour."
        )

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert len(stored) == 2, (
        f"Two identical posts left {len(stored)} entries in the platform's log: {stored!r}. ADR "
        "0052 accepts an equal timestamp and appends, and the sequence is the only evidence that a "
        "repost happened at all."
    )
    assert stored[0] == stored[1], (
        f"The two posts differ: {stored[0]!r} then {stored[1]!r}. A retry is the *identical* body "
        "re-sent — same value, same ledger, same timestamp — and a client that re-derived any of "
        "the three has sent a second score rather than repeated the first."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — a 409 stops the post and triggers a re-read.
# ---------------------------------------------------------------------------


def test_a_conflict_stops_the_post_and_triggers_a_re_read_carrying_what_the_platform_holds(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 5, with the 409 planted rather than reasoned about.

    Settled decision 6: "On 409 the client stops and re-reads. No re-post: a 409 from
    a score post makes the client read the line item's Result for that user and raise
    a typed error carrying what the platform holds (ADR 0052: 409 means 'the platform
    holds something newer; stop retrying')."

    **The 409 is planted by giving the platform something newer**, which is the real
    cause rather than a canned status: a score for the same user at a later timestamp
    is posted directly, and the client's post is then strictly earlier — exactly the
    out-of-order passback AGS's 409 exists for.

    **Three assertions, and each kills a different implementation.**

      - **One POST to the scores address, not two.** A client with an ordinary retry
        loop posts again and is refused again, forever; a 409 is the one 4xx that
        says retrying cannot work.
      - **A read of the Result after it.** Stopping silently and stopping after
        finding out what the platform holds are different behaviours, and only the
        second gives the caller anything to act on.
      - **A typed error carrying the held value.** Typed, so a caller can branch on
        it — an error defined in the client's own module rather than whatever the
        transport raised — and carrying the value, so "the platform holds something
        newer" is a fact rather than a guess.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    subject = section.subjects[0]
    planted = section.platform.post_score(
        created,
        {
            ags_contract.user_member: subject,
            ags_contract.timestamp_member: ags_contract.a_later_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: ags_contract.a_newer_score,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert planted.status_code == 200, (
        f"Planting the newer score answered {planted.status_code}, so the platform holds nothing "
        f"newer and the client's post below would simply be accepted. Body begins "
        f"{planted.text[:300]!r}."
    )

    grade = ags_contract.grade(subject, timestamp=ags_contract.a_timestamp)
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )

    scores_url = section.platform.scores_url(created)
    posts = calls_to(service_wire, scores_url, "POST")
    assert len(posts) == 1, (
        f"The client posted to {scores_url!r} {len(posts)} times after a 409. ADR 0052: a 409 means "
        "the platform holds something newer and there is no point retrying, so a second attempt is "
        "a loop that can only ever be refused — and against a platform under load it is a loop "
        "against every section at once."
    )

    results_path = urlsplit(section.platform.results_url(created)).path
    reads = [
        call
        for call in service_wire.calls
        if call.method.upper() == "GET" and call.path.startswith(results_path)
    ]
    assert reads, (
        f"The client made no `GET` under {results_path!r} after the 409. It called "
        f"{[f'{call.method} {call.url}' for call in service_wire.calls]}. Settled decision 6 has "
        "the client read the line item's Result for that user, which is the difference between "
        "stopping and stopping *knowing what the platform holds*."
    )

    assert raised is not None, (
        "The platform answered 409 and the client returned normally. Settled decision 6 raises a "
        "typed error, because a caller that cannot tell a posted score from a refused one will "
        "record a `grade_sync` row saying a grade was sent."
    )
    assert type(raised).__module__ == ags_contract.module, (
        f"The client raised {type(raised).__module__}.{type(raised).__name__}, which is not defined "
        f"in `{ags_contract.module}`. 'A typed error' means one a caller can branch on: an "
        "`HTTPError` out of the transport, or a bare `Exception`, is indistinguishable from every "
        "other failure the post can have."
    )
    carried = "\n".join(
        [
            str(raised),
            repr(getattr(raised, "args", ())),
            repr(vars(raised) if hasattr(raised, "__dict__") else {}),
        ]
    )
    assert str(ags_contract.a_newer_score) in carried, (
        f"The error the client raised carries {carried!r}, which does not mention the "
        f"{ags_contract.a_newer_score!r} the platform holds for that user. The re-read is there so "
        "the error can say what is on the platform; an error that made the read and dropped the "
        "answer has spent a request for nothing."
    )

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert len(stored) == 1, (
        f"The platform's log holds {len(stored)} scores against {identifier!r}: {stored!r}. Only "
        "the planted one should be there — a refused post that was recorded anyway would mean the "
        "409 came from somewhere other than the staleness rule."
    )


def test_the_conflict_error_carries_the_held_result_on_an_attribute_and_not_in_its_message(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """The security round's LOW on the conflict path: where the held Result is allowed to live.

    Settled decision 6 has the client "raise a typed error carrying what the platform
    holds", and the test above requires exactly that. What it does not say is *where*
    — and the difference is the whole finding. An error's `str()` is the thing every
    logger prints: a caller that writes `logger.exception(...)`, or a task runner that
    renders an unhandled exception, puts the message into a log stream without ever
    deciding to. An **attribute** is read only by a caller that asked for it.

    The held Result is one student's grade: it carries the platform's `userId`, the
    score the platform holds, and — where the earlier post set one — the comment. So
    the message may name none of them, and the attribute must carry them.

    **The mutation this kills:** the held document interpolated into the error's
    message — `f"the platform holds {result!r}"`, which is the obvious way to satisfy
    "carrying what the platform holds" and which the test above accepts, because that
    one looks for the value across the message *and* the attributes. This is the half
    that says which of the two it may be.

    **Both directions, and the second is what stops the fix being deletion.** The
    forbidden state is asserted over `str(raised)`; the control is that the held
    document is still reachable on the error, which is what the caller needs and what
    a client that simply stopped carrying it would fail. Read off the attributes
    (`vars`) rather than off the message, so a build that satisfies the control by
    putting it back in the message fails the forbidden half in the same run.

    **Four values, and the subject is the sharpest.** The posted score and the ledger
    are the caller's own and the client is holding them while it raises; the
    platform's held score and the student's subject come back from the re-read. A
    message that named any of them is a per-student statement in a log stream.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    subject = section.subjects[0]
    planted = section.platform.post_score(
        created,
        {
            ags_contract.user_member: subject,
            ags_contract.timestamp_member: ags_contract.a_later_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: ags_contract.a_newer_score,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert planted.status_code == 200, (
        f"Planting the newer score answered {planted.status_code}, so there is no 409 and no error "
        f"for this test to read. Body begins {planted.text[:300]!r}."
    )

    grade = ags_contract.grade(subject, timestamp=ags_contract.a_timestamp)
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )
    assert raised is not None, (
        "The platform answered 409 and the client returned normally, so there is no error to read. "
        "`test_a_conflict_stops_the_post_and_triggers_a_re_read_carrying_what_the_platform_holds` "
        "is where that is the subject."
    )

    # The control, read off the attributes only: the held Result is still reachable by
    # a caller that asks. A build that satisfied this from the message would fail the
    # forbidden half below in the same run, which is what makes the pair a pair.
    attributes = repr(vars(raised) if hasattr(raised, "__dict__") else {})
    assert str(ags_contract.a_newer_score) in attributes, (
        f"The error the client raised carries {attributes!r} on its attributes, which does not "
        f"mention the {ags_contract.a_newer_score!r} the platform holds for that student. The "
        "re-read is spent so a caller can find out what is on the platform; moving that out of the "
        "message is only correct if it lands on an attribute, and an error that dropped it has "
        "spent a request for nothing."
    )

    message = str(raised)
    for what, value in (
        ("the student's LMS subject", subject),
        ("the score the platform holds", str(ags_contract.a_newer_score)),
        ("the score the caller handed over", grade.score),
        ("a ledger line", grade.ledger.splitlines()[0]),
    ):
        assert value not in message, (
            f"The conflict error's message carries {what} ({value!r}): {message!r}. An error's "
            "`str()` is what every logger prints — a caller writing `logger.exception(...)`, or a "
            "task runner rendering an unhandled exception — so a message naming a student and the "
            "grade held for them is a per-student disclosure nobody decided to make. The held "
            "Result belongs on an attribute a caller inspects deliberately, and the message "
            "belongs to the section and the line item."
        )


def test_the_re_read_after_a_conflict_is_recorded_against_an_address_carrying_no_student(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
) -> None:
    """The one call in this client that puts a student's `sub` in a URL, and the row it leaves.

    Settled decision 6 sends the client to the Result container **for that user**
    after a 409, and AGS's own way of asking for one student's result is the
    `user_id` query parameter — so the address the client dials carries the
    student's LMS subject in a query string. Settled decision 5 keeps the call log
    to `url`, `response_code`, `called_at` and `section_id`, with "no score, no
    ledger, no user id in the row — and none in any log line either", and §6.1 puts
    that log on an operator's console. Those two sentences meet on exactly this
    call: the request is legitimately filtered and the record of it may not be.

    **This is `docs/MISTAKES.md` entry 2's shape and it is why the test exists.** The
    client is written to record the re-read against the *unfiltered* results address,
    and until now nothing asserted it — a confidentiality rule holding on an untested
    path, which is a convention rather than a guarantee. Re-introduce the defect and
    the suite stays green.

    **The mutation this kills:** the re-read's `ags_call` row handed the **dialled**
    URL, filter and all — one line, the obvious one, and every other test in this
    module stays green under it. What ships is one row per section per conflict with
    a student's LMS subject in a column an operator reads by section, on a table
    nothing purges until E13.

    **The near miss it is written around:** no `ags_call` row written for the re-read
    at all. That satisfies "no subject in any row" completely and by emptiness, and
    it breaks criterion 8's grain — the re-read is an HTTP call the tool made to a
    platform service, so it is a row. Both halves are asserted: the row is required
    to be *there*, against the unfiltered results path, and the row count is required
    to match the calls the client actually made.

    **The control direction, and it is what makes the absence mean anything.** The
    wire is required to have seen the subject *in the dialled URL* — so this test can
    tell "the row was sanitised" from "the re-read never happened", which are the same
    picture from the database side alone (`docs/MISTAKES.md` entry 3).

    **Born green**, on a tree where the client already does this. Its worth is the
    mutation it names, not the colour it starts at.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    subject = section.subjects[0]
    assert len(subject) >= 8, (
        f"The launched subject is {subject!r}, which is short enough that finding it absent from a "
        "URL says little — a two-character `sub` could be absent by coincidence and present by "
        "accident. E0-14 seeds UUID subjects; a seed that changed that makes this assertion weak "
        "rather than wrong, and it is said here rather than passing quietly."
    )

    planted = section.platform.post_score(
        created,
        {
            ags_contract.user_member: subject,
            ags_contract.timestamp_member: ags_contract.a_later_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: ags_contract.a_newer_score,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert planted.status_code == 200, (
        f"Planting the newer score answered {planted.status_code}, so there is nothing newer on the "
        f"platform, no 409, and no re-read for this test to be about. Body begins "
        f"{planted.text[:300]!r}."
    )

    grade = ags_contract.grade(subject, timestamp=ags_contract.a_timestamp)
    drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=grade,
    )

    # The control: the re-read genuinely happened, and it happened as a filtered
    # request. Without this the two assertions below hold of a client that never
    # re-read at all — the same picture from the database side.
    results_path = urlsplit(section.platform.results_url(created)).path
    filtered = [
        call
        for call in service_wire.calls
        if call.method.upper() == "GET"
        and call.path.startswith(results_path)
        and subject in call.url
    ]
    assert filtered, (
        f"No request the client dialled under {results_path!r} carries the subject {subject!r}. It "
        f"called {[f'{call.method} {call.url}' for call in service_wire.calls]}. Settled decision 6 "
        "reads the line item's Result **for that user** after a 409, and AGS's way of asking for "
        f"one student is the `{RESULT_USER_FILTER}` filter — so with no filtered call on the wire "
        "there is no address for the log to have sanitised, and the absences below would be "
        "absences of something that never existed."
    )

    recorded = ags_rows.calls_for(section.id)
    assert recorded, (
        f"The client wrote no `{ags_contract.call_table}` row for this section at all, so every "
        "absence below is an absence in an empty table."
    )

    # The near miss: a row for the re-read must exist, against the *unfiltered*
    # results address. "No subject in any row" is satisfied completely by a writer
    # that skipped this call, and that breaks criterion 8's grain instead.
    for_the_read = [
        row
        for row in recorded
        if urlsplit(str(row.get(ags_contract.call_url_column))).path == results_path
    ]
    assert for_the_read, (
        f"No `{ags_contract.call_table}` row is recorded against the results address "
        f"{results_path!r}; the section's rows are "
        f"{[row.get(ags_contract.call_url_column) for row in recorded]}. The re-read is an HTTP "
        "call the tool made to a platform service, so SPEC §6.1's grain makes it a row — and a "
        "writer that skipped it to keep the subject out of the log has bought the privacy rule by "
        "losing the record of the call that failed."
    )

    made = ags_calls(service_wire, section.platform)
    assert len(recorded) == len(made), (
        f"The client made {len(made)} AGS call(s) — {[f'{c.method} {c.url}' for c in made]} — and "
        f"wrote {len(recorded)} row(s). One row per HTTP call still holds on the conflict path: a "
        "count short here is the re-read recorded nowhere, which is the near miss the assertion "
        "above is written around."
    )

    # The forbidden state, over every row rather than the one this test expects to be
    # the re-read's: a writer that sanitised the address it *meant* to and passed the
    # dialled one somewhere else is the same disclosure.
    for row in recorded:
        url = str(row.get(ags_contract.call_url_column) or "")
        assert subject not in url, (
            f"An `{ags_contract.call_table}` row carries the student's LMS subject {subject!r} in "
            f"its `{ags_contract.call_url_column}`: {row!r}. Settled decision 5 keeps this log to "
            "the URL, the status, the instant and the section, and §6.1's console reads it per "
            "section — a subject here is a per-student record of a failed grade post, on a table "
            "nothing purges until E13, reached by whoever is looking at the section."
        )
        assert RESULT_USER_FILTER not in parse_qs(urlsplit(url).query), (
            f"An `{ags_contract.call_table}` row carries a `{RESULT_USER_FILTER}` filter in its "
            f"`{ags_contract.call_url_column}`: {row!r}. That parameter's value is a student, so "
            "the row is about one person whether or not this test's own subject is the one in it — "
            "asserted as the forbidden *shape* as well as the forbidden value, because the next "
            "conflict is a different student."
        )


# ---------------------------------------------------------------------------
# Criterion 8 — one `ags_call` row per HTTP call, successes and failures, and no
# score in any of them.
# ---------------------------------------------------------------------------


def test_every_http_call_the_client_makes_leaves_an_ags_call_row_carrying_its_status(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 8's successful half, at the grain SPEC §6.1 gives the log.

    "Each at the grain of one HTTP call the tool made to a platform service" — the
    same grain `nrps_call` keeps, where a paged sync writes one row per page. The
    count is the assertion: a client that wrote one row per *run* would leave an
    operator unable to tell a section whose line item took three requests from one
    that took one, and the row is also what §6.1's console reads per section.

    **The mutation this kills:** a call record written once, outside the loop — or
    written only on failure, which is the shape that looks like frugality and leaves
    a working passback invisible on the console.

    The response code is asserted present and correct, because ADR 0129 gives a NULL
    `response_code` exactly one meaning — a call that never reached the platform — so
    a 200 recorded as NULL is a working client that reads as a transport failure.

    Token requests are deliberately **not** rows: a client-credentials grant is how a
    call is authorised rather than a call to a platform service, which is the roster's
    rule unchanged. `ags_calls` is what draws that line, and the count below is over
    the calls it returns.
    """
    section = ags_sections()
    answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, f"Finding or creating the line item raised {raised!r}."

    grade = ags_contract.grade(section.subjects[0])
    _posted, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=answered,
        grade=grade,
    )
    assert raised is None, f"Posting the score raised {raised!r}."

    made = ags_calls(service_wire, section.platform)
    recorded = ags_rows.calls_for(section.id)
    assert made, "The client made no service call at all, so this test would count two zeroes."
    assert len(recorded) == len(made), (
        f"The client made {len(made)} AGS call(s) — {[f'{c.method} {c.url}' for c in made]} — and "
        f"wrote {len(recorded)} `{ags_contract.call_table}` row(s): {recorded!r}. SPEC §6.1 puts "
        "the log at the grain of one HTTP call, which is what lets a console show a section whose "
        "line item took three requests as three calls rather than as one."
    )
    for row in recorded:
        assert row.get(ags_contract.call_url_column), (
            f"An `{ags_contract.call_table}` row carries no `{ags_contract.call_url_column}`: "
            f"{row!r}. The URL is what tells an operator which service was called."
        )
        assert row.get(ags_contract.call_response_code_column) is not None, (
            f"A successful call was recorded with a NULL "
            f"`{ags_contract.call_response_code_column}`: {row!r}. ADR 0129 gives NULL exactly one "
            "meaning — the call never reached the platform — so a working client reads on §6.1's "
            "console as one whose network is down."
        )
        assert row.get(ags_contract.call_called_at_column) is not None, (
            f"An `{ags_contract.call_table}` row carries no `{ags_contract.call_called_at_column}`: "
            f"{row!r}. Without it the log has no order and 'the last call this section made' cannot "
            "be asked."
        )


def test_a_refused_token_and_a_transport_failure_each_leave_their_own_ags_call_row(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 8's failing half, over the two failures that look alike on a console.

    Settled decision 5: "One row per HTTP call, successes and failures,
    token-endpoint refusals recorded with the token endpoint's status against the AGS
    url". And ADR 0129 fixes what a NULL `response_code` means: the call never
    reached the platform.

    **Two failures, and telling them apart is the whole value of the row.** A refused
    *token* means this deployment's credentials are being rejected and the platform is
    up; a *transport* failure means nothing was sent at all. A client that recorded
    neither leaves the section looking never-synced (SPEC §7.3's other state
    entirely); one that recorded both the same way leaves an operator with no idea
    which to act on.

    **The mutations this kills:** the `ags_call` write skipped on the failure paths,
    which is the natural shape of a writer that records what a response said; and the
    answered status discarded, so a refusal is written as NULL and reads as a network
    that is down.

    **The pair is the run in between.** After each failure the endpoint is restored
    and the same section is driven again, so every assertion here is about a client
    that does work rather than one that never works.
    """
    section = ags_sections()
    grant = token_endpoint(section.platform)

    service_wire.failing(grant, 500)
    _answered, _raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    refused = ags_rows.calls_for(section.id)
    assert refused, (
        f"The token endpoint answered 500 and the client wrote no `{ags_contract.call_table}` row "
        "at all. With no row, a section whose tool is refused a token every hour is "
        "indistinguishable from a section that has never been posted to."
    )
    assert [row for row in refused if row.get(ags_contract.call_response_code_column) == 500], (
        f"The token endpoint answered 500 and the section's rows are {refused!r}. The status the "
        "tool met is what tells an operator the credentials were refused rather than the gradebook "
        "service — and a NULL here means a call that never reached the platform, which is a "
        "different fault with a different repair."
    )
    assert all(
        str(row.get(ags_contract.call_url_column)) != grant
        for row in refused
        if row.get(ags_contract.call_response_code_column) == 500
    ), (
        f"A refusal was recorded against the token endpoint {grant!r}: {refused!r}. §6.1's console "
        "reads this log per section, and a row carrying the platform's OAuth surface is a row about "
        "something a reader looking at one section's gradebook history is not asking about. The "
        "roster's own rule is the same one."
    )

    service_wire.recovering(grant)
    before = len(ags_rows.calls_for(section.id))
    _answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, (
        f"With the token endpoint answering again, the same section raised {raised!r}. Without "
        "this half every assertion above holds of a client that never works."
    )
    assert (
        len(ags_rows.calls_for(section.id)) > before
    ), "The recovered run wrote no new row, so the log stops the moment a failure is recorded."

    service_wire.failing_the_transport(str(section.container))
    # By primary key rather than by position: a `SELECT` with no `ORDER BY` may
    # return the rows in any order, so slicing the list would name whichever rows the
    # planner happened to put last and this assertion would pass or fail on the
    # shape of the table (`docs/MISTAKES.md` entry 3).
    already = {row.get("id") for row in ags_rows.calls_for(section.id)}
    _answered, _raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    written = [row for row in ags_rows.calls_for(section.id) if row.get("id") not in already]
    assert written, (
        f"The transport refused the connection and the client wrote no new "
        f"`{ags_contract.call_table}` row. A call that never left the machine is exactly the state "
        "ADR 0129 reserves a NULL `response_code` for, and a writer that records only what a "
        "*response* said can never write one."
    )
    assert any(row.get(ags_contract.call_response_code_column) is None for row in written), (
        f"The transport failed and every new row carries a status: {written!r}. ADR 0129 gives NULL "
        "exactly one meaning — the call never reached the platform — so a transport failure "
        "recorded with a code invents an answer nobody gave."
    )


def test_no_ags_call_row_carries_a_score_a_ledger_line_or_an_lms_user_id(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
) -> None:
    """Criterion 8's forbidden state, asserted over the values rather than the columns.

    "`ags_call` rows are written for successes and for failures, and carry no score
    value." Settled decision 5 widens that to what the row may hold at all: `url`,
    `response_code`, `called_at`, `section_id` — "no score, no ledger, no user id in
    the row".

    **Asserted over the values, not over the column names** (`docs/MISTAKES.md` entry
    2: prefer asserting the forbidden state). A column called `detail` or `note`
    holding the posted percentage passes any check made against a list of names, and
    that is the shape a well-meaning "record why it failed" change takes. So every
    value of every row for this section is searched for the three strings the client
    was actually handed.

    **The guard first.** The rows are required to be non-empty and the score post is
    required to have happened, because a table with nothing in it satisfies every
    absence assertion below and would report a client that writes nothing as one that
    writes safely (`docs/MISTAKES.md` entry 3).
    """
    section = ags_sections()
    answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, f"Finding or creating the line item raised {raised!r}."

    grade = ags_contract.grade(section.subjects[0])
    _posted, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=answered,
        grade=grade,
    )
    assert raised is None, f"Posting the score raised {raised!r}."

    recorded = ags_rows.calls_for(section.id)
    assert recorded, (
        f"The client wrote no `{ags_contract.call_table}` row for this section, so every absence "
        "below is an absence in an empty table."
    )
    forbidden = {
        "the score the caller handed over": grade.score,
        "a ledger line": grade.ledger.splitlines()[0],
        "the LMS user id": grade.user_id,
    }
    for row in recorded:
        rendered = " ".join(str(value) for value in row.values())
        for what, value in forbidden.items():
            assert value not in rendered, (
                f"An `{ags_contract.call_table}` row carries {what} ({value!r}): {row!r}. Settled "
                "decision 5 keeps this log to the URL, the status, the instant and the section — a "
                "call log that grew a value column is a per-student record of standing on a table "
                "§6.1 puts on an operator's console."
            )


# ---------------------------------------------------------------------------
# Settled decision 3 — every platform-chosen URL is judged before it is dialled.
# ---------------------------------------------------------------------------


def test_a_loopback_container_address_is_refused_before_it_is_dialled(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving: Any,
) -> None:
    """The stored gradebook address goes through the same rules the roster's does.

    E3-02 put `lms_ags_line_items_url` in `FETCHED_COLUMNS` and in
    `LOOPBACK_REFUSED_COLUMNS`, and `tests/unit/test_registration_address_
    constraints.py` pins the membership. **This is the test that says the tuple is
    consulted**: a membership assertion on its own is satisfied by a tuple nobody
    reads (`docs/MISTAKES.md` entry 9).

    A launch claim naming `http://127.0.0.1:9/lineitems` is a platform pointing this
    container at whatever is running beside it, and the client would dial it on a
    schedule with the tool's Bearer token attached and nobody watching.

    **The mutation this kills:** `refuse_invalid_fetched_address` never called on the
    container address — which every other test in this module stays green under,
    because they all store an address that would pass.

    **"Nothing was dialled" does not kill that mutation, and the battery proved it.**
    A second, independent control stands behind the judgment: the client mounts a
    pinned-resolution transport that fails closed on a host it never pinned, so with
    the judgment call removed the request is still not made — it is refused one layer
    lower, by the transport, and every assertion about what reached `127.0.0.1` holds
    either way. That is `docs/MISTAKES.md` entry 3 in its most expensive form: a
    security test that is green because *something* refused, without saying what.

    **So the observable difference is pinned instead: what the raise was caused by.**
    An address-judgment refusal raises the client's own error from
    `RegistrationAddressError`; a transport refusal raises it from
    `requests.ConnectionError`. `__cause__` is the one place those two paths differ,
    and with the judgment removed this assertion is the thing that goes red. It also
    pins the half an operator reads: a section that stops posting because its
    platform advertised a refused address needs a different repair from one whose
    network is down, and the two are indistinguishable from the call log alone.

    **What is deliberately not pinned** is the wording of the refusal's message. It is
    settled — it says the address "is one this container refuses to fetch" — and a
    later rewording should not redden a security test, so the cause type carries the
    assertion and the sentence carries the operator (`docs/MISTAKES.md` entry 14: the
    boundary is named rather than claimed away).

    **Under a deployment's `ENVIRONMENT`, and it has to be.** ADR 0081 switches every
    one of these rules off where the environment is exactly the development name, so
    a refusal test in development would pass against a validator that refuses
    nothing. The platform is reached over `https` for the same reason the roster's
    refusal suite reaches it that way: rule 1 refuses cleartext that leaves this
    machine, so an `http` platform would be refused before the loopback rule was
    reached and the refusal would be about the wrong rule.

    **The pair is inside the test.** The same section, the same platform, the same
    environment — with the advertised address put back, the client reaches the
    gradebook. Without that half, every assertion here holds of a client that refuses
    every address there is.
    """
    section = ags_sections(roster_contract.https_platform_issuer, container=LOOPBACK_CONTAINER)
    resolver = resolving({section.host: (roster_contract.a_global_address,)})

    _answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
        settings=deployment_settings,
        resolve=resolver,
    )

    refused_by_the_judgment(raised, LOOPBACK_CONTAINER, ags_contract, "the section's stored")

    dialled = [call for call in service_wire.calls if call.host == "127.0.0.1"]
    assert not dialled, (
        f"The client dialled {[call.url for call in dialled]}, which the section's stored "
        "gradebook address named. That request carries the tool's own Bearer token and reaches "
        "whatever is listening beside this container, and whatever answers is parsed as a line-item "
        "container."
    )
    recorded = ags_rows.calls_for(section.id)
    assert recorded, (
        f"The address was refused and no `{ags_contract.call_table}` row records it. §6.1's console "
        "is where an operator learns that a platform is advertising an address this tool will not "
        "fetch; with no row the section reads as one nothing has ever tried to post to."
    )
    assert not [
        row for row in recorded if row.get(ags_contract.call_response_code_column) == 200
    ], (
        f"A row records a 200 against a call that was never made: {recorded!r}. Nothing answered, "
        "so either the refusal was recorded as a success or the address was fetched after all."
    )

    restored = ags_sections.repoint(section, section.advertised)
    _answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        restored,
        committed_rows,
        service_wire,
        settings=deployment_settings,
        resolve=resolver,
    )
    assert raised is None, (
        f"With the platform's own advertised container address stored, the same section under the "
        f"same deployment raised {raised!r}. The refusal above would then hold of a client that "
        "refuses every address, which is a client that never posts a grade."
    )
    assert calls_to(service_wire, section.advertised), (
        f"The client made no request to the advertised container {section.advertised!r} once it was "
        "stored, so the accepted half of this pair is about nothing and the refusal above says "
        "only that the client is inert."
    )


def test_a_loopback_line_item_id_the_platform_answered_with_is_refused_before_it_is_dialled(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_rows: Any,
    ags_contract: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving: Any,
) -> None:
    """The rule defeated one level out: the address the *platform* chose at run time.

    Settled decision 3 judges "the one stored on the section AND one the platform just
    answered with, before the client GETs or POSTs to it". The stored address is the
    test above; this is the half a stored column cannot pose, and it is the same
    shape as E1-11's F1 — a roster walk that judged the stored address and then
    followed whatever the platform's `Link` header named.

    A container is served here holding a line item whose `id` is loopback. It carries
    the settled `resourceId`, so a client matching correctly will select it and then
    address it — the container read is legitimate and the id is not, which is
    precisely the case a check on the stored address alone walks past.

    **The mutation this kills:** the fetched-address rules applied to
    `section.lms_ags_line_items_url` and to nothing else. Every other test here stays
    green, because every other line-item id comes from the mock and is on the mock's
    own host.

    **And "nothing was dialled" does not kill it**, which the mutation battery
    measured. The client mounts a pinned-resolution transport that fails closed on a
    host it never pinned, so with the judgment on the answered id removed the request
    is still not made — the transport refuses one layer lower, and every assertion
    about what reached `127.0.0.1` holds either way. The two layers are told apart by
    what the raise was **caused by**: `RegistrationAddressError` for a judgment
    refusal, `requests.ConnectionError` for a transport one. `refused_by_the_judgment`
    asserts both directions of that, and it is what goes red when the judgment is
    deleted; the sentence the refusal carries is deliberately left unpinned, for the
    reason the test above gives.

    **The row is asserted against the section's stored address, not against the
    hostile id.** §6.1's console is read per section, and a row keyed to the value the
    platform supplied puts an attacker's string on an operator's screen and detaches
    the record from the section's own gradebook — the same finding E1-11's F1-4
    closed one service over.
    """
    section = ags_sections(roster_contract.https_platform_issuer)
    resolver = resolving({section.host: (roster_contract.a_global_address,)})
    service_wire.answering(
        str(section.container),
        [ags_contract.line_item_document(LOOPBACK_LINE_ITEM)],
        content_type=ags_contract.container_media_type,
    )

    _answered, raised = drive(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
        settings=deployment_settings,
        resolve=resolver,
    )

    refused_by_the_judgment(raised, LOOPBACK_LINE_ITEM, ags_contract, "the platform's answered")

    dialled = [call for call in service_wire.calls if call.host == "127.0.0.1"]
    assert not dialled, (
        f"The client dialled {[call.url for call in dialled]} because a line item in the container "
        f"gave that as its `{ags_contract.line_item_id_member}`. The address the platform chooses "
        "at run time is fetched with the tool's Bearer token exactly as the stored one is, and "
        "judging only the stored one is the rule defeated one level out."
    )
    recorded = ags_rows.calls_for(section.id)
    assert recorded, (
        f"No `{ags_contract.call_table}` row records the refused line-item address: the section has "
        f"{recorded!r}. A refusal is a call the tool decided not to make, and it is the thing an "
        "operator needs to see."
    )
    assert not [
        row for row in recorded if str(row.get(ags_contract.call_url_column)) == LOOPBACK_LINE_ITEM
    ], (
        f"A row carries the hostile line-item id {LOOPBACK_LINE_ITEM!r} in its "
        f"`{ags_contract.call_url_column}` column: {recorded!r}. The refusal is recorded against "
        f"the section's own stored address ({section.container!r}); a row keyed to the value the "
        "platform supplied hands the console a string an attacker chose."
    )


# ---------------------------------------------------------------------------
# Criterion 9 — the `PlatformProfile` seam is consulted, executed both ways.
# ---------------------------------------------------------------------------


def test_the_platform_profile_decides_the_progress_members_that_reach_the_platform(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 9, executed rather than cited (`docs/MISTAKES.md` entry 9).

    "A `PlatformProfile` exists as a seam with one profile behind it, and a test
    proves the seam is actually consulted rather than being a file the code never
    reads." Settled decision 9 makes the profile carry the conformant defaults the
    client consults on **every** score post — `activity_progress` "Completed" and
    `grading_progress` "FullyGraded" — resolved by registration issuer.

    **Both directions, in one test, which is what "executed" means here.** The
    default profile posts the conformant pair; a profile substituted for this
    platform's issuer posts the substituted pair, and the change is read off *what
    arrived at the platform* rather than off the profile object. A test that only
    asserted the defaults would be green against a client with the two strings
    written into its post body, which is exactly the file-nobody-reads this criterion
    is about.

    **The substitution replaces the resolver wherever the client looks it up.** A
    client that did `from app.lti.platforms import <resolver>` holds a name in its own
    module and one that did `from app.lti import platforms` reads through the
    package, so both bindings are replaced — this fixture does not know which import
    style the implementer chose, and settling that would be the test deciding.

    **The substituted values are inside AGS 2.0's own vocabularies**, so a red here is
    the seam not being consulted rather than the platform refusing a word it does not
    know.

    The two posts are at different timestamps, so the second is accepted as a later
    score rather than colliding with the first (ADR 0052 refuses only a strictly
    earlier one), and so the two bodies can be told apart in the log.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)
    subject = section.subjects[0]

    default = ags_contract.grade(subject, timestamp=ags_contract.a_timestamp)
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=default,
    )
    assert raised is None, f"The post under the default profile raised {raised!r}."

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert stored, "Nothing reached the platform under the default profile."
    conformant = stored[-1]
    assert conformant.get(ags_contract.activity_member) == ags_contract.conformant_activity, (
        f"The score posted under the default profile carries `{ags_contract.activity_member}` "
        f"{conformant.get(ags_contract.activity_member)!r} rather than "
        f"{ags_contract.conformant_activity!r}. Settled decision 9 fixes the conformant defaults, "
        "and a value outside AGS's five is one Canvas answers 422 to."
    )
    assert conformant.get(ags_contract.grading_member) == ags_contract.conformant_grading, (
        f"The score posted under the default profile carries `{ags_contract.grading_member}` "
        f"{conformant.get(ags_contract.grading_member)!r} rather than "
        f"{ags_contract.conformant_grading!r}."
    )

    issuer = (section.platform.discovery() or {}).get("issuer")
    assert isinstance(issuer, str) and issuer, (
        "The platform's discovery document states no `issuer`, so there is no key to resolve a "
        "profile by and the substitution below would be for nobody."
    )
    module, name, _resolver = ags_client.profile_resolver()
    substitute = ags_client.substituted_profile(issuer)
    assert getattr(substitute, ags_contract.activity_attribute) != ags_contract.conformant_activity
    monkeypatch.setattr(module, name, lambda *_args, **_kwargs: substitute)
    if hasattr(ags_client.module, name):
        monkeypatch.setattr(ags_client.module, name, lambda *_args, **_kwargs: substitute)

    later = ags_contract.grade(subject, timestamp=ags_contract.a_later_timestamp)
    _answered, raised = drive(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        grade=later,
    )
    assert raised is None, f"The post under the substituted profile raised {raised!r}."

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert len(stored) >= 2, (
        f"Only {len(stored)} score(s) reached the platform, so the substituted post never arrived "
        f"and the seam cannot be read off it: {stored!r}."
    )
    substituted = stored[-1]
    assert substituted.get(ags_contract.timestamp_member) == later.timestamp, (
        f"The last score the platform holds is stamped "
        f"{substituted.get(ags_contract.timestamp_member)!r} rather than {later.timestamp!r}, so "
        "this assertion is reading the first post again."
    )
    assert substituted.get(ags_contract.activity_member) == ags_contract.substituted_activity, (
        f"With a profile substituted for {issuer!r}, the score that reached the platform still "
        f"carries `{ags_contract.activity_member}` "
        f"{substituted.get(ags_contract.activity_member)!r}. The seam is a file the client never "
        "reads: the values are written into the post body, and changing the profile changes "
        "nothing that leaves this process."
    )
    assert substituted.get(ags_contract.grading_member) == ags_contract.substituted_grading, (
        f"With a profile substituted for {issuer!r}, the score still carries "
        f"`{ags_contract.grading_member}` {substituted.get(ags_contract.grading_member)!r} rather "
        f"than {ags_contract.substituted_grading!r}."
    )


# ---------------------------------------------------------------------------
# Criterion 10 — nothing this code logs carries a score, a ledger or a user id.
# ---------------------------------------------------------------------------


def test_nothing_the_client_logs_carries_a_score_a_ledger_line_or_an_lms_user_id(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterion 10, over what the code logs while it both succeeds and fails.

    "No log line emitted by this code contains a score, a ledger line, or an LMS user
    id, asserted by a test over what the code logs rather than by reading it." SPEC
    §4.1's confidentiality model is about read paths, and this is the same value
    arriving somewhere nobody reviews: a worker's log stream, kept longer than any
    table and read by whoever is on call.

    **Both a success and a failure, because they log different things.** The line a
    failing post writes is where the body it was trying to send ends up — "posting
    %r failed" is the natural sentence and it carries the score, the ledger and the
    student's `sub` in one go. The failure here is a refused token, which is the one
    an operator will actually meet.

    **The whole record is searched, not `record.msg`.** `getMessage()` renders the
    format arguments in, which is where a value hides from a check made against the
    template alone — `logger.info("posted %s", score)` has a template with no score
    in it. The arguments and any formatted exception text are folded in as well.

    **The guard first.** Something must have been logged, or the absence below is an
    absence in an empty capture and would report a silent client as a safe one
    (`docs/MISTAKES.md` entry 3). This is the one assertion here that is about
    *presence*, and it is what makes the rest mean anything.
    """
    section = ags_sections()
    grade = ags_contract.grade(section.subjects[0])

    with caplog.at_level(logging.DEBUG):
        answered, raised = drive(
            ags_client,
            ags_client.find_or_create_line_item,
            section,
            committed_rows,
            service_wire,
        )
        assert raised is None, f"Finding or creating the line item raised {raised!r}."
        _posted, raised = drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=answered,
            grade=grade,
        )
        assert raised is None, f"Posting the score raised {raised!r}."

        service_wire.failing(token_endpoint(section.platform), 500)
        drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=answered,
            grade=grade,
        )

    from_client = [
        record for record in caplog.records if str(record.name).startswith(ags_contract.module)
    ]
    assert from_client, (
        f"No log record came from a logger named `{ags_contract.module}` across a successful "
        "find-or-create, a successful post and a post whose token was refused. Two things look "
        f"like this and they are different: the client logs nothing at all — which SPEC §6.1's "
        "'AGS call logs' does not ask for but a silent failing passback is worse than a loud one — "
        "or it logs under a logger this suite is not looking for, which is a name to settle in the "
        "pull request rather than something to guess at here. Loggers that did record something: "
        f"{sorted({record.name for record in caplog.records})}."
    )
    # The forbidden values are searched over the **whole** capture rather than over
    # the client's own records. A value that reached a log stream reached it whoever
    # emitted it, and a filter is exactly how "we do not log that" survives the line
    # that hands it to somebody who does (`docs/MISTAKES.md` entry 2: assert the
    # forbidden state). The presence guard above is what keeps this from being an
    # absence in an empty capture.
    text = ags_contract.logged_text(caplog.records)
    for what, value in (
        ("the score the caller handed over", grade.score),
        ("a ledger line", grade.ledger.splitlines()[0]),
        ("the LMS user id", grade.user_id),
    ):
        assert value not in text, (
            f"A log record emitted while the client ran carries {what} ({value!r}). What was "
            f"logged was:\n{text[:2000]}\n\nA worker's log stream is read by whoever is on call and "
            "kept longer than any table in this system; a participation figure against an LMS user "
            "id there is a statement about a named person's standing, outside every read path §4.1 "
            "governs."
        )


def test_a_transport_failure_on_the_conflict_re_read_logs_no_student_subject(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterion 10 on the one branch where the client holds a URL with a student in it.

    The security round's MEDIUM, and it is a coverage finding rather than a new rule:
    the test above drives a success and a refused *token*, and neither reaches the
    branch where the leak lives. Every other address this client handles is a
    container, a line item or a scores endpoint — none of them names a person. The
    conflict re-read is the exception: settled decision 6 sends it to the Result
    container **for that user**, so the URL it dials carries `user_id=<sub>` in a
    query string, and that URL is what a transport failure hands back in the text of
    the exception it raises.

    **The mutation this kills: the transport-failure warning is handed the
    exception's text.** `logger.warning("re-reading the result failed: %s", failure)`
    is the natural sentence and the natural argument, and `requests` builds a
    `ConnectionError` whose message quotes the URL it could not reach — so the
    student's LMS subject reaches a log stream through a string nobody wrote it into.
    It is invisible to every other test in this module: the sanitised `ags_call` row
    is asserted next door and is a different surface, and the log test above never
    produces a transport failure at all.

    **The near miss: no warning emitted at all.** An absence of the subject is
    satisfied completely by a client that says nothing when a re-read fails, and that
    is a worse outcome than the leak for the operator SPEC §6.1 writes the call log
    for — a conflict whose re-read never landed, logged nowhere. So a warning is
    required to have been emitted, from the client's own logger, and the assertion
    below is over what it said rather than over whether it spoke.

    **The other control: the re-read was actually attempted.** The wire records a
    request before it refuses it, so the filtered `GET` is required to be on the wire
    carrying the subject — without that, "no subject in the log" holds of a run in
    which nothing was ever dialled with a subject in it (`docs/MISTAKES.md` entry 3),
    and the 409 might not even have fired.

    The whole capture is searched rather than the client's own records, for the reason
    the test above gives: a value that reached a log stream reached it whoever emitted
    it, and handing it to somebody else is exactly how "we do not log that" survives.
    """
    section = ags_sections()
    created = stored_line_item(section.platform, section.context)
    identifier = section.platform.line_item_id(created)
    section = ags_sections.store_line_item(section, identifier)

    subject = section.subjects[0]
    assert len(subject) >= 8, (
        f"The launched subject is {subject!r}, which is short enough that finding it absent from a "
        "log says little. E0-14 seeds UUID subjects; a seed that changed that makes this assertion "
        "weak rather than wrong, and it is said here rather than passing quietly."
    )

    planted = section.platform.post_score(
        created,
        {
            ags_contract.user_member: subject,
            ags_contract.timestamp_member: ags_contract.a_later_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: ags_contract.a_newer_score,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert planted.status_code == 200, (
        f"Planting the newer score answered {planted.status_code}, so there is no 409, no re-read "
        f"and no branch for this test to be about. Body begins {planted.text[:300]!r}."
    )

    # The 409 sends the client to the Result container for this student; the transport
    # then refuses that call, which is what puts the dialled URL inside an exception.
    # Keyed by host and path, so the filtered request is matched whatever query it
    # carries — which is also why the score post above is untouched.
    service_wire.failing_the_transport(section.platform.results_url(created))

    grade = ags_contract.grade(subject, timestamp=ags_contract.a_timestamp)
    with caplog.at_level(logging.DEBUG):
        drive(
            ags_client,
            ags_client.post_score,
            section,
            committed_rows,
            service_wire,
            line_item=created,
            grade=grade,
        )

    results_path = urlsplit(section.platform.results_url(created)).path
    attempted = [
        call
        for call in service_wire.calls
        if call.method.upper() == "GET"
        and call.path.startswith(results_path)
        and subject in call.url
    ]
    assert attempted, (
        f"No request under {results_path!r} carrying the subject {subject!r} reached the wire. It "
        f"called {[f'{call.method} {call.url}' for call in service_wire.calls]}. Either the 409 did "
        "not fire or the re-read was not attempted, and with no filtered URL dialled there is "
        "nothing for a log line to have leaked."
    )

    from_client = [
        record for record in caplog.records if str(record.name).startswith(ags_contract.module)
    ]
    warned = [record for record in from_client if record.levelno >= logging.WARNING]
    assert warned, (
        f"The re-read after a 409 failed at the transport and `{ags_contract.module}` logged "
        f"nothing at or above WARNING. It logged {[(r.name, r.levelname) for r in caplog.records]}. "
        "The absence asserted below is satisfied completely by a client that says nothing here, "
        "and a conflict whose re-read never landed is exactly the thing SPEC §6.1 wants legible — "
        "so the leak has to be ruled out on a line that was actually written."
    )

    text = ags_contract.logged_text(caplog.records)
    assert subject not in text, (
        f"A log record carries the student's LMS subject {subject!r}. What was logged was:\n"
        f"{text[:2000]}\n\nThe re-read is the one call this client makes whose URL names a person, "
        "and a transport failure quotes the URL it could not reach — so the subject arrives in a "
        "log stream through the text of an exception rather than through anything the client "
        "chose to write. Log the address without its query, or the failure's type and the section, "
        "and never the exception's own text on this branch."
    )
    for what, value in (
        ("the score the caller handed over", grade.score),
        ("a ledger line", grade.ledger.splitlines()[0]),
    ):
        assert value not in text, (
            f"A log record carries {what} ({value!r}) on the conflict path. What was logged "
            f"was:\n{text[:2000]}"
        )
