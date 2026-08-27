# 0095 — The roster sync records two windows, no status, and refuses a member it cannot date

## Context

E1-11 fills a section in from NRPS. SPEC §3.4 is what reads the result:

> **Late adds**: denominator starts at the student's first enrolled week (from
> NRPS enrollment data). Where the platform supplies no enrollment dates — most
> supply none — a student counts as enrolled from the section's start date,
> except a student who first appears in a roster sync later than their section's
> first sync, who counts from the week of that sync. **Drops**: scores stop
> updating.

Those are three different rules, and the tool can only choose between them if the
row says which situation it is in. NRPS 2.0 itself carries no date of any kind —
a member has `status`, and nothing says when — so any window at all arrives on a
vendor extension ([ADR 0048](0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md)),
and one seeded member deliberately carries none.

`enrollment` arrived in E0-08 with `started_on` and `ended_on` and an open
question about what they mean: "these two columns are most likely Pulse's record
of when a student was first and last seen in the roster… E1's roster sync is what
settles it." SPEC §8 decides none of this, and a reasonable engineer would choose
differently on every point below, so this record exists. The chokepoint mechanism
is [ADR 0090](0090-a-sanctioned-writer-passes-the-chokepoint-by-being-in-a-catalog.md)'s
and the resolution doors are [ADR 0094](0094-subjects-resolve-to-ids-through-definer-functions.md)'s;
neither is reopened here.

## Decision

**Four columns, two facts.** `started_on` and `ended_on` stay exactly as E0-08
declared them and are settled as what that ticket predicted: Pulse's own record of
the day a member was first and last *seen by a sync*, unprefixed because Pulse
derives them. `lms_window_start` and `lms_window_end` are added, nullable
`AwareDateTime`, carrying ADR 0048's extension values verbatim and `lms_`-prefixed
because the platform owns them. **NULL means the platform supplied none**, and
nothing may ever write a value there the extension did not carry.

**The rules the sync applies**, in full:

- *First appearance* — `started_on` is the day the sync ran, in the institution's
  timezone (SPEC §3.1); the window columns are the extension's values or NULL.
- *A drop* — the member is `Inactive`, `Deleted`, or absent from the container
  altogether. `ended_on` is the extension's end date where the platform supplies
  one and the sync's own day where it does not; `lms_window_end` is the platform's
  value or nothing.
- *A re-add* — a second `enrollment` row. The closed row keeps its end date.
- *A member already open* — the window columns follow the platform and nothing
  else is touched. Every update is conditional on a value actually differing, so a
  second run against an unchanged roster writes no row at all.

**There is no status column on `enrollment`, and there is deliberately not going
to be one.** The open and closed rows *are* the recorded transition. ADR 0023's
exclusion constraint already refuses two overlapping windows for one user and
section, and it refuses `UNIQUE (user_id, section_id)` by name so that a
drop-and-re-add stays two rows with a gap between them.

**A member whose extension carries a naive or unparseable timestamp is refused,
one member at a time.** No enrollment row is written for them, the refusal is
logged, and every other member of the container is ingested normally.

**The extension is found by shape, not by namespace.** The sync reads the member
key that is an absolute URI whose value is an object carrying a `start`. ADR 0048
forbids the alternative in as many words — "Nothing in `backend/` may hardcode
this URI. It is one platform's spelling of one vendor extension, and the tool's
side of it is an adapter" — and E1-11's boundary does not build E3's adapters.

**`user_identity.identity_name` becomes nullable**, and no `CHECK` replaces the
constraint. ADR 0050 measured that the roster exposes "an address and no name", so
the sync has an address to store for a user it has no name for at all.

**The launch trigger is debounced at five minutes**, measured against the
section's own most recent `nrps_call` row.

## Alternatives rejected

**One pair of date columns, holding whichever dates were known.** Half the schema
and it destroys §3.4's only signal: a member the platform dated and a member it
did not become the same row, and E3 has no way back. The absence has to be
storable to be honest.

**Synthesize a window where the platform sends none** — the section's start, the
sync's date, `now()`. It is the single most natural thing to write, because a NOT
NULL column would demand it, and a synthesized value is indistinguishable from a
real one on every screen and in every row afterwards.

**A status column beside the windows.** Tempting because NRPS sends one and
storing what you were told is usually right. It gives "was this student enrolled
in week N" two answers with no rule for choosing between them, and the two drift
the first time a platform sends `Active` for somebody whose window has closed.

**Let a naive timestamp reach the column.** `AwareDateTime` refuses it at bind
(ADR 0019) and takes the whole roster's transaction with it, so one member's bad
value stops a section syncing at all — and the symptom is a class that quietly
stops updating.

**Catch that refusal and store the absence instead.** Milder-looking and worse
than the refusal above in the way that matters: the row would then claim the
platform supplied no dates when it supplied one this tool could not read, which is
a false statement rather than a missing one.

**End an enrollment only on a non-`Active` status.** Several platforms remove a
dropped student from the container entirely rather than restating them, so every
leaver would stay enrolled for ever and E3 would go on counting them.

**Record a closed enrollment for a member who is already dropped on the first
sync.** Attractive — it would keep some history for a student who left before the
tool arrived — and it is unwritable: `started_on` would have to be synthesized,
and ADR 0023's `ended_on >= started_on` refuses a row whose end date precedes the
sync that first saw it. So such a member gets no row, which is the honest answer
to "how many weeks was this student enrolled in, as far as Pulse knows".

**Name ADR 0048's namespace in the sync.** One line instead of a shape test, and
it contradicts that record's closing rule. **A configuration setting for it** was
the next candidate and is worse: a deployment-wide knob for a per-*platform* fact,
which every registration after the first would be wrong about. **A column on
`lti_platform`** is where the fact honestly belongs and is E3's `PlatformProfile`
to add, with the registration surface that fills it in; adding the column now
would ship a schema nothing writes.

**A `CHECK (identity_name IS NOT NULL OR identity_email IS NOT NULL)` in place of
the NOT NULL.** It would refuse the ordinary intermediate state of a two-step edit
in §6.3's People editor, which nobody has built yet, in exchange for a rule no
writer needs: `record_roster_email` creates a row only where the platform exposed
an address, and clears an address without creating one.

**Debouncing by "has this section ever been called".** Passes a debounce test and
turns every section in the institution into one that syncs exactly once.

## Consequences

**Two of ADR 0023's stated costs become live.** The exclusion constraint's bounds
are inclusive at both ends, so a member dropped and re-added on the same day is
refused by the database — the sync does not work around it, and that record says
why. And a re-add is a second row, so anything counting enrollments per section
counts windows rather than people.

**Reading a window is a shape test until E3.** A platform sending two namespaced
extension objects that both carry `start` is read as carrying none, with a warning
— the tool has no rule for choosing and choosing would be inventing one. E3's
`PlatformProfile` adapter replaces the shape test with a per-platform spelling;
`docs/tickets/e1/deferred.md` carries it with a "done when".

**A member with no `user_id` is dropped from the container with a warning.** SPEC
§4 keys every response to that value, so there is nothing to write.

**The debounce's memory is `nrps_call`**, which means the record §6.1 asks for and
the trigger's window are the same rows. A retention purge that trimmed that table
(E13) would un-debounce the sections it trimmed, which is harmless and worth
knowing before somebody writes the purge.

**A refused token is recorded under the roster's URL carrying the token endpoint's
status**, and both halves of that were decided rather than fallen into. A sync
makes two calls to two endpoints and only one of them is the roster; when the token
endpoint answers an error the roster is never asked at all. The *URL* is the
roster's because the row is that section's record of an attempted sync and §6.1's
console reads it per section. The *status* is the token endpoint's because D9 gives
a NULL
`response_code` exactly one meaning — "the call never reached the platform" — and
the two states an operator has to tell apart here are "this deployment's
credentials were refused and the platform is up" and "nothing answered". Recording
the refusal without its status collapses the first into the second. Two
alternatives were available and both were rejected for the same reason: a second
row under the token endpoint's own address, and a `kind` column on `nrps_call`,
each put an OAuth fact into a table whose whole subject is one section's roster
history, and E11's console does not exist yet to be asked which it wants.

**The eager token fetch is redundant, and this paragraph used to claim otherwise.**
It said the call row was the only thing that could ever detect the fetch's removal.
Measured on 2026-08-27 by re-planting exactly that removal against the test written
for it: **the mutation survives all fourteen tests of the conformance and debounce
modules.** The property is over-determined. `_walked_roster`'s own page handler
catches the same `LtiServiceException` and records the same status against the URL
it called — and `ServiceConnector` caches an access token per scope set per
connector with no expiry check, so exactly one grant is attempted per sync and it
is attempted on the first page, whose URL *is* the section's stored address. Eager
or lazy, the row is identical, and nothing in this repository can tell the two
apart.

So what the eager fetch buys is determinacy rather than behaviour: the recorded URL
is the section's stored address because this module says so, rather than because
the library's token cache happens to make the first page the only page a grant is
ever attempted from. That becomes load-bearing only if the cache changes — a
version honouring `expires_in`, or one connector reused across sections — and it is
recorded here as the contingent thing it is. It is kept on that ground and on
legibility, not because anything fails without it, and a later reader is entitled
to delete it after re-running the measurement above.

What *is* asserted is the pairing.
`test_a_refused_token_is_recorded_against_the_roster_url_with_the_token_endpoints_status`
pins the URL and the status, and it was red against an implementation that recorded
the row and discarded the status — which is the defect it was written for. What the
sync does with the refusal *beyond* recording it stays the writer's, which is ADR
0090's consequence about a sanctioned writer running on a job rather than on a
request.

**`identity_name` being nullable is a widening the downgrade cannot undo
silently.** E1-11's revision fills any row that has no name with a stated marker
before it restores the constraint, because the alternative — refusing the
downgrade — leaves a database that cannot go back at all.
