"""Domain logic (SPEC §13).

`section_codes.py` reads a section code against its term's start-letter map and
derives the section's length, dates and modality (§2.2, E0-07). `authz.py` is
the authorization chokepoint every entry point passes through. `tokens.py`
verifies a signed `id_token` against its issuer's published key set for both
entry doors. `safety.py` holds the Care queue's one connection that can reach
identity. `landing.py` maps a verified token to the landing role and page it
sends the browser to (E0-18).

The package was created before any of them, because the strict mypy profile
in `pyproject.toml` was pinned to `app.services.*` from the start: the modules
that hold the guarantees get no untyped escape from their first line, rather
than from whenever someone remembers to tighten it.

That profile is no longer only this package. It covers `app.api.*` and
`app.lti.*` as well — the two entry doors, where untrusted input arrives — and
`app.ai.contracts`. `pyproject.toml`'s comment above the override is where the
reasoning lives, so there is one copy of it.
"""
