# 0047 — The posted-score readback is a mock-only route, not a widened AGS Result

## Context

E0-15's fourth acceptance criterion is that a posted score is retrievable by a
test "carrying the body the tool posted verbatim — its timestamp and its
`activityProgress` and `gradingProgress` among the rest". Its fifth is that the
conformant AGS Results endpoint answers for the same line item.

Those two cannot be one endpoint. An AGS 2.0 `Result` carries `id`, `userId`,
`resultScore`, `resultMaximum`, `scoreOf` and `comment`, and nothing else. It has
no timestamp and no progress members at all, because a Result is the grade a
platform currently holds rather than a record of what a tool sent. So every field
criterion 4 names is a field the protocol has no room for, and the choice was
between serving a non-conformant `Result` and serving the inspection surface
somewhere outside the protocol.

SPEC §3.4 says what will need the readback: participation is recomputed and
re-posted after every week closes, and E3 adds retry handling on top. What E3
has to be able to prove is *what it sent*, which is exactly what a Result cannot
say. The spec names neither surface.

## Decision

Two endpoints, and the second is deliberately outside the AGS namespace.

The conformant Result container is served at the line item's own URL with
`/results` appended, exactly as AGS 2.0 defines it, carrying nothing a `Result`
does not have. `resultScore` is the posted `scoreGiven` and `resultMaximum` is
the line item's own maximum; nothing is rescaled between them.

The inspection surface is `GET /mock/posted-scores`, answering

```json
{"scores": [{"lineItem": "<absolute line item URL>", "score": { …the posted body, verbatim… }}]}
```

in the order the scores arrived. Three things about it are part of the decision
rather than incidental to it:

- **The `/mock/` prefix is the point.** A tool that learned this route would have
  learned something no real platform serves, and the prefix is what says so in
  the URL rather than in a comment.
- **Verbatim is equality, not containment.** The recorded body carries the fields
  the tool posted and no others. A stray field is how a default invented by the
  platform gets mistaken for something the tool sent, so the score body is read
  raw and stored as it decoded — never through a typed model, which is precisely
  a thing that fills in defaults, drops unmodelled members and re-renders a
  timestamp.
- **The store is a log, not a table keyed by student.** A re-post is a second
  entry beside the first, and the sequence is the evidence that a repost
  happened.

Todd's decision, 2026-08-17; E0-15's scope carries the same paragraph.

## Alternatives rejected

**Widen `Result` with `timestamp`, `activityProgress` and `gradingProgress`.**
One endpoint instead of two, and every readback test passes. What it does is
teach E3 to read three fields no real platform sends: the tool's passback would
be built against them here, and would fail to verify itself against the first
live LMS. The mock exists to be the reference behaviour, so a field it invents is
a field a later epic inherits.

**Serve the readback under the AGS line item URL at a non-standard sub-path** —
`{lineitem}/posted-scores`. It keeps the routing tidy and it is worse than the
above rather than better: a route inside the AGS namespace looks like part of the
protocol to anyone reading a trace, and the whole value of this surface is that
nobody can mistake it for one.

**Let the test read the platform's internal state through a fixture hook rather
than over HTTP.** E0-15's scope explicitly allows "an endpoint or fixture hook".
A hook would have been reachable only from a test in this process, and E0-18's
Playwright run drives the platform in a container — so the hook would have had to
be re-invented as an endpoint one ticket later, and a developer debugging a
passback by hand could not use it at all.

**Record the score through a Pydantic model and dump it back.** It is the
idiomatic FastAPI shape and it cannot carry this criterion. A model normalises
`2026-03-02T14:05:09+00:00` to whatever its serialiser renders, supplies a
default for any member the tool omitted, and silently drops any member it has no
field for. Each of those produces a record that looks right and is not the body
the tool sent.

## Consequences

Two readbacks to keep in step. A change to what a score post accepts has to be
carried to both, and only one of them is checked against a published
specification.

**The log grows without bound** for as long as a platform process lives. That is
correct for a mock whose whole lifetime is a test session or a development
afternoon, and it would be a defect anywhere else; ADR 0049 is where the
lifetime of that state is settled.

E3 gets a surface it can assert its own passback against — including that a
retry happened, which nothing in AGS can express — and gets it without any
production code path learning that the surface exists. Nothing in `backend/`
refers to `/mock/posted-scores`, and nothing should: a tool that reads it is a
tool that will not work against Canvas.

The absence is now a criterion with a test of its own, so a later ticket cannot
quietly add the three fields to `Result` to make something easier.
