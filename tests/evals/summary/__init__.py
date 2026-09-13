"""SPEC §5.1's weekly-summary contract as an eval set — E4-05.

The set and its checks live in `cases.py`; the sycophantic variant that must make
those checks go red lives in `breach.py`. Neither is in `tests/evals/registry.py`'s
`TASKS`, so no run of the live eval runner can reach either of them: this ticket
ships the cases and the way of grading them, and the numbers wait for the first
real-provider measurement (`tests/evals/README.md`, and the ADR that stages it).
"""
