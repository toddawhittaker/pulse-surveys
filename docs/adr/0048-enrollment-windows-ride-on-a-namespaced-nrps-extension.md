# 0048 — Enrollment windows ride on a namespaced NRPS member extension

## Context

SPEC §3.4 says a late add's denominator "starts at the student's first enrolled
week (from NRPS enrollment data)", and §9.2 has the roster sync read enrollment
windows from NRPS. Both sentences assume the roster carries dates.

NRPS 2.0 does not. A membership container's member carries `status`, `user_id`,
`roles`, `name`, `email` and the other person members, and **no date field of any
kind**. The `status` is the whole of what the specification says about time: a
member is `Active`, `Inactive` or `Deleted`, with nothing saying when. So a
platform that supplies an enrollment window supplies it outside the standard,
which is what every real platform that supplies one does.

E0-15's first draft of the seed tests had to find the window by scanning a member
for any value that parsed as a date, which is a test satisfied by a field
carrying a date for an unrelated reason. That is what sent the question to Todd
rather than leaving it as a weak green assertion.

## Decision

> **Amended 2026-08-21 by [E0-28](../tickets/e0/E0-28-review-debt-from-e0-15.md)
> item 1.** Everything below stands for every member that *carries* the
> extension, and one seeded member now carries none — a student in
> `NURS-8100-Q2FF`, whose member document omits the key entirely rather than
> emitting it empty. The reason is in the consequences section: the tool will meet
> platforms that supply no window, and no seeded roster let E1 meet one. The decision is not reversed and no alternative above is
> reopened; one case is added beside the rule.

Every NRPS member carries one extension member, under a namespace that cannot be
mistaken for the specification's:

```json
"https://mock-lms.invalid/spec/nrps/enrollment": {"start": "2026-09-08T00:00:00-04:00", "end": null}
```

- `start` is **required on every member that carries the extension** (E0-15 said
  "on every member"; E0-28 item 1 added the one exception above) and is an RFC
  3339 timestamp carrying an offset, never a bare date. E0-06 made the calendar timezone-aware
  throughout, and a naive stamp hands E1 a value it has to guess a zone for —
  whichever it guesses is right for half the year.
- `end` is `null` for a member still enrolled and a timestamp for one who
  dropped. It is present and `null` rather than omitted, because an absent key
  cannot distinguish "still enrolled" from "this platform supplies no end date",
  and those need different handling.
- The namespace is `mock-lms.invalid`, which can never resolve. Nobody can
  mistake it for a published specification, and the path says which
  specification it extends.
- `status` and `end` describe one fact and are written together in the seed, so a
  tool cannot meet them disagreeing.

Todd's decision, 2026-08-17; E0-15's scope carries the same paragraph.

## Alternatives rejected

**Invent a plain `start` and `end` on the member, unnamespaced.** Shorter to
write and shorter to read, and it teaches E1 the one wrong thing: that enrollment
dates are core NRPS. A sync built on that assumption meets its first real
platform, finds no such member, and the failure surfaces as an empty denominator
rather than as a missing vendor extension.

**Carry the window on the `message` member NRPS defines for LTI claims.** It is
the specification's own extension point and it is the wrong one: `message` holds
the claims a platform would send in a launch for that member, so a window put
there is a statement about a hypothetical launch rather than about the
enrollment.

**Derive the window tool-side from `status` and the section's calendar.**
Attractive because it needs no extension at all, and it cannot answer the
question §3.4 asks. `status` says a student is gone, not when they left, and a
denominator computed from the section's start is exactly the answer a late add
makes wrong.

**Serve section start and end dates on the platform and let the tool subtract.**
Rejected because it is not the platform's fact to state. A section's calendar
derives from its code and the term's start-letter map (§2.2), both of which live
in Pulse's database; a platform publishing dates would be a second source for
something the tool already derives, and the two would drift.

## Consequences

E1 learns the right lesson from the mock: enrollment dates arrive per platform
rather than as core NRPS, so reading them belongs in a `PlatformProfile` adapter
(§7.3) rather than in the sync. The tool will meet platforms with no such
extension, and since 2026-08-21 E1 can meet one here: E0-28 item 1 seeds a
single member with no extension key, so the branch exists in a fixture rather
than only in this paragraph. What the *fallback* should be — what denominator
§3.4's participation formula uses when there is no window — was raised in
E0-28's pull request and **settled by Todd on 2026-08-21, in the spec rather
than here**: §3.4 now says a student with no dates counts as enrolled from the
section's start, except one who first appears in a roster sync later than the
section's first sync, who counts from that sync's week. The under-credit for a
late add the first sync already contained is accepted there in as many words.

The namespace is a string in two places that must agree: `app.nrps` writes it and
`tests/integration/test_mock_lms_seed_data.py` reads it. That is deliberate — the
test names the member the ticket names, rather than discovering it by the shape
of its value — and it means a rename is two edits, one of them on the far side of
the test wall.

Nothing in `backend/` may hardcode this URI. It is one platform's spelling of one
vendor extension, and the tool's side of it is an adapter.
