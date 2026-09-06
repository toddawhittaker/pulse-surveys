"""SPEC §3.4's line item, created on the first staff launch — ticket E3-05.

> One AGS line item per section: **"Pulse Participation"**, created by the tool on
> first launch.

That sentence is the whole of this module's subject, and E3-05 is the ticket that
wires it to the door. The trigger rule is SPEC §7.3's, borrowed whole: "A launch
by an instructor triggers a roster sync; a launch by a leadership role triggers
one only inside the launcher's own purview (§2.1) — an out-of-purview leadership
launch records a `context_outside_purview` defect and binds nothing … A
**student** launch triggers nothing." The ticket makes the student half a
requirement rather than a default: "a student launch must never cause a write to
the platform's gradebook."

**Every assertion here is against the mock platform's own container**, never
against a task that was or was not enqueued. Criterion 2 says so in as many
words — "asserted against the mock's line-item container being empty afterwards,
not merely against no task being enqueued" — and the reason generalises to the
rest of the module: an enqueue that was recorded proves an intention, and what a
gradebook holds is the fact.

**How a task reaches the platform inside a test.** The launch publishes; the work
is done by a Celery task; and a test process has neither a worker nor a network.
So the tasks run inline (`task_always_eager`, the work order's settled seam) and
`app.services.grading.outbound_transport` is substituted for the in-process wire,
which is the seam D3 puts there for exactly this. Both substitutions are made
**after** the door is built, because `tool_doors` imports the application fresh
and a Celery application imported before that is a different object from the one
the door's tasks are registered on (`docs/MISTAKES.md` entry 3);
`run_tasks_inline` in `tests/fixtures/line_item_creation.py` carries that
argument in full.

**The broker is at a closed port throughout.** Under eager it is never dialled,
which is what the seam rests on — so if the seam ever stops working, these tests
fail in milliseconds against a refused connection rather than hanging on a
publish, and the failure says which.

**The controls come first and they must be green today.** The wire, the launch's
own AGS claim, and eager execution are the three things every criterion below
rests on, and each is a statement about the harness rather than about E3-05. **A
red in that section means these tests are broken, not the code.**

**Which failure a red is.** Before E3-05 lands, every criterion test here is
expected red on a failed assertion — an empty container where a line item should
be, a `section.ags_line_item_url` still NULL, or `pytest.fail` naming
`app.services.grading` as a module that does not exist. None of them should be a
collection error or an error in setup: every deliverable guard is a plain call in
a test body (`docs/MISTAKES.md` entry 44).

**The environment** is `configured_env`'s documented values over the container's
database coordinates, laid down by `tool_doors` (`docs/MISTAKES.md` entry 40).
`ENVIRONMENT` is the development name, which is what makes the mock's own
cleartext container address storable at all (ADR 0081) — the deployment-name half
of the address question is `test_a_launch_stores_the_gradebook_address_it_was_given.py`'s
for the stored address and `test_the_created_line_items_own_address_is_judged_before_it_is_stored.py`'s
for the fetched one.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebook_door`, `line_item_contract` and `a_closed_broker` come from
# `tests/fixtures/line_item_creation.py`; `provisioning_contract`, `launch_ground`
# and `provisioned_rows` from `tests/fixtures/provisioning.py`; `web_identity`
# from `tests/fixtures/web_identity.py`; `committed_rows` from
# `tests/fixtures/authz_data.py`; `celery_application_in` from
# `tests/fixtures/repo.py`. All are reached as fixtures rather than imported: an
# import of a fixtures module by name depends on where pytest put `tests/` on
# `sys.path`, and an import error is not a red.

# §2.1's college-grain leadership role, by the spelling
# `tests/fixtures/supervision.py` resolves against the column's own enumeration.
# The same actor `test_a_staff_launch_binds_only_inside_the_launchers_purview.py`
# poses the roster half of criterion 3 with.
DEAN = "DEAN"

SUBJECT_CLAIM = "sub"

# A label for a line item that is not Pulse's, for the container control below.
# Any string will do; what it must not be is `pulse-participation`.
A_FOREIGN_RESOURCE_ID = "e3-05-somebody-elses-column"


def a_linked_person(web_identity: Any, door: Any, subject: str) -> Any:
    """One `person`, one `user` row for `subject` at this platform, and the ADR 0024 link.

    This module's own copy of the helper in
    `test_a_staff_launch_binds_only_inside_the_launchers_purview.py`, for the
    reason that module gives about importing across test modules. No assignment:
    which assignment the person holds is the whole subject of the leadership test,
    so it is written in the open where the assertion can see it
    (`docs/MISTAKES.md` entry 30).
    """
    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=door.registration.platform_row[web_identity.key_of("lti_platform")],
        subject=subject,
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    return person_id


def sections_coded(rows: Any, contract: Any, label: Any) -> list[Any]:
    """Every `section` row carrying the code this launch's label names."""
    return [row for row in rows.sections() if row.get(contract.section_code_column) == label.code]


def the_one_section(rows: Any, contract: Any, label: Any) -> Any:
    """The single section this launch bound, or a failure saying which way it went wrong."""
    found = sections_coded(rows, contract, label)
    assert len(found) == 1, (
        f"There are {len(found)} sections coded {label.code!r} after this launch: "
        f"{[dict(row) for row in found]}. Zero is a launch that bound nothing — E1-10's writer, "
        "not this ticket — and more than one is a writer that inserts on every launch. Either way "
        "the gradebook assertions below would be about a section that is not the launch's."
    )
    return found[0]


def stored_on(section: Any, column: str, ticket_says: str) -> Any:
    """One column of a `section` row, or a failure naming the column that owes it.

    A `row[column]` on a mapping with no such key raises `KeyError` from inside
    the assertion, which reads as a broken test rather than as a missing
    deliverable. `test_a_launch_stores_the_gradebook_address_it_was_given.py`'s
    idiom, borrowed for the same reason.
    """
    if column not in section:
        pytest.fail(
            f"`section` carries no `{column}` column — it carries {sorted(section.keys())}. "
            f"{ticket_says}"
        )
    return section[column]


def line_item_id(item: Any) -> str:
    """One AGS line item's own address, which is its `id` member."""
    identifier = item.get("id")
    assert isinstance(identifier, str) and identifier, (
        f"The platform served the line item {item!r}, whose `id` is not an address. AGS 2.0 makes "
        "a line item's `id` its own URL, and that is the value E3-05 stores so every later post "
        "can address it without re-reading the container."
    )
    return identifier


def a_launch_at(door: Any, contract: Any, launch_ground: Any, offer: Any) -> Any:
    """Seed the containment rows this launch resolves against, and hand back its label."""
    label = contract.label_of(door.driver.claims_of(offer))
    launch_ground(label)
    return label


def running_inline(
    monkeypatch: pytest.MonkeyPatch,
    celery_application_in: Any,
    line_item_contract: Any,
    door: Any,
) -> None:
    """Both substitutions, in the order the tests need them, with one call.

    Deliberately **not** a fixture: both of them import `app.*` modules, which
    only resolve to the objects the door holds once the door has been built, and a
    fixture would run before the test body chose its environment. It is also where
    the two deliverable guards fire, and a guard in a fixture turns a module's reds
    into setup errors (`docs/MISTAKES.md` entry 44).
    """
    line_item_contract.run_tasks_inline(monkeypatch, celery_application_in)
    line_item_contract.reaching_the_platform(monkeypatch, door.wire)


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_launch_this_module_drives_advertises_a_gradebook_container_of_its_own(
    gradebook_door: Any, provisioning_contract: Any, a_closed_broker: str, line_item_contract: Any
) -> None:
    """A control: the platform really sends an AGS endpoint claim, so there is a container.

    Every criterion below is about what appears in the container the *launch*
    named. If the launch carried no AGS claim, "one line item was created" would
    be a statement about an address this test composed, and the absent-claim
    criterion next door would be about a launch indistinguishable from every other
    one — two green tests measuring nothing (`docs/MISTAKES.md` entry 3).

    Both service addresses are read, and they are required to differ: a writer
    that stored the roster address in the gradebook column would otherwise satisfy
    every assertion in this module, and the tool would create a line item by
    POSTing to a membership container.

    Green today. E0-15 built the platform's half and E3-02 stores the address.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    claims = door.driver.claims_of(offer)

    line_items = provisioning_contract.line_items_url_in(claims)
    memberships = provisioning_contract.memberships_url_in(claims)

    assert line_items != memberships, (
        f"The launch advertises {line_items!r} for its line items and {memberships!r} for its "
        "roster, and they are the same string. Then this module cannot tell the two services "
        "apart, and a tool that posted a line item to the roster container would pass every test "
        "here."
    )


def test_the_container_this_module_reads_answers_over_the_wire_and_holds_what_is_put_in_it(
    gradebook_door: Any, provisioning_contract: Any, a_closed_broker: str, line_item_contract: Any
) -> None:
    """A control: the read every criterion rests on is a live read, both ways.

    Two halves, and the empty one is why the other exists. `pulse_items_in` is
    asserted **empty** by the student and leadership tests, and an empty answer is
    what a broken reader produces as readily as an untouched gradebook — so this
    requires the same reader to *find* a line item on a container that certainly
    has one, which is `docs/MISTAKES.md` entry 3's rule about a test satisfied by
    emptiness.

    The wire is exercised in the same test, because it is the transport the
    eagerly-run task speaks over: it must fetch the launch's own container, and it
    must refuse a host nothing mounted — which is what stands between "the task
    dialled somewhere it should not" and a silent pass.

    Green today. Nothing here calls anything E3-05 adds.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    signed = door.platform.mint(offer)

    assert not door.pulse_items_in(signed), (
        "The launched context's container already holds a "
        f"{line_item_contract.resource_id!r} line item before anything created one: "
        f"{door.pulse_items_in(signed)}. Then 'exactly one after the launch' is satisfied by a "
        "tool that does nothing, and the seeded item is doing this ticket's work."
    )

    planted = door.plant_a_line_item(signed, resource_id=A_FOREIGN_RESOURCE_ID)
    listed = [item.get("id") for item in door.items_in(signed)]
    assert line_item_id(planted) in listed, (
        f"A line item created on the platform out of band is not in what this module reads back "
        f"({listed}). Every 'the container is empty' assertion below would then be true of a "
        "reader that cannot see anything at all."
    )

    session = door.wire.session()
    answered = session.get(door.container_of(signed))
    assert answered.status_code in (200, 401, 403), (
        f"The wire answered {answered.status_code} for the launch's own container address "
        f"{door.container_of(signed)!r}. A status here means the request reached the platform — "
        "which credential it needs is E3-04's business — and anything else means the host is not "
        "mounted, so the task could never reach the gradebook through this transport. Body begins "
        f"{answered.text[:200]!r}."
    )
    with pytest.raises(Exception, match="no application is mounted"):
        session.get("http://a-platform-nobody-registered.invalid/lineitems")


def test_eager_execution_runs_the_tools_own_tasks_inline_against_a_broker_that_is_down(
    gradebook_door: Any,
    a_closed_broker: str,
    line_item_contract: Any,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A control: the seam every criterion rests on, proven on a task E3-05 does not touch.

    `run_tasks_inline` claims two things at once — that it reached the Celery
    application the *door* holds rather than one imported earlier, and that a
    publish under eager never dials the broker. Both are invisible in a criterion
    test: a line item that failed to appear would be reported as the tool not
    creating one, whichever of the two had actually gone wrong.

    So it is proven here on `ping`, which has been a task in `app.jobs.tasks`
    since E0-03 and which this ticket changes in no way. The broker is at a closed
    port, so a publish that really happened would raise rather than answer, and the
    result comes back with the value the task computed — which only an inline run
    can produce, since nothing in this process is consuming a queue.

    Green today.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    application = line_item_contract.run_tasks_inline(monkeypatch, celery_application_in)

    assert application.conf.task_always_eager, (
        "`task_always_eager` did not take on the Celery application the door holds, so every task "
        "below would be published to a broker at a closed port and nothing would run. This is the "
        "harness, not the ticket."
    )
    ping = line_item_contract.named_in(
        line_item_contract.tasks(),
        line_item_contract.ping_task,
        "E0-03 ships it and `tests/unit/test_celery_app.py` asserts it is a Celery task there. It "
        "is used here as a task whose behaviour E3-05 does not touch, so a round trip through it "
        "says something about this module's machinery rather than about the ticket.",
    )

    result = ping.delay()

    assert result.get(timeout=10) is not None, (
        "An eagerly-run `ping` answered nothing. Under `task_always_eager` the task runs in this "
        "process and its return value comes back directly; there is no worker here and the broker "
        f"is at a closed port ({a_closed_broker}), so a result that had to travel through a queue "
        "could not arrive at all. The door was opened before the flag was set, which is the order "
        "every criterion test uses."
    )
    assert door.wire is not None, (
        "The door handed back no wire, so the criterion tests would have no transport to "
        "substitute for the creation task's outbound session."
    )


# ---------------------------------------------------------------------------
# Criterion 1: the first instructor launch creates it, and the second does not.
# ---------------------------------------------------------------------------


def test_an_instructor_launch_creates_the_participation_line_item_and_stores_its_id(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 1, first half, and SPEC §3.4's sentence end to end.

    > An instructor launch of a section with no line item results in one being
    > created.

    One launch, by a real instructor, at the real door. Afterwards the launched
    context's container holds exactly one line item carrying
    `pulse-participation`, and the section row carries that line item's own `id`
    in `ags_line_item_url` — the column E3-02 created and left for this ticket to
    write.

    **Both halves are asserted and neither implies the other.** A container with
    the column in it and a section that stored nothing means every later post
    re-reads the container and E3-06's retry identity has nothing to rest on. A
    stored id with an empty container means the tool wrote down an address the
    platform does not serve.

    **The mutation this kills**: the hook left out of `api/lti.py` altogether,
    which is the state at HEAD — nothing is enqueued, the container stays empty
    and the column stays NULL. And, one step in: a hook that enqueues but whose
    worker never stores the answer, which the second assertion catches while the
    first stays green.

    **The near miss this must not fire on** is the student launch below, at the
    same door, through the same machinery: a hook written as "on launch, ensure
    the line item" passes this test and fails that one, which is the trap the
    ticket names.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    response, signed = door.driver.launch(offer)

    door.driver.accepted(response, "an instructor's first launch of a section with no line item")
    created = door.pulse_items_in(signed)
    assert len(created) == 1, (
        f"The launched context's container holds {len(created)} line items carrying "
        f"{line_item_contract.resource_id!r} after an instructor's first launch: {created}. SPEC "
        '§3.4: \'One AGS line item per section: "Pulse Participation", created by the tool on '
        "first launch.' Zero is the state at HEAD, where nothing on the launch path asks for one "
        "at all; more than one is a container this tool has started duplicating columns in, which "
        "an instructor sees as two participation grades in the same gradebook.\n\n"
        f"Everything the container holds: {door.items_in(signed)}."
    )
    section = the_one_section(provisioned_rows, provisioning_contract, label)
    stored = stored_on(
        section,
        line_item_contract.line_item_column,
        "E3-02 adds it as a nullable text column for the id of the line item this tool creates, "
        "and E3-05's work order (D3) makes `ensure_line_item` its writer — under `guard_write` "
        "with the `grade_passback` sanction, on the column-scoped `UPDATE` grant ADR 0136 adds.",
    )
    assert stored == line_item_id(created[0]), (
        f"The section carries `{line_item_contract.line_item_column}` = {stored!r} and the line "
        f"item the platform holds is {line_item_id(created[0])!r}. A line item created and not "
        "recorded is one every later run has to re-find by walking the container, and ADR 0052's "
        "retry identity has nothing to address; a recorded id the platform does not serve is a "
        "score posted to nothing."
    )


def test_a_second_instructor_launch_creates_no_second_line_item(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 1, second half: "a second launch creates nothing further".

    The steady state, and the one every section is in after its first day: an
    instructor launches the same section again and the gradebook does not change.
    D3 makes that a check on the stored id rather than a debounce — "only staff
    launches reach it and the stored-id check zeroes the steady-state cost" — so
    what this asserts is the outcome that rule exists to produce, and not the rule.

    **Two things are required to be unchanged and they fail differently.** The
    container still holds exactly one Pulse column: a second one is what an
    instructor would actually see, and it is what a hook with no idempotence at
    all produces on launch two. And the stored id is the *same* id: a tool that
    created a second item and then overwrote the column with the new one leaves
    the first assertion red and this one green, and a tool that re-found the same
    item and rewrote the same value leaves both green — which is correct, because
    the criterion is about the gradebook and not about how many times a column was
    written.

    **The mutation this kills**: the stored-id check dropped from
    `request_line_item_creation`, so every staff launch of every section asks the
    platform to create a column again. Against a mock that reconciles by
    `resourceId` the container stays at one, which is why the assertion below is
    written against the container *and* the id rather than against either alone —
    and why the first launch's assertion is a separate test: this one is about the
    difference between two launches, and it would be equally satisfied by a tool
    that never created anything.

    **Its precondition is asserted before the second launch**, so a run where the
    first launch created nothing reports that rather than reporting the second
    launch as correct (`docs/MISTAKES.md` entry 3).
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    first_response, signed = door.driver.launch(offer)
    door.driver.accepted(first_response, "an instructor's first launch")
    after_one = door.pulse_items_in(signed)
    assert len(after_one) == 1, (
        f"The first launch left {len(after_one)} Pulse line items in the container ({after_one}), "
        "so this test has no steady state to launch into a second time and would be asserting "
        "that nothing changed between two nothings. The first-launch criterion is the test above."
    )
    first_stored = stored_on(
        the_one_section(provisioned_rows, provisioning_contract, label),
        line_item_contract.line_item_column,
        "E3-02 adds it and E3-05 writes it.",
    )

    second_response, _ = door.driver.launch(offer)

    door.driver.accepted(second_response, "an instructor's second launch of the same section")
    after_two = door.pulse_items_in(signed)
    assert len(after_two) == 1, (
        f"A second launch of the same section left {len(after_two)} Pulse line items in the "
        f"container: {after_two}. SPEC §3.4 gives a section one, and a gradebook that grows a "
        "column per launch is what an instructor sees the day thirty students open the tool."
    )
    second_stored = stored_on(
        the_one_section(provisioned_rows, provisioning_contract, label),
        line_item_contract.line_item_column,
        "E3-02 adds it and E3-05 writes it.",
    )
    assert second_stored == first_stored, (
        f"The section pointed at {first_stored!r} after the first launch and points at "
        f"{second_stored!r} after the second. The line item did not move, so a section that now "
        "addresses a different one is a tool that created a second column somewhere this "
        "container read cannot see, or that repointed a live grade column at a new address — and "
        "every score already posted is on the old one."
    )


# ---------------------------------------------------------------------------
# Criterion 2: a student launch writes nothing to the gradebook.
# ---------------------------------------------------------------------------


def test_a_student_launch_writes_nothing_to_the_platforms_gradebook(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 2, and the failure this ticket exists to prevent.

    > A student launch of the same section, before any staff launch, creates
    > nothing and writes nothing to the gradebook — asserted against the mock's
    > line-item container being empty afterwards, not merely against no task being
    > enqueued.

    SPEC §7.3: "A **student** launch triggers nothing." The ticket's known traps
    section says why this is written first: "the natural implementation is 'on
    launch, ensure the line item', and the role check is the part that gets added
    second."

    **The container is read, not the queue.** A test that asserted no task was
    enqueued would pass against a hook that called the creation service
    synchronously, and against one that enqueued under a name this module does not
    watch. What a platform's gradebook holds afterwards is the property the ticket
    is about.

    **Emptiness is proved to be a real emptiness before it is believed**
    (`docs/MISTAKES.md` entry 3). The container read is the same one the instructor
    test above finds a line item with, so it demonstrably can see one; here it is
    run again after planting an item out of band, and the planted item has to come
    back. Without that, a container reader that answered `[]` for any reason at all
    would make this test unfalsifiable.

    **Its near miss is the instructor pair above**, at the same door and through
    the same machinery: without those, this test is equally satisfied by a build
    where the whole hook is missing, which is exactly the state at HEAD — so
    **this test is expected green today**, and it is here because it must stay
    green through the change the other tests force.

    **The mutation it kills**: `request_line_item_creation` called before or
    outside the `if section_id is not None:` block in `api/lti.py`, or called on a
    section id resolved some other way than through `provision_from_launch` — D1's
    "no second role or purview check anywhere" cuts both ways, and the one
    decision point is what makes the student answer `None`.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.student_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    response, signed = door.driver.launch(offer)

    door.driver.accepted(response, "a student's launch of a section nobody has bound")
    roles = signed.claims.get(provisioning_contract.roles_claim) or []
    assert provisioning_contract.instructor_role_urn not in roles, (
        f"The launch this test drove carries {roles!r}, which includes the Instructor URN — so it "
        "is a staff launch and whatever it did to the gradebook says nothing about §7.3's student "
        "rule."
    )
    assert not door.pulse_items_in(signed), (
        "A student's launch put "
        f"{door.pulse_items_in(signed)} into the platform's gradebook. The ticket, ruled at "
        "breakdown: 'a student launch must never cause a write to the platform's gradebook.' A "
        "student who opens the tool in a section nobody has bound has caused this tool to create "
        "a graded column in somebody's course."
    )
    assert not door.wire.calls, (
        f"A student's launch made {[str(call) for call in door.wire.calls]} on the outbound "
        "transport. Nothing about a student launch may reach the platform's grade services at "
        "all, and a call that was made and refused is still a call this tool had no authorization "
        "to make — the launching person's role authorizes the trigger, and there is no trigger "
        "here to authorize."
    )
    bound = [dict(row) for row in sections_coded(provisioned_rows, provisioning_contract, label)]
    assert not bound, (
        f"A student's launch bound a section: {bound}. "
        "That is E1-10's rule rather than this ticket's, and it matters here because it is the "
        "state the assertions above are read against: with a section bound, a hook reading "
        "`provision_from_launch`'s answer would have had something to act on."
    )

    planted = door.plant_a_line_item(signed, resource_id=A_FOREIGN_RESOURCE_ID)
    assert line_item_id(planted) in [item.get("id") for item in door.items_in(signed)], (
        "A line item created out of band after the launch does not come back from the container "
        "read this test just used to assert emptiness. So the emptiness above is this reader "
        "seeing nothing rather than the gradebook holding nothing, and the whole test proves "
        "nothing (`docs/MISTAKES.md` entry 3)."
    )


# ---------------------------------------------------------------------------
# Criterion 3: a leadership launch outside the launcher's own purview.
# ---------------------------------------------------------------------------


def test_a_leadership_launch_outside_the_launchers_purview_creates_nothing_and_is_recorded(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 3: the gradebook half of §7.3's purview limb.

    > A leadership launch outside the launcher's purview creates nothing and
    > records the defect §7.3 already defines for the roster case.

    The launcher holds a real, live `DEAN` assignment — one of the roles §7.3's
    leadership limb admits — scoped over a college that does not contain the
    launched prefix. Nothing about the person is wrong; what is wrong is the
    context they launched from, and E2-02 already refuses to bind the section or
    store the roster address for exactly this launch. This ticket's addition is
    that no gradebook column appears either, and the existing
    `context_outside_purview` row is what records it.

    **Asserted against the container, and against the defect, and against the
    launch landing.** The container because that is the fact; the defect because a
    hook that refused *silently* would leave E11's surface with nothing to say
    about a launch that discovered nothing; and the door's answer because E1-10's
    rule that "a provisioning refusal NEVER fails the launch or the person's
    landing" is unchanged by this ticket.

    **The mutation this kills**: a creation hook that reads the launch's own roles
    claim, or the section id from anywhere other than `provision_from_launch`'s
    answer. A dean's launch carries no Instructor URN, so a roles-claim hook would
    also refuse it — but a hook that took "any section this launch resolved to"
    would create the column, because the *context* is perfectly real and only the
    launcher's grant is wrong.

    **Its near miss is the instructor pair above**, which is what stops "refuse
    every launch" from passing; and the fact that the dean here is refused while
    a dean inside their own college binds is E2-02's pair, one module over, which
    this ticket does not re-litigate.

    **The assignment is read back out of the database before the launch.** The
    actor is "somebody whose only leadership assignment is a deanship elsewhere",
    and a launcher who ended up holding none is a stranger — every refusal below
    would then be about a person §7.3's leadership limb never admitted, which is a
    different test passing for a different reason.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.student_offer(provisioning_contract)
    claims = door.driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    person_id = a_linked_person(web_identity, door, claims[SUBJECT_CLAIM])
    graph = committed_rows.graph
    elsewhere = graph.scope("college")
    assigned = graph.assign(DEAN, scope=elsewhere, person=person_id, reports_to=None)
    committed_rows.commit()

    assert elsewhere != ground.college_id, (
        "This dean's assignment is scoped over the college that contains the launched prefix, so "
        "the launch is inside their purview and this test is posing the accepted case. The "
        "control at the head of "
        "`test_a_staff_launch_binds_only_inside_the_launchers_purview.py` is where that is "
        "diagnosed."
    )
    assert graph.assignments_of(person_id) == [assigned[graph.assignment_key]], (
        f"This launcher holds the assignments {graph.assignments_of(person_id)} and this test "
        f"wrote one {DEAN} assignment. None means the launcher is a stranger and the refusal "
        "below is about a person the leadership limb never admitted; more than one means a hat "
        "this test did not write, and §2.1 composes hats."
    )

    response, signed = door.driver.launch(offer)

    door.driver.accepted(response, "a dean's launch into a context outside their college")
    assert not door.pulse_items_in(signed), (
        "A leadership launch from outside the launcher's own purview put "
        f"{door.pulse_items_in(signed)} into the platform's gradebook. §7.3 admits that limb only "
        "'inside the launcher's own purview', and a column created here is this tool writing into "
        "the gradebook of a course whose records the launching person may not read."
    )
    recorded = provisioned_rows.defects()
    assert len(recorded) == 1, (
        f"There are {len(recorded)} `{provisioning_contract.defect_table}` rows where there "
        f"should be exactly one: {[dict(row) for row in recorded]}. §7.3's out-of-purview launch "
        "records one defect; a second row is this ticket recording a gradebook refusal of its "
        "own, which the criterion says it does not — it 'records the defect §7.3 already defines "
        "for the roster case'."
    )
    written = str(getattr(recorded[0]["kind"], "value", recorded[0]["kind"]))
    assert written == provisioning_contract.context_outside_purview, (
        f"The recorded defect's kind is {written!r} and §7.3's out-of-purview kind is "
        f"{provisioning_contract.context_outside_purview!r}. A record naming the wrong rule reads "
        "as though somebody checked, and it is the one question E11's surface exists to answer."
    )


# ---------------------------------------------------------------------------
# Criterion 6: a container that already holds one is reconciled to.
# ---------------------------------------------------------------------------


def test_an_instructor_launch_reconciles_to_a_participation_column_pulse_did_not_create(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 6, exercised from the launch path.

    > A container that already holds a "Pulse Participation" item produced by
    > something other than Pulse is reconciled to, not duplicated — the rule E3-04
    > settled, exercised from the launch path.

    The line item here is created on the platform out of band, carrying SPEC
    §3.4's `resourceId` and nothing else of Pulse's — the shape a re-installed
    tool, a course copy, or an administrator following the documentation leaves
    behind. E3-04 settled that the client matches by id and then by `resourceId`,
    never by label; what this asserts is that the *launch path* ends up pointing at
    that item rather than creating a second one beside it.

    **Two assertions, and the second is the one that says "reconciled to" rather
    than "left alone".** One Pulse column in the container after the launch, and
    the section's stored id equal to the planted item's own id. A tool that saw the
    existing column and stored nothing satisfies the first and leaves E3-06 with a
    section it cannot address; a tool that created a second column fails the first
    and would give an instructor two participation grades.

    **The mutation this kills**: reconciliation by `label` rather than by
    `resourceId`, which is invisible here because the planted item carries both —
    and the one it is really for, a `find_or_create` whose "find" is skipped
    whenever the section's own column is NULL, which is the state every section is
    in the first time this runs.

    **The precondition is asserted before the launch**: the container really holds
    a Pulse column beforehand, read back from the platform. Without it a run where
    the plant silently failed would report the ordinary create-one case as
    criterion 6 passing.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    signed_out_of_band = door.platform.mint(offer)
    planted = door.plant_a_line_item(signed_out_of_band)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    before = door.pulse_items_in(signed_out_of_band)
    assert [line_item_id(item) for item in before] == [line_item_id(planted)], (
        f"The container holds {before} before the launch and this test planted "
        f"{line_item_id(planted)!r}. Criterion 6 is about a container that *already* holds a "
        "participation column, and with the plant missing this is the ordinary first-launch case "
        "wearing criterion 6's name."
    )

    response, signed = door.driver.launch(offer)

    door.driver.accepted(response, "an instructor's launch into a container that already has one")
    after = door.pulse_items_in(signed)
    assert len(after) == 1, (
        f"The container holds {len(after)} Pulse line items after the launch: {after}. E3-04's "
        "settled rule is find-or-create by `resourceId`, so a launch meeting a column somebody "
        "else made reconciles to it — a second one is two participation grades in one gradebook, "
        "and neither of them is the one an instructor has been reading."
    )
    stored = stored_on(
        the_one_section(provisioned_rows, provisioning_contract, label),
        line_item_contract.line_item_column,
        "E3-02 adds it and E3-05's work order (D3) makes `ensure_line_item` its writer.",
    )
    assert stored == line_item_id(planted), (
        f"The section points at {stored!r} and the column that was already there is "
        f"{line_item_id(planted)!r}. Storing nothing leaves every later post walking the container "
        "again with nothing to retry against (ADR 0052); storing something else means this tool "
        "created a column it did not have to and left the instructor's existing one behind."
    )
