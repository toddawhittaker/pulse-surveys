# 0135 — The line item is asked for by the launch that authorized it, once, and retried by the next one

## Context

SPEC §3.4 gives every section one gradebook column, "created by the tool on
first launch". SPEC §7.3 already has a trigger on that door: an instructor
launch pulls the roster, a leadership launch pulls it only inside the launcher's
own purview, and a student launch pulls nothing. E3-05 adds a second trigger
beside the first, and four questions have to be answered before it can be
written.

**Who may cause it.** The rule is §7.3's, and the ticket's breakdown made the
student half a requirement rather than a default: a student launch must never
cause a write to a platform's gradebook. The question is not what the rule is but
where it is asked. The launch door can read the roles claim itself, or it can use
the answer `provision_from_launch` already computed for the roster trigger.

**Whether it is enqueued or synchronous.** The launch has already verified a
person and committed what it discovered by the time this runs, and a platform
that is slow to answer an AGS call must not be a launch that is slow to land.

**What a failed creation looks like on the next launch.** Retrying on every
launch and retrying never are both wrong: the first asks a platform to create a
column that exists once per launch for the rest of the term, and the second
leaves a section whose one attempt failed with no gradebook column and nothing
that will ever try again.

**What a section with no gradebook is.** A platform that grants this tool no AGS
scope advertises no endpoint claim, so `section.lms_ags_line_items_url` is NULL.
E3-02 already ruled that state a configuration rather than a fault.

## Decision

**One decision point.** `provision_from_launch` returns a section id for exactly
the launches §7.3 authorizes and `None` otherwise, and both triggers ride that
answer inside the same block in `app.api.lti.launch`. No role or purview check is
written a second time anywhere on this path. A student launch resolves no section
and so reaches neither trigger; an out-of-purview leadership launch records the
`context_outside_purview` defect §7.3 already defines and reaches neither.

**Enqueued, on the bounded publish.** `request_line_item_creation` publishes
`create_line_item` through `app.jobs.celery_app.publish_once` — one attempt, a
connection made for the call with its retries off and its socket timeouts
bounded, no result backend — and catches broadly. The launch is never failed and
never delayed by a broker.

**Two conditions decide whether anything is published**, and they are read off
the section's own row. No container address: nothing is asked for, no defect is
recorded, and it is logged at info at most. An id already recorded: nothing is
asked for, because the column exists and this tool knows its address.

**The retry is the next qualifying launch.** While `ags_line_item_url` is NULL
every qualifying launch asks again; the moment an id is stored no launch asks
anything. There is no scheduled backstop in this ticket. E3-06's weekly recompute
sweep walks every section that should have a score and is the natural place for
one; it is named here so the absence is a decision with an owner rather than a
gap.

**No debounce on the creation trigger**, deliberately, where the roster trigger
has one. Only staff launches reach it, and the recorded-id check makes the
steady-state cost of a staff launch one column read and no task at all — so the
worst case a debounce would protect against is the interval between a section's
first staff launch and the worker recording the id, which is seconds.

**A stated limit.** A staff launch whose platform advertised no roster address
also triggers no line-item creation, because `provision_from_launch` answers
`None` for it. This is accepted: a section with no roster has no enrollments and
therefore nobody to grade, and the alternative is a second discovery path into
the same block.

## Alternatives rejected

**A role check in the router, or in the creation service.** It reads as
defence in depth and is not: two places answering "may this launch cause a
write" is `docs/MISTAKES.md` entry 13's shape, and the copy that drifts is the
one nobody is looking at. The one that matters here is subtler than the roles
claim anyway — a dean launching outside their own college carries no Instructor
URN, so a roles-claim check would refuse them for the right outcome and the wrong
reason, and would admit them the day a leadership limb is widened.

**Creating the line item synchronously in the launch.** Simpler to follow, and it
puts a third-party HTTP call — a token grant, a container walk, a create — on a
door a person is waiting at, with a timeout budget nobody has set. SPEC §10 gives
the whole round trip 2.5 seconds.

**Retrying on a schedule of its own.** A beat entry that sweeps for sections with
a container address and no line item would be correct and is one more scheduled
job to own, monitor and reason about, for a case the next staff launch of that
section already covers. E3-06's sweep arrives with a schedule that has to exist
anyway.

**Treating an absent container address as a fault.** It would put a line on
§6.3's console for every section in an institution that grants no gradebook
scope, which is exactly the conflation E3-02 rejected one ticket earlier for the
same value.

## Consequences

- The launch door has two enqueues and one authorization decision. A third
  trigger added later inherits both properties by living in the same block, and
  gets neither if it does not.
- A section whose creation task fails repeatedly retries once per staff launch,
  and every failed attempt now leaves the `ags_call` rows it recorded before it
  raised: the worker task catches the `AgsError`, commits those rows and re-raises,
  so a failure is as durable on §6.1's console as a success (E3-05's security
  round; the earlier shape rolled a failed attempt's rows back with the session
  and left an endpoint probe invisible in the one log built to show it). What is
  still not recorded is an aggregate — nothing counts "this section has been asked
  four times"; the rows are per call, and the console that renders them is E11's.
- The worker's AGS calls dial under a finite timeout (`AGS_REQUEST_TIMEOUT` in
  `app.lti.ags`, and the token grant `pylti1p3` posts inherits it through the
  client's own bounded session). `ensure_line_item` holds `SELECT … FOR UPDATE`
  on the section across those calls so two workers racing to create one section's
  item serialise, and a platform that completed the handshake and then stalled
  would otherwise hold that lock, the connection and the worker slot without bound
  — on the single default queue, that would also stall the floored-comment
  reclassify and turn a slow gradebook write into a §3.3 safety outage. The lock
  stays; the timeout is what makes it safe to hold across the network (E3-05's
  security round).
- A section that a platform has stopped advertising a gradebook for keeps the id
  it already recorded; nothing here clears it. Reconciling a column a human
  deleted beyond E3-04's re-find rule is out of scope for E3 by the breakdown.
- Until E3-06 lands there is no backstop at all: a section whose only staff
  launch of the term fails to publish has no participation column. The window is
  one epic ticket wide and named here so it closes deliberately.
