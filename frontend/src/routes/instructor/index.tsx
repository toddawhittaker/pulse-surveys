import { useEffect, useState, type JSX } from 'react';

import { Link, useNavigate } from '@tanstack/react-router';

import { readTaughtSections, type TaughtSectionView } from '../../api/instructor';
import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/instructorReportPageCopy';
import '../../components/instructorReportPage.css';
import { INSTRUCTOR_LANDING_TESTID, REPORT_ROUTE } from './InstructorMondayReport';

/**
 * The instructor area's front door — SPEC §13's `routes/instructor/`, E4-11.
 *
 * It used to be an empty landing view, "empty by design rather than unfinished:
 * the Monday report is what this route grows into". This is that growth, and the
 * shape it took is a **dispatcher** rather than a report: SPEC §5.1's report is
 * per section, every route serving it takes a section key, and nothing a client
 * holds supplies one — a launch redirect carries the role and the session, and
 * the session claims carry keys and never sections. So this page asks
 * `GET /instructor/sections` (E4-18) whose sections these are and then gets out
 * of the way.
 *
 * **Four answers, four behaviours.** A reader who teaches nothing gets a calm
 * state saying so — an ordinary condition for a new instructor, and answered 200
 * by a route that has no refusal to make about it. A reader who teaches exactly
 * one section never sees this page at all: it replaces itself with her report,
 * because a menu of one is a page asking somebody to confirm they are where they
 * already are. A reader who teaches several gets the menu. And a read that was
 * refused or that failed gets the states the report page gets, for the same
 * reasons — a 401 says which page can answer, and everything else says the read
 * did not land rather than that she teaches nothing.
 *
 * **The section list is a menu and carries no figure**, which is the schema's
 * decision rather than this page's: `TaughtSection` has three members and no
 * fourth, so there is no rate, no roster size and no week here to have had a §4
 * suppression rule applied to it.
 */

/** Where a spec finds the section menu, as opposed to one of this page's states. */
export const INSTRUCTOR_SECTIONS_TESTID = 'pulse-instructor-sections';

const HEADING_ID = 'pulse-instructor-sections-heading';

/** What the read answered, as this screen holds it. */
type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'sections'; readonly sections: readonly TaughtSectionView[] };

export function InstructorLanding(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    void readTaughtSections().then((answer) => {
      if (!live) return;
      if (answer.kind === 'sections') {
        setLoad({ kind: 'sections', sections: answer.sections });
      } else if (answer.kind === 'session-ended') {
        // Never the "you teach nothing" state. A refused read and an empty
        // teaching set are different facts, and only one of them entitles this
        // page to say anything about what she teaches — the same distinction the
        // student surface draws between a refused read and an empty week.
        setLoad({ kind: 'session-ended' });
      } else {
        setLoad({ kind: 'error', detail: answer.detail });
      }
    });
    return () => {
      live = false;
    };
  }, []);

  const only = load.kind === 'sections' && load.sections.length === 1 ? load.sections[0] : undefined;

  useEffect(() => {
    if (only === undefined) return;
    // **Replace rather than push.** This page decided nothing a reader chose, so
    // leaving it in the history would put a back button between her report and
    // wherever she came from, and pressing it would land here and bounce her
    // forward again.
    void navigate({ to: REPORT_ROUTE, params: { sectionId: only.section_id }, replace: true });
  }, [navigate, only]);

  const picking = load.kind === 'sections' && load.sections.length > 1;

  return (
    <main
      className="pulse-report"
      data-testid={INSTRUCTOR_LANDING_TESTID}
      aria-labelledby={HEADING_ID}
    >
      <h1 className="pulse-report-title" id={HEADING_ID}>
        {copy(
          picking ? 'instructor_report_page.picker_heading' : 'instructor_report_page.heading',
        )}
      </h1>
      <LandingBody load={load} />
    </main>
  );
}

function LandingBody({ load }: { readonly load: Load }): JSX.Element | null {
  if (load.kind === 'loading') {
    return (
      <p className="pulse-report-status" role="status">
        {copy('instructor_report_page.loading')}
      </p>
    );
  }
  if (load.kind === 'session-ended') {
    return (
      <StateNotice
        variant="flat"
        title={copy('instructor_report_page.session_ended_title')}
        body={copy('instructor_report_page.session_ended_body')}
      />
    );
  }
  if (load.kind === 'error') {
    return (
      <StateNotice variant="flat" body={load.detail ?? copy('instructor_report_page.unavailable')} />
    );
  }
  if (load.sections.length === 0) {
    return (
      <StateNotice
        variant="flat"
        title={copy('instructor_report_page.no_sections_title')}
        body={copy('instructor_report_page.no_sections_body')}
      />
    );
  }
  if (load.sections.length === 1) {
    // The effect above is navigating away. Saying nothing new here is
    // deliberate: a sentence about a redirect is a sentence a reader meets for
    // a fraction of a second and cannot act on.
    return (
      <p className="pulse-report-status" role="status">
        {copy('instructor_report_page.loading')}
      </p>
    );
  }

  return (
    <div data-testid={INSTRUCTOR_SECTIONS_TESTID}>
      <p className="pulse-report-note">{copy('instructor_report_page.picker_body')}</p>
      <ul
        className="pulse-report-sections"
        aria-label={copy('instructor_report_page.picker_list_label')}
      >
        {load.sections.map((section) => (
          <li key={section.section_id}>
            {/* A link and not a button: a report has an address, so a reader can
                open one in a new tab, bookmark it, or send it to somebody. The
                name is the label the server composed — the same governed form
                the report's own heading carries, so a section is named one way
                in the menu and in the page the menu opens. */}
            <Link
              className="pulse-report-section-link"
              to={REPORT_ROUTE}
              params={{ sectionId: section.section_id }}
            >
              {section.course_label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
