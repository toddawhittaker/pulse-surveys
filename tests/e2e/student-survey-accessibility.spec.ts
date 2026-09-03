// The weekly survey for a student who cannot see it, or cannot see it well —
// ticket E2-17, items 1, 2, 3, 4, 7 and 8. SPEC §14.2 item 4, §4.1, §7.6.
//
// The epic-boundary review, re-measured against the live stack, found this
// screen unusable for a screen-reader student who has not answered everything,
// unreadable in two places for a low-vision student, silent where the design
// brief demands an announcement, and — from the other review — assembling its
// submission without the CSRF header the server's cookie path requires. Each of
// those is a browser fact: the accessibility tree, the used border width of a
// rendered ring, the header on a request the page built. None of them is
// reachable from pytest, which is why they are here.
//
// **What this file deliberately does not prove.** Nothing about who may read or
// submit — that is `app.services.survey_read` and `app.services.submissions`,
// and the integration suites own it. Nothing about the confidentiality
// sentence's count, which needs two open windows and is
// `student-survey-confidentiality.spec.ts`. Nothing about the bounce path, which
// `student-survey.spec.ts` already drives end to end; item 8's second half —
// "the bounce still announces" — is that spec's second test, and it is the
// control on this file's change to the live region rather than something
// re-driven here at the cost of another classifier round trip.
//
// **The clock, the section and the week.** One section, `BIOL-215-R3WW`, at
// 19:00 on Friday 2 October 2026 — term week 7, which is that section's fourth
// course week, inside a window that opened an hour earlier and nowhere near
// either edge. The same minute `student-survey.spec.ts` uses, for the same
// reason. The override is cleared in `afterAll`; `playwright.config.ts` pins
// `workers` to 1 because the stack has one clock.
//
// **Two seams this file needs and the ticket leaves to the implementer.** Item 3
// asks for "the existing token nearest the design intent" with a computed ratio
// ≥ 3:1, and which token that is, is the implementer's call — so the page
// *publishes the name it chose* and this spec resolves it. The unchecked Likert
// dot carries `data-pulse-ring-token` and the workload slider carries
// `data-pulse-track-token`, each holding the custom property the colour is drawn
// from (`--something`). That is the whole contract: the spec asserts that the
// token is one `design/tokens.css` declares, that the ratio it computes against
// `--paper` clears the floor, and that `design/`'s prototype names the same
// token — none of which chooses the token. An assertion written the other way,
// against a colour named in this file, would be this spec picking the palette.
//
// **"The rendered colour really is that token's value" is asserted on the dot
// and not on the slider track**, and dispute E2-17-01 is why: Chromium's
// `getComputedStyle` ignores the `::-webkit-slider-runnable-track` argument and
// answers with the input's own style, so a track colour cannot be read that way
// at all. The dot's element is styled directly and is read directly; the track's
// test keeps the token and the ratio, and the prototype test ties both tokens to
// `design/`.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { test, expect, type Locator, type Page } from '@playwright/test';

import { clearTheClock } from './support/clock';
import { TOOL_ORIGIN } from './support/doors';
import {
  BOUNCE_ANNOUNCEMENT,
  SUBMIT,
  type SectionUnderTest,
  chooseRating,
  clearTheWeek,
  expectTheFormIsShowing,
  firstQuestionPrompt,
  landOnTheSurvey,
  setSlider,
  standTheLearnerIn,
} from './support/survey';

const BIOLOGY: SectionUnderTest = { label: 'BIOL-215-R3WW', code: 'R3WW' };

// Transcribed from the seeded calendar, not computed from the code under test
// (`docs/MISTAKES.md` entry 19): the term begins Monday 17 August 2026, so term
// week 7 begins Monday 28 September, and SPEC §3.1 opens each week's survey on
// the Friday at 18:00 in the institution's timezone.
const INSIDE_THE_WINDOW = '2026-10-02T19:00';

// SPEC §3.2's first question, as `scripts/seed.py` transcribes it from the spec.
// Held as a literal for `landing-views.spec.ts`'s reason and checked against
// what is stored before it is used, so a stack seeded differently says so rather
// than failing the assertion this is an input to.
const SEEDED_FIRST_PROMPT = 'This week, my instructor supported my learning.';

// The words SPEC §3.2 and the design brief give the ends of a 1–5 scale. The
// scale's polarity is what item 2 puts into the accessibility tree, and these
// two strings are how a screen reader hears which end is which.
const LOW_END = 'Strongly disagree';
const HIGH_END = 'Strongly agree';

// The attributes the page publishes its chosen tokens under. See the header:
// this is the seam, not the choice.
const RING_TOKEN = 'data-pulse-ring-token';
const TRACK_TOKEN = 'data-pulse-track-token';

// WCAG 2.2 SC 1.4.11's floor for a non-text control boundary, and the width the
// ticket requires the ring to be drawn at so the rendered pixels hold the ratio
// the token promises. Both are the ticket's numbers.
const NON_TEXT_FLOOR = 3;
const MINIMUM_RING_WIDTH = 2;

// The card these ratios are computed against. SPEC §7.6 makes `design/tokens.css`
// the single source for the palette and the design brief names `--paper` as
// "cards and input surfaces"; it is resolved from the page rather than written
// out, so this file says which surface it means without holding a copy of its
// colour.
const CARD_TOKEN = '--paper';

// The slider track's colour before this ticket (`--hairline`), and the ratio a
// replacement has to clear.
//
// **The floor is this spec's line rather than the ticket's, and it is drawn here
// rather than left implicit.** Criterion 3 scopes SC 1.4.11's 3:1 to the dot and
// says only that the track gets "the same treatment" over a measured 1.30:1, so
// demanding 3:1 of the track would invent a requirement and demanding "greater
// than 1.30" would accept a rounding step as a fix. Two sits between them: a
// whole ratio point clear of the defect, and comfortably under the 3:1 the
// criterion deliberately does not ask for here. Named, so a disagreement about it
// is a disagreement about one constant.
const TRACK_COLOUR_TODAY = '#DCE4DD';
const TRACK_FLOOR = 2;

// Three ratios measured outside this file, used as the control on the arithmetic
// below (`docs/MISTAKES.md` entry 3: run the instrument against what you claim it
// says, in both directions). The first two are E2-17's own measurements of the
// palette — `--spruce` on `--paper`, and the `--mist` ring this ticket exists to
// replace; the third is `--hairline`, the slider track's colour today. The
// second and third are *failures*, and requiring the instrument to call them
// failures is what says it can report one.
const PUBLISHED_RATIOS: readonly (readonly [string, string, number])[] = [
  ['#1E3932', '#FFFFFF', 12.45],
  ['#93A5A0', '#FFFFFF', 2.58],
  ['#DCE4DD', '#FFFFFF', 1.3],
];
const RATIO_TOLERANCE = 0.02;

// The prototype files SPEC §7.6 makes the visual contract, and the token each
// draws its ring and its track from today. E2-17 item 3 changes both sides
// together; these are the "before" values, and they are used only to say that
// the prototype moved when the CSS did.
const LIKERT_PROTOTYPE = join('design', 'LikertInput.dc.html');
const SLIDER_PROTOTYPE = join('design', 'WorkloadSlider.dc.html');
const RING_TOKEN_TODAY = '--mist';
const TRACK_TOKEN_TODAY = '--hairline';

// A value nothing else could produce, planted as `pulse_csrf` so that a header
// carrying it can only have come from the cookie.
const PLANTED_CSRF = 'e2-17-planted-csrf-4f1c9ae2';
const CSRF_COOKIE = 'pulse_csrf';
const CSRF_HEADER = 'x-pulse-csrf';

let placement = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  placement = await standTheLearnerIn(browser, [BIOLOGY], INSIDE_THE_WINDOW);
});

test.beforeEach(() => {
  clearTheWeek([BIOLOGY.code]);
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

test('the contrast arithmetic agrees with three ratios measured outside it', () => {
  // **The control on this file's own instrument, and it must be green from the
  // first run.** Every colour assertion below is a number this file computes,
  // and a computation nobody has checked is a comment (`docs/MISTAKES.md` entry
  // 9). So it is run against WCAG's own extremes — white on black is 21:1 and a
  // colour against itself is 1:1 — and against three ratios E2-17 measured on
  // the live stack before any of this was written.
  //
  // **Both directions.** Two of the three published ratios are *failures*: the
  // `--mist` ring at 2.58:1 is the defect item 3 exists for, and the
  // `--hairline` track at 1.30:1 is the design-fidelity half. An instrument that
  // called everything a pass would satisfy the ≥ 3:1 assertions below against
  // any palette at all, so it is required to call these two failures here.
  expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 3);
  expect(contrastRatio('#1E3932', '#1E3932')).toBeCloseTo(1, 3);
  expect(
    contrastRatio('rgb(147, 165, 160)', '#FFFFFF'),
    'The same colour written as `rgb(...)` and as hex must compute the same ratio: the values ' +
      'this spec compares come one from `getComputedStyle` (always `rgb(...)`) and one from a ' +
      'custom property (whatever `tokens.css` spells it as).',
  ).toBeCloseTo(2.58, 2);

  for (const [colour, against, published] of PUBLISHED_RATIOS) {
    expect(
      Math.abs(contrastRatio(colour, against) - published),
      `${colour} on ${against} computes ${contrastRatio(colour, against).toFixed(4)}:1 here and ` +
        `was measured at ${published}:1 for E2-17's ticket, against the live stack, before this ` +
        'file existed. A different answer is this arithmetic, not the palette — the sRGB ' +
        'relative-luminance formula of WCAG 2.2, with the 0.03928 knee and the 1.055 divisor.',
    ).toBeLessThanOrEqual(RATIO_TOLERANCE);
  }
  expect(
    PUBLISHED_RATIOS.filter(
      ([colour, against]) => contrastRatio(colour, against) < NON_TEXT_FLOOR,
    ).map(([colour]) => colour),
    'The instrument has to *call* two of these three failures under the 3:1 floor — the `--mist` ' +
      'ring this ticket replaces and the `--hairline` track beside it — and the third a pass. An ' +
      'instrument that answered "pass" for everything would satisfy every ≥ 3:1 assertion below ' +
      'against any palette at all, which is the whole shape of `docs/MISTAKES.md` entry 3.',
  ).toEqual(['#93A5A0', '#DCE4DD']);
});

test('the submit control is reachable from the keyboard and is never disabled', async ({ page }) => {
  // Criterion 1, first clause. Verified before this ticket: with nothing
  // answered the submit button carries `disabled`, so it leaves the tab order
  // entirely — the sequence ends at the slider — and the screen offers a
  // keyboard user nothing at all to activate and nothing that explains why.
  //
  // **The mutation this kills**: the button disabled while any answer is
  // missing, which is what ships today. The settled construction is that it
  // stays enabled and focusable always, and refuses to send rather than refusing
  // to exist.
  //
  // **The near miss it must survive**: a button that is enabled but unreachable
  // — `tabindex="-1"`, or moved outside the form's focus order. So the reach is
  // driven from the keyboard rather than asserted from the attribute: focus the
  // last field of the form and press Tab.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const submit = block.getByTestId(SUBMIT);
  await expect(
    submit,
    'With nothing answered the submit control is disabled. SPEC §14.2 item 4 puts keyboard ' +
      'operation in slice, and a disabled button is not in the tab order: a student using a ' +
      'screen reader tabs to the end of the form, finds nothing, and is told nothing. E2-17 ' +
      'item 1 keeps it enabled and focusable always.',
  ).toBeEnabled();

  await block.getByRole('slider').focus();
  await page.keyboard.press('Tab');
  const reached = await submit.evaluate((button) => button === document.activeElement);
  expect(
    reached,
    'Tab from the workload slider — the last question — did not land on the submit control. The ' +
      'measured sequence before this ticket ended at the slider, because the button was disabled; ' +
      'a button that is enabled and still unreachable is the same defect wearing a different ' +
      'attribute.',
  ).toBe(true);
});

test('activating submit with answers missing sends nothing, says which question, and moves focus there', async ({
  page,
}) => {
  // Criterion 1, the rest of it: activating it submits nothing, the message is
  // announced and visible, and focus lands on the first unanswered control.
  //
  // **The mutations this kills.** A button that submits an incomplete week, which
  // the server would refuse and the student would meet as a failure rather than
  // as guidance. A message written into the live region and nowhere on screen,
  // which a sighted keyboard user never gets. A message put on screen and tied
  // to nothing, which a screen reader never reads when the button takes focus.
  // And a focus that stays on the button, which leaves the student to hunt for
  // the question the sentence is about.
  //
  // **The recorder is controlled inside the test, and it has to be**: "no
  // request was sent" is true of a page that sent nothing because its button was
  // still disabled, and true of a broken recorder. So the same recorder is
  // required to *see* a POST at the end, once the form is complete — which is
  // also the boundary pair for item 1, an always-enabled button that still
  // submits when there is something to submit.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const stored = firstQuestionPrompt();
  expect(
    stored,
    'SPEC §3.2\'s first question is not stored with the wording this spec holds, so the message ' +
      'assertion below would be looking for a sentence the page has no reason to say. The seeded ' +
      'set is `scripts/seed.py`\'s transcription of the spec.',
  ).toBe(SEEDED_FIRST_PROMPT);

  const posted = postsToTheTool(page);
  await expect(
    block.getByTestId(SUBMIT),
    'The submit control is disabled with nothing answered, so it cannot be activated and the ' +
      'rest of this test has nothing to measure. Asserted here rather than left to `click()`, ' +
      'which would wait for the button to enable and fail as a timeout — a red that reads as a ' +
      'broken spec rather than as the defect. The previous test is where this is the subject.',
  ).toBeEnabled();
  await block.getByTestId(SUBMIT).click();

  const described = await describedByText(block.getByTestId(SUBMIT));
  expect(
    described.text.trim(),
    'The submit control carries no description after being activated with every answer missing ' +
      `(aria-describedby: ${JSON.stringify(described.ids)}). E2-17 item 1: the message goes into ` +
      'visible text tied to the button by `aria-describedby`, so that a screen reader reads it ' +
      'when the button takes focus rather than only when a live region happens to fire.',
  ).not.toBe('');
  await expect(
    described.locator,
    'The message tied to the button is not visible. It is owed to a sighted keyboard user as ' +
      'well as to a screen reader; a visually-hidden description satisfies half the criterion.',
  ).toBeVisible();
  expect(
    described.text,
    `The message reads ${JSON.stringify(described.text)} and does not name the question that is ` +
      'unanswered. E2-17 item 1 settles a message "naming the first unanswered question", and ' +
      'with nothing answered that is SPEC §3.2\'s first. A message that says only "something is ' +
      'missing" sends a student back through five questions to find out which.',
  ).toContain(SEEDED_FIRST_PROMPT);
  expect(
    described.text.toLowerCase(),
    'A student who has not finished a form has done nothing wrong. `design/Usage Rules.md` §4 ' +
      'keeps student surfaces plain and blameless.',
  ).not.toMatch(/reject|fail|invalid|wrong|error/);

  const announced = await liveRegionTexts(block);
  expect(
    announced.join(' '),
    `No live region on this screen carries the message. The regions hold ${JSON.stringify(
      announced,
    )}. E2-17 item 1 puts the sentence into the form's live region as well as beside the button: ` +
      'a description is read when the button takes focus, and the announcement is what reaches a ' +
      'student whose focus has already moved on.',
  ).toContain(described.text.trim());

  const focused = await block.getByRole('radio').first().evaluate((radio) => {
    const group = radio.closest('fieldset') ?? radio.parentElement;
    const active = document.activeElement;
    return {
      radiosInTheGroup: group === null ? 0 : group.querySelectorAll('input[type=radio]').length,
      insideTheGroup: group !== null && active !== null && (group === active || group.contains(active)),
      active: active === null ? 'nothing' : `${active.tagName}${active.getAttribute('data-testid') ?? ''}`,
    };
  });
  expect(
    focused.radiosInTheGroup,
    'The first Likert radio has no group around it holding the whole scale, so "focus moved to ' +
      'the question" cannot be measured from here — the assertion below would be about a wrapper ' +
      'around one radio.',
  ).toBeGreaterThanOrEqual(5);
  expect(
    focused.insideTheGroup,
    `Focus is on ${focused.active} after the refused activation. E2-17 item 1 moves it to the ` +
      'first unanswered control, which with nothing answered is SPEC §3.2\'s first question. ' +
      'Focus left on the button leaves a keyboard user to hunt for the field the message is ' +
      'about (SPEC §14.2 item 4, and the same rule the bounce path already keeps).',
  ).toBe(true);

  expect(
    posted.map((request) => request.url),
    'Activating submit with every answer missing sent a request. E2-17 item 1: it submits ' +
      'nothing. A week the server refuses is a refusal the student meets as an error, which is ' +
      'the state this construction exists to replace.',
  ).toEqual([]);

  // The control on the recorder, and item 1's other side: the same button, the
  // same page, a complete form, and now it does submit.
  await chooseRating(block, 0, '4');
  await chooseRating(block, 1, '4');
  await setSlider(block, '3');
  await block.getByTestId(SUBMIT).click();
  await expect(block.getByTestId(SUBMIT)).toHaveCount(0);
  expect(
    posted.length,
    'The recorder saw no POST to the tool even after a complete week was submitted, so its ' +
      'silence above says nothing about whether the refused activation sent anything ' +
      '(`docs/MISTAKES.md` entry 3).',
  ).toBeGreaterThan(0);
});

test('the accessibility tree carries the scale’s polarity, in the group and in the end radios', async ({
  page,
}) => {
  // Criterion 2. Verified before this ticket: the ends are a `div` with no id,
  // the radio group is described by nothing, every radio's accessible name is a
  // bare digit, and the tree therefore offers "1" to "5" with no statement of
  // which end is which. A student using a screen reader is asked to agree or
  // disagree on a scale whose direction is drawn and never spoken.
  //
  // **The mutations this kills.** The ends given an id and nothing pointing at
  // it. The `aria-describedby` written on each radio rather than on the group,
  // which repeats the whole legend five times per scale. And end words put on
  // every radio, which is why the middle one is asserted to stay a digit.
  //
  // **The near miss it must survive**: how the two are worded. "1 — Strongly
  // disagree" is the settled shape, but the separator is a typography decision
  // this spec has no business pinning, so the names are matched on the digit and
  // the end words rather than on a whole string.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  await expect(
    block.getByRole('radio', { name: new RegExp(`^1\\b.*${LOW_END}`, 'i') }),
    `Neither scale offers a radio whose accessible name starts with 1 and carries ${LOW_END}. ` +
      'SPEC §3.2 gives both questions a 1–5 scale, so there are two of them.',
  ).toHaveCount(2);
  await expect(
    block.getByRole('radio', { name: new RegExp(`^5\\b.*${HIGH_END}`, 'i') }),
    `Neither scale offers a radio whose accessible name starts with 5 and carries ${HIGH_END}.`,
  ).toHaveCount(2);
  await expect(
    block.getByRole('radio', { name: '3', exact: true }),
    'The middle radios no longer answer to a bare "3". E2-17 item 2 puts the end words on 1 and ' +
      '5 only — a scale that names every point is five sentences a screen reader reads on the ' +
      'way past, and it is what the group description exists to avoid.',
  ).toHaveCount(2);

  const description = await groupDescriptionAround(block);
  expect(
    description.radiosInside,
    `The element describing the first scale is ${description.where}, and it holds ` +
      `${description.radiosInside} radios. E2-17 item 2 points the *group* at the ends — the one ` +
      'element holding that scale\'s five points, and not a radio (which repeats the legend five ' +
      'times), and not a wrapper around the whole form (which describes the second scale with the ' +
      'first one\'s ends).',
  ).toBe(5);
  expect(
    description.text,
    `The first scale's group is described by text reading ${JSON.stringify(description.text)}. ` +
      'E2-17 item 2 gives the ends element an id per question instance and points the radio group ' +
      'at it, so the polarity is read once when the group is entered rather than being drawn and ' +
      'never spoken.',
  ).toContain(LOW_END);
  expect(description.text).toContain(HIGH_END);
});

test('choosing a low rating announces that the comment has become required', async ({ page }) => {
  // Criterion 4. Verified before this ticket: a rating of 1 or 2 flips
  // `aria-required`, swaps the helper sentence and adds the "Needed to submit"
  // flag, all silently — a screen-reader student learns that the form has
  // changed under them only by going back and finding out.
  //
  // **The mutation this kills**: the flip made without any announcement, which
  // is today's behaviour and passes every existing assertion about
  // `aria-required`.
  //
  // **The pair, and the ruling it comes from.** Becoming *required* is
  // announced; becoming optional again is a relaxation and is not (the ruling of
  // 2026-09-03). So the second half of this test raises the rating and requires
  // that the become-required sentence is no longer being announced — a live
  // region still holding it would go on telling a student a comment is needed
  // when it is not.
  //
  // **The empty reading first.** The region is required to be empty before the
  // rating is chosen, or "it is non-empty afterwards" would be satisfied by a
  // region that always says something.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const before = await liveRegionTexts(block);
  expect(
    before.join('').trim(),
    `A live region on this screen already says ${JSON.stringify(before)} with nothing answered. ` +
      'The announcement below would then be indistinguishable from whatever was there already.',
  ).toBe('');

  await chooseRating(block, 0, '2');
  await expect(
    block.getByRole('textbox').nth(0),
    'A rating of 2 did not make the comment beside it required, so this test never reached the ' +
      'flip it is about (SPEC §3.2, "Required if Q1 ≤ 2"). That is the premise, not the subject.',
  ).toHaveAttribute('aria-required', 'true');

  const announced = (await liveRegionTexts(block)).join(' ').trim();
  expect(
    announced,
    'Nothing was announced when the comment became required. The rating changed, `aria-required` ' +
      'flipped, the helper sentence swapped and the flag appeared — and a student who is not ' +
      'looking at the screen was told none of it. E2-17 item 4 writes one copy-module sentence ' +
      'into the live region on the flip.',
  ).not.toBe('');
  expect(
    announced.toLowerCase(),
    'Nothing in this product shames. A low rating is an answer, not a fault, and the sentence ' +
      'that says a comment is now needed is the one most likely to slip into the language of ' +
      'error (`design/Usage Rules.md` §4).',
  ).not.toMatch(/reject|fail|invalid|wrong|error/);

  await chooseRating(block, 0, '4');
  await expect(block.getByRole('textbox').nth(0)).toHaveAttribute('aria-required', 'false');
  const afterward = (await liveRegionTexts(block)).join(' ').trim();
  expect(
    afterward,
    `The live region still announces ${JSON.stringify(afterward)} after the rating went back up ` +
      'and the comment became optional again. The ruling of 2026-09-03 announces the flip into ' +
      'required and not the relaxation out of it, and a region left holding the first sentence ' +
      'tells a student a comment is needed when it is not.',
  ).not.toBe(announced);
});

test('the accessibility-tree reading tells a rendered node from a display:none one', async ({
  page,
}) => {
  // **The control on the instrument the next test uses, and it must be green
  // from the first run.** "Chromium does not ignore this node" is a claim read
  // off the accessibility protocol, and a reader that answered `ignored: false`
  // for everything — or that failed to find any node at all — would make the
  // next test pass over exactly the defect it exists for
  // (`docs/MISTAKES.md` entry 35: require the guard to find the thing on a
  // subject that certainly has it, and to miss it on one that certainly has not).
  //
  // Two nodes are planted on the real page: one ordinary and one hidden the way
  // the live region is hidden today, `display: none` on an empty element.
  await landOnTheSurvey(page, placement, BIOLOGY.code);
  await page.evaluate(() => {
    const shown = document.createElement('p');
    shown.id = 'e2-17-control-shown';
    shown.textContent = 'A planted paragraph that is certainly in the accessibility tree.';
    const hidden = document.createElement('p');
    hidden.id = 'e2-17-control-hidden';
    hidden.style.display = 'none';
    hidden.textContent = 'A planted paragraph that Chromium is certain to ignore.';
    document.body.append(shown, hidden);
  });

  const shown = await accessibilityNodeFor(page, '#e2-17-control-shown');
  const hidden = await accessibilityNodeFor(page, '#e2-17-control-hidden');

  expect(shown.matched, 'The reader found no node for a paragraph in the document.').toBe(1);
  expect(hidden.matched, 'The reader found no node for the hidden paragraph.').toBe(1);
  expect(
    shown.ignored,
    'The reader reports an ordinary rendered paragraph as ignored, so it cannot say anything ' +
      `about the live region below. Its ignored reasons: ${JSON.stringify(shown.reasons)}.`,
  ).toBe(false);
  expect(
    hidden.ignored,
    'The reader reports a `display: none` paragraph as *not* ignored. That is the exact state ' +
      'the live region is in today, so a reader that cannot see it would report the defect fixed ' +
      'while it stands.',
  ).toBe(true);
});

test('the idle live region is rendered and not ignored by the accessibility tree', async ({
  page,
}) => {
  // Criterion 8. Verified before this ticket: `.pulse-bounce-announcement:empty
  // { display: none }` makes Chromium mark the node `notRendered`, so the region
  // a screen reader is supposed to be watching is not in the tree at all until
  // it already has something to say — which is the one moment it is too late to
  // start watching. The comment above that CSS states the opposite intent.
  //
  // **The mutation this kills**: hiding an empty live region by taking it out of
  // the render tree, in any of its spellings — `display: none`, `visibility:
  // hidden`, or the element simply not being in the document while idle.
  //
  // **The near misses it must survive**: the region is *not* required to be
  // visible. A visually-hidden treatment — the clipped 1px box — is exactly what
  // the ticket asks for, and it is rendered, unignored and invisible all at
  // once. And the region is required to be empty here, because a region that had
  // something in it would be rendered under today's CSS too and this test would
  // pass against the defect.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const region = block.getByTestId(BOUNCE_ANNOUNCEMENT);
  await expect(region, 'This screen has no live region at all.').toHaveCount(1);
  await expect(
    region,
    'The live region already holds text with nothing submitted, so its being in the tree says ' +
      'nothing about the idle state this criterion is about.',
  ).toBeEmpty();

  const display = await region.evaluate((element) => {
    const computed = getComputedStyle(element);
    return { display: computed.display, visibility: computed.visibility };
  });
  const hiddenBy =
    'The idle live region is taken out of the render tree; it computes ' +
    JSON.stringify(display) +
    '. Both "display: none" and "visibility: hidden" are what make Chromium ignore the node, and ' +
    'the ticket replaces the hiding with a visually-hidden treatment (the clipped 1px box) that ' +
    'keeps it rendered while still keeping it off the screen.';
  expect(display.display, hiddenBy).not.toBe('none');
  expect(display.visibility, hiddenBy).toBe('visible');

  const reading = await accessibilityNodeFor(page, `[data-testid="${BOUNCE_ANNOUNCEMENT}"]`);
  expect(
    reading.matched,
    'The accessibility reader matched no single node for the live region; it matched ' +
      `${reading.matched}. With one section on screen there is one region.`,
  ).toBe(1);
  expect(
    reading.ignored,
    `Chromium ignores the idle live region (${JSON.stringify(reading.reasons)}). A region the ` +
      'tree does not carry is one no screen reader is watching, so the bounce sentence written ' +
      'into it later announces to nobody — which is the whole of SPEC §3.3\'s coaching reaching ' +
      'the person at the keyboard.',
  ).toBe(false);
});

test('the unchecked Likert dot is drawn from a token that clears the non-text contrast floor', async ({
  page,
}) => {
  // Criterion 3, the dot. Measured for this ticket: the ring is `--mist` on the
  // white card, 2.58:1 by the token's own value and 1.92:1 as it is actually
  // rendered, because it is drawn one antialiased pixel wide. Both are under SC
  // 1.4.11's 3:1 floor for a non-text control boundary, and the second is the
  // one a person sees.
  //
  // **The mutations this kills.** The token left as it is. A darker token chosen
  // and the ring left at 1px, which is why the used width is asserted. And a
  // colour written straight into the component as a hex value, which the
  // frontend token sweep also refuses and which this test catches from the other
  // side: the rendered colour has to *equal* the value of the custom property
  // the element publishes.
  //
  // **What it does not choose**: which token. The element names it, and this
  // spec resolves whatever it names.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const dots = block.locator(`[${RING_TOKEN}]`);
  const count = await dots.count();
  expect(
    count,
    `No element in the section block publishes \`${RING_TOKEN}\`. E2-17 item 3 leaves the choice ` +
      'of token to the implementer, so the unchecked Likert dot names the custom property it ' +
      'draws its ring from and this spec resolves it. Without that attribute there is no way to ' +
      'assert the criterion without this file picking the palette.',
  ).toBeGreaterThan(0);

  const dot = dots.first();
  const token = ((await dot.getAttribute(RING_TOKEN)) ?? '').trim();
  expect(token, `\`${RING_TOKEN}\` is empty.`).toMatch(/^--[a-z0-9-]+$/);
  const value = await resolveToken(page, token);
  expect(
    value,
    `\`${token}\` resolves to nothing on this page. The attribute names a custom property that ` +
      '`design/tokens.css` does not define — SPEC §7.6 makes that file the single source for the ' +
      'palette, and no new token is in this ticket.',
  ).not.toBe('');

  const border = await dot.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      colour: computed.borderTopColor,
      width: Number.parseFloat(computed.borderTopWidth),
    };
  });
  expect(
    channels(border.colour),
    `The ring is drawn ${border.colour} and \`${token}\` is ${value}. The element names the token ` +
      'it draws from, so a rendered colour that is not that token’s value means the ring is ' +
      'painted from something else — a raw hex in the component, or a second declaration ' +
      'overriding the one that reads the token.',
  ).toEqual(channels(value));
  expect(
    border.width,
    `The ring is ${border.width}px wide. At 1px an antialiased ring renders lighter than its own ` +
      'colour — 2.58:1 by the token measured 1.92:1 on screen for this ticket — so the width is ' +
      'part of the criterion and not a detail of it.',
  ).toBeGreaterThanOrEqual(MINIMUM_RING_WIDTH);

  const behind = await effectiveBackground(dot);
  const ratio = contrastRatio(value, behind);
  expect(
    ratio,
    `The unchecked dot's ring is ${token} (${value}) against ${behind}, which computes ` +
      `${ratio.toFixed(2)}:1. WCAG 2.2 SC 1.4.11 requires 3:1 for the boundary of a control a ` +
      'person has to find, and this is the boundary of every unanswered radio on the highest-' +
      'traffic screen in the product.',
  ).toBeGreaterThanOrEqual(NON_TEXT_FLOOR);
});

test('the workload slider names a track token that clears the ratio the ticket recorded', async ({
  page,
}) => {
  // Criterion 3, the track. Measured for this ticket at 1.30:1 against the card
  // — a design-fidelity fix rather than a WCAG failure, because a slider track
  // is not the control's boundary; the thumb is, and it reads at 12.45:1.
  //
  // **What is asserted, and the ambiguity that is deliberately not papered
  // over.** The ticket says the track gets "the same treatment" and its criterion
  // scopes the ≥ 3:1 floor to the dot. So this test does not demand 3:1 of the
  // track. It demands the two things the ticket does say: the colour comes from a
  // token the element names and that token is declared, and it clears the 1.30:1
  // the ticket records as the defect by a stated margin. A track left as it is,
  // is not a fix.
  //
  // **This test read the painted colour until dispute E2-17-01, and could not.**
  // It compared `getComputedStyle(input, '::-webkit-slider-runnable-track')
  // .backgroundColor` against the token's value, on the belief that this is where
  // a range input's track lives. Chromium ignores that pseudo-element argument
  // and hands back the *input's own* style — proven twice independently, by the
  // implementer's probe in the dispute file (the returned `height` is the input's
  // 44px, not the track's declared 4px) and by the boundary verification's own
  // a11y pass, which hit the identical limitation and had to sample rendered
  // pixels instead. Worse, the two assertions were jointly unsatisfiable: the only
  // way to make that read carry the token's channels is to paint the *input*
  // with it, and then the ratio against its own background is 1.00. A test
  // asserting through an instrument that cannot see its subject is a broken
  // instrument, not a red, and the ruling is recorded in
  // `docs/disputes/E2-17-01.md`.
  //
  // **So the claim is narrowed to what can be measured here, and the rest is
  // measured where it can be.** "The rendered colour really is this token's
  // value" is asserted on the Likert dot, one test up, whose element
  // `getComputedStyle` reads directly. What this test keeps is the token: that
  // the slider publishes one, that `design/tokens.css` declares it, and that its
  // ratio against the card clears the floor. The prototype test below is what
  // ties the same token to `design/WorkloadSlider.dc.html`.
  //
  // **The card is resolved from `--paper` and not walked up from the slider.**
  // The dispute's closing paragraph is the reason: a background read from the
  // slider's own ancestry is the same colour the paint comparison would have
  // forced onto the input, and computing the ratio from it is how the
  // contradiction survives a repair.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  const slider = block.getByRole('slider');
  const token = ((await slider.getAttribute(TRACK_TOKEN)) ?? '').trim();
  expect(
    token,
    `The workload slider publishes no \`${TRACK_TOKEN}\`. As with the Likert ring, the token is ` +
      'the implementer’s choice and the attribute is how this spec learns it.',
  ).toMatch(/^--[a-z0-9-]+$/);

  const value = await resolveToken(page, token);
  expect(
    value,
    `\`${token}\` resolves to nothing on this page. The attribute names a custom property that ` +
      '`design/tokens.css` does not define — SPEC §7.6 makes that file the single source for the ' +
      'palette, and no new token is in this ticket. This is the assertion that keeps the ' +
      'attribute honest now that the painted colour is not read: a name nothing declares would ' +
      'otherwise satisfy every other reading here.',
  ).not.toBe('');

  const card = await resolveToken(page, CARD_TOKEN);
  expect(
    card,
    `\`${CARD_TOKEN}\` resolves to nothing on this page, so there is no card surface to compute a ` +
      'ratio against. The design brief names it as the colour of "cards and input surfaces".',
  ).not.toBe('');

  const ratio = contrastRatio(value, card);
  const measuredBefore = contrastRatio(TRACK_COLOUR_TODAY, card);
  expect(
    ratio,
    `The track is ${token} (${value}) against ${CARD_TOKEN} (${card}) at ${ratio.toFixed(2)}:1. ` +
      `The colour it replaces reads ${measuredBefore.toFixed(2)}:1 there, which is what the ` +
      'ticket records as the defect: at that ratio the track is invisible against the card and ' +
      `the slider reads as a floating thumb. The ${TRACK_FLOOR}:1 line is this spec's, drawn so ` +
      'that a rounding step does not pass as a fix; SC 1.4.11 is not being applied here, because ' +
      'criterion 3 scopes its 3:1 to the dot.',
  ).toBeGreaterThanOrEqual(TRACK_FLOOR);
});

test('the design prototype names the same tokens the screen draws with', async ({ page }) => {
  // Criterion 3's second half: "the design files agree with the CSS". SPEC §7.6
  // makes the prototype the visual contract — "the frontend implements it, it
  // does not reinterpret it" — so a colour changed in one and not the other
  // leaves the contract stating something untrue, and the next person to build
  // from `design/` rebuilds the defect.
  //
  // **The mutation this kills**: the CSS changed and the prototype left behind.
  // Read from the running page rather than from the frontend source, so what is
  // compared is what a browser actually painted.
  //
  // **The canary.** Each prototype is required to reference at least one custom
  // property before its content is judged, so a file that was moved, emptied or
  // renamed reports that rather than silently satisfying a search
  // (`docs/MISTAKES.md` entry 3).
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);

  // Counted before it is read, so a page publishing no ring token at all fails
  // here on an assertion rather than thirty seconds later inside `getAttribute`,
  // waiting for an element that does not exist. `count()` answers about the page
  // as it stands and never waits, which is what is wanted: the Likert test above
  // is where the seam's absence is the subject, and this one should say so in one
  // line rather than time out.
  const dots = block.locator(`[${RING_TOKEN}]`);
  expect(
    await dots.count(),
    `No element in the section block publishes \`${RING_TOKEN}\`, so there is no token for the ` +
      'prototype to be checked against. The Likert-ring test above is where that is diagnosed.',
  ).toBeGreaterThan(0);
  const ring = ((await dots.first().getAttribute(RING_TOKEN)) ?? '').trim();
  const track = ((await block.getByRole('slider').getAttribute(TRACK_TOKEN)) ?? '').trim();

  for (const [file, token, before] of [
    [LIKERT_PROTOTYPE, ring, RING_TOKEN_TODAY],
    [SLIDER_PROTOTYPE, track, TRACK_TOKEN_TODAY],
  ] as const) {
    const source = readFileSync(join(process.cwd(), file), 'utf8');
    expect(
      source,
      `${file} references no custom property at all, so a search of it for one proves nothing. ` +
        'It is read from the repository root, which is where `playwright.config.ts` is run from.',
    ).toContain('var(--');
    expect(
      token,
      `The page published no token for ${file} to be checked against, which the tests above ` +
        'diagnose.',
    ).toMatch(/^--[a-z0-9-]+$/);
    expect(
      source,
      `${file} does not draw with \`${token}\`, which is what the screen draws with. SPEC §7.6 ` +
        'makes the prototype the contract and the implementation its subject; the two moving ' +
        'apart is how the next screen built from `design/` reintroduces the ratio this ticket ' +
        'measured.',
    ).toContain(`var(${token})`);
    if (token !== before) {
      expect(
        source,
        `${file} still draws with \`${before}\` as well as with \`${token}\`. That is the value ` +
          'this ticket replaced; leaving it in the prototype leaves two answers to the same ' +
          'question in the file that is supposed to settle it.',
      ).not.toContain(`var(${before})`);
    }
  }
});

test('a submission assembled while the CSRF cookie is readable carries it in the header', async ({
  page,
}) => {
  // Criterion 7. `csrf_verified_student` requires `X-Pulse-CSRF` from a request
  // whose session rides the cookie, and before this ticket there was no `csrf`
  // anywhere under `frontend/src`: a student whose session travels as a cookie
  // could read the survey and never submit it, and the failure would arrive as a
  // 403 on the one action the screen exists for.
  //
  // **The cookie is planted rather than driven, and that is the E1 measurement
  // rather than a shortcut**: the dev stack sets its cookies `SameSite=None`
  // without `Secure`, so a browser refuses to store them and the jar stays empty
  // on a launch that succeeded. What is under test is the *client half* — that a
  // POST assembled while `pulse_csrf` is readable carries its value — so the
  // cookie is put where `document.cookie` will find it and the request is read
  // off the wire.
  //
  // **Planted before the launch**, so it is readable however the client reads
  // it: at the call site, or once when the module loads.
  await page.context().addCookies([
    {
      name: CSRF_COOKIE,
      value: PLANTED_CSRF,
      domain: 'localhost',
      path: '/',
      sameSite: 'Lax',
    },
  ]);

  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);
  const readable = await page.evaluate(() => document.cookie);
  expect(
    readable,
    'The planted `pulse_csrf` is not readable from the document, so this test would be asserting ' +
      'that the client sends a header for a cookie it cannot see. The cookie is deliberately not ' +
      '`HttpOnly` (ADR 0089) for exactly this reason.',
  ).toContain(PLANTED_CSRF);

  const posted = postsToTheTool(page);
  await chooseRating(block, 0, '4');
  await chooseRating(block, 1, '4');
  await setSlider(block, '3');
  await block.getByTestId(SUBMIT).click();
  await expect(block.getByTestId(SUBMIT)).toHaveCount(0);

  expect(
    posted.length,
    'No POST to the tool was recorded, so there is no request to read a header off.',
  ).toBeGreaterThan(0);
  expect(
    posted.map((request) => request.headers[CSRF_HEADER]),
    `The submission carried ${JSON.stringify(posted.map((r) => r.headers[CSRF_HEADER]))} in ` +
      `\`${CSRF_HEADER}\` and the readable cookie is ${JSON.stringify(PLANTED_CSRF)}. E2-17 item ` +
      '7: the API client sends the cookie’s value on every POST when the cookie is readable. A ' +
      'header carrying something else is a value minted in the browser, which is a double submit ' +
      'that verifies nothing (ADR 0089 binds the token to the session by HMAC).',
  ).toEqual(posted.map(() => PLANTED_CSRF));
});

test('a submission with no CSRF cookie to read still goes through on the Bearer path', async ({
  page,
}) => {
  // Criterion 7's other half: "the Bearer path is unchanged". The session
  // normally rides `Authorization: Bearer` inside the LMS iframe, and
  // `csrf_verified_student` exempts that carrier deliberately — a Bearer header
  // is not something a cross-site form can be tricked into sending, so there is
  // nothing there for a double submit to protect.
  //
  // **The mutation this kills**: a client that sends the header unconditionally
  // and, worse, one that *refuses to send the request* when the cookie is
  // missing. Either turns every student in the iframe — which is every student —
  // into a student who cannot submit, and neither is visible in the test above,
  // where the cookie is present.
  //
  // The pair is the point: with the cookie, the header; without it, no header
  // and the week still goes in.
  const block = await landOnTheSurvey(page, placement, BIOLOGY.code);
  await expectTheFormIsShowing(block);
  expect(
    await page.evaluate(() => document.cookie),
    'This browser has a cookie jar for the tool, so the "no cookie to read" case is not the case ' +
      'being measured. The dev stack’s own cookies are `SameSite=None` without `Secure` and ' +
      'Chromium refuses them, which is what makes this the ordinary state rather than a contrived ' +
      'one.',
  ).not.toContain(CSRF_COOKIE);

  const posted = postsToTheTool(page);
  await chooseRating(block, 0, '4');
  await chooseRating(block, 1, '4');
  await setSlider(block, '3');
  await block.getByTestId(SUBMIT).click();

  await expect(
    block.getByTestId(SUBMIT),
    'The week did not go in with no CSRF cookie readable. The session rides Bearer here, which ' +
      '`csrf_verified_student` exempts; a client that withholds the request until it finds a ' +
      'cookie has locked every student in the iframe out of the one action this screen is for.',
  ).toHaveCount(0);
  expect(
    posted.map((request) => request.headers[CSRF_HEADER] ?? null),
    'A submission with no readable `pulse_csrf` carried the header anyway. There is no cookie ' +
      'for the server to compare it against, so the value came from somewhere else in the ' +
      'browser — which is a token the double submit cannot verify.',
  ).toEqual(posted.map(() => null));
});

// ---------------------------------------------------------------------------
// Reading the page: colours, descriptions, live regions, the accessibility tree
// and the requests it makes.
// ---------------------------------------------------------------------------

/** One request this page made to the tool, with the headers it carried. */
interface PostedRequest {
  readonly url: string;
  readonly headers: Record<string, string>;
}

/**
 * Collect every POST this page makes to the tool, except the launch handshake.
 *
 * Armed by the test after it has landed, so the launch's own posts are behind it
 * and the list holds only what the survey screen assembled. The two launch paths
 * are excluded by address as well, because a spec that armed this earlier would
 * otherwise read a launch's headers and call them a submission's.
 *
 * Its control is the test that uses it first: the same recorder is required to
 * see a POST once the form is complete, so an empty list is a statement about
 * the page rather than about the recorder (`docs/MISTAKES.md` entry 3).
 */
function postsToTheTool(page: Page): PostedRequest[] {
  const seen: PostedRequest[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const url = request.url();
    if (!url.startsWith(TOOL_ORIGIN) || url.startsWith(`${TOOL_ORIGIN}/lti/`)) return;
    seen.push({ url, headers: request.headers() });
  });
  return seen;
}

/** What one element's `aria-describedby` points at: the ids, the locator, the text. */
interface Description {
  readonly ids: string[];
  readonly locator: Locator;
  readonly text: string;
}

/**
 * The text an element is described by, reached through its own `aria-describedby`.
 *
 * Through the attribute rather than by position or by class, so this is also the
 * assertion that the two are wired together: a sentence a screen reader never
 * reaches when the control takes focus is a sentence half the people meeting it
 * do not get (SPEC §14.2 item 4). The same reading `student-survey.spec.ts`
 * makes of a comment field's helper.
 */
async function describedByText(element: Locator): Promise<Description> {
  const attribute = (await element.getAttribute('aria-describedby')) ?? '';
  const ids = attribute.split(/\s+/).filter((id) => id.length > 0);
  const page = element.page();
  const locator = page.locator(ids.map((id) => `#${id}`).join(', ') || '#nothing-is-described-by');
  const texts = ids.length === 0 ? [] : await locator.allTextContents();
  return { ids, locator, text: texts.join(' ').trim() };
}

/** What describes the group the first Likert radio sits in, if anything does. */
interface GroupDescription {
  readonly where: string;
  readonly radiosInside: number;
  readonly text: string;
}

/**
 * The description on the nearest ancestor of the first radio that carries one.
 *
 * **The walk starts above the radio**, deliberately: a description written on
 * each radio rather than on their group is one of the two mutations item 2 is
 * about, and it reads correctly from a radio's own point of view. It answers
 * how many radios the describing element holds, so the caller can tell the
 * group of one scale from a wrapper around the whole form — the other mutation,
 * which would describe the second scale with the first one's ends.
 *
 * Written as one `evaluate` rather than as a chain of locators because the
 * question is about the document's own shape, and no ticket settles which
 * element the group is.
 */
async function groupDescriptionAround(block: Locator): Promise<GroupDescription> {
  return block.getByRole('radio').first().evaluate((radio) => {
    let walked: Element | null = radio.parentElement;
    while (walked !== null) {
      const ids = (walked.getAttribute('aria-describedby') ?? '')
        .split(/\s+/)
        .filter((id) => id.length > 0);
      if (ids.length > 0) {
        return {
          where: `<${walked.tagName.toLowerCase()} role=${JSON.stringify(
            walked.getAttribute('role') ?? '',
          )}>`,
          radiosInside: walked.querySelectorAll('input[type=radio]').length,
          text: ids
            .map((id) => document.getElementById(id)?.textContent ?? '')
            .join(' ')
            .trim(),
        };
      }
      walked = walked.parentElement;
    }
    return { where: 'nothing above the first radio', radiosInside: 0, text: '' };
  });
}

/** The text of every live region inside a block, in document order. */
async function liveRegionTexts(block: Locator): Promise<string[]> {
  return (await block.locator('[aria-live]').allTextContents()).map((text) => text.trim());
}

/** One custom property's value, resolved at the document root the way a component reads it. */
async function resolveToken(page: Page, token: string): Promise<string> {
  return page.evaluate(
    (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim(),
    token,
  );
}

/**
 * The colour actually behind an element, found by walking up until one is opaque.
 *
 * A contrast ratio is against what a person sees behind the thing, and a dot
 * sitting on a transparent wrapper inside a white card is against the card. The
 * walk stops at the first background that is not fully transparent and answers
 * it; the caller prints it, so a ratio computed against something unexpected is
 * readable in the failure rather than silently wrong.
 */
async function effectiveBackground(element: Locator): Promise<string> {
  return element.evaluate((node) => {
    let walked: Element | null = node;
    while (walked !== null) {
      const colour = getComputedStyle(walked).backgroundColor;
      const parts = colour.match(/[0-9.]+/g) ?? [];
      const opaque = parts.length < 4 || Number(parts[3]) > 0;
      if (colour !== 'transparent' && opaque) return colour;
      walked = walked.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
  });
}

/** What Chromium's accessibility tree says about one node. */
interface AccessibilityReading {
  readonly matched: number;
  readonly ignored: boolean;
  readonly reasons: string[];
}

/**
 * Read one node's accessibility state off the Chrome DevTools Protocol.
 *
 * The protocol rather than a rendered proxy, because "ignored" and its reasons
 * are exactly what a proxy does not carry: an element can be present, sized and
 * styled and still be `notRendered` in the tree, which is the defect item 8 is
 * about and the way it was measured for the ticket.
 *
 * The session is detached afterwards, so a test that opens one does not leave a
 * protocol client attached to a page the next test reuses.
 */
async function accessibilityNodeFor(
  page: Page,
  selector: string,
): Promise<AccessibilityReading> {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send('DOM.enable');
    await client.send('Accessibility.enable');
    const { root } = await client.send('DOM.getDocument', { depth: -1 });
    const { nodeIds } = await client.send('DOM.querySelectorAll', {
      nodeId: root.nodeId,
      selector,
    });
    if (nodeIds.length !== 1) return { matched: nodeIds.length, ignored: true, reasons: [] };
    const { nodes } = await client.send('Accessibility.getPartialAXTree', {
      nodeId: nodeIds[0],
      fetchRelatives: false,
    });
    if (nodes.length === 0) {
      // The protocol answered no node at all for an element that is in the
      // document. That is a stronger form of ignored, and it is reported as
      // ignored with its own reason rather than crashing on `nodes[0]` — a
      // reader that threw here would fail as a broken harness in the one state
      // the criterion is about.
      return { matched: 1, ignored: true, reasons: ['no accessibility node for the element'] };
    }
    const node = nodes[0];
    return {
      matched: 1,
      ignored: node.ignored,
      reasons: (node.ignoredReasons ?? []).map((reason) => reason.name),
    };
  } finally {
    await client.detach();
  }
}

/**
 * One colour as its three sRGB channels, however it is written.
 *
 * `getComputedStyle` answers `rgb(...)` and a custom property answers whatever
 * `tokens.css` spells — hex, usually — and the two have to be comparable. The
 * control on this function is the ratio test at the top of this file, which
 * computes the same published ratio from a hex value and from an `rgb(...)` one.
 */
function channels(colour: string): [number, number, number] {
  const text = colour.trim();
  if (text.startsWith('#')) {
    const digits = text.slice(1);
    const wide = digits.length >= 6 ? digits : [...digits].map((one) => `${one}${one}`).join('');
    expect(wide.length, `${colour} is not a hex colour this spec can read.`).toBeGreaterThanOrEqual(
      6,
    );
    return [0, 2, 4].map((at) => Number.parseInt(wide.slice(at, at + 2), 16)) as [
      number,
      number,
      number,
    ];
  }
  const numbers = text.match(/[0-9.]+/g) ?? [];
  expect(
    numbers.length,
    `${colour} carries fewer than three channels, so no ratio can be computed from it.`,
  ).toBeGreaterThanOrEqual(3);
  return [Number(numbers[0]), Number(numbers[1]), Number(numbers[2])];
}

/** WCAG 2.2's relative luminance of one sRGB colour. */
function luminance(colour: string): number {
  const [red, green, blue] = channels(colour).map((channel) => {
    const scaled = channel / 255;
    return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

/** WCAG 2.2's contrast ratio between two colours, lighter over darker. */
function contrastRatio(one: string, other: string): number {
  const first = luminance(one);
  const second = luminance(other);
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}
