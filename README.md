# Pulse Surveys

An LTI 1.3 / LTI Advantage tool that runs a brief, standardized weekly feedback
cycle in every enrolled course.

1. Students answer five questions each week inside the LMS.
2. Participation credit passes back to the gradebook automatically.
3. Every Monday, instructors get a report: rating distributions, workload data,
   de-identified comments, and an AI-generated summary.
4. Instructors publish a response (with advisory AI coaching); students see the
   aggregate results and that response, which closes the loop.
5. Academic leadership — lead faculty, chair, dean, VPAA — sees roll-up views
   across their span of oversight.

The design goal is trust. Students have to believe their responses are
confidential, and instructors have to believe the data is fair. Most of the
non-obvious requirements in the spec exist to protect one of those two beliefs.

## Status

Early. The backend package exists — a FastAPI application factory, the
environment-driven settings object, and a health endpoint — and CI enforces
lint, typing, dependency audit, and license compatibility against it. There is
no database, no background worker, and no frontend yet.

## Local development

Python 3.13 or newer (SPEC §7.1), and a virtual environment of your own making.

```sh
python3 -m venv .venv && source .venv/bin/activate
make tools          # the pinned CI tools: ruff, mypy, pip-audit, pip-licenses, pip-tools
make install        # the locked dependencies, plus this package, editable
cp .env.example .env
uvicorn app.main:create_app --factory --reload
```

`GET http://localhost:8000/healthz` answers with the service name, the version,
and the environment it was configured with. The interactive API documentation
is at `/docs`.

Configuration is entirely environment-driven and documented in
[`.env.example`](.env.example), which a unit test keeps in sync with
`app.config.Settings` in both directions. Six variables have no default,
because a working default for a deployment-specific value is a
misconfiguration that starts successfully: the application refuses to start
without them and names the one it is missing.

```sh
make ci             # every gate, in the same order as CI
make lint           # ruff check + ruff format --check
make typecheck      # mypy, strict over app/services/
make test           # pytest with coverage
make lock           # recompile the lockfiles after editing dependencies
```

`make ci` is the same set of gates as `.github/workflows/ci.yml`, so a green run
here should mean a green run there. Where the two disagree, the workflow is
right and the `Makefile` is the bug.

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — product and technical specification.
- [`docs/DESIGN_BRIEF.md`](docs/DESIGN_BRIEF.md) — visual and interaction brief.
- [`design/`](design/) — exported prototype components, design tokens, and the
  data model for roles and reporting. This is the visual contract the frontend
  implements.
- [`CLAUDE.md`](CLAUDE.md) — the constraints that must not be violated,
  condensed from the two documents above.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the branch and pull request model.

## Deployment model

Single tenant, self-hosted.

## License

MIT. See [`LICENSE`](LICENSE).
