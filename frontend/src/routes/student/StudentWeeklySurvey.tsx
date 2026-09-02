import { useEffect, useState, type JSX } from 'react';

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
import { copy } from '../../copy/studentSurvey';

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
  | { readonly kind: 'sections'; readonly sections: readonly EnrolledSection[] }
  | { readonly kind: 'unavailable' };

export function StudentWeeklySurvey(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    void readStudentSurvey().then((answer) => {
      if (!live) return;
      if (answer.kind === 'view') {
        setLoad({ kind: 'sections', sections: answer.view.sections });
      } else if (answer.kind === 'no-session') {
        // Nobody is *sent* here without a session, so this is somebody who
        // navigated to the address. The honest answer is the same one somebody
        // between terms gets: there is nothing here for you right now.
        setLoad({ kind: 'sections', sections: [] });
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
  if (load.kind === 'unavailable') {
    return <StateNotice variant="flat" body={copy('student_survey.unavailable')} />;
  }
  if (load.sections.length === 0) {
    return <StateNotice variant="flat" body={copy('student_survey.no_open_window')} />;
  }
  return (
    <>
      {load.sections.map((section) => (
        <SectionSurvey key={section.section_id} section={section} />
      ))}
    </>
  );
}

/** One enrolled section: its code, and whatever there is to do about it. */
function SectionSurvey({ section }: { readonly section: EnrolledSection }): JSX.Element {
  const survey = section.survey_is_open ? section.open_survey : null;
  return (
    <section className="pulse-survey-section" data-testid={sectionTestid(section.section_code)}>
      <h2 className="pulse-section-code">{section.section_code}</h2>
      {survey === null ? (
        <StateNotice
          variant="flat"
          title={copy('student_survey.section_closed_title')}
          body={copy('student_survey.section_closed_body')}
        />
      ) : (
        <OpenSurveyForm sectionId={section.section_id} survey={survey} />
      )}
    </section>
  );
}

/** Where a spec finds one section's block. */
export function sectionTestid(sectionCode: string): string {
  return `survey-section-${sectionCode}`;
}

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
 */
function OpenSurveyForm({
  sectionId,
  survey,
}: {
  readonly sectionId: string;
  readonly survey: OpenSurvey;
}): JSX.Element {
  const [values, setValues] = useState<Record<number, string>>(() => initialValues(survey));
  const [stored, setStored] = useState(survey.submission !== null);
  const [showForm, setShowForm] = useState(survey.submission === null);
  const [bounce, setBounce] = useState<Bounce | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [closed, setClosed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function setValue(position: number, value: string): void {
    setValues((current) => ({ ...current, [position]: value }));
    // Editing a coached field takes the coaching off that field and leaves it on
    // the others. The message itself is unchanged while any field still carries
    // it, so the live region does not announce the same sentence twice.
    setBounce((current) => {
      if (current === null) return null;
      const remaining = current.positions.filter((carried) => carried !== position);
      return remaining.length === 0 ? null : { ...current, positions: remaining };
    });
    setRefusal(null);
  }

  async function submit(): Promise<void> {
    setBusy(true);
    setRefusal(null);
    const outcome = await submitWeeklySurvey(
      { section_id: sectionId, answers: buildAnswers(survey.questions, values) },
      copy('student_survey.unavailable'),
    );
    setBusy(false);

    if (outcome.kind === 'stored') {
      setStored(true);
      setShowForm(false);
      setBounce(null);
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

  if (closed !== null) {
    return <StateNotice variant="flat" body={closed} />;
  }

  if (!showForm) {
    return (
      <StateNotice
        variant="beat"
        title={copy('student_survey.submitted_title')}
        body={copy('student_survey.submitted_body')}
      >
        <button
          type="button"
          className="pulse-secondary"
          onClick={() => {
            setShowForm(true);
          }}
        >
          {copy('student_survey.submitted_revise')}
        </button>
      </StateNotice>
    );
  }

  const incomplete = survey.questions.some((question) => {
    if (isAnswered(values, question)) return false;
    return question.kind !== 'comment' || isCommentRequired(question, values);
  });

  return (
    <div className="pulse-survey-form">
      <WeekEyebrow
        courseWeek={survey.course_week}
        termWeek={survey.term_week}
        closesAt={survey.closes_at}
      />

      {/* One live region for the whole form, so §3.3's coaching is announced
          once when it arrives rather than once per field carrying it. The region
          is in the document from the first render: a region added at the moment
          it has something to say is a region assistive technology has not been
          watching. */}
      <p className="pulse-bounce-announcement" role="status" aria-live="polite">
        {bounce?.message ?? ''}
      </p>
      {refusal === null ? null : (
        <p className="pulse-refusal" role="alert">
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
        disabled={incomplete || busy}
        busy={busy}
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
    const state: CommentState = coached
      ? 'bounce'
      : isCommentRequired(question, values)
        ? 'required'
        : 'optional';
    return (
      <ConditionalTextArea
        id={id}
        state={state}
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
