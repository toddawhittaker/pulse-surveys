# 0116 — The three webfonts are self-hosted in the bundle

**Status:** Accepted
**Date:** 2026-09-02
**Tickets:** E2-10

## Context

`design/tokens.css` names three faces and gives each a job (SPEC §7.6): Literata
for display, Schibsted Grotesk for body, Spline Sans Mono for every number. It
also gives each a fallback that is already on the machine, and until now nothing
fetched the real faces — no `<link>` in `frontend/index.html`, no `@font-face`,
no self-hosted files. E1-04 recorded that as a deferral rather than a decision
(`docs/tickets/e1/deferred.md`, item 1), carried into E2 with a "done when" that
names this ticket's circumstances: "the strategy is decided … and built, with
E2's first real screen, where there is something to look at while deciding."

This is that screen, so the deferral is due.

Two things make the choice contestable rather than obvious. `docs/DESIGN_BRIEF.md`
treats the type contrast as load-bearing — the anti-slop rules forbid Inter,
Roboto, Arial, Lato and system stacks by name, and say the contrast with the
host's Lato is "how the tool reads as its own considered thing inside the host" —
so shipping the fallbacks gives up something the brief spends a section on. And
Pulse renders inside somebody's LMS in an iframe, so a font fetch to a font host
is a third-party request made on a student's behalf from inside their
institution's page, which E0-18 already declined to make for the server-rendered
landings.

## Decision

**The three faces are self-hosted: they ship in the bundle and are fetched from
the tool's own origin.** `@fontsource/literata`, `@fontsource/schibsted-grotesk`
and `@fontsource/spline-sans-mono`, pinned exactly at 5.3.0 in
`frontend/package.json` with the resolution and hash in the root lockfile (ADR
0083's one lockfile, CLAUDE.md's pinned versions).

**Only the weights and the subset that have a job.** Literata 600 and 700,
Schibsted Grotesk 400 and 500, Spline Sans Mono 400 and 500 — the six the brief
names — in the latin subset and the normal style. Six imports rather than three,
because `@fontsource/<family>` without a weight is every weight and every subset,
and an italic nothing in this design uses is bytes a student on campus wifi pays
for.

**Imported from `frontend/src/main.tsx`**, so the bundler emits the files beside
the bundle and rewrites the `url()`s to the built asset paths. Not a `<link>` in
`index.html`, which would name a path the build does not know about.

**`design/tokens.css` is unchanged.** It stays the single source for the family
names and its fallback stacks stay exactly as they are: they are what renders
before the faces arrive (`font-display: swap`) and what renders if one never
does.

## Alternatives rejected

**A `<link>` to Google Fonts**, which is what the design prototype's own
`<helmet>` does and what the brief means by "all on Google Fonts, so prototypes
and production match". It is one line and it is the option this record exists to
refuse: the tool runs in an iframe inside a student's institutional page, so
every render would make a third-party request on that student's behalf,
attaching their IP address and a referrer to a request they did not choose. It
also makes first paint depend on a host outside the deployment, inside a §10
latency budget, on campus networks that sometimes block exactly this. E0-18 made
the same call for the server-rendered landings, and the deferred entry that
scheduled this decision carries the reasoning as its own.

**Ship the fallbacks and say so in the brief.** The other half of E1-04's
"done when", and it is a real option: Georgia, Helvetica Neue and `ui-monospace`
are decent faces and cost nothing. Rejected because the brief's typography
section is not decoration — three faces with three jobs is how the numbers read
as measurement and how the tool reads as its own thing inside Canvas — and
because the cost of taking it is 119 KB of woff2 on a page whose gzipped payload
is 91 KB, fetched once and cached.

**Variable fonts** (`@fontsource-variable/*`), one file per family instead of
two. Fewer requests and a smaller total where a design uses many weights. This
one uses two per family, and a variable file carries the whole axis; measured
against the six static latin faces the trade is not worth the extra decision, and
it stays available.

**Subset the faces further** — a custom pipeline building a glyph set from the
copy this application ships. Smaller again, and it makes the fonts a build step
this repository owns and has to keep correct as copy changes, including the
copy a student types into a comment box. The latin subset is already the narrow
one.

**Preload the faces with `<link rel="preload">`.** Not rejected on the merits;
not built, because nothing has measured a first-paint problem to fix, and a
preload for a face a page does not use on its first paint is a request that
competes with one it does.

## Consequences

**The counted payload grows by 219 bytes gzipped, and the uncounted assets by
119 KB.** Measured on this branch: the initial payload
`scripts/ci/check_bundle_size.py` counts — the entry chunk plus the stylesheet —
is **93,678 bytes gzipped with the faces and 93,459 without them**, so the six
`@font-face` rules are the whole of the decision's effect on the budget. The
budget stays comfortably green (entry 89,811 of 131,072; total 93,678 of
163,840). The faces themselves are **119,100 bytes of woff2**, emitted as
separate assets that the gate does not measure. That is the honest number for
this decision and it is stated here because the gate cannot state it: a font
regression is invisible to the budget, and the pull request that adds a fourth
face is where somebody has to say so out loud.

**A second copy of every face ships and no browser fetches it.** Each
`@fontsource` stylesheet lists woff2 and woff, so the build emits both and the
woff files are a further **147,028 bytes** in the image and in `dist`. Every
browser this application supports takes the woff2. The duplication is accepted
rather than removed, because removing it means hand-writing six `@font-face`
rules that restate what the package already declares — a second statement of the
family, the weight, the style and the file path, which is the shape of
duplication `docs/MISTAKES.md` entry 19 is about, and one that breaks silently on
an upgrade.

**The three packages are OFL-1.1, which the license gate does not recognise.**
`scripts/ci/check_licenses.py` has no rule for the SIL Open Font License, so the
three report as "no recognizable license" — a line in the report, not a failure,
because the gate is not run with `--strict-unknown`. The licence is permissive
and compatible with distributing this project under MIT (SPEC §10), and it also
asks that its own text travel with the font files, which this build does not do.
Neither half is fixed here: `scripts/ci/` is a heavy-lane path and this is a
light-lane ticket, so both are recorded in `docs/tickets/e2/deferred.md` with
what closes them.

**First paint is unchanged and second paint is not.** `font-display: swap` is
what `@fontsource` writes, so text renders immediately in the fallback and
reflows when the face arrives. That is the right trade for a form a student is
reading, and it is a visible reflow on a cold cache.

**The api image build gains three packages and no new step.** The frontend stage
already runs `npm ci` from the root lockfile and `npm run build`; the fonts ride
that. Nothing is fetched at build time from anywhere but the registry the
lockfile pins.

**This closes E1-04's deferred item 1**, recorded in place in
`docs/tickets/e1/deferred.md` in the shape E1-15 used. `docs/tickets/e2/carried-from-e1.md`
carries the same entry pointing at that file, which is where the closure is
written; the carried entry defers to it and is not restated here.
