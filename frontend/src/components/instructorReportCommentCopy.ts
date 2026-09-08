/**
 * Every sentence the instructor report's comment half writes itself — ticket E4-10.
 *
 * The shape is `frontend/src/copy/studentSurvey.ts`'s, deliberately: **stable
 * dotted keys, one entry per string, one mapping**, with `copy()` and
 * `fillCopy()` as the only ways a component reaches a word. No component in
 * this group carries a literal a person reads, so SPEC §4.1 items 4 and 5 —
 * rules about words — have one file to be read over rather than a search
 * through JSX.
 *
 * **Why it sits beside the components rather than in `frontend/src/copy/`.**
 * `tests/fixtures/copy_inventory.py` collects every `.ts` and `.tsx` under
 * `frontend/src/copy/` recursively, and the invariant-marked inventory test
 * reds on any key prefix its governance map does not list. Growing that map
 * over the report's vocabulary is **E4-12**'s work, and it is heavy-lane work
 * scheduled after this wave. A copy file landing in the collected directory
 * before E4-12 runs would red the inventory for every other ticket in the
 * wave. So the strings are externalized here, in the collected shape, one
 * directory short of the collector — and E4-12 moves them under
 * `frontend/src/copy/` with the governance entry that lets them be read.
 *
 * **The key is a name, not a sentence.** What a key *says* is the value; the
 * two are separated so that rewording is one edit here.
 *
 * ## What is deliberately not here
 *
 * **The flag reason word** (`harmful`, `privacy`, `nonsense`). It is the
 * classifier's, arrives on the payload, and is filled into the chip's template
 * rather than chosen from a list this file keeps — a second list would agree
 * with SPEC §5.2's only until one of them changed.
 *
 * **The held note's type**, for the same reason: ADR 0148 makes
 * `held_note_type` the caller's free string, and §5.1 asks for the sentence
 * "one comment is held for review" with the type only. The sentence is here;
 * the type is the payload's.
 *
 * **Anything the summary itself says.** The model's prose is data, not copy.
 */

/**
 * Every user-facing string these components ship, keyed by a stable dotted name.
 *
 * One flat key-to-text mapping, as the survey surface's is: the key is the
 * mapping's own key, so there is no second spelling of it to disagree with.
 */
export const INSTRUCTOR_REPORT_COMMENT_COPY = {
  // SPEC §5.1's two group headings, which are the same two words everywhere in
  // the product — the survey's question order, the trend panels' order, and
  // this list's order all follow them (`design/Usage Rules.md` §1).
  'instructor_report_comments.group.instructor_heading': 'About the instructor',
  'instructor_report_comments.group.course_heading': 'About the course',
  // §5.1: "empty groups show a one-line notice, not a hidden heading." One
  // line, stating the fact, blaming nobody — and deliberately not the small-N
  // sentence below: a week nobody wrote in and a week whose comments are
  // withheld are different facts, and one sentence covering both would tell an
  // instructor the wrong one half the time.
  'instructor_report_comments.group.empty_notice': 'No comments this week.',

  // The AI provenance treatment: `docs/DESIGN_BRIEF.md` gives AI-generated
  // content "a chalk-tinted inset panel with a small mono 'AI' label", one
  // consistent treatment "so provenance is legible at a glance and never
  // mistaken for a human voice".
  'instructor_report_comments.ai.label': 'AI',
  'instructor_report_comments.ai.instructor_heading': 'AI summary — instructor comments',
  'instructor_report_comments.ai.course_heading': 'AI summary — course comments',
  // §5.1: summaries "state the response count they draw from". The number is
  // the payload's — ADR 0148 keeps it out of the model's answer entirely,
  // because a count from a model is plausible by construction and the one
  // person reading it cannot check it. The singular has its own entry rather
  // than a plural rule in a component: "1 responses" is the shape of defect a
  // rule invented at the call site produces.
  'instructor_report_comments.ai.drawn_from': 'Drawn from {count} responses',
  'instructor_report_comments.ai.drawn_from_one': 'Drawn from 1 response',
  // §5.1: above small-N a summary "may note 'one comment is held for review'
  // with type only". Whether the note appears is the payload's decision and
  // never this component's; this is only what it says when it does.
  'instructor_report_comments.ai.held_note': 'One comment is held for review ({type}).',
  // A week the summary job has not written a summary for — it has not run yet,
  // or it failed (E4-11). §5.1 makes the summary the thing that leads a group,
  // so its absence is a fact about the report and is stated as one: one plain
  // line where the panel would have been, no apology and no promise about when
  // one will arrive, because this page does not know. An empty panel would be
  // the brief's provenance treatment wrapped around nothing, which reads as a
  // summary that said nothing rather than as a summary that was not written.
  'instructor_report_comments.ai.absent': 'No summary was written for this week.',

  // The small-N notice, in its instructor audience (the student audience is
  // E8's). SPEC §4 hides raw comments below the threshold; the brief asks for
  // "an honest explanation of why", and `design/Usage Rules.md` §4 asks the
  // instructor register to be "formative and factual". The threshold is the
  // configured number and arrives as a number, never a 5 written down here.
  'instructor_report_comments.small_n.title': 'Comments are hidden this week',
  'instructor_report_comments.small_n.body':
    'To keep individual voices unidentifiable, raw comments stay hidden until at least {threshold} responses arrive. The summary above draws on everything received so far.',

  // A comment card. The label is what an assistive technology announces the
  // card as; the words inside it are the student's.
  'instructor_report_comments.comment.aria_label': 'Comment',
  // §5.2's flagged-collapsed state: the chip and its reason are visible to the
  // instructor above small-N. `design/Usage Rules.md` §4: flagged comments are
  // procedural, not alarmed.
  'instructor_report_comments.comment.flag_chip': 'Flagged: {reason}',
  'instructor_report_comments.comment.flag_pending': 'Hidden from students pending your review',
  'instructor_report_comments.comment.expand': 'Review comment',
  'instructor_report_comments.comment.collapse': 'Collapse',
  // §5.2: "Excluded comments keep their text visible to the instructor, muted,
  // above the exclusion notice." The notice states the accountability record
  // the same section describes; it is not a warning and nothing here scolds.
  'instructor_report_comments.comment.excluded_notice':
    'Excluded — students will not see this comment. The exclusion is logged and visible to the Lead Faculty.',
  // The optional stream chip (SPEC §7.6: "optional stream chip, default off").
  // It has no use in E4 — the report groups by stream, so a chip inside a group
  // would repeat its heading — and exists for a later surface that lists
  // comments from both streams together.
  'instructor_report_comments.comment.stream_instructor': 'Instructor',
  'instructor_report_comments.comment.stream_course': 'Course',

  // There is deliberately no entry for a count of what small-N withheld. SPEC
  // §5.2 allows "an optional neutral participation trace" and nothing in E4
  // produces one; a sentence here would be a place for a number this surface
  // must not be given.
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type InstructorReportCommentCopyKey = keyof typeof INSTRUCTOR_REPORT_COMMENT_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: InstructorReportCommentCopyKey): string {
  return INSTRUCTOR_REPORT_COMMENT_COPY[key];
}

/**
 * One entry with its `{placeholders}` filled in.
 *
 * Four entries take them: the flag chip's reason, the summary's response
 * count, the held note's type, and the small-N threshold — each a value the
 * payload supplies. The substitution lives here rather than in the components
 * so that a sentence and the shape of its holes stay in one file.
 */
export function fillCopy(
  key: InstructorReportCommentCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
