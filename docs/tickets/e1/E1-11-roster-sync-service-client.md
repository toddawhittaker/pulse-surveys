# E1-11 — The roster sync is a conformant service client

**ID:** E1-11
**Branch:** `e1/roster-sync-service-client`
**Depends on:** E1-06, E1-10
**Security-relevant (⚠ line-by-line):** the client-assertion signing path (the
tool's private key in use), and every write of enrollment and INSTRUCTOR
assignment rows.

## Context

The exit clause this ticket exists for: "a roster read succeeds as an
authenticated service call, not an unauthenticated GET." The carried
client-credentials entry defines conformant: a token requested with a
tool-signed assertion, attached to every service call, the way `pylti1p3`'s
`ServiceConnector` performs it — and it points, by name, at
[`../e0/E0-35-the-writer-and-the-marker-nobody-routed.md`](../e0/E0-35-the-writer-and-the-marker-nobody-routed.md)
item 3 as required reading before writing the sync, because this module writes
`enrollment` and the `INSTRUCTOR` `role_assignment` — two of the four
relations the chokepoint guards — through the mechanism E1-10 settled.

SPEC §7.3 gives the schedule (hourly, plus launch-triggered and debounced) and
the discovery rule (the stored address from E1-10 is the only way the
scheduled job learns a section exists; a section with no stored address is
**never-synced**, a state distinct from empty, and stays visible as such).
ADR 0048 gives the enrollment-window extension, including the one seeded
member who carries none. ADR 0023's exclusion constraint already refuses
overlapping enrollments; the sync must live with it rather than around it.

Read first: E0-35 item 3 (the pointer the carried file makes mandatory);
ADR 0048 in full (window semantics, the member with none); ADR 0050 (emails,
no names — the sync must not invent name storage); ADR 0023; SPEC §7.3, §3.4
(what windows feed — the formula itself is E3's); §9.1 (NRPS paging is a
named test surface); ADR 0044 and §2.1 (INSTRUCTOR assignments join the
graph with no `reports_to` edge in E1 — edges are E9's admin surface).

## Scope

- The NRPS client through `pylti1p3`'s service machinery against E1-06's
  grant: token request with tool-signed assertion, token attached, container
  followed across **pages** (the mock's roster pages; §7.3 names NRPS paging
  a per-platform deviation, so the pagination handling lives where the
  adapter seam can reach it later, without building E3's adapters now).
- The hourly beat job walking stored addresses; the staff-launch trigger from
  E1-10 debounced (window: the builder's call, recorded); both paths converge
  on one sync routine.
- Member ingestion through the sanctioned-writer mechanism: `enrollment`
  rows with windows from the ADR 0048 extension — the member with no
  extension gets the absent-window state §3.4 expects (store the absence
  honestly; do not synthesize a start date — the denominator that reads it is
  E3's); `Active`/`Inactive`/`Deleted` transitions recorded (a drop ends the
  enrollment; ADR 0023 governs re-adds); the teaching instructor's
  `INSTRUCTOR` `role_assignment` per section, `reports_to` null, through the
  same mechanism; emails stored where exposed (ADR 0050's fields and no
  more).
- Never-synced remains visible: a section provisioned by a student launch
  (no address) is distinguishable from a synced-empty section in whatever
  record the job writes — E11's console reads it later; E1 asserts the state
  exists.
- Sync outcomes logged per §6.1's eventual needs (calls, response codes) —
  the log record, not the console.

## Acceptance criteria

1. The integration test performs the roster read exactly as the carried entry
   demands — token requested with a tool-signed assertion, attached,
   container returned — and a test proves the *unauthenticated* GET path no
   longer exists in the client (the forbidden state asserted).
2. A multi-page roster ingests completely; the page boundary is covered by a
   fixture that would catch off-by-one-page (first page alone satisfying the
   test is MISTAKES entry 3's shape — assert the member the *last* page
   holds).
3. The windowless member lands with an honest absent window; the windowed
   members carry RFC 3339 offsets end to end (naive datetimes are refused by
   the column type — ADR 0019 — so this is asserted at the boundary).
4. Adds, drops, and re-adds across two sync runs produce the enrollment
   history ADR 0023 permits; a mid-term add's window start is the extension's
   value, not the sync time.
5. The E0-35 sweep passes with the sync as a sanctioned writer; a planted
   unsanctioned write in the sync module still fails it.
6. Idempotence: running the sync twice against an unchanged roster changes no
   row (MISTAKES entry 31: prove it against a database the sync did not
   itself fill — seed one member out-of-band first).

## Out of scope

- The participation denominator (E3 reads the windows; §3.4).
- AGS anything (E3). Platform adapters (E3). Person/identity rows (E1-12).
- Email *sending* (E12; addresses are stored only).
