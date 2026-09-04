# E3-07 — A development trigger for passback, and the CSRF route sweep

**ID:** E3-07
**Branch:** `e3/dev-trigger-and-csrf-sweep`
**Depends on:** E3-06
**Lane:** heavy
**Security-relevant:** yes. Half the ticket is a sweep over the built
application's routes that decides which of them must carry a CSRF check, and
the other half adds a mutating development route. `backend/app/api/dev.py`
and `backend/app/api/deps.py` are both heavy-lane rows — `dev.py` as the
dev-only bypass surface, `deps.py` as the dependency chain every route
composes from.

## Context

**The trigger.** The beat fires on real time while the formula counts weeks
off the development clock (ADR 0109). Without a way to run a passback on
demand, the epic's behaviour is not drivable in a browser at all — set the
pretend clock past a window's close and nothing happens until the real
schedule comes round. This is exactly the gap E2-04 and E2-13 hit with survey
windows, and the answer there was the same: a `/dev` control.

**The sweep.** Carried from E2: nothing structurally forces the next mutating
route onto the CSRF dependency. `require_student` and
`csrf_verified_student` sit beside each other and nothing makes a writing
route reach for the checked one, so the next mutating route is one import
away from being unprotected in a way that reads as fine in review. The submit
path itself is correct; the guard is what is missing.

The two halves belong together because the sweep's red case needs a mutating
route that did not exist when the item was carried. E3's development trigger
is the first mutating route since E2-08, which makes this the first honest
moment to build the sweep.

One case is already known and has to be a declared exemption rather than a
failure: the dev-clock set and clear routes at
`backend/app/api/dev.py:1054-1055` are appended as `AnyMethodRoute` instances
carrying no `Depends` at all.

Read first: `carried-from-e2.md`, the CSRF entry, whose done-when governs;
ADR 0109; ADR 0063 and 0064 (the development-environment guard);
`backend/app/api/dev.py` around the route registrations named above;
`backend/app/api/deps.py`.

## Scope

- A `/dev` control that runs a section's passback now, behind the same
  development-environment guard every other `/dev` control sits behind, and
  inert outside development in both directions.
- The CSRF sweep: a test over the built application's routes that requires
  every mutating route to carry the checked dependency, with a declared
  exemption list.
- The exemption list asserted in both directions, so a stale exemption fails
  as loudly as an unguarded route.

## Acceptance criteria

1. With the development clock set past a window's close, the `/dev` trigger
   runs a passback and the mock's gradebook changes — driven in a browser
   once and scripted so it stays true.
2. The trigger is refused outside development, asserted in both directions
   (present and working in development, refused elsewhere), the shape ADR
   0063 and 0064 already require.
3. The sweep walks the routes of the **built application** rather than a
   hand-maintained list, and a planted mutating route with no CSRF dependency
   turns it red.
4. The sweep is red when an exemption names a route that no longer exists,
   and red when a route that should be exempt is not named — both directions,
   both planted.
5. The dev-clock `AnyMethodRoute` pair is a declared, tested exemption with a
   sentence saying why, not a silent pass.
6. The sweep has a canary: a route certainly carrying the dependency is found
   carrying it, so a collector that has gone blind says so
   (`docs/MISTAKES.md` entries 3 and 35).

## Decisions this ticket settles

- **What counts as a mutating route** for the sweep's purposes: the HTTP
  method, the presence of a body, or something the route declares. Whichever
  rule ships is the sweep's whole inventory, and its disclosed limits are
  written down the way the denial-module sweep's were.
- **What the exemption list is allowed to hold**, and what a new entry costs
  — an exemption added without a sentence is how a guard becomes a
  formality.
- **Whether the trigger takes a section or runs the whole sweep**, and
  whether it can be pointed at one student.

## Known traps

- **A closed-set guard is defeated one level out.** The sweep's inventory is
  the routes it can see; a route registered by appending to `router.routes`
  rather than by a decorator is exactly the shape that escapes a decorator
  walk, and `dev.py` already contains two of them. Build the inventory from
  the application's own route table, and prove it finds the appended pair.
- **A marker held in two currencies** is `docs/MISTAKES.md`'s recurring
  shape: a dependency can be attached at the route, at the router, or through
  a nested include, and a sweep that reads only one of the three reports
  clean over a real gap. Enumerate the ways the dependency can be held, and
  give each one a control that finds it on a route that certainly has it.
- **A rewound development clock can wedge a section's roster sync**
  (`carried-from-e2.md`) and can produce a 409 on a passback (E3-06's traps).
  The trigger makes both reachable by hand for the first time. Neither is
  this ticket's to fix; both are worth a sentence in the control's own copy
  so the next person driving it is not debugging the wrong thing.
- **A resubmission under a rewound development clock answers 500**
  (`carried-from-e2.md`). Same override, third victim, also not this
  ticket's.
- **The trigger is a mutating route, so it is subject to its own sweep.**
  Writing the sweep and the route in one ticket makes it tempting to exempt
  the route because it is a development route. It is not exempt; `/dev`
  routes are refused outside development by the environment guard, which is a
  different control from CSRF.

## Out of scope

- Fixing the rewound-clock interactions listed above — each is a carried
  entry with its own owner.
- Any production-facing trigger. §3.4 says the passback is fully automatic
  with no instructor action or override, so the only trigger outside the beat
  is a development one.
</content>
</invoke>
