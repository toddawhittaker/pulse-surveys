/**
 * Every sentence the leadership roll-up and drill-down pages write (SPEC §5.5,
 * §5.6): the tree, a node's figures, the named-set line, the attention list's
 * frame and the drill-down's context bar.
 *
 * The shape is `leadershipResponseCopy.ts`'s: stable dotted keys, one entry per
 * string, `copy()` and `fillCopy()` as the only ways a component reaches a word.
 * The prefix is `leadership_rollup.`, which the server's own roll-up sentences
 * already use (`app/copy/leadership_rollup.py`).
 *
 * ## What is deliberately not here
 *
 * **The words the server writes.** A tree row's label, a cohort's label, an
 * attention rule's name and the calm empty state all arrive in the payload, and
 * the pages show what they were sent, so one rule is never worded twice.
 *
 * **A confidentiality line.** The roll-up shows figures over sections, attention
 * cards and staff names, never a comment; the drill-down renders the
 * instructor report, which carries its own line once.
 *
 * **Any count of people, ranking or verdict** (SPEC §4.1 item 4). Every count on
 * these pages is the server's count of sections, courses, prefixes or
 * departments, and a card says "needs attention", never anything that blames.
 */

export const LEADERSHIP_ROLLUP_COPY = {
  // The page's states, before any figure.
  'leadership_rollup.loading': 'Opening your roll-up…',
  'leadership_rollup.unavailable':
    'Your roll-up could not be loaded just now. Reload the page to try again.',
  'leadership_rollup.session_ended':
    'The session this page was opened with has ended. Open Pulse Surveys again to read your roll-up.',
  'leadership_rollup.not_your_role':
    'You are signed in, in a role this page is not for. Open Pulse Surveys again the way you usually do, and it opens the pages your role has.',
  'leadership_rollup.no_term': 'There is no term to roll up yet.',

  // The term the page is reading, and the control that changes it.
  'leadership_rollup.term.label': 'Term',

  // The tree and its two modes. By-lead is offered only when the payload offers
  // it (chair and above, SPEC §2.1).
  'leadership_rollup.mode.label': 'Group the tree by',
  'leadership_rollup.mode.hierarchy': 'Hierarchy',
  'leadership_rollup.mode.by_lead': 'Lead faculty',
  'leadership_rollup.nav.label': 'Your purview',
  'leadership_rollup.nav.expand_all': 'Expand all',
  'leadership_rollup.nav.collapse_all': 'Collapse all',
  'leadership_rollup.nav.toggle': 'What {name} holds',
  'leadership_rollup.breadcrumbs.label': 'Where you are in the tree',

  // One node's figures.
  'leadership_rollup.figures.loading': 'Opening this part of the tree…',
  'leadership_rollup.figures.unavailable':
    'The figures for this part of the tree could not be loaded just now. Choose it again to retry.',
  'leadership_rollup.figures.no_cohorts':
    'No section here has a published week in this term yet.',
  'leadership_rollup.trend.heading': 'Ratings over the term',
  'leadership_rollup.trend.legend_node': 'These sections',
  'leadership_rollup.cohort.label': 'Start cohort',
  'leadership_rollup.workload.heading': 'Workload',
  'leadership_rollup.workload.absent': 'No workload figures for this start cohort yet.',
  'leadership_rollup.participation.heading': 'Participation',
  'leadership_rollup.participation.week': 'In the latest published week, course week {week}.',
  'leadership_rollup.participation.absent': 'No published week for this start cohort yet.',
  'leadership_rollup.attention.heading': 'Needs attention',
  'leadership_rollup.attention.open': 'Open the Monday report',
  'leadership_rollup.attention.open_named':
    'Open the Monday report: {course} · {section}, week {week}',
  'leadership_rollup.attention.week': 'WK {week}',

  // The named-set line beside the node's own (SPEC §5.5).
  'leadership_rollup.set.label': 'Compare with a named set',
  'leadership_rollup.set.none': 'No named set',
  'leadership_rollup.set.loading': 'Opening the named set’s figures…',
  'leadership_rollup.set.unavailable':
    'The named set’s figures could not be loaded just now. Choose it again to retry.',
  'leadership_rollup.set.suppressed':
    'The {name} line is withheld: too few sections or respondents in your purview stand behind it this term.',

  // The drill-down's context bar (SPEC §5.5), and the way back.
  'leadership_rollup.drill_down.context': 'Viewing as {role} · read-only',
  'leadership_rollup.drill_down.back': 'Back to your roll-up',
  'leadership_rollup.role.VP_ACADEMICS': 'VP of Academics',
  'leadership_rollup.role.DEAN': 'Dean',
  'leadership_rollup.role.ASSISTANT_DEAN': 'Assistant Dean',
  'leadership_rollup.role.CHAIR': 'Department Chair',
  'leadership_rollup.role.LEAD_FACULTY': 'Lead Faculty',
  'leadership_rollup.role.unknown': 'leadership',

  // The other leadership pages, below the roll-up.
  'leadership_rollup.more.label': 'More leadership pages',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type LeadershipRollupCopyKey = keyof typeof LEADERSHIP_ROLLUP_COPY;

/** The words behind one key; a key that is not this surface's fails to compile. */
export function copy(key: LeadershipRollupCopyKey): string {
  return LEADERSHIP_ROLLUP_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: LeadershipRollupCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
