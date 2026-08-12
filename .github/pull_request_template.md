# Seam

<!-- Which ticket seam from SPEC §14.3 does this PR deliver? Name the epic and
     the seam, e.g. "E0 — Foundations / core schema". One seam per PR. -->

## What changed

<!-- A few sentences in plain English. What can a person do now that they
     could not do before, or what is now true that was not true before? -->

## Definition of done (SPEC §14.2)

Check what this PR covers. For anything not applicable, write "n/a" and why.

- [ ] **Tests land with the feature.** Unit tests for new services, integration
      tests for any LTI/OIDC/AGS surface touched, and at least one Playwright
      end-to-end path through the new capability against the mock LMS and IdP.
      CI is green.
- [ ] **AI evals updated.** If this touches a model task, eval cases were added
      for the new behavior and the CI precision and recall gates still pass.
- [ ] **Security review by a separate agent.** An independent Claude Code
      session reviewed this diff against the adversarial checklist:
      authorization bypass across the role hierarchy, identity leakage past the
      §4 and §8 separation, LTI and OIDC token handling, injection, and
      audit-log completeness. Findings are triaged below.
- [ ] **Accessibility in-slice.** New user interface meets keyboard and screen
      reader basics now. The full WCAG 2.2 AA audit in E13 verifies; it does not
      do this work for the first time.
- [ ] **Docs.** README and configuration-surface updates for anything an
      operator or developer would need.

## Secrets check

- [ ] No real credential appears in this diff, its commit messages, or this
      description.
- [ ] Any new configuration variable is listed in `.env.example` with a
      placeholder value.
- [ ] If this adds or widens a `secrets.*` reference in a workflow, the
      repository owner agreed to it first. Say where.

## Confidentiality check

- [ ] No read path added or changed here widens what a student can see.
- [ ] No instructor or leadership path added here can join to identity columns.
- [ ] Small-N suppression still holds on every query this PR touches.

<!-- If this PR touches a ⚠ epic (E1, E9, E10, E13) or any confidentiality-
     critical path, say so here. Those require line-by-line human review of the
     security-relevant diff — agent review supplements human judgment, it never
     replaces it. -->

## Security review findings

<!-- Summarize what the review agent found and how each finding was resolved.
     Write "none" if the review came back clean. -->

## Deliberately deferred

<!-- Anything intentionally left out of this seam, and why. Be specific — this
     is the record of what the next seam has to pick up. Write "nothing" if
     the seam is complete as scoped. -->
