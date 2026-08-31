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
import { LeadershipLanding } from './routes/leadership';
import { StudentLanding } from './routes/student';

/**
 * The client route table — SPEC §13's `router.tsx`.
 *
 * The routes are declared one by one rather than generated from a table. There
 * are five, they are the five role areas, and each is the file E2 onwards edits;
 * a loop over a list would save nine lines and cost the thing that makes this
 * file readable, which is that you can see which component answers which path.
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

const routeTree = rootRoute.addChildren([
  indexRoute,
  studentRoute,
  instructorRoute,
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
