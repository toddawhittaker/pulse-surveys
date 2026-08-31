# 0096 — Every roster URL the walk fetches is judged, and the teaching-instructor write is bounded by a definer

## Context

E1-11's per-PR security review found two holes in the roster sync, one HIGH and one
MEDIUM. Both are construction decisions a reasonable engineer would make
differently, and SPEC settles neither, so this record exists. It sits beside
[ADR 0095](0095-the-roster-syncs-enrollment-windows-and-what-it-refuses.md) (the
sync's window semantics) and extends
[ADR 0081](0081-a-registrations-addresses-are-refused-at-one-write-time-chokepoint.md) (the fetched-address
rules) and [ADR 0090](0090-a-sanctioned-writer-passes-the-chokepoint-by-being-in-a-catalog.md)
(the sanctioned-writer chokepoint).

**F1 (HIGH, SSRF).** A roster walk does not fetch one address. It fetches the stored
one, then whatever the platform's `Link: rel="next"` header names, then that page's
`next`, each with the tool's Bearer token attached. E1-10's round 3 judged the
*stored* address against `refuse_invalid_fetched_address` — rule 4 was added there
against `169.254.169.254`, the cloud metadata service — and the walk then adopted a
URL the platform chose at run time and judged none of it. One `Link` header and a
compromised or hostile platform gets an authenticated GET to any address the worker
can route to, its response parsed as a membership container.

**F2 (MED).** `roster_sync_grants_v001.sql` granted `pulse_app` a table-wide
`INSERT` on `role_assignment` so the sync could write the teaching instructor's row.
`guard_write` refuses only an `INSTRUCTOR` row, and that is a *Python* rule — so the
connection every screen in the product runs on could write a `CARE` assignment, the
row E0-10's reveal definers check for before they return a name (§6.2, §4). Before
this ticket `pulse_app` held nothing on that table and the database was the control.

## Decision

**F1 — every URL the walk is about to fetch passes the fetched-address rules before
the GET.** The stored first page and every `rel="next"` go through
`refuse_invalid_fetched_address(settings.environment, column=lms_context_memberships_url, …)`.
The environment reaches the rules from `Settings`, threaded through `sync_section`,
never from `os.environ` — that read is the anti-pattern deferred E1-10 item 5
removed from the writer next door. Three further points:

- **Loopback joins link-local as a refusal on the roster service address, and on it
  alone among the fetched columns.** Link-local (rule 4) already covers all three
  fetched columns. Loopback did not: rule 3 refused it on `authorization_endpoint`
  only, on the reasoning that a browser resolves that string. A server-side fetch
  makes loopback an SSRF target that reasoning never covered — but only where the
  *URL is chosen by the platform*. The roster's pagination `next` is; `jwks_url` and
  `auth_token_url` are written by the registration writer under an operator's own
  hand, and a platform component reached as a loopback sidecar in the same pod is an
  ordinary deployment ADR 0077 protects by name. So loopback is refused on the
  roster address column (`LOOPBACK_REFUSED_COLUMNS = (authorization_endpoint,
  lms_context_memberships_url)`) and accepted on the two registration-fetched
  columns. See "Alternatives rejected".

- **Redirect-following is off on the sync's transport.** A 30x is the same bypass
  arriving before the `Link` header: the address that passed the rules is not the
  address the request ends at. `requests` has no session-level `allow_redirects`
  and `pylti1p3`'s `ServiceConnector` calls `get`/`post` without the per-request
  flag, so the lever is `max_redirects = 0`, which makes any redirect raise
  `TooManyRedirects` (recorded as a refused call) rather than being followed.

- **A refused fetch is recorded against the section's stored address, not the
  hostile URL**, `response_code` NULL, the refused URL in the log line only —
  writing a platform-chosen URL into a record a console reads back is a second
  channel. The walk stops there and keeps what earlier, validly-fetched pages
  already read (a class that synced correctly up to a hostile second page is not
  thrown away), and `_ingest` skips its close-the-vanished pass on a truncated walk,
  so a student on a page never fetched is not ended.

**F2 — the teaching-instructor write moves into a SECURITY DEFINER function and the
grant is dropped.** `GRANT INSERT ON role_assignment TO pulse_app` is gone.
`public.record_teaching_instructor(in_person_id uuid, in_section_id uuid)` in
`teaching_instructor_v001.sql`, owned by a new NOLOGIN `pulse_instructor_definer`
holding `INSERT` and `SELECT` on `role_assignment` and nothing anywhere else, writes
a row with `role` hardcoded to `'INSTRUCTOR'` and `reports_to` NULL — the value is
the body's and the signature has nowhere to put another. It is idempotent on its own
(an existence check, since `role_assignment` carries no unique constraint). The sync
calls it where it used to INSERT, and still calls `guard_write` there and still
reads `assignment_scope` first: three layers, none of them the only one. This
mirrors `record_roster_email` (ADR 0095, D7), which bounds its write to an address
and never a name for the same reason.

## Alternatives rejected

**F1 — validate only the stored address.** What ships until the review: the stored
address is judged and the pagination URL bypasses it. That is the finding.

**F1 — refuse loopback on all three fetched columns**, as the review's wording
first put it. It refuses a legitimate operator-registered sidecar on `jwks_url` /
`auth_token_url`, which `tests/unit/test_registration_address_constraints.py::test_a_loopback_fetched_address_is_accepted_outside_development`
asserts is accepted and which ADR 0077 protects by name. The security property is
about *who chose the address*: the platform chooses the roster's pagination URL and
an operator chooses the registration columns, so the split is by column, not "all
fetched columns". (The implementer narrowed the review's wording to the roster
column for exactly this reason and recorded it here rather than quietly.)

**F1 — follow redirects and re-judge the destination.** Judging then following
validates nothing about where the request ends; and a re-judge after each hop is a
larger surface than refusing redirects, which no legitimate NRPS service needs.

**F2 — a narrower grant, `INSERT` on `role_assignment` limited to columns.** A grant
bounds a table and its columns; it cannot bound a column's *value*. There is no
`GRANT INSERT (role = 'INSTRUCTOR')`, so no grant makes "may write an instructor and
nothing else" a property of the database. Only a function whose body writes the
value does.

**F2 — keep the grant and rely on `guard_write` alone.** `guard_write` is a Python
rule on one code path; the grant is what a second writer, a raw SQL statement, or a
future call site is bounded by, and it let a `CARE` row through. Defence in depth
means both, with the database as the layer that holds when the application layer is
bypassed.

## Consequences

- The fetched-address rules now have a caller per fetched URL rather than per stored
  row; `refuse_invalid_fetched_address` is called inside the walk loop.
- `pulse_app` holds no grant on `role_assignment` again, and the write is a definer
  door beside the email and resolver doors — the identity-grant inventory in
  `tests/integration/test_identity_grants.py` gains `record_teaching_instructor` and
  `pulse_instructor_definer`.
- **The E0-35 static sweep can no longer see the `role_assignment` write in
  `roster_sync.py`**, because it is now a SQL function call rather than a syntactic
  INSERT. That is the subject of dispute `docs/disputes/E1-11-05.md`: the sweep's
  guarantee is superseded here by the grant removal — the database refuses a direct
  write outright — and the assertion that the module must contain a syntactic
  `role_assignment` write is the premise F2 reverses.
- A truncated walk (a refused pagination URL) ingests a partial roster and closes
  nobody. That is a deliberate narrowing of ADR 0095's "anything short answers None":
  a validation refusal leaves a clean prefix of validly-fetched pages, unlike a
  transport failure, which still answers None.
