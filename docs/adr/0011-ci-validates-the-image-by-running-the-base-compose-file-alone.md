# 0011 — CI validates the image by running the base Compose file alone

**Status:** Accepted
**Date:** 2026-08-13
**Tickets:** E0-03

## Context

[SPEC §13](../SPEC.md) puts development wiring — hot reload, exposed ports — in
`docker-compose.override.yml`, and [§7.2](../SPEC.md) says production runs the
same topology as the base file. Neither says which of those two files CI should
run, nor how the pipeline should establish that the image it built is the thing
that works. That is construction, and it is contestable: the pipeline was green
for two tickets without anyone noticing the question existed.

`docker compose up` merges the override automatically, so "run the stack" means
the merged stack unless someone says otherwise. E0-03 made that consequential.
The override mounts the checkout over `/app/backend` with `PYTHONPATH` ahead of
site-packages, and E0-03 extended that mount from `api` to `worker` and `beat`,
because without it an edited task reaches the API and not the worker. After that
change **every dynamic gate in the pipeline imported the application from the
bind mount, and none executed the copy `pip install` had put in the image.**

Measured rather than reasoned about. An image was built from source whose `ping`
returned `STALE-IMAGE-BUILT-AT-T0`, and the checkout was then restored to
`pong`:

| stack | round trip returns | verdict |
|---|---|---|
| merged (every gate at the time) | `pong` | green |
| base file alone | `STALE-IMAGE-BUILT-AT-T0` | the artifact that ships |

Deleting `app/jobs/tasks.py` from the image path is sharper still: the base file
alone fails its health wait with `ModuleNotFoundError: No module named
'app.jobs.tasks'`, while the merged stack stays healthy and answers from the
mount. A stale or missing wheel was invisible to the build gate, the round trip,
and all three health waits, and would have surfaced first in a deployment.

## Decision

**CI validates the image by running it, in one pass on the base Compose file
alone.** The `docker` job ends with `docker compose -f docker-compose.yml down -v
&& up -d`, followed by `wait_for_health.sh` naming every service the stack brings
up. (`api worker beat` when this was written; E0-14 added `mock-lms`, and the
list grows with the stack — `tests/unit/test_ci_health_gate.py` holds it.) No
override: no source mount, no published host port, no reload.

Every other dynamic check in the job keeps running the merged topology, and that
is half the decision rather than an accident. The merged stack is what a
developer runs, what `make up` produces, and what E0-02's criteria require — they
request `localhost:8000`, which exists only because the override publishes it.
So the job proves two things once each: the developer's topology works, and the
artifact works.

The Makefile's `docker-build` recipe carries the same pass in the same position,
under the existing rule that the workflow wins on drift.

## Alternatives rejected

**Stop merging the override for dynamic checks.** The simplest fix, and it would
have prevented this outright. Rejected because it inverts the loss: CI would then
never exercise the topology anyone actually runs, and the acceptance criteria
that request a published port could not run at all. Hot reload and published
ports are the reason §13 has an override in the first place.

**Validate the image statically** — assert on `COPY` lines, check a build target,
or list the files in the layer. Cheaper and it needs no daemon. Rejected because
it does not catch what actually happened: a stale wheel *installs correctly* and
*imports correctly*, and returns last week's answer. The defect lives in what the
code does, not in whether a file is present, and only running it asks that.

**A third Compose file describing a production-like stack.** Rejected because
§7.2 already makes the base file the production topology. A third file would mean
the thing CI validates is not the thing that ships, which is this defect with an
extra file to keep in step.

**Accept the gap and document it.** Live, and rejected by Todd. Documenting a
hole in the artifact check leaves it exactly as invisible at the moment it
matters, which is a release.

## Consequences

- **One extra `down -v` and `up` per run.** Measured at sixteen seconds on a
  developer workstation, most of it Postgres initialising from an empty volume;
  a CI runner will be slower. It publishes no host port, which is what keeps it
  cheap — and is why every check that talks to `localhost` must stay *above* it
  in the job.
- **Its health-wait argument list is the whole of what it asserts.** Every
  service is named because nothing depends on `worker`, `beat` or `mock-lms`, so
  a name dropped from that list would leave the pass green against a container
  that never started. `tests/unit/test_ci_health_gate.py` holds both halves: that
  every wait in the job names every service, and that the base-file-only start is
  itself followed by such a wait. The second was written because the first could
  not see a step that simply stopped waiting — an empty contribution to a
  collection that other steps keep non-empty — which would have reduced this
  pass to an unverified `up -d` with the suite green.
- **The two topologies can now drift apart, and this is what surfaces it.** A
  service that only works with the override in place fails this pass, which is
  the point; a setting that production needs and that has been put in the
  override fails it too.
- **It stays honest only while the base file remains the production topology**
  (§7.2) and the override remains development-only (§13). If a later ticket
  moves a production-necessary setting into the override, this pass fails, and
  that failure is the decision working rather than an obstacle.
- **`down -v` inside the pass reclaims both named volumes**, because both are
  declared in the base file and the project name is the same either way. The
  teardown loop that follows therefore starts from nothing, as it did before.
