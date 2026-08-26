# 0086 — The single-page application is served by the app factory, at `/app`

## Context

[SPEC §13](../SPEC.md) draws two things that have to be reconciled. It gives
`backend/app/main.py` the job "FastAPI app factory, router mount, **SPA static
serve**", and it also draws a `frontend/Dockerfile` beside the frontend package,
which is what a separately-served frontend would need. E1-04 is the ticket that
lands the application, so it is the ticket that has to decide which of those is
the deployment.

Two more things are open and go with it. Nothing says at what address the
application is served, and that address has to be the same in three files —
`vite.config.ts`'s `base`, which decides the asset URLs the build writes,
`router.tsx`'s `basepath`, which decides what the client thinks a path is, and
the mount in the factory. And nothing says how the entry doors and the frontend
divide the question of *which* view a person gets: E1-08 and E1-09 land the
sessions and the post-entry redirects, and this ticket ships the five routes they
will redirect to.

The spec is silent on all three, and each is contestable, which is why this
record exists rather than a link to a section.

## Decision

**The application is served by the FastAPI process, mounted at `/app`, from a
directory named by `FRONTEND_DIST`.** `backend/Dockerfile` gains a Node build
stage that produces the bundle and copies it into the runtime image at a fixed
path, and sets that variable. There is no frontend image, no frontend service and
no reverse proxy.

**The mount is decided when the factory is called**, not when the module is
imported, and a missing build is a supported state: the application comes up and
`/app` answers 404. Every checkout that has not run `npm run build` is in that
state, including the one the backend suite, the migrations and the seed run on.

**Every path under the mount that matches no file is answered with
`index.html`**, so the client router can read the path. A path that matches a
file gets the file. Nothing on the server knows the five route names.

**The backend decides the landing role; the frontend renders the route it is
handed.** An entry door verifies the token, resolves the role, and redirects to
one of `/app/student`, `/app/instructor`, `/app/leadership`, `/app/care`,
`/app/admin`. The client never re-derives role from a claim, a cookie or
anything else on the reader's machine. This is the published contract with
E1-08, E1-09 and E1-13; E1-04 builds the frontend half of it and touches neither
door.

## Alternatives rejected

**A frontend container of its own, per §13's drawn `frontend/Dockerfile`.** The
tidiest picture and the most moving parts. It needs a fourth application service
in `docker-compose.yml`, and — because the browser has to reach one origin for
both the API and the application, or the tool acquires a cross-origin story it
does not have — a reverse proxy in front of both to route `/app` one way and
everything else the other. That is a new service, a new configuration file, and a
new closed-set entry in `test_compose_stack.py` for something §13's own sentence
about `main.py` says is not needed. It also splits `docker compose up` into two
things that can be at different versions, which is `docs/MISTAKES.md` entry 12
with a network in the middle. Rejected on cost, and it stays available: the mount
is one call, and the day this deployment needs a CDN in front of the bundle, what
changes is where the files come from rather than what the application is.

**Serve the application at `/`, with the API under a prefix.** The conventional
shape, and the one that reads best in a browser's address bar. Rejected because
the API's addresses are not this ticket's to move: `/healthz` is waited on by
every service in the Compose stack and by both CI health gates, `/lti/*` and
`/auth/*` are registered with a real platform and a real provider, and
`/openapi.json` is what §13's client generator reads. Moving all of them to buy a
shorter URL for five empty pages is a change with no upside and four gates'
worth of downside. `/app` also makes the mount's blast radius legible: anything
that goes wrong inside it is confined to one prefix, where a mount at `/`
swallows the API if it is registered in the wrong order — the failure being a
beautiful blank page and no health check.

**Let `StaticFiles(html=True)` answer without a fallback.** The one-line version,
and it is wrong in a way that looks right: it serves `/app/` correctly and
answers 404 at `/app/student`, so the application works exactly until somebody
arrives at a route rather than at the root — which is how every person arrives
once the doors redirect.

**Answer `index.html` to everything under the mount.** The other one-line
version. It passes every assertion about client routing and ships an application
whose scripts and stylesheets all come back as HTML, with the server reporting
200 throughout.

**Make `FRONTEND_DIST` a §6.3 setting in `app/config.py`.** Rejected because it
is not a deployment's choice. There are two answers — the repository's
`frontend/dist` and the path the image copied the bundle to — and the process
already knows which world it is in. A settings field would put it on the
documented configuration surface, in `.env.example`, as a knob whose only correct
values are the two defaults. `app/config.py` holds what an operator decides;
this is what a build step already decided.

**Fail startup when the build is missing.** Rejected because it takes down the
backend suite, `make migrate`, `make seed` and every backend developer's
checkout, none of which has a bundle. The mirror image — mount it anyway and
serve nothing — is worse: it reports 200 over an empty tree, which is ADR
[0083](0083-node-lives-in-a-root-npm-workspace-with-frontend-as-a-member.md)'s
"a gate turned on and made meaningless" wearing an application's clothes.

## Consequences

- **`/app` is a 404 on a checkout that has not built the frontend**, which is
  most of them. That is the honest report and it is also a thing to know before
  debugging: the first question about a 404 there is whether `npm run build
  --workspace frontend` has run.
- **The api image now depends on Node**, at build time only. It is pinned by tag
  and digest to the major `NODE_VERSION` names, so the bundle that ships and the
  bundle the pull-request gate builds come from the same runtime; a drift between
  those two would be a difference nothing compares. No `node_modules` and no node
  binary reach the runtime stage.
- **`design/tokens.css` became a build input.** `frontend/src/styles.css` imports
  it from outside its own package so that §7.6's single source stays one file,
  which means `.dockerignore` has to re-include it and the frontend build stage
  has to copy it. A context missing it fails the build loudly, which is the right
  direction, but it is an unusual dependency and worth knowing about.
- **The three copies of `/app` have to agree and nothing checks that they do.**
  `vite.config.ts`, `router.tsx` and `main.py` each spell it. Disagreement
  produces a page that loads and then fetches its assets from an address the API
  answers 404, which is a blank screen with a green health check behind it. The
  end-to-end spec is what catches it; a unit test cannot, because two of the
  three are read by a bundler and a browser.
- **The doors still render their own HTML at their own entry URLs.** E0-18's
  server-rendered landings are untouched by this ticket, so the five headings and
  five empty-state sentences exist in two places — `backend/app/services/landing.py`
  and `frontend/src/lib/landings.ts` — until E1-13 retires the first. The
  duplication is deliberate and is marked at both ends; an edit to either has to
  be an edit to both while it lasts.
- **The code-in-history note E0-18 recorded still stands.** Nothing here changes
  what those doors do, and it is E1-08 that reaches it.
- **A future CDN, or a cache header policy, has nowhere to be configured.**
  Starlette's `StaticFiles` decides the headers, and nothing overrides them.
  Nothing needs one today; the day something does, it is a decision of its own
  and this record is what it argues with.
