---
name: review-selftest
description: Measure whether the reviewer agents actually catch known-bad code. Applies each fixture patch in .claude/review-fixtures/ to a scratch worktree, runs the reviewer that should catch it, and reports caught or missed. Use before trusting the reviewers, and after editing any reviewer prompt.
---

# Reviewer self-test

A reviewer that always says "looks good" is worse than no reviewer, and you
cannot tell which kind you have by reading its prompt. This runs each reviewer
against a diff that is known to be broken and reports whether it noticed.

Run this **before trusting the roster**, and again **after editing any reviewer
prompt** — a prompt edit that improves the prose can quietly remove the sentence
that was doing the work.

## How it works

Each file in `.claude/review-fixtures/` is a patch plus a header naming the
reviewer that should catch it and what it should say. The header is in the
patch's leading comment block:

```
# fixture: identity-column-in-view
# reviewer: privacy-authz
# ticket: E0-10 (identity-separated views)
# expect: HIGH — user_identity column exposed through an instructor-readable view
```

`ticket:` is the ticket the pretend pull request names. Pass it through verbatim.
Where it reads `none`, tell the reviewer the pull request names no ticket and
say why — **never substitute a ticket you picked yourself.** Two reviewers read
the ticket before the diff, so a wrong number sends them auditing the wrong
acceptance criteria and spends findings on your mistake.

For each fixture:

1. **Try to apply it to a scratch worktree** so the reviewer gets surrounding
   context:
   ```bash
   git worktree add /tmp/selftest-<name> HEAD
   git -C /tmp/selftest-<name> apply <fixture>
   ```
2. **If it does not apply, feed the diff to the reviewer directly.** Most
   fixtures reference files that do not exist yet — the codebase is still being
   built — so this is the normal path today, not a failure. A reviewer judges a
   diff; it does not need the rest of the tree to see that a view exposes an
   identity column. As the codebase fills in, more fixtures will apply and the
   reviews get richer for free.
3. Spawn the named reviewer against that diff, exactly as `/review-pr` would —
   same inputs: a pull request number, the diff, the `ticket:` from the header,
   and the changed files. **Do not tell it a fixture is planted, and strip the
   whole `#` comment block before passing the diff.** A reviewer told to look
   for a bug finds one, which measures nothing.
4. Record whether it reported a finding matching `expect`, at the right severity
   or higher.
5. Remove the worktree if you made one.

Run the fixtures in parallel where you can; they are independent.

Several fixtures also carry **secondary planted defects**, noted in their
headers. Those measure noise in the other direction: a reviewer that reports
only the headline defect is under-reading, and one that invents issues beyond
the planted set is the kind of noisy that makes a user skim.

## Report

```
Reviewer self-test — 5 fixtures

  CAUGHT   privacy-authz    identity-column-in-view          HIGH
  CAUGHT   prompt-eval      eval-floor-lowered               HIGH
  MISSED   data-model       unindexed-report-join            (expected MED)
  CAUGHT   lti-oidc         unpaged-nrps-loop                HIGH
  PARTIAL  a11y-copy        chart-without-data-table         (found LOW, expected HIGH)

3 caught, 1 partial, 1 missed.
```

Report **misses and partials plainly**. A miss means that reviewer's prompt does
not carry the check, and the honest response is to say so, not to re-run until
it passes. Do not adjust a fixture to make a reviewer look better.

Also report **false positives**: findings unrelated to the planted defect. A
reviewer that catches the fixture and invents three other issues is noisy in a
way that will make the user skim.

## Fixing a miss

A miss is a prompt defect. Add the specific check to that reviewer's markdown,
in the concrete form the fixture represents — not a general exhortation to be
thorough. Then re-run the whole set, because a prompt edit can break a check
that previously passed.

If a fixture is genuinely unfair — it describes something the reviewer was never
scoped to catch — fix the fixture's `reviewer:` header or delete it. Say which
you did and why.

## Adding fixtures

The best fixtures come from real misses. When a reviewer lets something through
that reaches the user, add it here so the roster cannot regress on it. That is
how this set earns its keep over time.
