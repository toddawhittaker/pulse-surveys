// E5-11 criterion 4 — the student surfaces, swept for a benchmark trace, with
// the instructor's own page as the canary. SPEC §4.1 item 1, §5.4, §9.2.
//
// **What this file proves.** Item 1's full sentence: "Students never see
// comparables, benchmarks, university averages, or other sections — in charts,
// text, tooltips, exports, or aria labels", and §5.4's restatement, "Students
// **never** see comparison-set or university lines". The backend half of this
// ticket asserts it over every student route's payload; this is the half a
// payload cannot answer, because a word can reach a screen from the client as
// easily as from the server — a legend the chart draws for itself, an aria
// label, a tooltip, a class name.
//
// **Non-vacuity is the whole design, and it is asserted twice over.** A sweep
// that found nothing because it could no longer see anything would report every
// student screen as clean, and the report would be indistinguishable from a pass
// (`docs/MISTAKES.md` entry 3). So before each student surface is judged:
//
//   - **the canary**: the same sweep is run over `BIOL-310-R7FF`'s instructor
//     report — the section whose comparison set E5-10's world populates — and is
//     required to *hit* every word that page is expected to render;
//   - **the section-level control**: the same sweep is run over the instructor
//     report for `BIOL-215-R3WW`, which is a section the seeded learner is
//     enrolled in. So the same section, in the same world, at the same minute,
//     shows its instructor the comparison vocabulary (as suppression notices —
//     its default set is empty, because `BIOL 215` has no lead in
//     `scripts/seed.py`) and shows its student none of it. That
//     is the ticket's "the same world that shows an instructor three lines shows
//     the student two" at the grain of one section;
//   - **the value**: one comparison figure is read off the hero report's own
//     payload, shown to appear in the instructor's DOM in the spelling the page
//     writes it in, and then required to appear in no student DOM. A member name
//     can be renamed; a statistic travelling under an innocent label is what a
//     vocabulary sweep alone would walk past.
//
// **Whose student screens these are, and why not the hero's.** `mock-lms/app/
// seed.py`'s `LAUNCH_PAGE_CAST` offers three people: the shared instructor, the
// shared learner and the dean. The shared learner is deliberately **not**
// enrolled in `BIOL-310-R7FF` — the seed's own comment says why — and the
// roster-amendment route mints ordinal students who cannot launch from that
// page, so no browser in this repository can stand in front of the hero
// section's student view. The student surfaces swept here are therefore the
// shared learner's own sections in this same benchmark-bearing world:
// `BIOL-215-R3WW`, whose instructor report carries the benchmark members, and
// `MATH-140-E1FF`. That is a narrower proof than "the hero's own students see
// nothing" and it is the strongest one a browser can make here; the route-level
// sweep in
// `tests/integration/test_every_student_route_carries_nothing_of_a_benchmark.py`
// drives a student enrolled in the hero section itself.
//
// **What is not swept, and where that is recorded.** SPEC §5.4's closing-the-loop
// view pages back through published weeks, and nothing asserts that a student
// paging from one week to the next sees no comparison figure — there is no page
// to drive until E8 builds it. `docs/tickets/e5/deferred.md` records that gap
// under "The student benchmark sweep runs over one week, because that is all
// there is (E5-11)", with E8 as its owner.
//
// **The clock moves twice per test, which is shared state.**
// `playwright.config.ts` pins `workers` to 1 and this file is serial. The
// instructor's reports are read at the minute E5-10 reads them at, and the
// learner's windows are open at a different minute entirely, so each test moves
// the clock from the first to the second between the canary and the drive. The
// override is cleared in `afterAll` inside a `finally`, so a failing assertion
// cannot leave the stack in October 2026 for whatever runs next.
//
// **Every expectation is a literal.** The section codes, the course weeks and
// the governed sentences are transcribed from the seeded calendar and from the
// copy modules that hold them — none is computed by the code under test
// (`docs/MISTAKES.md` entry 19).
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from "@playwright/test";

import { seedTheBenchmarkHistory } from "./support/benchmarkWorld";
import { clearTheClock, setTheClockTo } from "./support/clock";
import { launchAs, placementInto } from "./support/doors";
import { deriveSurveyWindows, seedTheDemoStory } from "./support/stack";
import {
  INSTRUCTOR_SUBJECT,
  LEARNER_SUBJECT,
  REVISE,
  STUDENT_VIEW,
  SUBMIT,
  type SectionUnderTest,
  chooseRating,
  clearTheWeek,
  expectTheFormIsShowing,
  landOnTheSurvey,
  sectionBlock,
  sectionStartClock,
  setSlider,
} from "./support/survey";

// ---------------------------------------------------------------------------
// The sections, and why each is the one it is.
// ---------------------------------------------------------------------------

// **The hero: the only section whose comparison set is populated.** E5-10's
// spec records why in full — the three prior-term `BIOL-310` sections
// `mock-lms/app/seed.py` publishes are twelve-week undergraduate sections, which
// is this section's own length and level, and it is also the section E4-20's
// demo story writes. It is the canary's page.
const HERO = {
  label: "BIOL-310-R7FF",
  code: "R7FF",
  menuName: "BIOL 310 R7FF",
  lengthWeeks: 12,
};

// **The section that is both an instructor report and a student screen.**
// `BIOL-215-R3WW`'s default comparison set is empty — its course, `BIOL 215`,
// has no lead in `scripts/seed.py`, and SPEC §5.1 draws the set from "the same
// Lead Faculty's courses" — so its instructor report carries the comparison
// members as suppression notices rather than lines — and the seeded
// learner is enrolled in it. It is the second control and one of the two
// surfaces swept.
const ALONE = {
  label: "BIOL-215-R3WW",
  code: "R3WW",
  menuName: "BIOL 215 R3WW",
  lengthWeeks: 12,
};

// The learner's other seeded section, which shares the screen with `R3WW` at the
// minute below. Both blocks on one screen is what makes the sweep a sweep of a
// student's whole surface rather than of one section's block.
const MATHEMATICS: SectionUnderTest = { label: "MATH-140-E1FF", code: "E1FF" };

// The two sections the learner's screen shows at the minute below. Both are put
// back to unanswered before and after every case; `BIOL-215-R3WW` is the one
// this file answers.
const THE_LEARNERS_SECTIONS = [ALONE.code, MATHEMATICS.code];

// The minute the instructor's reports are read at, transcribed from
// `instructor-report-benchmarks.spec.ts`, which transcribes it from the seeded
// calendar: start letter `R` runs twelve weeks from Monday 7 September 2026, and
// at 09:00 on Monday 19 October six of those weeks have closed. E4-20's demo
// story writes a response for every week whose window has closed at the
// effective clock and refuses when none has.
const READ_CLOCK = "2026-10-19T09:00";

// The minute the learner's two windows are both open, transcribed from
// `student-survey-confidentiality.spec.ts`: the seeded term begins Monday 17
// August 2026, so term week 4 begins Monday 7 September, and SPEC §3.1 opens
// each week's survey on the Friday at 18:00 in the institution's timezone.
// `MATH-140-E1FF` is in its fourth course week and `BIOL-215-R3WW` in its first.
const BOTH_WINDOWS_OPEN = "2026-09-11T19:00";

// The hours the learner reports when this file answers a week. **Distinct from
// any comparison figure the hero's report carries**, which is asserted rather
// than assumed below: the value sweep searches the student's screen for a
// figure's own digits, and a needle equal to a number the student herself put on
// the screen would be found on a clean page.
const STUDENT_HOURS = "2.5";

// ---------------------------------------------------------------------------
// The vocabulary, defined once, with where each word comes from.
// ---------------------------------------------------------------------------

// The trend legend, as `frontend/src/copy/instructorReportTrendCopy.ts` writes it
// and `instructor-report-benchmarks.spec.ts` transcribes it. Written out here
// rather than imported: a spec that asked the page what its own words were would
// pass against any words at all (`tests/e2e/landing-views.spec.ts` states the
// rule).
const COMPARISON_LEGEND = `Comparable ${String(HERO.lengthWeeks)}-week courses`;
const UNIVERSITY_LEGEND = "University";

/**
 * Every word, phrase, testid and class stem a benchmark reaches a screen as.
 *
 * **One list, and it is a class rather than an enumeration.** The four generic
 * stems at the end are the ones
 * `tests/integration/test_every_student_route_carries_nothing_of_a_benchmark.py`
 * sweeps payload keys with, for the reason that module gives
 * (`docs/MISTAKES.md` entry 53): a member spelled some new way has to defeat a
 * rule about the class of names rather than be missed by a list. They subsume
 * most of the phrases above them; the phrases are kept anyway, because a failure
 * naming `Mean hours, university` tells a reader what is on the screen and a
 * failure naming `university` tells them to go and look.
 *
 * **If one of these fires on a word a student screen legitimately says**, the
 * repair is to narrow that stem here and write down why, in the same change —
 * never to drop it. This file's author cannot read `frontend/src/copy/` (the
 * test-author read boundary), so the near-miss triage is deliberately left as a
 * loud failure with the rule attached rather than as a quietly narrowed list.
 */
const SWEPT_TERMS: readonly string[] = [
  // The trend legend and its two suppression sentences —
  // `frontend/src/copy/instructorReportTrendCopy.ts`.
  COMPARISON_LEGEND,
  "no line on this chart",
  "The set behind it is too small to report on",
  // The workload columns and their withheld treatment —
  // `frontend/src/copy/instructorReportStatCopy.ts` and
  // `frontend/src/components/StatPair.tsx`.
  "comparable courses",
  "Mean hours, university",
  "Median hours, university",
  "Not shown",
  "The set behind this figure is too small to report on",
  // The testids the report surface publishes (E4-11, E5-07, E5-08), as
  // `instructor-report-benchmarks.spec.ts` names them.
  "trend-line-comparison",
  "trend-line-university",
  "trend-suppression-comparison",
  "trend-suppression-university",
  "stat-cell-comparison",
  "stat-cell-university",
  // The class stem E5-07's overlays carry.
  "--benchmark",
  // The generic stems, from the backend sweep.
  "benchmark",
  "compar",
  "cohort",
  "university",
];

/**
 * What the hero's report must render, or this sweep has gone blind.
 *
 * **Not every term in the list above, and the difference is deliberate.** A
 * section whose comparison set is populated draws its lines and shows its
 * figures, so it renders no suppression notice at all — E5-10's first criterion
 * asserts exactly that, `trend-suppression-comparison` absent and the cells
 * carrying hours. Requiring the withheld vocabulary here would be requiring the
 * page to contradict its own ticket. The suppressed half is the second control's
 * to prove.
 */
const CANARY_ON_THE_HERO: readonly string[] = [
  COMPARISON_LEGEND,
  UNIVERSITY_LEGEND,
  "comparable courses",
  "Mean hours, university",
  "trend-line-comparison",
  "trend-line-university",
  "stat-cell-comparison",
  "stat-cell-university",
];

/**
 * What the suppressed report must render — the other half of the vocabulary.
 *
 * `BIOL-215-R3WW`'s default set is empty, so SPEC §4.1 item 7's treatments are
 * what its comparison members become. Between this list and the hero's, every
 * phrase in `SWEPT_TERMS` is shown to be findable except three: `Median hours,
 * university` (the cells are asserted as a pair, and the mean is enough to prove
 * the sweep reaches them), `trend-suppression-university` (whether the
 * university series is suppressed for this section depends on how many sections
 * of its length and level the stack holds, which E5-10 records as not fixed by
 * this world) and `--benchmark` (a class the overlays carry, not a word any page
 * is required to write). Their absence from a student screen is still asserted;
 * what is not claimed is that this file has watched the sweep find them.
 */
const CANARY_ON_THE_SUPPRESSED: readonly string[] = [
  COMPARISON_LEGEND,
  "no line on this chart",
  "The set behind it is too small to report on",
  "Not shown",
  "The set behind this figure is too small to report on",
  "trend-suppression-comparison",
];

// The testids the report surface and the two landings publish.
const INSTRUCTOR_LANDING = "pulse-landing-instructor";
const REPORT = "pulse-instructor-report";
const SECTIONS_MENU = "pulse-instructor-sections";

// The governed heading the submitted state carries, transcribed from
// `frontend/src/copy/studentSurvey.ts` the way `exit-weekly-survey.spec.ts`
// transcribes it, and for that file's reason.
const SUBMITTED_TITLE = "Your pulse is in";

// Budgets. The world is five prior-term launches, two current-term launches, two
// seeders and a window derivation; each case then makes two instructor launches,
// a student launch and (twice) a submission. A case that ran out of harness
// rather than out of patience would read as a flake.
const WORLD_TIMEOUT_MS = 600_000;
const CASE_TIMEOUT_MS = 240_000;

// How much of the document is quoted around a value that should not be there.
const CONTEXT_CHARACTERS = 120;

/** The placement each section launches through, discovered in `beforeAll`. */
const placements: Record<string, string> = {};

/** The placement the learner lands through — one launch shows every section. */
let learnerPlacement = "";

// ---------------------------------------------------------------------------
// The payload, in the shape this file reads it — the members
// `app/schemas/report_benchmark.py` serves, as
// `instructor-report-benchmarks.spec.ts` types them.
// ---------------------------------------------------------------------------

interface ComparisonFigure {
  readonly suppressed: boolean;
  readonly reason: string | null;
  readonly figure: number | null;
}

interface ReportPayload {
  readonly week: { readonly course_week: number };
  readonly workload_benchmark?: {
    readonly comparison: {
      readonly mean: ComparisonFigure;
      readonly median: ComparisonFigure;
    };
    readonly university: {
      readonly mean: ComparisonFigure;
      readonly median: ComparisonFigure;
    };
  };
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(WORLD_TIMEOUT_MS);
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    // E5-10's construction, copied rather than re-invented: the prior term
    // first, because it is the half that has to exist before any comparison
    // figure can, then the two current-term sections at their own start days,
    // then the hero's own weeks with the clock forward.
    await seedTheBenchmarkHistory(page);

    for (const section of [HERO, ALONE]) {
      placements[section.label] = await placementInto(
        page,
        INSTRUCTOR_SUBJECT,
        section.label,
      );
      // **The anchor rule, in this direction** (E4-22,
      // `tests/e2e/00-enrollment-anchor.spec.ts`): the roster sync stamps
      // `enrollment.started_on` from the effective clock and never rewrites it,
      // so a launch at the wall clock dates the roster the day CI happens to
      // run. Both sections began on 7 September 2026, which is in the past of
      // any clock this suite runs under.
      await setTheClockTo(page, sectionStartClock(section.code));
      await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? "");
      await expect(
        page.getByTestId(INSTRUCTOR_LANDING),
        `The staff launch into ${section.label} did not land, so it provisioned nothing and ` +
          "stored no roster address — and the seeder below would refuse.",
      ).toBeVisible();
      deriveSurveyWindows();
    }

    await setTheClockTo(page, READ_CLOCK);
    const wrote = seedTheDemoStory();
    expect(
      wrote,
      `E4-20's demo story wrote nothing into ${HERO.label}. Its output is above. Without a week ` +
        "of its own this section draws no line of its own, and the canary below would be run " +
        "against a report with nothing on it — which is the one failure that makes every " +
        "assertion in this file vacuous.",
    ).toContain(HERO.label);

    // The learner's own door, discovered once. No launch by anybody but the
    // instructor above: the enrollments this file reads on the student side are
    // the seeded world's, so there is no second roster sync to wait for
    // (`student-survey-confidentiality.spec.ts` records the same).
    learnerPlacement = await placementInto(page, LEARNER_SUBJECT, ALONE.label);
  } finally {
    await context.close();
  }
});

test.beforeEach(() => {
  // Both of the learner's weeks start unanswered. Two of the three cases answer
  // one of them, and a week left answered would put the next case's first sweep
  // over the submitted state while it was asserting about the form.
  clearTheWeek(THE_LEARNERS_SECTIONS);
});

test.afterAll(async ({ browser }) => {
  // The weeks first, then the clock. Both are shared state and this file is not
  // the last thing the suite runs: `student-survey.spec.ts` sorts after it and
  // starts by asserting the form is showing, which an answered week would deny.
  clearTheWeek(THE_LEARNERS_SECTIONS);

  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test("the landing a student lands on carries no benchmark trace, on a screen the instructor reads three lines from", async ({
  page,
}) => {
  // **Criterion 4, surface 1: `STUDENT_VIEW` with every section block on it.**
  // SPEC §4.1 item 1 covers "charts, text, tooltips, exports, or aria labels",
  // so the whole rendered document is swept — every element, every attribute —
  // rather than the words a reader happens to see.
  test.setTimeout(CASE_TIMEOUT_MS);

  const instructor = await theInstructorsBenchmarkPages(page);
  const student = await theStudentsLanding(page);

  expectNoBenchmarkTrace(
    student,
    "the student landing with both section blocks open",
    instructor,
  );
});

test("the submitted state carries no benchmark trace", async ({ page }) => {
  // **Surface 2.** The state a student meets *after* answering is where a
  // "now that you have answered, here is how your section compares" member would
  // arrive, and it is a different screen from the form: no submit bar, a
  // different heading, whatever the server chose to send back.
  // `docs/MISTAKES.md` entry 51 is the same reading one level up — a property
  // proven over one view is a property about one view.
  test.setTimeout(CASE_TIMEOUT_MS);

  const instructor = await theInstructorsBenchmarkPages(page);
  await theStudentsLanding(page);
  // `answerTheWeek` asserts the submitted heading before it answers, which is
  // this case's premise: a sweep taken over the form a second time would be case
  // 1 run twice.
  await answerTheWeek(page);

  expectNoBenchmarkTrace(
    await theWholeDocument(page),
    "the submitted state",
    instructor,
  );
});

test("the revise state carries no benchmark trace", async ({ page }) => {
  // **Surface 3.** Revising is a distinct screen and not a repaint of the
  // submitted one: SPEC §3.3 allows resubmission inside the window, ADR 0115
  // revises in place, and what comes back is the form prefilled from the server
  // with the answers already stored. The page is reloaded before `REVISE` is
  // taken, the way `exit-weekly-survey.spec.ts` takes it, so what is swept is
  // the state the server prefilled rather than one the browser still had in
  // hand.
  test.setTimeout(CASE_TIMEOUT_MS);

  const instructor = await theInstructorsBenchmarkPages(page);
  await theStudentsLanding(page);
  await answerTheWeek(page);

  await page.reload();
  const block = page.getByTestId(sectionBlock(ALONE.code));
  await expect(block.getByText(SUBMITTED_TITLE, { exact: true })).toBeVisible();
  await block.getByTestId(REVISE).click();
  await expect(
    block.getByTestId(SUBMIT),
    "The revise action did not bring the form back, so the sweep below would be over the " +
      "submitted state a second time rather than over the state a revising student reads.",
  ).toBeVisible();

  expectNoBenchmarkTrace(
    await theWholeDocument(page),
    "the revise state",
    instructor,
  );
});

// ---------------------------------------------------------------------------
// The canaries, and what they hand to the sweep.
// ---------------------------------------------------------------------------

/** What one run of the canary establishes, and the needle it found. */
interface InstructorPages {
  readonly needle: number;
  readonly spellings: readonly string[];
}

/**
 * Read both instructor reports, require the sweep to hit on each, and answer the
 * comparison figure it will look for on the student's screen.
 *
 * **Run at the top of every test, not once at authoring time** — the ticket's
 * known traps name it, quoting `docs/MISTAKES.md` entry 3's canary rule: a sweep
 * that has stopped seeing reports every screen it is pointed at as clean, and
 * that report is indistinguishable from a pass.
 *
 * Two pages, because the vocabulary has two halves: the hero's report draws its
 * comparison lines and prints its figures, and `BIOL-215-R3WW`'s prints the
 * withheld treatments instead. The second is also the section-level control —
 * the learner swept below is enrolled in it, so the same section in the same
 * world at the same minute is shown to carry this vocabulary for its instructor.
 *
 * Leaves the clock at `READ_CLOCK`; the caller moves it to the learner's minute.
 */
async function theInstructorsBenchmarkPages(
  page: Page,
): Promise<InstructorPages> {
  await setTheClockTo(page, READ_CLOCK);

  // The report region is asserted visible inside `openTheReport`, so the dump
  // below is taken off a page that has rendered one.
  await openTheReport(page, HERO);
  const payload = await theReportPayload(page);
  const hero = await theWholeDocument(page);

  const missing = CANARY_ON_THE_HERO.filter((term) => !found(hero, term));
  expect(
    missing,
    `The sweep did not find ${JSON.stringify(missing)} in ${HERO.label}'s own instructor report, ` +
      "which is the page that renders them. **A red here is this file or the world, never the " +
      "student read path**: either the world was not built (an empty comparison set draws no " +
      "lines and prints no figures), or the copy modules have respelled these words and the " +
      "constants at the top of this file are stale. Until the sweep is shown finding something, " +
      "a clean student screen means only that the sweep found nothing anywhere.",
  ).toEqual([]);
  expect(
    termsIn(hero).length,
    "Not one of this file's swept terms appears in the instructor's own report. A blind sweep " +
      "reports every student surface as clean, and every assertion in this file would pass over " +
      "a world with nothing in it.",
  ).toBeGreaterThan(0);

  // The value, taken off the payload rather than computed here
  // (`docs/MISTAKES.md` entry 19), and required to be a number nothing else on a
  // student screen could be before it is searched for.
  const mean = payload.workload_benchmark?.comparison.mean;
  expect(
    mean !== undefined &&
      mean.suppressed === false &&
      typeof mean.figure === "number",
    `The hero report's workload comparison mean is ${JSON.stringify(mean)}, so this world serves ` +
      "no comparison figure for the value sweep to look for. That is the prior term being empty " +
      "or below a minimum, not a student leaking anything.",
  ).toBe(true);
  const needle = mean?.figure ?? 0;
  expect(
    Number.isInteger(needle),
    `The comparison workload mean is ${String(needle)}, a whole number. Every week number, ` +
      "length, count, rating and threshold a student screen carries is a whole number too, so a " +
      "whole number is a needle that would be found on a clean screen. The world has to make this " +
      "statistic a value nothing else can equal.",
  ).toBe(false);
  expect(
    needle,
    `The comparison workload mean is ${String(needle)}, which is also the ${STUDENT_HOURS} hours ` +
      "this file submits as the learner. A student may put her own hours on her own screen, so " +
      "this needle could not tell a comparison figure from an answer.",
  ).not.toBe(Number(STUDENT_HOURS));

  const spellings = spellingsOf(needle).filter((spelling) =>
    hero.includes(spelling),
  );
  expect(
    spellings,
    `None of the spellings ${JSON.stringify(spellingsOf(needle))} of the comparison workload ` +
      `mean (${String(needle)}) appears anywhere in ${HERO.label}'s instructor report, which is ` +
      "the page that was serving it. The value search is therefore blind, and a clean student " +
      "screen below would mean nothing (`docs/MISTAKES.md` entry 3). If the page writes hours in " +
      "some other spelling, teach it to `spellingsOf` in this file.",
  ).not.toEqual([]);

  // The second control: the suppressed half of the vocabulary, on a section the
  // learner is enrolled in.
  await openTheReport(page, ALONE);
  const alone = await theWholeDocument(page);
  const withheld = CANARY_ON_THE_SUPPRESSED.filter(
    (term) => !found(alone, term),
  );
  expect(
    withheld,
    `The sweep did not find ${JSON.stringify(withheld)} in ${ALONE.label}'s instructor report. ` +
      "That section's default set is empty (its course has no lead), so SPEC §4.1 item 7 has " +
      "its comparison members rendered as the withheld treatments — and it is the section the " +
      "learner swept below is " +
      'enrolled in, which is what makes "this instructor sees it, this student does not" a ' +
      "statement about one section rather than about two different ones. **A red here is this " +
      "file or the world**: either the default set is no longer empty, or the copy has been respelled.",
  ).toEqual([]);

  return { needle, spellings };
}

/**
 * Land the learner on her own screen at the minute both her windows are open,
 * and answer the whole document.
 *
 * The clock moves here and nowhere else in a test body: the instructor's reports
 * are read six weeks later in the term, and a learner read at that minute would
 * be reading a week she has already answered or one that has closed.
 */
async function theStudentsLanding(page: Page): Promise<string> {
  await setTheClockTo(page, BOTH_WINDOWS_OPEN);
  await landOnTheSurvey(page, learnerPlacement, ALONE.code);

  // **The premise, asserted in every test rather than in one of them.** An
  // absence swept off a screen that showed nothing is explained just as well by
  // a screen that showed nothing, and each test gets its own browser context, so
  // the previous test's reading says nothing about this one's page.
  await expect(
    page.getByTestId(STUDENT_VIEW),
    "The learner did not land on the student view, so what is swept below is not a student " +
      "surface at all.",
  ).toBeVisible();
  for (const code of THE_LEARNERS_SECTIONS) {
    await expect(
      page.getByTestId(sectionBlock(code)),
      `The learner has no block for ${code} at ${BOTH_WINDOWS_OPEN}. The seeded world enrols her ` +
        "in both of this file's sections; a block missing here is an enrollment the seed no " +
        "longer holds, or one that is not live on the pretended day — and a screen with fewer " +
        "sections on it is a screen with less to leak.",
    ).toBeVisible();
  }

  return theWholeDocument(page);
}

/** Answer `BIOL-215-R3WW`'s open week, leaving the submitted state on screen. */
async function answerTheWeek(page: Page): Promise<void> {
  const block = page.getByTestId(sectionBlock(ALONE.code));
  await expectTheFormIsShowing(block);
  // Both ratings above SPEC §3.2's "required if Q ≤ 2" threshold, so no comment
  // is owed and none is written: a week with no words in it leaves no
  // classification row, and `clearTheWeek` then has nothing to race.
  await chooseRating(block, 0, "4");
  await chooseRating(block, 1, "5");
  await setSlider(block, STUDENT_HOURS);
  await block.getByTestId(SUBMIT).click();
  await expect(
    block.getByText(SUBMITTED_TITLE, { exact: true }),
    "The submission was not accepted, so the state this test sweeps was never reached.",
  ).toBeVisible();
}

// ---------------------------------------------------------------------------
// The sweep.
// ---------------------------------------------------------------------------

/**
 * Assert that one student surface carries no word, no testid, no class and no
 * figure of a benchmark.
 *
 * One assertion per term, so the failure output names the surface and the word
 * without anybody opening this file.
 */
function expectNoBenchmarkTrace(
  dump: string,
  surface: string,
  instructor: InstructorPages,
): void {
  for (const term of SWEPT_TERMS) {
    expect(
      found(dump, term),
      `${surface} carries ${JSON.stringify(term)}: ${quotedAround(dump, term)}\n\n` +
        'SPEC §4.1 item 1: "Students never see comparables, benchmarks, university averages, or ' +
        'other sections — in charts, text, tooltips, exports, or aria labels." §5.4 says it again ' +
        "for this surface: a student sees their own section, and never comparison-set or " +
        "university lines. The whole rendered document is searched — text, `aria-*`, `title`, " +
        "`data-testid` and class names alike — case-insensitively, because all of those are " +
        "surfaces item 1 names.\n\n" +
        "If this word is on the student screen for a reason that has nothing to do with a " +
        "benchmark, the repair is to narrow this stem in `SWEPT_TERMS` and write down why, in " +
        "the same change. Dropping it is the sweep that reports every screen clean.",
    ).toBe(false);
  }

  for (const spelling of instructor.spellings) {
    expect(
      dump.includes(spelling),
      `${surface} carries ${JSON.stringify(spelling)}, which is the comparison set's workload ` +
        `mean (${String(instructor.needle)}) as ${HERO.label}'s instructor report spells it: ` +
        `${quotedAround(dump, spelling)}\n\n` +
        "The figure was read off the instructor's own payload in this same world and shown to " +
        "appear on the instructor's own page before it was looked for here. A statistic can " +
        "travel without its member name — under a generic label, inside a sentence, in an aria " +
        "description — and the vocabulary sweep above would walk past it.",
    ).toBe(false);
  }
}

/** Whether one term appears anywhere in a document, case-insensitively. */
function found(dump: string, term: string): boolean {
  return dump.toLowerCase().includes(term.toLowerCase());
}

/** Which of the swept terms this document carries. */
function termsIn(dump: string): string[] {
  return SWEPT_TERMS.filter((term) => found(dump, term));
}

/**
 * The whole rendered document, with `<script>` and `<style>` elements removed.
 *
 * **Everything item 1 names, in one string**: element text, `aria-*`, `title`,
 * `data-testid` and class names are all attributes or nodes of this markup, so
 * one search covers the lot and a surface nobody thought of is covered too.
 *
 * **The two removals are load-bearing and neither is a loophole.** A stylesheet
 * shipped with the application declares the report's own rules — a
 * `--benchmark` modifier among them — on every page that loads it, and a
 * bundle's source text carries every identifier the client was built from. Both
 * are the same bytes on a student's screen and on an instructor's, so neither
 * can distinguish a student surface that leaks from one that does not; leaving
 * them in would make this sweep red against a correct page, which is the sweep
 * that gets deleted rather than fixed. What a *rendered* benchmark puts in this
 * dump — the drawn element, its class attribute, its label, its notice — is
 * untouched by either removal.
 */
async function theWholeDocument(page: Page): Promise<string> {
  return page.evaluate(() => {
    const copy = document.documentElement.cloneNode(true) as HTMLElement;
    Array.from(copy.querySelectorAll("script, style")).forEach((noise) => {
      noise.remove();
    });
    return copy.outerHTML;
  });
}

/**
 * The ways one statistic plausibly reaches a screen as text.
 *
 * A number is written without trailing zeros, a fixed-scale figure keeps one,
 * and the report writes its hours to a decimal place (`\d+\.\d h`). Every
 * spelling is carried, and the ones that actually appear on the instructor's own
 * page are the ones the student's is searched for — the same rule the backend
 * module's `spellings_of` states, and for the same reason.
 */
function spellingsOf(figure: number): string[] {
  return Array.from(
    new Set([String(figure), figure.toFixed(1), figure.toFixed(2)]),
  );
}

/** The document around the first occurrence of something that should not be in it. */
function quotedAround(dump: string, term: string): string {
  const at = dump.toLowerCase().indexOf(term.toLowerCase());
  if (at < 0) return "(nowhere)";
  const from = Math.max(0, at - CONTEXT_CHARACTERS);
  return JSON.stringify(
    dump.slice(from, at + term.length + CONTEXT_CHARACTERS),
  );
}

// ---------------------------------------------------------------------------
// Reaching an instructor report. Both helpers are copied from
// `instructor-report-benchmarks.spec.ts`, which exports neither — a spec module
// is a drive rather than machinery, and lifting them into `support/` would put a
// diff on the file this one uses as its control.
// ---------------------------------------------------------------------------

/** Launch the instructor, open one section's report from the menu, answer the region. */
async function openTheReport(
  page: Page,
  section: typeof HERO,
): Promise<Locator> {
  await launchAs(page, INSTRUCTOR_SUBJECT, placements[section.label] ?? "");
  await expect(page.getByTestId(INSTRUCTOR_LANDING)).toBeVisible();
  const menu = page.getByTestId(SECTIONS_MENU);
  await expect(
    menu,
    "The instructor did not land on the section menu, so there is no link to open a report from.",
  ).toBeVisible();
  // **Named by prefix, number and §2.2 code**: this persona teaches four
  // `BIOL 310` sections and three `BIOL 215` ones once the prior term exists, and
  // a locator naming only the course resolves to several links.
  await menu.getByRole("link", { name: new RegExp(section.menuName) }).click();
  const report = page.getByTestId(REPORT);
  await expect(report).toBeVisible();
  return report;
}

/** The report the page is showing, read from the route with the page's own session. */
async function theReportPayload(page: Page): Promise<ReportPayload> {
  const token = await page.evaluate(() =>
    window.sessionStorage.getItem("pulse.session"),
  );
  expect(
    token,
    "The instructor launch handed over no session, so nothing here is a read of the report.",
  ).not.toBeNull();
  const headers = {
    Authorization: `Bearer ${token ?? ""}`,
    Accept: "application/json",
  };

  const matched = /\/instructor\/sections\/([0-9a-f-]+)/.exec(page.url());
  expect(
    matched,
    `The report's address does not carry a section key: ${page.url()}`,
  ).not.toBeNull();
  const sectionId = matched?.[1] ?? "";

  const weeks = await page.request.get(
    `/instructor/sections/${sectionId}/published-weeks`,
    {
      headers,
    },
  );
  expect(weeks.status()).toBe(200);
  const published = ((await weeks.json()) as { published_weeks: number[] })
    .published_weeks;
  expect(
    published.length,
    "The published-weeks route answered an empty list, so this section has no report to read and " +
      "the page cannot have rendered one.",
  ).toBeGreaterThan(0);
  const latest = published[published.length - 1] ?? 0;

  const answer = await page.request.get(
    `/instructor/sections/${sectionId}/report/${String(latest)}`,
    { headers },
  );
  expect(answer.status()).toBe(200);
  const payload = (await answer.json()) as ReportPayload;
  expect(
    payload.week.course_week,
    "The report route answered for a week other than the one that was asked for.",
  ).toBe(latest);
  return payload;
}
