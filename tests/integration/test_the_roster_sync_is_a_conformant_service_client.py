"""The roster read is an authenticated service call — E1-11, criteria 1 and 2.

The exit clause this ticket exists for, quoted in its own context section: "a
roster read succeeds as an authenticated service call, not an unauthenticated
GET." The carried entry defines conformant — "a token requested with a tool-signed
assertion, attached to every service call, the way `pylti1p3`'s `ServiceConnector`
performs it" — and this module is that sequence asserted from the client's side of
the wire.

**Why the evidence is what the client *sent* rather than what it got back.** E1-06
ruled that the mock's Advantage services do not begin requiring a token — "a roster
read with no `Authorization` header still answers" (ADR 0084's consequences) — and
E1-11's boundary keeps the mock that way. So a 200 from the membership service says
nothing at all about whether a token was attached, and a test written on it would
pass against exactly the client this ticket exists to replace. Every assertion below
reads `service_wire`, which records each request as it left the client, and the
forbidden-state half turns the harness's own gate on: a wire that refuses an
unauthenticated read, so that a client with any such path left in it fails.

**The controls come first and they must be green.** The wire, the composed roster
and the two-platform arrangement are new machinery, and machinery whose only
evidence is that the tests using it went red proves nothing (`docs/MISTAKES.md`
entry 35). **A red in the control section means these tests are broken, not the
code.**
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `roster_sync`, `roster_platforms`, `service_wire`, `synced_section`,
# `compose_a_roster` and `roster_contract` come from `tests/fixtures/roster_sync.py`
# and are reached as fixtures rather than imported, for the reason every module in
# this suite gives: an import of a fixtures module by name depends on where pytest
# put `tests/` on `sys.path`, and an import error is not a red.

# RFC 6749 §4.4's grant and RFC 7523 §2.2's assertion profile, spelled as
# `test_mock_lms_client_credentials_grant.py` spells them. Specification constants.
CLIENT_CREDENTIALS_GRANT = "client_credentials"
JWT_BEARER_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# Two issuers, so that two platforms are two registrations rather than one row
# written twice — the same device `test_registration_endpoints_are_per_platform.py`
# uses, and `.invalid` is RFC 2606's.
FIRST_ISSUER = "http://roster-platform-one.invalid"
SECOND_ISSUER = "http://roster-platform-two.invalid"


def token_calls(wire: Any, host: str | None) -> list[Any]:
    """Every client-credentials grant the client posted to `host`."""
    return [
        call
        for call in wire.to_host(host)
        if call.method.upper() == "POST"
        and call.form.get("grant_type") == [CLIENT_CREDENTIALS_GRANT]
    ]


def roster_calls(wire: Any, section: Any) -> list[Any]:
    """Every request the client made to one section's stored roster address."""
    from urllib.parse import urlsplit

    path = urlsplit(section.address or "").path
    return [call for call in wire.to_host(section.host) if call.path == path]


def published_keys(tool: Any, contract: Any) -> list[dict[str, Any]]:
    """The tool's own key set, fetched from the route E1-06 publishes it at."""
    response = tool.get(contract.jwks_path)
    assert response.status_code == 200, (
        f"`GET {contract.jwks_path}` answered {response.status_code} rather than 200, so this test "
        "has no key set to verify the client assertion against. E1-06 adds that route and "
        "`tests/integration/test_the_tool_publishes_its_key_set.py` is where its absence is "
        f"diagnosed. Body begins {response.text[:200]!r}."
    )
    keys = response.json().get("keys")
    assert isinstance(keys, list) and keys, (
        f"The tool published {response.json()!r}, which carries no keys. D11 has this ticket sign "
        "its `client_assertion` with the same `tool_signing_key` row that route publishes."
    )
    return [key for key in keys if isinstance(key, dict)]


def verified_assertion(assertion: str, keys: list[dict[str, Any]], audience: str) -> dict[str, Any]:
    """The claims of `assertion`, verified against the tool's published key set.

    Verified rather than decoded, and that is the whole point of the test that
    calls it: an assertion nobody can verify is a formality, and the difference
    between the two is invisible to a client that only reads its own output.
    """
    import base64

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    def integer(value: str) -> int:
        padded = value + "=" * (-len(value) % 4)
        return int.from_bytes(base64.urlsafe_b64decode(padded), "big")

    failures: list[str] = []
    for key in keys:
        try:
            return dict(
                jwt.decode(
                    assertion,
                    rsa.RSAPublicNumbers(integer(key["e"]), integer(key["n"])).public_key(),
                    algorithms=["RS256"],
                    audience=audience,
                )
            )
        except Exception as failure:
            failures.append(f"{key.get('kid')}: {type(failure).__name__}: {failure}")
    pytest.fail(
        f"The `client_assertion` the sync signed verifies against none of the {len(keys)} keys the "
        f"tool publishes, for audience {audience!r}: {failures}. D11 has one construction path for "
        "inbound and outbound — the same `tool_signing_key` row the JWKS route serves — so an "
        "assertion signed with anything else is one this platform, and every real platform, "
        "refuses."
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the sync.**
# ---------------------------------------------------------------------------


def test_the_wire_carries_a_request_to_the_platform_and_refuses_an_unmounted_host(
    synced_section: Any, service_wire: Any
) -> None:
    """The transport under every assertion in this module, exercised both ways.

    A `requests.Session` that answered nothing would make every "the client called
    this" assertion below unfalsifiable and every "it did not call that" assertion
    trivially true. So it is required to *fetch* — the section's own stored roster
    address, through the real mock — and to *refuse* a host nothing mounted, which
    is what stands between "the sync resolved the wrong platform" and a silent
    pass (deferred E1-10 item 1's failure mode).

    **A red here means these tests are broken, not the sync.**
    """
    session = service_wire.session()

    answered = session.get(str(synced_section.address))
    assert answered.status_code == 200, (
        f"The wire answered {answered.status_code} for the section's own stored roster address "
        f"{synced_section.address!r}. Body begins {answered.text[:200]!r}."
    )
    assert isinstance(answered.json().get("members"), list), (
        f"The wire carried back {answered.text[:200]!r}, which is not an NRPS membership "
        "container. Every ingestion assertion in this suite rests on the mock's real container "
        "reaching the client through this transport."
    )
    assert service_wire.to_host(synced_section.host), (
        "The wire recorded no call to the platform's host, so its record is empty and every "
        "assertion in this module that reads it would be satisfied by a client that made no "
        "request at all."
    )

    with pytest.raises(Exception, match="no application is mounted"):
        session.get("http://a-platform-nobody-registered.invalid/memberships")


def test_the_wire_refuses_a_service_read_that_carries_no_bearer_token(
    synced_section: Any, service_wire: Any
) -> None:
    """The gate AC1's forbidden state is asserted with, proven able to fire.

    `refusing_unauthenticated_reads` is a harness gate rather than the platform's,
    because E1-06 ruled the mock's services do not require a token. A gate nobody
    has watched refuse anything is a comment (`docs/MISTAKES.md` entry 9), and the
    test that rests on it —
    `test_the_sync_has_no_unauthenticated_path_to_the_roster` — would then be green
    against a client that attaches nothing.

    Both directions, one request apart: the same URL with a bearer token and
    without one.

    **A red here means these tests are broken, not the sync.**
    """
    service_wire.refusing_unauthenticated_reads()
    session = service_wire.session()

    granted = session.get(
        str(synced_section.address), headers={"authorization": "Bearer a-token-shaped-string"}
    )
    assert granted.status_code == 200, (
        f"The wire refused a read carrying a bearer token with {granted.status_code}, so its gate "
        "refuses everything and the pair below would be about nothing."
    )

    refused = session.get(str(synced_section.address))
    assert refused.status_code == 401, (
        f"The wire answered {refused.status_code} for a read carrying no `Authorization` header "
        "while its unauthenticated gate was on. That gate is the only thing in this suite that "
        "refuses an unauthenticated roster read — the mock deliberately does not — so with it "
        "inert, AC1's forbidden state cannot be asserted at all."
    )


def test_the_roster_this_suite_composes_is_the_shape_the_mock_serves(
    synced_section: Any, roster_contract: Any, compose_a_roster: Any, a_subject: Any
) -> None:
    """The composed container is checked against the real one before anything reads it.

    The window, drop, re-add and email cases are not all expressible against a
    static seed, so the modules beside this one install a membership container this
    suite wrote. That is a licence to drift into a document no platform sends —
    the exact error ADR 0048 was written to prevent ("it teaches E1 the one wrong
    thing: that enrollment dates are core NRPS") — so the composed member's member
    names are compared against a member the mock actually serves, and the extension
    is required to be the namespaced key that record fixes.

    **A red here means these tests are broken, not the sync.**
    """
    served = synced_section.platform.membership_pages(str(synced_section.address))
    real = [member for page in served for member in page.members]
    assert real, (
        "The mock served no members at the section's own roster address, so there is nothing to "
        "compare a composed member against. `test_mock_lms_nrps_roster.py` diagnoses an empty "
        "roster."
    )

    composed = roster_contract.member(
        a_subject("control"),
        roles=[roster_contract.learner_role_urn],
        status=roster_contract.active,
        email="control@pulse-tests.invalid",
        window=roster_contract.window("2026-09-08T00:00:00-04:00", None),
    )
    required = {
        roster_contract.member_id,
        roster_contract.member_roles,
        roster_contract.member_status,
    }
    missing = sorted(required - set(composed))
    assert not missing, f"The composed member omits {missing}, which NRPS 2.0 makes a member's own."

    unknown = sorted(set(composed) - set().union(*(set(member) for member in real)))
    assert not unknown, (
        f"The composed member carries {unknown}, which no member the mock serves carries. Members "
        f"the mock serves carry {sorted(set().union(*(set(member) for member in real)))}. A "
        "composed roster that has drifted from the real document teaches this ticket a shape no "
        "platform sends, which is the error ADR 0048 exists to prevent."
    )
    assert roster_contract.extension in composed, (
        "The composed member carries no enrollment extension under "
        f"{roster_contract.extension!r}. ADR 0048 fixes that namespace, and a window carried "
        "anywhere else is a member this ticket must read as windowless."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — the token, the assertion, and the header every call carries.
# ---------------------------------------------------------------------------


def test_the_sync_reads_the_roster_with_a_token_it_requested_with_a_tool_signed_assertion(
    roster_sync: Any,
    roster_platforms: Any,
    synced_section: Any,
    service_wire: Any,
    roster_contract: Any,
    committed_rows: Any,
    roster_rows: Any,
) -> None:
    """Criterion 1, as the carried entry defines it, read off what the client sent.

    Four things have to be true at once and each is a separate mutation:

      - a **client-credentials grant** was posted to the token endpoint the
        section's own registration carries, asking for the NRPS scope. A client
        that skipped the grant and read the roster reaches a 200 from this mock,
        which is why this is asserted from the request record rather than from the
        answer.
      - its `client_assertion` **verifies against the tool's published key set**.
        Signed with any other key it is refused by every real platform, and by this
        one — ADR 0084 decision 4. A decode is not enough: a decoded assertion
        satisfies a client that signed with a key nobody published.
      - `iss` and `sub` are the **registered client id** and `aud` is the token
        endpoint (ADR 0084 decision 2), which is what stops the assertion being
        spendable at another endpoint of the same platform.
      - the roster request carried the token as a **`Bearer` credential**, and the
        token is one *this* platform issued — verified against the platform's own
        published key set rather than compared to a string, so a client that
        attached the assertion, a stale token, or the string "None" fails here.

    And the container was actually ingested: without that last assertion every one
    above is satisfied by a client that authenticates beautifully and writes
    nothing.
    """
    wire = service_wire
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=wire.session(),
    )
    committed_rows.commit()

    granted = token_calls(wire, synced_section.host)
    assert len(granted) == 1, (
        f"The sync posted {len(granted)} client-credentials grants to the platform "
        f"{synced_section.host!r}; the calls it made were {wire.to_host(synced_section.host)}. The "
        "carried entry's definition of done is 'a token requested with a tool-signed assertion, "
        "attached to every service call' — no grant at all is the unauthenticated GET this ticket "
        "exists to replace, and more than one per sync is a client re-minting a credential it "
        "already holds."
    )
    body = granted[0].form
    assert body.get("client_assertion_type") == [JWT_BEARER_ASSERTION_TYPE], (
        f"The grant carried `client_assertion_type` {body.get('client_assertion_type')!r}. RFC "
        "7523 §2.2 fixes that value, and a platform reads it before it reads the assertion."
    )
    assert roster_contract.membership_scope in " ".join(body.get("scope", [])).split(), (
        f"The grant asked for scope {body.get('scope')!r} and not "
        f"{roster_contract.membership_scope!r}. A token is granted for the exact scope string the "
        "NRPS claim names, and one granted for anything else is a token the service will refuse "
        "the moment E1-06's deferred enforcement lands."
    )

    assertion = (body.get("client_assertion") or [""])[0]
    assert assertion, "The grant carried no `client_assertion` at all."
    claims = verified_assertion(
        assertion,
        published_keys(roster_platforms.tool, roster_contract),
        str(granted[0].url),
    )
    client_id = synced_section.registration.client_id
    assert claims.get("iss") == client_id and claims.get("sub") == client_id, (
        f"The assertion claims `iss` {claims.get('iss')!r} and `sub` {claims.get('sub')!r}, and "
        f"this platform registered the tool as {client_id!r}. A `client_assertion` is the tool "
        "speaking about itself, and a platform resolves which registration it belongs to from "
        "exactly those two claims."
    )

    reads = roster_calls(wire, synced_section)
    assert reads, "The sync made no request to the section's stored roster address at all."
    for call in reads:
        token = call.bearer_token
        assert token, (
            f"A roster read carried `Authorization` {call.authorization!r}. The exit clause this "
            "ticket exists for is that the roster read is 'an authenticated service call, not an "
            "unauthenticated GET', and this mock answers either."
        )
        assert token.count(".") == 2 and synced_section.platform.verifies(token) is not None, (
            "The token the sync presented on the roster read is not one this platform issued: it "
            "verifies against none of the keys the platform publishes. ADR 0084 decision 5 makes "
            "the access token a compact JWS signed by the platform's issuer key, so a client "
            "presenting its own assertion, a token from another platform, or a token it invented "
            "fails here and nowhere else."
        )

    assert roster_rows.enrollments(), (
        "The sync completed the whole authenticated sequence and wrote no enrollment. Every "
        "assertion above is satisfied by a client that authenticates correctly and ingests "
        "nothing, which is why this one is here."
    )


def test_the_sync_has_no_unauthenticated_path_to_the_roster(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    roster_rows: Any,
) -> None:
    """Criterion 1's forbidden state, asserted as a refusal rather than as an absence.

    "A test proves the *unauthenticated* GET path no longer exists in the client
    (the forbidden state asserted)." A client can have two paths — the conformant
    one and a fallback that reaches the container without a token — and every
    assertion in the test above stays green while the fallback sits there unused.
    What finds it is a roster that refuses an unauthenticated read: with the header
    stripped on the way out, a client with a fallback still ingests and a
    conformant one does not.

    **The pair is the test above**, which drives the same section over a wire that
    strips nothing and requires the ingestion this one requires the absence of. A
    test that only asserted "nothing was written under refusal" would be satisfied
    by a sync that writes nothing ever.

    **What the sync does with the refusal is deliberately not asserted.** Whether
    it raises, retries or returns is the implementer's, and D9 settles only what is
    *recorded*: one `nrps_call` row per HTTP call, carrying the response code. So
    the refusal has to leave that record, and no enrollment.
    """
    service_wire.refusing_unauthenticated_reads()
    service_wire.stripping_the_authorization_header()

    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=synced_section.id,
            http=service_wire.session(),
        )
        committed_rows.commit()
    except Exception:
        committed_rows.session.rollback()

    assert not roster_rows.enrollments(), (
        "Every roster read was answered 401 and the sync wrote enrollments anyway, so the members "
        "came from somewhere that did not present the token — a second, unauthenticated path into "
        "the container. The carried entry's whole subject is that this path does not exist."
    )
    refused = [
        row for row in roster_rows.calls_for(synced_section.id) if row.get("response_code") == 401
    ]
    assert refused, (
        f"No `nrps_call` row records the refused read: the section's rows are "
        f"{[dict(row) for row in roster_rows.calls_for(synced_section.id)]}. SPEC §6.1 puts 'NRPS "
        "and AGS call logs with response codes' on the admin console, and a sync that reaches a "
        "service and records nothing leaves an operator reading a section that looks never-synced "
        "while the tool is being refused every hour."
    )


def test_the_client_asks_the_container_for_no_filter_the_platform_refuses(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_contract: Any,
    committed_rows: Any,
) -> None:
    """The roster is fetched at the address the claim advertised, with nothing added.

    E1-11's work order records the trap: "the mock's NRPS page size is 5 and the
    mock refuses `role`/`limit`/`rlid` filters with 400 — the client must not send
    them." A client that added one gets a 400 from this mock and an empty roster
    from a section, which reads as a small class rather than as a rejected request.

    **The mutation this kills**: a client that asks for `?role=Learner` to save
    itself the filtering, or for `?limit=100` to save itself the paging — both of
    which are legal NRPS and both of which this platform refuses.

    The requests are required to be non-empty first: a client that made no request
    at all sends no forbidden filter either (`docs/MISTAKES.md` entry 3).
    """
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    reads = roster_calls(service_wire, synced_section)
    assert reads, "The sync made no roster request, so this test would assert nothing about one."
    for call in reads:
        sent = sorted(set(call.query) & set(roster_contract.refused_filters))
        assert not sent, (
            f"The client asked for `{call.url}`, which carries {sent}. This platform answers 400 "
            "for those parameters, so the request is refused and the section syncs empty — which "
            "looks exactly like a small class."
        )


# ---------------------------------------------------------------------------
# Criterion 2 — the whole container, across every page.
# ---------------------------------------------------------------------------


def test_a_multipage_roster_ingests_the_member_only_the_last_page_holds(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
) -> None:
    """Criterion 2, against the member `docs/MISTAKES.md` entry 3 would let through.

    "A multi-page roster ingests completely; the page boundary is covered by a
    fixture that would catch off-by-one-page (first page alone satisfying the test
    is MISTAKES entry 3's shape — assert the member the *last* page holds)."

    The last page's member is learned from the platform rather than from the sync:
    the roster is walked here with E0-15's own driver, which follows `Link` headers
    and is the independent ground truth this assertion needs. A test that read the
    expected member out of what the sync wrote would agree with a client that
    stopped after page one.

    **The mutation this kills**: a client that reads the container's first page and
    never follows the `next` relation — which is what a first implementation does,
    because `NamesRolesProvisioningService.get_members()` and a single
    `make_service_request` differ by one method call and only one of them pages.

    The guards are load-bearing rather than ceremony: over a roster that fits on one
    page, "the last page's member was ingested" is satisfied by a client that reads
    one page, and the whole test says nothing.
    """
    pages = synced_section.platform.membership_pages(str(synced_section.address))
    assert len(pages) > 1, (
        f"The seeded roster for this section came back on {len(pages)} page(s), so there is no "
        "page boundary for a member to be lost at and this test cannot see the mutation it exists "
        "for. E0-15 seeds a roster larger than one page; "
        "`test_mock_lms_nrps_roster.py::test_a_roster_larger_than_one_page_advertises_the_next_"
        "page_in_a_link_header` is where a roster that stopped paging is diagnosed."
    )
    assert pages[-1].members, "The last page of the seeded roster carries no members."
    last = str(pages[-1].members[-1][roster_contract.member_id])
    first_page = {str(member[roster_contract.member_id]) for member in pages[0].members}
    assert last not in first_page, (
        f"The member this test looks for ({last!r}) is also on the first page, so a client that "
        "read one page would satisfy the assertion below and the boundary would go unasserted."
    )

    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    assert roster_rows.enrollments_for(last), (
        f"The roster's last page carries {last!r} and no enrollment was written for them. The "
        f"walk returned {len(pages)} pages carrying "
        f"{sum(len(page.members) for page in pages)} members between them; the sync wrote "
        f"{len(roster_rows.enrollments())} enrollments. A client that stops at the first page "
        "syncs a class with its later pages missing, and a short roster looks exactly like a small "
        "section."
    )


def test_every_page_of_a_roster_walk_leaves_a_call_record_carrying_its_response_code(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    roster_rows: Any,
) -> None:
    """SPEC §6.1's call log, at the grain D9 settles: one row per HTTP call.

    "One row per NRPS HTTP call (a paged sync writes one per page)." The count is
    the assertion: a sync that wrote one row per *sync* would leave an operator
    unable to tell a roster that took four requests from one that took one, and the
    row is also the never-synced discriminator and the debounce's memory, so its
    grain is load-bearing in three places.

    **The mutation this kills**: a call record written once, outside the paging
    loop. Every other test in this module stays green.

    The response code is asserted present, because §6.1 asks for "NRPS and AGS call
    logs with response codes" and D9 gives `response_code` NULL exactly one
    meaning — a transport failure — so a successful read that recorded none would
    read on the console as a call that never reached the platform.
    """
    pages = synced_section.platform.membership_pages(str(synced_section.address))
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    recorded = roster_rows.calls_for(synced_section.id)
    assert len(recorded) == len(pages), (
        f"The roster came back over {len(pages)} pages and the sync wrote {len(recorded)} "
        f"`nrps_call` row(s): {[dict(row) for row in recorded]}. D9 makes it one row per HTTP "
        "call — 'a paged sync writes one per page' — which is what lets the admin console show a "
        "section whose roster takes four requests as four calls rather than as one."
    )
    assert all(row.get("response_code") == 200 for row in recorded), (
        f"A successful roster walk left call rows {[dict(row) for row in recorded]}. D9 gives a "
        "NULL `response_code` exactly one meaning — the call never reached the platform — so a "
        "200 recorded as NULL is a working sync that reads as a transport failure on §6.1's "
        "console."
    )


def test_a_refused_token_is_recorded_against_the_roster_url_with_the_token_endpoints_status(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """The failure §6.1's console would otherwise read as the roster service refusing.

    A sync makes two calls to two endpoints, and only one of them is the roster.
    When the **token endpoint** answers an error, the roster is never asked at all —
    so a call log that recorded nothing leaves the section looking never-synced
    (SPEC §7.3's other state entirely), and one that recorded a row with no status
    leaves it looking like a transport failure, which D9 gives a NULL
    `response_code` as its single meaning. Neither says the thing an operator has
    to act on: this deployment's credentials were refused, and the platform is up.

    So the sync fetches its token eagerly and records what happened to it, against
    the roster's own URL, carrying the token endpoint's status. That is the only
    reason the eager fetch exists: `pylti1p3` gets a token per request by itself, so
    dropping it is invisible to every conformance assertion in this module.

    **The mutation this kills** — and it is the survivor a mutation battery found,
    which is why this test was written after the fact: removing the eager
    `ServiceConnector.get_access_token` before the walk, so the failure surfaces
    from inside `get_members()` with no row written; and its quieter sibling,
    keeping the fetch and discarding the status it came back with, so the row is
    written with `response_code` NULL and reads as a call that never reached the
    platform.

    **The pair is inside the test.** The same section, the same roster, the same
    wire — with the token endpoint restored, the sync ingests. Without that half,
    every assertion here is satisfied by a sync that never works at all.

    **What the sync does with the failure beyond recording it is deliberately not
    asserted.** ADR 0090's consequences leave that to the writer — "a later
    sanctioned writer running on a job rather than on a request may reasonably want
    the opposite: fail loudly, let the task retry — and this record does not decide
    that for it" — so a raise and a return are both permitted here and the one
    thing that is not is swallowing it in silence, which is what the row asserts.
    """
    token_url = (synced_section.platform.discovery() or {}).get("token_endpoint")
    assert isinstance(token_url, str) and token_url, (
        "The mock platform advertises no `token_endpoint`, so this test has no endpoint to fail "
        "and could not pose its question. `test_mock_lms_client_credentials_grant.py` is where "
        "that absence is diagnosed."
    )
    member = a_subject("after-the-token-recovers")
    service_wire.serve(compose_a_roster(synced_section, [roster_contract.member(member)]))
    service_wire.failing(token_url, 500)

    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=synced_section.id,
            http=service_wire.session(),
        )
        committed_rows.commit()
    except Exception:
        committed_rows.session.rollback()

    recorded = roster_rows.calls_for(synced_section.id)
    assert recorded, (
        "The token endpoint answered 500 and the sync wrote no `nrps_call` row at all. SPEC §6.1 "
        "puts 'NRPS and AGS call logs with response codes' on the admin console, and D9 makes "
        "`nrps_call` the discriminator between a section that has never been synced and one that "
        "has: with no row, a section whose tool is being refused a token every hour is "
        "indistinguishable from a section whose platform never gave out a roster address."
    )
    refused = [row for row in recorded if row.get("response_code") == 500]
    assert refused, (
        f"The token endpoint answered 500 and the section's call rows are "
        f"{[dict(row) for row in recorded]}. The status the tool met is what tells an operator "
        "that the credentials were refused rather than that the roster service was: a NULL "
        "`response_code` means a call that never reached the platform (D9), and this call reached "
        "it and was answered."
    )
    assert all(row.get("url") == synced_section.address for row in refused), (
        f"The refused call was recorded against {[row.get('url') for row in refused]} and this "
        f"section's roster lives at {synced_section.address!r}. The row is the section's record of "
        "an attempted sync, and §6.1's console reads it per section — a row carrying the token "
        "endpoint's URL is a row about the platform's OAuth surface, which is not what a reader "
        "looking at one section's roster history is asking about."
    )
    assert not roster_rows.enrollments(), (
        "The token endpoint answered 500 and enrollments were written anyway, so members reached "
        "the database over a call that was never authorised — which is the unauthenticated path "
        "`test_the_sync_has_no_unauthenticated_path_to_the_roster` is about, arriving here."
    )

    service_wire.recovering(token_url)
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    assert roster_rows.enrollments_for(member), (
        "With the token endpoint answering again, the same section and the same roster ingested "
        "nothing. So the assertions above hold of a sync that never works rather than of one that "
        "recorded a refusal — and the failing half of this test would be about nothing."
    )


# ---------------------------------------------------------------------------
# Deferred E1-10 item 1 — whose credentials this section's roster is fetched with.
# ---------------------------------------------------------------------------


def test_each_section_is_synced_with_the_credentials_of_its_own_registered_platform(
    roster_sync: Any,
    roster_platforms: Any,
    service_wire: Any,
    committed_rows: Any,
) -> None:
    """Deferred E1-10 item 1's done-when, and it cannot be posed with one platform.

    "**Done when** E1-11's client resolves its registration from the section's own
    `lti_deployment_id` and a test drives two registered platforms, each with a
    section, and asserts each sync presents the assertion of its own platform — a
    test that fails against a resolver that takes whichever registration it finds
    first."

    Two platforms are registered at once, each with a section bound to its own
    deployment and carrying its own roster address. Each section is synced, and
    each platform is required to have issued the token its own section's roster was
    read with.

    **Why it fails against a first-found resolver, in the two places it can be
    caught.** Such a resolver signs an assertion audienced at the *other*
    platform's token endpoint and posts it there, so the second platform's token
    endpoint sees no grant at all — the first assertion. And it then presents the
    first platform's token to the second platform's roster, which this mock answers
    happily, so the token on the wire verifies against the wrong key set — the
    second. Either one alone would be a test about a symptom; together they are
    the finding: "a sync that resolved the platform any other way could present one
    institution's token to another institution's roster service."

    The two platforms are asserted to be at different addresses first. Two mocks
    serving one host would make every routing assertion below true of a client
    that ignored the registration entirely (`docs/MISTAKES.md` entry 3), and the
    remedy is `MOCK_LMS_ISSUER`, which is what `roster_platforms` varies.
    """
    first = roster_platforms(FIRST_ISSUER)
    second = roster_platforms(SECOND_ISSUER)

    assert first.host and second.host and first.host != second.host, (
        f"The two platforms advertise their rosters at {first.address!r} and {second.address!r}, "
        "which share a host — so a client that fetched both from one platform could not be told "
        "from one that resolved each section's own. The two are started under different "
        "`MOCK_LMS_ISSUER` values, and a mock that composes its service URLs from something else "
        "is what this guard reports."
    )

    for section in (first, second):
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=section.id,
            http=service_wire.session(),
        )
    committed_rows.commit()

    for section, other in ((first, second), (second, first)):
        granted = token_calls(service_wire, section.host)
        assert len(granted) == 1, (
            f"The platform at {section.host!r} was asked for {len(granted)} tokens while its own "
            f"section was synced, and the platform at {other.host!r} was asked for "
            f"{len(token_calls(service_wire, other.host))}. A resolver that takes whichever "
            "registration it finds first asks one platform for both tokens, which is exactly this "
            "shape."
        )
        audience = str(granted[0].url)
        assert audience.startswith(f"http://{section.host}"), (
            f"A grant for this section was posted to {audience!r}, which is not this platform's "
            "own token endpoint. The registration a section resolves to through "
            "`section.lti_deployment_id` is what carries `auth_token_url`."
        )
        for call in roster_calls(service_wire, section):
            token = call.bearer_token or ""
            assert section.platform.verifies(token) is not None, (
                f"The roster at {call.url!r} was read with a token the platform at "
                f"{section.host!r} did not issue. That is one institution's credential presented "
                "to another institution's roster service — the failure deferred E1-10 item 1 "
                "names, arriving an epic after the binding that closed its launch-side twin."
            )
            assert other.platform.verifies(token) is None, (
                f"The token presented at {call.url!r} verifies against the *other* registered "
                "platform's key set. Whichever registration this sync resolved, it was not this "
                "section's."
            )


def test_the_scheduled_walk_syncs_a_section_under_each_registered_platform(
    roster_sync: Any,
    roster_platforms: Any,
    service_wire: Any,
    committed_rows: Any,
    roster_rows: Any,
) -> None:
    """The hourly job's own version of the same question, one level up.

    SPEC §7.3 gives the scheduled job one discovery rule — the stored address —
    and D10 has it walk every section that carries one. With two registrations in
    the table, a walk that resolved a platform once and reused it for the whole
    run produces exactly the failure above, and the per-section test next door
    cannot see it: that one calls the sync per section, so a resolver hoisted out
    of the loop is still called twice.

    **The mutation this kills**: a `sync_rosters` that builds one `ServiceConnector`
    before the loop.
    """
    first = roster_platforms(FIRST_ISSUER)
    second = roster_platforms(SECOND_ISSUER)

    roster_sync.call(
        roster_sync.sync_every_stored_address,
        session=committed_rows.session,
        http=service_wire.session(),
    )
    committed_rows.commit()

    for section in (first, second):
        assert roster_rows.calls_for(section.id), (
            f"The scheduled walk left no `nrps_call` row for the section at {section.address!r}, "
            "so it never reached that section's roster. SPEC §7.3: the stored address 'is what "
            "gives the scheduled job the discovery it otherwise lacks', and both sections carry "
            "one."
        )
        for call in roster_calls(service_wire, section):
            assert section.platform.verifies(call.bearer_token or "") is not None, (
                f"During the scheduled walk, the roster at {call.url!r} was read with a token the "
                "platform that serves it did not issue. A connector built once before the loop "
                "presents one platform's credentials to every section in the institution."
            )
