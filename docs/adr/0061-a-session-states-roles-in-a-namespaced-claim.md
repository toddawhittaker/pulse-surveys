# 0061 — A session states roles in one namespaced claim, and states no scope

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-16

## Context

An `id_token` from this provider has to say what the person signing in may do,
or E1 has nothing to resolve. OpenID Connect defines no claim for that: OIDC
Core 1.0 §5.1's standard claims are all about *who* somebody is — name, email,
picture — and every provider invents its own for authorization, which is why
`groups`, `roles` and namespaced URIs all appear in the wild.

[SPEC §2](../SPEC.md) decides what the *values* are — the role names, and that
Care never composes with a reporting role — and §2.1 decides that purview is
computed from Pulse's own supervision graph. Neither says what the claim is
called or what shape it takes, and E1 reads whatever this ticket chooses.

## Decision

One claim, `https://pulse.example/claims/roles`, holding an array of role names
spelled exactly as `role_assignment.role` enumerates them: `VP_ACADEMICS`,
`DEAN`, `ASSISTANT_DEAN`, `CHAIR`, `LEAD_FACULTY`, `CARE`, `ADMIN`.

An array, always, even for the seven people who hold one role — a client that
met a bare string once would have to handle both shapes forever.

The claim name is published in the discovery document's `claims_supported` and in
the registration document as `roles_claim`, so a client learns it rather than
hardcoding it. Only the second of those actually identifies it — `claims_supported`
is an unordered list of names with nothing marking which one carries roles — which
is why
[ADR 0058](0058-the-mock-provider-publishes-its-registration-and-its-seed.md)
names `roles_claim` among the members a later ticket may depend on.

**The roles claim is bound to `openid` and is not gated behind a scope**, unlike
the OIDC standard claims beside it: a review found the provider handing over
`email` and `preferred_username` on an `openid`-only grant, which no real IdP
does, and those are now gated on `email` and `profile` (OIDC Core 1.0 §5.4). The
roles claim deliberately stays outside that scheme. It is the reason a client asks
this provider anything, and a client that had to know to request it would discover
that it did not at role-resolution time, which is the worst place to find out.

**Nothing else about authorization is in the token.** No org node, no assignment
scope, no purview, no supervision edge. The seeded assignments carry the node
they are scoped to and it stays in the seed document, where it is prose for a
later ticket rather than a value for a resolver.

## Alternatives rejected

**An unprefixed `roles` claim.** Shorter, and it is what most examples show.
RFC 7519 §4 keeps the unprefixed name space for registered claims and for
collision-resistant names by agreement; `roles` is neither, so a client that one
day federates a second provider has two different things under one name and no
way to tell which it is holding.

**The LIS vocabulary URIs the platform uses**, e.g.
`http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator`. Right
for `mock-lms`, where LTI fixes them and `pylti1p3` parses them. Wrong here: this
is not an LTI message, these roles are Pulse's own vocabulary — there is no LIS
term for Care, or for a lead faculty in the sense §2.1 gives it — and a
translation table between two vocabularies would be a thing to keep in step for
no gain.

**Roles nested inside a namespaced object**, e.g.
`{"https://pulse.example/claims": {"roles": [...], "assignments": [...]}}`. It
leaves room for more, which is the argument against it: the room would be filled
with a purview.

**Ship the assignments, scope included, so E1 can resolve a purview from the
token.** This is the one that looks most helpful and is most wrong. §2.1 makes
purview a function of the supervision graph, which is Pulse-owned data an
identity provider does not have — a real institutional IdP knows Entra ID groups,
not which chairs report through an assistant dean. A provider that shipped a
scope would teach E1 to trust one, and the first thing it would break is the
assistant-dean case §2.1 is written around.

## Consequences

**E1 reads one claim, and reads a purview from nowhere.** The session says who
the person is and which roles they may act under; everything about *what they can
see* comes from Pulse's own tables through `services/authz.py`. That is the
division SPEC §2.1 and E0-11 already built, and this record keeps the second door
from quietly opening a second route into it.

**A real institutional IdP will not send this claim.** Entra ID sends `groups`
and `roles` of its own; Okta sends whatever a claim mapping was configured to.
So E1's ingestion needs a mapping step, and the fact that this mock's claim is
already namespaced makes that step visible rather than skippable — a mock
sending exactly what Pulse wants would hide the work until the first real
deployment.

**The domain is reserved.** `pulse.example` is under RFC 2606's `.example`, so
the URI can never resolve and can never collide with a real one. If Pulse ever
has a real domain, changing this is a one-line change here and a mapping change
in E1 — and the registration document is what tells anyone where to look.
