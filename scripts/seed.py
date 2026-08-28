#!/usr/bin/env python3
"""The demo institution every later epic develops against — ticket E0-17, SPEC §13.

`make seed` runs this file. It loads a small, deliberately awkward institution:
two colleges, a department that groups three prefixes, courses across all five of
SPEC §8's level bands, a Fall 2026 term carrying §2.2's start-letter map, sections
spanning sixteen start positions and seven lengths in both modalities, and a
people graph holding the two shapes that break naive purview code — SPEC §2.1's
assistant dean, and a person wearing two hats.

**Nothing here is survey data.** No responses, no comments, no classifications:
those arrive in E2 and E4. This seeds structure only.

## What it connects as, and why not the obvious thing

The address comes from `DATABASE_URL` and the identity from `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD`, which is exactly what `backend/migrations/env.py` does
and for exactly the reason ADR 0012 gives. `DATABASE_URL` names `pulse_app`,
which holds `CONNECT` plus `SELECT` on three read views and no `INSERT` on
anything (ADR 0009, E0-10, E0-11) — a loader wired to it fails on its first
write, and the repair that suggests itself, granting the application role
`INSERT`, is the thing ADR 0009 exists to forbid.

**This module must never import `app.db`.** That module builds an engine out of a
whole `Settings()` when imported, as the application role, so importing it here
would open a connection this script may not use and demand five configuration
variables that say nothing about seeding.

## Two things this script deliberately does not do

**It does not disable triggers.** `SET session_replication_role = replica` turns
off E0-09's supervision trigger for the whole session with no `ALTER TABLE`, no
ownership check and nothing in the schema to notice — ADR 0027 measured a two-row
reporting cycle stored cleanly under it, and the parameter is superuser-only, so
this script is one of the few places in the system that could reach for it. It
does not. Every row below goes in through the same guards the People editor and
the roster sync will meet, and the seed is a few hundred rows in one transaction,
so there is no speed here worth buying with an unpoliced supervision graph. **If
you are about to add it as an optimisation: don't** — and if you must, this file
then owes a check afterwards that the graph it wrote is still acyclic and still
free of edges touching a `CARE` assignment, because with the trigger off nothing
else in the system will ever look.

**It registers the mock LMS, and that row is the one thing written here that a
deployment must never receive.** ADR 0038 argues that `mock-lms` is safe in the
base Compose file because a tool trusts it only if a row in `lti_platform` says
so. Until E0-31 that argument rested on no such row existing anywhere in this
repository. It now rests on the `ENVIRONMENT` guard described below, which ADR
0038 has been amended to name and ADR 0068 records; `seed_mock_platform`
evaluates that guard at the write itself, so the row cannot be reached by a
caller who arrived some other way than through `main`.

**The demo institution's own people belong to a different platform**, a fictional
one at an RFC 2606 `.invalid` address that resolves nowhere and that nobody holds
a signing key for (ADR 0065). Nobody launches as them. The mock registration
carries no `user` rows at all: it exists so that E0-18 can drive a real launch
past the registration boundary, and provisioning the user a launch resolves to is
E1's (SPEC §14.3, "automatic section/enrollment provisioning from launch").

## Where it will run, and where it refuses to

Only where `ENVIRONMENT` is `development`. E0-17's security review asks that the
seed "cannot run against a non-development environment", and this is a script that
writes people, an institution and a term into whatever database it is pointed at,
as a superuser. ADR 0063 records why the check is on that variable and why it is
an equality rather than a deny-list.

Since E0-31 that guard carries a second load. It is now the only thing standing
between a deployment and a registration that would make it trust the mock
platform, so it is checked twice: once in `main` before a connection is opened,
and once inside `seed_mock_platform` at the row itself.

Since E1-05 it carries a third, on the same terms. `seed_tool_signing_key`
generates the private half of this tool's own identity, and a key created in a
production database by a script nobody meant to run there sits outside whatever
key management that deployment has. It checks the guard at its own write for the
same structural reason, and E1-05's address chokepoint reads the environment a
third time at each registration — so the same variable is what admits every row
here that a deployment must never receive.

## Running it twice

Every row is matched on the natural key the schema already gives it — an
institution's name, a course's `(prefix, number)`, an assignment's `(person, role,
scope node)` — and re-used where it is found. So a second run over a database only
this seed has written to changes nothing, and a run interrupted half way finishes
on the next one. ADR 0064 records why matching rather than reloading.

**It will not share a database with a real institution.** Every key above is
either scoped to a row this seed created or is a value this file invented, with
one exception the schema forces: `prefix.code` is unique across the whole table
rather than per institution (ADR 0017), and `MATH` is a name a real institution
uses too. Matching there would adopt a real prefix rather than create one, and
carry every course under it along — so `seed_containment` refuses instead, naming
the code and the department that holds it. ADR 0064 carries the measurement.

**`Institution.name` relies on the second half of that rule, and only on it.**
It is matched unscoped — nothing sits above the root to scope it to — so what
keeps the match safe is that `Pulse Demo University` is a value this file
invented rather than a name a real institution uses. That is the whole of the
protection, and it is worth saying where the loader is edited: a collision would
be **adopted** rather than refused, and the blast radius would be larger than the
`prefix.code` case, because three role assignments are scoped to
`("institution", INSTITUTION_NAME)` and demo leadership would gain purview over
the whole of somebody's real tree. Changing that name to something plausible —
a real university's — is the way to make this reachable.

The refusal described next does not cover that case. It refuses an institution
carrying a **different** name; one carrying this name is this seed's own row from
an earlier run, which is what keeps a second run idempotent, and there is nothing
in the database that could tell the two apart.

**Since E0-22 it refuses on the institution first.** SPEC §8 says a deployment
serves exactly one institution and `uq_institution_one_row` holds that, so a
database already holding somebody else's institution has no room for this one.
`seed_containment` checks for a standing institution before it writes anything
and refuses in one sentence; without that check the index refuses the `INSERT`
instead, and an `IntegrityError` is not a `SeedError`, so the operator would meet
a traceback for a decision this file makes on purpose. The prefix guard still
does its job — inside the one institution, where a real department can hold
`MATH` and this file would otherwise adopt it.
"""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.config import DEVELOPMENT_ENVIRONMENT
from app.models.base import Base
from app.models.identity import (
    AssignmentRole,
    LeadFacultyMapping,
    Person,
    RoleAssignment,
    User,
    UserIdentity,
    WebLoginSubject,
)
from app.models.lti import (
    LtiDeployment,
    LtiPlatform,
    ToolSigningKey,
    refuse_invalid_registration_addresses,
)
from app.models.org import College, Course, Department, Institution, Prefix, Section
from app.models.term import StartLetterMap, Term, Week, week_rows_for_term
from app.services.section_codes import apply_section_code

# The repository root, from `scripts/seed.py`. Named rather than searched for,
# for the reason `backend/migrations/env.py` gives about `find_dotenv()`: a
# script that reads a different `.env` depending on where it was invoked from is
# the kind of thing nobody notices until two databases disagree.
REPO_ROOT = Path(__file__).resolve().parents[1]

# The developer's local configuration file, and the fourth reader of it (ADR 0008
# as amended). A default rather than a constant everything reaches for: every
# function below is handed the mapping it reads, so this name is used exactly
# once, by `main`.
DOTENV_PATH = REPO_ROOT / ".env"

# The environment name this script will run under, and the only one, imported
# above from the module that declares it (E0-37 item 2). **Free-form, and not by
# SPEC §6.3** — that section is three bullets on the admin console's
# configuration surface and names no environment variable, and `ENVIRONMENT`
# appears nowhere in the spec at all. `.env.example` documents the vocabulary,
# naming `development`, `staging` and `production` as conventions and enforcing
# none, so the check below is a comparison against a convention rather than
# against an enumeration `Settings` enforces.
#
# It used to be spelled here as well as in `app/db.py`, each file internally
# consistent and nothing anywhere comparing the two — `docs/MISTAKES.md` entry 3.
# There is one of it now, beside the `environment` field it describes.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# Where the database is, and who is allowed to write this much of it. The same
# three names `backend/migrations/env.py` reads, and deliberately no fourth of
# this script's own: a name only this file read could not earn an `.env.example`
# entry (ADR 0008), and `tests/unit/test_env_example_sync.py` would say so.
ADDRESS_VARIABLE = "DATABASE_URL"
IDENTITY_VARIABLES = ("DB_SUPERUSER", "DB_SUPERUSER_PASSWORD")

# One mapped row, whichever table it belongs to — what `upsert` below is given and
# what it hands back. A `TypeVar` rather than PEP 695's `def upsert[RowT: Base]`,
# which the pinned mypy 1.11.2 refuses with "PEP 695 generics are not yet
# supported"; the two spellings mean the same thing and this is the one the gate
# accepts.
RowT = TypeVar("RowT", bound=Base)


class SeedError(Exception):
    """The seed will not run, or cannot finish, and says which in one sentence.

    Raised for every condition this script refuses on purpose — a deployed
    environment, a missing variable, a calendar that does not fit its term, a
    database already holding another institution — so that `main` can print one
    line instead of a traceback. Anything else that goes wrong keeps its
    traceback, because it is a defect rather than a decision.

    **That means a rule the database enforces usually needs a guard here too.**
    A constraint refusing a row raises `IntegrityError`, which is not a
    `SeedError`, so it escapes `main` and the operator meets a stack trace for a
    condition this file decided about on purpose. Both keys in `seed_containment`
    that are not scoped to a row this seed created — `prefix.code` and the
    institution itself — are checked before the write for exactly that reason.
    """


# ---------------------------------------------------------------------------
# The demo institution, as data.
#
# Every name below is invented and every one says what its holder does rather
# than who they are: "Demo Chair of Mathematics" and not a plausible human name.
# E0-17's last criterion is that "no name resembles a real person at a real
# institution", and a name that describes a role cannot. ADR 0066 records the
# choice, including why it disagrees with `design/`.
# ---------------------------------------------------------------------------

INSTITUTION_NAME = "Pulse Demo University"

# SPEC §2.2's Fall 2026 reference calendar: eighteen weeks from Monday 17 August
# 2026, ending Sunday 20 December. The end date is the term's last day, inclusive,
# which is the convention `app.services.section_codes` derives every section
# against — §2.2's own `Q` cohort runs twelve weeks from 9/28 and ends exactly on
# the term's last day, which is what settles it.
TERM_NAME = "Fall 2026"
TERM_START = date(2026, 8, 17)
TERM_END = date(2026, 12, 20)
TERM_LENGTH_WEEKS = 18

# §2.2's start-letter map, as `(position, length in weeks, first day)`.
#
# **The lengths and three of the dates are the spec's.** "12-week U/R/Q starting
# 8/17, 9/7, 9/28; 6-week E/F/H; 8-week X/Y/Z; 10-week S/T; 15-week V/D; 16-week
# K; 3-week sections numbered 2-7." Those three dates are the only ones §2.2
# writes down.
#
# **The other seventeen dates are this file's**, chosen so that each family of
# equal-length cohorts starts at the term's first day and then staggers — which is
# what makes §2.2's cohort selector worth having in development — and so that
# every cohort ends on or before the term's last day. `_check_calendar_fits`
# below re-derives that rather than trusting this comment.
#
# A start position is one character and is not always a letter: §2.2 numbers the
# 3-week cohorts 2 through 7, which is why the schema's check is `^[A-Z0-9]$`.
START_LETTER_MAP: tuple[tuple[str, int, date], ...] = (
    ("U", 12, date(2026, 8, 17)),
    ("R", 12, date(2026, 9, 7)),
    ("Q", 12, date(2026, 9, 28)),
    ("E", 6, date(2026, 8, 17)),
    ("F", 6, date(2026, 9, 28)),
    ("H", 6, date(2026, 11, 9)),
    ("X", 8, date(2026, 8, 17)),
    ("Y", 8, date(2026, 9, 28)),
    ("Z", 8, date(2026, 10, 26)),
    ("S", 10, date(2026, 8, 17)),
    ("T", 10, date(2026, 10, 12)),
    ("V", 15, date(2026, 8, 17)),
    ("D", 15, date(2026, 9, 7)),
    ("K", 16, date(2026, 8, 17)),
    ("2", 3, date(2026, 8, 17)),
    ("3", 3, date(2026, 9, 7)),
    ("4", 3, date(2026, 9, 28)),
    ("5", 3, date(2026, 10, 19)),
    ("6", 3, date(2026, 11, 9)),
    ("7", 3, date(2026, 11, 30)),
)

# The registration the demo people belong to. **Not the mock platform**, and the
# module docstring says why at length. Every part of it is unresolvable by
# construction: RFC 2606 reserves `.invalid` precisely so that a fixture cannot
# name something somebody owns, and no key exists anywhere that would let a launch
# claiming this issuer verify.
DEMO_PLATFORM_ISSUER = "https://lms.pulse-demo.invalid"
DEMO_PLATFORM_CLIENT_ID = "pulse-demo-tool"
DEMO_PLATFORM_JWKS_URL = "https://lms.pulse-demo.invalid/.well-known/jwks.json"
DEMO_PLATFORM_DEPLOYMENT_ID = "pulse-demo-deployment-1"

# The in-repo mock platform, registered so that E0-18 can drive a real launch
# (E0-31 item 1). **Nothing about this one is fictional**: these are the literal
# values `docker-compose.yml` gives the `mock-lms` service, the host is a name
# that resolves on the Compose network, and the key set behind the JWKS URL is
# the one that signs the launches it offers. Writing this row is what makes a
# Pulse trust that platform, so `seed_mock_platform` below checks the environment
# guard before it does.
#
# Copied rather than read at runtime, because this script runs where the files
# these come from may not be, and asserted equal to them by
# `test_the_seeded_mock_registration_is_the_registration_compose_configures` —
# which is the "or a test asserts the two copies agree" half of the rule
# `docs/MISTAKES.md` entry 13 carries.
#
# **Two sources, not one.** The issuer and the client ID are Compose literals
# (ADR 0037). The JWKS path is `mock-lms/app/config.py`'s `JWKS_PATH`, which is
# not in the Compose environment at all because the platform composes that URL
# from its own issuer — so a drift guard whose whole inventory was the Compose
# `environment:` block would report clean over it forever. The test imports the
# mock's configuration module for exactly that value. `docs/MISTAKES.md` entry 35
# is the entry about a guard that cannot see the currency a value is held in, and
# the E0-31 security review found this instance of it.
#
# The scheme is `http`, deliberately and unavoidably: this is a container talking
# to a container on the Compose network with no certificate anywhere. Nothing
# reads the column yet. E0-24 item 1 has E1 constrain what a legitimate
# `jwks_url` looks like, and this row is the one committed value any such rule
# has to admit — see that ticket.
MOCK_PLATFORM_ISSUER = "http://mock-lms:8000"
MOCK_PLATFORM_CLIENT_ID = "mock-lms-client"
MOCK_PLATFORM_DEPLOYMENT_ID = "mock-lms-deployment-1"
MOCK_PLATFORM_JWKS_URL = f"{MOCK_PLATFORM_ISSUER}/.well-known/jwks.json"

# **A third source, and the only value here on the browser horizon** (E1-05,
# ADR 0075's per-value rule). Every constant above is what one container reaches
# another by; this one is a string handed to a *browser* on the developer's own
# machine, which cannot resolve a Compose service name at all. The mock's own
# `/registration` document publishes `{issuer}/oidc/authorize` — right for a
# container, wrong for this column — so copying that value here is the mistake
# `test_the_seeded_mock_registration_is_the_registration_compose_configures`
# asserts against, one half at a time: the path against the platform's own
# `AUTHORIZATION_PATH`, the origin against the host port
# `docker-compose.override.yml` publishes.
MOCK_PLATFORM_BROWSER_ORIGIN = "http://localhost:8080"
MOCK_PLATFORM_AUTHORIZATION_ENDPOINT = f"{MOCK_PLATFORM_BROWSER_ORIGIN}/oidc/authorize"

# **Where the mock issues access tokens** (E1-06, `mock-lms/app/config.py`'s
# `TOKEN_PATH`). This column was NULL until the endpoint existed, because a
# registration naming an address that answers nothing is the record the
# platform's own discovery document refuses to be; the carried entry is why the
# two moved in one change, and this is that change.
#
# **On the issuer's horizon, not the browser's**, which is what makes it differ
# from its neighbour two constants up. The authorization endpoint is a string a
# developer's *browser* resolves, so it carries `localhost` and a published host
# port; this one is fetched by the `api` container over the Compose network,
# exactly as `jwks_url` is. The two are right in two different currencies, and
# copying either into the other is a registration that fails at the point of use.
# ADR 0075's per-value horizon rule, and ADR 0081 rule 4 refuses link-local on
# precisely these two columns for the same reason.
MOCK_PLATFORM_AUTH_TOKEN_URL = f"{MOCK_PLATFORM_ISSUER}/token"

# **Which identity provider a seeded web login is linked to** (E1-12). Read from
# the resolved configuration rather than written down, with the Compose default
# behind it: the linkage's issuer has to be the exact string a verified `id_token`
# states as `iss`, and the tool compares that against `OIDC_ISSUER`. A copy here
# that disagreed with the deployment's setting would leave every seeded persona's
# web login landing on the no-account page, with nothing saying why. Not a new
# variable — `.env.example` has carried this one since E1-09.
#
# Trailing slash stripped and whitespace trimmed the way `mock-idp/app/config.py`
# does it: OIDC Discovery 1.0 §4.3 compares an issuer as an origin, so
# `http://mock-idp:8000/` and `http://mock-idp:8000` are one issuer and would be
# two linkage rows.
MOCK_IDP_ISSUER_VARIABLE = "OIDC_ISSUER"
MOCK_IDP_ISSUER = "http://mock-idp:8000"

# The size of the tool's own RSA key (E1-05). 2048 is the floor every conformant
# LTI 1.3 platform accepts for an RS256 assertion, and it is the number to raise
# rather than a number to tune: a shorter key loads and signs exactly like a long
# one and is refused at the platform, which is a failure against a real LMS and
# nowhere before it.
TOOL_SIGNING_KEY_BITS = 2048

# Where a demo person's address points: nowhere. RFC 2606 reserves `.invalid` for
# exactly this, and a demo seed is a thing that gets copied into a staging
# environment by somebody in a hurry. `mock-lms/app/seed.py` makes the same choice
# with the same suffix.
MAIL_DOMAIN = "pulse-demo.invalid"


@dataclass(frozen=True, slots=True)
class DemoCollege:
    """One college, and the departments under it."""

    name: str
    departments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DemoPrefix:
    """One course prefix, and the department that groups it.

    `prefix.code` is unique across the whole table (ADR 0017), so these are the
    institution's prefixes rather than one college's.
    """

    code: str
    department: str


@dataclass(frozen=True, slots=True)
class DemoCourse:
    """One course. `number` is text, and SPEC §8's bands derive the level from it.

    `title` is not optional: `course.lms_title` is `NOT NULL` (E0-05, kept
    deliberately — see E0-21), so a course inserted without one fails at write
    time.
    """

    prefix: str
    number: str
    title: str

    @property
    def handle(self) -> str:
        """How the rest of this file names the course: `MATH 210`."""
        return f"{self.prefix} {self.number}"


@dataclass(frozen=True, slots=True)
class DemoSection:
    """One section of one course, named by the code its calendar derives from."""

    course: str
    code: str

    @property
    def handle(self) -> str:
        """How the rest of this file names the section: `MATH 210 U1WW`."""
        return f"{self.course} {self.code}"


@dataclass(frozen=True, slots=True)
class DemoPerson:
    """One person in the demo institution's people graph.

    `category` is free text in the schema (SPEC §2.1 names the field and never
    enumerates its values), so these three words are this file's vocabulary and
    nothing reads them.
    """

    key: str
    name: str
    category: str


@dataclass(frozen=True, slots=True)
class DemoAssignment:
    """One grant, and the assignment it reports to.

    `key` is this file's handle for the row, and `reports_to` names another
    handle — never a person and never an org node, which is SPEC §2.1's rule in
    bold and the whole reason a two-hat person is expressible at all.

    `scope` is the containment level and the handle of the node, resolved against
    what has already been seeded. Which level is legal for which role is not this
    file's choice: `SCOPE_GRAIN_RULE` in `app/models/identity.py` refuses the
    others.
    """

    key: str
    person: str
    role: AssignmentRole
    scope: tuple[str, str]
    reports_to: str | None


# Two colleges, five departments. Two is the minimum that makes a dean's purview
# and the VP's different sets — with one, every scoping bug in E9 looks like a
# correct answer.
COLLEGES: tuple[DemoCollege, ...] = (
    DemoCollege(
        name="College of Arts and Sciences",
        departments=("Mathematics", "Biology", "Psychology"),
    ),
    DemoCollege(
        name="College of Business and Technology",
        departments=("Computer Science", "Business Administration"),
    ),
)

# SPEC §2.1's awkward case, seeded on purpose: "Department (groups one or more
# prefixes: Math may hold MATH, STAT, MIS)". Where every department holds exactly
# one prefix, a roll-up that aggregates by prefix and one that aggregates by
# department agree on every row, and the first is wrong.
PREFIXES: tuple[DemoPrefix, ...] = (
    DemoPrefix(code="MATH", department="Mathematics"),
    DemoPrefix(code="STAT", department="Mathematics"),
    DemoPrefix(code="MIS", department="Mathematics"),
    DemoPrefix(code="BIOL", department="Biology"),
    DemoPrefix(code="PSYC", department="Psychology"),
    DemoPrefix(code="CSCI", department="Computer Science"),
    DemoPrefix(code="BUSA", department="Business Administration"),
)

# **These numbers are chosen against SPEC §8 and disagree with every screenshot in
# `design/`.** §8's bands are three digits in `000`-`799` — DEV `000`-`099`, UG
# `100`-`499`, UGGR `500`-`599`, GR `600`-`799` — and four digits in `8000`-`9999`
# for DR. All 27 distinct course numbers written across `design/` are four digits
# below `8000`, which is the gap between the two bands, so not one of them can be
# stored: `course.level` is generated from the number and is `NOT NULL`, so a
# number in no band is refused at write time rather than stored without a level.
# E0-17's ticket says to expect that disagreement and to raise it rather than
# quietly reconciling either side, and its pull request does.
#
# All five levels appear, because §5.1 compares a section only against others of
# the same length *and* level: a level with no seeded course is a comparison set
# nobody can build a fixture for.
COURSES: tuple[DemoCourse, ...] = (
    DemoCourse("MATH", "040", "Foundations of Algebra"),
    DemoCourse("MATH", "210", "Calculus I"),
    DemoCourse("MATH", "505", "Applied Linear Algebra"),
    DemoCourse("STAT", "250", "Introduction to Statistics"),
    DemoCourse("STAT", "610", "Statistical Inference"),
    DemoCourse("MIS", "320", "Database Systems"),
    DemoCourse("BIOL", "101", "Principles of Biology"),
    DemoCourse("BIOL", "8200", "Doctoral Research Seminar in Biology"),
    DemoCourse("PSYC", "110", "Introduction to Psychology"),
    DemoCourse("PSYC", "545", "Cognitive Neuroscience"),
    DemoCourse("CSCI", "060", "Computer Literacy Workshop"),
    DemoCourse("CSCI", "240", "Data Structures"),
    DemoCourse("CSCI", "720", "Distributed Systems"),
    DemoCourse("BUSA", "300", "Principles of Management"),
    DemoCourse("BUSA", "8400", "Doctoral Colloquium in Business"),
)

# Sixteen of the twenty start positions, seven lengths, both modalities. §2.2
# plots aggregate pages "with one line per start cohort and a cohort selector",
# and a demo institution with one cohort leaves that screen with nothing to select
# between.
SECTIONS: tuple[DemoSection, ...] = (
    DemoSection("MATH 210", "U1WW"),
    DemoSection("MATH 210", "R1FF"),
    DemoSection("MATH 040", "E1WW"),
    DemoSection("MATH 505", "V1FF"),
    DemoSection("STAT 250", "Q1WW"),
    DemoSection("STAT 610", "T1FF"),
    DemoSection("MIS 320", "X1WW"),
    DemoSection("BIOL 101", "X1FF"),
    DemoSection("BIOL 101", "21WW"),
    DemoSection("BIOL 8200", "K1WW"),
    DemoSection("PSYC 110", "S1FF"),
    DemoSection("PSYC 110", "U2WW"),
    DemoSection("PSYC 545", "H1WW"),
    DemoSection("CSCI 060", "31FF"),
    DemoSection("CSCI 240", "D1WW"),
    DemoSection("CSCI 720", "Y1FF"),
    DemoSection("BUSA 300", "F1WW"),
    DemoSection("BUSA 8400", "Z1FF"),
)

PEOPLE: tuple[DemoPerson, ...] = (
    DemoPerson("vp", "Demo VP of Academics", "Leadership"),
    DemoPerson("dean-arts-sciences", "Demo Dean of Arts and Sciences", "Leadership"),
    DemoPerson("dean-business-technology", "Demo Dean of Business and Technology", "Leadership"),
    DemoPerson(
        "assistant-dean-arts-sciences",
        "Demo Assistant Dean of Arts and Sciences",
        "Leadership",
    ),
    DemoPerson("chair-mathematics", "Demo Chair of Mathematics", "Faculty"),
    DemoPerson("chair-biology", "Demo Chair of Biology", "Faculty"),
    DemoPerson("chair-psychology", "Demo Chair of Psychology", "Faculty"),
    DemoPerson("chair-computer-science", "Demo Chair of Computer Science", "Faculty"),
    DemoPerson("chair-business-administration", "Demo Chair of Business Administration", "Faculty"),
    DemoPerson("lead-mathematics-one", "Demo Lead Faculty for Calculus", "Faculty"),
    DemoPerson(
        "lead-mathematics-two", "Demo Lead Faculty for Linear Algebra and Statistics", "Faculty"
    ),
    DemoPerson("lead-biology", "Demo Lead Faculty for Principles of Biology", "Faculty"),
    DemoPerson("lead-computer-science", "Demo Lead Faculty for Data Structures", "Faculty"),
    DemoPerson("instructor-one", "Demo Instructor of Calculus I", "Faculty"),
    DemoPerson("instructor-two", "Demo Instructor of Principles of Biology", "Faculty"),
    DemoPerson("instructor-three", "Demo Instructor of the Biology Doctoral Seminar", "Faculty"),
    DemoPerson("care", "Demo Care Team Member", "Staff"),
    DemoPerson("admin", "Demo Administrator", "Staff"),
)

# The people graph. Three shapes here are seeded because they break naive purview
# code and are invisible in a tidy institution:
#
# **The assistant dean** (SPEC §2.1's worked example). Scoped to the *same college
# node as the dean* — "authority comes from the supervision graph, not the scope"
# — with two chairs reporting through them and a third reporting straight to the
# dean. A college where every chair reports through the assistant dean is a chain
# rather than an insertion, and a roll-up that ignored the assistant dean entirely
# would produce the same numbers over it. The assistant dean also *leads a course
# in the one department they do not supervise*, which is what makes §2.1's
# sentence true of these rows: "own led courses union every supervised chair's
# department — a set no single containment node holds".
#
# **The two-hat person.** The chair of Mathematics also leads MATH 040, and that
# lead assignment reports to their own chair assignment — §2.1 calls that "legal
# and expected", and it is only expressible because `reports_to` joins assignments
# rather than people.
#
# **Two sibling leads in one prefix**, so SPEC §4.1 invariant 2 is visible in
# development: with one lead per prefix, a purview that handed over the whole
# prefix would look right on every screen.
#
# Every edge climbs SPEC §2.1's role rank, which E0-11 put in E0-09's trigger
# (ADR 0044): `INSTRUCTOR` 1, `LEAD_FACULTY` 2, `CHAIR` 3, `ASSISTANT_DEAN` 4,
# `DEAN` 5, `VP_ACADEMICS` 6. `CARE` and `ADMIN` hold no rank and carry no edge at
# either end — §2.1 puts Care outside the graph entirely, and §2 gives Admin no
# reporting access at all.
ASSIGNMENTS: tuple[DemoAssignment, ...] = (
    DemoAssignment(
        key="vp",
        person="vp",
        role=AssignmentRole.VP_ACADEMICS,
        scope=("institution", INSTITUTION_NAME),
        reports_to=None,
    ),
    DemoAssignment(
        key="dean-arts-sciences",
        person="dean-arts-sciences",
        role=AssignmentRole.DEAN,
        scope=("college", "College of Arts and Sciences"),
        reports_to="vp",
    ),
    DemoAssignment(
        key="dean-business-technology",
        person="dean-business-technology",
        role=AssignmentRole.DEAN,
        scope=("college", "College of Business and Technology"),
        reports_to="vp",
    ),
    DemoAssignment(
        key="assistant-dean-arts-sciences",
        person="assistant-dean-arts-sciences",
        role=AssignmentRole.ASSISTANT_DEAN,
        scope=("college", "College of Arts and Sciences"),
        reports_to="dean-arts-sciences",
    ),
    DemoAssignment(
        key="chair-mathematics",
        person="chair-mathematics",
        role=AssignmentRole.CHAIR,
        scope=("department", "Mathematics"),
        reports_to="assistant-dean-arts-sciences",
    ),
    DemoAssignment(
        key="chair-biology",
        person="chair-biology",
        role=AssignmentRole.CHAIR,
        scope=("department", "Biology"),
        reports_to="assistant-dean-arts-sciences",
    ),
    # The chair who reports straight to the dean. Without this row the college is
    # a chain, and §2.1's example stops being an example.
    DemoAssignment(
        key="chair-psychology",
        person="chair-psychology",
        role=AssignmentRole.CHAIR,
        scope=("department", "Psychology"),
        reports_to="dean-arts-sciences",
    ),
    DemoAssignment(
        key="chair-computer-science",
        person="chair-computer-science",
        role=AssignmentRole.CHAIR,
        scope=("department", "Computer Science"),
        reports_to="dean-business-technology",
    ),
    DemoAssignment(
        key="chair-business-administration",
        person="chair-business-administration",
        role=AssignmentRole.CHAIR,
        scope=("department", "Business Administration"),
        reports_to="dean-business-technology",
    ),
    # The assistant dean's own led course, in Psychology — the one department in
    # their college whose chair they do not supervise.
    DemoAssignment(
        key="lead-psyc-110",
        person="assistant-dean-arts-sciences",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "PSYC 110"),
        reports_to="chair-psychology",
    ),
    # The second hat: the chair of Mathematics leading a course, reporting to
    # their own chair assignment.
    DemoAssignment(
        key="lead-math-040",
        person="chair-mathematics",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "MATH 040"),
        reports_to="chair-mathematics",
    ),
    DemoAssignment(
        key="lead-math-210",
        person="lead-mathematics-one",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "MATH 210"),
        reports_to="chair-mathematics",
    ),
    DemoAssignment(
        key="lead-math-505",
        person="lead-mathematics-two",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "MATH 505"),
        reports_to="chair-mathematics",
    ),
    # The same lead across a second prefix in the same department: §2.1's "a
    # lead's practical span may cross prefixes and departments".
    DemoAssignment(
        key="lead-stat-250",
        person="lead-mathematics-two",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "STAT 250"),
        reports_to="chair-mathematics",
    ),
    DemoAssignment(
        key="lead-biol-101",
        person="lead-biology",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "BIOL 101"),
        reports_to="chair-biology",
    ),
    DemoAssignment(
        key="lead-csci-240",
        person="lead-computer-science",
        role=AssignmentRole.LEAD_FACULTY,
        scope=("course", "CSCI 240"),
        reports_to="chair-computer-science",
    ),
    DemoAssignment(
        key="instructor-math-210-u1ww",
        person="instructor-one",
        role=AssignmentRole.INSTRUCTOR,
        scope=("section", "MATH 210 U1WW"),
        reports_to="lead-math-210",
    ),
    DemoAssignment(
        key="instructor-biol-101-x1ff",
        person="instructor-two",
        role=AssignmentRole.INSTRUCTOR,
        scope=("section", "BIOL 101 X1FF"),
        reports_to="lead-biol-101",
    ),
    # The fall-to-chair path, as rows: BIOL 8200 has no lead-faculty mapping, so
    # its instructor reports to the department chair (SPEC §2.1: "a course with no
    # mapping falls to its department chair").
    DemoAssignment(
        key="instructor-biol-8200-k1ww",
        person="instructor-three",
        role=AssignmentRole.INSTRUCTOR,
        scope=("section", "BIOL 8200 K1WW"),
        reports_to="chair-biology",
    ),
    # Outside the supervision graph in both directions, and E0-09's trigger is
    # what refuses an edge here. Seeded so that the demo institution has a Care
    # queue to develop §6.2 against at all.
    DemoAssignment(
        key="care",
        person="care",
        role=AssignmentRole.CARE,
        scope=("institution", INSTITUTION_NAME),
        reports_to=None,
    ),
    DemoAssignment(
        key="admin",
        person="admin",
        role=AssignmentRole.ADMIN,
        scope=("institution", INSTITUTION_NAME),
        reports_to=None,
    ),
)

# Who leads which course. `lead_faculty_mapping` is the authority on this, not the
# `LEAD_FACULTY` assignments above — the schema lets the two disagree and E9 is
# where an editor keeping them in step gets built, so the demo seeds them
# agreeing.
#
# **Eight of the fifteen courses are deliberately absent**, so the fall-to-chair
# path has something to exercise: with every course mapped, an implementation that
# never implements the fallback passes every screen in development.
LEAD_FACULTY_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("chair-mathematics", "MATH 040"),
    ("lead-mathematics-one", "MATH 210"),
    ("lead-mathematics-two", "MATH 505"),
    ("lead-mathematics-two", "STAT 250"),
    ("lead-biology", "BIOL 101"),
    ("lead-computer-science", "CSCI 240"),
    ("assistant-dean-arts-sciences", "PSYC 110"),
)


@dataclass(frozen=True, slots=True)
class MockWorldPerson:
    """One person the two in-repo mocks know, as rows in Pulse's own database.

    E1-12. The demo institution's eighteen belong to a fictional platform nobody
    launches from, and the mocks know a different, smaller cast: eight people at
    `mock-idp` and a handful of subjects at `mock-lms`. Until this ticket neither
    cast existed here at all, so a launch from the mock reached no person and a web
    login through the mock provider reached no identity.

    **These are new `person` rows and never the demo eighteen re-linked**, which
    ADR 0024 settles rather than this file: a person corresponds to at most one
    `user`, and every demo person is already linked to their own fictional
    platform's user. A mock-world person is a second human who happens to work at
    the same invented university.

    `idp_subject` is the `sub` `mock-idp/app/seed.py` publishes — every one of them
    is `mock-idp-user-<slug>`, built from the slug so that a subject seen in a
    session says which persona it is without a lookup.

    `lms_user_id` is the launch-side identity of the same human where there is
    one, and `None` for the six who exist at the provider only. A `person` with no
    `user` is the ordinary case ADR 0024 makes `person.user_id` nullable for.

    `assignments` is `(role, (containment level, node handle))` pairs, resolved
    against what has already been seeded, and every one of them is a root: none
    reports to anybody. Which level is legal for which role is not this file's
    choice — `SCOPE_GRAIN_RULE` in `app/models/identity.py` refuses the others.
    """

    key: str
    name: str
    category: str
    assignments: tuple[tuple[AssignmentRole, tuple[str, str]], ...] = ()
    lms_user_id: str | None = None

    @property
    def idp_subject(self) -> str:
        """The `sub` the mock provider publishes for this person."""
        return f"mock-idp-user-{self.key}"


# The launch-side subjects of the two mock-world people who have one, and the
# whole of what a launch from the mock platform can reach.
#
# **`mock-lms` authenticates nobody**: it signs a launch as whatever subject the
# caller picks (ADR 0038), and the seed registers it as a trusted issuer, so every
# `user` row on that registration is a subject anyone who can reach the container
# on a development box can launch as — and every `person` such a row links to is a
# purview they then hold. E0-31 made that set empty and said so; E1-12 makes it
# these two, argues for both in ADR 0097, and
# `test_the_only_users_on_the_mock_platform_are_the_mock_worlds_own` pins it as an
# inventory so a third is a red rather than a quiet widening.
#
# The first is `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID` — the two-hat
# person's other identity, and the one reference either mock holds to the other.
# The second exists so §7.3's leadership limb is drivable on the running stack: it
# needs a launchable subject whose person holds a live leadership assignment, and
# nothing else in either cast has both.
MOCK_LMS_TWO_HAT_USER_ID = "mock-lms-user-instructor"
MOCK_LMS_LEADERSHIP_USER_ID = "mock-lms-user-dean"

# The mock world's people, in the order `mock-idp/app/seed.py` publishes them.
#
# **Every one of them holds the assignment their persona names**, and until E1-13
# six of the eight held nothing but a linkage. That was right at the time: which
# view a person landed on came from a claim, so an assignment would have been a
# purview no ticket had asked for, on people reachable through a mock. E1-13
# resolves the landing from the assignment model instead (ADR 0098), which turns
# the same absence into a mock world nobody can demonstrate anything on — all six
# would sign in correctly and be met with the calm no-access page. So each now
# holds one live assignment naming the role the provider publishes them under, and
# `test_every_mock_world_persona_holds_the_assignment_their_role_names` pins the
# inventory.
#
# **All eight are roots**: no `reports_to` anywhere in this table. A supervision
# edge is SPEC §2.1's own subject and the demo eighteen are where the graph is
# seeded and asserted; an edge invented here would be this file deciding who
# answers to whom, for a screen that reads none of it in E1.
#
# **The scope nodes are the demo institution's**, because that is the only
# containment tree a development box holds. Two of them avoid a node the demo
# already uses the same way: the assistant dean sits in the College of Business
# and Technology, whose own assistant dean the demo does not seed, and the lead
# faculty leads `BUSA 300`, one of the eight courses `LEAD_FACULTY_MAPPINGS`
# leaves unmapped on purpose — so neither can be mistaken for part of §2.1's
# assistant-dean shape or for a second lead on a mapped course. The other four
# share a node with a demo person holding the same role, which `role_assignment`
# permits and no rule forbids: the institution cannot be duplicated at all (ADR
# 0072), and every department in that college already has a chair.
#
# **The two that carry more are the two E1-12 is demonstrated with.** The two-hat
# person holds Care at the institution and an instructor assignment, because §2's
# "entry doors are a property of the assignment" is the thing that ticket is about
# and it is not visible on a stack where she holds one hat. Her instructor
# assignment is scoped to a *demo* section rather than to the one the mock
# platform launches into: `BIOL-215-R3WW` does not exist until somebody launches
# it, and a seed cannot scope a grant to a row a later launch will create. The
# dean is the launchable subject §7.3's leadership limb needs.
MOCK_WORLD_PEOPLE: tuple[MockWorldPerson, ...] = (
    MockWorldPerson(
        "vpaa",
        "Demo Mock-World VP of Academics",
        "Leadership",
        assignments=((AssignmentRole.VP_ACADEMICS, ("institution", INSTITUTION_NAME)),),
    ),
    MockWorldPerson(
        "dean",
        "Demo Mock-World Dean",
        "Leadership",
        assignments=((AssignmentRole.DEAN, ("college", "College of Business and Technology")),),
        lms_user_id=MOCK_LMS_LEADERSHIP_USER_ID,
    ),
    MockWorldPerson(
        "assistant-dean",
        "Demo Mock-World Assistant Dean",
        "Leadership",
        assignments=(
            (AssignmentRole.ASSISTANT_DEAN, ("college", "College of Business and Technology")),
        ),
    ),
    MockWorldPerson(
        "chair",
        "Demo Mock-World Chair",
        "Faculty",
        assignments=((AssignmentRole.CHAIR, ("department", "Business Administration")),),
    ),
    MockWorldPerson(
        "lead-faculty",
        "Demo Mock-World Lead Faculty",
        "Faculty",
        assignments=((AssignmentRole.LEAD_FACULTY, ("course", "BUSA 300")),),
    ),
    MockWorldPerson(
        "admin",
        "Demo Mock-World Administrator",
        "Staff",
        assignments=((AssignmentRole.ADMIN, ("institution", INSTITUTION_NAME)),),
    ),
    MockWorldPerson(
        "care",
        "Demo Mock-World Care Officer",
        "Staff",
        assignments=((AssignmentRole.CARE, ("institution", INSTITUTION_NAME)),),
    ),
    MockWorldPerson(
        "care-who-teaches",
        "Demo Mock-World Care Officer Who Also Teaches",
        "Staff",
        assignments=(
            (AssignmentRole.CARE, ("institution", INSTITUTION_NAME)),
            (AssignmentRole.INSTRUCTOR, ("section", "BIOL 101 X1FF")),
        ),
        lms_user_id=MOCK_LMS_TWO_HAT_USER_ID,
    ),
)

# Which column on `role_assignment` holds a scope of each grain (ADR 0025). There
# is deliberately no `prefix`: no role in SPEC §2.1's table is scoped to one, so
# the column does not exist and a scope that cannot be spelled is stronger than
# one that is spelled and rejected.
SCOPE_COLUMNS = {
    "institution": "institution_id",
    "college": "college_id",
    "department": "department_id",
    "course": "course_id",
    "section": "section_id",
}

_DAYS_PER_WEEK = 7


# ---------------------------------------------------------------------------
# Reaching the database.
# ---------------------------------------------------------------------------


def resolved_configuration(environ: Mapping[str, str], dotenv_path: Path) -> dict[str, str]:
    """`environ`, with `dotenv_path` filling in only the names it does not set.

    The precedence every other reader in this repository uses — the process
    environment beats the file (ADR 0008, ADR 0012) — expressed as a value rather
    than as a mutation of `os.environ`. Reading `.env` at all is what lets
    `make seed` work on a stock checkout, which is the whole reason the seed is a
    reader of that file.

    **This function is the subject of `docs/disputes/E0-17-01.md`,** which asked
    whether a name the file supplies and the process does not should be enough to
    let a destructive script run. Todd settled it: yes — the guard reads *resolved*
    configuration, so a developer who has copied `.env.example` can seed and a
    context with no file and no exported name is refused. The consequence Todd
    accepted knowingly is that the address and the environment name can then come
    from different sources; ADR 0063 records it as an open gap rather than a
    closed one.

    Returning a new mapping instead of mutating a global is what makes that
    question askable in one call, with any file and any environment, rather than
    only by starting a process in a directory with a particular `.env` in it. A
    missing file contributes nothing, which is the case a deployment is in.

    `dotenv_values` interpolates `${...}` exactly as `load_dotenv` does — measured
    against this project's own `.env`, including a reference to a name the file
    does not define and the process does — so the two resolve `DATABASE_URL`
    identically and this is a change of shape rather than of behaviour.
    """
    from_file = {
        name: value for name, value in dotenv_values(dotenv_path).items() if value is not None
    }
    return {**from_file, **environ}


def seed_url(configuration: Mapping[str, str]) -> URL:
    """The database `DATABASE_URL` names, addressed as the bootstrap identity.

    Reads the resolved configuration it is handed rather than `os.environ`, so
    that what this function does is a question about a mapping — see
    `resolved_configuration` above for why that matters.

    No value is quoted in the failure, for the reason `app.config` and
    `backend/migrations/env.py` both give at length: this message goes to a
    terminal and to whatever captured it, and two of the three variables carry
    credentials. Naming them is enough to act on and is all that is safe to print.
    """
    address = configuration.get(ADDRESS_VARIABLE, "").strip()
    identity = {name: configuration.get(name, "").strip() for name in IDENTITY_VARIABLES}

    missing = ([ADDRESS_VARIABLE] if not address else []) + [
        name for name, value in identity.items() if not value
    ]
    if missing:
        raise SeedError(
            "The demo seed cannot reach a database without these variables:\n"
            + "\n".join(f"  {name} — not set" for name in missing)
            + "\nIt connects as the bootstrap superuser identity, which is not the role "
            "DATABASE_URL points at (docs/adr/0009, docs/adr/0012). DATABASE_URL supplies the "
            "host, port and database; DB_SUPERUSER and DB_SUPERUSER_PASSWORD supply the "
            "identity. .env.example documents all three.\n"
            "No values are shown here on purpose: this message goes to a log."
        )

    return make_url(address).set(
        username=identity["DB_SUPERUSER"],
        password=identity["DB_SUPERUSER_PASSWORD"],
    )


def check_environment_is_development(configuration: Mapping[str, str]) -> None:
    """Refuse to run anywhere but a development environment (ADR 0063).

    An equality and not a deny-list. `ENVIRONMENT` is free-form — `.env.example`
    documents it and names `development`, `staging` and `production` as
    conventions, and nothing enforces the vocabulary — so the set of names a
    deployment might use is open, and a check that enumerated the ones to refuse
    would let every name nobody thought of through. The one name that is safe is
    the one this script is for.

    **Surrounding whitespace is stripped; case is not folded.** So ` development `
    runs and `Development` does not, which is deliberate in the first half and
    inherited in the second — a trailing space in a hand-edited `.env` is
    invisible on screen and a refusal quoting it would be unreadable, while a
    miscased name is something the reader can see is wrong. ADR 0063 carries the
    reasoning and the containment argument: the strip admits the padded spellings
    of this one name and nothing else, so no deployment name reaches it.

    **Takes the resolved configuration rather than reading `os.environ`.** Which
    absence this sees — no value anywhere, or a value `.env` supplied — is the
    question E0-17-01 was disputed over and Todd settled, and a guard that reached
    for a global could only be asked it by starting a process with a particular
    file on disk. Here it is one call with one mapping.
    """
    raw = configuration.get(ENVIRONMENT_VARIABLE)
    if (raw or "").strip() == DEVELOPMENT_ENVIRONMENT:
        return

    # Three ways to be wrong and three different things to do about it, so the
    # message says which. An earlier version reported an absent variable and one
    # set to the empty string identically, as `'(not set)'` — and those two are
    # exactly the pair that cost this ticket a dispute, an arbitration and a
    # decision escalated to Todd, because a hand measurement asked one of them
    # and recorded the answer against the other (`docs/MISTAKES.md` entry 9).
    # Whoever meets this message should not have to repeat that.
    if raw is None:
        found = "(not set — nothing in the process environment, and none from `.env`)"
    elif not raw.strip():
        found = f"{raw!r} (set, but empty)"
    else:
        found = repr(raw)

    raise SeedError(
        f"The demo seed refuses to run with {ENVIRONMENT_VARIABLE}={found}.\n"
        f"It runs only where {ENVIRONMENT_VARIABLE} is {DEVELOPMENT_ENVIRONMENT!r}. This script "
        "writes an invented institution, an invented term and eighteen invented people into "
        "whatever database it is pointed at, as the bootstrap superuser (docs/adr/0009), and "
        "there is no environment other than a developer's own where that is the right thing to "
        "do. See docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md."
    )


# ---------------------------------------------------------------------------
# Writing a row once.
# ---------------------------------------------------------------------------


def upsert(session: Session, model: type[RowT], key: dict[str, Any], **values: Any) -> RowT:
    """Find the row `key` identifies, or insert it; either way, return it.

    `key` is the natural key the schema already enforces — a name, a code, a
    `(prefix, number)` pair — and never a uuid, because every primary key here is
    server-generated (ADR 0016) and a second run has no way to guess the one the
    first run got. That is the whole of what makes this script idempotent, and
    ADR 0064 records why matching rather than reloading.

    `values` are the columns the key does not determine. They are compared before
    they are set, so a second run over unchanged data issues no `UPDATE` at all
    and a row edited by hand is put back the way this file describes it.

    Flushed before returning, because the caller almost always needs the
    server-generated id to build the next row's foreign key.
    """
    statement = select(model)
    for column, value in key.items():
        statement = statement.where(getattr(model, column) == value)
    row = session.scalars(statement).one_or_none()

    if row is None:
        row = model(**key, **values)
        session.add(row)
        session.flush()
        return row

    for column, value in values.items():
        if getattr(row, column) != value:
            setattr(row, column, value)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# The calendar.
# ---------------------------------------------------------------------------


def check_calendar_fits() -> None:
    """Every cohort in the start-letter map begins and ends inside the term.

    Derived here rather than asserted in a comment, and checked before anything is
    written. The schema catches part of this on its own — `start_letter_map` has a
    CHECK that a letter's length fits the term's, and
    `app.services.section_codes` refuses a section whose dates fall outside its
    term — but neither notices a *letter nobody seeds a section for*, which is
    most of this map. A cohort that runs past the end of the term is a calendar
    somebody has to fix, and finding it here costs one loop and names the letter.
    """
    wrong: list[str] = []
    for letter, length_weeks, start in START_LETTER_MAP:
        end = start + _days(length_weeks)
        if start < TERM_START or end > TERM_END:
            wrong.append(f"{letter}: {length_weeks} weeks, {start} to {end}")
    if wrong:
        raise SeedError(
            f"These start positions do not fit inside {TERM_NAME} ({TERM_START} to {TERM_END}):\n"
            + "\n".join(f"  {line}" for line in wrong)
            + "\nA section using one of them would be refused by "
            "`app.services.section_codes.derive_section_calendar`, and a position nothing uses "
            "would sit in the map looking usable. SPEC §2.2 fixes the lengths and three of the "
            "dates; the rest are chosen in this file."
        )


def _days(length_weeks: int) -> timedelta:
    """The offset from a cohort's first day to its last, inclusive.

    `start + 7 * length_weeks - 1`, which is E0-07's convention and the one
    `app.services.section_codes` derives every section with.
    """
    return timedelta(days=length_weeks * _DAYS_PER_WEEK - 1)


# ---------------------------------------------------------------------------
# Loading the institution.
# ---------------------------------------------------------------------------


def seed_containment(session: Session) -> dict[tuple[str, str], UUID]:
    """Institution, colleges, departments, prefixes, courses and sections.

    Returns every node by `(level, handle)`, which is how the assignments below
    name the thing they are scoped to. Sections come last because a section's four
    derived columns are set from its code read against the term, and the term has
    to exist first — `seed_calendar` is called between the two.
    """
    nodes: dict[tuple[str, str], UUID] = {}

    # **The second natural key in this file that is not scoped to a row the seed
    # created**, and it is the root of the tree. SPEC §8 says a deployment serves
    # exactly one institution and `uq_institution_one_row` refuses a second row
    # (ADR 0072), so a database already holding somebody else's institution has no
    # room for this one. Without this guard the refusal still happens — at the
    # `INSERT`, as an `IntegrityError` with a forty-line traceback — and an
    # operator who pointed `make seed` at a real database would meet a stack trace
    # rather than a sentence. The rule exists to put the error on the row that is
    # actually wrong; a traceback puts it back where E0-22 found it.
    #
    # An institution under this file's own name is this seed's own row from an
    # earlier run and is reused, which is what keeps the second run idempotent.
    standing = session.scalars(select(Institution)).first()
    if standing is not None and standing.name != INSTITUTION_NAME:
        raise SeedError(
            f"This database already holds the institution {standing.name!r}, which this seed did "
            "not create.\n"
            "Pulse serves one institution per deployment (SPEC §8), enforced by "
            "`uq_institution_one_row`, so there is no second row for the demo institution to "
            "occupy. Nothing has been written.\n"
            "Use a database of your own for the demo, or drop the institution that is there "
            "first."
        )

    institution = upsert(session, Institution, {"name": INSTITUTION_NAME})
    nodes["institution", INSTITUTION_NAME] = institution.id

    for college in COLLEGES:
        college_row = upsert(
            session, College, {"institution_id": institution.id, "name": college.name}
        )
        nodes["college", college.name] = college_row.id
        for department in college.departments:
            department_row = upsert(
                session, Department, {"college_id": college_row.id, "name": department}
            )
            nodes["department", department] = department_row.id

    # **The one natural key in this file that is not scoped to a row the seed
    # created**, and the reason this loop is not a call to `upsert`. `prefix.code`
    # is `UNIQUE` across the whole table rather than per institution (ADR 0017),
    # so a database that already holds a real institution's `MATH` would have that
    # row *adopted* — re-pointed at Pulse Demo University's Mathematics department
    # — and every real course under it reached by `(prefix_id, lms_number)`, with
    # its title overwritten and its lead-faculty mapping replaced by a demo
    # person. Measured before this guard existed: the run exited 0 and printed its
    # success line. The yield is an authorization change, because purview is
    # computed from the containment tree and from `lead_faculty_mapping`, so demo
    # leadership gains purview over real courses and the real lead loses theirs.
    #
    # So the seed refuses rather than adopts, the way `seed_calendar` refuses a
    # term whose weeks it cannot reconcile. A prefix already pointing at the
    # department this file wants is this seed's own row from an earlier run and is
    # reused, which is what keeps the second run idempotent.
    prefixes: dict[str, UUID] = {}
    for prefix in PREFIXES:
        wanted = nodes["department", prefix.department]
        found = session.scalars(select(Prefix).where(Prefix.code == prefix.code)).one_or_none()
        if found is not None and found.department_id != wanted:
            holder = session.get(Department, found.department_id)
            holder_college = session.get(College, holder.college_id) if holder else None
            raise SeedError(
                f"The prefix {prefix.code!r} already exists and belongs to the department "
                f"{(holder.name if holder else '(unknown)')!r}"
                f"{f' in {holder_college.name!r}' if holder_college else ''}, which this seed "
                "did not create.\n"
                f"`prefix.code` is unique across the whole table rather than per institution "
                f"(docs/adr/0017), so seeding {prefix.code!r} here would not add a prefix — it "
                "would take that one over, re-point it at Pulse Demo University, and carry every "
                "course under it along: a course whose number matches a seeded one is reached by "
                "`(prefix_id, lms_number)`, its title overwritten and its lead-faculty mapping "
                "replaced by a demo person. Purview is computed from containment and from that "
                "mapping, so the result is an authorization change nobody asked for.\n"
                "The demo institution and a real one cannot share a prefix code in one database. "
                "Use a database of your own for the demo, or drop the demo institution first."
            )
        prefixes[prefix.code] = upsert(
            session, Prefix, {"code": prefix.code}, department_id=wanted
        ).id

    for course in COURSES:
        course_row = upsert(
            session,
            Course,
            {"prefix_id": prefixes[course.prefix], "lms_number": course.number},
            lms_title=course.title,
        )
        nodes["course", course.handle] = course_row.id

    return nodes


def seed_calendar(session: Session, institution_id: UUID) -> Term:
    """The Fall 2026 term, its eighteen weeks, and §2.2's start-letter map."""
    term = upsert(
        session,
        Term,
        {"institution_id": institution_id, "name": TERM_NAME},
        start_date=TERM_START,
        end_date=TERM_END,
        length_weeks=TERM_LENGTH_WEEKS,
    )

    # `week_rows_for_term` is the one producer of these rows, and it always emits
    # 1..N — it is handed a term and nothing else, so it cannot see what is
    # already there. Adding its output to a term that already has weeks is refused
    # by `uq_week_term_id_number`, so the count is what decides, and a count that
    # is neither zero nor N is a term whose length was edited underneath its weeks
    # (ADR 0018's consequence, routed to E2 and E11). That is not something a seed
    # can reconcile, so it says so instead.
    existing = len(session.scalars(select(Week).where(Week.term_id == term.id)).all())
    if existing == 0:
        session.add_all(week_rows_for_term(term))
        session.flush()
    elif existing != TERM_LENGTH_WEEKS:
        raise SeedError(
            f"{TERM_NAME} holds {existing} week rows and runs {TERM_LENGTH_WEEKS} weeks. "
            "`app.models.term.week_rows_for_term` always produces 1..N and cannot fill a gap, "
            "and reconciling a term whose length was edited belongs to E2 and E11's calendar "
            "editor rather than to a seed script (docs/adr/0018). Drop the term's weeks and run "
            "this again, or fix the term."
        )

    for letter, length_weeks, start in START_LETTER_MAP:
        upsert(
            session,
            StartLetterMap,
            {"term_id": term.id, "letter": letter},
            term_length_weeks=TERM_LENGTH_WEEKS,
            length_weeks=length_weeks,
            start_date=start,
        )

    return term


def demo_context_id(section: DemoSection) -> str:
    """The context identifier a demo section is bound to.

    **Fiction, and shaped so it can never be mistaken for a real one.** E1-10
    round 3 binds every section to the context it was discovered from, and a demo
    section was discovered from nothing — these eighteen are invented, and the
    in-repo mock platform's own three contexts are different courses entirely. A
    launch resolves a section by the context id its platform signed, so a
    synthetic value under this prefix is a section no launch can ever reach,
    which is exactly right for a row no launch created.
    """
    return f"pulse-demo-context-{section.handle.lower().replace(' ', '-')}"


def seed_sections(
    session: Session,
    term: Term,
    nodes: dict[tuple[str, str], UUID],
    deployment: LtiDeployment,
) -> dict[tuple[str, str], UUID]:
    """One section per entry in `SECTIONS`, with its calendar derived from its code.

    The four derived columns are never assigned here.
    `app.services.section_codes.apply_section_code` is the only thing in the system
    that writes them (SPEC §8, ADR 0021), so a seeded section whose dates disagree
    with its code is not a state this script can produce — and a code the term's
    map cannot resolve stops the seed by name rather than storing a section nobody
    can load.

    **Each section is bound to the demo platform's deployment** (E1-10 round 3),
    under a synthetic context id — see `demo_context_id`. The demo institution's
    people belong to that fictional platform, so its sections belonging to it is
    the same fiction told consistently; binding them to the *mock* platform would
    say these eighteen sections came from the mock LMS, which is not true of any
    of them.
    """
    for section in SECTIONS:
        course_id = nodes["course", section.course]
        row = session.scalars(
            select(Section).where(
                Section.course_id == course_id,
                Section.term_id == term.id,
                Section.lms_section_code == section.code,
            )
        ).one_or_none()
        if row is None:
            row = Section(
                course_id=course_id,
                term_id=term.id,
                lms_section_code=section.code,
                lti_deployment_id=deployment.id,
                lms_context_id=demo_context_id(section),
            )
            apply_section_code(session, row)
            session.add(row)
        else:
            apply_section_code(session, row)
        session.flush()
        nodes["section", section.handle] = row.id
    return nodes


def seed_mock_platform(session: Session, configuration: Mapping[str, str]) -> LtiPlatform:
    """Register the in-repo mock platform, and refuse anywhere but a development box.

    E0-31 item 1. E0-18 drives a real launch from `mock-lms`, and a tool with no
    row naming that issuer rejects every launch it signs — which is ADR 0038's
    fourth property working exactly as designed, and is why this row could not
    simply be added. ADR 0068 is where the decision to add it is recorded and
    where the cost is stated.

    **The guard is checked here rather than only in `main`.** `main` checks it
    before it opens a connection, which is what actually stops a deployed run, and
    that check would be enough if `main` were the only way in. Checking it again
    at the row makes the dependency structural: there is no ordering of calls in
    this file, and no future caller of `seed`, that writes this registration
    without the environment having been read and found to say `development`.
    `test_the_seed_refuses_to_register_the_mock_outside_a_development_environment`
    is what holds that, by calling `seed` directly with a configuration `main`
    would never have let past.

    **No `user` rows hang off this platform**, unlike the fictional registration
    `seed_people` writes. A launch from the mock arrives as one of *its* two
    invented subjects (`mock-lms/app/seed.py`), not as one of the eighteen demo
    people, and turning such a subject into a Pulse person is launch-time
    provisioning — E1's, by SPEC §14.3. What this row does is make that launch
    reach the code at all.

    **Both endpoint columns are written on an update as well as on an insert**,
    which `upsert` does for every value it is given and which matters here more
    than usual: every development database already holds this registration,
    written before E1-05's columns existed, and a launch from the mock is refused
    until the authorization endpoint is filled. The migration cannot fill either
    — that is half of why they are nullable — so this re-run is the upgrade path,
    and it completes the row rather than replacing it, because `user` and
    `lti_deployment` both key to it. `auth_token_url` arrives the same way in
    E1-06, so a developer who seeded before this ticket gets the token endpoint
    from the next `make seed` rather than from a hand-written `UPDATE`.
    """
    check_environment_is_development(configuration)
    refuse_invalid_registration_addresses(
        configuration.get(ENVIRONMENT_VARIABLE, ""),
        authorization_endpoint=MOCK_PLATFORM_AUTHORIZATION_ENDPOINT,
        jwks_url=MOCK_PLATFORM_JWKS_URL,
        auth_token_url=MOCK_PLATFORM_AUTH_TOKEN_URL,
    )

    platform = upsert(
        session,
        LtiPlatform,
        {"issuer": MOCK_PLATFORM_ISSUER, "client_id": MOCK_PLATFORM_CLIENT_ID},
        jwks_url=MOCK_PLATFORM_JWKS_URL,
        jwks_fetched_at=None,
        authorization_endpoint=MOCK_PLATFORM_AUTHORIZATION_ENDPOINT,
        auth_token_url=MOCK_PLATFORM_AUTH_TOKEN_URL,
    )
    upsert(
        session,
        LtiDeployment,
        {"lti_platform_id": platform.id, "deployment_id": MOCK_PLATFORM_DEPLOYMENT_ID},
    )
    return platform


@dataclass(frozen=True)
class DemoRegistration:
    """The fictional platform the demo institution belongs to, and its deployment.

    Both halves, because two writers need different ones: the people key to the
    platform, and the sections bind to the deployment (E1-10 round 3).
    """

    platform: LtiPlatform
    deployment: LtiDeployment


def seed_demo_platform(session: Session, configuration: Mapping[str, str]) -> DemoRegistration:
    """Register the fictional platform the demo institution belongs to.

    **Its own function since E1-10 round 3**, and the reason is ordering rather
    than tidiness: a section is now bound to the deployment it was discovered
    through, so the demo sections need this registration before `seed_sections`
    runs, and it used to be written half-way down `seed_people`, which runs after.
    Nothing about what it writes has changed.

    **It is the second writer of an `lti_platform` row in this file**, so it goes
    through E1-05's address chokepoint exactly as `seed_mock_platform` does — a
    chokepoint one writer can walk past is not one. Its address is https at an RFC
    2606 reserved domain and would pass in any environment; the call is what makes
    that a fact the code states rather than one a reader has to check.
    """
    refuse_invalid_registration_addresses(
        configuration.get(ENVIRONMENT_VARIABLE, ""),
        # No endpoints: nobody launches from this platform. It exists so the demo
        # people have a `user.lti_platform_id` to key to, and a browser is never
        # sent anywhere on its behalf, so stating an address it does not serve
        # would be the untrue record `MOCK_PLATFORM_AUTH_TOKEN_URL` explains.
        authorization_endpoint=None,
        jwks_url=DEMO_PLATFORM_JWKS_URL,
        auth_token_url=None,
    )
    platform = upsert(
        session,
        LtiPlatform,
        {"issuer": DEMO_PLATFORM_ISSUER, "client_id": DEMO_PLATFORM_CLIENT_ID},
        jwks_url=DEMO_PLATFORM_JWKS_URL,
        jwks_fetched_at=None,
        authorization_endpoint=None,
        auth_token_url=None,
    )
    deployment = upsert(
        session,
        LtiDeployment,
        {"lti_platform_id": platform.id, "deployment_id": DEMO_PLATFORM_DEPLOYMENT_ID},
    )
    return DemoRegistration(platform=platform, deployment=deployment)


def seed_people(session: Session, configuration: Mapping[str, str]) -> dict[str, Person]:
    """Every demo person, with the `user` and `user_identity` rows behind them.

    Three tables and not one, because SPEC §4.1's separation is table-level: `user`
    is the key and the platform reference, `user_identity` holds the name and the
    address `pulse_app` is refused any grant on, and `person` is the Pulse-owned
    node the supervision graph hangs off (E0-08, ADR 0024).

    **`configuration` is threaded here for one row**, the fictional platform the
    demo people belong to. It is the second writer of an `lti_platform` row in
    this file, so it goes through E1-05's address chokepoint exactly as
    `seed_mock_platform` does — a chokepoint one writer can walk past is not one.
    Its three addresses are https at an RFC 2606 reserved domain and would pass
    in any environment; the call is what makes that a fact the code states rather
    than one a reader has to check.

    **Every demo person is linked to a `user`.** The schema allows a person with
    none — a dean who has never launched still supervises chairs — and this seed
    links them all anyway, for two reasons: `person.user_id` is then the natural
    key a second run matches on, since `person` has no other unique column; and a
    demo institution where somebody cannot log in is a demo institution somebody
    will file a bug about.
    """
    platform = seed_demo_platform(session, configuration).platform
    people: dict[str, Person] = {}
    for demo in PEOPLE:
        user = upsert(
            session,
            User,
            {"lti_platform_id": platform.id, "lms_user_id": f"pulse-demo-{demo.key}"},
        )
        upsert(
            session,
            UserIdentity,
            {"user_id": user.id},
            identity_name=demo.name,
            identity_email=f"{demo.key}@{MAIL_DOMAIN}",
        )
        people[demo.key] = upsert(
            session,
            Person,
            {"user_id": user.id},
            identity_name=demo.name,
            category=demo.category,
        )
    return people


def seed_assignments(
    session: Session, people: dict[str, Person], nodes: dict[tuple[str, str], UUID]
) -> None:
    """The supervision graph, parents before children.

    `ASSIGNMENTS` is written in dependency order — a row's `reports_to` always
    names a row above it — and this walks it once rather than sorting, so a handle
    named before it is defined stops the seed with the handle in the message
    instead of writing an assignment with no supervisor.

    Nothing here disables a trigger, and the module docstring says why at length.
    Every one of these rows meets E0-09's cycle guard, its Care rules and ADR
    0044's role rank on the way in.
    """
    written: dict[str, RoleAssignment] = {}
    for assignment in ASSIGNMENTS:
        level, handle = assignment.scope
        node = nodes.get((level, handle))
        if node is None:
            raise SeedError(
                f"Assignment {assignment.key!r} is scoped to the {level} {handle!r}, which this "
                "seed has not created. The scope handles are the names in COLLEGES, PREFIXES, "
                "COURSES and SECTIONS at the top of this file."
            )

        parent: UUID | None = None
        if assignment.reports_to is not None:
            supervisor = written.get(assignment.reports_to)
            if supervisor is None:
                raise SeedError(
                    f"Assignment {assignment.key!r} reports to {assignment.reports_to!r}, which "
                    "is not an assignment this seed has already written. ASSIGNMENTS is in "
                    "dependency order on purpose: a supervisor is written before anything that "
                    "reports to it."
                )
            parent = supervisor.id

        written[assignment.key] = upsert(
            session,
            RoleAssignment,
            {
                "person_id": people[assignment.person].id,
                "role": assignment.role,
                SCOPE_COLUMNS[level]: node,
            },
            reports_to=parent,
        )


def mock_idp_issuer(configuration: Mapping[str, str]) -> str:
    """The issuer a seeded web-login linkage is written against.

    Taken from the resolved configuration, because it has to be the same string
    the tool compares an `id_token`'s `iss` to; the Compose default stands behind
    it so `make seed` works on a stock checkout. Normalised as an origin (OIDC
    Discovery 1.0 §4.3), so a trailing slash cannot make one issuer into two rows.
    """
    stated = configuration.get(MOCK_IDP_ISSUER_VARIABLE) or MOCK_IDP_ISSUER
    return stated.strip().rstrip("/")


def person_behind_a_mock_subject(session: Session, issuer: str, mock: MockWorldPerson) -> Person:
    """The `person` one mock provider subject resolves to, created if there is none.

    **The linkage is the natural key**, and it has to be: `person` carries no
    unique column of its own, `seed_people` keys the demo eighteen on their
    `user_id`, and a mock-world person may have no `user` row at all. So a second
    run finds the person through the `(idp_issuer, idp_subject)` row it wrote the
    first time, which is a value this file invented and therefore a key ADR 0064
    allows it to match on.

    Written in this order for a reason a re-run makes visible: the person first,
    then the linkage that points at it, so a run interrupted between the two leaves
    a person with no linkage — which the next run replaces rather than duplicates,
    because it is the linkage that is looked up.
    """
    linkage = session.scalars(
        select(WebLoginSubject).where(
            WebLoginSubject.idp_issuer == issuer,
            WebLoginSubject.idp_subject == mock.idp_subject,
        )
    ).one_or_none()
    if linkage is not None:
        standing = session.scalars(select(Person).where(Person.id == linkage.person_id)).one()
        standing.identity_name = mock.name
        standing.category = mock.category
        session.flush()
        return standing

    person = Person(identity_name=mock.name, category=mock.category)
    session.add(person)
    session.flush()
    session.add(
        WebLoginSubject(idp_issuer=issuer, idp_subject=mock.idp_subject, person_id=person.id)
    )
    session.flush()
    return person


def seed_the_mock_world(
    session: Session,
    configuration: Mapping[str, str],
    platform: LtiPlatform,
    nodes: dict[tuple[str, str], UUID],
) -> None:
    """The people the two in-repo mocks know, as rows both doors can resolve (E1-12).

    Criterion 1 has to be demonstrable on the running stack and not only in the
    integration suite: the two-hat person's launch and her web login have to reach
    one `person` row, by its primary key. That needs three kinds of row — a person,
    a `user` on the mock platform's registration, and a `web_login_subject` linking
    her provider subject to the same person — and this is where they are written.

    **The environment guard is checked here as well as in `main`**, exactly as
    `seed_mock_platform` checks it. These `user` rows are what turn the registration
    of a platform that authenticates nobody into a set of subjects somebody can
    launch as, so there must be no ordering of calls in this file, and no future
    caller of `seed`, that writes them without the environment having been read and
    found to say `development`.

    **Nothing here touches the demo eighteen.** ADR 0024 gives a person at most one
    `user` and every demo person already has theirs; re-pointing one at a mock
    subject would hand a launch from `mock-lms` a demo person's whole purview, which
    is the failure E0-31 wrote its guard against.
    """
    check_environment_is_development(configuration)
    issuer = mock_idp_issuer(configuration)

    for mock in MOCK_WORLD_PEOPLE:
        person = person_behind_a_mock_subject(session, issuer, mock)

        if mock.lms_user_id is not None:
            user = upsert(
                session,
                User,
                {"lti_platform_id": platform.id, "lms_user_id": mock.lms_user_id},
            )
            if person.user_id != user.id:
                person.user_id = user.id
                session.flush()

        for role, (level, handle) in mock.assignments:
            node = nodes.get((level, handle))
            if node is None:
                raise SeedError(
                    f"The mock-world person {mock.key!r} holds {role.value} over the {level} "
                    f"{handle!r}, which this seed has not created. The scope handles are the "
                    "names in COLLEGES, PREFIXES, COURSES and SECTIONS at the top of this file."
                )
            upsert(
                session,
                RoleAssignment,
                {"person_id": person.id, "role": role, SCOPE_COLUMNS[level]: node},
                reports_to=None,
            )


def seed_lead_faculty_mappings(
    session: Session, people: dict[str, Person], nodes: dict[tuple[str, str], UUID]
) -> None:
    """Who leads which course, keyed on the course — one lead per course (E0-09)."""
    for person_key, course_handle in LEAD_FACULTY_MAPPINGS:
        upsert(
            session,
            LeadFacultyMapping,
            {"course_id": nodes["course", course_handle]},
            person_id=people[person_key].id,
        )


def seed_tool_signing_key(session: Session, configuration: Mapping[str, str]) -> ToolSigningKey:
    """Generate this tool's own signing key if it has none, and refuse outside development.

    E1-05 criterion 4. LTI 1.3 needs a key pair this tool owns: E1-06 signs a
    `client_assertion` with the private half and publishes the public half for a
    platform to verify against. `docs/adr/0082` records why custody is a database
    row — the api container and the celery worker are two processes and one tool,
    and they have to sign with the same key.

    **An existing row is kept, never rotated.** Rotation is the dangerous shape,
    because it fails invisibly: a fresh key signs perfectly, and nothing goes
    wrong until a platform that already fetched the old public half rejects an
    assertion, hours later, somewhere else. So this reads first and writes only
    into an empty table, which also keeps `make seed` re-runnable — the ordinary
    state of every development database after the first run is that a key is
    already there.

    **The guard is checked here rather than only in `main`**, exactly as
    `seed_mock_platform` is and for the same reason: `main` checks it before it
    opens a connection, which is what actually stops a deployed run, and checking
    it again at the row makes the dependency structural rather than a property of
    the current call order. What the miss would cost is worse here than there —
    the private half of the tool's identity, created in a production database
    outside whatever key management that deployment has, by whoever had a
    development checkout and a production `DATABASE_URL`.

    **The PEM never leaves this function.** It is not printed, not logged, and
    not put in an exception message: `make seed` runs in a terminal, in CI and
    inside `docker compose logs`, and a private key printed once is a private key
    in a scrollback buffer, a CI artefact and whatever gets pasted when somebody
    asks for help (SPEC §10).

    RSA 2048 through `cryptography`, which is already pinned and is what the tool
    verifies launches with (ADR 0073) — ADR 0035's bound says the tool's real key
    uses a real library, and this is that. PKCS#8, unencrypted, because the
    process that reads it has nowhere to get a passphrase from.
    """
    check_environment_is_development(configuration)

    existing = session.scalars(select(ToolSigningKey)).first()
    if existing is not None:
        return existing

    key = rsa.generate_private_key(public_exponent=65537, key_size=TOOL_SIGNING_KEY_BITS)
    row = ToolSigningKey(
        private_key_pem=key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
    )
    session.add(row)
    session.flush()
    return row


def seed(session: Session, configuration: Mapping[str, str]) -> None:
    """Load the whole demo institution into `session`. The caller commits.

    `configuration` is the resolved mapping `main` has already checked, and it is
    threaded here for four writes: `seed_mock_platform`, `seed_tool_signing_key`
    and `seed_the_mock_world` re-read the environment guard at the rows each of
    them would write, and both registrations go through E1-05's address
    chokepoint, which reads the environment too. The first two guarded writes run
    first so that a refusal costs no writes at all; the third cannot, because its
    rows hang off almost everything here — and its own guard is what makes a
    refusal there cost nothing that reaches the mock's registration.
    """
    check_calendar_fits()
    mock = seed_mock_platform(session, configuration)
    seed_tool_signing_key(session, configuration)
    demo = seed_demo_platform(session, configuration)
    nodes = seed_containment(session)
    term = seed_calendar(session, nodes["institution", INSTITUTION_NAME])
    seed_sections(session, term, nodes, demo.deployment)
    people = seed_people(session, configuration)
    seed_assignments(session, people, nodes)
    seed_lead_faculty_mappings(session, people, nodes)
    # Last, because the mock world hangs off everything above it: its people are
    # scoped to containment nodes and to a seeded section, and its two launchable
    # subjects key to the registration written first (E1-12).
    seed_the_mock_world(session, configuration, mock, nodes)


def main(environ: Mapping[str, str] | None = None, dotenv_path: Path | None = None) -> int:
    """Run the seed against the database `DATABASE_URL` names.

    One transaction. A seed that failed half way through would leave a partial
    institution behind — a college with no departments, an assignment with no
    supervisor — and the next run would match those rows and build on them.

    Both arguments default to the real thing and exist so that the guard's answer
    can be asked without starting a process in a directory with a particular
    `.env` in it. `make seed` passes neither.
    """
    configuration = resolved_configuration(
        os.environ if environ is None else environ,
        DOTENV_PATH if dotenv_path is None else dotenv_path,
    )

    try:
        check_environment_is_development(configuration)
        url = seed_url(configuration)
    except SeedError as refused:
        print(refused, file=sys.stderr)
        return 2

    engine = create_engine(url)
    try:
        # The session states the environment it writes under (ADR 0101): the
        # registration-address rules are a mapper event on `LtiPlatform` now, and
        # a session that states nothing is judged as a deployment — which would
        # refuse the mock platform's own cleartext addresses on a Compose service
        # name, and stop `make seed`. This script has already refused to run
        # anywhere but development by the time it reaches here (ADR 0063), so the
        # name is a constant rather than a reading of the configuration.
        with Session(bind=engine, info={"environment": DEVELOPMENT_ENVIRONMENT}) as session:
            try:
                seed(session, configuration)
            except SeedError as refused:
                session.rollback()
                print(refused, file=sys.stderr)
                return 2
            session.commit()
    finally:
        engine.dispose()

    print(
        f"Seeded {INSTITUTION_NAME}: {len(COLLEGES)} colleges, "
        f"{sum(len(college.departments) for college in COLLEGES)} departments, "
        f"{len(PREFIXES)} prefixes, {len(COURSES)} courses, {len(SECTIONS)} sections, "
        f"{TERM_NAME} with {len(START_LETTER_MAP)} start positions, "
        f"{len(PEOPLE)} people, {len(ASSIGNMENTS)} assignments, "
        f"{len(LEAD_FACULTY_MAPPINGS)} lead-faculty mappings, two platform "
        f"registrations — the fictional one its people belong to, and {MOCK_PLATFORM_ISSUER} "
        f"for the mock LMS — this tool's own signing key, and the mock world: "
        f"{len(MOCK_WORLD_PEOPLE)} people linked to their mock-provider subjects, of whom two "
        "are launchable from the mock LMS."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
