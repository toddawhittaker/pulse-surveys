"""A purged nonce is always a nonce whose in-flight state is already dead — the replay window.

SPEC §7.2's launch is OpenID Connect's implicit flow, and the thing that makes a
signed `id_token` single-use is the nonce: the tool mints one, remembers it, and
refuses a launch that presents one it has already seen. Two pieces of state stand
behind that refusal and they expire on two different timers, both in
`app.lti.launch`:

  - **the in-flight record** — what the tool remembers about a launch it has
    started: the `state`, the nonce it minted, where the launch was going. It lives
    `IN_FLIGHT_LIFETIME_SECONDS`.
  - **the nonce ledger** — what the tool remembers about nonces it has *spent*, so
    a second presentation of the same one is refused. It lives
    `NONCE_LEDGER_LIFETIME_SECONDS`.

**The invariant is that the ledger outlives the in-flight state, strictly.** Read
the other way round and the hole is plain: if a nonce could be forgotten by the
ledger while its in-flight record were still live, a captured `id_token` replayed
in that gap would find an in-flight record to match against and no memory of
having been spent — which is a second successful launch on one token, and a
session issued to whoever held it.

**Nothing else bounds that window, and this is the reason the test exists rather
than the reasoning being left in a comment.** The obvious answer — "the token's own
expiry stops it" — is not available here: this tool does not enforce `exp` on the
launch token (`verify_exp` is off), deliberately, because clock skew between a
platform and a tool is the most common cause of a launch that should have worked
and did not, and SPEC §6.1's health panel reports skew rather than refusing on it.
So the token stays cryptographically valid indefinitely, and the *only* thing
standing between a captured token and a replay is the ordering of these two
lifetimes.

**Why this is not `invariant`-marked.** The isolated §4.1 pass is for the
visibility invariants — who may see whose data. This is launch authentication: a
replay is an authentication defect rather than a widening of what a legitimate
reader sees. It runs in the ordinary unit pass, and putting it in the §4.1 pass
would dilute what a failure there means.

**Which failure a red is.** The module and both names are looked up inside the test
body, each with a `pytest.fail` naming what is missing, so a rename or a move is a
FAILED naming the constant rather than a collection error
(`docs/MISTAKES.md` entry 44).
"""

from importlib import import_module
from typing import Any

import pytest

LAUNCH_MODULE = "app.lti.launch"
NONCE_LEDGER_LIFETIME = "NONCE_LEDGER_LIFETIME_SECONDS"
IN_FLIGHT_LIFETIME = "IN_FLIGHT_LIFETIME_SECONDS"


def _launch_module() -> Any:
    """`app.lti.launch`, or a failure naming it."""
    try:
        return import_module(LAUNCH_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == LAUNCH_MODULE or LAUNCH_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{LAUNCH_MODULE}` does not exist. It is where SPEC §7.2's launch handshake lives, "
            "and where both of the lifetimes this test is about are defined."
        )


def _seconds(module: Any, name: str) -> int:
    """One lifetime constant, as a whole number of seconds, or a failure naming it."""
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(
            f"`{LAUNCH_MODULE}` exposes no `{name}`. Both lifetimes are named constants in that "
            "module precisely so the relationship between them is readable in one place; a value "
            "that has moved into a settings field or been inlined into a query takes this "
            "invariant with it, and the change that moves it is where the new home is asserted."
        )
    assert isinstance(value, int | float) and not isinstance(value, bool), (
        f"`{LAUNCH_MODULE}.{name}` is {value!r}, which is not a number of seconds this test can "
        "compare. A timedelta or a string would need converting, and the conversion belongs in "
        "this file rather than in an assertion that quietly compares the wrong units."
    )
    return int(value)


def test_the_nonce_ledger_outlives_the_in_flight_record_it_guards() -> None:
    """`NONCE_LEDGER_LIFETIME_SECONDS` is strictly greater than `IN_FLIGHT_LIFETIME_SECONDS`.

    The whole of the replay argument is this comparison. While an in-flight record
    is live, a captured `id_token` presented a second time has something to match
    against; the only thing that refuses it is the ledger remembering the nonce was
    spent. So the ledger has to still be remembering for at least as long as the
    in-flight record can still be matched — and strictly longer, because equal
    lifetimes purge in an order nothing here controls and a purge that ran the
    ledger's sweep first opens the gap for as long as that sweep takes.

    **The mutation this kills:** the two constants swapped, or the ledger's
    lifetime shortened to the in-flight one on the reasoning that a nonce cannot
    be replayed after its launch has expired. It can: the tool does not enforce the
    token's `exp` (clock skew, §6.1), so the token itself never stops being valid
    and the in-flight record is the only thing that expires.

    **The near miss it must survive:** the two set equal. That is the version an
    implementer reaches for when tidying two numbers that "mean the same window",
    and it is why the comparison is `>` rather than `>=`.

    **What this does not reach** (`docs/MISTAKES.md` entry 14): whether either
    sweep actually *runs* on its stated interval, and whether the ledger is
    consulted before the in-flight record is matched. Both are behaviours rather
    than constants, and this test asserts the relationship the behaviours rest on.
    """
    module = _launch_module()
    ledger = _seconds(module, NONCE_LEDGER_LIFETIME)
    in_flight = _seconds(module, IN_FLIGHT_LIFETIME)

    assert ledger > in_flight, (
        f"`{NONCE_LEDGER_LIFETIME}` is {ledger} and `{IN_FLIGHT_LIFETIME}` is {in_flight}, so a "
        f"nonce is forgotten by the ledger {in_flight - ledger} seconds before the in-flight "
        "record it belongs to expires.\n\n"
        "In that window a captured `id_token` replayed against this tool finds an in-flight record "
        "to match and no memory of the nonce having been spent, and the launch succeeds a second "
        "time — a session issued to whoever holds the token. Nothing else closes the window: this "
        "tool does not enforce the launch token's `exp`, deliberately, because clock skew between "
        "a platform and a tool is the ordinary cause of a launch that should have worked and did "
        "not (SPEC §6.1 reports skew rather than refusing on it). So the token stays valid and the "
        "ordering of these two lifetimes is the whole of the replay defence.\n\n"
        "If the in-flight window genuinely needs to grow, the ledger grows with it in the same "
        "change."
    )


def test_both_lifetimes_are_positive_so_neither_is_a_window_nothing_remembers() -> None:
    """The control under the comparison. **A red here means this module is broken.**

    `ledger > in_flight` is satisfied by `1 > 0`, and by any pair where the
    in-flight lifetime has been zeroed — a tool that remembers no launch at all,
    which refuses every legitimate launch and passes the assertion above for a
    reason that has nothing to do with replay. It is also satisfied by a negative
    number, which reads as a lifetime and behaves as an immediate purge.

    So both are required to be real windows before their ordering means anything
    (`docs/MISTAKES.md` entry 3: where a test can be satisfied by emptiness, assert
    non-emptiness first and say why the guard is not ceremony).
    """
    module = _launch_module()
    ledger = _seconds(module, NONCE_LEDGER_LIFETIME)
    in_flight = _seconds(module, IN_FLIGHT_LIFETIME)

    assert in_flight > 0, (
        f"`{IN_FLIGHT_LIFETIME}` is {in_flight}, so the tool remembers a launch it has started for "
        "no time at all and every legitimate launch is refused when it comes back. It also makes "
        "the ordering assertion beside this one true for a reason that has nothing to do with "
        "replay."
    )
    assert ledger > 0, (
        f"`{NONCE_LEDGER_LIFETIME}` is {ledger}, so no spent nonce is remembered and every launch "
        "token is replayable immediately."
    )
