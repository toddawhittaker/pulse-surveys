"""Domain logic (SPEC §13).

Empty until E0-11 lands `authz.py`. The package exists now because the strict
mypy profile in `pyproject.toml` is pinned to `app.services.*`: the module that
will hold the authorization chokepoint gets no untyped escape from its first
line, rather than from whenever someone remembers to tighten it.
"""
