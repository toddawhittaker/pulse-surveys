# 0081 — A registration's addresses are judged at one write-time chokepoint, by four rules

## Context

An `lti_platform` row holds three URLs after E1-05: `jwks_url`, which E0-08
created, and the two this ticket adds — `authorization_endpoint` and
`auth_token_url`. Until now any string at all could be written into any of them.

E0-24 item 1 is the carried finding: **`jwks_url` is credential-equivalent and
unconstrained.** It decides which public keys may sign a launch this tool
accepts, so whoever controls the address controls who may log in as anyone; and
the tool fetches it server-side on every launch, so a stored row is also an
outbound request this container makes on somebody else's behalf. That entry
assigns the constraint to E1, because E1 is the epic that writes and fetches the
column. E1-05's ticket adds two conditions the finding does not: the decision
must be **this ticket's own**, with refusal tests on both sides of every boundary
it draws, and it must take a position on loopback, link-local and private-range
addresses rather than inherit one.

ADR 0077 answers a question that reads like the same one — what a legitimate
address is for the *web door's identity provider* — and it is not. That record
governs five `.env`-supplied settings, read once at startup, in a deployment
whose operator wrote them. These are database columns, written today by the demo
seed and later by E11's registration console, by someone typing into a form. The
threat model differs in who writes the value and in when it is judged, so the
vocabulary carries and the conclusions must be re-derived.

**Where ADR 0077's vocabulary carries over, deliberately.** Four questions about
a URL's host have already been answered here the hard way, and re-deriving any of
them is `docs/MISTAKES.md` entry 13 — a hazard worked around in one of the two
places facing it. `url_host` reads a host the way a resolver does, brackets
stripped, case folded, and **exactly one** trailing dot removed, with an exact
comparison after it so `mock-lms.example.edu.` is not swept up.
`is_on_this_machine` decides whether cleartext crosses no network.
`is_a_loopback_host` decides whether a host names the machine the *reader* is
sitting at, as a class rather than a list, with the IPv4-mapped form unwrapped
first. `is_a_deployment` compares the environment name exactly, so `staging`,
`production`, `development-blue` and `pre-development` are all deployments.
`app.models.lti` imports all four rather than writing them again — and all four
lost a leading underscore in the doing, because it stopped being true the moment
`app.config` was no longer their only caller.

**Where it deliberately differs, and why.** ADR 0077 *exempts* `oidc_jwks_url`
from its loopback rule, on the argument that a key-set sidecar reached by this
container at a loopback address is an ordinary deployment. That argument is
correct and it survives here — but ADR 0077 draws no line at all around
link-local, and for a `.env`-supplied setting that is defensible: the operator
who set it is the operator who owns the machine. A registration column is
written through a console by someone who may not be, and the two addresses this
tool *fetches* are the only ones in the system that turn a stored row into an
outbound request.

## Decision

**A validator, `app.models.lti.refuse_invalid_registration_addresses`, at one
chokepoint every writer of an `lti_platform` row passes through.** It takes the
environment name and the three addresses and raises
`RegistrationAddressError`, whose message names the column and quotes no value —
ADR 0056's house rule, and it applies with more force here because this refusal
reaches a seed's stderr, a container log and later a rendered console page.

**A NULL passes.** Both new columns are nullable and absence means "not stated",
never a default. A NULL `authorization_endpoint` is refused at the *launch* and
not at the write, because "an administrator has not finished this registration"
and "an administrator wrote something wrong" are different situations with
different repairs.

Four rules, every one of them switched off where `ENVIRONMENT` is exactly the
development name:

1. **https**, unless the host names this machine. The exemption is ADR 0077 rule
   4's and is kept for the shape that record protects by name: a platform or
   key-set sidecar running beside the application, reached at a loopback address
   over plain `http`, where the packet never leaves the machine.
2. **The mock platform's host is refused on all three columns.** Compared as the
   parsed host against the Compose service name `mock-lms`, not against the
   seeded URL: a container on this network reaches the mock on whatever port it
   listens on, so an equality against `http://mock-lms:8000/...` is defeated by
   an operator who changes the port or terminates TLS in front of it. ADR 0038's
   fourth property — that a production Pulse holds no row naming that issuer — is
   what makes shipping the mock in the base Compose file survivable, and ADR 0068
   moved that boundary from "no such row exists in this repository" to "no run
   permitted to write it can start". This is the third layer: the row is refused
   at the write even where a guard was bypassed.
3. **Loopback is refused on `authorization_endpoint`, and on no other column.**
   That string is never resolved in this container: it is handed to a browser and
   resolved on the machine that browser runs on. A deployment registering
   `http://localhost:8080/oidc/authorize` — the development value, and the value
   an operator copies forward — answers every launch with a redirect to a port on
   the launching person's own computer, where anything listening receives an
   institution-issued link arriving from a Pulse URL. As a class rather than a
   list of spellings: `127.0.0.2` is an ordinary address in `127.0.0.0/8` and
   `::ffff:127.0.0.1` matches no written-out spelling.
4. **Link-local is refused on `jwks_url` and `auth_token_url`**, both families —
   `169.254.0.0/16` and `fe80::/10`. These two are the only addresses a stored
   row makes this container fetch. `169.254.169.254` is where the cloud metadata
   service answers credentials to any request that reaches it on every major
   provider, and no legitimate LMS is there.

**Where "class" actually ends for rules 3 and 4, measured by this PR's security
review (2026-08-25).** Both rules judge only spellings `ipaddress.ip_address`
parses. A shortened dotted quad (`127.1`), a bare decimal (`2130706433`,
`2852039166`), dotted hex or octal (`0x7f.0.0.1`, `0251.0376.0251.0376`), and a
resolver-backed name for a refused address (`metadata.google.internal`) are all
accepted while the addresses they reach are refused — the same residue ADR 0077
records for its loopback class, arrived at the same way. The impact cap is rule
1: cleartext off this machine is refused regardless of spelling, so the
plain-`http` metadata endpoints stay unreachable, and today's only writer is
the development-only seed. Closing it means resolving the host and judging
every returned address, or refusing hosts that parse as integer or dotted-hex
literals — a reviewed tightening with its own test pairs, owed before E11's
console becomes a second writer; `docs/tickets/e1/deferred.md` carries the
done-when.

**Private ranges are accepted on every column**, RFC 1918 and IPv6 unique-local
alike. A university running Canvas on `10.0.0.5` behind its own network is an
ordinary deployment, and a browser on that network resolves the address
perfectly well. This is the position the ticket asks to be taken explicitly, and
it is the boundary rule 4 stands or falls on: `169.254.169.254` refused and
`10.0.0.5` accepted is one line apart in the implementation and a product
difference in the field.

**Rules 1 and 3 compose rather than short-circuit.** `http://localhost:8080/
oidc/authorize` on the browser-facing column is exempt from the transport rule
and refused by the loopback rule. Written as an early return — "on this machine,
nothing more to check" — the exemption answers first and the hole stays open
with every other test green.

**In development everything is accepted.** The mock's own addresses have to seed
or `make seed` stops, which takes SPEC §14.3's exit criterion with it. A rule
that kept firing there would meet a developer as an unexplained refusal after
moving a service.

## Alternatives rejected

**A database `CHECK` constraint, or one alongside the validator.** Every rule
above reads `ENVIRONMENT`, and the database does not hold it. A check constraint
could express only the environment-independent part, which is none of these four
rules — and a constraint that encoded the deployment rules unconditionally would
refuse the demo seed. The ticket leaves the location to the builder and this is
the answer: there is no rule here a constraint can carry.

**Refusing every address that is not publicly routable** (`not ip.is_global`).
One line, covers loopback, link-local and private range at once, and reads like
a tightening. It refuses the private-address deployment above, which is a very
ordinary way for an institution to run an LMS, and no refusal test would notice.
Rejected on that; the acceptance tests for RFC 1918 and ULA are what hold it.

**Reusing ADR 0077's rules wholesale.** They were written for `.env` values in a
deployment the operator wrote, they exempt `jwks_url` from the loopback class
without asking about link-local, and the ticket asks for a decision of this
ticket's own. Rejected as a decision; adopted as vocabulary, which is the split
this record states.

**Validating on read instead of on write.** A launch could judge the address it
is about to use. It would catch a row written round the chokepoint, which is the
one thing this design does not — but it converts a bad registration into a
refusal at every launch rather than at the moment somebody could fix it, and it
puts four rules on the hot path of the busiest code in the system. Rejected;
the read-side counterpart that does exist is the NULL refusal in
`begin_a_launch`, which is about absence rather than validity.

## Consequences

**A writer that goes round SQLAlchemy is not judged.** Raw SQL against the
database, a migration, or `psql`, all write whatever they are given. This is the
same accepted posture ADR 0068 records for the seed's own guard and ADR 0063 for
the environment check: the guard binds the writers that exist, and the writers
that exist are the demo seed today and E11's registration console later, both of
which call this function. It is stated here rather than hidden, because a reader
who assumes the database enforces it will build the next writer accordingly.

**Four rules over three columns is where a green test is most likely to be
green for the wrong reason.** Any refusal can be produced by a neighbouring rule
firing on a background value — `docs/MISTAKES.md` entry 3, and here it is the
likely failure rather than a hypothetical. Every refusal case in
`tests/unit/test_registration_address_constraints.py` therefore carries `https`
and a real institution's addresses in the two columns it is not testing, and the
two rules that genuinely overlap have a test that says so by name.

**Development accepts everything, so no rule here is exercised by the demo
stack.** The suite is the whole of what holds these rules, and the acceptance
half of it is what stops the cheapest wrong implementation — a validator that
raises whenever the environment is not development, which passes every refusal
test in the module and makes Pulse registrable nowhere.

**The mock catalog is a written-out name that can go stale.** A rule refusing a
service nothing runs under refuses nothing and reports every registration clean
(`docs/MISTAKES.md` entry 35). A control test holds `MOCK_PLATFORM_SERVICE`
against the fixture every other module reasons about the mock through.

**E11's registration console inherits a refusal it must render.** The message
names a column and quotes no value, which is right for a log and slightly terse
for a form; the console may add the field highlighting, and it may not add the
value to the message.
