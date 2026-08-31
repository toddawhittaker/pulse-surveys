// E1-09 criterion 1 — a seeded leadership, Care and admin identity each logs in
// through the web door and lands on their E1-04 route with a session.
//
// What it proves: starting the web door at the tool's GET /auth/oidc/login,
// signing in at the mock IdP as one of the three, and returning to the tool's
// callback ends on that role's E1-04 route with a session the page can use. E1-09
// retires E0-18's inline 200 landing: the callback now answers 302 to
// /app/<role>#session=<jwt>, frontend/src/lib/session.ts lifts the token into
// sessionStorage and strips it from the address bar, and the SPA renders the
// landing view at that route. So the browser-level witness is four things at
// once — the route, the view, the stored session, and the stripped fragment.
//
// Falsification (the changes that must turn a case red): a door that landed every
// login on one route (Care and admin are the two cases that catch it, and each
// asserts the other four testids absent); a door that redirected without issuing
// a session (sessionStorage would be empty); a door that put the token in a query
// string rather than a fragment (it would still be in the address bar after the
// SPA had captured what it could, and it would be in the server's access log,
// which is the reason the fragment was chosen).
//
// Nobody's subject is written down here. The three identities are found by role in
// the mock IdP's own /mock/registration document (ADR 0058), the same way
// tests/integration/test_web_login_door.py::person_holding finds them, and matched
// against the login form's offered option values the way that suite's driver
// matches an identity — so a reseeding moves these cases with it instead of
// leaving them quietly asserting about somebody who is no longer there.
//
// This spec cannot be run without a production frontend build and a seeded,
// running Compose stack; its green is the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

// Testids the mock IdP login form publishes (mock-idp/app/pages.py).
const IDP_IDENTITY = 'mock-idp-identity';
const IDP_SUBMIT = 'mock-idp-submit';

// Where the SPA keeps the session it lifted out of the fragment (E1-08,
// frontend/src/lib/session.ts; the same key tests/e2e/cookieless-launch.spec.ts
// reads).
const SESSION_STORAGE_KEY = 'pulse.session';

// Every landing view the tool can route to; each login must reach exactly one.
const ALL_LANDINGS = [
  'pulse-landing-student',
  'pulse-landing-instructor',
  'pulse-landing-leadership',
  'pulse-landing-care',
  'pulse-landing-admin',
];

// The three §2 gives this door, with the E1-04 route and landing testid each
// reaches. DEAN stands for the leadership set — §2's reporting chain enters here
// too, and which of those five a seeded person holds is the mapping E1-13 owns.
const CASES = [
  { role: 'DEAN', route: 'leadership', testid: 'pulse-landing-leadership' },
  { role: 'CARE', route: 'care', testid: 'pulse-landing-care' },
  { role: 'ADMIN', route: 'admin', testid: 'pulse-landing-admin' },
];

type Published = Record<string, unknown>;

// Every mapping anywhere in the registration document that carries a `roles`
// member — a person is found by what a person has, not by the name of the array
// holding them, which is what tests/fixtures/mock_idp.py does and for the same
// reason: the document's shape below its contract members is not pinned.
function publishedPeople(node: unknown, found: Published[] = []): Published[] {
  if (Array.isArray(node)) {
    for (const item of node) publishedPeople(item, found);
  } else if (node !== null && typeof node === 'object') {
    const mapping = node as Published;
    if ('roles' in mapping) found.push(mapping);
    for (const value of Object.values(mapping)) publishedPeople(value, found);
  }
  return found;
}

// Sign in at the mock IdP's login form as the one seeded person holding `role`.
//
// The person is chosen from the registration document and then matched against
// the values the form actually offers, rather than by assuming which member of
// the published person is the option's value. `launch_only_roles` empty
// distinguishes the Care office from the person who holds Care *and* teaches —
// without it "the Care person" is whichever of the two the document lists first.
async function signInAs(page: Page, role: string): Promise<void> {
  const registration: unknown = await page.evaluate(async () => {
    const answer = await fetch('/mock/registration', { headers: { accept: 'application/json' } });
    if (!answer.ok) throw new Error(`/mock/registration answered ${answer.status}`);
    return (await answer.json()) as unknown;
  });

  const holders = publishedPeople(registration).filter((person) => {
    const roles = Array.isArray(person.roles) ? person.roles : [];
    const launchOnly = Array.isArray(person.launch_only_roles) ? person.launch_only_roles : [];
    return roles.includes(role) && launchOnly.length === 0;
  });
  expect(
    holders,
    `the registration document should publish exactly one person holding ${role} with no ` +
      'launch-only assignment; this case names one',
  ).toHaveLength(1);

  const identity = page.getByTestId(IDP_IDENTITY);
  const offered = await identity.evaluate((element) =>
    Array.from((element as HTMLSelectElement).options).map((option) => option.value),
  );
  const candidates = Object.values(holders[0]).filter(
    (value): value is string => typeof value === 'string' && value.length > 0,
  );
  const chosen = candidates.find((value) => offered.includes(value));
  expect(
    chosen,
    `no value published for the ${role} identity (${JSON.stringify(candidates)}) is offered by ` +
      `the login form (${JSON.stringify(offered)}), so this case cannot sign in as them`,
  ).toBeDefined();

  await identity.selectOption(chosen as string);
  await page.getByTestId(IDP_SUBMIT).click();
}

for (const item of CASES) {
  test(`a ${item.role} web login lands on /app/${item.route} with a session`, async ({ page }) => {
    // baseURL is the tool; GET /auth/oidc/login begins the code flow and the tool
    // redirects the browser to the mock IdP's authorization endpoint. The fetch
    // inside signInAs runs on the IdP's own page, so it is same-origin and no
    // provider address is written down here.
    await page.goto('/auth/oidc/login');
    await signInAs(page, item.role);

    // Positive first: this waits for the callback's redirect to be followed and
    // the SPA to render, so everything below is about a finished navigation
    // rather than about one that had not started (docs/MISTAKES.md entry 3).
    await expect(page.getByTestId(item.testid)).toBeVisible();

    expect(new URL(page.url()).pathname).toBe(`/app/${item.route}`);

    // The stripped fragment first, and the read second — the order is the fix for
    // a race, not a preference. The SPA captures the token and then strips it
    // (E1-08, frontend/src/lib/session.ts), so a URL with no `session=` in it is
    // the observable proof that the capture effect has run; `toHaveURL` retries
    // until it does. Read before that edge, under a loaded machine where the
    // bundle executes late, and sessionStorage is legitimately still empty on a
    // login that succeeded — which is how tests/e2e/web-login-cancel.spec.ts
    // failed once under six workers and passed alone (docs/MISTAKES.md entry 13:
    // the same hazard, worked around in one of the two places facing it).
    //
    // The assertion is unchanged: the fragment must be gone from the address bar,
    // and the token must never have been in the query string.
    await expect(
      page,
      'the fragment should have been stripped from the address bar once captured, and the token ' +
        'should never have been in the query string',
    ).not.toHaveURL(/session=/);

    const stored = await page.evaluate(
      (key) => window.sessionStorage.getItem(key),
      SESSION_STORAGE_KEY,
    );
    expect(
      stored,
      'the session token should be in sessionStorage, lifted from the fragment',
    ).not.toBeNull();
    expect(stored).toContain('.');

    // Exactly one of the five, so a door that landed every login on one route —
    // or on the wrong one — fails here rather than passing on the testid it was
    // asked for.
    for (const other of ALL_LANDINGS.filter((testid) => testid !== item.testid)) {
      await expect(page.getByTestId(other)).toHaveCount(0);
    }
  });
}
