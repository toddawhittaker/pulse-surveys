"""Fixtures shared by the test suite, one module per subject.

The tests under `tests/unit/` for tickets E0-01 and E0-02 are written from those
tickets' acceptance criteria, not from the implementation. Where a criterion
needs a name the ticket does not spell — an environment variable, a JSON key —
the choice is made once, in a named constant, and marked as the test's choice so
it is cheap to change. Everything below inherits that rule.

Nothing lives here any more except this index. The fixtures are in
`tests/fixtures/`, loaded as plugins by the tuple below, and a test still asks
for one by name — there is nothing to import. They are **not** split into
per-directory `conftest.py` files, because they cross the unit and integration
boundary: `metadata_tables` is asked for by both.

  - `fixtures/repo.py` — the repository's own files: `.env.example`, the two
    Compose files, the CI workflow, and the Celery application lookup.
  - `fixtures/database.py` — E0-04: a testcontainers Postgres on the image the
    stack deploys, production's three roles, `alembic upgrade head` once per
    session, and a transaction-rollback session per test.
  - `fixtures/section_codes.py` — E0-07's section-code service, discovered
    rather than named.
  - `fixtures/lti_platform.py` — where the mock LTI platform lives, and the JWS,
    HTML-form and URL helpers both mocks read a response with.
  - `fixtures/app_imports.py` — importing a package called `app` when three of
    them answer to that name. Every `sys.meta_path` manipulation is there.
  - `fixtures/lti_services.py` — E0-14's `mock_platform` and the LTI Advantage
    services E0-15 reaches through a launch's own claims; since E1-11's fix round
    it also holds the access token the mock's NRPS route requires, which is why
    every roster read in the suite goes through `roster_get`.
  - `fixtures/supervision.py` — E0-09's assignment graph and the row-seeding
    helper, with the two counters that keep seeded values unique.
  - `fixtures/authz_data.py` — E0-10's committed rows and Care environment,
    E0-26's `pulse_care` connections, and E0-11's `authz` chokepoint and
    application-role session.
  - `fixtures/mock_idp.py` — E0-16's mock OIDC provider, driven the way a client
    drives one.
  - `fixtures/seed.py` — E0-17: `scripts/seed.py` run as a program, against a
    database of its own.
  - `fixtures/doors.py` — E0-18 PR 1: this project's own two doors, built here
    and driven in process against the mocks.
  - `fixtures/suite_keys.py` — the key set this suite signs its own tokens with.
  - `fixtures/client_credentials.py` — E1-06: the tool's key set, the assertions a
    client-credentials grant is asked with, and the seam a mock platform fetches
    that key set through.
  - `fixtures/provisioning.py` — E1-10: the launch-time writer, reached by
    discovery; the committed prefix, term and start-letter map a launch resolves
    against; and a launch's claims as a value for the cases nothing mints.
  - `fixtures/roster_sync.py` — E1-11: the roster sync reached by discovery, the
    `requests` seam its service calls travel over and are recorded on, a
    membership container a test composes, and the registered platform and section
    a sync starts from.
  - `fixtures/web_identity.py` — E1-12: the `person`, `user` and
    `web_login_subject` rows a door resolves a subject through, seeded committed,
    and the session claims a landing carries them back in.
  - `fixtures/landing.py` — E1-13: the names the assignment-derived landing is
    settled under, one `enrollment` row with the window the caller chose, and the
    rows a launch-driving suite needs before its subject can land at all.
  - `fixtures/celery_broker.py` — E0-03's real Redis on the image the stack
    deploys, moved here in E2-04 when a second module needed a broker.
  - `fixtures/clock.py` — E2-04: the `clock_override` row a test chose the values
    of, committed or not, and `Settings` built under an environment the test named.
  - `fixtures/survey_windows.py` — E2-06: SPEC §3.1's Fall 2026 window calendar
    written out by hand as UTC instants, and the term, weeks and cohort sections
    a derivation is run over.
  - `fixtures/mock_ai.py` — E2-07's mock AI provider, in process and on a loopback
    socket, plus the non-mock provider a deployment-environment test needs.
  - `fixtures/ai_tasks.py` — E2-07: the comment-validity task, found rather than
    named, and ADR 0056's failure classes looked up by name.

`pytest_plugins` is spelled `fixtures.<name>` rather than `tests.fixtures.<name>`
because pytest puts `tests/` on `sys.path` when it loads this file: there is no
`tests/__init__.py`, so this directory is the import root for everything under
it.
"""

pytest_plugins = (
    "fixtures.repo",
    "fixtures.database",
    "fixtures.section_codes",
    "fixtures.lti_platform",
    "fixtures.app_imports",
    "fixtures.lti_services",
    "fixtures.supervision",
    "fixtures.authz_data",
    "fixtures.mock_idp",
    "fixtures.seed",
    "fixtures.doors",
    "fixtures.suite_keys",
    "fixtures.client_credentials",
    "fixtures.provisioning",
    "fixtures.roster_sync",
    "fixtures.web_identity",
    "fixtures.landing",
    "fixtures.celery_broker",
    "fixtures.clock",
    "fixtures.survey_windows",
    "fixtures.mock_ai",
    "fixtures.ai_tasks",
)
