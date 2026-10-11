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
 * E4-10 shipped this file beside its components; **E4-12 moved it into
 * `frontend/src/copy/`**, the directory the inventory walks, so the strings
 * below are collected and swept rather than held to items 4 and 5 by review.
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
  // The wording is the mockup's — "Generated from 18 responses"
  // (`design/AiPanel.dc.html:20`), restored by E4-21. "Drawn from" was this
  // file's own phrasing and said less: what the panel states is where a
  // generated paragraph came from, and the verb that names the generation is the
  // one the provenance treatment is for.
  'instructor_report_comments.ai.generated_from': 'Generated from {count} responses',
  'instructor_report_comments.ai.generated_from_one': 'Generated from 1 response',
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
  // E8's). SPEC §4 hides one stream's raw comments when fewer than the threshold
  // of distinct students commented in it that week; the brief asks for "an
  // honest explanation of why", and `design/Usage Rules.md` §4 asks the
  // instructor register to be "formative and factual". The threshold is the
  // configured number and arrives as a number, never a 5 written down here.
  //
  // **Per stream, and no count of anybody** (E5.1-01, ADR 0182). The notice now
  // sits inside one comment group, so a count on it would read as that group's:
  // in a stream of one commenter, "1 student commented" is the whole disclosure,
  // and §5.2 forbids a count below the threshold. E4-21's leading "Only {responded}
  // of {enrolled}" sentence is gone for that reason; the week's participation
  // pair is still on the page, in the Participation region, as a fact about the
  // week rather than about a group. The body says where held comments go — the
  // from-earlier-weeks list, with no week — and keeps "the AI summary above",
  // the brief's provenance rule applied to a reference. The identity promise is
  // in the body only; the title is a plain statement of what the group shows.
  'instructor_report_comments.small_n.title': 'No raw comments are shown here this week',
  'instructor_report_comments.small_n.body':
    'To keep individual voices unidentifiable, raw comments in this group are shown only when at least {threshold} students comment in it in the same week. Comments held back may appear later among comments from earlier weeks, with no week named. The AI summary above draws on everything received so far.',

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
  // SPEC §5.2's three decisions, in the mockup's words
  // (`design/CommentCard.dc.html`). Excluding is the one that changes what
  // students see, so it says so; keeping is the default the instructor confirms.
  'instructor_report_comments.comment.keep': 'Keep for students',
  'instructor_report_comments.comment.exclude': 'Exclude from student view',
  'instructor_report_comments.comment.undo': 'Undo',
  // Read aloud after a decision lands, because the pressed control is gone and
  // nothing else says what happened.
  'instructor_report_comments.comment.announce_excluded':
    'Comment excluded from the student view.',
  'instructor_report_comments.comment.announce_kept': 'Comment kept for students.',
  'instructor_report_comments.comment.announce_undone': 'Decision undone.',
  // §5.2's logged decision on a kept comment. "You" is the only attribution any
  // card carries (ADR 0189): another reader's decision is stated without a name.
  'instructor_report_comments.comment.kept_by_you': 'You kept this comment for students.',
  'instructor_report_comments.comment.kept': 'Kept after review.',
  // §5.2: excluding a comment the AI did not flag requires a stated reason. The
  // prompt asks plainly and does not suggest the comment was wrong to write.
  'instructor_report_comments.comment.reason_label': 'Why should students not see this comment?',
  'instructor_report_comments.comment.reason_remaining': '{remaining} characters left',
  'instructor_report_comments.comment.reason_submit': 'Exclude with this reason',
  'instructor_report_comments.comment.reason_cancel': 'Cancel',
  // A decision that got no answer the server wrote a sentence for. The server's
  // own refusals are shown as sent and are not here.
  'instructor_report_comments.comment.decision_unavailable':
    'The decision could not be sent. Try again in a moment.',
  'instructor_report_comments.comment.decision_session_ended':
    'Your session has ended. Open the report again from your course to make this decision.',

  // The optional stream chip (SPEC §7.6: "optional stream chip, default off").
  // It has no use in E4 — the report groups by stream, so a chip inside a group
  // would repeat its heading — and exists for a later surface that lists
  // comments from both streams together.
  'instructor_report_comments.comment.stream_instructor': 'Instructor',
  'instructor_report_comments.comment.stream_course': 'Course',

  // There is deliberately no entry for a count of what small-N withheld. SPEC
  // §5.2 says "no count" below the threshold and allows no participation trace;
  // a sentence here would be a place for a number this surface must not be
  // given.
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
 * Five entries take them: the flag chip's reason, the summary's response
 * count, the held note's type, the small-N threshold — each a value the
 * payload supplies — and the reason prompt's remaining characters. The substitution lives here rather than in the components
 * so that a sentence and the shape of its holes stay in one file.
 */
export function fillCopy(
  key: InstructorReportCommentCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
