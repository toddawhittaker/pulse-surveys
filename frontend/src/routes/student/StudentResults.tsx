import { useEffect, useRef, useState, type JSX } from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';

import {
  readStudentResults,
  readStudentSurvey,
  type ResultsRead,
  type StudentStream,
  type StudentWeekResults,
} from '../../api/student';
import { CommentCard } from '../../components/CommentCard';
import { CommentGroup } from '../../components/CommentGroup';
import { PulseDivider } from '../../components/PulseDivider';
import { RatingHistogram, type RatingDistribution } from '../../components/RatingHistogram';
import { ResponseCard } from '../../components/ResponseCard';
import { SmallNNotice } from '../../components/SmallNNotice';
import { StateNotice } from '../../components/StateNotice';
import { TrendDuo } from '../../components/TrendDuo';
import { WeekNav } from '../../components/WeekNav';
import { copy, fillCopy } from '../../copy/studentResults';

/**
 * SPEC §7.6's `StudentResults` — the shell: one section's reply for one
 * published week, and the way back through the published weeks (SPEC §5.4).
 *
 * **The course is named first, in every state.** The label is the section's own
 * course and says nothing about the week. Then the response leads the page (the
 * page is a reply, not a dashboard), the student's own posted score follows it,
 * and below them, in a released week only, come the trend, the distributions, the
 * workload median, the comments, the comments released from earlier weeks and the
 * page's one confidentiality line.
 *
 * **The page asks and draws.** Which weeks exist, which state the week is in and
 * who wrote the reply are the API's answers; a week the API refuses is the same
 * single calm sentence as any other refusal, and nothing here distinguishes
 * "not yours" from "not yet" because the server does not.
 *
 * **`awaiting` is a closed door.** One sentence: no number, date, countdown,
 * name or response text, because the week is held and anything more would tease
 * it.
 *
 * **Everything below the response is gated on the state before it is read.** A
 * held week draws none of it whatever the payload happens to hold, the same
 * fail-closed rule the response follows. A member the payload sends as null draws
 * nothing, and no stream is ever compared with anything: the page holds this
 * section's own figures only (SPEC §4.1 item 1, §5.4).
 *
 * The survey read is made beside the results one for the one thing the results
 * do not carry: the institution's time zone, which the date on the card is shown
 * in. A failed survey read costs the card its date, not the page its reply.
 */

/** The two addresses this page answers, relative to the router's `/app` mount. */
export const LATEST_RESULTS_ROUTE = '/student/sections/$sectionId/results';
export const WEEK_RESULTS_ROUTE = '/student/sections/$sectionId/weeks/$courseWeek/results';

/**
 * Set when the student picks a week, so that focus moves to the heading once
 * that week's answer is drawn, not on the first load. Module-level because
 * moving between the "latest" and a named week changes the route, which
 * mounts a new page; a flag held by the old one would be lost with it.
 */
let focusHeadingOnLoad = false;

const HEADING_ID = 'pulse-student-results-heading';

type Load =
  | { readonly kind: 'loading' }
  | {
      readonly kind: 'read';
      readonly answer: Exclude<ResultsRead, { kind: 'results' }>;
    }
  | {
      readonly kind: 'results';
      readonly results: StudentWeekResults;
      readonly week: number | null;
    };

/** A course week from an address, or `null` for anything that is not a positive whole number. */
function weekOfAddress(raw: string | undefined): number | null | undefined {
  if (raw === undefined) return undefined;
  const asked = Number(raw);
  return Number.isInteger(asked) && asked > 0 ? asked : null;
}

export function StudentResults({
  sectionId,
  courseWeek,
  onSelectWeek,
}: {
  readonly sectionId: string;
  /** `undefined` opens the latest published week; `null` is an address that names no week. */
  readonly courseWeek: number | null | undefined;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [timeZone, setTimeZone] = useState<string | undefined>(undefined);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let live = true;
    if (courseWeek === null) {
      // An address naming no week asks nothing of the API.
      void Promise.resolve().then(() => {
        if (live) setLoad({ kind: 'read', answer: { kind: 'nothing' } });
      });
      return () => {
        live = false;
      };
    }
    void readStudentResults(sectionId, courseWeek).then((answer) => {
      if (!live) return;
      if (focusHeadingOnLoad) {
        focusHeadingOnLoad = false;
        // After the state below renders; the heading exists in every state.
        requestAnimationFrame(() => headingRef.current?.focus());
      }
      setLoad(
        answer.kind === 'results'
          ? {
              kind: 'results',
              results: answer.results,
              week: courseWeek ?? null,
            }
          : { kind: 'read', answer },
      );
    });
    return () => {
      live = false;
    };
  }, [sectionId, courseWeek]);

  useEffect(() => {
    let live = true;
    void readStudentSurvey().then((answer) => {
      if (!live || answer.kind !== 'view') return;
      setTimeZone(answer.view.institution_timezone);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="pulse-survey" data-testid="pulse-student-results" aria-labelledby={HEADING_ID}>
      <h1 id={HEADING_ID} ref={headingRef} tabIndex={-1}>
        {copy('student_results.heading')}
      </h1>
      <PulseDivider />
      <Body
        load={load}
        timeZone={timeZone}
        onSelectWeek={(week) => {
          focusHeadingOnLoad = true;
          onSelectWeek(week);
        }}
      />
    </main>
  );
}

function Body({
  load,
  timeZone,
  onSelectWeek,
}: {
  readonly load: Load;
  readonly timeZone: string | undefined;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  if (load.kind === 'loading') {
    return (
      <p className="pulse-survey-status" role="status">
        {copy('student_results.loading')}
      </p>
    );
  }
  if (load.kind === 'read') {
    if (load.answer.kind === 'session-ended') {
      return (
        <StateNotice
          variant="flat"
          title={copy('student_results.session_ended_title')}
          body={copy('student_results.session_ended_body')}
        />
      );
    }
    return (
      <StateNotice
        variant="flat"
        body={copy(
          load.answer.kind === 'nothing'
            ? 'student_results.nothing_to_show'
            : 'student_results.unavailable',
        )}
      />
    );
  }

  const { results } = load;
  // The week the reply belongs to is the one asked for; for "the latest" it is
  // the last published week, which the payload lists in ascending order.
  const current = load.week ?? results.published_weeks.at(-1) ?? null;
  return (
    <>
      <h2 className="pulse-results-course" data-testid="pulse-results-course">
        {results.course_label}
      </h2>
      {current === null ? null : (
        <div className="pulse-results-week">
          {/* A held week shows no number, not even its own week's. */}
          {results.state === 'awaiting' ? null : (
            <p className="pulse-eyebrow">
              {fillCopy('student_results.week_label', {
                week: String(current),
              })}
            </p>
          )}
          <WeekNav
            publishedWeeks={results.published_weeks}
            currentWeek={current}
            onSelectWeek={onSelectWeek}
          />
        </div>
      )}
      <Reply results={results} timeZone={timeZone} />
      <Participation participation={results.participation ?? null} />
      {results.state === 'awaiting' ? null : <Week results={results} />}
    </>
  );
}

type RatingKey = '1' | '2' | '3' | '4' | '5';

/** The wire's shares keyed 1 to 5, with a missing bucket read as none. */
function sharesOf(shares: Readonly<Record<string, number>>): RatingDistribution {
  const share = (key: RatingKey): number => shares[key] ?? 0;
  return { '1': share('1'), '2': share('2'), '3': share('3'), '4': share('4'), '5': share('5') };
}

/**
 * One stream's ratings as shares, or the student notice when too few students
 * rated to show them: the payload sends `shares` null then, and nothing here
 * draws a number in its place.
 */
function Distribution({ stream }: { readonly stream: StudentStream }): JSX.Element {
  if (stream.shares === null) {
    const title = copy(
      stream.stream === 'instructor'
        ? 'student_results.ratings_held_instructor'
        : 'student_results.ratings_held_course',
    );
    return (
      <div className="pulse-results-held-chart">
        <SmallNNotice title={title} body={copy('student_results.ratings_held_body')} />
      </div>
    );
  }
  return (
    <RatingHistogram stream={stream.stream} distribution={sharesOf(stream.shares)} unit="percent" />
  );
}

/**
 * What a released week holds below the response, in the order the page reads:
 * trend, distributions, workload, comments, comments from earlier weeks, and the
 * confidentiality line once. Each member that arrived null draws nothing.
 */
function Week({ results }: { readonly results: StudentWeekResults }): JSX.Element {
  const streams = results.streams ?? [];
  const instructor = streams.find((stream) => stream.stream === 'instructor');
  const course = streams.find((stream) => stream.stream === 'course');
  const released = results.released ?? [];
  const lengthWeeks = Math.max(1, ...results.published_weeks);
  const points = (stream: StudentStream | undefined) =>
    (stream?.trend ?? []).map((point) => ({
      courseWeek: point.course_week,
      termWeek: null,
      mean: point.mean,
    }));

  return (
    <>
      {instructor === undefined || course === undefined ? null : (
        <section className="pulse-results-figures" aria-labelledby="pulse-class-heading">
          <h2 id="pulse-class-heading">{copy('student_results.class_heading')}</h2>
          <TrendDuo
            instructor={points(instructor)}
            course={points(course)}
            lengthWeeks={lengthWeeks}
          />
          <Distribution stream={instructor} />
          <Distribution stream={course} />
        </section>
      )}
      {results.workload_median === null ? null : (
        <p className="pulse-results-workload">
          {fillCopy('student_results.workload_median', {
            hours: results.workload_median.toFixed(1),
          })}
        </p>
      )}
      {[instructor, course].map((stream) =>
        stream === undefined ? null : (
          <CommentGroup
            key={stream.stream}
            audience="student"
            stream={stream.stream}
            suppressed={stream.small_n}
            // A held stream's comments are not read at all, whatever the array holds.
            comments={stream.small_n ? [] : stream.comments.map(({ text }) => ({
              text,
              status: 'published' as const,
            }))}
          />
        ),
      )}
      {released.length === 0 ? null : (
        <section className="pulse-results-released" aria-labelledby="pulse-released-heading">
          <h3 id="pulse-released-heading">{copy('student_results.released_heading')}</h3>
          <ul className="pulse-comment-group__cards">
            {released.map((comment, position) => (
              <li key={position}>
                <CommentCard text={comment.text} status="published" stream={comment.stream} />
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="pulse-results-confidentiality">{copy('student_results.confidentiality')}</p>
    </>
  );
}

function Reply({
  results,
  timeZone,
}: {
  readonly results: StudentWeekResults;
  readonly timeZone: string | undefined;
}): JSX.Element {
  if (results.state === 'awaiting') {
    return <StateNotice variant="flat" body={copy('student_results.awaiting')} />;
  }
  if (results.state === 'unanswered' || results.response === null) {
    return <StateNotice variant="flat" body={copy('student_results.unanswered')} />;
  }
  return (
    <ResponseCard
      text={results.response.text}
      authorName={results.response.author_name}
      authorRole={results.response.author_role}
      publishedAt={results.response.published_at}
      timeZone={timeZone}
    />
  );
}

/**
 * The student's own posted score and ledger, line for line, with the one
 * sentence about re-checking. It is their own record and not an aggregate, so it
 * shows in every state, `awaiting` included. Before any score has been posted
 * there is nothing: no zero and no placeholder (SPEC §3.4).
 */
function Participation({
  participation,
}: {
  readonly participation: StudentWeekResults['participation'] | null;
}): JSX.Element | null {
  if (participation === null || participation === undefined) return null;
  return (
    <section className="pulse-results-participation" aria-labelledby="pulse-participation-heading">
      <h2 id="pulse-participation-heading">{copy('student_results.participation_heading')}</h2>
      <p>{fillCopy('student_results.participation_score', { score: participation.score_text })}</p>
      {/* The server joins the ledger's lines with a newline; one item per line keeps them apart. */}
      <ul className="pulse-results-ledger">
        {participation.ledger_text.split('\n').map((line, position) => (
          <li key={position}>{line}</li>
        ))}
      </ul>
      <p>{copy('student_results.participation_note')}</p>
    </section>
  );
}

/** Route glue: the address in, a navigation out. */
export function StudentResultsRoute(): JSX.Element {
  const { sectionId, courseWeek } = useParams({ strict: false });
  const navigate = useNavigate();
  return (
    <StudentResults
      key={`${sectionId ?? ''}:${courseWeek ?? 'latest'}`}
      sectionId={sectionId ?? ''}
      courseWeek={weekOfAddress(courseWeek)}
      onSelectWeek={(week) => {
        void navigate({
          to: WEEK_RESULTS_ROUTE,
          params: { sectionId: sectionId ?? '', courseWeek: String(week) },
        });
      }}
    />
  );
}
