"""The session module both doors share — ticket E1-08.

E1-08's module layout puts `SessionClaims`, `issue_session`, `verified_session`,
`set_session_cookie`/`clear_session_cookie`, `issue_csrf_token`/`verify_csrf_token`,
`session_from_request` and `fragment_redirect` in `backend/app/services/session.py`
— "the shared session module" the launch door issues from here and the web door
(E1-09) reuses unchanged. This module tests the parts of it that are pure
functions over a token, a secret and a clock, without opening a database or
building the FastAPI application: `tests/integration/test_lti_launch_door.py`
covers the parts only observable on the wire (the cookie attributes a live
response carries, and the fragment-redirect shape a valid launch produces).

**Every `app.services.session` access below goes through `imported_session_module`**,
matching `tests/unit/test_registration_address_constraints.py`'s convention: a
module that does not exist yet fails each test individually with a clear "no
module named `app.services.session`", rather than one collection error that
hides which of these are worth reading first.

**The interface below is the settled ruling, not an inference** — see
`/tmp/claude-1000/-home-todd-projects-pulse-surveys/5c7ece32-356e-499c-b2a7-7643017a73b6/scratchpad/E1-08-interface-ruling.md`,
sent to this test-author after the first pass: `issue_session`/`verified_session`
take `Door`/`LandingRole` enums and a `bytes` secret; `now` is `int | None`, epoch
seconds, not a `datetime`; the CSRF primitive is `issue_csrf_token`/
`verify_csrf_token`, renamed from this test-author's first-pass guess.
`session_from_request(request, secret)`'s positional shape was confirmed
correct as originally written.

**The two enums moved in E1-13, and how they are reached moved with them.** They
lived in `app.services.landing`, which that ticket deletes: the landing view comes
from the assignment model now, so `Door` and `LandingRole` live in
`app.services.authz` — the module that answers "what may this session act as" —
with their **member names unchanged**, because `verified_session` reads
`Door[...]`/`LandingRole[...]` by member name and every session issued before the
move has to keep verifying. They are resolved inside each test through
`landing_enums()` rather than imported at the top of this file: a module-level
import of a name that has not landed yet takes every test here down as a
collection error, and an uncollected test is not a red test — it reports as a
broken suite rather than as a criterion nobody has met, and the two are fixed by
different people.
"""

import importlib
import time
from typing import Any
from uuid import uuid4

import pytest

# The module E1-13 moves `Door` and `LandingRole` into, spelled once. Its own
# tests are in `tests/unit/test_chosen_landing.py`; all this file needs is the two
# enums, and a rename is this one line.
LANDING_ENUM_MODULE = "app.services.authz"


def landing_enums() -> tuple[Any, Any]:
    """`Door` and `LandingRole`, or a failure naming where E1-13 puts them.

    See the note in this module's docstring on why this is a function rather than
    an import: a missing symbol has to fail the tests that use it, one by one,
    rather than the whole file at collection.
    """
    try:
        module = importlib.import_module(LANDING_ENUM_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{LANDING_ENUM_MODULE}` does not import ({missing}). E0-11 puts the authorization "
            "chokepoint there and E1-13 moves the session's two enums into it."
        )
    door = getattr(module, "Door", None)
    role = getattr(module, "LandingRole", None)
    if door is None or role is None:
        pytest.fail(
            f"`{LANDING_ENUM_MODULE}` exposes `Door`={door!r} and `LandingRole`={role!r}. E1-13's "
            "work order moves both out of the deleted `app/services/landing.py` into the "
            "chokepoint, members unchanged, because a session token carries a door and a role and "
            "`verified_session` reads them back by member name."
        )
    return door, role


# ---------------------------------------------------------------------------
# This module's own choices — none of them a citation of the ruling.
# ---------------------------------------------------------------------------


def a_door() -> Any:
    """The door this module issues its stand-in sessions at."""
    door, _ = landing_enums()
    return door.LAUNCH


def a_role() -> Any:
    """The landing this module issues its stand-in sessions for."""
    _, role = landing_enums()
    return role.STUDENT


def another_role() -> Any:
    """A second landing, for the one test that needs two sessions to differ by role."""
    _, role = landing_enums()
    return role.INSTRUCTOR


# An issuer and a subject this module invents, standing in for a launch's
# `iss`/`sub` — this module's own choice of value, not a claim about what a
# real launch carries.
AN_ISSUER = "https://platform.e1-08-session-unit-tests.invalid"
A_SUBJECT = "e1-08-session-unit-tests-subject"

# Two independent secrets, `bytes` per the ruling, so a "wrong key" test can
# show the two actually differ rather than the same value compared to itself.
CORRECT_SECRET = b"e1-08-session-unit-tests-correct-secret-000000"
WRONG_SECRET = b"e1-08-session-unit-tests-a-different-secret-01"

# The plan's own number (decision 4): "Session lifetime → 60 minutes."
SESSION_LIFETIME_SECONDS = 3600

# A margin comfortably larger than the wall-clock jitter one `issue_session`
# call plus one `verified_session` call can accumulate in this process, and
# comfortably smaller than anything that would make "just inside the window"
# an interesting number the module ought to special-case. Chosen so the pair
# below needs neither `time.sleep` nor a patched clock: `issue_session`'s own
# `now` parameter (epoch seconds, per the ruling) places `exp` this many
# seconds to either side of the real clock at the moment `verified_session`
# reads it.
BOUNDARY_MARGIN_SECONDS = 3


def now_epoch_seconds() -> int:
    """The wall clock, as `issue_session`'s `now` takes it. `verified_session` has no injectable `now`."""
    return int(time.time())


def imported_session_module() -> Any:
    """`app.services.session`, or a failure naming what the ruling says should be there."""
    try:
        import app.services.session as session_module
    except ModuleNotFoundError as missing:
        pytest.fail(
            f"`app.services.session` does not import ({missing}). E1-08's module layout puts the "
            "shared session module there — `backend/app/services/session.py (new)` — with "
            "`issue_session`, `verified_session`, `SessionClaims` and the cookie/CSRF primitives "
            "this test asks for."
        )
    return session_module


def issued(
    module: Any,
    *,
    secret: bytes = CORRECT_SECRET,
    door: Any = None,
    role: Any = None,
    sub: str = A_SUBJECT,
    iss: str | None = AN_ISSUER,
    now: int | None = None,
) -> str:
    """One session token, issued with this module's own stand-in claim values.

    `door` and `role` default to `None` and are resolved here rather than in the
    signature, because a default evaluated at import time would need the two enums
    at import time — which is the collection error this module's docstring
    explains it is avoiding.
    """
    return module.issue_session(
        door=a_door() if door is None else door,
        role=a_role() if role is None else role,
        sub=sub,
        iss=iss,
        secret=secret,
        now=now,
    )


# ---------------------------------------------------------------------------
# `issue_session` / `verified_session` — the round trip.
# ---------------------------------------------------------------------------


def test_a_session_issued_then_verified_carries_back_the_same_claims() -> None:
    """The whole point of the module: what goes in with `issue_session` reads back.

    **Dies if `verified_session` ignores the token and returns some other
    session**, and dies if any one of the five claim values is dropped, swapped
    with another, or silently defaulted — each is checked individually rather
    than compared as a blob, so a mutation touching exactly one field is caught
    by name.
    """
    module = imported_session_module()

    token = issued(module)
    claims = module.verified_session(token, CORRECT_SECRET)

    assert claims is not None, (
        "`verified_session` answered `None` for a token this test just issued with the same "
        "secret. The round trip this module exists for does not hold."
    )
    assert claims.door == a_door(), f"`.door` is {claims.door!r}, not {a_door()!r}."
    assert claims.role == a_role(), f"`.role` is {claims.role!r}, not {a_role()!r}."
    assert claims.sub == A_SUBJECT, f"`.sub` is {claims.sub!r}, not {A_SUBJECT!r}."
    assert claims.iss == AN_ISSUER, f"`.iss` is {claims.iss!r}, not {AN_ISSUER!r}."
    assert claims.jti, "`.jti` is empty. E1-08's `SessionClaims` names a `jti` for every session."
    assert claims.exp - claims.iat == SESSION_LIFETIME_SECONDS, (
        f"`.exp - .iat` is {claims.exp - claims.iat}, not {SESSION_LIFETIME_SECONDS} — the plan's "
        "own decision 4, '60 minutes'."
    )


def test_two_sessions_issued_for_the_same_person_carry_different_jti() -> None:
    """**Dies if `jti` is derived from the claims rather than generated fresh.**

    A `jti` that is a function of `door`/`role`/`sub`/`iss` alone is the same
    value for every session that person ever holds, which is what lets a CSRF
    token minted for a session yesterday still verify against one issued today
    — the exact binding `verify_csrf_token`'s "a token for session A fails
    against session B" is supposed to prevent.
    """
    module = imported_session_module()

    first = module.verified_session(issued(module), CORRECT_SECRET)
    second = module.verified_session(issued(module), CORRECT_SECRET)

    assert first is not None and second is not None, (
        "One of two identically-issued sessions failed to verify, so this test cannot compare "
        "their `jti` values."
    )
    assert first.jti != second.jti, (
        f"Two separate `issue_session` calls for the same door/role/sub/iss both produced `jti` "
        f"{first.jti!r}. A `jti` derived from the claims rather than generated fresh binds no "
        "particular session — which defeats the CSRF primitive's whole purpose."
    )


# ---------------------------------------------------------------------------
# The two refusals: `alg: none`, and the wrong key.
# ---------------------------------------------------------------------------


def test_verified_session_refuses_a_token_re_signed_alg_none() -> None:
    """RFC 7519's unsecured JWT. **Dies if the algorithm is read from the token's own header.**

    Built from a genuinely issued token's own claims, re-encoded with an empty
    third segment and `alg: none` in the header — the RFC 7519 §6 "unsecured
    JWT" shape, and the one every `alg` confusion attack in this repository's
    other suites is posed the same way. A verifier that lets the token's own
    header choose the algorithm accepts this; ADR 0073's closing condition
    ("the algorithm list stays a constant") is the rule this test is the
    session module's half of.
    """
    import base64
    import json

    module = imported_session_module()
    token = issued(module)
    header_b64, claims_b64, _ = token.split(".")

    def padded_b64decode(segment: str) -> bytes:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

    header = json.loads(padded_b64decode(header_b64))
    assert header.get("alg") not in (None, "none"), (
        f"The header of a session this module just issued is {header!r} — it already carries no "
        "algorithm, or `none`, before this test has tampered with anything."
    )
    none_header = base64.urlsafe_b64encode(json.dumps({**header, "alg": "none"}).encode("utf-8"))
    none_token = f"{none_header.rstrip(b'=').decode('ascii')}.{claims_b64}."

    assert module.verified_session(none_token, CORRECT_SECRET) is None, (
        "`verified_session` accepted a token re-signed `alg: none` — an unsecured JWT whose third "
        "segment is empty. This is the classic algorithm-confusion bypass, and it means the "
        "verifier is reading `alg` off the token's own header rather than pinning it."
    )


def test_verified_session_refuses_a_token_signed_with_a_different_secret() -> None:
    """**Dies if the secret is not actually checked.**

    A verifier that decodes without verifying, or that verifies against a
    hardcoded value, both pass a plain round trip and both fail this.
    """
    module = imported_session_module()

    token = issued(module, secret=WRONG_SECRET)

    assert module.verified_session(token, CORRECT_SECRET) is None, (
        f"`verified_session` accepted a token signed with a different secret ({WRONG_SECRET!r} "
        f"rather than {CORRECT_SECRET!r}). Key custody (the plan's decision 1) buys nothing if "
        "the key is never actually checked."
    )


# ---------------------------------------------------------------------------
# Expiry at the boundary. Criterion 4: "tested at the boundary, not just
# 'eventually'." No sleep, no monkeypatch: `issue_session`'s injectable `now`
# (epoch seconds) places `exp` a few real seconds to either side of the real
# clock, and `verified_session` is called immediately, against the real
# clock, on both sides of that line.
# ---------------------------------------------------------------------------


def test_a_session_that_has_not_yet_expired_is_accepted() -> None:
    """Just inside the window — the near miss for the refusal below.

    Without this, a `verified_session` that refused *every* token — or every
    token issued through this helper, for a reason having nothing to do with
    expiry — would make the refusal below look like an expiry check when it is
    not one.
    """
    module = imported_session_module()
    issued_at = now_epoch_seconds() - (SESSION_LIFETIME_SECONDS - BOUNDARY_MARGIN_SECONDS)

    token = issued(module, now=issued_at)

    assert module.verified_session(token, CORRECT_SECRET) is not None, (
        f"A session whose `exp` is still {BOUNDARY_MARGIN_SECONDS}s in the future was refused. "
        "This is the near miss for the expiry refusal below, and without it that refusal could be "
        "`verified_session` refusing everything."
    )


def test_a_session_past_its_expiry_is_refused() -> None:
    """Just outside the window. **Dies if `exp` is never compared to now.**

    The pair to the test above: `issue_session`'s `now` is moved back just far
    enough that `exp` is already a few seconds in the past by the time
    `verified_session` reads the real clock.
    """
    module = imported_session_module()
    issued_at = now_epoch_seconds() - (SESSION_LIFETIME_SECONDS + BOUNDARY_MARGIN_SECONDS)

    token = issued(module, now=issued_at)

    assert module.verified_session(token, CORRECT_SECRET) is None, (
        f"A session whose `exp` is already {BOUNDARY_MARGIN_SECONDS}s in the past was accepted. "
        "The plan's decision 4 gives a session a 60-minute lifetime; without this check that "
        "number is decoration."
    )


# ---------------------------------------------------------------------------
# The CSRF primitive. Criterion 5's second half: where `SameSite=None`
# requires a defence, "the primitive it names exists in the session module
# with its own tests (issue and verify, both directions)". Two pure
# functions, per the ruling: `issue_csrf_token(jti, secret)` and
# `verify_csrf_token(token, jti, secret)`.
# ---------------------------------------------------------------------------


def test_a_csrf_token_verifies_against_the_jti_it_was_issued_for() -> None:
    """Issue, then verify, the ordinary direction."""
    module = imported_session_module()
    jti = str(uuid4())

    token = module.issue_csrf_token(jti, CORRECT_SECRET)
    verified = module.verify_csrf_token(token, jti, CORRECT_SECRET)

    assert verified, (
        f"`verify_csrf_token` refused a token `issue_csrf_token` just minted for its own `jti` "
        f"({jti!r}). This is the ordinary direction the double-submit primitive exists for."
    )


def test_a_csrf_token_for_one_session_fails_against_another_sessions_jti() -> None:
    """The bound half. Criterion 5, spelled exactly: "a token for session A fails
    against session B".

    **Dies if the token is a bare HMAC of the secret alone**, with no `jti`
    bound into it — that shape verifies here just as it did above, because it
    never looked at which session it was minted for.
    """
    module = imported_session_module()
    session_a = str(uuid4())
    session_b = str(uuid4())
    assert session_a != session_b, "Two freshly generated UUIDs collided; nothing to compare."

    token_for_a = module.issue_csrf_token(session_a, CORRECT_SECRET)

    assert not module.verify_csrf_token(token_for_a, session_b, CORRECT_SECRET), (
        f"A CSRF token minted for session {session_a!r} verified against a different session's "
        f"`jti` ({session_b!r}). §2's cross-site defence is exactly this binding: a double-submit "
        "token that verifies for any session is a defence against nothing."
    )


def test_a_csrf_token_signed_with_a_different_secret_is_refused() -> None:
    """The other half of "verified", alongside the `jti` binding above."""
    module = imported_session_module()
    jti = str(uuid4())

    token = module.issue_csrf_token(jti, WRONG_SECRET)

    assert not module.verify_csrf_token(token, jti, CORRECT_SECRET), (
        f"A CSRF token signed with {WRONG_SECRET!r} verified against {CORRECT_SECRET!r}. 'A "
        "tossed cookie without the secret still fails' is the plan's own phrase for this."
    )


# ---------------------------------------------------------------------------
# `session_from_request` — Bearer first, cookie fallback — and "a session
# survives navigation": the same token verifies again on a later call, which
# is what a session that is not single-use looks like from this function's
# own vantage point. Real `starlette.requests.Request` objects, built from a
# minimal ASGI scope, so nothing here depends on a duck-typed guess at what
# the function reads off a request.
# ---------------------------------------------------------------------------


def request_carrying(
    *, bearer: str | None = None, cookie: str | None = None, cookie_name: str = "session"
) -> Any:
    """A real `starlette.requests.Request`, carrying only the headers named."""
    from starlette.requests import Request

    headers: list[tuple[bytes, bytes]] = []
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if cookie is not None:
        headers.append((b"cookie", f"{cookie_name}={cookie}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_session_from_request_reads_a_bearer_only_request() -> None:
    """A request carrying only `Authorization: Bearer <token>`, no cookie at all.

    This is the shape the cookieless path (criterion 2) needs after the SPA has
    captured the session fragment: every later fetch carries the session as a
    Bearer header, never a cookie, inside the third-party iframe.
    """
    module = imported_session_module()
    token = issued(module)

    claims = module.session_from_request(request_carrying(bearer=token), CORRECT_SECRET)

    assert claims is not None and claims.sub == A_SUBJECT, (
        f"`session_from_request` did not read a valid Bearer-only session (got {claims!r}). "
        "Nothing here carries a cookie at all, so a `None` means the Bearer branch itself is "
        "broken, not that the fallback chose correctly."
    )


def test_session_from_request_falls_back_to_the_cookie_when_there_is_no_bearer_header() -> None:
    """A request carrying only the session cookie, no `Authorization` header at all."""
    module = imported_session_module()
    token = issued(module)
    cookie_name = getattr(module, "SESSION_COOKIE", "session")

    claims = module.session_from_request(
        request_carrying(cookie=token, cookie_name=cookie_name), CORRECT_SECRET
    )

    assert claims is not None and claims.sub == A_SUBJECT, (
        f"`session_from_request` did not read a valid cookie-only session (got {claims!r}), under "
        f"cookie name {cookie_name!r}. The plan: `session_from_request` '(Bearer first, cookie "
        "fallback)' — there is no Bearer header here for it to have preferred instead."
    )


def test_session_from_request_prefers_the_bearer_header_over_a_conflicting_cookie() -> None:
    """**Dies if the cookie is read first**, or if the two are merged rather than one chosen.

    A request carrying a *valid* session in the cookie and a *different*
    person's session as the Bearer header must resolve to the Bearer session —
    "Bearer first, cookie fallback" names an order, and an order is only
    observable when the two disagree.
    """
    module = imported_session_module()
    cookie_name = getattr(module, "SESSION_COOKIE", "session")
    bearer_token = issued(module, role=another_role(), sub="e1-08-bearer-subject")
    cookie_token = issued(module, role=a_role(), sub="e1-08-cookie-subject")

    claims = module.session_from_request(
        request_carrying(bearer=bearer_token, cookie=cookie_token, cookie_name=cookie_name),
        CORRECT_SECRET,
    )

    assert claims is not None and claims.sub == "e1-08-bearer-subject", (
        f"A request carrying both a Bearer session and a different cookie session resolved to "
        f"{claims!r}. `session_from_request` is documented Bearer-first; a cookie-first or "
        "merged reading defeats the whole point of trying Bearer before falling back."
    )


def test_the_same_bearer_session_verifies_again_on_a_second_request() -> None:
    """Criterion 4: "a session survives navigation between landing routes".

    Presented to `session_from_request` a second time — modelling a second
    landing route read with the same token — and the session is not single-use:
    unlike a launch nonce, nothing here claims it. **Dies if the function
    mutates state on a successful read** (invalidating the token, consuming a
    single-use record) — the shape that would make a second, perfectly
    ordinary navigation look like a replay.
    """
    module = imported_session_module()
    token = issued(module)

    first = module.session_from_request(request_carrying(bearer=token), CORRECT_SECRET)
    second = module.session_from_request(request_carrying(bearer=token), CORRECT_SECRET)

    assert first is not None and second is not None, (
        f"Presenting the same session token twice answered {first!r} then {second!r}. A session "
        "is read multiple times over its lifetime — every landing route it navigates to — and "
        "reading it is not the single-use operation a launch nonce's claim is."
    )
    assert (first.sub, first.jti) == (second.sub, second.jti), (
        "The same token read twice produced two different identities. Both reads are the same "
        "session and must resolve to the same person."
    )
