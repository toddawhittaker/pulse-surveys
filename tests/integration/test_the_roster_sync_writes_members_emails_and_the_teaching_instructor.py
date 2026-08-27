"""Who a roster member becomes in Pulse — E1-11, criterion 6 and decisions D5, D6, D7.

Three writes and one refusal, and the refusal is the interesting one.

**A member becomes a `user` row and nothing more** (D6). The match is
`(lti_platform_id, lms_user_id)` through `public.resolve_platform_user`, the
definer function ADR 0094 ships, because `pulse_app` holds no read on
`user.lms_user_id` at all — E1-10's round-3 review revoked it, on the ground that
a connection able to read it "can enumerate every subject that ever launched and
join a response back to the person who gave it". What that means here is that
matching and enumerating are different privileges and this sync only has the
first.

**An email is written through `record_roster_email` and a name never is** (D7,
ADR 0050). NRPS carries no name in this mock and the sync must not invent
somewhere to put one; `user_identity.identity_name` becomes nullable in this
ticket for exactly that reason, and the sync writing it would be Pulse inventing
identity from a roster.

**The teaching instructor's assignment is written only where a `person` already
exists** (D5). An `INSTRUCTOR` `role_assignment` is a purview grant — SPEC §2.1
computes purview from these rows — so writing one is handing somebody oversight of
a section, with the moderation view and the report that hang off it. The sync
never creates the `person` it would be granted to: that graph is Pulse's (ADR
0024), `identity_name` is NOT NULL on it, and NRPS carries no name to fill it
with. So a roster instructor nobody has entered as a person gets no assignment and
a logged skip.

**And criterion 6, which is the one `docs/MISTAKES.md` entry 31 is about**:
running the sync twice against an unchanged roster changes no row — proved against
a database the sync did not itself fill.

**The environment** is `configured_env`'s documented values over the container's
database coordinates, laid down by `tool_doors` inside `roster_platforms`
(`docs/MISTAKES.md` entry 40).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# A member's address, in a domain RFC 2606 reserves so that nothing here could
# ever be delivered to. E1-11 stores addresses and sends nothing (SPEC §12 is
# E12's); these exist to be compared against.
AN_ADDRESS = "roster-member@pulse-tests.invalid"
ANOTHER_ADDRESS = "roster-member-renamed@pulse-tests.invalid"

# A name this suite writes onto an identity row **before** a sync runs, so that
# "the sync never writes `identity_name`" is asserted against a value that would
# visibly change. A sync that overwrote it with an empty string, or with the
# member's email, or with `None`, is caught by comparing against this.
A_NAME_PULSE_ALREADY_HELD = "A Name Only Pulse Knows"

WEEKS_AGO = 3


def a_window(days_ago: int) -> str:
    """An RFC 3339 timestamp with a non-zero offset, `days_ago` days back."""
    moment = datetime.now(UTC) - timedelta(days=days_ago)
    return f"{moment.date().isoformat()}T09:30:00-04:00"


@pytest.fixture
def run_a_sync(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
) -> Any:
    """Serve one membership container at the section's address and sync it."""

    def run(members: Any, size: int = 5) -> None:
        service_wire.serve(compose_a_roster(synced_section, members, size))
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=synced_section.id,
            http=service_wire.session(),
        )
        committed_rows.commit()

    return run


def instructor_assignments(committed_rows: Any, roster_rows: Any, section_id: Any) -> list[Any]:
    """Every `INSTRUCTOR` assignment scoped to this section.

    The scope columns come from `SupervisionGraph`, which discovers how this schema
    records "scoped to a section" rather than naming it — E0-09 left three shapes
    open and `tests/fixtures/supervision.py` explains why guessing here would make
    every test in this module fail inside its own setup.
    """
    graph = committed_rows.graph
    scope = graph.scope_overrides("section", section_id)
    instructor = graph.role_value("INSTRUCTOR")
    return [
        row
        for row in roster_rows.assignments()
        if row.get(graph.role_column) == instructor
        and all(row.get(name) == value for name, value in scope.items())
    ]


def test_an_unknown_member_gets_a_user_row_and_a_known_one_is_matched_rather_than_duplicated(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """Decision D6, in both directions, against a `user` row the sync did not write.

    "The sync resolves members via `public.resolve_platform_user(...)`; unknown
    members get a `user` row written first (guard_write, insert-tolerant like
    provisioning's `_tolerating_a_row_that_is_already_there`), then resolved."

    **The mutation this kills**: a sync that inserts a `user` row for every member
    it reads. Postgres would refuse the duplicate if a unique constraint on
    `(lti_platform_id, lms_user_id)` exists and would quietly double the table if
    one does not — and either way SPEC §4 keys every response to that row, so a
    second row for one subject splits a student's history in half.

    **The near miss beside it** is the genuinely new member: a sync that resolved
    everybody and inserted nobody would satisfy the "not duplicated" half and would
    ingest an empty class on a section's first sync.

    The known member's row is seeded out of band — the same database the sync did
    not fill that criterion 6 requires, one test below.
    """
    known = a_subject("known")
    unknown = a_subject("unknown")
    seeded = seed_a_member(
        synced_section,
        known,
        started_on=(datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date(),
    )
    before = len(roster_rows.users())

    run_a_sync([roster_contract.member(known), roster_contract.member(unknown)])

    key = roster_rows.key("user")
    matched = roster_rows.user_for(known)
    assert matched is not None and matched[key] == seeded["user"][key], (
        f"The member {known!r} already had a `user` row ({seeded['user'][key]}) and after the sync "
        f"the row carrying that subject is {matched and matched[key]}. A sync that inserts rather "
        "than resolves gives one subject two rows, and SPEC §4 keys every response to that "
        "subject — so half of a student's term goes to one row and half to the other."
    )
    assert roster_rows.user_for(unknown) is not None, (
        f"The member {unknown!r} is new to this deployment and no `user` row was written for them, "
        "so nothing could be enrolled. D6: 'unknown members get a `user` row written first … then "
        "resolved.'"
    )
    assert len(roster_rows.users()) == before + 1, (
        f"The roster carried two members, one of them already known, and the `user` table grew by "
        f"{len(roster_rows.users()) - before}. Exactly one of them was new."
    )


def test_a_member_who_exposes_an_email_gets_one_and_a_member_who_exposes_none_gets_no_identity_row(
    run_a_sync: Any, roster_rows: Any, roster_contract: Any, a_subject: Any
) -> None:
    """Decision D7 and ADR 0050, both directions in one container.

    "Emails are written only through … `public.record_roster_email` … A member
    exposing no email: no `user_identity` row is created (absence is the honest
    state)."

    **The mutation this kills**: a sync that creates a `user_identity` row for
    every member it writes a `user` for, with a null email. That row is not
    harmless bookkeeping — `user_identity` is the table §4.1's whole grant model is
    built around, and a row per member turns "this deployment holds an address for
    nobody" into "this deployment holds a record for everybody, empty".

    **The near miss**: a sync that writes no identity row at all, which satisfies
    the absence half and loses every address the platform exposed. Both members are
    in one container so neither answer can be given twice.

    The name is asserted absent as well, because ADR 0050 is the record that makes
    this ticket's identity write an *email* write: "the mock roster exposes an
    address and no name", and a sync that filled `identity_name` with anything —
    the email, the subject, an empty string — would be Pulse inventing identity
    from a roster.
    """
    exposed = a_subject("emailed")
    withheld = a_subject("unemailed")

    run_a_sync(
        [
            roster_contract.member(exposed, email=AN_ADDRESS),
            roster_contract.member(withheld),
        ]
    )

    stored = roster_rows.identity_for(exposed)
    assert stored is not None, (
        f"The roster exposed {AN_ADDRESS!r} for {exposed!r} and no `user_identity` row holds it. "
        "E1-11's scope: 'emails stored where exposed (ADR 0050's fields and no more)'."
    )
    assert stored[roster_contract.identity_email_column] == AN_ADDRESS, (
        f"The row carries `{roster_contract.identity_email_column}` "
        f"{stored[roster_contract.identity_email_column]!r} and the roster sent {AN_ADDRESS!r}."
    )
    assert stored[roster_contract.identity_name_column] is None, (
        f"The row carries `{roster_contract.identity_name_column}` "
        f"{stored[roster_contract.identity_name_column]!r}. NRPS carries no name here (ADR 0050) "
        "and D7 makes this ticket's writer one that 'never writes `identity_name`' — a value in "
        "that column is a name this deployment invented, and every §4.1 rule about names now "
        "applies to it."
    )
    assert roster_rows.identity_for(withheld) is None, (
        f"The member {withheld!r} exposed no email and a `user_identity` row exists for them "
        f"anyway: {dict(roster_rows.identity_for(withheld) or {})}. D7: 'A member exposing no "
        "email: no `user_identity` row is created (absence is the honest state).'"
    )


def test_an_email_that_disappears_from_the_roster_is_nulled_and_a_name_beside_it_is_untouched(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    committed_rows: Any,
) -> None:
    """The rest of D7: the update path, and the column it may not touch.

    "An email that disappears from the roster nulls the field." A platform that
    stops exposing addresses — a setting an administrator can change — must not
    leave Pulse holding an address it is no longer told about.

    **The identity row is seeded with a name this suite chose**, and that is the
    load-bearing part of the test rather than scenery. D7's function body is an
    `INSERT … ON CONFLICT (user_id) DO UPDATE`, and the natural way to write one is
    to set every column in the row; a body that did would erase a name a person
    entered through §6.3's People editor every time an hourly sync ran, and nothing
    else in this suite would notice. So the name is written first, by hand, and
    required to survive.

    **The mutation this kills**: `DO UPDATE SET identity_email = …, identity_name =
    excluded.identity_name`, and its sibling that lists the columns positionally.
    """
    subject = a_subject("renamed")
    seeded = seed_a_member(
        synced_section,
        subject,
        started_on=(datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date(),
    )
    committed_rows.seed(
        "user_identity",
        dict(synced_section.chain),
        **{
            roster_rows.link("user_identity", "user"): seeded["user"][roster_rows.key("user")],
            roster_contract.identity_name_column: A_NAME_PULSE_ALREADY_HELD,
            roster_contract.identity_email_column: ANOTHER_ADDRESS,
        },
    )
    committed_rows.commit()

    run_a_sync([roster_contract.member(subject, email=AN_ADDRESS)])
    updated = roster_rows.identity_for(subject)
    assert updated is not None and updated[roster_contract.identity_email_column] == AN_ADDRESS, (
        f"The roster exposed {AN_ADDRESS!r} and the stored row carries "
        f"{updated and updated[roster_contract.identity_email_column]!r}. An address the platform "
        "changed has to reach the row that already exists, which is what D7's "
        "`ON CONFLICT (user_id) DO UPDATE` is for."
    )
    assert updated[roster_contract.identity_name_column] == A_NAME_PULSE_ALREADY_HELD, (
        f"The identity row's `{roster_contract.identity_name_column}` was "
        f"{A_NAME_PULSE_ALREADY_HELD!r} before the sync and is "
        f"{updated[roster_contract.identity_name_column]!r} after it. The sync writes an email and "
        "nothing else (D7); a name it overwrote is one somebody entered on purpose, gone on the "
        "hour."
    )

    run_a_sync([roster_contract.member(subject)])
    cleared = roster_rows.identity_for(subject)
    assert cleared is not None and cleared[roster_contract.identity_email_column] is None, (
        f"The member stopped exposing an address and the stored row still carries "
        f"{cleared and cleared[roster_contract.identity_email_column]!r}. D7: 'an email that "
        "disappears from the roster nulls the field' — a platform that stops exposing addresses is "
        "a deployment that has withdrawn them, and Pulse holding one it is no longer told about is "
        "identity nobody can account for."
    )
    assert (
        cleared[roster_contract.identity_name_column] == A_NAME_PULSE_ALREADY_HELD
    ), "Clearing the email took the name with it."


def test_the_teaching_instructor_is_assigned_only_where_the_member_resolves_to_a_person(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    committed_rows: Any,
) -> None:
    """Decision D5, both directions, with the two instructors in one container.

    "The sync writes the INSTRUCTOR `role_assignment` (scope grain `section`,
    `reports_to` NULL) only when the member's `user` row resolves to a `person`
    (via `public.resolve_person_for_user`). No person → no assignment, and the skip
    is logged; the sync never creates `person` rows."

    **Why the refusing half is the one that matters.** An `INSTRUCTOR` assignment
    is a purview grant: SPEC §2.1 computes purview from exactly these rows, so the
    row hands somebody the section's moderation view and its report. A sync that
    created the `person` it needed would let a platform's roster mint an
    identity-bearing row in Pulse's own graph — `person.identity_name` is NOT NULL
    and NRPS carries no name (ADR 0050), so whatever filled it would be invented.

    **The mutation the permitting half kills**: a sync that writes no assignment at
    all, which no denial test can see and which leaves every instructor without the
    report the product exists to send them.

    `reports_to` is asserted NULL because ADR 0044 and SPEC §2.1 put the
    supervision edge outside E1 — "INSTRUCTOR assignments join the graph with no
    `reports_to` edge in E1; edges are E9's admin surface" — and an edge invented
    here would be a supervision claim nobody made.

    The `person` count is asserted unchanged, which is the assertion that catches
    the tempting repair: creating the missing person so the assignment can be
    written.
    """
    with_person = a_subject("instructor-known")
    without_person = a_subject("instructor-unknown")
    first_seen = (datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date()
    seeded = seed_a_member(synced_section, with_person, started_on=first_seen)
    seed_a_member(synced_section, without_person, started_on=first_seen)
    committed_rows.seed(
        "person",
        dict(synced_section.chain),
        **{roster_rows.link("person", "user"): seeded["user"][roster_rows.key("user")]},
    )
    committed_rows.commit()
    people_before = len(roster_rows.all_of("person"))

    run_a_sync(
        [
            roster_contract.member(with_person, roles=[roster_contract.instructor_role_urn]),
            roster_contract.member(without_person, roles=[roster_contract.instructor_role_urn]),
        ]
    )

    graph = committed_rows.graph
    written = instructor_assignments(committed_rows, roster_rows, synced_section.id)
    people = roster_rows.all_of("person")
    linked = {
        row[roster_rows.key("person")]
        for row in people
        if row.get(roster_rows.link("person", "user")) == seeded["user"][roster_rows.key("user")]
    }
    holders = {row[graph.person_column] for row in written}

    assert holders == linked, (
        f"The section's `INSTRUCTOR` assignments are held by {sorted(holders)} and the only roster "
        f"instructor whose `user` row resolves to a `person` is {sorted(linked)}. An assignment "
        "for the instructor with no person is a purview grant to a row the sync invented; no "
        "assignment for the one with a person leaves a real instructor without the section's "
        "report and moderation view."
    )
    assert all(row.get(graph.reports_to_column) is None for row in written), (
        f"An assignment the sync wrote carries a `{graph.reports_to_column}` edge: "
        f"{[dict(row) for row in written]}. SPEC §2.1 and ADR 0044 keep supervision edges out of "
        "E1 — they are E9's admin surface — so an edge here is a supervision claim no human made."
    )
    assert len(people) == people_before, (
        f"The `person` table grew from {people_before} to {len(people)} rows during a roster sync. "
        "That graph is Pulse's (ADR 0024) and `identity_name` on it is NOT NULL while NRPS carries "
        "no name (ADR 0050), so a person created here holds a name this deployment invented."
    )


def test_running_the_sync_twice_against_an_unchanged_roster_changes_no_row(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """Criterion 6, against a database the sync did not fill — `docs/MISTAKES.md` entry 31.

    "Idempotence: running the sync twice against an unchanged roster changes no row
    (MISTAKES entry 31: prove it against a database the sync did not itself fill —
    seed one member out-of-band first)."

    That entry's incident is the whole design of this test: a loader tested only
    against its own output matches the rows it wrote by whatever key it wrote them
    with, and meets a row somebody else wrote — with a different key shape, a
    different null, a different case — as something new. Every database this sync
    runs against after the first hour is a database somebody else filled, including
    its own previous self.

    **Row identity, not counts.** A sync that deleted an enrollment and re-inserted
    it has changed the row that E3's participation history hangs off while leaving
    every count identical.

    **`nrps_call` is deliberately excluded from the comparison**, and saying so is
    part of the assertion rather than an escape: D9 makes it one row per HTTP call,
    which is the point of it — the second run *must* add rows there, and a sync
    that did not would have skipped the call. It is asserted to have grown, so the
    exclusion cannot hide a second run that never happened.
    """
    seeded = a_subject("already-there")
    fresh = a_subject("first-seen")
    start = a_window(WEEKS_AGO * 7)
    seed_a_member(
        synced_section,
        seeded,
        started_on=(datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date(),
    )
    roster = [
        roster_contract.member(
            seeded, window=roster_contract.window(start, None), email=AN_ADDRESS
        ),
        roster_contract.member(fresh, window=roster_contract.window(start, None)),
    ]

    run_a_sync(roster)
    watched = ("enrollment", "user", "user_identity", "role_assignment")
    before = {name: sorted(map(dict, roster_rows.all_of(name)), key=repr) for name in watched}
    calls_before = len(roster_rows.calls_for(synced_section.id))

    assert before["enrollment"] and before["user"], (
        "The first run wrote no enrollment and no user, so the comparison below is between two "
        "empty tables and would hold for a sync that does nothing at all."
    )

    run_a_sync(roster)
    after = {name: sorted(map(dict, roster_rows.all_of(name)), key=repr) for name in watched}

    changed = {name: (before[name], after[name]) for name in watched if before[name] != after[name]}
    assert not changed, (
        "A second sync against an unchanged roster changed rows in "
        f"{sorted(changed)}:\n"
        + "\n".join(
            f"  {name}\n    before: {was}\n    after:  {now}"
            for name, (was, now) in changed.items()
        )
        + "\n\nOne of the two members was seeded out of band before the first sync ever ran, which "
        "is `docs/MISTAKES.md` entry 31's requirement: a sync that matches only the rows it wrote "
        "itself is idempotent against its own output and duplicates everything it meets in a "
        "database somebody else filled — which is every database it will ever run against."
    )
    assert len(roster_rows.calls_for(synced_section.id)) > calls_before, (
        "The second run left no new `nrps_call` row, so it did not call the service at all and "
        "this test compared a database against itself. D9 makes that record one row per HTTP call."
    )
