# E1 deferred-item cleanup plan

Written after E1-15 merged (PR #110, `5c1b4f1`), before the epic-boundary
reviews, which wait on this plan's build batches. Scope: every item still
open in [`deferred.md`](deferred.md) and
[`../e2/carried-from-e1.md`](../e2/carried-from-e1.md). The question asked
of each: can it be resolved *now, inside E1*, without building against
machinery a later epic owns — and if not, exactly why not.

Three dispositions. **Build now**: self-contained, needs nothing a later
epic creates, lands as a normal ticket-shaped batch below. **Decision**:
resolvable by a ruling rather than by code; each gets a recommendation and
waits for the ruling. **Stays carried**: resolving it now would build
against structures that do not exist yet, or reopen a decision made
deliberately days ago with no new facts — each carries its one-line why.

## Disposition of every open item

| Item (source) | Disposition |
|---|---|
| Catalog sweep misses the whole-row join form (E1-01 d.1) | **Build now — Batch A** |
| Name-sweep passes over tables it recognises nothing in (E1-01 d.2, second half) | **Build now — Batch A** |
| Structural source for `PERSON_TABLES` (E1-01 d.2, first half) | **Attempt in Batch A**; falls back to carried (E13) if no honest source exists |
| `://`-mark literal check beside the console sweep (PR #110 review note) | **Build now — Batch A** (one line, rides along) |
| Mock IdP unpadded-spelling pin (E1-06 d.3) | **Build now — Batch B** |
| Served defect-selector vocabulary (E1-07 d.1) | **Build now — Batch B** |
| Permissive-alg mint and the end-to-end algorithm-pin proof (E1-08 d.1) | **Build now — Batch B** |
| Machine-readable reason marker on the refusal page (PR #110 review note) | **Build now — Batch B** (companion to the pin proof, same page) |
| Address rules resolve and pin, both surfaces (E1-05 d.2 + E1-11 d.1) | **Build now — Batch C** |
| Registration write-time chokepoint made structural (E1-05 d.3) | **Build now — Batch C** |
| Security response headers (E1-04 d.2) | **Build now — Batch D** |
| Webfonts (E1-04 d.1) | **Decision 1** |
| Logout / back-channel logout (carried, unscheduled) | **Decision 2** |
| Local-account fallback (carried, unscheduled) | **Decision 3** |
| Deep Linking (carried, unscheduled) | **Decision 4** |
| Owners assigned by E1-15 with no prior record | **Decision 5** |
| TypeScript 7 pair (E1-03 d.1) | **Stays carried — re-measured 2026-08-28**: `typescript-eslint` 8.68.0 still pins `typescript >=4.8.4 <6.1.0`, so the pair is blocked upstream, not by this repo |
| Production signing-key supply and rotation (E1-05 d.1) | **Stays carried (E3)** — no deployment exists to shape the supply route against; ADR 0082 already rejected the config-variable route, and inventing the mechanism before the first real platform fixes its shape in the wrong ticket |
| AGS token enforcement (fix-round entry) | **Stays carried (E3)** — ADR 0099 decided this deliberately this week: enforcement pairs with the first AGS client, and none exists; reopening a fresh decision with no new facts is churn |
| Squatted section binding rebind/retire (E1-10 d.4) | **Stays carried (E11)** — the repair needs an operator surface and a who-may-rebind authorization rule; neither belongs on a launch path, and building an interim admin mechanism now shapes E11's console in its absence |
| Web-login linkage provisioning (E1-12 d.2) | **Stays carried (E9/E11)** — the write needs whatever authorization that surface uses; `pulse_app` holding no grant on the table is the current guarantee, and a stopgap writer would spend it |
| Reveal-subject guard (carried from E0, restated) | **Stays carried (E4)** — the guard binds the reveal's subject to a Care case, and Care-case machinery is E6/E10's; the spec's own deadline (before any instructor-facing roster surface) is the strongest record this repo has, and nothing E1 shipped makes the path reachable |
| Scope-superstring residue (PR #109) | **Stays carried (conditional)** — nothing to build until a ticket widens `ADVERTISED_SCOPES` |

## Batch A — the sweep closures (heavy lane)

One subject: the §4.1 sweeps stop trusting what they cannot see.

1. **The catalog half flags a whole-row read in the presence of a join**
   (E1-01 d.1's done-when governs). Postgres drops the `refobjsubid = 0`
   dependency row once a view also names a column of the same table, so the
   mechanism is the one the entry records: for each guarded table a view
   holds any dependency edge to, compare the recorded column set against
   `pg_get_viewdef`'s text for a whole-row use of that table's alias, and
   fail on a whole-row form the column-grain rows do not explain. Proven by
   the existing planted join-form control
   (`SELECT to_jsonb(u) FROM enrollment e JOIN "user" u …`), which today
   passes both halves.
2. **The reached-table report** (E1-01 d.2, second half). The fixed-point
   walk in `test_identity_column_marker.py` already knows every table it
   reaches; the closure is: a reached table must have at least one column a
   fragment recognises, or a whole-table marker (ADR 0022's third shape),
   or an explicit entry saying it carries nothing — anything else is a
   failure naming the table, never a silent pass. `web_login_subject` is
   the measured case that motivates it: `idp_subject` matches no fragment
   and never will.
3. **Attempt a structural source for `PERSON_TABLES`** (first half of the
   same entry). Candidate: the union of the root identity tables and every
   table the FK walk reaches, so the hand-written list shrinks to the roots
   that cannot be derived. If no source survives contact with the schema —
   a real possibility — the attempt is recorded and the item stays carried
   to E13, with item 2's report as the compensating control (a list that
   can silently omit matters much less when the walk reports what it
   cannot classify).
4. **The one-line `://`-mark literal check** in
   `test_the_dev_console_names_nobody.py`, mirroring `ADDRESS_MARK` — the
   PR #110 reviewer's escaping-independent complement to the exact-string
   address set.

Heavy because it is the §4.1 guard surface. Mutation battery: each closure
proven against its planted case (the join-form control, an unmarked
reachable table, an escaped address).

## Batch B — the mock speaks every wrong sentence (heavy lane)

One subject: closing the proof gaps on the mock platforms' signing and
defect surfaces.

1. **The permissive-alg mint and the end-to-end pin proof** (E1-08 d.1's
   done-when governs). A mock variant publishes a key set a confused
   verifier would accept `alg: none` or HS256 against; an end-to-end
   refusal test drives a launch signed that way and asserts the door still
   refuses it — so removing `_refuse_unpinned_algorithm` turns a green
   launch red, which today it does not (the verifier's one recorded
   survivor from E1-08).
2. **The machine-readable reason marker on the refusal page** — a
   `data-reason` attribute carrying the guard's own name beside the prose.
   It adds no disclosure (the per-guard prose already distinguishes the
   guards) and it decouples E1-15's refusal specs from error copy; those
   specs switch to the marker and keep one prose assertion as the copy
   canary. Done here because item 1 adds refusal cases to the same page,
   and the next toucher was always going to be this batch.
3. **The served defect vocabulary** (E1-07 d.1's done-when governs): the
   mock serves its own selector list (a `/mock/defects` route), a test pins
   the served list to `ALL_SELECTORS`, and both copied literal sets — the
   integration suite's and `exit-refused-launches.spec.ts`'s — assert
   against the served list.
4. **The mock IdP's unpadded-spelling pin** (E1-06 d.3): the third encoder
   gets the same test as the other two, proven against the same
   `.rstrip(b"=")` mutation before being trusted.

Heavy because items 1 and 2 touch launch validation and its refusal page.

## Batch C — addresses are judged as addresses (heavy lane)

One subject, the composed fix E1-05 d.2 and E1-11 d.1 were merged into,
plus the chokepoint that guarantees future writers meet it.

1. **Resolution and judgment at both surfaces.** The registration-write
   rules and `refuse_invalid_fetched_address` resolve the host and refuse
   any resolved address that is not `ip.is_global` (RFC1918, loopback,
   link-local, carrier-grade NAT). The development stack's exemption is the
   rule the E1-11 entry already names: the section's own stored roster
   host — judged at registration-write time, where the development
   environment's rules deliberately admit the mock — is exempt at fetch
   time; a `rel="next"` hop to any *other* host gets the full resolved
   judgment. That closes the residual MEDIUM (a registered platform
   pointing a tokened GET at an internal service behind a valid
   certificate) without breaking the mock's private-network address.
2. **The pin.** The connection is made to the address that was judged —
   resolve once, connect to that address with the hostname preserved for
   TLS verification — so a DNS rebind between check and GET swaps nothing.
   In `requests` this is a transport adapter; the test pair is a stub
   resolver that answers differently on its second call, defeated by the
   pin, beside a plain pair on both sides of `is_global`.
3. **The chokepoint becomes structural** (E1-05 d.3): a
   `before_insert`/`before_update` mapper event on `LtiPlatform` calls
   `refuse_invalid_registration_addresses`, so a future writer cannot skip
   it by not knowing to call it; the raw-SQL writer ADR 0081 records stays
   the documented residue.

Heavy: SSRF surface, token-bearing requests. This batch closes the only
open finding with a severity attached (the residual MEDIUM), which is why
it runs first.

## Batch D — the response headers (heavy lane, with an ADR)

E1-04 d.2's done-when governs: the app factory attaches a deliberate header
set to every response — a CSP that admits what the bundle legitimately
loads and refuses inline script, `X-Content-Type-Options: nosniff`, a
`Referrer-Policy`, and a `frame-ancestors` naming who may frame the app —
with a test pinning each header.

The design decision that needs the ADR: `frame-ancestors` must admit the
platforms that legitimately frame launches, and the browser-facing origin a
registration exposes is its `authorization_endpoint` — so the directive is
derived from the registered platforms' origins plus `'self'`, which keeps
the policy a property of the registration table rather than a hardcoded
list. Two verification steps the batch owes: confirm the built bundle needs
no inline script or style the CSP would have to bless (Vite production
output should not), and run the full e2e suite against the enforced headers
— the launch iframe path is exactly what a wrong `frame-ancestors` breaks,
and the suite's cookieless spec is the canary.

## The decisions

1. **Webfonts** (E1-04 d.1). Recommendation: **keep the deferral to E2's
   first real screen**, as recorded. The deferred entry's reasoning — the
   choice between self-hosting and shipping fallbacks deserves a real
   screen to be judged against — still holds, and deciding blind now saves
   nothing later.
2. **Logout**. Recommendation: **schedule in E9**, beside the role switcher
   and the admin surfaces — the people who need a session to end before its
   hour expires are the web-door roles E9 serves, and the Care queue (E10)
   should not ship without it, which E9-before-E10 satisfies in the current
   order.
3. **Local-account fallback**. Recommendation: **decide at E13** — it is
   release-readiness insurance against the pilot IdP falling through, and
   E13 is where that risk is either real or expired; if expired, the §7.1
   sentence is deleted there.
4. **Deep Linking**. Recommendation: **record as post-v1 in §7.3** unless a
   real platform demands it, in which case it is E3's (the epic that meets
   real platforms). Either way the spec sentence changes, which is a spec
   edit and Todd's.
5. **The owners E1-15 assigned without a prior record** (flagged in
   `carried-from-e1.md`): Batch A resolves two of them by building the
   items; the rest stand for confirmation — E13 for the alg-pin proof
   becomes moot (Batch B builds it), so what actually remains to confirm is
   E13 as the fallback owner for the structural `PERSON_TABLES` source.

## Order, process, and what the boundary waits on

Batches run **C → A → B → D**: C closes the only open finding with a
severity, A closes the guard blind spots the reviewers rely on, B closes
the proof gaps, D lands last because its e2e verification wants the other
batches' suites stable. Each batch is one ticket branch and one PR into the
epic under the standing loop — tests first, independent verification,
mutation proof, fresh-context security review; nothing here relaxes because
the items are "cleanup." The decisions can land at any point; none blocks a
batch.

When the four batches are merged and the five decisions recorded, the open
set is exactly the stays-carried table above — every entry blocked on a
later epic's machinery by named reasoning, none on effort. That is the
state the epic-boundary reviews and the exit checklist then run against.
