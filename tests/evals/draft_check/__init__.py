"""SPEC §7.4's draft-check task as an eval set — E7-04 done-when 8.

The cases and the check that grades an answer live in `cases.py`; each case's
expected answer is built through the task's own `CheckTheme` contract. There is no
floor file and no registry slot, for the reason `tests/evals/response_draft/`
gives. The cases are graded offline by
`tests/unit/test_the_draft_eval_cases_can_go_red.py`.
"""
