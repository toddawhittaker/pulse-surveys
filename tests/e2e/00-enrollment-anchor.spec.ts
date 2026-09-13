// The shared learner enrollments the student-survey specs read, created once and
// up front at each section's own start day — ticket E4-22. SPEC §3.4, §7.3.
//
// **The bug this removes is a calendar time-bomb, not a regression.** Enrollments
// are provisioned only by a staff launch and the roster sync it triggers
// (`scripts/seed.py` creates none), and the sync stamps `enrollment.started_on`
// from the effective clock the moment it first sees a member — "a first-seen fact
// and is never rewritten" (`backend/app/services/roster_sync.py`). The student
// read path then shows a section only while `started_on <= today`
// (`backend/app/services/survey_read.py`). So a sync-triggering launch left at
// the wall clock dates every enrollment the day CI happens to run, and a spec
// that reads at a fixed past minute — `student-survey-confidentiality.spec.ts`
// and `student-survey-heading-and-next-window.spec.ts` both read at
// `2026-09-11T19:00` — is refused at the no-access door the moment the real date
// passes it. The fix is to date `started_on` at the section's start instead,
// which is what SPEC §3.4 says is right anyway: a platform that supplies no
// enrollment dates — the mock supplies none — enrolls a student from the
// section's start.
//
// **Why this is a file of its own that runs first, rather than a change to the
// specs' own `beforeAll` blocks.** `started_on` is stamped once, by whichever
// staff launch reaches a section first in the run, and the two sections the
// student-survey specs read are first reached by launches that are the *subject*
// of another test and must not have their clocks moved: `BIOL-215-R3WW` by the
// placement-less instructor launch in `exit-roster-auth.spec.ts` (measured: it
// creates the whole R3WW roster dated at the wall clock), and `MATH-140-E1FF` by
// the dean's launch in `exit-dean-both-doors.spec.ts`. Anchoring the student
// specs' own `beforeAll` launches would be too late — the enrollment already
// exists, at the wall clock, and nothing may rewrite its start date. So the
// deterministic first creation is done here, before any other spec in the
// `chromium` project runs (this file sorts first), and every later launch into
// these sections is then a debounced or immutable-`started_on` no-op that leaves
// the anchored date standing. `docs/MISTAKES.md` entry 48's shape read forwards:
// the enrollment a later spec relies on must actually reach the product's
// database, dated when that spec needs it.
//
// **`MATH-140-E1FF` is stored by the dean, deliberately.** SPEC §7.3 has an
// instructor's *or* a leadership person's launch store a section's roster
// address, and `exit-dean-both-doors.spec.ts`'s witness is that the *dean's*
// launch — carrying no Instructor URN — stores E1FF's. Storing it here via the
// instructor would leave the address already set by an Instructor-URN launch
// before that spec runs, and its mutation-killer ("a door that stores the address
// only for an Instructor URN") could no longer tell the fix from the defect. The
// dean stores it the same way that spec does, so under that mutation this file's
// wait times out and reds too, and the witness is untouched.
//
// **The clock is global state on a shared stack.** `playwright.config.ts` pins
// `workers` to 1 for that reason, and this file clears the override in `afterAll`
// so the section-start clock it stands on cannot leak into whatever runs next.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from '@playwright/test';

import { clearTheClock, setTheClockTo } from './support/clock';
import { launchAs, placementInto } from './support/doors';
import { databaseStatement, deriveSurveyWindows } from './support/stack';
import {
  INSTRUCTOR_SUBJECT,
  INSTRUCTOR_VIEW,
  LEARNER_SUBJECT,
  type SectionUnderTest,
  sectionStartClock,
  waitForTheLearnersBlocks,
} from './support/survey';

// The dean, spelled the way `exit-dean-both-doors.spec.ts` spells him, and his
// one landing view. He is enrolled in `MATH-140-E1FF` and nowhere else
// (`mock-lms/app/seed.py`), so a launch by him reaches exactly that section.
const DEAN_LAUNCH_SUBJECT = 'mock-lms-user-dean';
const LEADERSHIP_VIEW = 'pulse-landing-leadership';

/** One section to anchor, and the staff subject whose launch stores its roster address. */
interface AnchoredSection extends SectionUnderTest {
  readonly staff: string;
  readonly staffView: string;
}

const R3WW: AnchoredSection = {
  label: 'BIOL-215-R3WW',
  code: 'R3WW',
  staff: INSTRUCTOR_SUBJECT,
  staffView: INSTRUCTOR_VIEW,
};
const E1FF: AnchoredSection = {
  label: 'MATH-140-E1FF',
  code: 'E1FF',
  staff: DEAN_LAUNCH_SUBJECT,
  staffView: LEADERSHIP_VIEW,
};
const SECTIONS: readonly AnchoredSection[] = [R3WW, E1FF];

// Generous, because each case waits on the roster worker after a staff launch,
// and its latency is seconds — the same budget the student-survey specs give
// their own world setup.
const SETUP_TIMEOUT_MS = 120_000;

test.describe.configure({ mode: 'serial' });

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

for (const section of SECTIONS) {
  test(`the learner is enrolled in ${section.label} from its own section start`, async ({
    browser,
  }) => {
    test.setTimeout(SETUP_TIMEOUT_MS);
    const anchor = sectionStartClock(section.code);
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      // Both people's resource link into the section, required to be the same one:
      // a sync is discovered per section, so a staff launch into one section
      // enrolls nobody in another, and this file would then wait out its whole
      // window for an enrollment nothing was writing.
      const learnerPlacement = await placementInto(page, LEARNER_SUBJECT, section.label);
      const staffPlacement = await placementInto(page, section.staff, section.label);
      expect(
        staffPlacement,
        `The mock platform should offer ${section.staff} and the learner the same resource link ` +
          `into ${section.label}. A sync is discovered per section, so a staff launch into one ` +
          'section enrolls nobody in another.',
      ).toBe(learnerPlacement);

      // Stand the stack on the section's start day BEFORE the launch, and hold it
      // there through the wait below, so the roster sync the launch triggers
      // stamps `started_on` at the section start rather than at the wall clock.
      await setTheClockTo(page, anchor);

      // The trigger. SPEC §7.3: a staff launch stores the section's roster
      // address, which is the whole of what gives the scheduled sync its
      // discovery. The landing is the control on it — a launch that was refused
      // provisioned nothing and stored no address, and the wait would then be
      // waiting for a sync nobody asked for.
      await launchAs(page, section.staff, staffPlacement);
      await expect(page.getByTestId(section.staffView)).toBeVisible();

      // The section reached this database through that launch, so it has no
      // `survey_window` rows yet; they are materialized up front (ADR 0111) by an
      // hourly job, invoked rather than waited for. The learner's block renders
      // for an enrolled section whether or not a window is open, so this is not
      // what the wait below turns on — it is here so the section is whole.
      deriveSurveyWindows();

      // Hold the clock at the section start until the learner's block is on
      // screen, which is the observable form of "the roster sync has enrolled
      // them here" — so the sync has run and dated the enrollment before this
      // case moves on.
      await waitForTheLearnersBlocks(browser, learnerPlacement, [section]);
    } finally {
      await context.close();
    }

    // **The forbidden state, asserted** (`docs/MISTAKES.md` entry 3): no
    // enrollment in this section is dated anywhere but the section start. A
    // single distinct value proves the whole roster was synced at the anchored
    // clock; a second line — the wall-clock date — is the bug this file removes,
    // and reads back here rather than surfacing three specs later at a door.
    const startDay = anchor.slice(0, 'YYYY-MM-DD'.length);
    const distinctStarts = databaseStatement(
      'select distinct started_on from enrollment e ' +
        'join section s on s.id = e.section_id ' +
        `where s.lms_section_code = '${section.code}' order by 1;`,
    );
    expect(
      distinctStarts,
      `Enrollments in ${section.code} carry start dates ${JSON.stringify(distinctStarts)}, and ` +
        `every one should be ${startDay} — the day start letter ${JSON.stringify(section.code.charAt(0))} ` +
        "names in scripts/seed.py's START_LETTER_MAP. Any other value is a roster sync that ran " +
        'at the wall clock, which is the calendar time-bomb E4-22 removes: a section dated in the ' +
        'future of a spec that reads at a fixed past minute is refused at the no-access door.',
    ).toBe(startDay);
  });
}
