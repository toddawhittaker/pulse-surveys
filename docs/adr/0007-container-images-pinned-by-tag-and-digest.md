# 0007 — Container images are pinned by tag and by digest

**Status:** Accepted
**Date:** 2026-08-12
**Tickets:** E0-02

## Context

E0-02 introduces the first images this project runs: a base image in
`backend/Dockerfile` and three registry images in `docker-compose.yml`.

`CLAUDE.md` says to pin dependency versions and forbids floating ranges, but it
was written about package managers and says nothing about image references.
[SPEC §7.2](../SPEC.md) writes the service list as `postgres:17` and `redis:7`,
which are version *constraints* rather than pins: a tag is a mutable pointer,
and `postgres:17` names a different image this month than it did last month. So
the spec is silent on granularity, and the choice is genuinely contestable —
bare major tag, exact patch tag, and immutable digest all have live advocates.

Two facts constrain the answer. [ADR 0005](0005-dependency-locking.md) already
settled the same question for Python and settled it at the strict end: a version
pin without a digest still trusts whatever the index serves under that version.
And Dependabot is what keeps any pin from rotting, so whatever form is chosen
has to be a form Dependabot can read and update.

## Decision

Every image reference names a tag at patch granularity **and** the digest that
tag resolved to when it was written:

```
postgres:17.10-bookworm@sha256:9b18b783...
```

That applies to `FROM` lines in `backend/Dockerfile` and `image:` lines in
`docker-compose.yml` alike. The digest is the multi-architecture index digest,
not a per-platform manifest digest, so the same reference resolves on arm64 and
on amd64.

`.github/dependabot.yml` gains two ecosystems to maintain them: `docker`, which
reads `FROM` lines under `/backend`, and `docker-compose`, which reads `image:`
lines at the root. Dependabot moves the tag and re-resolves the digest in the
same pull request, so the pair never disagrees. Postgres and Redis major
versions are in that file's `ignore` list, because §7.1 and §7.2 name those
majors and moving off one is a spec change.

## Alternatives rejected

**The bare tags §7.2 writes, `postgres:17` and `redis:7`.** Rejected because the
content is mutable and nothing records what actually ran. Two developers, or a
developer and a CI runner, can pull the same line a fortnight apart and get
different databases, and the only evidence is a bug that reproduces on one
machine. It is also the least maintainable option in practice, not the most:
Dependabot has no new tag to propose, because the tag never changes.

**An exact patch tag with no digest, `postgres:17.10-bookworm`.** The
respectable middle, and rejected on ADR 0005's own argument. A patch tag is
still a pointer — the publisher rebuilds it for base-OS security fixes — so it
constrains the version and not the artifact. Having paid one flag for hashes
over the whole Python closure, accepting "whatever the registry currently serves
under this tag" for the process that holds every student comment would be
inconsistent about the same risk.

**A digest alone, `postgres@sha256:...`.** Immutable, and rejected because it is
unmaintainable and unreadable. Dependabot needs a tag to know what a newer
version would be, so a digest-only reference is frozen until someone updates it
by hand, and no reviewer can tell from the diff whether a pull request moves
Postgres by a patch or by a major.

**Digest-pinning the base image but not the Compose images.** Rejected as the
worst of both: it is the same risk in both files, and a rule with an exception
nobody can state gets applied inconsistently within two tickets.

## Consequences

- **Updating an image is a deliberate pull request**, never an implicit
  consequence of pulling. That is the point, and it is also the cost: a
  developer cannot pick up a Postgres security fix by running `docker compose
  pull`.
- **Dependabot pull requests for images arrive weekly** and each one changes a
  long unreadable string. The tag beside the digest is what makes them
  reviewable, which is most of the reason the tag is kept.
- **A digest that is garbage-collected from the registry breaks the build
  outright**, rather than silently substituting a newer image. Loud, and the
  right failure — but the fix is a real edit, not a retry.
- **Two Dependabot ecosystems now cover two files.** If a future image reference
  lands somewhere neither ecosystem reads — a workflow `container:`, a
  Kubernetes manifest — it will be pinned and never updated, and nothing will
  say so. Adding the reference means adding the ecosystem in the same change.
- **One such reference already exists, and it has no ecosystem to add.** The
  `migration-drift` job in `.github/workflows/ci.yml` declares a `services.postgres.image`.
  Dependabot's `github-actions` ecosystem updates `uses:` references and
  explicitly not image references in a workflow, and the two ecosystems above
  read `backend/Dockerfile` and `docker-compose.yml` only, so nothing updates
  it. It is pinned to the identical reference as the `db` service and moves by
  hand together with it; the comment beside it says so, and this is the whole
  cost of the exemption. **An earlier version of this line claimed the drift
  would be "visible in a diff on both sides", and that was wrong**: the
  mechanism that will cause the drift is a Dependabot `docker-compose` pull
  request, which by construction changes `docker-compose.yml` and nothing else,
  so it shows one side only. Verified by mutation — the two references can be
  set to different digests with every gate green. The safety net is a test
  asserting the two are identical, comparing `services.postgres.image` in
  `.github/workflows/ci.yml` against `services.db.image` in
  `docker-compose.yml`. E0-04 activates that gate and is the natural place to reconsider
  whether the job should start the Compose `db` service instead, which would
  delete the second reference rather than maintain it.
- **This ADR does not govern the digests themselves.** They are values in the
  files that name them, and re-resolving one is not a decision.
