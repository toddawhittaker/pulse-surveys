"""E5.1-03 criterion 3 — the dev clock controls refuse a cross-site post, over HTTP.

> `/dev/clock` and `/dev/clock/clear` answer 403 to a cross-origin POST and
> still work from the same origin. Both directions are driven over HTTP
> (entry 47).

The clock pair moves the clock every survey window, term lookup and
live-enrollment check reads in a development stack, and until this ticket it
carried no origin check: any page a developer's browser happened to be showing
could post to it. ADR 0141 accepted that risk by name and named its end — a
ticket about those routes. Ruling R4 of the work order registers both as
`DevControlRoute`s, whose endpoint wrapper already refuses an `Origin` that is
not this application's own with a 403 and lets an absent `Origin` through.

**Why this is driven over HTTP against the built application.**
`docs/MISTAKES.md` entry 47: on the pinned FastAPI, `include_router` rebuilds a
plain route from the endpoint and discards anything a route subclass put
anywhere else, while the subclass stays visible to every sweep that walks the
router. The CSRF sweep and the dev-control inventory read the class; only a
request through the application says whether the gate runs. So every case here
is a POST through `dev_console_tool`, which builds `app.main.create_app()` and
enters its lifespan.

**What each case reads afterwards is the row, not only the status.** A 403 that
moved the clock anyway — a handler that ran and then a check that refused the
response — is the defect a status alone cannot see. The row is read through
`committed_clock_overrides`, which selects the table directly and shares nothing
with the code under test (`docs/MISTAKES.md` entry 19).

**The pairs.** Each refused case has a twin one header apart: the same path,
the same form, carrying this application's own origin, which must answer the
303 back to the console and move the row. A gate that refused every origin
would pass the refusals and fail the twins; a gate that refused nothing would
do the reverse. The third direction — no `Origin` at all, which is not a
forgery vector and must keep working — is
`tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`, whose
requests carry no `Origin` and which must stay green unmodified.

**How a red reads.** The same-origin twins are the controls: an origin check that
refused everything would fail them. Each of the four refusals is red on its
status assertion if the origin check is gone — the route answers 303 to a
cross-site post, and the row moves.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.clock import PRETEND_NOW_COLUMN
from fixtures.dev_console import (
    CROSS_SITE_ORIGIN,
    CROSS_SITE_REFUSED,
    DEV_CLOCK_CLEAR_PATH,
    DEV_CLOCK_SET_PATH,
    OPAQUE_ORIGIN,
    ORIGIN_HEADER,
    redirected_to_the_console,
    same_origin_of,
)

pytestmark = pytest.mark.integration

# The form field `POST /dev/clock` reads, settled by E2-04's work order. Sent on
# every set request, refused or not, so a refusal cannot be a validation error
# about a missing field wearing the wrong number.
PRETEND_NOW_FIELD = "pretend_now"
POSTED_PRETEND_NOW = "2031-03-14T10:30"
POSTED_YEAR = 2031

# The row each case starts from: an override standing at an instant in a
# different year from the posted one, so "the row moved" and "the row did not
# move" are told apart by the year alone, whatever zone the posted wall time is
# read in.
SEEDED_PRETEND_NOW = datetime(2029, 6, 1, 12, 0, tzinfo=UTC)

# The two `Origin` values that are not this application's: a cross-site page,
# and the literal `null` a sandboxed or opaque document sends, which is a
# mismatch and not an absence.
REFUSED_ORIGINS = {"cross-site": CROSS_SITE_ORIGIN, "opaque-null": OPAQUE_ORIGIN}

CLOCK_PATHS = {"set": DEV_CLOCK_SET_PATH, "clear": DEV_CLOCK_CLEAR_PATH}


def form_for(path: str) -> dict[str, str] | None:
    """The form a browser posts to `path`: the pretend now for the set route, nothing to clear."""
    return {PRETEND_NOW_FIELD: POSTED_PRETEND_NOW} if path == DEV_CLOCK_SET_PATH else None


def seed_the_standing_override(overrides: Any) -> None:
    """Put one override row in place, committed, and check it is the one this module seeded."""
    overrides.set(pretend_now=SEEDED_PRETEND_NOW, anchored_at=datetime.now(UTC))
    rows = overrides.rows()
    assert len(rows) == 1 and rows[0][PRETEND_NOW_COLUMN] == SEEDED_PRETEND_NOW, (
        f"Seeding the override left {rows} in `clock_override`, not one row standing at "
        f"{SEEDED_PRETEND_NOW!r}. Every case below reads whether that row moved, so it has to be "
        "there first."
    )


@pytest.mark.parametrize("origin", sorted(REFUSED_ORIGINS))
@pytest.mark.parametrize("control", sorted(CLOCK_PATHS))
def test_a_post_from_another_origin_is_refused_and_leaves_the_clock_where_it_stood(
    control: str, origin: str, dev_console_tool: Any, committed_clock_overrides: Any
) -> None:
    """Criterion 3's refusing half: 403, and the clock row exactly as it was.

    **The mutations it kills:** either clock route left as a plain
    `AnyMethodRoute`, which answers 303 and moves the clock for any page that
    posts to it; the origin check placed on the route object rather than in its
    endpoint, which entry 47 records as discarded at dispatch; and a check
    written as `if origin and origin != ours`, which reads `null` as absent —
    the `opaque-null` rows. **Its near miss** is the same request carrying this
    application's own origin, in the test below, which must not be refused.

    The row is read after the refusal, because a 403 that followed a write is
    the gate running too late, and its status alone would read as a pass.
    """
    path = CLOCK_PATHS[control]
    sent_origin = REFUSED_ORIGINS[origin]
    client = dev_console_tool()
    seed_the_standing_override(committed_clock_overrides)

    answered = client.post(path, data=form_for(path), headers={ORIGIN_HEADER: sent_origin})

    assert answered.status_code == CROSS_SITE_REFUSED, (
        f"`POST {path}` carrying `{ORIGIN_HEADER}: {sent_origin}` answered {answered.status_code} "
        f"in development, not {CROSS_SITE_REFUSED}. E5.1-03 registers the clock pair as "
        "`DevControlRoute`s, whose endpoint refuses an origin that is not this application's own. "
        "A 303 is the clock moved by a page on another site. Body begins "
        f"{answered.text[:300]!r}."
    )
    rows = committed_clock_overrides.rows()
    assert len(rows) == 1 and rows[0][PRETEND_NOW_COLUMN] == SEEDED_PRETEND_NOW, (
        f"After the refused `POST {path}`, `clock_override` holds {rows}; it held one row standing "
        f"at {SEEDED_PRETEND_NOW!r} before. A refusal that wrote first and refused after has moved "
        "the clock anyway."
    )


def test_a_same_origin_post_to_set_the_clock_moves_it(
    dev_console_tool: Any, committed_clock_overrides: Any
) -> None:
    """Criterion 3's working half for `/dev/clock`: this application's own origin sets the row.

    **The mutation it kills:** an origin check that refuses everything, or that
    compares against an address this application never answers on — either
    satisfies every refusal above and deletes the feature. **Its pair** is the
    refusal above with `control=set`.
    """
    client = dev_console_tool()
    seed_the_standing_override(committed_clock_overrides)

    answered = client.post(
        DEV_CLOCK_SET_PATH,
        data=form_for(DEV_CLOCK_SET_PATH),
        headers={ORIGIN_HEADER: same_origin_of(client)},
    )

    redirected_to_the_console(
        answered, f"`POST {DEV_CLOCK_SET_PATH}` carrying this application's own origin"
    )
    rows = committed_clock_overrides.rows()
    assert len(rows) == 1 and rows[0][PRETEND_NOW_COLUMN].year == POSTED_YEAR, (
        f"After a same-origin `POST {DEV_CLOCK_SET_PATH}` of {POSTED_PRETEND_NOW!r}, "
        f"`clock_override` holds {rows}. The control replaces the standing row with the posted "
        "instant; a row still in the seeded year is a redirect that changed nothing."
    )


def test_a_same_origin_post_to_clear_the_clock_clears_it(
    dev_console_tool: Any, committed_clock_overrides: Any
) -> None:
    """Criterion 3's working half for `/dev/clock/clear`: this origin removes the row.

    **The mutation it kills:** the same over-refusing check on the clear route,
    and a clear handler that answers 303 and deletes nothing once the shared
    wrapper is in front of it. **Its pair** is the refusal above with
    `control=clear`.
    """
    client = dev_console_tool()
    seed_the_standing_override(committed_clock_overrides)

    answered = client.post(DEV_CLOCK_CLEAR_PATH, headers={ORIGIN_HEADER: same_origin_of(client)})

    redirected_to_the_console(
        answered, f"`POST {DEV_CLOCK_CLEAR_PATH}` carrying this application's own origin"
    )
    assert committed_clock_overrides.rows() == [], (
        f"After a same-origin `POST {DEV_CLOCK_CLEAR_PATH}`, `clock_override` still holds "
        f"{committed_clock_overrides.rows()}. Clearing removes the row."
    )
