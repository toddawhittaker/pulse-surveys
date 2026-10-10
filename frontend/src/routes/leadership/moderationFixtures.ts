import type { LogRowView, QueueItemView } from '../../api/leadership';

/**
 * What `api/leadership.py`'s moderation routes answer, for the review queue and
 * exclusion log tests.
 *
 * The section labels are in `section_codes.course_label`'s section form, and the
 * refusal sentences are transcribed from `app/copy/leadership_moderation.py`,
 * which stands behind the server these fixtures stand in for.
 */

export const A_BIOLOGY_ITEM: QueueItemView = {
  answer_id: '0b6c1f9e-3a52-4d0b-9a0e-6f1f2c3d4e51',
  text: 'The lab instructor is useless and should be fired before the next lab.',
  section_label: 'BIOL 215 R3WW — Principles of Ecology, Fall 2026',
};

export const A_MATHEMATICS_ITEM: QueueItemView = {
  answer_id: '7d2e8a14-5c63-4f1e-8b2d-0a1b2c3d4e52',
  text: 'Nobody in this class respects how badly the worksheets are written.',
  section_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
};

/** An exclusion of an AI-flagged comment, by its Lead Faculty, with an excerpt. */
export const AN_EXCLUSION_BY_A_LEAD: LogRowView = {
  section_label: 'BIOL 215 R3WW — Principles of Ecology, Fall 2026',
  decision: 'EXCLUDED',
  decided_as: 'LEAD_FACULTY',
  flagged: true,
  reason: null,
  decided_on: '2026-10-20',
  excerpt: 'This professor is clueless and should not be allowed near a classroom.',
};

/** An instructor's exclusion of an unflagged comment, with the reason SPEC §5.2 requires. */
export const AN_UNFLAGGED_EXCLUSION: LogRowView = {
  section_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
  decision: 'EXCLUDED',
  decided_as: 'INSTRUCTOR',
  flagged: false,
  reason: 'Personal attack with no actionable content.',
  decided_on: '2026-10-13',
  excerpt: 'The pace is fine but the grader is a joke.',
};

/** A chair's keep, whose excerpt the server withheld (ADR 0190). */
export const A_KEEP_WITH_NO_EXCERPT: LogRowView = {
  section_label: 'BUSA 300 F1WW — Operations Management, Fall 2026',
  decision: 'KEPT',
  decided_as: 'CHAIR',
  flagged: true,
  reason: null,
  decided_on: '2026-09-28',
  excerpt: null,
};

export const NO_REVIEW_GRANT = 'This leadership role has no review queue or exclusion log to read.';
export const NOT_IN_QUEUE = 'There is no comment awaiting your review here. Nothing was changed.';

/**
 * Members the wire never carries, planted beside the real ones.
 *
 * A page that rendered what it was sent rather than the members it means to
 * show would print these, so a test that serves them and finds none of them on
 * screen proves the page chooses its members (SPEC §4: no name, no week, no
 * time beside a comment).
 */
export const PLANTED = {
  instructor_name: 'Dr. M. Ellison',
  decided_by: 'Margaret Ellison',
  course_week: 4,
  week_label: 'COURSE WK 04',
  submitted_at: '2026-10-02T19:42:00-04:00',
  decided_at: '2026-10-20T14:32:00-04:00',
} as const;
