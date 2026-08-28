# 0101 — A fetched address is judged by what it resolves to, and the connection is pinned to it

## Context

E1's last open finding with a severity attached. E1-11's security fix round
closed the roster walk's server-side request forgery (ADR 0096: every fetched URL
is judged, redirects are off) and measured what was left: a registered platform
can point `rel="next"` at an internal service holding a **valid public
certificate on an RFC 1918 or split-horizon address**. It is `https`, it is not
the mock, and its host is a name rather than a refused literal — so every one of
ADR 0081's four rules passes it, TLS verifies, and the tool issues the GET with
its NRPS Bearer token attached. The answer is parsed as a membership container.

Two deferred entries record the same defect at two surfaces, and the cleanup plan
merged them: E1-05 item 2 (the write-time rules judge spellings, so `127.1`,
`2130706433`, `0x7f.0.0.1` and any resolver-backed name walk past rules 3 and 4 —
ADR 0081's own measured residue) and E1-11 item 1 (the fetched path trusts the
host literal). E1-05 item 3 is the third: the write-time chokepoint is a **call
convention**, kept by `scripts/seed.py` because that script calls it, and E11's
registration console is the next writer.

## Decision

**Rule 5: resolve the host and judge every address that comes back**, in both
chokepoints in `app.models.lti`, after rules 1 to 4 have passed — an address a
spelling rule refuses is never looked up.

- An address that is **not `ip.is_global`** is refused: private ranges,
  carrier-grade NAT, link-local, reserved and loopback.
- **Except loopback on a column outside `LOOPBACK_REFUSED_COLUMNS`**, which
  preserves ADR 0096's split: an operator registering a key-set or token sidecar
  reached at a loopback address in the same pod is doing it on purpose. Rule 5
  adds a resolution dimension to that split rather than reopening it, so `127.1`
  on `jwks_url` is a badly spelled sidecar and the same string on
  `authorization_endpoint` is refused.
- The **IPv4-mapped form is unwrapped** before the question is asked, by the shape
  `app.config.is_a_loopback_host` already uses.
- An **unresolvable host is refused**, in both of the shapes a resolver fails in —
  a raise and an empty answer. Unresolvable is unjudgeable, and a name that
  resolves nowhere at the moment of the check resolves wherever its owner likes at
  the moment of the fetch.
- Every rule stays **off under the development name**, rule 5 included, with one
  exception in the other direction: `refuse_invalid_fetched_address` runs rule 5
  in development for a host that is **not** the one its caller named as its own.
  `app.services.roster_sync` names the section's stored host, so the demo stack's
  own roster costs no lookup and a `rel="next"` hop anywhere else is judged;
  `app.services.provisioning` names none, so launch-time storage keeps
  development's blanket admission.
- Resolution is a **parameter** (`resolve`), defaulting to `getaddrinfo`. No test
  in this repository reaches a name server: a rule measured against a resolver is
  measuring the machine (`docs/MISTAKES.md` entry 40).

**The pin: the connection is made to the address that was judged.**
`refuse_invalid_fetched_address` answers the addresses it resolved.
`app.services.roster_sync` keeps one pin table per sync — first resolution wins,
a later one never moves it — and `PinnedResolutionAdapter`, mounted over whatever
adapter the session already holds, sends a pinned request to that address with
the `Host` header stating the platform's own name and TLS verified against that
name (urllib3's `server_hostname` and `assert_hostname` on the pool). A host with
no pin passes through untouched. Without the pin the check and the request are
about two different addresses, which is the redirect bypass one layer down.

**The write-time chokepoint becomes structural.** `before_insert` and
`before_update` mapper events on `LtiPlatform` call
`refuse_invalid_registration_addresses`, so a writer that never heard of it is
judged anyway, on the first write and on every edit after it. The environment
comes from `Session.info["environment"]` — stamped by `app.db.SessionLocal` from
the settings it already builds its engine from, and by the demo seed both where
it builds its session and in each of its two registration writers, which state it
from the configuration mapping they are handed because `main` is not the only way
in. **A session that states none is judged as a deployment.** That direction is
the whole decision: read as development, a writer nobody thought about registers
the mock platform in production and nothing notices; read as a deployment, a
legitimate development writer is refused loudly on its first run, with a message
naming the column and a one-line repair where the session is built.

## Alternatives rejected

**A denylist of literal spellings** — refuse hosts that parse as bare decimals or
dotted hex, which is the other half of E1-05 item 2's done-when. It is a closed
set defeated one level out (E1-01's battery lesson), and it says nothing at all
about `metadata.google.internal`, which is the case the finding is actually
about. Resolution subsumes it: every one of ADR 0081's four residue spellings is
refused by rule 5 because of the address it reaches.

**Flat `not ip.is_global`, with no loopback carve-out.** One line, and it refuses
the operator-registered sidecar ADR 0077 protects by name and ADR 0096 kept when
it added loopback to the roster column — a supported deployment made
unregistrable, which no refusal test would notice.

**Judging before the walk and letting the transport resolve the name again.**
That is a check of one thing and a request to another: the platform's own DNS can
answer a public address while the walk is judging and a private one while the
page is being fetched. The pin is the whole difference, and the test that holds it
answers a *different but still global* address the second time, so an unpinned
sync cannot pass by refusing.

**Reading the environment from `os.environ` in the mapper event.** It is the
defect deferred E1-10 item 5 removed from the writer next door: a process-wide
read that no caller states and no test can pose without mutating the process. The
session is the unit of work doing the writing, and it is the thing that knows.

## Consequences

**This record supersedes [ADR 0081](0081-a-registrations-addresses-are-refused-at-one-write-time-chokepoint.md)
in part**, in two paragraphs:

- Its **"Private ranges are accepted on every column"** decision. Rule 5 refuses
  them, on every column, in a deployment.
- Its rejected alternative **"Refusing every address that is not publicly
  routable"**, which rejected `not ip.is_global` by name.

**And 0081's stated cost is now the accepted price.** That record named it
exactly: a university running Canvas on `10.0.0.5` behind its own network is an
ordinary deployment, and it can no longer be registered in a deployment — the
address is refused at write time and at fetch time. E1-11's residual finding is
the other side of the same argument, and nothing at the point of judgment can
tell an institution's own LMS from an internal service holding a valid
certificate. The refusal is loud, it names the column, and the repair is an
address on the public internet; the acceptance was silent and the failure it
permitted was a tokened request to somebody's internal network. Everything else
in ADR 0081 stands, and it carries a pointer to this record.

**A question ADR 0081 deliberately left open is now closed.** A link-local
`authorization_endpoint` is refused — the browser-facing column is resolved here
too, once, at the write. Nothing was asserted about it either way before.

**The token POST and the key-set fetch keep registration-time judgment only.**
The sync's token request travels over the same session the pinned adapter is
mounted on, but its host is never judged at fetch time and so never pinned: it
passes through untouched, as everything unpinned does. `pylti1p3` fetches
`jwks_url` on a launch through a transport of its own, which nothing here mounts
an adapter on at all. So both keep the rebind window the roster walk no longer
has. What bounds it is who chose the address — both are the operator's, written
into the registration and judged there, rather than a platform's run-time choice
— and closing it means judging and pinning inside the library's own client, which
is a wider change than this batch.

**Raw SQL and a Core `insert()` still escape the flush chokepoint**, because
mapper events do not fire for either. This extends rather than closes the residue
ADR 0081 records, and it is stated here for the same reason: a reader who assumes
the database enforces it will build the next writer accordingly.

**A deployment pays a name lookup per registration write and per roster page.**
The write is a rare administrative act. The page lookup is the hourly walk's, once
per page per section, and it is what the development exemption exists to keep off
the demo stack — a Compose service name that half the time resolves to nothing.

**`Session.info["environment"]` is now load-bearing for anything that writes an
`lti_platform` row through the ORM.** A new writer states it where the session is
built; a session that states nothing is refused in a deployment's terms, with a
message naming the column.
