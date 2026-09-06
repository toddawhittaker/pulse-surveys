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
"Owned by the spec already" list passes through with one change: E3's own row
is closed — grade passback is built, and the superseded validity-state
reading is recorded in the source entry as amended.

`../e3/deferred.md` holds one entry after the cleanup pass, re-listed below.

## A lowered participation score is not announced, and nothing explains the credit rule to anybody

The one `deferred.md` entry, and E3-08's own first named item — the same
subject, carried once. §3.3 now records that v1 does not announce a downward
adjustment, and the AGS comment's ledger is the entire disclosure of §3.4's
arithmetic (ADR 0125 records that instructors read it too).
**Owner:** E8's student results view for the student half; E4's report
surfaces for the instructor half; whichever ships first takes the copy
question with it. **Done when:** `../e3/deferred.md`'s — a student can read,
on a Pulse surface, what a week's credit is made of, what a blank optional
comment costs, and that a posted score can move down on a later
re-classification.

## Comment de-anonymization by completion pattern

Accepted in ADR 0125 on the ground that a weekly-updated score already
carries the same signal through its deltas.
**Owner:** E4 and E6, the epics that render comments beside a roster.
**Done when:** each states in writing that its suppression holds against a
reader who also has the gradebook open, or changes what it suppresses.
Nothing was owed inside E3.

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
custody, none touching a person. `PERSON_TABLES` is unchanged. The
structural source remains E13's at the latest, and every epic keeps asking
the question of the tables it adds.

## The TypeScript 7 pair waits on typescript-eslint

Checked at the E3 boundary on 2026-09-05: latest `typescript-eslint` is
8.69.0 and declares `typescript >=4.8.4 <6.1.0`, so 7.x was not admitted
during E3 and the wait continues — a re-carry with a dated fact.
**Owner and done when:** unchanged from the source entry.

## The session-read sweep's two disclosed limits

Re-affirmed at the E3 boundary: criterion 7's planted violations in
`services/grading.py` and `lti/ags.py` were both named by the sweep's red
(`../e3/boundary-review.md` holds the run), and E3 added no route-serving
package outside `backend/app/`, so the disclosed limits (computed-name
indirection; anything outside `backend/app/`) stand as disclosed.
**Done when:** unchanged from the source entry.

## The rewound-clock family, enriched by what E3 learned

The wedge itself stands as carried (rewind plus a sync silently stops one
section's roster updating; development only). E3-08 added the sharper fact:
§3.4's tier-3 comparison crosses clock currencies — `started_on` is a
dev-clock day while the first-sync day derives from real-time
`nrps_call.called_at` — so a dev-clock drive's tier answers depended on the
calendar date CI ran on until ADR 0142 pinned the dev sync control's log
rows to the effective clock. Production sees one currency and is unaffected.
**Done when:** the source entry's, unchanged — and any later work on the
dev clock reads ADR 0142 first.
