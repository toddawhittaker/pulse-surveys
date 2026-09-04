/**
 * Every sentence the weekly survey screen writes itself — ticket E2-10.
 *
 * The surface's strings live here and nowhere else, in the shape
 * `backend/app/copy/` settles for the strings the server writes: **stable dotted
 * keys, one entry per string, one mapping**. SPEC §4.1 items 4 and 5 are rules
 * about words, E2-11 ships the inventory that reads them, and an inventory can
 * only read strings it can find — a sentence written into JSX is a sentence it
 * cannot. So no component under this screen carries a literal a person reads;
 * each one looks its words up by key.
 *
 * **The key is a name, not a sentence.** `student_survey.confidentiality` says
 * which surface and which thing; what it *says* is the value, and the two are
 * separated so that rewording is one edit here rather than an edit in a
 * component.
 *
 * ## What is deliberately not here
 *
 * **The question wording.** SPEC §3.2 stores the five questions in a versioned
 * table and `GET /student/survey` serves them; the form renders `prompt`,
 * `minimum_value`, `maximum_value`, `step`, `required_if_position` and
 * `required_if_at_most` off that answer. A prompt copied into this file would be
 * a second instrument that agrees with the real one only until a set is
 * versioned. §3.2 quotes no sentence for the two comments or the slider, so their
 * *labels* are this screen's and are here; their *rules* are still the API's.
 *
 * **The bounce coaching and every refusal.** SPEC §3.3's coaching copy is
 * `app.copy.submit`'s, served with the 422, and the refusals are served with
 * their own statuses. The form shows what the server said, verbatim. A local copy
 * of a bounce sentence would be a second wording of a governed string for the
 * inventory to choose between, and it would drift the first time the server's
 * changed.
 *
 * **The landmark's `data-testid`.** It is an identifier five end-to-end specs
 * address, not something a person reads, and it lives beside the screen that
 * carries it.
 *
 * ## Where two of these came from
 *
 * `student_survey.heading` and `student_survey.no_open_window` were
 * `frontend/src/lib/landings.ts`'s until this ticket, which replaces the student
 * landing view with the survey screen. They are moved verbatim rather than
 * rewritten: `tests/e2e/landing-views.spec.ts` holds its own copies of both
 * sentences deliberately — "a spec that asked the page what its own heading was
 * would pass against any heading at all" — so the move is proved by that spec
 * staying green without being touched.
 */

/**
 * Every user-facing string this surface ships, keyed by a stable dotted name.
 *
 * A flat key-to-text mapping rather than the backend's `CopyEntry(key, text)`
 * pair: the key here is the mapping's own key, so there is no second spelling of
 * it for the two to disagree in, and a reader — E2-11's collector included —
 * walks one object literal.
 */
export const STUDENT_SURVEY_COPY = {
  // The screen, and the calm state it shows when there is nothing to answer.
  // Both are E1-04's governed wording, moved rather than rewritten.
  'student_survey.heading': 'Your weekly check-in',
  'student_survey.no_open_window':
    'There is no survey open for you yet. When one opens, it appears here.',

  // While the answer is on its way, and when it did not arrive. The second is
  // not "there is nothing open for you": a read that failed is a different fact
  // from an empty week, and saying the calm thing about a broken one is how a
  // student misses a survey they could have answered.
  'student_survey.loading': 'Looking for this week’s survey…',
  'student_survey.unavailable':
    'This week’s survey could not be loaded just now. Reload the page to try again.',

  // What a 401 from the read path says. The session a launch issues lives an
  // hour and a survey window stands open for days, so the ordinary way to meet
  // this is a student coming back to yesterday's tab — and the one thing this
  // page must not do then is say what is due, because it was refused the answer.
  // So it says which page can. Second person, plain, nobody at fault: nothing
  // went wrong here, and nothing in these two sentences reads as an error.
  //
  // `app.copy.student_read`'s `student.not_a_student` is the server's sentence
  // for the same refusal and is deliberately not what this renders. That one
  // answers a request; this one has to tell the person looking at a rendered
  // page what to do next in it, and it has to say so even when the 401 carried
  // no body at all — which is what a proxy or a gateway in front of the tool
  // answers with.
  'student_survey.session_ended_title': 'Open this from your course',
  'student_survey.session_ended_body':
    'This page is not signed in, so it cannot say what is due. Open Pulse Surveys from inside your course in the LMS, and this week’s questions will be here.',

  // The mono eyebrow. SPEC §2.2's two week axes, each named in words — the
  // owner's ruling of 2026-09-03, after "TERM 03" had to be explained to them.
  // The week numbers are the API's and arrive through `fillCopy`; the comma
  // belongs to the first string rather than to the component, so the whole of
  // what a reader sees is inside this inventory and the §4.1 sweeps read it.
  'student_survey.course_week_eyebrow': 'COURSE WK {week},',
  'student_survey.term_week_eyebrow': 'TERM WK {week}',
  'student_survey.closes_label': 'closes',

  // The Likert scale's ends. The scale's *values* are the question's bounds.
  'student_survey.likert_low_label': 'Strongly disagree',
  'student_survey.likert_high_label': 'Strongly agree',

  // The two free-text questions. SPEC §3.2 quotes no wording for either, so the
  // label and the placeholder are this screen's; which of them is required, and
  // when, is the question row's.
  'student_survey.comment_label': 'Why that rating?',
  'student_survey.comment_placeholder': 'What helped, or what got in the way?',
  // §3.3: "optional-state helper copy notes that written feedback counts toward
  // full participation credit."
  'student_survey.comment_optional_help':
    'Optional, but written feedback counts toward full participation credit — a sentence or two is enough.',
  // The conditional-required state, in marigold and in words. The brief calls
  // this an invitation rather than an error, which is why it explains what the
  // sentence buys rather than what is missing.
  'student_survey.comment_required_help':
    'A low rating needs a why — a specific sentence is what earns participation credit and gives your instructor something to act on.',
  // The required state announced in text as well as in colour and in
  // `aria-required` (SPEC §14.2 item 4: a state carried by colour alone is a
  // state some readers do not have).
  'student_survey.comment_required_flag': 'Needed to submit',
  // And announced in words when it *changes*, which is the half a flag cannot
  // carry: choosing a low rating swaps the helper, adds the flag and flips
  // `aria-required` all at once, and a student who is not looking at the screen
  // was told none of it (E2-17 item 4). Only the crossing into required is
  // announced — becoming optional again is a relaxation, and a sentence saying
  // a comment is needed is the last thing that should be left standing when it
  // is not.
  'student_survey.comment_now_required':
    'A rating that low asks for a sentence: the comment beside it is now needed to submit.',

  // The workload slider. The range, the step and the readout's precision are all
  // the question's; these are the words around them.
  'student_survey.workload_label': 'Hours spent on this course this week',
  'student_survey.workload_unit': 'h',
  // The readout before the slider has been moved. A slider that started at zero
  // and read "0.0 h" would submit a figure the student never chose, and workload
  // is a headline number on §5.1's report — so the unanswered state says so, and
  // the submit button waits for it.
  'student_survey.workload_unanswered': 'Not set yet',
  // Filled with the question's own bounds by `fillCopy`. It is what the slider
  // announces to a screen reader beside its label, so the range and the step are
  // spoken rather than only drawn.
  'student_survey.workload_range_hint': '{minimum} to {maximum} hours, in steps of {step}',

  // The submit bar.
  'student_survey.submit': 'Submit this week’s pulse',
  'student_survey.submit_again': 'Update this week’s answers',
  'student_survey.submitting': 'Sending…',
  // What the submit control says when it is pressed with a question still
  // unanswered (E2-17 item 1). The button used to carry `disabled` until every
  // question was answered, which took it out of the tab order: a student using
  // a screen reader tabbed to the end of the form, found nothing to activate
  // and was told nothing about why. It stays operable now and says this
  // instead, naming the question so nobody has to go back through five of them
  // to find out which. Filled with the question's own wording by `fillCopy`.
  // Nobody is at fault here and nothing has gone wrong, so neither sentence
  // reads as an error.
  'student_survey.missing_answer': 'Answer “{question}” to send this week’s pulse.',
  // The same message for a question the served set gives no wording for. §3.2
  // quotes none for the two comments or the slider, so their labels stand in —
  // and a set that named a rating question nothing at all would leave even that
  // empty, which is what this sentence is for.
  'student_survey.missing_answer_unnamed':
    'One question above still needs an answer before this week’s pulse can be sent.',
  // SPEC §4.1 item 5: the confidentiality line, in plain words, in the submit
  // bar, and nowhere else on this surface. There is exactly one entry for it
  // here, which is the form the inventory reads it in.
  'student_survey.confidentiality':
    'Responses are confidential. Your instructor never sees your name with your answers.',
  // The in-window resubmit path, stated where the student is deciding whether to
  // send. No deadline is quoted: the window's own close is in the eyebrow above,
  // from the API, and a second statement of it here would be a copy to keep in
  // step.
  'student_survey.submit_again_note':
    'You can come back and change these answers until this week’s survey closes.',

  // What a stored week looks like. §3.3 gives the student their own verdict and
  // nothing about the section, so this says what was recorded and what comes
  // next.
  'student_survey.submitted_title': 'Your pulse is in',
  'student_survey.submitted_body':
    'Your answers for this week are recorded. Results and your instructor’s response appear here once the week has closed.',
  'student_survey.submitted_revise': 'Change these answers',

  // A section with no window open at this moment. SPEC §3.1: missed weeks cannot
  // be back-filled, and the design brief asks for calm and dated rather than a
  // countdown — so this states the fact and blames nobody.
  'student_survey.section_closed_title': 'Nothing to answer here right now',
  'student_survey.section_closed_body':
    'When the next survey for this course opens, it appears here.',
  // The same sentence for a section that has a window ahead of it, which is the
  // ordinary case: the system holds the row and the sentence above was
  // withholding it (the owner's ruling of 2026-09-03). `{time}` and `{day}` are
  // filled by the screen from the next window's instant, read in the
  // institution's zone — the zone abbreviation is derived from the date by
  // `Intl.DateTimeFormat` and is written down nowhere, because a survey opening
  // at six in October and six in November is two different offsets.
  'student_survey.section_closed_body_dated':
    'When the next survey for this course opens at {time} on {day}, it appears here.',

  // There is deliberately no entry for what a 409 says. The window shutting
  // under an open form, a week already recorded, and a judged comment that
  // cannot be withdrawn are three different sentences, all of them
  // `app.copy.submit`'s, and the screen shows whichever one the server sent
  // rather than a title of its own invented to sit above all three.
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type StudentSurveyCopyKey = keyof typeof STUDENT_SURVEY_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing so that every component reads the
 * mapping the same way and a key that is not one of this surface's fails to
 * compile.
 */
export function copy(key: StudentSurveyCopyKey): string {
  return STUDENT_SURVEY_COPY[key];
}

/**
 * One entry with its `{placeholders}` filled in.
 *
 * Four entries take them: the slider's range hint, whose numbers come off the
 * question row; the two week eyebrows, whose numbers come off the read answer;
 * and the dated closed-section sentence, whose two halves are formatted by the
 * screen from the next window's instant. The substitution lives here rather than
 * in the components so that a sentence and the shape of its holes stay in one
 * file.
 */
export function fillCopy(
  key: StudentSurveyCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
