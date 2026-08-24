"""The LTI 1.3 tool side (SPEC §13, §7.3).

§13 gives this package five modules — `registration.py`, `launch.py`, `nrps.py`,
`ags.py` and a `platforms/` directory of adapters. E0-18 ships one of them:
`launch.py`, which is launch validation, because that is what E0's exit criterion
needs and because the other four have no caller yet. A module with no caller is a
guess at an interface, and §13 is a map of where things go rather than a list of
files that must exist.

**`pylti1p3` is not here, and §13 names it.** E0-18 verifies launches with PyJWT
instead; the decision, and what it costs when E1 restructures this, is in
docs/adr/0073.
"""
