"""Domain logic (SPEC §13).

`section_codes.py` reads a section code against its term's start-letter map and
derives the section's length, dates and modality (§2.2, E0-07). `authz.py` is
the authorization chokepoint every entry point passes through. `tokens.py`
verifies a signed `id_token` against its issuer's published key set for both
entry doors. `safety.py` holds the Care queue's one connection that can reach
identity. `identity.py` resolves a verified subject to the rows this system
stores for them (E1-12); `session.py` signs and verifies what a door hands the
browser. `landing.py` mapped a verified token's roles claim to a landing view
until E1-13 deleted it: the landing comes from the assignment model now, out of
`authz.py`, and the four pages a door renders live in `app/api/deps.py`.
`clock.py` is the one place the scheduling and visibility code asks what time it
is — the effective instant, and the effective day in the institution's timezone —
and the one place a development-only override moves them from (E2-04, ADR 0109).

The package was created before any of them, because the strict mypy profile
in `pyproject.toml` was pinned to `app.services.*` from the start: the modules
that hold the guarantees get no untyped escape from their first line, rather
than from whenever someone remembers to tighten it.

That profile is no longer only this package. It covers `app.api.*` and
`app.lti.*` as well — the two entry doors, where untrusted input arrives — and
`app.ai.contracts`. `pyproject.toml`'s comment above the override is where the
reasoning lives, so there is one copy of it.
"""
