"""The posted value scales to the line item's maximum, and the reads ask for the writing scope — E3-08's boundary round, LO-H1 and LO-M1.

Two rulings from the boundary round, both about what the AGS client puts on the
wire, so they are asserted together against one platform.

**R1 (LO-H1) — the score scales.** `scoreGiven = percentage / 100 x scoreMaximum`,
posted beside that same `scoreMaximum`. `grade_sync.score_text` stays the
canonical percentage string, so the comparison E3-06 makes and the ledger §3.4
puts in the comment are unchanged; only the wire body scales. A maximum that is
missing, zero, negative **or not finite** means the section is walked past with a
logged refusal (ADR 0135's no-address shape) — never a divide, and never a post.
The last of those is E3-08's security round: `nan` and `inf` are not nonpositive,
so a guard written `maximum <= 0` lets both through.

**Why this was a HIGH and not a rounding detail.** Every line item *this tool
creates* is out of 100, so the identity holds and nothing is visibly wrong. The
line items it *finds* are another matter: an instructor can re-point a column's
points in every LMS in the sector, and ADR 0051 already has the client read the
maximum and send it. Sending the right maximum beside an unscaled value posts
`61.5` into a column out of 50 — a grade of 123%, or whatever the platform makes
of it, for every student in that section. `test_the_ags_client_is_a_conformant_
service_client.py` asserted the maximum and said in as many words that it did
**not** assert the value, because ADR 0051 settled the first and left the second
open. R1 closes it, and that module's paragraph is corrected to point here.

**R2 (LO-M1) — the line-item reads ask for `lineitem`, not `lineitem.readonly`.**
The tool must hold the writing scope anyway to create a column, so a read that
asks for the read-only sibling buys no privilege reduction and costs a second
token: a platform granting scopes per request hands the tool two credentials
where one would do, and a platform that grants only what was asked leaves the
client holding a token it cannot create with. Result reads keep
`result.readonly` — production never calls them, so they gate nothing.

**Asserted on the observable, not on a constant.** What this module reads is the
`scope` the platform's own token endpoint was *asked for* when the client
performed a line-item read. Nothing here imports `app.lti.ags`, so the assertion
survives a constant being renamed and fails when the request changes — which is
the direction that matters.

**The scope comparison is membership of a space-delimited list, never a
substring.** `…/scope/lineitem.readonly` has `…/scope/lineitem` as a prefix, so
`required in granted` answers yes for the wrong one. That is the same superstring
trap `tests/integration/test_mock_lms_ags_requires_a_token.py` is written around
on the platform's side, and this module keeps the premise honest with a control.

**Which failure a red here is.** All four tests are expected **RED** before the
round's fixes: the two scaling tests on the value that reached the platform, and
the scope test on the string in the grant. Each drives the client through
`AgsClient.call`, which fails naming any parameter it cannot fill, so an interface
that moved is a FAILED naming it rather than an ERROR.
"""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_client`, `ags_sections` and `ags_contract` come from
# `tests/fixtures/ags_client.py`; `service_wire` from
# `tests/fixtures/roster_sync.py`; `committed_rows` from the shared fixtures. All
# are reached as fixtures rather than imported, for the reason every module in
# this suite gives.

# The maximum this module seeds a found line item with. **Fifty, and the value is
# the instrument**: `A_SCORE_STRING` is `61.5`, so the scaled body is
# `61.5 / 100 x 50 = 30.75` — a number with two decimal places that no
# implementation reaches by accident, that differs from the unscaled `61.5`, and
# that is not the maximum, not the percentage, and not half of anything round.
A_FOUND_MAXIMUM = 50

# **Hand-computed from R1's rule, not from the client.** `A_SCORE_STRING` is the
# canonical percentage string `"61.5"` (`tests/fixtures/ags_client.py`), and
# R1 settles `scoreGiven = percentage / 100 x scoreMaximum`:
#
#     61.5 / 100 = 0.615
#     0.615 x 50 = 30.75
#
# Written out rather than computed here, so this file holds an expectation a
# person derived rather than a second copy of the arithmetic under test
# (`docs/MISTAKES.md` entry 19).
THE_SCALED_VALUE = 30.75

# What the same grade posts against a line item out of 100, which is the identity
# case: 61.5 / 100 x 100 = 61.5. Named so the two tests below can say what the
# other one expects, and so a reader can see that the mutation "send the
# percentage unscaled" is right in one of these worlds and wrong in the other.
THE_UNSCALED_VALUE = 61.5

# The three maxima R1 refuses. Zero is the divide; negative is a column that
# cannot be scored into at all; `None` is a platform that served a line item with
# no maximum, which AGS permits a container to do for a line item it did not ask
# this tool to create.
REFUSED_MAXIMA = (0, -50, None, float("nan"), float("inf"))

# The two E3-08's security round adds, and why they are reachable rather than
# pathological. `json.loads` accepts the bare literals `NaN`, `Infinity` and
# `-Infinity` by default — they are not JSON, and Python's decoder takes them
# anyway — so a platform (or a proxy, or a fixture) that serves
# `{"scoreMaximum": NaN}` hands this client a float, not a parse error.
#
# **Neither is caught by a `maximum <= 0` guard.** `float("nan") <= 0` is `False`,
# because every comparison with NaN is; `float("inf") <= 0` is `False` because
# infinity is not nonpositive. So both walk straight past a guard whose own refusal
# message names them, and the division then produces `nan` or `0.0` and posts it.
# The parametrisation is what keeps them separate: a guard written `if not
# maximum` takes `0` and `None` and neither of these, and one written
# `if maximum <= 0` takes three of the five.
NON_FINITE_IDS = ("nan", "infinity")

# What a token grant carries its requested scopes in, and how RFC 6749 §3.3
# delimits them. The specification's, not this suite's.
SCOPE_PARAMETER = "scope"
SCOPE_DELIMITER = " "


def token_path_of(section: Any) -> str:
    """Where this platform issues access tokens, read out of its own discovery document."""
    document = section.platform.discovery() or {}
    url = document.get("token_endpoint")
    assert isinstance(url, str) and url, (
        f"The platform advertises no `token_endpoint` (it carries {sorted(document)}), so no grant "
        "can be told from an AGS call and this module cannot read what any scope was asked for."
    )
    return urlsplit(url).path


def scopes_asked_for(wire: Any, token_path: str) -> list[list[str]]:
    """The scopes each token grant on the wire requested, one list per grant.

    A list of lists rather than a set: how many grants were made and what each
    asked for are two different questions, and a module that flattened them could
    not tell one two-scope grant from two one-scope grants.
    """
    asked: list[list[str]] = []
    for call in wire.calls:
        if urlsplit(str(call.url)).path != token_path:
            continue
        body = call.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        requested = parse_qs(str(body or "")).get(SCOPE_PARAMETER, [])
        asked.append([scope for value in requested for scope in value.split(SCOPE_DELIMITER)])
    return asked


def call_the_client(
    ags_client: Any,
    function: Any,
    section: Any,
    rows: Any,
    wire: Any,
    **extra: Any,
) -> tuple[Any, BaseException | None]:
    """Drive one client entry point, answering what it returned and what escaped it.

    `test_the_ags_client_is_a_conformant_service_client.py::drive`'s shape, and
    its reasons: whether the client raises or returns on a refusal is settled
    nowhere and is not asserted anywhere, so it is caught rather than allowed to
    fly; and the commit is attempted whichever way the call exited, because a
    refusal's own `ags_call` row is written inside it and a rollback would throw
    away the record this module reads.
    """
    available: dict[str, Any] = {
        "session": rows.session,
        "section_id": section.id,
        "http": wire.session(),
        **extra,
    }
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


def a_line_item_out_of(section: Any, ags_contract: Any, maximum: Any) -> tuple[Any, str]:
    """Create a line item on the platform out of `maximum`, and store it on the section."""
    created = section.platform.create_line_item(
        section.context.launches[0],
        resourceId=ags_contract.resource_id,
        scoreMaximum=maximum,
    )
    return created, section.platform.line_item_id(created)


# ---------------------------------------------------------------------------
# The control on the scope reader, before either direction is believed of it.
# ---------------------------------------------------------------------------


def test_the_scope_reader_tells_the_writing_scope_from_its_read_only_sibling(
    ags_contract: Any,
) -> None:
    """The premise the scope assertion rests on, checked against the two strings.

    `…/scope/lineitem.readonly` contains `…/scope/lineitem` as a prefix, so a check
    written as `required in granted` — over the raw claim, or over a joined string
    — answers yes for the read-only one. This module's reader splits the
    space-delimited list RFC 6749 §3.3 defines and compares members, and this test
    is what says the two constants actually stand in the containment relation that
    makes the distinction non-trivial.

    **A red here means these tests are broken, not the client** — or the two
    constants have been mistyped, which is the same finding.
    """
    assert ags_contract.line_item_readonly_scope.startswith(ags_contract.line_item_scope), (
        f"{ags_contract.line_item_readonly_scope!r} does not begin with "
        f"{ags_contract.line_item_scope!r}, so a substring check would already tell the two apart "
        "and the assertion below would be an ordinary equality wearing this one's name."
    )
    assert ags_contract.line_item_readonly_scope != ags_contract.line_item_scope, (
        "The two scope constants are the same string, so no grant can ask for one without the "
        "other and R2 is not expressible."
    )

    granted = [ags_contract.line_item_readonly_scope]
    assert ags_contract.line_item_scope not in granted, (
        "Membership of the split list reports the writing scope present in a grant that asked only "
        "for the read-only one. That is the superstring defect this module's reader exists to "
        "avoid, and with it the scope assertion below would pass against the state R2 forbids."
    )


# ---------------------------------------------------------------------------
# R2 — the line-item read asks for the writing scope.
# ---------------------------------------------------------------------------


def test_a_line_item_read_asks_the_platform_for_the_writing_scope(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """R2: the container walk and the single-item read request `lineitem`.

    Driven through the client's own find-or-create, which is the entry point every
    line-item read in production goes through, and read off the platform's token
    endpoint — so what is asserted is the request the platform saw rather than a
    constant in a module this test may not import.

    **The mutation this kills:** `lineitem.readonly` on the read paths, which is
    the state LO-M1 found. It buys no privilege reduction — the tool holds the
    writing scope anyway, because it creates the column — and it costs a second
    credential: a platform that grants exactly what was asked hands back a token
    the client cannot then create with, so the create path takes a grant of its
    own on the very next call.

    **The near miss it must survive:** a grant asking for `lineitem` *beside*
    other scopes. RFC 6749 §3.3 makes the parameter a space-delimited list and
    nothing in R2 forbids a client asking for what it will need next, so the
    assertion is membership rather than equality with a single string.

    **The non-vacuity guard is that a grant happened at all.** "No grant asked for
    the read-only scope" is satisfied perfectly by a client that made no grant,
    which is also what a client that never reached the platform looks like.
    """
    section = ags_sections()
    token_path = token_path_of(section)
    service_wire.calls.clear()

    _answered, raised = call_the_client(
        ags_client,
        ags_client.find_or_create_line_item,
        section,
        committed_rows,
        service_wire,
    )
    assert raised is None, (
        f"Resolving the section's line item raised {raised!r}, so the client may not have reached "
        "the platform at all and the grants below would be a record of however far it got."
    )

    grants = scopes_asked_for(service_wire, token_path)
    assert grants, (
        f"The client made no token grant while resolving a line item — the calls it made were "
        f"{[str(call.url) for call in service_wire.calls]}. Every AGS route requires a bearer "
        "token this platform issued (ADR 0134), so a read that took no grant made no read, and "
        "every assertion about which scope was asked for would be about nothing."
    )

    asked_read_only = [
        scopes for scopes in grants if ags_contract.line_item_readonly_scope in scopes
    ]
    assert not asked_read_only, (
        f"A token grant made while reading a line item asked for "
        f"{ags_contract.line_item_readonly_scope!r}: {grants}. E3-08's boundary round (LO-M1) "
        "settles the writing scope on both line-item reads — the tool holds it anyway to create "
        "the column, so the read-only sibling reduces no privilege and costs a second credential "
        "on the very next call."
    )
    assert any(ags_contract.line_item_scope in scopes for scopes in grants), (
        f"No token grant made while reading a line item asked for "
        f"{ags_contract.line_item_scope!r}: {grants}. This is the half that says the read still "
        "authorised itself — without it, 'nothing asked for the read-only scope' is satisfied by a "
        "client that asked for nothing at all."
    )


def test_a_standalone_post_asks_for_the_score_scope_and_not_the_line_item_write(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """E3-08's security round: the standalone post path takes a score credential, and only that.

    `post_score` called with no caller — the standalone path, which is what the
    dev trigger and any single-section retry take — built its connector from the
    sweep's scope set and so asked the platform for a token carrying the
    **line-item write** scope to post a score with.

    **Why that is worth a finding rather than tidiness.** AGS separates the two on
    purpose: `…/scope/score` posts a result, `…/scope/lineitem` creates, edits and
    **deletes** columns. A credential minted for a score post that also carries the
    write scope is a token that can drop every column in that gradebook, held for
    whatever lifetime the platform grants, obtained on a path that had no reason to
    ask. Least privilege is the whole of AGS's scope split, and this is the one
    call in the client that does not need the writing half.

    **The mutation this kills**: the standalone path inheriting `SWEEP_SCOPES`
    again. Invisible to every behavioural test in the epic — the post succeeds
    either way, because the mock grants what it is asked for and the tool holds
    both scopes — so nothing but the grant on the wire can see it.

    **Read off the platform's own token endpoint**, the observable R2 uses one
    section over: what the platform was asked for, rather than a constant in a
    module this test may not import.

    **Two halves, and the second is the non-vacuity guard.** No grant asks for the
    line-item scope; *and* some grant asks for the score scope — without which
    "nothing asked for the write scope" is satisfied perfectly by a client that
    made no grant at all, which is also what a client that never reached the
    platform looks like.

    **The line item is resolved before the wire is cleared.** Finding or creating
    it legitimately takes a `lineitem` grant (R2, asserted above), so a test that
    counted grants across both steps would find the write scope for a reason this
    ruling does not touch. What is asserted here is the grants made by the *post*.
    """
    section = ags_sections()
    token_path = token_path_of(section)
    created, identifier = a_line_item_out_of(section, ags_contract, ags_contract.score_maximum)
    section = ags_sections.store_line_item(section, identifier)
    grade = ags_contract.grade(section.subjects[0])
    service_wire.calls.clear()

    _answered, raised = call_the_client(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        user_id=grade.user_id,
        score=grade.score,
        ledger=grade.ledger,
        timestamp=grade.timestamp,
    )
    assert raised is None, (
        f"The standalone post raised {raised!r}, so it may not have reached the platform at all "
        "and the grants below would be a record of however far it got."
    )

    grants = scopes_asked_for(service_wire, token_path)
    assert grants, (
        f"The standalone post made no token grant — the calls it made were "
        f"{[str(call.url) for call in service_wire.calls]}. Every AGS route requires a bearer "
        "token this platform issued (ADR 0134), so a post that took no grant made no post, and "
        "the assertion below would be about nothing."
    )
    asked_to_write = [scopes for scopes in grants if ags_contract.line_item_scope in scopes]
    assert not asked_to_write, (
        f"A token grant made while posting a score asked for {ags_contract.line_item_scope!r}: "
        f"{grants}. That scope creates, edits and deletes gradebook columns; a score post needs "
        f"{ags_contract.score_scope!r} and nothing else. The standalone path inherited the sweep's "
        "scope set, so a credential able to delete every column in the gradebook was minted for a "
        "call that only ever writes one number."
    )
    assert any(ags_contract.score_scope in scopes for scopes in grants), (
        f"No token grant made while posting a score asked for {ags_contract.score_scope!r}: "
        f"{grants}. This is the half that says the post still authorised itself — without it, "
        "'nothing asked for the write scope' is satisfied by a client that asked for nothing."
    )


# ---------------------------------------------------------------------------
# R1 — the posted value scales, and a nonpositive maximum is walked past.
# ---------------------------------------------------------------------------


def test_the_posted_value_scales_to_a_found_line_items_maximum(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
) -> None:
    """R1: `61.5` against a column out of 50 reaches the platform as `30.75`.

    The line item is created out of 50 and read back from the platform's own
    document before anything is posted, so the maximum this test scales against is
    the platform's rather than the one it seeded with.

    **The arithmetic, by hand** (`docs/MISTAKES.md` entry 19, and E3-08's own
    criterion 1 for the drive): the canonical percentage string is `61.5`, R1
    settles `scoreGiven = percentage / 100 x scoreMaximum`, so
    `61.5 / 100 = 0.615` and `0.615 x 50 = 30.75`.

    **The mutations this kills:**
      1. *The percentage sent unscaled* — `61.5` into a column out of 50, which is
         a grade of 123% for every student in a section whose column an instructor
         re-pointed. This is the state LO-H1 found, and it is invisible to every
         other test in the epic because every line item the tool *creates* is out
         of 100, where scaling and not scaling agree exactly.
      2. *Scaling against a constant 100 rather than against the line item's own
         maximum*, which is the same defect wearing the fix's clothes: it sends
         `61.5` again.
      3. *Scaling against the maximum but sending some other maximum beside it* —
         the platform refuses a `scoreMaximum` that disagrees with the line item
         (ADR 0051), so the maximum is asserted here too and the two are one body.

    **The near miss that must stay green:** the canonical string in
    `grade_sync.score_text` is unchanged. R1 scales the wire body only, and the
    comparison E3-06 makes and the ledger §3.4 carries are both untouched — which
    is why this module asserts the platform's copy of the body and says nothing
    about the row.
    """
    section = ags_sections()
    created, identifier = a_line_item_out_of(section, ags_contract, A_FOUND_MAXIMUM)
    section = ags_sections.store_line_item(section, identifier)

    held = section.platform.ags_get(identifier, scope=ags_contract.line_item_scope).json()
    maximum = held.get(ags_contract.score_maximum_member)
    assert maximum == A_FOUND_MAXIMUM, (
        f"The line item this test seeded is out of {maximum!r} rather than {A_FOUND_MAXIMUM}, so "
        f"the hand-computed {THE_SCALED_VALUE} is the wrong expectation and this test would be "
        "asserting arithmetic nobody did."
    )
    assert maximum != ags_contract.score_maximum, (
        f"The seeded maximum is {maximum!r}, which is §3.4's own default — scaling and not scaling "
        "agree exactly there, and the mutation this test exists for would be invisible."
    )

    grade = ags_contract.grade(section.subjects[0])
    assert grade.score == str(THE_UNSCALED_VALUE), (
        f"The canonical percentage string this suite hands the client is {grade.score!r} and this "
        f"module's arithmetic was done for {THE_UNSCALED_VALUE}. The two must agree or "
        f"{THE_SCALED_VALUE} is not what R1's rule produces here."
    )

    _answered, raised = call_the_client(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=created,
        user_id=grade.user_id,
        score=grade.score,
        ledger=grade.ledger,
        timestamp=grade.timestamp,
    )
    assert raised is None, (
        f"Posting against a line item out of {maximum!r} raised {raised!r}. A column an instructor "
        "re-pointed is an ordinary state, not a fault."
    )

    stored = ags_contract.scores_posted(section.platform, identifier)
    assert stored, (
        f"The platform recorded no score against {identifier!r}. Either nothing was posted or the "
        "post was refused — this platform refuses a `scoreMaximum` that disagrees with the line "
        "item's (ADR 0051), so a client that scaled the value and sent the wrong maximum lands "
        "here rather than on the comparison below."
    )
    delivered = stored[-1]

    assert delivered.get(ags_contract.given_member) == THE_SCALED_VALUE, (
        f"The platform received `{ags_contract.given_member}` "
        f"{delivered.get(ags_contract.given_member)!r} against a line item out of {maximum!r}, "
        f"and R1 settles {THE_SCALED_VALUE}: {THE_UNSCALED_VALUE} / 100 x {A_FOUND_MAXIMUM}.\n\n"
        f"A value of {THE_UNSCALED_VALUE} is the percentage sent unscaled — a grade of 123% in "
        "this column, for every student in a section whose points an instructor changed. It is "
        "right for every line item this tool creates, which is why nothing else in this epic can "
        "see it."
    )
    assert delivered.get(ags_contract.maximum_sent_member) == maximum, (
        f"The platform received `{ags_contract.maximum_sent_member}` "
        f"{delivered.get(ags_contract.maximum_sent_member)!r} beside a scaled value, and the line "
        f"item is out of {maximum!r}. R1 posts the scaled value *beside that same maximum*; the "
        "two are one body and a client that scaled against one number and declared another has "
        "posted a value the platform will read against the wrong denominator."
    )


@pytest.mark.parametrize(
    "maximum", REFUSED_MAXIMA, ids=["zero", "negative", "absent", *NON_FINITE_IDS]
)
def test_a_nonpositive_maximum_is_walked_past_rather_than_divided_by(
    ags_client: Any,
    ags_sections: Any,
    service_wire: Any,
    committed_rows: Any,
    ags_contract: Any,
    maximum: Any,
) -> None:
    """R1's refusal half: no divide, no post, for a maximum that cannot be scored into.

    A line item document carrying zero, a negative maximum, none at all, `NaN` or
    `Infinity` is handed to the client's post path. R1 gives it ADR 0135's
    no-address shape: the section is walked past with a logged refusal.

    **A second layer also refuses these values, and the first assertion exists to
    tell the two apart.** This is the gap E3-08's security round found in the two
    rows it had just added: with the guard reverted to `maximum <= 0`, `nan` and
    `inf` flow past it into the scaling arithmetic and die a layer later on the
    JSON-number check — so **nothing is posted either way**, and an assertion that
    only reads the platform's log is satisfied by both. A battery mutation
    reverting the guard would have survived. What separates them is *how* the call
    ended: R1's guard walks the section past and does not raise, while the
    downstream check raises. `raised is None` is therefore the layer-pin, and it
    is asserted before the post is looked at (`docs/MISTAKES.md` entry 3 — a guard
    test whose outcome a second defence layer also produces).

    **All five rows carry it, not just the two new ones**, because the ambiguity is
    not confined to them: with the guard gone entirely, the absent row reaches the
    arithmetic as `None` and dies of a `TypeError`, posting nothing, which the
    no-post assertion also accepts.

    **The mutations these kill:**
      1. *The guard reverted to a sign comparison* — `maximum <= 0`, which `nan`
         and `inf` both pass because neither is nonpositive. Killed by the
         raise-shape assertion, not by the post assertion.
      2. *A `ZeroDivisionError` reaching the caller* — the naive reading of R1's
         formula, which turns one badly configured column into an exception on the
         weekly beat. Also killed by the raise-shape assertion.
      3. *A post going out anyway* — `0`, `inf`, `nan` or the unscaled percentage
         against a column that cannot hold it. Asserted on the platform's own log.
      4. *The refusal treated as a reason to stop the sweep.* Nothing here asserts
         that, deliberately: which sections the walk visits after a refusal is
         E3-06's `test_the_sweep_walks_past_a_section_it_cannot_post_to.py`'s
         subject, and asserting it in two places would put one rule in two
         inventories.

    **The maxima are parametrised rather than folded together**, because they are
    five values and no single sloppy guard takes them all: `if not maximum` gets
    `None` and `0` right and a negative one wrong, `if maximum is None` gets
    exactly one, and `if maximum <= 0` — the guard as shipped — gets three and lets
    both non-finite values through. Each is its own row so the runner names which.

    **NaN and Infinity are E3-08's security round**, and they are reachable rather
    than pathological: `json.loads` accepts the bare literals `NaN` and `Infinity`
    by default — they are not JSON and Python's decoder takes them anyway — so a
    document carrying `{"scoreMaximum": NaN}` arrives here as a float. `nan <= 0`
    is `False` because every comparison with NaN is, and `inf <= 0` is `False`
    because infinity is not nonpositive. Both therefore walk past a guard whose own
    refusal message names them, and the division then produces `nan` or `0.0` and
    **posts it**: a gradebook column holding `NaN` is a grade nobody can read, and
    one holding `0.0` is a statement about a student this tool reached by dividing
    by infinity.

    **The positive control is the test above**, which posts through the identical
    path against a maximum that *can* be scored into — without it, "nothing was
    posted" is satisfied by a client that never posts at all.
    """
    section = ags_sections()
    created, identifier = a_line_item_out_of(section, ags_contract, ags_contract.score_maximum)
    section = ags_sections.store_line_item(section, identifier)

    # The document the client is handed, carrying the maximum under test. Composed
    # rather than created on the platform: AGS gives a container no reason to
    # accept a line item out of zero, so a platform that refused the creation
    # would make this case unposeable rather than untested.
    unscoreable = dict(created)
    if maximum is None:
        unscoreable.pop(ags_contract.score_maximum_member, None)
    else:
        unscoreable[ags_contract.score_maximum_member] = maximum

    before = ags_contract.scores_posted(section.platform, identifier)
    grade = ags_contract.grade(section.subjects[0])

    _answered, raised = call_the_client(
        ags_client,
        ags_client.post_score,
        section,
        committed_rows,
        service_wire,
        line_item=unscoreable,
        user_id=grade.user_id,
        score=grade.score,
        ledger=grade.ledger,
        timestamp=grade.timestamp,
    )

    assert raised is None, (
        f"Posting against a line item whose maximum is {maximum!r} raised {raised!r}. R1 gives this "
        "case ADR 0135's no-address shape — the section is **walked past** with a logged refusal, "
        "which does not raise — so what escaped names the layer that refused, and this is the "
        "assertion that tells the two apart.\n\n"
        "A `ZeroDivisionError` is the guard gone and the zero row dividing. A `ValueError` or a "
        "typed serialisation refusal is the guard reverted to `maximum <= 0` and the value flowing "
        "on to the JSON-number check a layer later, which is where `nan` and `inf` die if nothing "
        "stops them first. A `TypeError` is the absent row reaching the arithmetic as `None`. In "
        "every one of those the no-post assertion below still holds, which is exactly why it "
        "cannot be the only thing asserted."
    )

    after = ags_contract.scores_posted(section.platform, identifier)
    assert after == before, (
        f"A score reached the platform against a line item whose maximum is {maximum!r}. Before "
        f"the call the platform held {before}; it now holds {after}. R1, widened by E3-08's "
        "security round: a maximum that is missing, zero, negative **or not finite** means the "
        "section is walked past with a logged refusal, never a post — there is no value that means "
        "anything in a column that cannot be scored into, and `0`, `inf` and `nan` are each worse "
        "than an absent grade.\n\n"
        "If this is the `nan` or `infinity` row, the guard is almost certainly still written "
        "`maximum <= 0`: both comparisons answer `False`, so the value reaches the division and "
        "what got posted is whatever `percentage / 100 x maximum` produced."
    )
