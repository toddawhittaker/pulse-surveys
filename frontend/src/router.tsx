import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router';

import { UnknownAddress } from './components/UnknownAddress';
import { AdminLanding } from './routes/admin';
import { CareLanding } from './routes/care';
import { InstructorLanding } from './routes/instructor';
import { InstructorReportRoute } from './routes/instructor/InstructorMondayReport';
import { LeadershipLanding } from './routes/leadership';
import { StudentLanding } from './routes/student';

/**
 * The client route table — SPEC §13's `router.tsx`.
 *
 * The routes are declared one by one rather than generated from a table. There
 * are six now — the five role areas, and the instructor's per-section report
 * under hers — and each is the file E2 onwards edits; a loop over a list would
 * save a few lines and cost the thing that makes this file readable, which is
 * that you can see which component answers which path.
 *
 * **The report is the first route in this repository with a parameter**, and
 * with a search parameter, and both are here rather than in the page for the
 * same reason: this file is the route table, so what an address may say is what
 * it says. `validateReportWeek` below is the whole of the client's opinion about
 * a week — that it is a positive whole number — and deciding whether such a week
 * has a report is emphatically not part of it (SPEC §5.1, and E4-11's third
 * criterion): the API answers that, and a page that filtered the address against
 * a list first would be a second copy of the rule that says which weeks exist.
 *
 * **The backend decides the role; this file only knows the paths.** ADR 0086
 * states the contract with E1-08/E1-09/E1-13: an entry door verifies the token,
 * resolves the landing role, and redirects to one of these five addresses. There
 * is no guard here, no role check and nothing to configure — a client-side
 * decision about which of these a person may see would be a second authority on
 * a question SPEC §2.1 gives to the server, and one that runs on the reader's own
 * machine.
 */

const rootRoute = createRootRoute({
  component: Outlet,
  notFoundComponent: UnknownAddress,
});

// `/app` itself. Nobody is sent here — the doors redirect to a role route — so
// it says so rather than guessing at one.
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: UnknownAddress,
});

const studentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/student',
  component: StudentLanding,
});

const instructorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/instructor',
  component: InstructorLanding,
});

/**
 * The one thing an address may say about a week, and the whole of it.
 *
 * A course week is a positive whole number (SPEC §2.2 counts from one), so
 * anything else — a word, a decimal, a zero, a negative, an absent parameter —
 * is not a week this client can ask about and is treated as no week at all. The
 * page then opens the latest published week, which is what an address with no
 * week means.
 *
 * **It does not decide whether the week has a report.** That is the API's
 * answer, and asking for an unpublished week is how the page gets it: the route
 * refuses with its own sentence and the page shows it. Filtering here against
 * `published_weeks` would put week arithmetic in the client under another name.
 *
 * The value arrives as a number when the address carries a bare digit string and
 * as a string when it carries anything else, because TanStack Router parses
 * search values as JSON where it can. Both are read, so `?week=4` and a value
 * some other producer quoted mean the same thing.
 *
 * **It answers with the member every time, `undefined` included, and that is
 * load-bearing rather than a style.** A route's validated search is *merged over*
 * what came off the address, so a validator that refuses a value by leaving the
 * member out leaves the raw one standing — `?week=banana` reaches the page as the
 * string "banana" and the page asks the API for a report on week "banana".
 * Measured while building this, not supposed;
 * `routes/instructor/instructorRoutes.test.tsx` holds four addresses to it.
 *
 * The declared type keeps the member **optional** even though the value is
 * always written, because that is what decides whether a link has to name a
 * week: the section menu links to a report without one, and a required member
 * would make every such link carry `week: undefined` out loud.
 */
function validateReportWeek(search: Record<string, unknown>): { week?: number } {
  const raw = search.week;
  const asked = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : Number.NaN;
  return { week: Number.isInteger(asked) && asked > 0 ? asked : undefined };
}

// SPEC §5.1's report, for one of the reader's own sections and one course week.
// The section is in the path because that is what the API's routes are keyed by;
// the week is a search parameter because it is optional — an address with none
// means the latest published week — and because that is what makes any week a
// reader reaches a link they can send to somebody.
const instructorReportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/instructor/sections/$sectionId',
  validateSearch: validateReportWeek,
  component: InstructorReportRoute,
});

const leadershipRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/leadership',
  component: LeadershipLanding,
});

const careRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/care',
  component: CareLanding,
});

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/admin',
  component: AdminLanding,
});

/**
 * The route tree, exported so a test can mount it on a memory history.
 *
 * `router` below is the application's one router and the one the type
 * augmentation registers; a test that needs to prove what an address does builds
 * its own over this same tree rather than over a second copy of it, because a
 * second copy is a route table that can agree with a test and disagree with the
 * application.
 */
export const routeTree = rootRoute.addChildren([
  indexRoute,
  studentRoute,
  instructorRoute,
  instructorReportRoute,
  leadershipRoute,
  careRoute,
  adminRoute,
]);

/**
 * `basepath` is the mount, and it has to agree with two other places: the
 * `base` in `vite.config.ts`, which decides the asset URLs the build writes, and
 * the mount in `backend/app/main.py`, which decides where the application is
 * served. All three are `/app` (ADR 0086).
 */
export const router = createRouter({
  routeTree,
  basepath: '/app',
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
