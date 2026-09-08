import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import { SECTIONS_PATH, publishedWeeksPath, reportPath } from '../../api/instructor';
import { routeTree } from '../../router';
import {
  A_PUBLISHED_WEEK,
  A_SMALL_N_WEEK,
  COURSE_LABEL,
  ONE_TAUGHT_SECTION,
  OTHER_COURSE_LABEL,
  OTHER_SECTION_ID,
  PUBLISHED_WEEKS,
  SECTION_ID,
  TWO_TAUGHT_SECTIONS,
} from './instructorReportFixtures';

/**
 * What the instructor area's two addresses do — ticket E4-11.
 *
 * The states each page can be in are driven in `InstructorMondayReport.test.tsx`
 * against props. This file is about the other half of the ticket: which address
 * opens which page, what an address says about a week, and what choosing a week
 * does to the address (criterion 6). It mounts the application's **own** route
 * tree on a memory history rather than a second table written for a test — a
 * second table is a route map that can agree with a test and disagree with the
 * application.
 */

/** Governed copy, transcribed rather than imported (`docs/MISTAKES.md` entry 19). */
const NO_SECTIONS_TITLE = 'No sections to report on yet';
const PICKER_HEADING = 'Your sections';
const COURSE_WEEK_UNAVAILABLE = 'There is no report for that week of this section.';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** Serve the stack, one answer per address, and remember the order they were asked in. */
function serving(answers: Record<string, () => Response>): string[] {
  const asked: string[] = [];
  vi.stubGlobal('fetch', (input: string) => {
    asked.push(input);
    const answer = answers[input];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

/** The whole application, mounted at one address on a memory history. */
function mountAt(address: string) {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [address] }),
  });
  render(<RouterProvider router={router} />);
  return router;
}

/** Where the browser would be: the path the router is on, and its query string. */
function addressOf(router: ReturnType<typeof mountAt>): string {
  return router.state.location.href;
}

describe('/instructor, the dispatcher', () => {
  it('says so calmly when the reader teaches nothing', async () => {
    // `app.api.instructor` answers a person who teaches nothing 200 with an
    // empty list, and says why in as many words: a 404 invented there "would
    // refuse a new instructor on the day she is hired". This is the page half of
    // the same decision — an ordinary state, not a refusal.
    serving({ [SECTIONS_PATH]: () => json(200, { sections: [] }) });
    const router = mountAt('/app/instructor');

    await screen.findByText(NO_SECTIONS_TITLE);
    expect(addressOf(router)).toBe('/instructor');
    expect(screen.getByTestId('pulse-landing-instructor')).toBeTruthy();
  });

  it('replaces itself with the report when the reader teaches exactly one section', async () => {
    serving({
      [SECTIONS_PATH]: () => json(200, { sections: ONE_TAUGHT_SECTION }),
      [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [reportPath(SECTION_ID, 7)]: () => json(200, A_SMALL_N_WEEK),
    });
    const router = mountAt('/app/instructor');

    // The report itself, at the section's own address.
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });
    expect(addressOf(router)).toBe(`/instructor/sections/${SECTION_ID}`);

    // **Replaced rather than pushed.** A menu of one decided nothing the reader
    // chose, so leaving it in the history would put a back button between her
    // report and wherever she came from, and pressing it would bounce her
    // forward again.
    expect(router.history.length).toBe(1);

    // The landing testid survives the redirect, which is what nine end-to-end
    // specs assert to say an instructor launch landed.
    expect(screen.getByTestId('pulse-landing-instructor')).toBeTruthy();
  });

  it('offers a menu named by the server’s own labels when there are several', async () => {
    serving({
      [SECTIONS_PATH]: () => json(200, { sections: TWO_TAUGHT_SECTIONS }),
      // The second section is opened below, and it has no published week yet —
      // which is enough to say the link went somewhere, without this case also
      // having to be about a report.
      [publishedWeeksPath(OTHER_SECTION_ID)]: () => json(200, { published_weeks: [] }),
    });
    const router = mountAt('/app/instructor');

    await screen.findByRole('heading', { level: 1, name: PICKER_HEADING });
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([COURSE_LABEL, OTHER_COURSE_LABEL]);

    // Each is a real address, so a reader can open one in a new tab or send it
    // to somebody — which a button could not be.
    expect(links[0]?.getAttribute('href')).toBe(`/app/instructor/sections/${SECTION_ID}`);

    // And following one opens that section's report.
    fireEvent.click(links[1] as Element);
    await waitFor(() => {
      expect(addressOf(router)).toBe(`/instructor/sections/${OTHER_SECTION_ID}`);
    });
  });
});

describe('/instructor/sections/$sectionId, the report', () => {
  /** The stack every case below reads, with one report per published week. */
  function servingReports(): string[] {
    return serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [reportPath(SECTION_ID, 4)]: () => json(200, A_PUBLISHED_WEEK),
      [reportPath(SECTION_ID, 7)]: () => json(200, A_SMALL_N_WEEK),
    });
  }

  it('opens the week the address names', async () => {
    const asked = servingReports();
    mountAt(`/app/instructor/sections/${SECTION_ID}?week=4`);

    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });
    expect(asked).toContain(reportPath(SECTION_ID, 4));
    expect(asked).not.toContain(reportPath(SECTION_ID, 7));
  });

  it('opens the latest published week when the address names none', async () => {
    const asked = servingReports();
    mountAt(`/app/instructor/sections/${SECTION_ID}`);

    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });
    expect(asked).toContain(reportPath(SECTION_ID, 7));
  });

  // The four shapes junk arrives in, each of which would otherwise reach the API
  // as a path segment: a word, a decimal, a zero and a negative. SPEC §2.2
  // counts course weeks from one, so none of them names a week, and the page
  // does what an address with no week does — opens the latest published one.
  // A case each rather than a loop inside one, so the failure names the value.
  for (const junk of ['banana', '4.5', '0', '-2']) {
    it(`treats ?week=${junk} as no week at all`, async () => {
      const asked = servingReports();
      mountAt(`/app/instructor/sections/${SECTION_ID}?week=${junk}`);

      await screen.findByRole('heading', { level: 2, name: 'Rating trend' });
      // **The mutation this kills is measured rather than imagined.** A route's
      // validated search is merged over what came off the address, so a
      // validator that refuses a value by omitting the member leaves the raw one
      // standing — and the page then asks the API for a report on week
      // "banana". Every one of these four cases was red against exactly that.
      expect(asked).toContain(reportPath(SECTION_ID, 7));
      expect(asked).not.toContain(reportPath(SECTION_ID, 4));
    });
  }

  it('puts a chosen week in the address, so any week a reader reaches is a link', async () => {
    // Criterion 6. The week lives in the address rather than in this page's
    // state, which is the whole of what makes it linkable.
    servingReports();
    const router = mountAt(`/app/instructor/sections/${SECTION_ID}?week=4`);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }));

    await waitFor(() => {
      expect(addressOf(router)).toBe(`/instructor/sections/${SECTION_ID}?week=7`);
    });
    // And the week that arrived is the one the address now names.
    await screen.findByRole('region', { name: 'Comments are hidden this week' });
  });

  it('mirrors the API on a deep link to a week that is not published', async () => {
    // Criterion 6's second half. Week 3 is not in the published list, and this
    // page does not check that: it asks, and shows the refusal the route makes.
    // A membership test here would be a second copy of the rule that decides
    // which weeks a section has.
    const asked = serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [reportPath(SECTION_ID, 3)]: () => json(404, { detail: COURSE_WEEK_UNAVAILABLE }),
    });
    mountAt(`/app/instructor/sections/${SECTION_ID}?week=3`);

    await screen.findByText(COURSE_WEEK_UNAVAILABLE);
    expect(asked).toContain(reportPath(SECTION_ID, 3));
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });
});
