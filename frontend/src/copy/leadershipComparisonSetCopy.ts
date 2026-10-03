/**
 * Every sentence the comparison-set management screen writes — ticket E5-09.
 *
 * The shape is the four `instructorReport*Copy.ts` modules': **stable dotted
 * keys, one entry per string, one mapping**, with `copy()` and `fillCopy()` as
 * the only ways a component reaches a word. Nothing in the two components
 * carries a literal a person reads, so SPEC §4.1 items 4 and 5 have one file to
 * be read over rather than a search through JSX.
 *
 * ## What is deliberately not here
 *
 * **Every refusal the API writes.** `api/leadership.py` answers a duplicate
 * name, a set somebody else defined, an unknown course and a cross-level member
 * with its own sentence, and this screen shows whichever one it was sent. The
 * rules behind those sentences live once, on the server; a second wording here
 * would be a second statement of a rule that is the API's to make, and the two
 * would drift the first time either changed.
 *
 * **The lengths and the levels.** The lengths sections actually run and §8's
 * five levels reach the form from `GET /leadership/comparison-sets/options` and
 * from nowhere else, so no entry below names one. `length_option` is the treatment
 * given to a number the server sent, not a list of the numbers it may send.
 *
 * **Any comparison figure.** This surface manages sets; it never shows what a
 * set measures. There is no mean, no median and no benchmark word below —
 * §4.1 item 7 has no chokepoint on this screen, so nothing figure-shaped is
 * written for it at all. The two counts the preview renders are counts of
 * courses and of sections, which is the aggregate language §4.1 item 4 asks
 * for.
 *
 * **A confidentiality promise.** Nothing here is anybody's response: a set is a
 * list of courses with a length and a level. Item 5's sentence would have no
 * subject on this screen, which is the reason recorded beside the surface in
 * `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`.
 */

export const LEADERSHIP_COMPARISON_SET_COPY = {
  // The page, and the one honest sentence about what a set is for today. E5's
  // breakdown decision 4 keeps set *selection* in E9: a set can be defined,
  // edited and resolved here, and no report renders one yet. Saying so is the
  // alternative to a reader defining a set and waiting for it to appear
  // somewhere.
  'leadership_comparison_sets.heading': 'Comparison sets',
  'leadership_comparison_sets.intro':
    'A comparison set is a named group of courses that share one length and one level, so their sections can be compared with each other.',
  'leadership_comparison_sets.no_report_yet':
    'No report shows a named set yet. Sets defined here are ready for the reports that will use them.',

  // While the list is on its way, and when it did not arrive. The second is not
  // "you have no sets": a read that failed is a different fact from an empty
  // list, and saying the calm thing about a broken one is how somebody defines
  // a set they already have.
  'leadership_comparison_sets.loading': 'Opening your comparison sets…',
  'leadership_comparison_sets.unavailable':
    'These sets could not be loaded just now. Reload the page to try again.',

  // What a 401 says, in the register the instructor report's pair set: this page
  // cannot say anything about sets, having just been refused the answer, so it
  // says which door leads to a page that can.
  'leadership_comparison_sets.session_ended_title': 'This page is not signed in',
  'leadership_comparison_sets.session_ended_body':
    'The session this page was opened with has ended, so it cannot show any sets. Open Pulse Surveys again, and the sets you can read will be here.',

  // Nobody has defined one yet. It states what a set is for and asks for
  // nothing — `docs/DESIGN_BRIEF.md`'s tone rules apply to an empty list as
  // much as to data.
  'leadership_comparison_sets.empty_title': 'No sets yet',
  'leadership_comparison_sets.empty_body':
    'Nothing has been defined here so far. Define a set when you want a group of courses compared together.',

  // The list itself.
  'leadership_comparison_sets.list_label': 'Comparison sets you can read',
  'leadership_comparison_sets.define': 'Define a set',
  'leadership_comparison_sets.edit': 'Edit',
  'leadership_comparison_sets.delete': 'Delete',
  // A set somebody else defined. The API answers `editable: false` and this
  // screen shows no edit and no delete for it; the label is what tells a reader
  // the controls are absent by decision rather than by accident. It names
  // nobody: who defined a set is not on the wire and is not this screen's to
  // guess.
  'leadership_comparison_sets.read_only': 'Read only',
  // The line under a set's name: the two declared facts, in the server's own
  // spelling for the level and the treatment below for the length.
  'leadership_comparison_sets.set_facts': '{length} · level {level}',
  'leadership_comparison_sets.length_option': '{weeks} weeks',

  // The preview. Two plain counts and their plain labels, and a sentence for
  // the set whose section count did not arrive — E5-06's scope note allows a
  // preview to answer the member count and not the resolved section count, and
  // a zero printed in that case would state something the server did not say.
  //
  // `{courses}` and `{sections}` are filled with one of the four counted
  // phrases below rather than a bare number, for the reason the removal notice
  // has two entries: "1 courses" is a phrase nobody wrote on purpose.
  'leadership_comparison_sets.preview_counting': 'Counting what this set reaches…',
  'leadership_comparison_sets.preview_counts': '{courses}, {sections} across retained terms',
  'leadership_comparison_sets.preview_courses_only':
    '{courses}. The number of sections this set reaches is not available just now.',
  'leadership_comparison_sets.count_courses_one': '1 course',
  'leadership_comparison_sets.count_courses_many': '{count} courses',
  'leadership_comparison_sets.count_sections_one': '1 section',
  'leadership_comparison_sets.count_sections_many': '{count} sections',
  'leadership_comparison_sets.preview_unavailable':
    'What this set reaches could not be counted just now.',

  // Deleting. `design/Usage Rules.md` §4 asks a wide-effect change to confirm by
  // stating what will change rather than by asking whether somebody is sure, so
  // the confirmation names the set and says what survives it.
  'leadership_comparison_sets.delete_confirm_title': 'Delete “{name}”?',
  'leadership_comparison_sets.delete_confirm_body':
    'This removes the set for everyone who can read it. The courses in it are not changed, and nothing else about them is affected.',
  'leadership_comparison_sets.delete_confirm': 'Delete this set',
  'leadership_comparison_sets.delete_cancel': 'Keep it',
  'leadership_comparison_sets.delete_unavailable':
    'This set could not be deleted just now. Try again in a moment.',

  // The status line a write that landed is said in, once. A row appearing or
  // vanishing is the whole of the visible change, and a reader whose attention
  // is elsewhere on the page, or who is listening to it, is owed the sentence.
  'leadership_comparison_sets.set_saved': 'Set saved.',
  'leadership_comparison_sets.set_deleted': 'Set deleted.',

  // The form, in both of its jobs.
  'leadership_comparison_sets.form_create_heading': 'Define a comparison set',
  'leadership_comparison_sets.form_edit_heading': 'Edit this comparison set',
  'leadership_comparison_sets.form_loading': 'Opening this set…',
  'leadership_comparison_sets.name_label': 'Set name',
  'leadership_comparison_sets.length_label': 'Course length',
  'leadership_comparison_sets.length_unchosen': 'Choose a length',
  'leadership_comparison_sets.level_label': 'Course level',
  'leadership_comparison_sets.level_unchosen': 'Choose a level',
  'leadership_comparison_sets.members_label': 'Courses in this set',
  // Before a level is chosen there is no course list to offer, because which
  // courses may be offered is what the level decides.
  'leadership_comparison_sets.members_await_level':
    'Choose a level first. The courses of that level appear here.',
  'leadership_comparison_sets.members_none':
    'There are no courses of this level for you to choose from.',

  // Changing the level with courses already chosen. The ones that match the new
  // level stay; the rest leave, and they leave visibly — named, counted and on
  // screen until the reader dismisses the notice. A second change that removes
  // more adds its own sentence under the first.
  // Two entries rather than one with a number in it, because "1 courses" is a
  // sentence nobody wrote on purpose.
  'leadership_comparison_sets.members_removed_one':
    'The level changed, so one course left this set: {labels}.',
  'leadership_comparison_sets.members_removed_many':
    'The level changed, so {count} courses left this set: {labels}.',
  'leadership_comparison_sets.members_removed_dismiss': 'Dismiss',

  // A course that is in the stored set and is not in the choice lists this
  // reader was served — withdrawn from the catalogue, or moved out of their
  // purview, while nobody was looking. It is taken out of the form as the form
  // opens, and said so at once: a course the form cannot offer is one the
  // reader cannot see, uncheck or reason about, and leaving it in the body
  // being saved would submit a member they never chose and cannot read.
  //
  // These two sentences name no course, and that is the wire's doing rather
  // than a choice: the label lives on the options answer, and a course missing
  // from that answer has no label to print. So they count instead of naming,
  // which is the honest half of what is known.
  'leadership_comparison_sets.members_withdrawn_one':
    'One course in this set is no longer offered to you, so it is not in the form and will not be saved.',
  'leadership_comparison_sets.members_withdrawn_many':
    '{count} courses in this set are no longer offered to you, so they are not in the form and will not be saved.',

  'leadership_comparison_sets.save': 'Save this set',
  'leadership_comparison_sets.saving': 'Saving…',
  'leadership_comparison_sets.cancel': 'Cancel',
  // Why the save control is not ready yet. A set carries a name, a length and a
  // level by the shape of the request, so this says what is still missing from
  // the form rather than restating a rule the API owns.
  'leadership_comparison_sets.save_incomplete':
    'A set needs a name, a length and a level before it can be saved.',
  'leadership_comparison_sets.save_unavailable':
    'This set could not be saved just now. Try again in a moment.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type LeadershipComparisonSetCopyKey = keyof typeof LEADERSHIP_COMPARISON_SET_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: LeadershipComparisonSetCopyKey): string {
  return LEADERSHIP_COMPARISON_SET_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: LeadershipComparisonSetCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
