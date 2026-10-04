"""The roster's token grant runs under a bound — E5.1-02, criterion 5.

"The roster's token grant runs under a bound. A token endpoint that accepts the
connection and then stalls fails that section within the bound. Time it against a
stalling stub (entry 41)."

The roster sync built an unbounded `requests.Session`, so a platform whose token
endpoint accepted a connection and never answered held the hourly job on that one
section indefinitely — every section after it waited too. `docs/MISTAKES.md`
entry 41 is the rule: a client library's defaults are written for somewhere else,
and the only evidence a bound holds is a clock read across a call to something
that stalls.

**The stub is a real loopback listener**, because the property is about a socket:
it accepts the connection — so "refused at once" cannot stand in for "bounded" —
and then says nothing. It holds the connection for `STALL_SECONDS` and then closes
it, so on a tree with no bound the sync comes back after that long instead of
hanging the suite; the assertion then fails on the time, as it should.

**Both addresses sit on the loopback listener's host**, the token endpoint and the
section's own roster address, because the fetched-address rules that run under
the development name run only for a host that differs from the section's stored
one (Batch C). A token host that differed would be judged, possibly refused before
any connection, and the test would be about the rules.

**The bound is shortened for the test, through the module constant the work order
settles** (D6: `ROSTER_REQUEST_TIMEOUT`, read from the module at call time), so the
measurement takes about a second. The shipped value is asserted separately: two
finite positive numbers.

**What is asserted is time, the stub's own record, and the call log** — never the
sync's return value, which on a token failure says nothing a test can rely on
(`docs/MISTAKES.md` entry 49).

**How a red reads.** The two tests that need the constant fail at once, naming
it, before any socket is opened, if it is missing. The prompt-answer control is
what says the harness itself adds no delay.
"""

import contextlib
import math
import socket
import threading
import time
from typing import Any

import pytest
from fixtures.roster_sync import (
    AUTH_TOKEN_URL_COLUMNS,
    ROSTER_SYNC_MODULE,
    SECTION_ADDRESS_COLUMN,
    StubResolver,
)
from fixtures.supervision import require_column, require_table, single_primary_key

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The constant the work order (D6) settles, by name.
TIMEOUT_CONSTANT = "ROSTER_REQUEST_TIMEOUT"

# The bound the test runs the sync under: one second to connect, one to read. A
# loopback connect is immediate, so the read half is the one the stall exercises.
SHORT_BOUND = (1.0, 1.0)

# How long the stub holds a connection before closing it. Long enough that a sync
# with no bound is unmistakably late; short enough that the red does not cost the
# suite more than this.
STALL_SECONDS = 15.0

# The window the stalled sync must come back inside: the short bound, plus room
# for a retry or two and for a slow CI machine — and well short of the stall.
WITHIN_SECONDS = 6.0

# The least a stalled call can take if it really waited on the stub: most of the
# read bound. A sync that gave up before connecting comes back faster than this,
# and is not evidence of a bound.
AT_LEAST_SECONDS = 0.8 * SHORT_BOUND[1]

# How fast a prompt answer must come back, for the control.
PROMPT_WITHIN_SECONDS = 3.0

# What the prompt endpoint answers: a token refusal, so the sync ends the section
# at once as a token failure and never goes on to fetch a roster from this host.
PROMPT_BODY = b'{"error": "invalid_client"}'
PROMPT_REFUSAL = (
    b"HTTP/1.1 400 Bad Request\r\n"
    b"Content-Type: application/json\r\n"
    + f"Content-Length: {len(PROMPT_BODY)}\r\n".encode("ascii")
    + b"Connection: close\r\n"
    b"\r\n" + PROMPT_BODY
)


class LoopbackTokenEndpoint:
    """A TCP listener on 127.0.0.1 that either stalls every connection or answers it at once.

    Records how many connections it accepted, which is the half of the evidence
    the clock cannot give: a sync that never connected comes back fast too.
    """

    def __init__(self, *, answer: bytes | None, hold_seconds: float) -> None:
        self.answer = answer
        self.hold_seconds = hold_seconds
        self.accepted = 0
        self._held: list[socket.socket] = []
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(16)
        self._listener.settimeout(0.1)
        self._thread = threading.Thread(target=self._serve, daemon=True)

    @property
    def port(self) -> int:
        return int(self._listener.getsockname()[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _serve(self) -> None:
        deadline = time.monotonic() + self.hold_seconds
        while not self._stop.is_set() and time.monotonic() < deadline:
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.accepted += 1
            if self.answer is None:
                self._held.append(connection)
                continue
            try:
                connection.settimeout(1.0)
                connection.recv(65536)
                connection.sendall(self.answer)
            except OSError:
                pass
            finally:
                connection.close()
        self._release()

    def _release(self) -> None:
        for connection in self._held:
            with contextlib.suppress(OSError):
                connection.close()
        self._held.clear()

    def __enter__(self) -> "LoopbackTokenEndpoint":
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=self.hold_seconds + 2)
        self._release()
        self._listener.close()


def the_sync_module(roster_sync: Any) -> Any:
    """`app.services.roster_sync`, carrying the bound the work order settles, or a failure."""
    module = roster_sync.module
    if not hasattr(module, TIMEOUT_CONSTANT):
        pytest.fail(
            f"`{ROSTER_SYNC_MODULE}` has no `{TIMEOUT_CONSTANT}`. E5.1-02's work order (D6) settles "
            "it as the roster's `(connect, read)` bound — the AGS client's shape — applied to every "
            "request the sync makes that names no timeout of its own, the token grant included, and "
            "read from the module at call time."
        )
    return module


def point_the_section_at(
    section: Any, endpoint: LoopbackTokenEndpoint, committed_rows: Any, metadata_tables: Any
) -> None:
    """Point the section's registration's token endpoint, and its roster address, at the stub."""
    from sqlalchemy import update

    platform = require_table(metadata_tables, "lti_platform")
    platform_key = single_primary_key(platform)
    committed_rows.session.execute(
        update(platform)
        .where(platform.c[platform_key] == section.registration.platform_row[platform_key])
        .values(**{require_column(platform, AUTH_TOKEN_URL_COLUMNS): f"{endpoint.base_url}/token"})
    )
    table = require_table(metadata_tables, "section")
    committed_rows.session.execute(
        update(table)
        .where(table.c[single_primary_key(table)] == section.id)
        .values(**{SECTION_ADDRESS_COLUMN: f"{endpoint.base_url}/lti/memberships"})
    )
    committed_rows.commit()


def timed_sync(roster_sync: Any, section: Any, committed_rows: Any) -> tuple[float, Any]:
    """Run the sync for one section with its own transport; answer the seconds it took and any raise."""
    raised: Any = None
    started = time.perf_counter()
    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=section.id,
            resolve=StubResolver(),
        )
        committed_rows.commit()
    except Exception as failure:  # recorded, and asserted on by the caller
        committed_rows.session.rollback()
        raised = failure
    return time.perf_counter() - started, raised


def test_the_shipped_roster_bound_is_two_finite_positive_numbers(roster_sync: Any) -> None:
    """The bound the sync ships with is a bound: a connect timeout and a read timeout, both finite.

    **The mutations this kills:** `None` (requests' "wait forever"), a single
    number where the shape is a pair, zero (which requests refuses at the call),
    and `math.inf`.
    """
    bound = getattr(the_sync_module(roster_sync), TIMEOUT_CONSTANT)
    assert (
        isinstance(bound, tuple) and len(bound) == 2
    ), f"`{TIMEOUT_CONSTANT}` is {bound!r}; the work order settles a `(connect, read)` pair."
    for name, value in zip(("connect", "read"), bound, strict=True):
        assert (
            isinstance(value, int | float) and math.isfinite(value) and value > 0
        ), f"The {name} half of `{TIMEOUT_CONSTANT}` is {value!r}, which bounds nothing."


def test_a_token_endpoint_that_accepts_and_stalls_fails_the_section_within_the_bound(
    roster_sync: Any,
    synced_section: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 5: a stalled token endpoint costs the section the bound, and no more.

    The stub accepts the connection and never answers. With the bound shortened to
    a second through the module constant, the sync must come back in under
    `WITHIN_SECONDS` — and not before most of a second has passed, which is what
    says it really waited on the stub rather than refusing to connect. The stub
    must have accepted at least one connection, and the section's call log must
    hold a row with a NULL response code: ADR 0129's "never reached the platform",
    which is what a token grant that timed out is.

    **The mutations this kills:** the bound not applied to the token grant (it is
    a POST through the library, not a roster page); the bound applied only to an
    injected session and not to the one the sync builds for itself; the constant
    read once at import rather than at call time; and a timeout that escapes the
    token-failure handling and leaves no record.

    **The pair** is the prompt endpoint below, which is fast on every tree.
    """
    module = the_sync_module(roster_sync)
    monkeypatch.setattr(module, TIMEOUT_CONSTANT, SHORT_BOUND)
    calls_before = {row["id"] for row in roster_rows.calls_for(synced_section.id)}

    with LoopbackTokenEndpoint(answer=None, hold_seconds=STALL_SECONDS) as endpoint:
        point_the_section_at(synced_section, endpoint, committed_rows, metadata_tables)
        elapsed, raised = timed_sync(roster_sync, synced_section, committed_rows)
        accepted = endpoint.accepted

    assert accepted >= 1, (
        f"The stalling token endpoint accepted no connection (the sync took {elapsed:.2f}s), so the "
        "sync never asked it for a token and the time below is not about a stall."
    )
    assert elapsed < WITHIN_SECONDS, (
        f"Against a token endpoint that accepted the connection and never answered, the sync took "
        f"{elapsed:.2f}s with `{TIMEOUT_CONSTANT}` set to {SHORT_BOUND}. The stub closes after "
        f"{STALL_SECONDS:.0f}s, so a figure near that is a token grant with no bound at all."
    )
    assert elapsed >= AT_LEAST_SECONDS, (
        f"The sync came back in {elapsed:.2f}s, faster than the {SHORT_BOUND[1]}s read bound, so it "
        "did not wait on the stalled connection and this is not a measurement of the bound."
    )
    new_calls = [
        row for row in roster_rows.calls_for(synced_section.id) if row["id"] not in calls_before
    ]
    assert any(row.get("response_code") is None for row in new_calls), (
        f"The stalled token grant left the call log {[dict(row) for row in new_calls]}; the work "
        "order (D6) records it as one `nrps_call` row with a NULL response code — a call that "
        "never got an answer — so an operator sees the section failed rather than never synced."
    )
    assert raised is None, (
        f"The stalled token grant escaped the sync as {raised!r}. A token failure ends that one "
        "section; it must not abort the hourly walk over every other section."
    )


def test_a_token_endpoint_that_answers_at_once_is_not_slowed_by_the_harness(
    roster_sync: Any,
    synced_section: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The control for the stall test: the same stub, answering at once, comes back fast.

    If this is slow, the time measured above is the harness's — the listener, the
    resolver, a lookup the sync makes before its first request — and not the
    bound's. It also says the sync reaches the stub at all, through the transport
    it builds for itself. Green on every tree.
    """
    with LoopbackTokenEndpoint(answer=PROMPT_REFUSAL, hold_seconds=STALL_SECONDS) as endpoint:
        point_the_section_at(synced_section, endpoint, committed_rows, metadata_tables)
        elapsed, _raised = timed_sync(roster_sync, synced_section, committed_rows)
        accepted = endpoint.accepted

    assert accepted >= 1, (
        f"The token endpoint accepted no connection (the sync took {elapsed:.2f}s), so the sync "
        "never reached the loopback stub and neither test in this module measures anything."
    )
    assert elapsed < PROMPT_WITHIN_SECONDS, (
        f"A token endpoint that refused at once still cost the sync {elapsed:.2f}s, so something "
        "other than the token grant is slow and the stall test's figure includes it."
    )
