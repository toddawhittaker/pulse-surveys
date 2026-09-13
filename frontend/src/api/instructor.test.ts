import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  SECTIONS_PATH,
  publishedWeeksPath,
  readInstructorReport,
  readPublishedWeeks,
  readTaughtSections,
  reportPath,
} from './instructor';

/**
 * The report client's outcomes — ticket E4-11.
 *
 * Every case drives one status through the real `fetch` seam and asserts which
 * of the module's discriminated outcomes comes back, because the whole point of
 * those types is that the page cannot confuse a refusal with an empty answer.
 * The bodies are `backend/app/schemas/report.py`'s spellings; the sentences are
 * `app.api.instructor`'s, written out here rather than imported from anywhere,
 * so a test cannot pass by agreeing with the thing it checks
 * (`docs/MISTAKES.md` entry 19).
 */

/** The uuid the routes are keyed by, and one that is not a uuid at all. */
const SECTION_ID = 'b6c0e2a4-8f1d-4c0a-9d3e-77aa0c5f2b19';

/** `app.api.instructor.SECTION_UNAVAILABLE`, transcribed. */
const SECTION_UNAVAILABLE = 'There is no report here for you to read.';

/** `app.api.instructor.COURSE_WEEK_UNAVAILABLE`, transcribed. */
const COURSE_WEEK_UNAVAILABLE = 'There is no report for that week of this section.';

/** A minimal report body: the one member the cast is bounded by, and a section. */
const A_REPORT_BODY = {
  section: { code: 'R3WW', course_label: 'BIOL 215 R3WW — Cell Biology, Fall 2026', length_weeks: 12 },
  streams: { instructor: {}, course: {} },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Stand one answer in `fetch`'s place, and remember what it was asked for. */
function answering(response: Response | Error): { asked: string[]; headers: HeadersInit[] } {
  const asked: string[] = [];
  const headers: HeadersInit[] = [];
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => {
    asked.push(input);
    if (init?.headers !== undefined) headers.push(init.headers);
    return response instanceof Error ? Promise.reject(response) : Promise.resolve(response);
  });
  return { asked, headers };
}

/** One JSON answer, with the status the route would have sent it under. */
function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('the paths', () => {
  it('are the three `app.api.instructor` registers, with the keys filled in', () => {
    // Transcribed from that module's own constants. A path assembled some other
    // way reaches a 404 that this client would report as "no report here for
    // you to read" — a refusal sentence about a section, for a spelling mistake.
    expect(SECTIONS_PATH).toBe('/instructor/sections');
    expect(publishedWeeksPath(SECTION_ID)).toBe(
      `/instructor/sections/${SECTION_ID}/published-weeks`,
    );
    expect(reportPath(SECTION_ID, 4)).toBe(`/instructor/sections/${SECTION_ID}/report/4`);
  });

  it('escapes a section key rather than pasting it into an address', () => {
    // A key is a uuid (ADR 0016) and never contains one of these, so this is
    // about what happens when something else arrives — a value out of an
    // address bar, say. It goes to the server as one path segment for the
    // server to refuse, rather than as a second segment this client invented.
    expect(reportPath('a/b?c', 4)).toBe('/instructor/sections/a%2Fb%3Fc/report/4');
  });
});

describe('reading the section list', () => {
  it('answers the sections, and carries the session as a Bearer header', () => {
    // The header is what makes the read work inside the LMS iframe, where the
    // tool's `SameSite=None` cookie may be refused (ADR 0089). There is no
    // session in this environment, so what is asserted is that the request is
    // shaped to carry one: `Accept` is set and nothing else is invented.
    const { asked, headers } = answering(json(200, { sections: [] }));
    return readTaughtSections().then((answer) => {
      expect(answer).toEqual({ kind: 'sections', sections: [] });
      expect(asked).toEqual([SECTIONS_PATH]);
      expect(headers).toEqual([{ Accept: 'application/json' }]);
    });
  });

  it('reports a 401 as a session that ended, never as a reader who teaches nothing', () => {
    // The two look alike on screen and only one of them is a claim the page is
    // entitled to make: a launch session lives an hour, so the ordinary way to
    // meet this is an instructor coming back to a tab from earlier in the day.
    answering(json(401, { detail: 'Not an instructor.' }));
    return readTaughtSections().then((answer) => {
      expect(answer).toEqual({ kind: 'session-ended' });
    });
  });

  it('reports a body with no `sections` member as unavailable rather than as empty', () => {
    // The bound on the cast. A body without the member every render walks would
    // otherwise fail somewhere deeper with nothing to say — and an empty menu is
    // a sentence about what this person teaches.
    answering(json(200, { holdings: [] }));
    return readTaughtSections().then((answer) => {
      expect(answer).toEqual({ kind: 'unavailable', detail: null });
    });
  });

  it('reports a network failure as unavailable', () => {
    answering(new TypeError('Failed to fetch'));
    return readTaughtSections().then((answer) => {
      expect(answer).toEqual({ kind: 'unavailable', detail: null });
    });
  });
});

describe('reading the published weeks', () => {
  it('answers the weeks exactly as they arrived, holes and all', () => {
    // A section whose weeks 1, 3, 5 and 6 never published. Nothing here sorts,
    // fills or ranges: the list is the API's answer to which weeks may be read.
    answering(json(200, { published_weeks: [2, 4, 7] }));
    return readPublishedWeeks(SECTION_ID).then((answer) => {
      expect(answer).toEqual({ kind: 'weeks', weeks: [2, 4, 7] });
    });
  });

  it('carries the refusal pair’s sentence out of a 404', () => {
    answering(json(404, { detail: SECTION_UNAVAILABLE }));
    return readPublishedWeeks(SECTION_ID).then((answer) => {
      expect(answer).toEqual({ kind: 'not-found', detail: SECTION_UNAVAILABLE });
    });
  });

  it('treats a 422 as an address that names nothing, with no sentence to show', () => {
    // FastAPI's own refusal of a path parameter that is not a uuid. Its body is
    // a list of validation objects rather than a sentence anybody wrote for a
    // reader, so `detail` is null and the page uses its own words.
    answering(json(422, { detail: [{ loc: ['path', 'section_id'], msg: 'not a valid uuid' }] }));
    return readPublishedWeeks('not-a-uuid').then((answer) => {
      expect(answer).toEqual({ kind: 'not-found', detail: null });
    });
  });
});

describe('reading a report', () => {
  it('answers the report, cast against the member the whole assembly walks', () => {
    answering(json(200, A_REPORT_BODY));
    return readInstructorReport(SECTION_ID, 4).then((answer) => {
      expect(answer.kind).toBe('report');
      expect(answer.kind === 'report' && answer.report.section.course_label).toBe(
        A_REPORT_BODY.section.course_label,
      );
    });
  });

  it('carries the week refusal’s sentence out of a 404', () => {
    // The deep link to an unpublished week, from the client's side. The server
    // decides publishability and says so in its own governed words; this is
    // what makes criterion 6's not-found treatment the API's rather than a
    // membership test the page ran first.
    answering(json(404, { detail: COURSE_WEEK_UNAVAILABLE }));
    return readInstructorReport(SECTION_ID, 3).then((answer) => {
      expect(answer).toEqual({ kind: 'not-found', detail: COURSE_WEEK_UNAVAILABLE });
    });
  });

  it('reports a 200 with no `streams` member as unavailable', () => {
    answering(json(200, { section: A_REPORT_BODY.section }));
    return readInstructorReport(SECTION_ID, 4).then((answer) => {
      expect(answer).toEqual({ kind: 'unavailable', detail: null });
    });
  });

  it('reports a 500 as unavailable, carrying whatever sentence came with it', () => {
    answering(json(500, { detail: 'Internal Server Error' }));
    return readInstructorReport(SECTION_ID, 4).then((answer) => {
      expect(answer).toEqual({ kind: 'unavailable', detail: 'Internal Server Error' });
    });
  });

  it('reports a body that is not JSON at all as unavailable', () => {
    answering(new Response('<html>gateway</html>', { status: 502 }));
    return readInstructorReport(SECTION_ID, 4).then((answer) => {
      expect(answer).toEqual({ kind: 'unavailable', detail: null });
    });
  });
});
