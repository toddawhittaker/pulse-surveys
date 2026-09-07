# Carried from E3 into E4

Things E3 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E3-08.
Entries point at the record that owns the detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e3/carried-from-e2.md` not closed inside E3, plus every entry of
`../e3/deferred.md` still open after E3-08's cleanup pass, plus everything the
E3 boundary reviews found and did not fix inside the epic, appears here.** The
demonstration is the ledger below: every source entry is named with what
happened to it, in the source file's own order. Nothing was dropped silently.

## The ledger: every `carried-from-e2.md` entry, dispositioned

Closed inside E3 (each closure is recorded in the source file itself, with
what closed it):

1. **A non-development deployment has no way to supply the tool's signing
   key** — closed by E3-01 (#169). Its rotation rule was then revised at the
   E3 boundary: ADR 0143 supersedes ADR 0127 in part (the oldest live key
   signs), because newest-signs defeated the ADR's own wait-then-retire
   procedure against platforms that cache a key set.
2. **AGS still answers without a token** — closed by E3-04 (#170).
3. **The mock's scope check is only provably a membership check while no
   advertised scope is a superstring** — closed by E3-04 (#170).
4. **Nothing structurally forces the next mutating route onto the CSRF
   dependency** — closed by E3-07 (#177).
5. **The launch-path roster enqueue still waits six seconds on a broker that
   is down** — closed by E3-05 (#171).

Re-carried below with a new dated fact: the `PERSON_TABLES` standing
question, the TypeScript 7 pair, the session-read sweep's limits, and the
rewound-clock family. Carried through unchanged (the source entry's owner and
done-when govern; nothing about them moved in E3): the registration
chokepoint's CSP-breaking endpoint (E11); the squatted section binding (E11);
the web-login linkage provisioning (E9's People editor or E11's console);
logout and back-channel logout (E9); the local-account fallback (E13); the
reveal-subject guard with its E4 deadline; the two registration-write blind
spots (E11 to-know); the generative purview coverage note (E9); the
denial-module closure sweep's inventory note (see also the new entry below —
the E3 boundary widened the inventory and sharpened the disclosed limit); the
bounced verdict rows' cap and aggregation halves; the unproven structural
battery rows; the bounce that names no offending position; the week eyebrow's
course length; the self-hosted font licences (E13); the resubmission that
500s under a rewound clock; the model identifier in three untied places; the
floor-headroom variance point (E10); the copy collector's symlinked-directory
gap (E4); the bounced comment refused before harm screening (E10, with the
E6 hook); the rendered student surface's string convention (E4); and the Care
landing's stale docstring (a light-lane candidate E3 could not take). The
"Owned by the spec already" list passes through with one change: E3's own
row — grade passback reading validity state — is superseded, not closed. The
item-based formula E3 built counts completed items from the answer rows and
each comment's most recent classification rather than reading
`response.is_valid`, and the source entry records the row as superseded and
left as E2's own hand-off, amended rather than rewritten.

`../e3/deferred.md` holds one entry after the cleanup pass, re-listed below.

## A lowered participation score is not announced, and nothing explains the credit rule to anybody

The one `deferred.md` entry, and E3-08's own first named item — the same
subject, carried once. §3.3 now records that v1 does not announce a downward
adjustment, and the AGS comment's ledger is the entire disclosure of §3.4's
arithmetic (ADR 0125 records that instructors read it too).
**Owner:** E8's student results view for the student half; E4's report
surfaces for the instructor half; whichever ships first takes the copy
question with it. **Done when:** `../e3/deferred.md`'s — a student can read,
on a Pulse surface, what a week's credit is made of, that a comment refused
by §3.3 does not complete its item, what a blank optional comment costs, and
that a posted score can move down on a later re-classification.

## Comment de-anonymization by completion pattern

Accepted in ADR 0125 on the ground that a weekly-updated score already
carries the same signal through its deltas.
**Owner:** E4 and E6, the epics that render comments beside a roster.
**Done when:** each states in writing that its suppression holds against a
reader who also has the gradebook open, or changes what it suppresses.
Nothing was owed inside E3.

**E4's half is done, at E4-04, and it changed what it suppresses.** ADR 0153
is the statement: a released comment carries no week attribution anywhere,
because a comment labelled with its week, read beside the per-week completion
ledger the gradebook carries, narrows the author to about one person in a
four-response week. That record also names the residual it does not close — a
term's first release can be attributable by elimination when only one held week
exists — and says why that is accepted. **E6 still owes the same statement for
its moderation views**, which put comments beside a roster with reviewer
decisions attached, and this entry stays open against that epic alone.

## The roster sync's token-acquisition dial is unbounded

E3-05's security round bounded the AGS client's token dial and named the
same defect in `roster_sync`'s `ServiceConnector` as out of scope; PR #171
and #172 both said so, and no durable record carried it until the E3
boundary's docs review caught the gap. A platform that completes the TCP
handshake and stalls on its token endpoint holds the sync worker for the
client library's own default patience.
**Owner:** a candidate ticket for whichever epic next touches the roster
machinery; the shape to copy is the AGS client's bounded transport
(commit 83a18d3). **Done when:** the token dial carries bounded socket
timeouts, measured against a stalling endpoint the way the AGS fix was.

## The gradebook's two instructor-visible strings sit outside the copy inventory

`PULSE_LABEL` ("Pulse Participation") and the ledger line format ship into
an LMS gradebook, and the copy-inventory gate that enforces §4.1 items 4 and
5 collects neither — its governed surfaces are the copy modules, and E3
added none. The ledger's exact format is pinned byte-for-byte by the grading
suites, so the strings cannot drift silently; what is missing is only the
items-4-and-5 vocabulary gate over them.
**Owner:** E4, with the copy-inventory growth over report surfaces.
**Done when:** both strings are collected by the inventory or the inventory
records why the gradebook is not a governed surface.

## The launch door ignores `azp` and reads a multi-valued `aud` as its first element

Pre-E3, found by the boundary's protocol review. LTI 1.3 requires the
client id to be a member of `aud` and, when `aud` is multi-valued, requires
`azp` to name it. Today a legitimate multi-audience launch is refused, and a
token authorized for another tool with the right first element is accepted.
**Owner:** a candidate ticket for whichever epic next touches launch
validation. **Done when:** membership plus the `azp` check, with a test pair
driving both wrong-way cases.

## The platform's JWKS is fetched on every launch, uncached

Pre-E3, same review. Safe for rotation, but a platform JWKS blip stalls or
refuses every launch in progress, synchronously, inside the iframe's
critical path. **Owner:** E11/E13 candidate. **Done when:** a bounded cache
with a stated lifetime, or a recorded decision that per-launch fetch is the
accepted cost.

## The denial-module inventory is a name convention, and the isolated pass has no collection floor

The E3 boundary paid this entry's standing warning twice: the epic's four
new denial modules matched no shape until the round widened the inventory,
and the re-verification battery then proved a marked module could lose its
marker silently because `scripts/ci/check_invariants.py` fails on a skip,
an xfail or an empty collection but not on a *smaller* one — a 230→223 drop
passes both layers. The widened shapes close the instances; the class stays
open. **Owner:** a candidate process ticket. **Done when:** the isolated
pass carries a collection-count floor (or an equivalent the guarded set
cannot shrink), watched failing against a planted marker removal.

## The `PERSON_TABLES` standing question, re-asked and re-carried

E3's answers, recorded at the boundary (`../e3/boundary-review.md`):
`grade_sync` is in the carries-nothing inventory with its column tuple;
`ags_call` is unreached by the person walk (single foreign key into
`section`); the columns E3 added to existing tables are addresses and key
custody, none touching a person. `PERSON_TABLES` is unchanged.
**Owner:** E13 at the latest, as the structural source — and every epic
boundary re-asks the question of the tables it adds in the meantime.

## The TypeScript 7 pair waits on typescript-eslint

Checked at the E3 boundary on 2026-09-05: latest `typescript-eslint` is
8.69.0 and declares `typescript >=4.8.4 <6.1.0`, so 7.x was not admitted
during E3 and the wait continues — a re-carry with a dated fact. What this
repository has installed is unmoved by the check: `typescript` is pinned at
6.0.3 and `typescript-eslint` at 8.68.0 (`package.json`), both inside the
declared range, so the wait costs nothing installed today.
**Owner:** whichever epic is running when `npm view typescript-eslint
peerDependencies` admits 7.x. **Done when:** `docs/tickets/deps-triage-2026-08-24.md`
entry 3's — both majors land in one change, `npm ci` resolves, and the
exact-pin equality guard and all four Node-facing gates stay green.

## The session-read sweep's two disclosed limits

Re-affirmed at the E3 boundary: criterion 7's planted violations in
`services/grading.py` and `lti/ags.py` were both named by the sweep's red
(`../e3/boundary-review.md` holds the run), and E3 added no route-serving
package outside `backend/app/`, so the disclosed limits (computed-name
indirection; anything outside `backend/app/`) stand as disclosed.
**Owner:** each epic's boundary review, which re-affirms the two disclosed
limits; the structural close is E13's at the latest. **Done when:** unchanged
from the source entry.

## The rewound-clock family, enriched by what E3 learned

The wedge itself stands as carried (rewind plus a sync silently stops one
section's roster updating; development only). E3-08 added the sharper fact:
§3.4's tier-3 comparison crosses clock currencies — `started_on` is a
dev-clock day while the first-sync day derives from real-time
`nrps_call.called_at` — so a dev-clock drive's tier answers depended on the
calendar date CI ran on until ADR 0142 pinned the dev sync control's log
rows to the effective clock. Production sees one currency and is unaffected.
**Owner:** a candidate ticket for whichever epic next touches the dev-clock
machinery. **Done when:** the source entry's, unchanged — and any later work
on the dev clock reads ADR 0142 first.

## The flaky fail-closed framing test

`tests/unit/test_the_spa_is_served_from_the_app_factory.py:391`,
`test_the_framing_policy_fails_closed_to_self_when_the_registration_table_is_unreachable`,
turns up red roughly one whole-suite run in six. The mechanism is test
isolation, not chance: the module-level engine in `backend/app/db.py`
(~lines 192-217) is built at import, so under `-n 4` a worker that imported
`app.db` while the database was reachable never takes the fail-closed branch
this test drives. Recorded until now only in PR #172's body and the E3-06
attempts note.
**Owner:** a candidate ticket for whichever epic next touches
`backend/app/db.py` or the app factory. **Done when:** the test forces the
fail-closed branch deterministically and stays green over a stated run count.

## `post_score` returns nothing

`backend/app/lti/ags.py`'s `post_score` (~line 434) returns `None`, and its
caller re-reads the outcome off the row it just wrote
(`backend/app/services/grading.py` ~1198-1219, `_accepted_status`). The
proposal that `post_score` return its own status lives only in that
function's docstring and in PR #172's body.
**Owner:** whichever epic next touches the AGS client. **Done when:**
`post_score` returns its outcome and callers stop re-reading it, or a
recorded decision keeps the `None`.

## Provisioning's separation from the line-item column is docstring-only

`backend/app/services/provisioning.py` (~985-995) states that the
application role's column-scoped `UPDATE` on `section.ags_line_item_url`,
plus `launch_provisioning`'s catalog naming `section`, means a writer added
there would pass both controls — what keeps the column unwritten is only
that a launch never makes the call that produces a line item id. The
declined hardening lives only in PR #171's body.
**Owner:** a hardening candidate for whichever epic next touches
provisioning. **Done when:** a test asserts provisioning writes the column
nowhere, proven against a planted write, or a recorded decision that the
docstring suffices.

## Rehoming the pinned-resolution adapter and the copied Link parser

ADR 0132 (~line 85) proposes, and does not take, rehoming
`PinnedResolutionAdapter` and the `Link` header parser to a module both the
AGS client and the roster sync can import, and moving `roster_sync.py` under
`app/lti/`.
**Owner:** a candidate for whichever epic next restructures the LTI
plumbing. **Done when:** rehomed per the ADR, or a recorded decision to keep
the copies where they are.

## The clock routes lack the origin check

ADR 0141 (~lines 113-118) names retrofitting the same-origin check onto
`/dev/clock` and `/dev/clock/clear` as a strict improvement deferred to a
ticket that is about those routes, because doing it in E3-07 would have
deleted the CSRF ledger's only worked example.
**Owner:** a candidate ticket for whichever epic next touches the dev-clock
routes. **Done when:** both routes carry the check and the ledger's
both-direction assertions are re-proven on what remains.

## The signing-key supply path has no runbook

ADR 0126 says the operator command `scripts/signing_key.py` is documented
only by its own `--help`, and that a deployment runbook is owed by E13; no
ledger entry carried that obligation forward.
**Owner:** E13. **Done when:** a runbook documents supply and rotation,
naming `scripts/signing_key.py`, ADR 0126, and ADR 0143's selection rule.

## The daily purge of the launch replay ledger cannot run

Not an E3 item — found by FIX-04's Celery drive on 2026-09-06, and live since
E1-08 shipped the ledger on 2026-08-26. The beat entry
`app.jobs.tasks.purge_launch_nonces` raises
`psycopg.errors.InsufficientPrivilege: permission denied for table
lti_launch_nonce` every run. The cause is not the runtime move and not the task:
`backend/app/views_sql/lti_launch_nonce_grants_v001.sql` grants `pulse_app`
`INSERT, DELETE` and withholds `SELECT` on purpose, and Postgres requires
`SELECT` on the columns a `DELETE ... WHERE` reads — the purge deletes on
`expires_at`. Measured as `pulse_app` on the dev database: `DELETE ... WHERE
expires_at < now()` refused, the same `DELETE` with no `WHERE` permitted, the
same `DELETE ... WHERE` on `lti_launch_state` permitted because that table's
grant includes `SELECT`. The launch path itself is unaffected — `claim_nonce`'s
`INSERT` is permitted — so what this costs is the ledger's expired tail, which
ADR 0089 says the daily purge exists to reclaim: the table grows without bound.
The half of the task that purges `lti_launch_state` never runs either, because
the nonce half raises first.

Nothing about this was fixable inside FIX-04: widening the grant means a
`GRANT SELECT` (or a column-scoped one on `expires_at`), a decision about what a
role that can enumerate spent nonces learns, and a matching entry in
`RUNTIME_BASE_TABLE_PRIVILEGES` — which lives behind the test wall.

**Owner:** whichever epic next touches launch validation or the runtime grants;
a candidate for a standalone fix ticket, since it is small and currently silent.
**Done when:** the purge completes as `pulse_app` against a table holding
expired rows, proven by driving the task rather than by reading the grant, and
the privilege record names whatever was added with the reason `SELECT` was
withheld in the first place.

**Closed by E4-14.** `lti_launch_nonce_grants_v002.sql` grants `pulse_app` the
column-scoped `SELECT (expires_at)` the purge's own `DELETE ... WHERE` needs;
`RUNTIME_COLUMN_PRIVILEGES` in `tests/integration/test_identity_grants.py`
records it, beside a direct-query negative control proving `nonce` itself
stays unreadable. `tests/integration/test_the_launch_replay_purge_runs_as_pulse_app.py`
drives `purge_launch_nonces` as `pulse_app` against a table seeded with an
expired and a live row in each of `lti_launch_nonce` and `lti_launch_state`:
the task completes, the expired rows are gone, the live rows are intact, and
the `lti_launch_state` half — the latent failure this entry names explicitly —
now runs too. ADR 0150 records why `SELECT` was withheld in E1-08 and what
this one-column widening concedes.

## ruff still lints as though the runtime were Python 3.13

Not an E3 item — added by FIX-04, which moved the runtime to Python 3.14.
Every place that declares the version says 3.14 now except one:
`[tool.ruff] target-version` in `pyproject.toml` stays `"py313"`, because the
pinned ruff, 0.6.9, does not know `py314` and refuses the value outright.
The consequence is small and worth knowing: ruff's version-gated rules and
its formatter target a language one minor behind the interpreter, so a 3.14-only
syntax or a rule that fires only from 3.14 is not seen. A comment beside the
line says the same thing, and FIX-04's runtime-declaration guard deliberately
does not read this key, so nothing goes red while it waits.
**Owner:** whoever takes the next ruff version bump — Dependabot's `pip`
ecosystem proposes it. **Done when:** `target-version` says `py314` and the
pinned ruff accepts it, proven by a `ruff check` that exits 0 rather than by
the version number alone.
