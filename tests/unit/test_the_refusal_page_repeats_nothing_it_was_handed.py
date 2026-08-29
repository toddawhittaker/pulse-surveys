"""The refusal page has nowhere to put a caller's words — E1 boundary fix, M7.

`refusal_page` is the one answer either door can give whose body no test ever
scanned. Its three siblings in `app.api.deps` are swept by
`tests/unit/test_chosen_landing.py::test_a_page_built_only_from_constants_takes_
no_parameter_at_all`, and that sweep deliberately leaves this page out: it takes
a value, because naming which check refused is its job. Taking a value is not
the same as printing one, and until this module nothing said which of the two it
does — today it does both, and its text argument is rendered into the body.

**The settled design this module is written from.** The page derives its body
copy from the guard name alone, through a module constant with a constant
default for a guard nothing maps, and accepts no free-text message parameter.
The guard name reaches the page as the `data-reason` attribute — the machine
vocabulary the `LaunchRefusedError` subclasses and the web door's
`SessionRefusedError` already publish, which `tests/e2e/exit-refused-launches.
spec.ts` reads in a browser.

**Why that is worth a module of tests.** This page is rendered for people who
have not authenticated: anybody who can post a form at `/lti/launch` can reach
it. A page that prints something a caller chose is a page an attacker writes
half of, and the value most likely to be handed to it is the one that is right
there — the exception that refused. `test_a_refusal_does_not_name_the_key_set_
address_the_tool_could_not_reach` in the launch door suite is the record of
what that costs already, for a value nobody chose deliberately.

**Nothing here names a parameter.** The ticket settles what the page may *do*,
not what its argument is called, and a test that pinned a spelling would be
choosing an interface the ticket leaves open. So the signature is read, every
parameter is handed a canary of its own, and the assertions are about where
those canaries end up. That also makes the central test say the whole rule
rather than one instance of it: *no* argument this page takes can reach its
body, whatever it is called and however many there are.

**The canaries are plain lowercase and hyphens on purpose.** A canary
containing `<` or `&` would be escaped on its way into the markup, so "the
canary is not in the body" would be true of a page that printed it — the
scan going blind on exactly the value it exists to find (`docs/MISTAKES.md`
entry 3). Nothing in these canaries is changed by HTML escaping, so a literal
search finds them wherever they are.

**The integration half is next door.** `refused()` in
`tests/integration/test_lti_launch_door.py` and in
`tests/integration/test_web_login_door.py` requires every refusal either door
actually answers to render this page with exactly one marker on it. This module
is the half that says what the page can and cannot contain; those say that it is
the page the doors reach.
"""

import importlib
import inspect
import re
from typing import Any

import pytest

# The page under test, by the name every record in this repository spells it —
# `tests/fixtures/landing.py`'s D5 note ("`PAGE`, `refusal_page`,
# `cancelled_page`, `no_account_page` and the new `no_access` move into"
# `app.api.deps`) and `test_chosen_landing.py`'s note on why it is not in that
# module's constants-only sweep. The module it lives in comes from
# `landing_contract`, so a move is one line there rather than one here.
REFUSAL_PAGE = "refusal_page"

# `data-reason="<guard>"` as it is rendered. Both quote styles are matched, for
# the reason the two door modules give: which one the renderer emits is not
# this test's decision, and a marker written with single quotes is the same
# marker.
REASON_MARKER = re.compile(r"""data-reason=(?:"([^"]*)"|'([^']*)')""")

# What a canary is built from. One per parameter, derived from the parameter's
# own name so a failure says which argument leaked rather than that something
# did. Lowercase and hyphens only — see the module docstring on escaping.
CANARY_PREFIX = "e1-boundary-canary"

# The guard names the two doors publish today, which the page's copy is keyed
# by. **Copies, and knowingly so**: the authoritative lists are
# `tests/integration/test_lti_launch_door.py` (the ten `LaunchRefusedError`
# subclasses E1-08 names, plus `AnonymousLaunchRefused`, which this batch adds)
# and `tests/integration/test_web_login_door.py::WEB_DOOR_GUARD`. A name that
# drifts out of step with those does not make this module lie — it becomes one
# more unknown guard, which the default copy covers and which
# `test_an_unknown_guard_is_answered_with_the_same_constant_copy_as_any_other`
# is about. What this list buys is that every name a door can actually emit
# renders a page rather than raising on a missing mapping entry.
DOOR_GUARDS = (
    "SignatureRefused",
    "AudienceRefused",
    "IssuerRefused",
    "NonceRefused",
    "NonceReplayedError",
    "DeploymentRefused",
    "MessageTypeRefused",
    "VersionRefused",
    "StateRefused",
    "ClockSkewRefused",
    "AnonymousLaunchRefused",
    "SessionRefusedError",
)

# Two names no guard class has, for the unknown-guard cases. Two rather than
# one, because the rule is that an unmapped guard gets *the* default copy and a
# single sample cannot tell a constant from a value derived from what it was
# handed.
AN_UNKNOWN_GUARD = "e1-boundary-guard-nothing-maps"
ANOTHER_UNKNOWN_GUARD = "e1-boundary-guard-nothing-maps-either"


def refusal_page_of(landing_contract: Any) -> Any:
    """`app.api.deps.refusal_page`, or a failure naming where it was looked for."""
    try:
        module = importlib.import_module(landing_contract.deps_module)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{landing_contract.deps_module}` does not import ({missing}). E1-13 gathers the door "
            "pages there — the module whose docstring already describes them."
        )
    page = getattr(module, REFUSAL_PAGE, None)
    assert callable(page), (
        f"`{landing_contract.deps_module}` exposes no callable `{REFUSAL_PAGE}`; it exposes "
        f"{sorted(name for name in vars(module) if not name.startswith('_'))}. Both doors answer a "
        "token they cannot accept with that page, and E1-15's browser proof addresses it."
    )
    return page


def parameter_names(page: Any) -> list[str]:
    """Every parameter `page` accepts, in order, excluding `*args`/`**kwargs`.

    A page taking none would be a page with no marker either, since the guard
    name has to arrive somehow; that is a different design from the settled one
    and the tests below say so where it would matter, rather than treating an
    empty list as a quiet pass.
    """
    signature = inspect.signature(page)
    return [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]


def canary_for(parameter: str) -> str:
    """The one value handed to the parameter called `parameter`.

    Derived from the name so that a leak names the argument that leaked. Nothing
    in it is touched by HTML escaping (module docstring), so a literal search
    over the rendered body cannot miss it because the renderer was careful.
    """
    return f"{CANARY_PREFIX}-{parameter.replace('_', '-')}"


def render(page: Any, **chosen: str) -> str:
    """Call `page` with every parameter filled, and answer the rendered markup.

    Every parameter gets `chosen[name]` where the caller named one and its own
    canary otherwise, so this works whatever the page's arity is: the whole
    point is that the tests below never name an argument.

    A page whose parameter cannot take a string fails here with a message
    saying so rather than raising through the test. That is not a pass — it is
    this helper reporting that the settled design ("the guard name alone") has
    grown a parameter of some other type, which is a question for the pull
    request.
    """
    names = parameter_names(page)
    signature = inspect.signature(page)
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for name in names:
        value = chosen.get(name, canary_for(name))
        if signature.parameters[name].kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[name] = value
    try:
        rendered = page(*positional, **keyword)
    except Exception as failure:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{REFUSAL_PAGE}` raised {type(failure).__name__}: {failure} when called with a "
            f"string for each of {names}. Every one of these tests renders the page that way, "
            "because none of them may name an argument the ticket does not settle a name for. A "
            "parameter that cannot take a string is an interface question for the pull request."
        )
    return body_of(rendered)


def body_of(rendered: Any) -> str:
    """The markup a page answered with, whatever kind of object it answered with.

    A `Response`, a string, or something that stringifies to markup: which of
    those `refusal_page` returns is not settled by anything this module may read
    from, and every assertion here is about the bytes a browser receives either
    way.
    """
    body = getattr(rendered, "body", None)
    if isinstance(body, bytes | bytearray):
        return bytes(body).decode("utf-8", "replace")
    if isinstance(body, str):
        return body
    if isinstance(rendered, str):
        return rendered
    text = str(rendered)
    assert "<" in text, (
        f"`{REFUSAL_PAGE}` answered {rendered!r}, which carries no `body` and does not look like "
        "markup, so this module cannot read what a browser would be shown. Say in the pull request "
        "what the page returns and `body_of` here is the one place that changes."
    )
    return text


def markers_in(body: str) -> list[str]:
    """Every `data-reason` value the markup carries, in document order."""
    return [double or single for double, single in REASON_MARKER.findall(body)]


def outside_the_markers(body: str) -> str:
    """The markup with every `data-reason` value emptied out.

    What is left is everything a reader sees plus the markup around it, which is
    where a caller's words must never appear. Blanking the attribute rather than
    deleting the element keeps the rest of the document intact, so a leak that
    happened to sit next to the marker is still found.
    """
    return REASON_MARKER.sub('data-reason=""', body)


def the_guard_parameter(page: Any) -> str:
    """Which of `page`'s parameters carries the guard name into the marker.

    Found rather than named, for the reason this module's docstring gives: the
    ticket settles that the page derives its copy from the guard name and does
    not settle what that argument is called, so a test that spelled it would be
    choosing an interface the ticket leaves open.

    Found by rendering with a canary in every parameter and reading which one
    came back inside `data-reason` — the page's own answer to the question,
    rather than this module's guess at it. Ambiguity stops rather than picks: a
    marker carrying two of the canaries is a page nobody designed, and choosing
    one would be this helper deciding what the tests are about.
    """
    body = render(page)
    markers = markers_in(body)
    carried = [
        name
        for name in parameter_names(page)
        if any(canary_for(name) in marker for marker in markers)
    ]
    if len(carried) != 1:
        pytest.fail(
            f"{len(carried)} of `{REFUSAL_PAGE}`'s parameters reach the `data-reason` marker "
            f"({carried}; the markers were {markers}). Exactly one carries the guard name — that "
            "is what the marker is — so none means the vocabulary the doors publish no longer "
            "reaches the page, and more than one means the attribute is assembled from several "
            "arguments and no reader can tell which is the guard."
        )
    return carried[0]


def test_the_refusal_page_renders_markup_this_module_can_read(
    landing_contract: Any, configured_env: dict[str, str]
) -> None:
    """The control for every test below, and worth nothing to skip.

    `render` and `body_of` are this module's own machinery: they call a page
    without naming its arguments and turn whatever it answers into the markup a
    browser would receive. If that machinery is broken — a page that answers
    something with no body, a signature nothing can be filled from — every scan
    below is a scan over an empty string, and "the canary is not in the body" is
    true of nothing at all (`docs/MISTAKES.md` entry 3, and entry 9 on citing a
    guard that has never been run).

    So this asserts the two facts the rest depends on: the page renders
    something, and it carries exactly one reason marker. Nothing here is about
    what the page may contain.

    `configured_env` is depended on and not used, for the reason
    `test_chosen_landing.py` gives: `app.api.deps` is an application module and
    anything it imports may build a `Settings` (`docs/MISTAKES.md` entry 40).
    """
    page = refusal_page_of(landing_contract)

    body = render(page)

    assert body.strip(), (
        f"`{REFUSAL_PAGE}` rendered an empty body. Every assertion in this module is about what "
        "that body does and does not carry, and all of them are true of nothing."
    )
    assert len(markers_in(body)) == 1, (
        f"`{REFUSAL_PAGE}` rendered the reason markers {markers_in(body)}; it renders exactly one, "
        "which is what both doors' refusal assertions and `exit-refused-launches.spec.ts` read to "
        "say which guard fired. With none, the test below cannot tell an argument that reached the "
        "marker from one that reached nothing."
    )


def test_no_argument_the_refusal_page_takes_can_reach_its_body(
    landing_contract: Any, configured_env: dict[str, str]
) -> None:
    """The rule, stated over the whole signature rather than over one parameter.

    Every parameter the page accepts is handed a canary of its own, and the
    rendered markup is required to carry none of them anywhere except inside the
    `data-reason` attribute. That is the settled design as a property: the body
    copy comes from the guard name through a module constant, so the only thing
    a caller can put on this page is a name in a machine-readable attribute.

    **The mutation this must kill, and it is the state of the code today:** the
    page takes a text argument and renders it into the body. Today's callers all
    pass constants, so nothing has leaked yet — the finding is latent, and the
    value nearest to hand at every call site is the exception that refused, whose
    `str()` carries whatever a library was told by whoever provoked it.

    **The near miss it must survive:** removing the parameter and interpolating
    the *guard name* into the copy instead. That still reaches the body from
    something a caller chose, and it fails here, because the guard's canary is
    scanned for outside the marker exactly like every other argument's.

    **Two controls, because a scan for absence is satisfied by emptiness.** The
    body has to be non-empty, and at least one canary has to be *found* — inside
    the marker, where it is allowed. A search that finds nothing anywhere is a
    search that has gone blind (`docs/MISTAKES.md` entry 3, and entry 35 on
    requiring a guard to find the thing on a subject that certainly has it).
    """
    page = refusal_page_of(landing_contract)
    names = parameter_names(page)

    body = render(page)

    assert body.strip(), (
        f"`{REFUSAL_PAGE}` rendered an empty body, so 'no argument reached it' is a statement "
        "about nothing."
    )
    markers = markers_in(body)
    found_where_allowed = sorted(
        name for name in names if any(canary_for(name) in marker for marker in markers)
    )
    assert found_where_allowed, (
        f"None of the values handed to {names} appears in any `data-reason` marker ({markers}), so "
        "this scan has no evidence it can see a caller's value at all — and its silence about the "
        f"body says nothing. Either `{REFUSAL_PAGE}` no longer carries the guard name into the "
        "marker, which is a change to the vocabulary both doors publish, or it takes no argument "
        "at all, which would mean the page cannot say which check refused."
    )
    leaked = sorted(name for name in names if canary_for(name) in outside_the_markers(body))
    assert not leaked, (
        f"The values handed to {leaked} appear in the refusal page's body. Rendered:\n\n"
        f"{body}\n\n"
        "This page is answered to anybody who can post a form at a door, so a caller's string "
        "reaching its body is half the page written by whoever provoked it — and the string "
        "nearest to hand at a call site is the exception that refused, which carries whatever a "
        "library was handed. The settled design is that the copy comes from the guard name alone "
        "through a module constant, with a constant default, and that the guard name reaches only "
        "the `data-reason` attribute."
    )


def test_an_unknown_guard_is_answered_with_the_same_constant_copy_as_any_other(
    landing_contract: Any, configured_env: dict[str, str]
) -> None:
    """Two guards nothing maps get one default, not two derived sentences.

    The settled design gives the copy mapping a constant default. This is that
    default being constant: two guard names that differ in every character
    produce markup that differs only in the marker.

    **The mutation this kills:** a default that reports what it was given —
    `f"…({guard})…"`, or a `.title()` of the name — which is the natural way to
    write a fallback and puts a caller's string back in the body under a name
    nobody would call free text. It is also the shape a future call site would
    reach for when it wants to be helpful.

    **The near miss it must survive:** a mapping that happens to give these two
    unknown names the same *keyed* copy. It cannot: nothing maps either, which
    is what makes them the default's own case, and the guard parameter is found
    rather than named so the value certainly reaches the lookup.

    **Its control is that the two bodies are not empty**, and that the two
    markers do differ — over a page that rendered nothing, or that dropped the
    guard entirely, "the bodies are identical" is true and says nothing.
    """
    page = refusal_page_of(landing_contract)
    guard = the_guard_parameter(page)

    one = render(page, **{guard: AN_UNKNOWN_GUARD})
    other = render(page, **{guard: ANOTHER_UNKNOWN_GUARD})

    assert one.strip() and other.strip(), (
        f"`{REFUSAL_PAGE}` rendered an empty body for one of {AN_UNKNOWN_GUARD!r} and "
        f"{ANOTHER_UNKNOWN_GUARD!r}, so 'the two are the same' is a statement about two empty "
        "strings."
    )
    assert markers_in(one) != markers_in(other), (
        f"Both renderings carry the reason markers {markers_in(one)}, so the guard name did not "
        f"reach the page and the comparison below is between two copies of one constant page. The "
        f"parameter this test filled was {guard!r}."
    )
    assert outside_the_markers(one) == outside_the_markers(other), (
        "Two guard names nothing maps produced different pages.\n\n"
        f"  {AN_UNKNOWN_GUARD}: {outside_the_markers(one)}\n\n"
        f"  {ANOTHER_UNKNOWN_GUARD}: {outside_the_markers(other)}\n\n"
        "The copy for a guard the mapping does not know is a constant, so everything outside the "
        "`data-reason` attribute is the same page whatever the name was. A default that varies "
        "with the name is the name being printed, and the name is a value a caller chose."
    )


@pytest.mark.parametrize("guard_name", (*DOOR_GUARDS, AN_UNKNOWN_GUARD))
def test_a_guard_name_renders_a_page_naming_that_guard_and_no_other(
    landing_contract: Any, configured_env: dict[str, str], guard_name: str
) -> None:
    """Every name a door can emit renders a page, and the page names that one.

    Two mutations, one per assertion. A copy mapping that raises on a name it
    has no entry for turns a refusal into a 500 — the same failure this batch is
    closing on the launch path, arriving from the other side. And a page that
    renders a marker other than the guard it was handed leaves both doors'
    refusals, and `exit-refused-launches.spec.ts`, naming the wrong check.

    **The near miss it must survive:** a page that prints every guard's marker,
    which leaves "the guard is named" true and useless. The assertion is on the
    exact list of markers rather than on membership.

    The unknown name is a case here as well as in the test above, because the
    default's copy is a different question from the default's *marker*: whatever
    the copy, the name a caller was refused under is the name that goes in the
    attribute.
    """
    page = refusal_page_of(landing_contract)
    guard = the_guard_parameter(page)

    body = render(page, **{guard: guard_name})

    assert body.strip(), f"`{REFUSAL_PAGE}` rendered an empty body for the guard {guard_name!r}."
    assert markers_in(body) == [guard_name], (
        f"The page rendered for the guard {guard_name!r} carries the reason markers "
        f"{markers_in(body)}; it should carry exactly {[guard_name]}. That name is the machine "
        "vocabulary both doors publish, and it is how a browser-side spec says which check refused "
        "without reading a sentence."
    )
