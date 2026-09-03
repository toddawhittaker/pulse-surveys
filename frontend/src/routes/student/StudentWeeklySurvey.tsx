import { useCallback, useEffect, useState, type JSX } from 'react';

import {
  readStudentSurvey,
  submitWeeklySurvey,
  type EnrolledSection,
  type OpenSurvey,
  type SubmittedValue,
  type SurveyQuestion,
} from '../../api/student';
import { ConditionalTextArea, type CommentState } from '../../components/ConditionalTextArea';
import { LikertInput } from '../../components/LikertInput';
import { StateNotice } from '../../components/StateNotice';
import { SubmitBar } from '../../components/SubmitBar';
import { WeekEyebrow } from '../../components/WeekEyebrow';
import { WorkloadSlider } from '../../components/WorkloadSlider';
import { copy, fillCopy } from '../../copy/studentSurvey';

/**
 * SPEC §7.6's `StudentWeeklySurvey` — the five questions, and the states around
 * them.
 *
 * **The screen renders the answer and decides nothing about who is looking.**
 * ADR 0086's contract holds: a door verifies the launch, resolves the role and
 * redirects here with a session; this file asks `GET /student/survey` what there
 * is for whoever that session belongs to and draws it. There is no role check
 * here, no section parameter, and nothing a reader could put in an address that
 * would change what comes back — the read path takes none, which is itself part
 * of SPEC §4.1 item 1's argument.
 *
 * **The instrument is the API's.** Question wording, the Likert bounds, the
 * slider's range and step, and §3.2's conditional rule ("required if Q1 ≤ 2")
 * all arrive on the question rows and are consumed as they arrive. Nothing about
 * the five questions is written down in this repository's frontend, which is
 * what acceptance criterion 2 is proved by: reseed an altered set and the screen
 * follows.
 *
 * **The states, and where each comes from.** A reader enrolled in nothing today
 * gets an empty list and the calm between-terms state; a section with no window
 * open right now says so and offers nothing to answer; an open window with no
 * submission is the form; an open window the reader has already answered opens
 * in the submitted state with their own answers prefilled and the in-window
 * revision path; and a submission the server refused is either §3.3's bounce —
 * coaching on the comment fields, the rest of the form untouched — or one of
 * `app.copy.submit`'s sentences shown where the student is standing.
 *
 * **A read the server refused is none of those.** A 401 gets its own state, and
 * the reason it is called out here is that collapsing it into the calm one is an
 * easy and quiet mistake: the two look alike on screen and only one of them is a
 * claim this page is entitled to make. The session lives an hour, a window
 * stands open for days, and "there is no survey open for you yet" told to a
 * student whose session has simply run out is this screen answering a question
 * it was refused. So the refusal says which page can answer instead.
 *
 * **This replaces the student landing view.** The landmark keeps E0-18's
 * `pulse-landing-student` testid, which five end-to-end specs address to say a
 * student landed; the heading and the between-terms sentence are E1-04's
 * governed wording, moved verbatim into `../../copy/studentSurvey` with the rest
 * of this surface's strings.
 */

/**
 * The landmark's testid — E0-18's, and the five specs that address it are
 * `landing-views`, `lti-launch`, `web-login`, `two-hat` and `exit-dean-both-doors`
 * (through `tests/e2e/support/doors.ts`'s `ALL_LANDINGS`). It is an identifier
 * rather than something a person reads, so it is here and not in the copy
 * module.
 */
export const STUDENT_SURVEY_TESTID = 'pulse-landing-student';

const HEADING_ID = 'pulse-student-survey-heading';

/** What the read answered, as this screen holds it. */
type Load =
  | { readonly kind: 'loading' }
  | {
      readonly kind: 'sections';
      readonly sections: readonly EnrolledSection[];
      readonly institutionTimezone: string;
    }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable' };

export function StudentWeeklySurvey(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    void readStudentSurvey().then((answer) => {
      if (!live) return;
      if (answer.kind === 'view') {
        setLoad({
          kind: 'sections',
          sections: answer.view.sections,
          institutionTimezone: answer.view.institution_timezone,
        });
      } else if (answer.kind === 'session-ended') {
        // **Never the empty-week state.** A refused read and an empty week are
        // different facts, and only one of them entitles this page to say what
        // is due. The session a launch issues lives an hour while a window
        // stands open for days, so the ordinary way here is a student coming
        // back to yesterday's tab — and "there is no survey open for you yet"
        // would be this screen answering, authoritatively and wrongly, a
        // question it had just been refused.
        setLoad({ kind: 'session-ended' });
      } else {
        setLoad({ kind: 'unavailable' });
      }
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="pulse-survey" data-testid={STUDENT_SURVEY_TESTID} aria-labelledby={HEADING_ID}>
      <h1 id={HEADING_ID}>{copy('student_survey.heading')}</h1>
      <PulseDivider />
      <ScreenBody load={load} />
    </main>
  );
}

function ScreenBody({ load }: { readonly load: Load }): JSX.Element {
  if (load.kind === 'loading') {
    return (
      <p className="pulse-survey-status" role="status">
        {copy('student_survey.loading')}
      </p>
    );
  }
  if (load.kind === 'session-ended') {
    return (
      <StateNotice
        variant="flat"
        title={copy('student_survey.session_ended_title')}
        body={copy('student_survey.session_ended_body')}
      />
    );
  }
  if (load.kind === 'unavailable') {
    return <StateNotice variant="flat" body={copy('student_survey.unavailable')} />;
  }
  if (load.sections.length === 0) {
    return <StateNotice variant="flat" body={copy('student_survey.no_open_window')} />;
  }
  return (
    <SectionSurveys sections={load.sections} institutionTimezone={load.institutionTimezone} />
  );
}

/**
 * Every enrolled section, and the one submit area that carries the
 * confidentiality sentence.
 *
 * SPEC §4.1 item 5, as the ruling of 2026-09-03 reads it: the sentence appears
 * exactly once per *screen*, in the submit area. A student enrolled in two
 * courses whose windows are open at the same minute is one screen and not two,
 * so exactly one of the submit bars on it carries the sentence — the first, in
 * the order the sections are drawn.
 *
 * **Which sections are offering a submit action is reported rather than
 * re-derived.** Whether a section has one depends on what the student has done
 * in it since the page loaded: submitted it, reopened it, or had its window shut
 * underneath them. Those rules live in `OpenSurveyForm` and a second copy of
 * them here would be a second answer to keep in step, so each form says which
 * state it is in and this decides from the answers. The initial set is read off
 * the wire instead, so the sentence is on screen from the first paint rather
 * than one frame later.
 *
 * **A screen with nothing to submit carries no sentence, and that is the
 * shipped reading rather than a gap.** The sentence belongs to the act of
 * sending; a week already answered shows the submitted state, which has no
 * submit area in it and nothing to be reassured about.
 */
function SectionSurveys({
  sections,
  institutionTimezone,
}: {
  readonly sections: readonly EnrolledSection[];
  readonly institutionTimezone: string;
}): JSX.Element {
  const [offering, setOffering] = useState<ReadonlySet<string>>(
    () => new Set(sections.filter(offersASubmitActionOnArrival).map((it) => it.section_id)),
  );

  // Stable, so a form's report is an effect that runs when its own state
  // changes rather than on every render of this list. Answering with the set it
  // was given when nothing changed is what lets React stop there.
  const report = useCallback((sectionId: string, offeringOne: boolean) => {
    setOffering((current) => {
      if (current.has(sectionId) === offeringOne) return current;
      const next = new Set(current);
      if (offeringOne) next.add(sectionId);
      else next.delete(sectionId);
      return next;
    });
  }, []);

  const carriesConfidentiality =
    sections.find((section) => offering.has(section.section_id))?.section_id ?? null;

  return (
    <>
      {sections.map((section) => (
        <SectionSurvey
          key={section.section_id}
          section={section}
          institutionTimezone={institutionTimezone}
          showConfidentiality={section.section_id === carriesConfidentiality}
          onSubmitArea={report}
        />
      ))}
    </>
  );
}

/** Whether this section's block will draw a submit area on the first render. */
function offersASubmitActionOnArrival(section: EnrolledSection): boolean {
  const survey = section.survey_is_open ? section.open_survey : null;
  return survey !== null && survey.submission === null;
}

/** One enrolled section: its course, and whatever there is to do about it. */
function SectionSurvey({
  section,
  institutionTimezone,
  showConfidentiality,
  onSubmitArea,
}: {
  readonly section: EnrolledSection;
  readonly institutionTimezone: string;
  readonly showConfidentiality: boolean;
  readonly onSubmitArea: (sectionId: string, offering: boolean) => void;
}): JSX.Element {
  const survey = section.survey_is_open ? section.open_survey : null;
  return (
    <section className="pulse-survey-section" data-testid={sectionTestid(section.section_code)}>
      {/* One string, and the server composed all of it — FIX-01 item 2. The
          heading used to be the §2.2 code in one span beside the course in
          another, and it never said which term; the ruling of 2026-09-03 folds
          the code in and adds the term name, which makes this the page's visual
          headline and tells several courses on one screen apart. The section
          code still travels on the wire, because `sectionTestid` addresses
          blocks by it. */}
      <h2 className="pulse-section-heading">{section.course_label}</h2>
      {survey === null ? (
        <StateNotice
          variant="flat"
          title={copy('student_survey.section_closed_title')}
          body={closedSentence(section.next_window_opens_at, institutionTimezone)}
        />
      ) : (
        <OpenSurveyForm
          sectionId={section.section_id}
          survey={survey}
          showConfidentiality={showConfidentiality}
          onSubmitArea={onSubmitArea}
        />
      )}
    </section>
  );
}

/** Where a spec finds one section's block. */
export function sectionTestid(sectionCode: string): string {
  return `survey-section-${sectionCode}`;
}

/**
 * What a closed section says: when its next survey opens, or the plain sentence.
 *
 * FIX-01 item 4. The dated sentence needs two things to be true — the answer
 * carries an instant, and that instant can be formatted in the deployment's zone
 * — and the undated sentence is what stands when either is not. Both are
 * governed copy; nothing here writes a word a reader sees.
 */
function closedSentence(opensAt: string | null, timeZone: string): string {
  const when = opensAt === null ? null : institutionInstant(opensAt, timeZone);
  return when === null
    ? copy('student_survey.section_closed_body')
    : fillCopy('student_survey.section_closed_body_dated', when);
}

/**
 * One instant in the institution's zone, as the two halves of the ruled sentence.
 *
 * "6:00PM EDT" and "Friday, September 4". **The zone abbreviation is derived and
 * never written down**, which is the whole point of the ruling: the same six
 * o'clock is EDT in October and EST in November, and a page carrying either
 * letter as a literal tells half the term's students the wrong hour.
 * `formatToParts` is what lets the abbreviation be taken from the format without
 * accepting the punctuation the locale would put around it — "6:00 PM" has a
 * space the ruled shape does not.
 *
 * **`en-US` deliberately, rather than the reader's locale.** The eyebrow's
 * closing instant follows the reader, because it is a bare time inside their own
 * day; this one is filled into an English sentence the owner ruled word for word,
 * and a date formatted to another locale's conventions inside it would read as
 * neither.
 *
 * **The zone is the institution's, not the browser's** (SPEC §8, §3.1). A survey
 * opens at six o'clock where the institution is; a student reading in another
 * zone is owed the institution's hour, which is the one the door will actually
 * open at.
 *
 * `null` when the instant will not parse or the zone is not one `Intl` knows —
 * `Intl.DateTimeFormat` throws a `RangeError` on an unknown zone — so the caller
 * falls back to the undated sentence rather than rendering "Invalid Date".
 */
function institutionInstant(
  instant: string,
  timeZone: string,
): { readonly time: string; readonly day: string } | null {
  const when = new Date(instant);
  if (Number.isNaN(when.getTime())) return null;
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    }).formatToParts(when);
  } catch {
    return null;
  }
  const held = new Map(parts.map((part) => [part.type, part.value]));
  const named = ['hour', 'minute', 'dayPeriod', 'timeZoneName', 'weekday', 'month', 'day'] as const;
  if (named.some((type) => held.get(type) === undefined)) return null;
  return {
    time: `${held.get('hour')}:${held.get('minute')}${held.get('dayPeriod')} ${held.get('timeZoneName')}`,
    day: `${held.get('weekday')}, ${held.get('month')} ${held.get('day')}`,
  };
}

/**
 * Where a spec finds the two things the form says about a submission that did
 * not go through: SPEC §3.3's coaching, announced once, and the server's
 * sentence for a refusal that left the answers where they were.
 */
export const BOUNCE_ANNOUNCEMENT_TESTID = 'survey-bounce-announcement';
export const REFUSAL_TESTID = 'survey-refusal';

/** Where a spec finds the way back into a week it has already answered. */
export const REVISE_TESTID = 'survey-revise';

/** SPEC §3.3's gate having refused this submission, and which fields it lands on. */
interface Bounce {
  /** `app.copy.submit`'s coaching sentence, as the server sent it. */
  readonly message: string;
  /** The comment positions the coaching is attached to. */
  readonly positions: readonly number[];
}

/**
 * The form for one section's open window.
 *
 * Answers are held by **question position**, which is the spelling both wire
 * contracts use — §3.2 numbers its questions by it and writes its conditional
 * rules against it, and a submission names its answers by it. Every value is a
 * string all the way to the wire: the two numeric columns are decimals on the
 * server, and a float round-tripped through JavaScript is how an answer lands
 * between two of the steps its question moves in.
 *
 * **An incomplete week is refused here rather than sent and refused there, and
 * the control that refuses it stays operable** (E2-17 item 1). The submit button
 * used to carry `disabled` until every non-comment question was answered, which
 * took it out of the tab order: the screen offered a keyboard user nothing to
 * activate and nothing that explained why. Pressing it now names the first
 * question still owed, moves focus to that question's control, and sends
 * nothing.
 *
 * **Three live regions, one fact each.** SPEC §3.3's coaching, §3.2's
 * conditional rule turning a comment required, and what stops this week being
 * sent. They were not always three: sharing one made "the region is not empty"
 * ambiguous about which fact had arrived, which is measured in this ticket's
 * attempts log. Each is in the document from the first render and each is empty
 * until its own fact is true, so a change to one of them is that fact and
 * nothing else.
 */
function OpenSurveyForm({
  sectionId,
  survey,
  showConfidentiality,
  onSubmitArea,
}: {
  readonly sectionId: string;
  readonly survey: OpenSurvey;
  readonly showConfidentiality: boolean;
  readonly onSubmitArea: (sectionId: string, offering: boolean) => void;
}): JSX.Element {
  const [values, setValues] = useState<Record<number, string>>(() => initialValues(survey));
  const [stored, setStored] = useState(survey.submission !== null);
  const [showForm, setShowForm] = useState(survey.submission === null);
  const [bounce, setBounce] = useState<Bounce | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [closed, setClosed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Why this week cannot be sent yet, written beside the button when it is
  // pressed with a question still unanswered (E2-17 item 1). Empty otherwise,
  // and empty again as soon as any answer changes: it is the result of one
  // activation, and an edit is what makes it possibly untrue.
  const [missing, setMissing] = useState('');
  // That §3.2's conditional rule has just made a comment required (E2-17 item
  // 4), announced and never drawn: the flag beside the label and the helper
  // under the box are the visible statement of the same fact, and a third one on
  // screen would say it twice.
  //
  // **Its own region rather than the bounce's**, and that is a measured
  // correction rather than a preference. Sharing one meant that a form where a
  // low rating had already been chosen was announcing this sentence when the
  // bounce arrived, so "the region is not empty" no longer identified the
  // server's coaching and `student-survey.spec.ts` read the wrong sentence out
  // of it. Two facts, two regions, each empty until its own is true.
  const [requiredNotice, setRequiredNotice] = useState('');

  // Whether this section is offering a submit action at all, told to the screen
  // so that exactly one submit area on it carries the confidentiality sentence
  // (SPEC §4.1 item 5; see `SectionSurveys`). The two states below that return
  // early — a window that shut, and a week already answered — have no submit
  // area in them, so this is the one place the answer is known.
  const showsSubmitArea = closed === null && showForm;
  useEffect(() => {
    onSubmitArea(sectionId, showsSubmitArea);
  }, [onSubmitArea, sectionId, showsSubmitArea]);

  function setValue(position: number, value: string): void {
    const before = values;
    const after = { ...before, [position]: value };
    setValues(after);
    setRefusal(null);
    setMissing('');

    // Editing a coached field takes the coaching off that field and leaves it on
    // the others. The message itself is unchanged while any field still carries
    // it, so the live region does not announce the same sentence twice.
    const stillCoached =
      bounce === null ? [] : bounce.positions.filter((carried) => carried !== position);
    const nextBounce =
      bounce === null || stillCoached.length === 0 ? null : { ...bounce, positions: stillCoached };
    setBounce(nextBounce);

    // SPEC §3.2's conditional rule crossing *into* required is announced (E2-17
    // item 4) — the flag, the helper and `aria-required` all change at once and
    // a student who is not looking at the screen was told none of it. Crossing
    // back out of it is a relaxation and is not announced: the sentence is
    // cleared rather than left standing while it is untrue, and clearing a live
    // region says nothing to anybody.
    const wasRequired = requiredComments(survey.questions, before);
    const nowRequired = requiredComments(survey.questions, after);
    if (nowRequired.some((at) => !wasRequired.includes(at))) {
      setRequiredNotice(copy('student_survey.comment_now_required'));
    } else if (wasRequired.some((at) => !nowRequired.includes(at))) {
      setRequiredNotice('');
    }
  }

  async function submit(): Promise<void> {
    // The button is never disabled (E2-17 item 1), so a second press while the
    // first is in flight is reachable and is refused here rather than by taking
    // the control away.
    if (busy) return;

    // An incomplete week is not sent. The server would refuse it and the student
    // would meet the refusal as a failure; this says which question is still
    // owed, announces it, and puts the keyboard on it.
    const unanswered = firstUnanswered(survey.questions, values);
    if (unanswered !== null) {
      setMissing(missingAnswerSentence(unanswered));
      document.getElementById(fieldId(sectionId, unanswered.position))?.focus();
      return;
    }

    setBusy(true);
    setRefusal(null);
    setMissing('');
    const outcome = await submitWeeklySurvey(
      { section_id: sectionId, answers: buildAnswers(survey.questions, values) },
      copy('student_survey.unavailable'),
    );
    setBusy(false);

    if (outcome.kind === 'stored') {
      setStored(true);
      setShowForm(false);
      setBounce(null);
      setRequiredNotice('');
      return;
    }
    if (outcome.kind === 'bounced') {
      // **The bounce names no position**, so the coaching goes to every comment
      // this submission actually carried and the rest of the form is left
      // exactly as the student typed it. Attaching it to one field would be this
      // screen guessing which comment the classifier judged;
      // `docs/tickets/e2/deferred.md` carries what closes that.
      const positions = submittedCommentPositions(survey.questions, values);
      setBounce({ message: outcome.message, positions });
      const first = positions[0];
      if (first !== undefined) {
        document.getElementById(fieldId(sectionId, first))?.focus();
      }
      return;
    }
    if (outcome.kind === 'closed') {
      setClosed(outcome.message);
      return;
    }
    // Everything else says the answers are still worth keeping — the classifier
    // being unreachable says so in as many words — so the form stays and the
    // server's sentence goes above it.
    setRefusal(outcome.message);
  }

  // The eyebrow stands above every one of these states, because the week is the
  // one fact that is true in all of them — `docs/DESIGN_BRIEF.md` puts it before
  // anything else on the screen, and a submitted week that stopped saying which
  // week it was would be the layout losing the term's rhythm at the moment it
  // matters.
  const eyebrow = (
    <WeekEyebrow
      courseWeek={survey.course_week}
      termWeek={survey.term_week}
      closesAt={survey.closes_at}
    />
  );

  if (closed !== null) {
    return (
      <>
        {eyebrow}
        <StateNotice variant="flat" body={closed} />
      </>
    );
  }

  if (!showForm) {
    return (
      <>
        {eyebrow}
        <StateNotice
          variant="beat"
          title={copy('student_survey.submitted_title')}
          body={copy('student_survey.submitted_body')}
        >
          <button
            type="button"
            className="pulse-secondary"
            data-testid={REVISE_TESTID}
            onClick={() => {
              setShowForm(true);
            }}
          >
            {copy('student_survey.submitted_revise')}
          </button>
        </StateNotice>
      </>
    );
  }

  return (
    <div className="pulse-survey-form">
      {eyebrow}

      {/* SPEC §3.3's coaching, announced once for the whole form rather than
          once per field carrying it. The region is in the document from the
          first render: a region added at the moment it has something to say is a
          region assistive technology has not been watching — and, since E2-17
          item 8, it is *rendered* from the first render too. It used to be
          `display: none` while empty, which is the same defect wearing a
          stylesheet: Chromium marked the node `notRendered` and kept it out of
          the accessibility tree until it already had something to say.
          `styles.css` hides it by clipping now. */}
      <p
        className="pulse-bounce-announcement"
        data-testid={BOUNCE_ANNOUNCEMENT_TESTID}
        role="status"
        aria-live="polite"
      >
        {bounce?.message ?? ''}
      </p>
      {/* And §3.2's conditional rule turning a comment required (E2-17 item 4).
          Its own region, because the two facts are independent and a shared one
          made "the coaching has arrived" unreadable — a form where a low rating
          had already been chosen was announcing the conditional sentence when the
          bounce landed. Never drawn: the flag beside the label and the helper
          under the box are the same fact on screen already. */}
      <p className="pulse-required-announcement" role="status" aria-live="polite">
        {requiredNotice}
      </p>
      {refusal === null ? null : (
        <p className="pulse-refusal" data-testid={REFUSAL_TESTID} role="alert">
          {refusal}
        </p>
      )}

      {groupQuestions(survey.questions).map((group) => (
        <div className="pulse-question-card" key={group[0]?.position ?? 0}>
          {group.map((question) => (
            <QuestionField
              key={question.position}
              question={question}
              sectionId={sectionId}
              values={values}
              bounce={bounce}
              onChange={setValue}
            />
          ))}
        </div>
      ))}

      <SubmitBar
        label={copy(stored ? 'student_survey.submit_again' : 'student_survey.submit')}
        busy={busy}
        missingAnswer={missing}
        missingAnswerId={missingAnswerId(sectionId)}
        showConfidentiality={showConfidentiality}
        showResubmitNote={!stored}
        onSubmit={() => {
          void submit();
        }}
      />
    </div>
  );
}

/** One question, drawn by the primitive its kind names. */
function QuestionField({
  question,
  sectionId,
  values,
  bounce,
  onChange,
}: {
  readonly question: SurveyQuestion;
  readonly sectionId: string;
  readonly values: Readonly<Record<number, string>>;
  readonly bounce: Bounce | null;
  readonly onChange: (position: number, value: string) => void;
}): JSX.Element | null {
  const id = fieldId(sectionId, question.position);
  const raw = values[question.position] ?? '';

  if (question.kind === 'likert') {
    return (
      <LikertInput
        question={question}
        name={id}
        value={raw === '' ? null : raw}
        onSelect={(value) => {
          onChange(question.position, value);
        }}
      />
    );
  }

  if (question.kind === 'comment') {
    const coached = bounce !== null && bounce.positions.includes(question.position);
    const required = isCommentRequired(question, values);
    const state: CommentState = coached ? 'bounce' : required ? 'required' : 'optional';
    return (
      <ConditionalTextArea
        id={id}
        state={state}
        required={required}
        value={raw}
        bounceMessage={coached ? bounce.message : undefined}
        onChange={(value) => {
          onChange(question.position, value);
        }}
      />
    );
  }

  if (question.kind === 'workload') {
    return (
      <WorkloadSlider
        question={question}
        id={id}
        value={raw === '' ? null : raw}
        onChange={(value) => {
          onChange(question.position, value);
        }}
      />
    );
  }

  // A kind this build does not know how to draw. Nothing rather than a guess: a
  // control chosen for the wrong kind submits into the wrong column and the
  // write path refuses it with a sentence about the instrument.
  return null;
}

/** The short marigold pulse line the brief puts under a page title. */
function PulseDivider(): JSX.Element {
  return (
    <svg
      className="pulse-line pulse-line-divider"
      width="120"
      height="14"
      viewBox="0 0 120 14"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M1 10 H52 L60 3 L68 10 H106"
        stroke="var(--marigold)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="112" cy="10" r="3.5" fill="var(--marigold)" />
    </svg>
  );
}

/** One field's DOM id, which is also the Likert group's radio name. */
function fieldId(sectionId: string, position: number): string {
  return `survey-${sectionId}-q${position}`;
}

/** Where one section's submit control finds its own description. */
function missingAnswerId(sectionId: string): string {
  return `survey-${sectionId}-missing`;
}

/**
 * The first question this week cannot be sent without, or nothing.
 *
 * The same rule the submit button used to be disabled by: every question but a
 * comment, and a comment that SPEC §3.2's conditional rule has made required.
 * In position order, because "the first unanswered question" is the one a
 * student reading down the form meets first.
 */
function firstUnanswered(
  questions: readonly SurveyQuestion[],
  values: Readonly<Record<number, string>>,
): SurveyQuestion | null {
  const owed = questions.find((question) => {
    if (isAnswered(values, question)) return false;
    return question.kind !== 'comment' || isCommentRequired(question, values);
  });
  return owed ?? null;
}

/** What the submit control says about the question it stopped at (E2-17 item 1). */
function missingAnswerSentence(question: SurveyQuestion): string {
  const named = questionName(question);
  return named === null
    ? copy('student_survey.missing_answer_unnamed')
    : fillCopy('student_survey.missing_answer', { question: named });
}

/**
 * What to call one question in a sentence about it, or nothing.
 *
 * The served wording when there is one. SPEC §3.2 quotes none for the two
 * comments or the slider — `scripts/seed.py` stores `null` for all three — so
 * their own labels stand in, which are this surface's copy and are what the
 * student is looking at. A rating question with no wording at all leaves nothing
 * honest to say, and the caller has a sentence for that rather than quoting an
 * empty string or leaking the machine name.
 */
function questionName(question: SurveyQuestion): string | null {
  const prompt = (question.prompt ?? '').trim();
  if (prompt !== '') return prompt;
  if (question.kind === 'comment') return copy('student_survey.comment_label');
  if (question.kind === 'workload') return copy('student_survey.workload_label');
  return null;
}

/** The positions of every comment SPEC §3.2's conditional rule requires right now. */
function requiredComments(
  questions: readonly SurveyQuestion[],
  values: Readonly<Record<number, string>>,
): number[] {
  return questions
    .filter((question) => question.kind === 'comment' && isCommentRequired(question, values))
    .map((question) => question.position);
}

/**
 * The reader's own answers, laid out by position, ready to be edited again.
 *
 * All three value columns travel on the read for exactly this reason
 * (`app.schemas.student`): a prefill missing one would blank a field the student
 * had filled in, and the resubmission would then overwrite what they wrote with
 * nothing. The workload figure is re-formatted to the precision its question
 * steps in, so a column that stores `6.50` reads back as the `6.5` the slider
 * offers.
 */
function initialValues(survey: OpenSurvey): Record<number, string> {
  const submitted = new Map(
    (survey.submission?.answers ?? []).map((answer) => [answer.question_id, answer]),
  );
  const values: Record<number, string> = {};
  for (const question of survey.questions) {
    const answer = submitted.get(question.id);
    if (answer === undefined) continue;
    if (answer.rating !== null) values[question.position] = String(answer.rating);
    else if (answer.comment_text !== null) values[question.position] = answer.comment_text;
    else if (answer.workload_hours !== null) {
      values[question.position] = onStepScale(answer.workload_hours, question.step);
    }
  }
  return values;
}

/** A stored decimal in the precision its question's step is written to. */
function onStepScale(value: string, step: string | null): string {
  const fraction = (step ?? '').split('.')[1];
  const places = fraction === undefined ? 0 : fraction.replace(/0+$/, '').length;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toFixed(places) : value;
}

/** Whether this question carries an answer worth sending. */
function isAnswered(values: Readonly<Record<number, string>>, question: SurveyQuestion): boolean {
  return (values[question.position] ?? '').trim() !== '';
}

/**
 * SPEC §3.2's conditional rule, read off the question row.
 *
 * "Required if Q1 ≤ 2", carried as `required_if_position` and
 * `required_if_at_most` so that a later set's rule travels with it. A rule
 * naming a position this set has no answer at yet is not a rule anything can
 * evaluate, so it is not applied — which is also what the write path does with
 * a dangling one.
 */
function isCommentRequired(
  question: SurveyQuestion,
  values: Readonly<Record<number, string>>,
): boolean {
  const { required_if_position: dependsOn, required_if_at_most: atMost } = question;
  if (dependsOn === null || atMost === null) return false;
  const raw = (values[dependsOn] ?? '').trim();
  // An unanswered rating is not a low one. Tested for as an empty string rather
  // than through the number, because `Number('')` is 0 and 0 is at most 2 — the
  // reading under which every comment is required before anything is answered.
  if (raw === '') return false;
  const answered = Number(raw);
  return Number.isFinite(answered) && answered <= atMost;
}

/**
 * The submission body, in the shape `app.schemas.survey` parses.
 *
 * A question left blank is an **absent entry**, never one holding null: "the
 * comment is blank" and "the required comment is missing" look the same on the
 * wire, and what tells them apart is the rating beside it.
 */
function buildAnswers(
  questions: readonly SurveyQuestion[],
  values: Readonly<Record<number, string>>,
): SubmittedValue[] {
  const answers: SubmittedValue[] = [];
  for (const question of questions) {
    const raw = values[question.position] ?? '';
    if (raw.trim() === '') continue;
    if (question.kind === 'likert') {
      answers.push({ position: question.position, rating: Number(raw) });
    } else if (question.kind === 'comment') {
      answers.push({ position: question.position, comment_text: raw });
    } else if (question.kind === 'workload') {
      answers.push({ position: question.position, workload_hours: raw.trim() });
    }
  }
  return answers;
}

/** Which comment positions this submission actually carried. */
function submittedCommentPositions(
  questions: readonly SurveyQuestion[],
  values: Readonly<Record<number, string>>,
): number[] {
  return questions
    .filter((question) => question.kind === 'comment' && isAnswered(values, question))
    .map((question) => question.position);
}

/**
 * The questions in cards, a rating with the comment that depends on it.
 *
 * The pairing is read off `required_if_position` rather than off the positions
 * being adjacent, so a versioned set that orders its questions differently
 * groups correctly and one that pairs nothing gets a card per question.
 */
function groupQuestions(questions: readonly SurveyQuestion[]): SurveyQuestion[][] {
  const groups: SurveyQuestion[][] = [];
  for (const question of questions) {
    const previous = groups.at(-1);
    const joins =
      previous !== undefined &&
      question.kind === 'comment' &&
      question.required_if_position !== null &&
      previous.some((held) => held.position === question.required_if_position);
    if (joins && previous !== undefined) previous.push(question);
    else groups.push([question]);
  }
  return groups;
}
