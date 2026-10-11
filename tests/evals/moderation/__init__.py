"""SPEC §7.4's moderation task as an eval set.

The cases live in `cases.py`, built through `typed.py`. The threat and self-harm
cases live under `tests/evals/threat/`, beside SPEC §9.3's strictest floor, and
are joined into this set. There is no moderation floor file and no moderation
registry slot: the slot and its floor arrive together in E10's floor-setting pull
request, after the first live run, and the threat slot stays deferred with no
cases (a deferred slot carrying cases is refused by the runner).
"""
