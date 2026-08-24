# E1-07 — The mock platform mints deliberately wrong launches

**ID:** E1-07
**Branch:** `e1/mock-wrong-launches`
**Depends on:** nothing
**Security-relevant:** none line-by-line — mock-only, development-only surface;
the review checks it cannot leak into a deployed path (ADR 0038's posture) and
that ADR 0035's signing bound holds.

## Context

E0-25 item 5, carried out of E0 with E1 as owner: "the mock LMS cannot mint a
deliberately wrong launch — tool-side launch validation is E1's, and E0-14
defined no interface for a bad launch deliberately." E1-08 must prove refusals
— §14.3 E1's exit line includes "a replayed or state/nonce-tampered launch is
refused" — and a driver that can only speak correctly makes the invalid half of
every guard unreachable (MISTAKES entry 28, which is this ticket's reason for
existing).

One more fixture rides here because it has no other home: E0-14's withdrawn
note records that **no title-less LTI context exists anywhere in the
repository** — E0-15 required every *seeded* course titled — while the LTI
context claim requires only `id`, and `course.lms_title` is `NOT NULL`. E1-10's
ingestion must meet that case in a test, so this ticket makes it mintable
rather than seeded.

Read first: E0-25 item 5 and E0-14's withdrawn paragraph; MISTAKES entries 28
and 3; ADR 0035 (signing stays standard-library, mock-only); `mock-lms/app/`
launch flow.

## Scope

A mint interface on the mock — a launch page parameter or a dedicated
endpoint, the builder's call — producing launches wrong in exactly one named
way each:

- signature by a key not in the platform's JWKS (`kid` present but unknown);
- signature by the right key over tampered claims;
- wrong `aud`; wrong `iss`; missing `nonce`; **reused** `nonce` (same token
  replayed — the replay case E1-08's exit clause names);
- tampered or missing `state` on the return leg;
- `iat`/`exp` outside plausible windows (the clock-skew cases §9.1 names);
- a syntactically valid launch whose context carries `id` alone — no `title`,
  no `label` (the E0-14 case; not *wrong*, but edge — the mint interface is
  where it lives so the seed stays fully titled per E0-15).

Each mint is labelled by its defect in the page/endpoint so a Playwright spec
can select it by name, and each produces exactly its named defect — a mint
that is wrong two ways is two tests that cannot tell which guard fired.

## Acceptance criteria

1. Every mint above is producible and covered by a mock-side test asserting
   the artifact really carries the named defect (assert the defect, not just
   a 200 — MISTAKES entry 3's spirit: prove the fixture is what it claims).
2. The correct launch path is byte-identical to before this ticket — minting
   is additive; a diff in the happy path is a finding.
3. The mint surface exists only on the mock; nothing under `backend/` changes.

## Out of scope

- Tool-side validation and the refusal tests themselves (E1-08 consumes these
  mints).
- Deep Linking message types (deferred; README not-do list).
- NRPS/AGS wrongness (the service surface has its own refusal cases in E1-06).
