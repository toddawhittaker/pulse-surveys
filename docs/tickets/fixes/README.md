# Standalone fix tickets

Small, owner-ruled fixes that belong to no open epic. Ruled 2026-09-03,
after the E2 merge: each rides its own `fix/<kebab-slug>` branch cut from
`main`, through the same gates and lanes as any ticket, one PR per ticket.
The lane rules, the per-PR security review, and CLAUDE.md's merge
discipline apply unchanged. A fix that grows past "small" stops and waits
for an epic.

| # | Ticket | Branch | Merged |
|---|---|---|---|
| 01 | [The survey page reads the way its owner asked](FIX-01-student-surface-copy.md) | `fix/student-surface-copy` | #161 |
| 02 | [The eval set measures fluent off-topic English](FIX-02-eval-fluent-off-topic.md) | `fix/eval-fluent-off-topic` | #162 |
| 03 | [Every test starts from the documented environment](FIX-03-test-env-parity.md) | `fix/test-env-parity` | #174 |
| 04 | [The runtime moves to Python 3.14](FIX-04-python-3-14.md) | `fix/python-3-14` | |

Where a ticket landed in two pull requests — one adding the ticket, one doing
the work — the Merged column names the one that did the work. FIX-03's ticket
was #173 and FIX-04's was #176.
