# 0205 — The roll-up tree is one payload, its names come through a label view, and its reads are set-based

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-07](../tickets/e9/E9-07-roll-up-backend.md)

## Context

SPEC §5.5 gives every leadership role one roll-up template: a tree over the
reader's purview (roots and labels per §2.1), a node's figures per start cohort
on the term axis (§2.2), and §5.6's attention cards. The spec does not say how
many requests the tree costs, where its node figures are computed, how rule 4
("response required and delinquent 48 hours or more") is read for many
sections without copying `response_loop.is_owed`, or how the tree learns a
department's or a college's name. That last one is a hard constraint, not a
taste: `pulse_app` holds no `SELECT` on `institution`, `college` or
`department` (`views_sql/containment_path_v001.sql`), and the first build of
this ticket failed on exactly that.

## Decision

- **The whole tree in one payload.** `GET /leadership/rollup?term_id=` answers
  every node over the reader's held sections in the term, built once in
  `services/rollups.py`; one node's figures are a second route. Every count is
  over held sections, so a department reached through one led course counts
  that course. The staff names (dean, chairs, leads, instructors) come through
  ADR 0201's door in one call per payload.
- **Names through `public.org_node_label (level, node_id, name, parent_id)`**,
  one row per institution, college, department, prefix and course, granted
  `SELECT` to `pulse_app` alone (migration `e9f6c8e0a706`). A prefix is named
  by its code; a course by `course_label`'s course form, "MATH 140 — College
  Algebra", built in the view's SQL. The view is read only through
  `authz.ScopedReader.org_node_labels(section_ids=...)`, which refuses a section
  outside the purview and walks `parent_id` upward from each section's course,
  so a reader is named only the nodes above sections they hold.
- **Node series through the set functions.** `benchmarks.node_series` groups a
  node's sections by start date and reads `benchmark_set_week` and
  `benchmark_set_rating_week` once per cohort. Node figures are plain values,
  not sealed comparison figures: every section in the node is one the reader
  may open.
- **One owed rule, read as a set.** `response_loop.owed_section_weeks` answers
  every owed (section, course week) for a set of sections with a fixed number
  of statements, and `is_owed` calls it. The attention list imports it by name.
- **Order is a label, never a figure.** Tree children by name, sections by
  code, cohorts by start date, cards by course name, section code and §5.6's
  rule order. `rollups.attention_cards` is pure, so a Hypothesis property can
  vary every figure and check the order.
- **No index.** The breakdown reserved `e9f6c8e0a706` for an index on
  `instructor_response (section_id, week_id, sequence)` if `EXPLAIN` asked. It
  did not. The owed read's statement, `SELECT DISTINCT section_id, week_id ...
  WHERE section_id IN (...)`, was explained over a structural copy of the table
  (same columns and indexes, no write trigger) holding about 230,000 rows, four
  terms of 2,000 sections: a bitmap index scan on the existing
  `ix_instructor_response_section_id_week_id` at 40 sections (0.5 ms) and at
  2,000 (23 ms). The statement reads no `sequence`, and the existing index is a
  prefix of the proposed one. The policy read already has
  `ix_response_policy_course_id_sequence`.

## Alternatives rejected

- **A column grant on `college.name` and `department.name`.** Smaller, but it
  breaks the rule that `pulse_app` holds nothing on those tables, for one
  reader.
- **Course names from the `course` and `prefix` rows in Python.** `pulse_app`
  can read both, and it would keep `course_label` the only spelling. Rejected
  so the tree has one source of names, and so E9-10's org-node picker can read
  the same view; the cost is the next consequence.
- **One request per tree level.** Expanding a node would cost a round trip and
  a purview resolution each time, for a tree a few hundred rows deep at most.
- **Applying §4.1 item 7's minimums to node figures.** A node is not a
  comparison set; its sections are the reader's own.

## Consequences

- The course-form label is spelled twice, in `section_codes.course_label` and
  in `org_node_label_v001.sql`. They must move together; nothing yet checks it.
- A section whose path is incomplete in the view fails the read loudly
  (`LookupError`) rather than leaving a node unnamed.
- The view lists every org node to `pulse_app`; the narrowing to the reader's
  purview is `ScopedReader`'s, as for every other org view (ADR 0046).
