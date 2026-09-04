# 0132 — The AGS client lives in `app/lti/`, copies the roster sync's shape, and never retries

## Context

E3-04 is the first code in this repository that calls a platform's Assignment
and Grade Services. Three construction questions come with it and the spec
answers none of them.

**Where it lives.** SPEC §13 puts `ags.py` in `backend/app/lti/` and puts
`nrps.py` there too — and the roster client was built at
`backend/app/services/roster_sync.py` instead. Two siblings in two places is
the thing to avoid, so this ticket had to either follow §13 and leave the
roster where it is, or move the roster and leave §13 disagreeing with itself in
the other direction.

**What shape it takes.** `roster_sync.py` already solved the conformance
problems an outbound service client has, and solved them under review: the
transport arrives as a constructor argument so a test can drive it; redirects
are off, because a redirect is a bypass of the address check; every
platform-chosen URL is judged before it is dialled and the connection is pinned
to the address that was judged, which closes the rebinding window between the
two; and the registration is resolved from the section's own deployment, so a
token minted for one platform is never presented to another. A second client
either repeats that or invents a second answer to each.

**What happens when a post fails.** The roster sync has no retry: a failed page
is recorded and the next hourly walk is the retry. Grade passback has an
operator watching a gradebook that stopped updating, which is a different
audience, so whether the same answer holds is a real question.

## Decision

**The client is `backend/app/lti/ags.py`, and the roster client stays at
`app/services/roster_sync.py`.** SPEC §13 is followed for the new module and
the existing one is not moved. The roster client is confidentiality-critical,
works, and is covered by a suite that names its module; re-homing it to satisfy
a diagram would be a rename touching every one of those for no behaviour. The
disagreement is recorded here and in `backend/app/lti/__init__.py`'s docstring
rather than left to be discovered, and what would change the answer is a ticket
that has a reason to open `roster_sync.py` anyway.

Platform profiles are at `backend/app/lti/platforms/`, which is §13's home for
them and has no incumbent.

**The client copies the roster sync's shape, function by function, with each
copy's docstring naming its sibling.** `_no_redirects`, `_pinned`,
`_platform_for`, `_registration_for`, `_answered_status`, `_record_call`, and
the RFC 8288 `Link` reader are all copies. The one thing shared rather than
copied is `PinnedResolutionAdapter`, which is imported: it is a security
control, and a security control with two implementations is a control with one
of them out of date.

**There is no retry and no backoff in the client.** One attempt per HTTP call.
What an operator sees of a failing post is the `ags_call` row — the URL, the
status, the instant and the section (SPEC §6.1) — where a NULL status means the
call never reached the platform (ADR 0129) and a status means it was refused.
E3-06's scheduled sweep is the retry, and it is where a policy about *when* to
try again belongs, because it is the only thing that knows what has already
been posted.

## Alternatives rejected

**Move `roster_sync.py` to `app/lti/nrps.py` so both siblings sit under §13.**
The tidiest end state, and it costs a rename of a module that four suites, two
ADRs and a Celery task name by path, in a ticket whose subject is grade
passback. A refactor of a confidentiality-critical client riding in a ticket
that also turns on credential enforcement across a service surface is two risky
changes in one review. Left undone deliberately; the cost of leaving it is one
paragraph of explanation in two places, which is what this record and the
package docstring are.

**Put the AGS client in `app/services/` beside the roster, matching the
repository rather than the spec.** Symmetric, and it would put the module
somewhere §13 does not name — so the next reader looking for `ags.py` where the
spec says it is finds nothing, and the spec would have to move to describe a
layout nobody chose on purpose. Following §13 where there is no incumbent costs
nothing.

**Copy `PinnedResolutionAdapter` too, keeping `app/lti/` free of any import
from `app/services/`.** Cleaner on layering, and it duplicates about 120 lines
of DNS-rebinding defence. The pin is the layer behind the address rules and it
is only reached when they are removed, so a stale copy of it would be a control
that looks present and is not — `docs/MISTAKES.md` entry 13 with a security
consequence. The import direction is the smaller cost and it is stated here
rather than hidden. Rehoming the adapter and the `Link` reader to a module both
clients can import is the follow-up, and it is a change that crosses a module
boundary rather than something this ticket takes.

**Retry inside the client, with backoff.** It is what a reader expects to find,
and it is wrong here twice over. A retry loop inside one post has no memory
across runs, so it cannot tell a transient failure from a platform that has
been refusing this deployment's credentials all week — and against a platform
under load, a client retrying per section is every section retrying at once.
Every failure this client can meet is either recorded and retried by the next
sweep, or is a 409, which is the one refusal a retry cannot fix.

## Consequences

- Two service clients in two packages, permanently until something moves them.
  `app/lti/__init__.py` says so, so a reader looking for the roster client under
  §13's `nrps.py` is told where it is instead of finding an absence.
- `app/lti/ags.py` imports one public name from `app/services/roster_sync.py`.
  That is the only edge from `lti/` into `services/` in this repository, and it
  is the thing to look at first if the layering is ever tightened.
- The RFC 8288 `Link` reader now exists twice, in two modules, guarding the same
  hazard. Both copies say so and name the other. It is the duplication most
  likely to be repaired by the follow-up above.
- An operator debugging a stalled gradebook reads `ags_call` and gets one row
  per HTTP call rather than a retry storm. A section whose posts are failing
  shows the same status once per sweep, which is a rate an eye can read.
- A client that does not retry can be called twice in quick succession by a
  caller that does. ADR 0052 is what makes that safe: an identical body at an
  equal timestamp is accepted as a retry rather than doubled.
