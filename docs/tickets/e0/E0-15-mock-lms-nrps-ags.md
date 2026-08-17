# E0-15 — Mock LMS: NRPS, AGS, and seed data

**ID:** E0-15
**Branch:** `e0/mock-lms-nrps-ags`
**Depends on:** E0-14

## Context

Roster sync and grade passback are the two LTI Advantage services this product
depends on: NRPS supplies enrollments and enrollment windows, AGS receives
participation scores. The mock has to be realistic enough that E1's sync and
E3's passback are built against real behavior, including paging.

Read first: SPEC §9.2, §7.3 (NRPS paging and AGS score semantics as the two
places platforms deviate), §3.4 (participation and enrollment windows), §2.2
(section codes the seed data must use).

## Scope

- Names and Role Provisioning Service 2.0 endpoint returning a course roster
  with roles, enrollment status, and email where exposed.
- **Paged** NRPS responses using `Link` headers, because paging is one of the
  named per-platform deviations in §7.3 and unpaged mock data would hide the
  bug class entirely.
- Assignment and Grade Services 2.0 stubs: line-item creation and listing, and
  score posting that records what it received so a test can assert on it.

  **The readback is a mock-only route, not a widened AGS Result.** A conformant
  AGS `Result` carries `userId`, `resultScore` and `resultMaximum` and nothing
  else — no timestamp, no `activityProgress` — so the fields criterion 4 names
  cannot be read back through the protocol. Serve the conformant Results
  endpoint for E3 to build against, and serve the inspection surface separately
  at `GET /mock/posted-scores`, outside the AGS namespace, answering

  ```json
  {"scores": [{"lineItem": "<absolute line item URL>", "score": { ...the posted body, verbatim... }}]}
  ```

  in the order the scores arrived. Verbatim means verbatim: a recorder that
  normalises `timestamp` or fills in a default `gradingProgress` is a recorder a
  test cannot use to prove what the tool sent. Todd's decision, 2026-08-17;
  ADR 0047. The `/mock/` prefix is the point — a tool that learned this route
  would have learned something no real platform serves.

  Three readings of that paragraph, settled here so nobody has to guess:
  **verbatim is equality, not containment** — the recorded body carries the
  fields the tool posted and no others, since a stray field is how a default
  invented by the mock gets mistaken for something the tool sent. **The store is
  a log, not a table keyed by student** — §3.4 re-posts a section's score after
  every week closes and E3 adds retries on top, so a re-post is a second entry
  beside the first rather than a replacement, and the sequence is the evidence
  E3 needs that a retry happened. **The Results endpoint does not rescale** —
  `resultScore` is the posted `scoreGiven` and `resultMaximum` is the line
  item's maximum.

  **Two rules the review round added, one of which goes past AGS 2.0 and one of
  which does not.** A posted `scoreMaximum` that differs from the line item's own
  maximum is **refused**, rather than accepted and dropped. AGS permits the
  mismatch and expects the platform to scale — Canvas does — so this is a
  deliberate narrowing, and it is the only shape that keeps the no-rescale ruling
  from producing a wrong grade in silence. It needs its own ADR, and E3 has to
  learn from it that it posts against the line item's own maximum rather than
  relying on a platform to scale for it. In the other direction, a score whose
  `timestamp` is **strictly earlier** than the last score held for that user on
  that line item is refused with `409 Conflict`, and an *equal* timestamp is
  accepted — AGS says "before", and a retry that re-sends an identical body after
  a network timeout is the case that makes accepting the equal one right.

  **The seed numbers its people, and a test may rely on it.** Every seeded
  student's identifier carries its section and a zero-padded ordinal, contiguous
  from 01 within a section. That is the only ground truth on this surface for
  "no member was dropped" — the NRPS container carries no total — so it is stated
  here rather than left as an accident of the seed. Renumbering the seed means
  changing the test that reads it.
- Seed data: a small institution with a handful of courses and sections whose
  codes exercise more than one start letter and both modalities, plus students,
  instructors, and enrollments including at least one mid-term add and one drop.

  **Every seeded course needs a title and a number in SPEC §8's bands.**
  `course.lms_title` is `NOT NULL` (E0-05, kept deliberately — see
  [E0-21](E0-21-review-debt.md)), so a course inserted without one fails, and
  course numbers outside the bands are refused at write time. Note that the
  numbers written across `design/` — `BIOL 2150` and the rest — are all invalid
  under those bands; all 27 distinct ones are, with no exception. Pick numbers
  against §8 rather than from a prototype screen. [E0-17](E0-17-seed-script.md)
  carries the decision about what to do with that corpus.

  **Every** means every, and that withdraws a requirement E0-14 shipped. E0-14
  asked this mock to seed one context carrying `id` alone, so that E1's
  ingestion would meet a titleless course in a test rather than in a deployment,
  and `test_mock_lms_launch.py::test_a_seeded_context_carries_no_title` asserted
  it. Todd ruled on 2026-08-17 that every seeded course carries a title; that
  test goes, in its own commit, and E0-14's scope is amended to point here.
  **What goes with it is the only fixture in the repository that exercises the
  empty-title path**, so E1 has to mint a titleless context itself before it can
  test its fallback, and until it does, the `NOT NULL` on `course.lms_title`
  will first be met by a real launch from a real course with no name.
- An endpoint or fixture hook that lets a test inspect posted scores — settled
  above as `GET /mock/posted-scores`.

- **Enrollment windows ride on a namespaced member extension.** SPEC §3.4 says a
  late add's denominator starts at the student's first enrolled week "from NRPS
  enrollment data", and §9.2 repeats that the sync reads enrollment windows from
  NRPS — but NRPS 2.0 defines no date field on a member at all, so a platform
  that supplies one supplies it as a vendor extension. This mock does the same,
  under a namespace that cannot be mistaken for the standard's:

  ```json
  "https://mock-lms.invalid/spec/nrps/enrollment": {"start": "2026-09-08T00:00:00-04:00", "end": null}
  ```

  `start` is required on every member and is an RFC 3339 timestamp with an
  offset, never a bare date — E0-06 made the calendar timezone-aware throughout
  and a naive stamp here would hand E1 a value it has to guess a zone for. `end`
  is `null` for a member still enrolled and a timestamp for one who dropped.
  Todd's decision, 2026-08-17; ADR 0048. E1 learns from this that enrollment
  dates arrive per-platform rather than as core NRPS, which is true of every
  real platform, and what a platform that supplies none should do is E1's
  question, not this ticket's.

## Out of scope

- Tool-side roster sync, enrollment provisioning, and the hourly schedule (E1).
- Tool-side line-item management, the participation formula, and retry handling
  (E3).
- `PlatformProfile` adapters for real platforms (E1 and beyond) — the mock is
  the reference behavior, not a quirk profile.
- The OAuth 2.0 client-credentials grant that guards NRPS and AGS on a real
  platform. This ticket names no token endpoint and E0-14 built none, so both
  services answer unauthenticated and the tests call them that way. **E1 and E3
  cannot build a conformant client against that**, and whichever of them needs a
  token first is where the grant belongs; note it there rather than discovering
  it against a real LMS.
- The full seeded demo institution used for development (E0-17); this seed data
  belongs to the mock platform and stays small.

## Acceptance criteria

- [ ] NRPS returns a roster whose members carry role and enrollment status.
- [ ] A roster larger than one page returns `Link` headers and a test walks all
      pages to assemble the full membership.
- [ ] AGS line-item creation returns an identifier that score posting accepts.
- [ ] A posted score is retrievable by a test at `GET /mock/posted-scores`,
      carrying the body the tool posted verbatim — its timestamp and its
      `activityProgress` and `gradingProgress` among the rest.
- [ ] The conformant AGS Results endpoint answers for the same line item, and
      carries none of those three fields, because a `Result` does not have them.
- [ ] Every NRPS member carries the enrollment extension named in the scope,
      with an offset-bearing `start`, and `end` set on the dropped member alone.
- [ ] Every seeded context carries a `title`.
- [ ] Seed sections use at least two different start letters and both `WW` and
      `FF` modalities, so E0-07's parser has real input.
- [ ] Seed enrollments include a mid-term add and a mid-term drop, giving E3 the
      edge cases its property tests need. Asserted within a section rather than
      against a calendar: the added member's `start` falls after every
      classmate's in the same section, and the dropped member's `end` is set
      while everyone else's is `null`. The mock publishes no section start or
      end date — a section's calendar is derived tool-side from its code and the
      term's start-letter map (§2.2), which live in Pulse's database, not on the
      platform — so "mid-term" is not a claim this surface can support, and a
      criterion written as though it could would be a criterion no test can
      honestly meet.
- [ ] `docker compose up -d` still reaches healthy on every service.

## Definition of done

**Tests apply.** Integration tests for NRPS paging — walking every page and
asserting no member is duplicated or dropped — and for the AGS post-and-read
round-trip.

**Docs apply, briefly.** `README.md` documents the seeded courses and users so a
developer knows who to launch as.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** The mock is not a product surface.
Confirm it is unreachable outside the Compose network and that the seeded
identities are obviously fake, so no test fixture ever resembles real student
data.
