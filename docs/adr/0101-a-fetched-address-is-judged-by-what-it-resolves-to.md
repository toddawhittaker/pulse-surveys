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
- An **unresolvable host is refused**, in every shape a resolver fails in — an
  empty answer, an `OSError` for a name nothing answers for, and a `UnicodeError`
  for a name the IDNA codec will not encode at all (a label over 63 octets, an
  empty label), which is a `ValueError` and no `OSError`. Catching only the first
  two let the third escape the rules, the walk and the section's own error
  handling, taking the refusal row and the validly-fetched prefix with it; the
  review found that as a MEDIUM. Unresolvable is unjudgeable, and a name that
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

**Three IPv6 forms that embed an IPv4 are unwrapped, not one.** The first cut
unwrapped only the IPv4-mapped `::ffff:0:0/96`, the form `.ipv4_mapped` reports,
and judged the wrapper for the other two — but `ipaddress` reports every embedded
form `is_global` true, so `64:ff9b::a9fe:a9fe` (the NAT64 well-known prefix, RFC
6052) and `::a9fe:a9fe` (the deprecated IPv4-compatible form, RFC 4291) both read
as globally routable while a DNS64/NAT64 egress translates the packet to
`169.254.169.254`. E1 Batch C's security review found it. All three forms are now
unwrapped to the embedded IPv4 and that address is judged, at both entries into
the shared judgment. It is an unwrap, not a blanket reject: a NAT64-wrapped
*global* IPv4 (`64:ff9b::8.8.8.8`) is the legitimate DNS64 synthesis for a v4-only
global platform on an IPv6-only network and stays accepted, which a reject-all fix
would break while every refusal test stayed green. The IPv4-compatible range
`::/96` contains the specials `::` (unspecified) and `::1` (IPv6 loopback), which
are not an embedded IPv4 and are excluded from the unwrap — unwrapping `::1` to
`0.0.0.1` would lose the loopback this record's own ADR 0096 split turns on — so
the IPv6 loopback handling is left intact, while an embedded `127.0.0.1`
(`::7f00:1`) is a genuine IPv4-compatible address and is unwrapped and refused on
the browser-facing column.

**One residual limit remains, and it is inherent.** A *custom* NAT64 prefix — a
network-specific prefix (RFC 6052 §3.1) rather than the well-known
`64:ff9b::/96` — is indistinguishable from an ordinary global IPv6 address without
the egress's own NAT64 configuration, which the application does not hold and has
no way to learn. So on an IPv6-only network configured with a network-specific
prefix, a name resolving to `<custom-prefix>::a9fe:a9fe` is judged as the global
IPv6 address it is spelled as and accepted. This is a limit of resolve-and-judge
itself, not a gap in the rule: the only place the mapping from that prefix to an
embedded IPv4 is known is the NAT64 gateway. Closing it would mean handing the
application the egress's NAT64 configuration, which is a deployment coupling this
batch does not take on.

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

**Four write shapes still escape the flush chokepoint, and three that look like
them do not.** Measured on SQLAlchemy 2.0.52 rather than assumed, because the
review found the first list understated: `session.add`, an attribute changed on a
persistent row, and `session.merge` are all **judged**, while
`Session.bulk_save_objects`, an ORM-enabled
`session.execute(update(LtiPlatform).values(...))`, a Core `insert()` and raw SQL
fire **no event at all**. The ORM-enabled bulk `UPDATE` is the one that matters:
it is written through the ORM's own API, it looks exactly like a judged write, and
it is a natural way to write the save button on E11's registration console — which
is the use case this chokepoint exists for. What bounds the residue is the grant
rather than the event: `pulse_app` holds `SELECT` on `lti_platform` and nothing
else, so a bypassing write on the application's own connection is refused by the
database, and what is left is a writer connecting as an identity that may write —
the seed's bootstrap superuser, a migration, `psql`. This extends rather than
closes the residue ADR 0081 records, and it is stated for the same reason: a
reader who assumes the database enforces it will build the next writer
accordingly.

**The pin depends on one canonical spelling of a host, and both ends share the
helper that produces it.** A hostname has more than one legal spelling —
`host.example.` and `host.example` are the same name, and so are `röster.example`
and `xn--rster-jua.example`, because a transport encodes a non-ASCII host before
it dials. The first cut of this decision wrote the pin under one folding and
looked it up under another, so those spellings missed their own pin, and a miss is
silent: the request goes out unpinned and the transport resolves the name a second
time, which is precisely the window this record claims to close. E1 Batch C's
security review found it as a HIGH.

So `app.config.canonical_host` is the one implementation — case folded, one
trailing dot stripped, and the IDNA form taken for a host that is not ASCII —
`url_host` routes through it, every address rule keys on it, and
`PinnedResolutionAdapter` looks its pin up under it. The IDNA step asks
`urllib3`'s own `parse_url`, the encoder the request will actually use, rather
than reproducing its rule: two IDNA implementations agree until the first name the
two standards disagree on, and a disagreement there is a missed pin. An ASCII host
never reaches that step, which is what leaves ADR 0077's three rules seeing
exactly the strings they saw before. **A pinned request states the authority
`requests` prepared** — encoded form, trailing dot and all — so the platform is
asked for the virtual host an unpinned request would have asked for, and its
certificate is verified against the name it serves.

**A deployment pays a name lookup per registration write and per roster page.**
The write is a rare administrative act. The page lookup is the hourly walk's, once
per page per section, and it is what the development exemption exists to keep off
the demo stack — a Compose service name that half the time resolves to nothing.

**`Session.info["environment"]` is now load-bearing for anything that writes an
`lti_platform` row through the ORM.** A new writer states it where the session is
built; a session that states nothing is refused in a deployment's terms, with a
message naming the column.
