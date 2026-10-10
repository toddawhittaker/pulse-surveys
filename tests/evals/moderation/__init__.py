"""SPEC §7.4's moderation task as an eval set.

The cases live in `cases.py` and the floor slot in `floors.py`. The threat and
self-harm cases live under `tests/evals/threat/`, beside SPEC §9.3's strictest
floor. Neither set is attached to its registry slot: both floors are deferred to
the first live run (E10), and a deferred slot carrying cases is refused by the
runner.
"""
