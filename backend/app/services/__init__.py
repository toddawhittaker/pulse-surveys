"""Domain logic (SPEC §13).

`section_codes` reads a section code against its term's start-letter map and
derives the section's length, dates and modality (§2.2, E0-07). `authz.py`, the
authorization chokepoint every entry point passes through, arrives with E0-11.

The package was created before either of them, because the strict mypy profile
in `pyproject.toml` is pinned to `app.services.*`: the modules that hold the
guarantees get no untyped escape from their first line, rather than from
whenever someone remembers to tighten it.
"""
