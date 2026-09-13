import type { ReportComment } from './CommentCard';

/**
 * The comment half of `docs/tickets/e4/README.md`'s payload sketch, as data —
 * ticket E4-10.
 *
 * One fixture module beside the four test files it serves, rather than four
 * copies of the same sketch: what a group is made of is the same shape whether
 * a test renders the group, the panel leading it or one of its cards, and three
 * copies of a payload shape drift the first time E4-07's schema settles one of
 * them. ADR 0151 puts a fixture module beside the test file it serves; this one
 * sits beside all four.
 *
 * The words are the prototype's own week-7 comments
 * (`design/InstructorMondayReport.dc.html`), so a test that renders a card
 * renders something a person actually wrote rather than "lorem ipsum" — the
 * prototype is the contract, and the fixtures may as well come from it.
 *
 * **Two rules the sketch carries on purpose, and these fixtures keep:** a
 * comment has no timestamp field and no author field at any depth, and no
 * fixture anywhere here counts comments that are being withheld.
 */

/** The instructor stream's summary, as the sketch's `streams.instructor.summary`. */
export const INSTRUCTOR_SUMMARY = {
  text: 'Students describe office hours as genuinely helpful and credit the instructor for the field sampling lab. The most consistent criticism is pacing.',
  responseCount: 13,
  heldNote: null,
} as const;

/** The course stream's summary. */
export const COURSE_SUMMARY = {
  text: 'The field sampling lab is called out as the strongest part of the week. The reading load ahead of the midterm is the dominant criticism.',
  responseCount: 13,
  heldNote: null,
} as const;

/** A published comment about the instructor. */
export const PUBLISHED_COMMENT: ReportComment = {
  text: 'Went to office hours for the first time this week. Should have gone sooner — genuinely helpful.',
  status: 'published',
};

/** The instructor stream's comments, in the order the payload gave them. */
export const INSTRUCTOR_COMMENTS: readonly ReportComment[] = [
  PUBLISHED_COMMENT,
  {
    text: 'Credit where due: the field sampling lab was designed and run really well.',
    status: 'published',
  },
  {
    text: 'Racing through material to hit the midterm. My questions keep getting deferred.',
    status: 'published',
  },
];

/** The course stream's comments. */
export const COURSE_COMMENTS: readonly ReportComment[] = [
  {
    text: 'The field sampling lab finally made the quadrat math click for me. More weeks like this one.',
    status: 'published',
  },
  {
    text: 'Three chapters in one week before an exam is too much. Cut a chapter or move the midterm.',
    status: 'published',
  },
];

/**
 * A flagged comment, with the classifier's reason (SPEC §5.2).
 *
 * No E4 path produces one — E4 writes only the initial `published` status — so
 * the flagged states are proven against this fixture, which is what the ticket
 * asks for and why the fixture exists.
 */
export const FLAGGED_COMMENT: ReportComment = {
  text: 'Emma from my lab group copied most of our shared report and still got full credit.',
  status: 'flagged',
  flagReason: 'privacy',
};

/** An excluded comment: §5.2 keeps its text visible to the instructor, muted. */
export const EXCLUDED_COMMENT: ReportComment = {
  text: 'This professor is clueless and should not be allowed near a classroom.',
  status: 'excluded',
};

/**
 * The configured response threshold the sketch's `small_n.threshold` carries.
 *
 * Deliberately not the default 5 everywhere in these tests: a component reading
 * a hardcoded 5 passes every assertion made with 5.
 */
export const SMALL_N_THRESHOLD = 5;

/** The summary a below-threshold week still gets (§5.1: it is the only comment signal). */
export const SMALL_N_SUMMARY = {
  text: 'All three responses mention the field sampling lab positively. Two note that the reading load felt heavier than usual.',
  responseCount: 3,
  heldNote: null,
} as const;

/**
 * How many comments the withheld week holds, and the comments themselves.
 *
 * A suppressed group is handed a non-empty array on purpose: the concealment
 * has to hold whatever the array contains, and a fixture of zero comments would
 * make "no cards rendered" true of an empty list rather than of the
 * suppression. Seven is a number no coordinate, class name or other fixture
 * value in these tests contains, so a test can assert the whole rendered
 * markup carries it nowhere.
 */
export const WITHHELD_COMMENT_COUNT = 7;

export const WITHHELD_COMMENTS: readonly ReportComment[] = [
  { text: 'The field lab was the best part of the week.', status: 'published' },
  { text: 'Office hours helped me more than lecture did.', status: 'published' },
  { text: 'The reading is stacking up faster than I can keep pace with.', status: 'published' },
  { text: 'Please post the worked examples after class.', status: 'published' },
  { text: 'Grading has been fair and the feedback is specific.', status: 'published' },
  { text: 'The lab write-up rubric is clear but demanding.', status: 'published' },
  { text: 'More field sessions like this one, please.', status: 'published' },
];
