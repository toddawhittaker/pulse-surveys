import type {
  ComparisonSetDetailView,
  ComparisonSetOptionsView,
  ComparisonSetPreviewView,
  ComparisonSetSummaryView,
} from '../../api/leadership';

/**
 * The comparison-set answers this screen's tests render — ticket E5-09.
 *
 * **Shaped as the wire shapes them**, snake_case members and all, because these
 * describe E5-06's schemas rather than anything of this screen's choosing: a
 * divergence between the API and what the screen maps shows up as a compile
 * error here rather than as a list rendering the wrong member. E5-06 builds in
 * parallel and is not merged, so these are written from the contract both
 * tickets were handed (the epic's breakdown decision 8) and are the fixtures the
 * reconciliation reads when it lands.
 *
 * **This module is the only place in `frontend/src` where SPEC §2.2's lengths
 * and §8's five levels are written.** The form reads them from
 * `GET /leadership/comparison-sets/options` and never from a literal, and a
 * second list inside a component is the two-currencies defect this ticket's
 * trap section names. That the closed sets appear here at all is because a
 * fixture stands in for the server: this file is the server's answer, not the
 * screen's opinion.
 *
 * **`THE_OPTIONS` cannot prove that, and the first version of this paragraph
 * said it could.** Its lengths and levels are the real ones, so a form carrying
 * its own copy of §2.2 and §8 would render exactly what this fixture serves and
 * every test over it would stay green — a fixture that supplies the value under
 * test (`docs/MISTAKES.md` entry 30). `OPTIONS_NO_INSTITUTION_WOULD_SEND` below
 * is what settles the question: values no spec anywhere in this repository
 * contains, so a select offering anything else is offering something it did not
 * read from its options.
 *
 * **It sits beside the route it serves**, where
 * `routes/instructor/instructorReportFixtures.ts` sits beside the instructor
 * route (ADR 0151's placement convention). The strings in it — course labels,
 * set names, the API's own refusal sentences — are inside the tree
 * `tests/unit/test_the_component_and_route_trees_ship_no_ungoverned_string.py`
 * sweeps, and that sweep steps over this module by name, in
 * `EXCLUDED_SUPPORT_MODULES`. The exclusion is a claim rather than a licence:
 * the rule module requires this file to exist and requires nothing shipped to
 * import it, so the day a component reads these fixtures the sweep says so.
 *
 * **The numbers are chosen so a wrong member renders a different string.** The
 * member counts, the section counts, the lengths and the level codes are all
 * distinct from one another, so a preview that printed its section count where
 * its course count belongs, or a set that rendered its neighbour's length, is
 * visible rather than plausible.
 */

/** The six courses the options answer offers, across four of the five levels. */
export const A_BIOLOGY_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d001',
  label: 'BIOL 215 — Cell Biology',
  level: 'UG',
} as const;

export const A_CHEMISTRY_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d002',
  label: 'CHEM 121 — General Chemistry',
  level: 'UG',
} as const;

export const A_NURSING_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d003',
  label: 'NURS 640 — Advanced Practice Nursing',
  level: 'GR',
} as const;

export const A_DEVELOPMENTAL_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d004',
  label: 'MATH 040 — Foundations of Algebra',
  level: 'DEV',
} as const;

export const A_DUAL_CREDIT_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d005',
  label: 'SOCI 530 — Social Policy',
  level: 'UGGR',
} as const;

export const A_SECOND_GRADUATE_COURSE = {
  id: '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d006',
  label: 'NURS 655 — Population Health',
  level: 'GR',
} as const;

/**
 * The closed choice lists, as `GET .../options` answers them.
 *
 * The eight lengths are SPEC §2.2's course lengths plus the dissertation length,
 * and the five levels are §8's bands in the order that section lists them. Both
 * are the server's data; they are written once, here.
 */
export const THE_OPTIONS: ComparisonSetOptionsView = {
  lengths: [3, 6, 8, 10, 12, 15, 16, 18],
  levels: ['DEV', 'UG', 'UGGR', 'GR', 'DR'],
  courses: [
    A_BIOLOGY_COURSE,
    A_CHEMISTRY_COURSE,
    A_NURSING_COURSE,
    A_DEVELOPMENTAL_COURSE,
    A_DUAL_CREDIT_COURSE,
    A_SECOND_GRADUATE_COURSE,
  ],
};

/** The set the edit form opens: two undergraduate courses over twelve weeks. */
export const A_SET_THIS_READER_DEFINED: ComparisonSetDetailView = {
  id: '9c1b77e3-5d84-4a06-b0f2-6e9a1b4c7a10',
  name: 'Fall biology cohort',
  length_weeks: 12,
  level: 'UG',
  member_count: 2,
  editable: true,
  member_course_ids: [A_BIOLOGY_COURSE.id, A_CHEMISTRY_COURSE.id],
  created_at: '2026-08-31T14:05:00-04:00',
  updated_at: '2026-09-07T09:20:00-04:00',
};

/** A set this reader may read and may not change: the API answered `editable: false`. */
export const A_SET_SOMEBODY_ELSE_DEFINED: ComparisonSetSummaryView = {
  id: '9c1b77e3-5d84-4a06-b0f2-6e9a1b4c7a11',
  name: 'Doctoral inquiry sections',
  length_weeks: 18,
  level: 'DR',
  member_count: 5,
  editable: false,
};

/** A third set, so the list is a list rather than a pair. */
export const A_GRADUATE_SET: ComparisonSetSummaryView = {
  id: '9c1b77e3-5d84-4a06-b0f2-6e9a1b4c7a12',
  name: 'Graduate nursing',
  length_weeks: 8,
  level: 'GR',
  member_count: 4,
  editable: true,
};

/** The summary of the set the edit form opens, as the list carries it. */
export const A_SET_SUMMARY: ComparisonSetSummaryView = {
  id: A_SET_THIS_READER_DEFINED.id,
  name: A_SET_THIS_READER_DEFINED.name,
  length_weeks: A_SET_THIS_READER_DEFINED.length_weeks,
  level: A_SET_THIS_READER_DEFINED.level,
  member_count: A_SET_THIS_READER_DEFINED.member_count,
  editable: A_SET_THIS_READER_DEFINED.editable,
};

/** The list, in the order the route answers it: by name. */
export const THREE_SETS: readonly ComparisonSetSummaryView[] = [
  A_SET_SOMEBODY_ELSE_DEFINED,
  A_SET_SUMMARY,
  A_GRADUATE_SET,
];

/**
 * A preview that answered both counts.
 *
 * Three and eleven rather than two and two: the member count here is
 * deliberately not the summary's `member_count`, so a line that printed the
 * summary's number in the preview's place is a different string rather than the
 * same one.
 */
export const A_PREVIEW_WITH_BOTH_COUNTS: ComparisonSetPreviewView = {
  member_count: 3,
  section_count: 11,
};

/**
 * A preview that answered the member count and not the section count.
 *
 * E5-06's scope note allows this, and the line renders the absence in words.
 * The member is left off the object entirely rather than set to `null`, because
 * that is the shape a response with no such key parses to.
 */
export const A_PREVIEW_WITHOUT_A_SECTION_COUNT: ComparisonSetPreviewView = {
  member_count: 7,
};

/** The same fact spelled the other way, which a JSON `null` parses to. */
export const A_PREVIEW_WITH_A_NULL_SECTION_COUNT: ComparisonSetPreviewView = {
  member_count: 9,
  section_count: null,
};

/** What a create sends and what the server answers with, for the form's tests. */
export const A_NEW_SET: ComparisonSetDetailView = {
  id: '9c1b77e3-5d84-4a06-b0f2-6e9a1b4c7a13',
  name: 'Graduate nursing, eight weeks',
  length_weeks: 8,
  level: 'GR',
  member_count: 2,
  editable: true,
  member_course_ids: [A_NURSING_COURSE.id, A_SECOND_GRADUATE_COURSE.id],
  created_at: '2026-09-14T11:00:00-04:00',
  updated_at: '2026-09-14T11:00:00-04:00',
};

/**
 * A choice list no institution would send, for the provenance test.
 *
 * Four and seven are not course lengths in SPEC §2.2 and `ZZ` is not one of
 * §8's five bands, so nothing in this repository could supply them by accident:
 * a form that offers them offers them because this answer carried them, and a
 * form that offers 12 weeks or `UG` while holding this answer is reading a list
 * of its own. The course list is empty, which is the other half of the same
 * question — a picker with a literal catalogue would still show courses here.
 */
export const OPTIONS_NO_INSTITUTION_WOULD_SEND: ComparisonSetOptionsView = {
  lengths: [4, 7],
  levels: ['ZZ'],
  courses: [],
};

/**
 * A stored set carrying a member the options answer does not offer.
 *
 * The course was withdrawn, or moved out of this reader's purview, between the
 * set being defined and the form being opened — the race the form cannot
 * prevent and must not hide. Two of its three members are courses
 * `THE_OPTIONS` carries; the third is an id nothing in that answer names, so
 * this screen has no label for it and no box to render it in.
 */
export const A_COURSE_NO_LONGER_OFFERED = '0f4c6a11-0c4e-4b2f-9a3d-2a71c3e5d0ff';

export const A_SET_WITH_A_WITHDRAWN_COURSE: ComparisonSetDetailView = {
  id: '9c1b77e3-5d84-4a06-b0f2-6e9a1b4c7a14',
  name: 'Fall biology cohort, as it was',
  length_weeks: 12,
  level: 'UG',
  member_count: 3,
  editable: true,
  member_course_ids: [A_BIOLOGY_COURSE.id, A_COURSE_NO_LONGER_OFFERED, A_CHEMISTRY_COURSE.id],
  created_at: '2026-08-31T14:05:00-04:00',
  updated_at: '2026-09-07T09:20:00-04:00',
};

/**
 * The refusals the routes answer with, as sentences on the wire.
 *
 * Written here as the server's words rather than imported from anywhere: they
 * are `api/leadership.py`'s copy, this screen renders whichever one it is sent,
 * and a test that asked the screen for its own sentence would prove nothing.
 */
export const A_DUPLICATE_NAME_REFUSAL = 'A comparison set with that name already exists.';
export const A_NOT_THE_DEFINER_REFUSAL = 'This comparison set belongs to somebody else to change.';
export const AN_UNKNOWN_SET_REFUSAL = 'There is no comparison set here for you to read.';
