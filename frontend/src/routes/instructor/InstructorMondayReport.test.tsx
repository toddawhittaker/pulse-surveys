import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SECTIONS_PATH, publishedWeeksPath, reportPath } from '../../api/instructor';
import { InstructorMondayReport } from './InstructorMondayReport';
import {
  A_PUBLISHED_WEEK,
  A_SMALL_N_WEEK,
  A_WEEK_NOBODY_ANSWERED,
  A_WEEK_WITH_A_HELD_COMMENT,
  A_WEEK_WITH_A_RELEASE,
  A_WEEK_WITH_NOBODY_ENROLLED,
  COURSE_COMMENT,
  COURSE_LABEL,
  HELD_COMMENT,
  INSTRUCTOR_COMMENT,
  ONE_TAUGHT_SECTION,
  PUBLISHED_WEEKS,
  RELEASED_COMMENT,
  RELEASED_INSTRUCTOR_COMMENT,
  SECTION_ID,
  SMALL_N_THRESHOLD,
} from './instructorReportFixtures';

/**
 * SPEC §7.6's `InstructorMondayReport`, state by state — ticket E4-11.
 *
 * The page takes the section and the week as props and answers with a DOM, so
 * every state the ticket names is driven here against a stubbed `fetch` serving
 * `backend/app/schemas/report.py`'s shapes. What the *address* does — a deep
 * link, a week that is not published, a chosen week reaching the URL — is
 * `instructorRoutes.test.tsx`'s, against a real router.
 *
 * The expected sentences are written out rather than read from the copy module:
 * a test that asked the page what its own words were would pass against any
 * words at all (`docs/MISTAKES.md` entry 19, and the rule
 * `tests/e2e/landing-views.spec.ts` states for the same reason).
 */

/** Governed copy this page ships, transcribed from `instructorReportPageCopy.ts`. */
const LOADING = 'Opening this week’s report…';
const UNAVAILABLE = 'This report could not be loaded just now. Reload the page to try again.';
const SESSION_ENDED_TITLE = 'Open this from your course';
const NO_WEEKS_TITLE = 'No weeks have closed yet';
const COMMENTS_NOTE = 'Shown in random order. No names, no timestamps.';
const PARTICIPATION_ABSENT =
  'There is no response rate for this week: nobody is enrolled in this section yet.';
const RELEASED_HEADING = 'Comments from earlier weeks';

/**
 * The credit-rule note (E4-12), transcribed as two meaning-bearing fragments
 * rather than the whole three-sentence entry: what must survive a rewording is
 * the arithmetic and the can-move-down promise, not the phrasing around them.
 */
const CREDIT_NOTE_ARITHMETIC = 'completed items out of total items';
const CREDIT_NOTE_CAN_LOWER = 'lower a score that has already posted';

/** Copy the components ship, transcribed the same way. */
const ABSENT_SUMMARY = 'No summary was written for this week.';
const SMALL_N_TITLE = 'Comments are hidden this week';
const NO_RESPONSES = 'No responses yet this week';

/** `app.api.instructor`'s two refusal sentences, transcribed from that module. */
const SECTION_UNAVAILABLE = 'There is no report here for you to read.';
const COURSE_WEEK_UNAVAILABLE = 'There is no report for that week of this section.';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** One JSON answer, under the status the route would have sent it with. */
function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Serve the stack this page reads, one answer per address.
 *
 * A map rather than a single answer, because the page makes two reads in order
 * and the second depends on the first — a stub that answered everything the same
 * way could not tell "the weeks came back" from "the report came back".
 * An address nothing serves rejects loudly rather than answering something
 * plausible, so a test that asked for a week it did not set up says so.
 */
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

/** The ordinary stack: the published weeks, and one report per week it holds. */
function servingWeeks(
  reports: Record<number, unknown>,
  weeks: readonly number[] = PUBLISHED_WEEKS,
): string[] {
  const answers: Record<string, () => Response> = {
    [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: weeks }),
  };
  for (const [week, body] of Object.entries(reports)) {
    answers[reportPath(SECTION_ID, Number(week))] = () => json(200, body);
  }
  return serving(answers);
}

/** The page, opened at whichever week the address names. */
function open(week: number | null, onSelectWeek = vi.fn()) {
  return render(
    <InstructorMondayReport sectionId={SECTION_ID} week={week} onSelectWeek={onSelectWeek} />,
  );
}

describe('while the report is on its way', () => {
  it('says so in a polite live region, and shows no part of a report', () => {
    serving({});
    open(4);

    const status = screen.getByRole('status');
    expect(status.textContent).toBe(LOADING);
    // The heading is there from the first paint — the landmark is labelled by
    // it — but it names the page rather than a section nothing has answered for.
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Your section report');
    expect(screen.queryByRole('heading', { name: 'Rating trend' })).toBeNull();
  });
});

describe('a published week with data in it', () => {
  it('assembles §5.1 in order, under the section’s own name', async () => {
    servingWeeks({ 4: A_PUBLISHED_WEEK });
    const { container } = open(4);

    // The heading is the governed label the server composed, which is the same
    // string the student's own page carries for this section (FIX-01 item 2).
    expect((await screen.findByRole('heading', { level: 1 })).textContent).toBe(COURSE_LABEL);

    // The eyebrow, with both of SPEC §2.2's axes and the section's own length —
    // and no closing instant, because this week's window has already shut.
    const shown = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(shown).toContain('COURSE WK 04 / 12,');
    expect(shown).toContain('TERM WK 07');
    expect(shown).not.toContain('closes');

    // Every region §5.1 names, as a heading, so the page is navigable by them.
    for (const heading of [
      'Rating trend',
      'This week’s ratings',
      'Workload',
      'Participation',
      'Comments',
    ]) {
      expect(screen.getByRole('heading', { level: 2, name: heading })).toBeTruthy();
    }

    // The stacked pair, read through the accessible tables E4-08 gives it: one
    // per panel, so two.
    expect(screen.getAllByRole('table')).toHaveLength(2);

    // The two distributions, the workload pair and both rates. Each figure is
    // asserted as the string the payload's number formats to, so a member read
    // from the wrong place renders differently.
    //
    // The two histogram means are computed from the distributions the payload
    // carried — 49/13 is 3.769 and 45/13 is 3.462 — so a page that handed a
    // histogram the other stream's counts renders a different number here.
    expect(shown).toContain('mean 3.8');
    expect(shown).toContain('mean 3.5');
    // The workload pair, rounded rather than truncated: 8.04 is "8.0" and 9.46
    // is "9.5".
    expect(shown).toContain('8.0 h');
    expect(shown).toContain('9.5 h');
    expect(shown).toContain('13 / 21 · 62%');
    expect(shown).toContain('12 / 13 · 92%');
    // And the trend's own last point, which is a different number again from
    // either histogram mean, read out of the chart's accessible table.
    expect(shown).toContain('3.6');

    // Both groups, each led by its own summary, each with its comment.
    expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'AI summary — course comments' })).toBeTruthy();
    expect(screen.getByText(INSTRUCTOR_COMMENT)).toBeTruthy();
    expect(screen.getByText(COURSE_COMMENT)).toBeTruthy();
    expect(screen.getByText(COMMENTS_NOTE)).toBeTruthy();

    // One main landmark, named by the one first-level heading in it.
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(container.querySelectorAll('h1')).toHaveLength(1);
  });

  it('names no comparison anywhere, though the payload carries the member', async () => {
    // SPEC §4.1 item 7 and E4's breakdown: the `comparison` member is on the
    // wire from day one so E5's benchmarks have a chokepoint to pass through,
    // and nothing in E4 may render a figure from one. The fixture carries the
    // member — suppressed, with its reason — so this is a fact about a payload
    // that had one rather than about a payload that did not.
    servingWeeks({ 4: A_PUBLISHED_WEEK });
    const { container } = open(4);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });

    expect(A_PUBLISHED_WEEK.comparison.suppressed).toBe(true);
    const markup = container.innerHTML;
    for (const word of ['comparable', 'benchmark', 'university', 'below-minimum', 'suppressed']) {
      expect(markup.toLowerCase()).not.toContain(word);
    }
  });

  it('offers exactly the published weeks the API answered, holes included', async () => {
    // E4-11's third criterion. The fixture's section published weeks 2, 4 and 7
    // and no others, so from week 4 the step back is 2 and the step forward is
    // 7 — a control that counted by one would ask for weeks 3 and 5, which this
    // stub does not serve and the report cannot answer for.
    const chosen = vi.fn();
    servingWeeks({ 4: A_PUBLISHED_WEEK });
    open(4, chosen);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });

    fireEvent.click(screen.getByRole('button', { name: 'Previous week' }));
    expect(chosen).toHaveBeenCalledWith(PUBLISHED_WEEKS[0]);

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }));
    expect(chosen).toHaveBeenCalledWith(PUBLISHED_WEEKS[2]);
  });

  it('opens the latest published week when the address names none', async () => {
    // "Absent week means the latest published week", and the latest is the last
    // entry of the API's own ascending list rather than a maximum this page
    // computed over a range it invented.
    const asked = servingWeeks({ 7: A_SMALL_N_WEEK });
    open(null);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });

    expect(asked).toEqual([publishedWeeksPath(SECTION_ID), reportPath(SECTION_ID, 7)]);
  });

  it('moves focus to the heading when another week arrives, and not on the first one', async () => {
    // SPEC §14.2 item 4. Paging replaces everything under the heading, so a
    // reader whose focus stayed on the navigation button would be told nothing.
    // The first render deliberately does not take focus — that would pull it off
    // whatever the browser had just given it.
    servingWeeks({ 4: A_PUBLISHED_WEEK, 7: A_SMALL_N_WEEK });
    const chosen = vi.fn();
    const { rerender } = open(4, chosen);
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(document.activeElement).not.toBe(heading);

    fireEvent.click(screen.getByRole('button', { name: 'Next week' }));
    expect(chosen).toHaveBeenCalledWith(7);

    // The address changed, which is what the click asked for.
    rerender(
      <InstructorMondayReport sectionId={SECTION_ID} week={7} onSelectWeek={chosen} />,
    );
    await screen.findByRole('region', { name: SMALL_N_TITLE });
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
    });
  });
});

describe('a week nobody answered', () => {
  it('draws every figure’s absent treatment and no zero pretending to be one', async () => {
    servingWeeks({ 2: A_WEEK_NOBODY_ANSWERED });
    const { container } = open(2);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });

    const shown = (container.textContent ?? '').replace(/\s+/g, ' ');
    // The whole report is still here — the shape does not change because a week
    // was quiet — and every figure in it says it has nothing behind it.
    expect(screen.getByRole('heading', { level: 2, name: 'Participation' })).toBeTruthy();
    expect(shown).toContain(NO_RESPONSES);
    expect(shown).toContain('No responses that week');

    // A real zero over a real enrolment: the counts are exact and the percent is
    // withheld, because "0%" reads as a verdict on the week.
    expect(shown).toContain('0 / 21 · —');
    // And no validity row at all, the payload having no rate to be one of.
    expect(shown).not.toContain('Validity rate');

    // Neither stream had a summary, and both say so where the panel would be.
    expect(screen.getAllByText(ABSENT_SUMMARY)).toHaveLength(2);
    expect(screen.queryAllByRole('article')).toHaveLength(0);
  });

  it('renders no response bar at all for a section nobody is enrolled in', async () => {
    // The schema's rule, which only means something if the page draws the two
    // apart: `response_rate` is `null` rather than `0` when there is nothing to
    // be a rate of, and a nought-percent bar there would be a claim about
    // participation in a section with no students in it.
    servingWeeks({ 2: A_WEEK_WITH_NOBODY_ENROLLED });
    const { container } = open(2);
    await screen.findByText(PARTICIPATION_ABSENT);

    const shown = (container.textContent ?? '').replace(/\s+/g, ' ');
    expect(shown).not.toContain('Response rate');
    expect(shown).not.toContain('0 / 0');
  });
});

describe('the credit-rule note', () => {
  it('explains the rule in an ordinary week and in a week with nobody enrolled', async () => {
    // E4-12's criterion 4: ambient explanatory copy in the Participation
    // region, rendered in every week — it explains SPEC §3.3 and §3.4 rather
    // than this week's figures, so an empty week keeps it too. The mutation it
    // kills: the note made conditional on a rate being present, or its render
    // removed while the copy entry stays collected and the inventory green.
    servingWeeks({ 4: A_PUBLISHED_WEEK });
    const ordinary = open(4);
    await screen.findByRole('heading', { level: 2, name: 'Rating trend' });
    const ordinaryText = (ordinary.container.textContent ?? '').replace(/\s+/g, ' ');
    expect(ordinaryText).toContain(CREDIT_NOTE_ARITHMETIC);
    expect(ordinaryText).toContain(CREDIT_NOTE_CAN_LOWER);
    cleanup();

    servingWeeks({ 2: A_WEEK_WITH_NOBODY_ENROLLED });
    const empty = open(2);
    await screen.findByText(PARTICIPATION_ABSENT);
    const emptyText = (empty.container.textContent ?? '').replace(/\s+/g, ' ');
    expect(emptyText).toContain(CREDIT_NOTE_ARITHMETIC);
    expect(emptyText).toContain(CREDIT_NOTE_CAN_LOWER);
  });
});

describe('a week below the response threshold', () => {
  it('keeps both summaries, shows no comment card, and states the reason once', async () => {
    servingWeeks({ 7: A_SMALL_N_WEEK });
    const { container } = open(7);
    await screen.findByRole('heading', { level: 2, name: 'Comments' });

    // §5.1: the summary is generated even in a small-N week, and there it is the
    // only comment signal. Both groups keep theirs.
    expect(screen.getByRole('region', { name: 'AI summary — instructor comments' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'AI summary — course comments' })).toBeTruthy();
    expect(screen.queryAllByRole('article')).toHaveLength(0);

    // §4.1 item 5: confidentiality copy appears exactly once per surface. Both
    // groups are suppressed and exactly one of them carries the notice.
    expect(screen.getAllByRole('region', { name: SMALL_N_TITLE })).toHaveLength(1);
    expect((container.textContent ?? '').match(/raw comments stay hidden/g)).toHaveLength(1);

    // The configured threshold is the payload's number, not a 5 written down
    // anywhere: the fixture uses 4 for exactly that reason.
    expect(container.textContent).toContain(`at least ${String(SMALL_N_THRESHOLD)} responses`);
  });
});

describe('a week whose summary was never written', () => {
  it('states the absence and leaves the rest of the report intact', async () => {
    // E4-11's fifth criterion. E4-06 has not run over this week, or failed on
    // it; the report is otherwise a report.
    const noSummaries = {
      ...A_PUBLISHED_WEEK,
      streams: {
        instructor: { ...A_PUBLISHED_WEEK.streams.instructor, summary: null },
        course: { ...A_PUBLISHED_WEEK.streams.course, summary: null },
      },
    };
    servingWeeks({ 4: noSummaries });
    open(4);
    await screen.findByRole('heading', { level: 2, name: 'Comments' });

    expect(screen.getAllByText(ABSENT_SUMMARY)).toHaveLength(2);
    expect(screen.queryByRole('region', { name: 'AI summary — instructor comments' })).toBeNull();

    // The rest: the charts, the figures, and both comments.
    expect(screen.getAllByRole('table')).toHaveLength(2);
    expect(screen.getByText(INSTRUCTOR_COMMENT)).toBeTruthy();
    expect(screen.getByText(COURSE_COMMENT)).toBeTruthy();
  });
});

describe('comments released from earlier weeks', () => {
  it('shows them in their own block, with their stream and without a week', async () => {
    // SPEC §4 requires under-threshold comments to surface once the section's
    // cumulative volume crosses the threshold, "batched so that timing cannot
    // identify an author", and ADR 0153 strips the week from every one of them.
    servingWeeks({ 4: A_WEEK_WITH_A_RELEASE });
    const { container } = open(4);
    await screen.findByRole('heading', { level: 2, name: RELEASED_HEADING });

    expect(screen.getByText(RELEASED_COMMENT)).toBeTruthy();
    // The chip §7.6 keeps off by default: this is the one list on the surface
    // holding both streams, so a chip names the question rather than repeating
    // a heading. Both directions, because the wire spells streams 'COURSE' and
    // 'INSTRUCTOR' and a mapping that answered one constant for every value
    // would satisfy a single-sided assertion — the mutation this pair kills is
    // the page comparing against a spelling the wire never sends, which is how
    // the chip was dead until the E4 boundary round.
    const released = screen.getByText(RELEASED_COMMENT).closest('article');
    expect(released?.textContent).toContain('Course');
    expect(released?.textContent).not.toContain('Instructor');
    const releasedInstructor = screen.getByText(RELEASED_INSTRUCTOR_COMMENT).closest('article');
    expect(releasedInstructor?.textContent).toContain('Instructor');
    expect(releasedInstructor?.textContent).not.toContain('Course');

    // Nothing in the block names a week or counts anything.
    const block = container.querySelector('.pulse-report-released');
    expect(block?.textContent).not.toMatch(/week \d|WK \d|\bweeks? [0-9]/i);
  });

  it('is absent entirely when the payload released nothing', async () => {
    servingWeeks({ 4: A_PUBLISHED_WEEK });
    open(4);
    await screen.findByRole('heading', { level: 2, name: 'Comments' });

    expect(A_PUBLISHED_WEEK.released_from_earlier_weeks).toEqual([]);
    expect(screen.queryByRole('heading', { name: RELEASED_HEADING })).toBeNull();
  });
});

describe('a comment a moderator is holding', () => {
  // §5.2's flagged-collapsed treatment, on the wire's own spelling. The page
  // maps `flagged_collapsed` onto the card's collapsed variant; the mutation
  // this kills is the mapping comparing against a value the wire never sends
  // ('flagged'), under which the held comment renders as a plain published
  // card — its words in the DOM, no chip, no disclosure. That is exactly the
  // defect the E4 boundary round found, so this is its regression pin.
  it('collapses it: chip and disclosure shown, the words out of the DOM until reviewed', async () => {
    servingWeeks({ 4: A_WEEK_WITH_A_HELD_COMMENT });
    const { container } = open(4);
    // Canary first: a published comment is on the page, so the held one's
    // absence below is about one comment, not about a page with no comments.
    await screen.findByText(INSTRUCTOR_COMMENT);

    expect(screen.getByText('Hidden from students pending your review')).toBeTruthy();
    const disclosure = screen.getByRole('button', { name: 'Review comment' });
    expect(disclosure.getAttribute('aria-expanded')).toBe('false');
    expect(container.textContent).not.toContain(HELD_COMMENT);

    // Opening the disclosure is what proves the absence was a collapse rather
    // than a dropped comment — the near miss a bare absence assertion passes.
    fireEvent.click(disclosure);
    await screen.findByText(HELD_COMMENT);
  });
});

describe('a section before its first Monday', () => {
  it('says so calmly, and still names the section', async () => {
    // The empty list is a state and not a failure, and it is most instructors'
    // first sight of the product. The section list is what names the section
    // here, there being no report to take a name from.
    const asked = serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: [] }),
      [SECTIONS_PATH]: () => json(200, { sections: ONE_TAUGHT_SECTION }),
    });
    open(null);

    await screen.findByText(NO_WEEKS_TITLE);
    expect((await screen.findByRole('heading', { level: 1 })).textContent).toBe(COURSE_LABEL);
    expect(asked).toEqual([publishedWeeksPath(SECTION_ID), SECTIONS_PATH]);
    expect(screen.queryByRole('heading', { name: 'Rating trend' })).toBeNull();
  });
});

describe('a read the server refused', () => {
  it('shows the server’s own sentence for a week that is not published', async () => {
    // Criterion 6's second half. The API decides publishability; this page asks
    // for the week the address named and renders whichever refusal came back.
    serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [reportPath(SECTION_ID, 3)]: () => json(404, { detail: COURSE_WEEK_UNAVAILABLE }),
    });
    const { container } = open(3);

    await screen.findByText(COURSE_WEEK_UNAVAILABLE);
    // **No partial data beside the apology** — criterion 2's second clause. The
    // published weeks came back before the refusal did, so a page that kept a
    // week navigation, an eyebrow or a heading from them would be showing part
    // of a report it could not read.
    expect(screen.queryByRole('navigation', { name: 'Week navigation' })).toBeNull();
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
    expect(screen.queryAllByRole('table')).toEqual([]);
    expect(container.textContent).not.toContain('COURSE WK');
    expect(container.textContent).not.toContain(COURSE_LABEL);
  });

  it('shows the refusal pair’s sentence for a section that is not this reader’s', async () => {
    serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(404, { detail: SECTION_UNAVAILABLE }),
    });
    open(4);

    await screen.findByText(SECTION_UNAVAILABLE);
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });

  it('falls back to its own words when nothing carried a sentence', async () => {
    // A network failure, or a gateway in front of the tool answering with no
    // body at all. There is no server sentence to show and the page still has to
    // say something true.
    serving({});
    open(4);

    await screen.findByText(UNAVAILABLE);
  });

  it('never says a section has nothing to report when the session ended', async () => {
    // A 401 is not an empty section. The session a launch issues lives an hour;
    // the ordinary way here is an instructor coming back to a tab from earlier
    // in the day, and telling her the week is empty would be this page answering
    // a question it had just been refused.
    serving({
      [publishedWeeksPath(SECTION_ID)]: () => json(401, { detail: 'Not an instructor.' }),
    });
    open(4);

    await screen.findByText(SESSION_ENDED_TITLE);
    expect(screen.queryByText(NO_WEEKS_TITLE)).toBeNull();
    expect(screen.queryByText(UNAVAILABLE)).toBeNull();
  });
});
