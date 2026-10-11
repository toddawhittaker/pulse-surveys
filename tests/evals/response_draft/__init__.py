"""SPEC §7.4's response-draft task as an eval set — E7-04 done-when 8.

The cases and the checks that grade an answer live in `cases.py`. There is no
floor file and no registry slot: a floor needs the owner's live endpoint (the E7
breakdown's "Left out": "Eval floors for the draft and the check. Typed cases
only"), and a slot in `tests/evals/registry.py` would spend a provider call per
case on every pull request touching `backend/app/ai/`. The cases are graded
offline by `tests/unit/test_the_draft_eval_cases_can_go_red.py`.
"""
