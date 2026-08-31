# E1-10 — Launch-time provisioning, and how a sanctioned writer satisfies `guard_write`

**ID:** E1-10
**Branch:** `e1/launch-provisioning-guard-write`
**Depends on:** E1-07, E1-08
**Security-relevant (⚠ line-by-line):** the sanctioned-writer mechanism (it is
the difference between "LMS-owned data has one guarded writer" and "anything
can write it"), and the staff-only trigger rule for storing the roster address.

## Context

**Settled 2026-08-26 in this ticket: ADR 0090 is the mechanism** — a sanctioned
writer calls `guard_write` and passes a `WriteSanction` that `SANCTIONED_WRITERS`
has to back, and ADR 0091 records what a launch provisions and what it writes
down instead. The paragraph below is what was true when the ticket was written.

This is the first code that writes LMS-owned relations, which makes it the
ticket that settles **ADR 0069's open half**: `guard_write(table="course")`
refuses unconditionally today, every write path is required by the E0-35 sweep
(`test_every_writer_of_an_lms_owned_relation_names_the_guard.py`) to name the
guard, and "how a *sanctioned* writer satisfies the rule is left to E1, which
arrives with a real writer to design against." The mechanism designed here is
followed, not redesigned, by E1-11's sync — if the sync finds it wrong, that
is a dispute, not a quiet second mechanism.

SPEC §7.3 fixes the trigger semantics: a launch by an instructor or any
leadership role triggers a roster sync and **stores the roster service
address from the launch claim**; a student launch does not trigger one; the
launching person's role authorizes the trigger, never the request. §2.1 makes
courses, sections, section codes, enrollments and teaching instructors
LMS-owned and launch-time ingestion one of their two arrival paths.

One inherited edge case: E0-14's withdrawn note means a context with `id` and
no `title` has no fixture until E1-07 mints one, while `course.lms_title` is
`NOT NULL`. The fallback is this ticket's decision — E0-14 named `label`, or
prefix and number, as the candidates.

Read first: ADR 0069 (all three properties of the sweep, and what a syntactic
sweep cannot see); ADR 0045 (the chokepoint's grain); SPEC §7.3 and §2.1;
§8 and ADR 0015 (course number bands — a launch carrying an out-of-band number
is a defect to see, not a row to accept); ADR 0021 (derived calendar has one
writer — provisioning derives dates only through `apply_section_code`);
E0-35's ticket for what the sweep leaves open; E1-07's mint list (the
title-less context); ADR 0024 (person carries the user link — this ticket
creates `user`, not `person`).

## Scope

- **The sanctioned-writer mechanism**, with its ADR: how a writer is
  authorized to pass `guard_write` for a named table set, such that the E0-35
  sweep still fails any module that writes without naming the guard, the
  refusal for everything unsanctioned stays unconditional, and the sanction is
  visible in the catalog or the code — not a bypass flag. The design must keep
  MISTAKES entry 35 in view: the mechanism's inventory of sanctioned writers
  comes from somewhere the guarded structure cannot shrink.
- **What counts as a staff launch is a closed, named set** — §7.3 makes the
  launching person's role the authorization for the trigger, so the set is
  the authorization boundary and is stated here rather than left to the
  builder: the roles claim contains the canonical context-instructor URN
  (`http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor`) by **exact
  string match** — never substring, because the TeachingAssistant sub-role
  URN embeds the word Instructor — or the launching subject holds a live
  leadership `role_assignment` resolved through the app's own model. The
  leadership limb is stated here as the rule but **activates with E1-12**:
  resolving a launch subject to an assignment needs the `sub` → `user` →
  `person` link that only E1-12 builds, so in this ticket only the
  Instructor-URN limb can fire, which fails safe — §7.3's Dean-launch trigger
  arrives when E1-12 lands, and E1-12 carries the accept-side criterion. A
  limb with no test here is not left untested; it is tested where it becomes
  testable. Nothing
  else qualifies: TeachingAssistant, Mentor, ContentDeveloper, Observer, and
  platform-Administrator launches store no address and trigger no sync.
  Under-inclusion fails safe (a real instructor's next launch triggers the
  sync); over-inclusion hands a TA the full roster — names and emails — that
  §7.3 does not authorize. A platform that sends the plain Instructor URN
  alongside the TA sub-role has made its TAs instructors; that is the
  platform's call, and the exact-match rule records it.
- On a validated staff or leadership launch: upsert `course` and `section`
  from the context claim through the mechanism; derive the section calendar
  only via `apply_section_code` (ADR 0021); store the NRPS service address
  from the claim on the section's registration scope (§7.3's stored-address
  rule; E0-23's column arrives here, with the sync that reads it in E1-11).
  On a student launch: no sync trigger, no address write; the student's own
  `user` row may still be created (their enrollment arrives via NRPS, not
  here).
- A `user` row for the launching subject (`sub` → `lms_user_id`), idempotent
  across launches, created through whatever the mechanism says about
  `user` — and if `user` is outside the LMS-owned guarded set, the ADR says
  so explicitly rather than leaving it implied.
- The `lms_title` fallback decided and applied; the E1-07 title-less mint is
  the fixture that proves it; the fallback value is distinguishable from a
  platform-supplied title (the ADR says how, so a later sync does not
  "correct" a real title into a fallback or vice versa).
- Out-of-band course numbers (§8's bands) are refused at ingestion with the
  defect visible in the launch outcome log surface E11 will read — for now,
  a structured log/DB record, not a silent drop. The record's field set is
  enumerated in this ticket's design: defect kind, issuer, deployment,
  context id, timestamp — never a claim payload, a name, an email, or
  `lms_user_id` (§10; the stable join key E1-01 keeps out of views does not
  enter an Admin-visible record here either), and log lines on this path
  carry no more than the record does.

## Acceptance criteria

1. A staff launch against an unknown section creates course and section with
   correct derived dates; a second identical launch changes nothing
   (idempotence asserted on row identity, not just count).
2. A student launch against an unknown section stores no roster address and
   triggers no sync; so does a launch whose roles claim carries only the
   TeachingAssistant sub-role URN (E1-07's near-miss mint — its URN contains
   the string "Instructor"), and one carrying only Mentor. Each assertion
   covers the forbidden state.
3. The E0-35 sweep still fails a planted unsanctioned writer, and the new
   sanctioned path passes it — both directions run, per MISTAKES entry 9.
4. A launch whose context carries its `label` and no `title` provisions a
   course whose `lms_title` carries the decided fallback, marked as a fallback;
   a titled launch stores the platform's title. **Reworded 2026-08-26 on Todd's
   ruling**, because the title-less case is two cases: E1-07's
   `titleless_context` mint carries `id` alone, which identifies no course at
   all, so it is refused and recorded under criterion 5's shape rather than
   provisioned from a guess. E1-10 adds a second mint — `label` kept, `title`
   deleted — and that one is the fixture this criterion is about.
5. An out-of-band course number is refused and recorded; nothing is written.

## Out of scope

- Enrollment and INSTRUCTOR assignment writes (E1-11's, from NRPS — a launch
  proves one person's presence, not a roster).
- Identity merge (E1-12); `person` rows are not created here. With it goes
  the accept side of the leadership limb — a Dean's launch triggering the
  sync — which is E1-12's criterion 6, activating with the linkage it builds.
- The hourly schedule and the service client (E1-11).
