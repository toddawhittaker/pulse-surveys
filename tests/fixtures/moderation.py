"""E6-01 — moderation verdicts, planted through the one writer the ticket settles.

E6-01 makes a comment reachable only once it holds a moderation verdict:
`report_comment` v004 returns a comment only when a `classification` row with
`task = 'MODERATION'` exists for its answer, and never when any of its moderation
verdicts, ever, is threat or self-harm. So every world in this suite that expects
to *see* a comment has to plant a verdict first, and `docs/MISTAKES.md` entry 22
is the shape of what happens otherwise: the day v004 lands, every comment in every
test world disappears.

**One writer, and the worlds go through it.** The work order (decisions 2 and 4)
settles that a moderation verdict is written only by
`public.route_moderation_verdict(answer_id, verdict, prompt_version, model_id)`,
owned by its own NOLOGIN role, and that Python reaches it through exactly one
function: `app.services.moderation.route_verdict(session, answer_id, verdict, *,
prompt_version, model_id)`. Seeds and fixtures pass the named seed provenance
`SEED_PROMPT_VERSION` and `SEED_MODEL_ID`, defined once in that module. So
`plant_verdict` below calls that function with those two constants, and never
inserts a `classification` row itself — the `BEFORE INSERT` trigger the work order
adds (decision 3) would refuse a direct insert anyway, and a fixture that wrote
around the definer would plant a threat verdict with no `threat_case`, which is
the state the trigger exists to make impossible.

**Every guard here is a plain function that fails from a test body** (entry 44):
on a tree where E6-01 is unbuilt, a world that plants a verdict fails naming
`route_verdict` rather than erroring at setup. Where a world is built inside a
fixture (`tests/fixtures/report_api.py::report_door`), that fixture's tests error
at setup instead, which is entry 22's cost and is said in the report that ships
this file.

**The verdict tokens are written out, not read off the enum** (entry 19). They are
ADR 0030's values — the stored token is the enum member's value, lower case, and
self-harm is `self_harm` — and the tests compare what the database holds against
these literals. A set derived from `ModerationVerdict` would agree with any change
to it.

**Nothing here decides an answer.** It writes rows through the product's own
writer and reads rows back on the bootstrap connection; every expectation is the
test's (`docs/MISTAKES.md` entry 30).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# The interface E6-01's work order settles, spelled once.
# ---------------------------------------------------------------------------

MODERATION_SERVICE_MODULE = "app.services.moderation"
ROUTE_VERDICT = "route_verdict"
# E6-01's fix round: the refusal `route_verdict` raises for a comment whose survey
# window has not closed by the app clock. A `ValueError` subclass.
MODERATION_BEFORE_CLOSE = "ModerationBeforeClose"
SEED_PROMPT_VERSION_NAME = "SEED_PROMPT_VERSION"
SEED_MODEL_ID_NAME = "SEED_MODEL_ID"

# The value both constants hold. Work order decision 4: `SEED_PROMPT_VERSION =
# "seed"` and `SEED_MODEL_ID = "seed"`, "a prompt version that says it is a seed,
# never a real one". Written here so a test can assert the stored provenance against
# the decision rather than against the constant it is checking.
SEED_PROVENANCE = "seed"

CONTRACTS_MODULE = "app.ai.contracts"
VERDICT_ENUM = "ModerationVerdict"

# The definer, its owner, and the trigger's subject.
ROUTING_FUNCTION = "route_moderation_verdict"
ROUTING_CALL = (
    f"SELECT public.{ROUTING_FUNCTION}("
    "CAST(:answer_id AS uuid), CAST(:verdict AS text), "
    "CAST(:prompt_version AS text), CAST(:model_id AS text))"
)
ROUTING_ARGUMENT_TYPES = ["uuid", "text", "text", "text"]
MODERATION_DEFINER_ROLE = "pulse_moderation_definer"

# `classification.task`'s two tokens. `COMMENT_VALIDITY` is E2's
# (`tests/fixtures/grading.py`); `MODERATION` is the work order's decision 1.
MODERATION_TASK = "MODERATION"
VALIDITY_TASK = "COMMENT_VALIDITY"

# The tables E6-01 creates or writes, and the columns the tests read.
CLASSIFICATION_TABLE = "classification"
MODERATION_STATE_TABLE = "moderation_state"
THREAT_CASE_TABLE = "threat_case"
MODERATION_ATTEMPT_TABLE = "moderation_attempt"
SEQUENCE_COLUMN = "sequence"
ANSWER_ID_COLUMN = "answer_id"
ATTEMPTED_AT_COLUMN = "attempted_at"

# ADR 0030's six moderation tokens, as stored.
CLEAR = "clear"
HARMFUL = "harmful"
PRIVACY = "privacy"
NONSENSE = "nonsense"
THREAT = "threat"
SELF_HARM = "self_harm"
EVERY_VERDICT = (CLEAR, HARMFUL, PRIVACY, NONSENSE, THREAT, SELF_HARM)

# The three routes the work order's decision 2 gives them.
CARE_CLASS = (THREAT, SELF_HARM)
FLAGGING = (HARMFUL, PRIVACY)
QUIET = (CLEAR, NONSENSE)

# The `moderation_state` token a flagging verdict writes (decision 2), in E4-02's
# stored spelling (`tests/integration/test_report_schema.py`).
FLAGGED_COLLAPSED = "FLAGGED_COLLAPSED"

# Validity tokens (SPEC §3.3), for the per-task check: a validity verdict that is
# not also a moderation verdict, and the reverse. `nonsense` is in both sets and is
# deliberately never used as a crossing case.
SUBSTANTIVE = "substantive"

# What a world passes to say "plant no verdict at all" for one comment.
UNMODERATED = None

ROUTE_VERDICT_IS_OWED = (
    "E6-01's work order (decision 4) puts one Python call to the routing definer in "
    f"`backend/app/services/moderation.py`: `{ROUTE_VERDICT}(session, answer_id, verdict: "
    "ModerationVerdict, *, prompt_version: str, model_id: str) -> UUID`, beside the two seed "
    f"provenance constants `{SEED_PROMPT_VERSION_NAME}` and `{SEED_MODEL_ID_NAME}` (both "
    f"{SEED_PROVENANCE!r}). Every fixture, seed and e2e world plants its verdicts through it."
)


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


def moderation_service() -> Any:
    """`app.services.moderation`, or a failure naming what owes it."""
    try:
        return import_module(MODERATION_SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == MODERATION_SERVICE_MODULE
            or MODERATION_SERVICE_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(f"`{MODERATION_SERVICE_MODULE}` does not exist. {ROUTE_VERDICT_IS_OWED}")


def named_in_moderation(name: str) -> Any:
    """One name off the moderation service, or a failure quoting what owes it."""
    module = moderation_service()
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{MODERATION_SERVICE_MODULE}` exposes no `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n"
            f"{ROUTE_VERDICT_IS_OWED}"
        )
    return found


def verdict_member(token: str) -> Any:
    """The `ModerationVerdict` member whose stored value is `token` (ADR 0030)."""
    module = import_module(CONTRACTS_MODULE)
    enum = getattr(module, VERDICT_ENUM, None)
    if enum is None:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{CONTRACTS_MODULE}` exposes no `{VERDICT_ENUM}`. E0-12 ships it with six members "
            "(ADR 0030), and E6-01's definer stores their values."
        )
    try:
        return enum(token)
    except ValueError:  # pragma: no cover - a broken test, not a red
        pytest.fail(
            f"`{VERDICT_ENUM}` has no member whose value is {token!r}; its values are "
            f"{sorted(member.value for member in enum)}. ADR 0030 settles the six stored tokens, "
            "and this file transcribes them."
        )


def plant_verdict(session: Any, answer_id: Any, token: str) -> Any:
    """Route one moderation verdict for one answer through the product's own writer.

    Flushed first, so the answer row the verdict names is visible to the
    definer's insert on the same transaction. Answers what `route_verdict`
    returned (the new classification's id); no test treats that value as
    evidence of anything (`docs/MISTAKES.md` entry 49) — they read the rows.
    """
    route = named_in_moderation(ROUTE_VERDICT)
    prompt_version = named_in_moderation(SEED_PROMPT_VERSION_NAME)
    model_id = named_in_moderation(SEED_MODEL_ID_NAME)
    session.flush()
    return route(
        session,
        answer_id,
        verdict_member(token),
        prompt_version=prompt_version,
        model_id=model_id,
    )


def the_clock_reads(session: Any) -> datetime:
    """The instant the product's clock would answer on `session`, as near as a fixture can say.

    **A scheduling aid, never an expectation.** Since E6-01's fix round,
    `route_verdict` refuses an answer whose survey window has not closed by
    `app.services.clock.now()` (ADR 0109), so a world must not route a verdict
    before its window's close by that clock. ADR 0109's development override is an
    offset — `pretend_now + (real now - anchored_at)` — read off the one
    `clock_override` row; with no row, the clock is the real one. This reads the
    row on the caller's own session, which is the session the planting will run
    on. It is read a moment *before* the product reads it, and the clock only moves
    forward, so a window this calls closed the product calls closed too.
    """
    real = datetime.now(UTC)
    row = session.execute(
        text("SELECT pretend_now, anchored_at FROM public.clock_override LIMIT 1")
    ).first()
    if row is None:
        return real
    return row[0] + (real - row[1])


class PendingVerdicts:
    """Verdicts a world owes comments whose windows had not closed when they were written.

    E6-01's fix round: `route_verdict` refuses a comment whose window is still
    open, because an answer is revised in place on resubmission (ADR 0115) and a
    verdict written before the close would vouch for text the student could still
    replace. So a world routes a comment's verdict at once when its window has
    closed by the clock, and otherwise holds it here until the test moves the
    clock past the close (`route_the_closed`), which is when moderation would run
    (SPEC §7.4: at window close).

    **Strictly after the close, since E6-03 (its work order's decision 8).** The
    window is open at its `closes_at` instant itself — `survey_windows.py` reads
    `closes_at >= instant` as open — and `route_verdict` now refuses that instant
    too, so a verdict is routed here only once the clock has passed it.
    """

    def __init__(self) -> None:
        self.waiting: list[tuple[Any, Any, datetime]] = []

    def route_when_closed(
        self, session: Any, answer_id: Any, tokens: Any, closes_at: datetime
    ) -> None:
        if tokens is None:
            return
        if closes_at < the_clock_reads(session):
            plant_verdicts(session, answer_id, tokens)
        else:
            self.waiting.append((answer_id, tokens, closes_at))

    def route_the_closed(self, session: Any) -> None:
        still_open: list[tuple[Any, Any, datetime]] = []
        for answer_id, tokens, closes_at in self.waiting:
            if closes_at < the_clock_reads(session):
                plant_verdicts(session, answer_id, tokens)
            else:
                still_open.append((answer_id, tokens, closes_at))
        self.waiting = still_open


def plant_verdicts(session: Any, answer_id: Any, tokens: tuple[str, ...] | str | None) -> None:
    """Plant nothing, one verdict, or a sequence of verdicts in order, for one answer.

    A tuple is the "a later verdict on the same comment" case of E6-01's second
    criterion: each token is routed as its own call, in the order given.
    """
    if tokens is None:
        return
    for token in (tokens,) if isinstance(tokens, str) else tokens:
        plant_verdict(session, answer_id, token)


# ---------------------------------------------------------------------------
# Schema guards, called as a test's first statement (entry 44).
# ---------------------------------------------------------------------------


def require_table(tables: Mapping[str, Any], name: str, owed: str) -> Any:
    """One table off `Base.metadata`, or a failure naming the deliverable."""
    table = tables.get(name)
    if table is None:
        pytest.fail(f"There is no `{name}` table (what is there: {sorted(tables)}). {owed}")
    return table


THREAT_CASE_IS_OWED = (
    "E6-01 adds `backend/app/models/safety.py` with `threat_case` (`answer_id` unique, "
    "`classification_id`, `opened_at`) in the `models/report.py` style: the opening row the "
    "routing definer writes for a threat or self-harm verdict."
)
MODERATION_ATTEMPT_IS_OWED = (
    "E6-01 creates `moderation_attempt` in `backend/app/models/ai.py` (`answer_id` with "
    "`RESTRICT`, `attempted_at`): one append-only row per failed moderation call, which E6-02's "
    "attempt cap counts."
)
SEQUENCE_IS_OWED = (
    "E6-01 adds `moderation_state.sequence`, an identity column that orders the rows, and "
    "`reported_status_of` orders by it (work order decision 9)."
)


def require_threat_case(tables: Mapping[str, Any]) -> Any:
    return require_table(tables, THREAT_CASE_TABLE, THREAT_CASE_IS_OWED)


def require_moderation_attempt(tables: Mapping[str, Any]) -> Any:
    return require_table(tables, MODERATION_ATTEMPT_TABLE, MODERATION_ATTEMPT_IS_OWED)


def require_sequence(tables: Mapping[str, Any]) -> Any:
    table = require_table(tables, MODERATION_STATE_TABLE, SEQUENCE_IS_OWED)
    if SEQUENCE_COLUMN not in table.c:
        pytest.fail(
            f"`{MODERATION_STATE_TABLE}` declares no `{SEQUENCE_COLUMN}`; it declares "
            f"{[column.name for column in table.columns]}. {SEQUENCE_IS_OWED}"
        )
    return table


def require_routing_function(session: Any) -> None:
    """The definer exists in `public`, or a failure naming it."""
    found = session.execute(
        text(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = :name"
        ),
        {"name": ROUTING_FUNCTION},
    ).scalar_one()
    if not found:
        pytest.fail(
            f"There is no `public.{ROUTING_FUNCTION}` function. E6-01 ships it in "
            "`backend/app/views_sql/moderation_routing_v001.sql`: a `SECURITY DEFINER` owned by the "
            f"NOLOGIN role `{MODERATION_DEFINER_ROLE}`, taking `(answer_id uuid, verdict text, "
            "prompt_version text, model_id text)` and returning the new classification's id. One "
            "call writes the verdict and its route together."
        )


def require_definer_role(session: Any) -> None:
    """The definer's owner exists, or a failure naming it."""
    present = session.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": MODERATION_DEFINER_ROLE}
    ).scalar_one_or_none()
    if present is None:
        pytest.fail(
            f"There is no `{MODERATION_DEFINER_ROLE}` role. E6-01's work order (decision 2) gives the "
            "routing definer a NOLOGIN owner of its own, the `teaching_grant_end_v001.sql` pattern "
            "(ADR 0043)."
        )


# ---------------------------------------------------------------------------
# Reading the rows back, on whatever connection the caller holds.
# ---------------------------------------------------------------------------


def moderation_verdicts(session: Any, answer_id: Any) -> list[dict[str, Any]]:
    """Every `MODERATION` classification row for one answer."""
    session.flush()
    return [
        dict(row)
        for row in session.execute(
            text(
                "SELECT * FROM public.classification "
                "WHERE answer_id = CAST(:answer AS uuid) AND task = :task"
            ),
            {"answer": str(answer_id), "task": MODERATION_TASK},
        ).mappings()
    ]


def threat_cases(session: Any, answer_id: Any) -> list[dict[str, Any]]:
    """Every `threat_case` row for one answer."""
    session.flush()
    return [
        dict(row)
        for row in session.execute(
            text("SELECT * FROM public.threat_case WHERE answer_id = CAST(:answer AS uuid)"),
            {"answer": str(answer_id)},
        ).mappings()
    ]


def moderation_states(session: Any, answer_id: Any) -> list[dict[str, Any]]:
    """Every `moderation_state` row for one answer."""
    session.flush()
    return [
        dict(row)
        for row in session.execute(
            text("SELECT * FROM public.moderation_state WHERE answer_id = CAST(:answer AS uuid)"),
            {"answer": str(answer_id)},
        ).mappings()
    ]
