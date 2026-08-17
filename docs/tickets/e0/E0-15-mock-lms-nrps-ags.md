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
- An endpoint or fixture hook that lets a test inspect posted scores.

## Out of scope

- Tool-side roster sync, enrollment provisioning, and the hourly schedule (E1).
- Tool-side line-item management, the participation formula, and retry handling
  (E3).
- `PlatformProfile` adapters for real platforms (E1 and beyond) — the mock is
  the reference behavior, not a quirk profile.
- The full seeded demo institution used for development (E0-17); this seed data
  belongs to the mock platform and stays small.

## Acceptance criteria

- [ ] NRPS returns a roster whose members carry role and enrollment status.
- [ ] A roster larger than one page returns `Link` headers and a test walks all
      pages to assemble the full membership.
- [ ] AGS line-item creation returns an identifier that score posting accepts.
- [ ] A posted score is retrievable by a test, including its timestamp and
      activity progress fields.
- [ ] Seed sections use at least two different start letters and both `WW` and
      `FF` modalities, so E0-07's parser has real input.
- [ ] Seed enrollments include a mid-term add and a mid-term drop, giving E3 the
      edge cases its property tests need.
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
