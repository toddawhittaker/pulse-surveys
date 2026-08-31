# 0103 — The refusing guard's class name is a `data-reason` marker on the refusal page

> **Amended by the E1 boundary fix (M7), and by ADR 0106.** The decision below
> stands: the guard's class name is the marker. Three statements in it are no
> longer true of the code. `refusal_page`/`refused` no longer take a `reason`
> and a keyword `guard` — the guard name is the *only* parameter either takes,
> and the body copy is derived from it through `REFUSAL_COPY`, so there is no
> parameter a caller's words can arrive in. There is therefore no
> attribute-less case left: every refusal names a guard, including the web
> door's provider-error branch, which names its own `SessionRefusedError`.
> And the launch vocabulary is eleven subclasses rather than ten —
> `AnonymousLaunchRefused` joined it with ADR 0106.

## Context

Both doors answer a refusal with the same page (`app.api.deps::refusal_page`),
and E1-15's browser proof reads that page to say *which* guard refused. Until
now the only per-guard signal on the page was the prose sentence each refusal
carries, so `exit-refused-launches.spec.ts` matched error copy — and once found
its own bug there: a page repeating every guard's sentence made "the guard's
name is on the page" true and meaningless, which it closed by asserting the
*other* guard's sentence absent.

The launch door already has a machine vocabulary for this: the ten
`LaunchRefusedError` subclasses, one per validate step, whose class name is the
guard string the door logs (`app.lti.launch`). The web door has one,
`SessionRefusedError`. Nothing carried that vocabulary to the page, so a
browser-side spec had no stable token to read and was coupled to copy that is
allowed to change.

## Decision

The refusing guard's own class name reaches the refusal page as a
`data-reason="<guard>"` attribute on the container that already carries
`data-testid="pulse-entry-refused"`. `refusal_page`/`refused` take an optional
keyword `guard`; each door's refusal handler passes it. The launch door's two
sites pass `refusal.guard` — a new property on `LaunchRefusedError` that is the
class name for every subclass and, for the one refusal that wraps another
guard (the nonce-ledger replay, re-raised as a bare `LaunchRefusedError`), the
wrapped `NonceReplayedError`'s name — so the marker and the WARNING agree. The
web door passes `type(refusal).__name__`, its single `SessionRefusedError`.

**When no guard is named the attribute is omitted entirely** — never
`data-reason=""`. The value is escaped with `escape(guard, quote=True)`, for the
day a guard name is not a bare Python identifier, and the three calm pages
(cancelled, no-account, no-access) render no marker: they are not refusals.

## Alternatives rejected

- **Prose only, as today.** It couples every browser-side refusal spec to error
  copy, so a wording change that helps a person reading the page reds a test
  that is not about wording, and the copy is the thing most likely to change.
- **An opaque numeric code.** A second vocabulary to invent and maintain against
  the exception class names that already exist and are already what the door
  logs. Two names for one guard is one more thing to keep in step, and the class
  name is already the published token.
- **Render `data-reason=""` when no guard is named.** An empty marker defeats the
  suites' "exactly one marker" assertion, which is what tells a page reading one
  guard from a page reading all of them — the near miss that motivated the whole
  marker.

## Consequences

- **No new disclosure.** A guard's class name (`SignatureRefused`,
  `NonceReplayedError`) is not claim payload, a person, a section or a count; the
  per-guard prose already distinguished the guards on the same page. The §4.1
  "names nobody" invariant on the launch views is untouched — a refusal is not a
  landing.
- The refusal specs decouple from copy: E1-15's browser proof can name a guard
  by its marker and keep one prose assertion as a copy canary.
- The web door's single refusal type means its marker carries one value; it is
  asserted anyway, because a marker that reached only one of the two doors is
  one a reader cannot rely on, and the page is shared.
- `LaunchRefusedError` gains a `guard` property. The wrapper case is the only
  place its default (the class name) is overridden, so the exception type stays
  the guard vocabulary everywhere else.
