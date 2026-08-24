# E1-05 — Registration owns its endpoints and its keys

**ID:** E1-05
**Branch:** `e1/registration-columns`
**Depends on:** nothing
**Security-relevant (⚠ line-by-line):** every column and constraint here is a
trust anchor — the endpoints the browser is sent to, the URL keys are fetched
from, and the custody of the tool's own private key.

## Context

Two carried entries land here, and their "done when"s govern:

- **"`LTI_PLATFORM_AUTHORIZATION_ENDPOINT` is process-wide and platforms are
  not"** — with one registered platform the setting and the registration agree;
  with two, a launch from platform B would be redirected to A's endpoint. Done
  when two platforms are registered at once, each launch round-trips to its own
  authorization endpoint (proved by a test that fails if both go to one
  address), and the setting is **gone** from `Settings` and `.env.example`,
  not left as a fallback.
- **E0-24 item 1 — `jwks_url` is credential-equivalent and unconstrained.**
  E1 writes and fetches the column, so E1 says what a legitimate value looks
  like.

ADR 0075 records why the columns did not exist in E0 ("arrive with the code
that calls them, in the same change") and its per-value horizon rule —
browser-facing versus tool-facing addresses are different strings — governs
which horizon each new column is. The client-credentials grant (E1-06) needs
two more things from the tool side: an `auth_token_url` column, and a tool key
pair whose public half a platform can fetch — the registration document's keys
are the column names, so both sides move together across E1-05/E1-06.

Read first: the two carried entries; ADR 0075 and ADR 0077 (what stands, what
was superseded, the refusal rules that must keep holding); ADR 0007/0005
posture on pins for any new dependency; `backend/app/models/lti.py`;
`backend/app/lti/launch.py::registered_platform`; SPEC §7.3.

## Scope

- `lti_platform` gains per-registration columns: the platform's authorization
  endpoint (browser horizon) and `auth_token_url` (tool horizon), beside the
  existing issuer/client/deployment and `jwks_url`. Migration plus model, with
  the E0-33 catalog assertions extended to the new objects.
- `jwks_url` (and the two new URL columns) are **constrained, and the
  constraint is this ticket's own decision with its own ADR** — not a reuse
  of ADR 0077's vocabulary, which was written for `.env`-supplied values in a
  trusted deployment context and explicitly exempts `jwks_url` from its
  loopback-class rule. This column is a different thing: database-resident,
  written by the seed today and by E11's registration UI later,
  credential-equivalent (it decides which keys may sign an accepted launch),
  and fetched server-side on every launch — an SSRF surface and a trust
  anchor at once. The floor is fixed here: an encrypted transport outside
  development, and the mock addresses refused outside development (those two
  rules do carry over from ADR 0077). The ADR must additionally take a
  position on loopback, link-local, and private-range addresses as
  server-side fetch targets — weighing that an institution's real LMS may
  legitimately live on a private address — with refusal tests on both sides
  of whatever boundary it draws. The constraint's location (check constraint,
  validator at the chokepoint, or both) is the builder's call in the same
  ADR.
- **The tool's key pair exists**, for signing client assertions (E1-06/E1-11)
  — generated or supplied per environment, never committed; custody (settings
  variable, file path, or database) is a real decision: write the ADR. The
  private key never appears in `.env.example` (placeholder name only), logs,
  or fixtures; test keys are generated per run like the mocks' (§9.1).
- `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` deleted from `Settings`,
  `.env.example`, and the Compose anchors; `app/lti/launch.py` reads the
  registration's column instead.
- The seed registers the mock platform with the new columns filled (behind the
  ADR 0063/0068 guard, as today).

## Acceptance criteria

1. Two platforms registered in a test round-trip to their own authorization
   endpoints; the test fails if both resolve one address.
2. `grep -r LTI_PLATFORM_AUTHORIZATION_ENDPOINT` over the tree finds only
   history (ADRs, tickets); no code, config, example, or Compose reference.
3. Invalid `jwks_url`/endpoint values are refused at write time per this
   ticket's constraint ADR — at least a cleartext URL and a mock address
   outside development — with tests on both sides of every boundary the ADR
   draws; ADR 0077's existing refusal tests still pass untouched.
4. The tool key pair exists in development bring-up with no committed private
   key anywhere in the repository (a test greps for key material in the tree —
   PEM headers make a serviceable canary).

## Out of scope

- The mock platform's half of the grant and the tool's public JWKS route
  (E1-06 — one change, four parts, over there).
- Any NRPS/AGS call (E1-11).
- The launch flow itself (E1-08) — this ticket changes where it reads, not
  what it does.
