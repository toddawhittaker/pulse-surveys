# Entry 29. A value was repaired before the check that should have refused it

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(One review pass after the entry was written, and it is the same
class with a different tool — which is the sharpening worth keeping: **the repair
need not look like a repair.** The scope string was split with a bare
`str.split()`, which treats a tab, a newline and U+00A0 as separators, where RFC
6749 Appendix A.4 separates scope tokens by one space and by nothing else. So
`openid<TAB>email` — a single unknown token to any conformant server — arrived at
the checks as two well-known ones and was granted, with the token response
echoing "openid email" and the session releasing the `email` claims. The
unknown-scope refusal that had been added *the round before*, three lines below,
could not fire: the value it was written to catch had already been turned into
two values it was written to accept. A standard-library parser named after a
concept is not a check against that concept's grammar, and `split()`, `int()`,
`urlsplit()` and `fromisoformat()` are all repairs in this sense — each accepts a
wider language than the specification it is standing in for. Fixed by writing the
grammar out where it is used and carrying the result as a tuple that nothing
re-splits;
[ADR 0062](../adr/0062-a-request-is-parsed-once-at-the-edge.md) is the rule
generalised, since this was the fifth instance of the shape in three rounds.)*

**What happened.** The mock OIDC provider read every request parameter through one
helper, and that helper ended in `.strip()`. One habit, three specification
breaks, in a file that had already been through two of the implementer's own
review passes *and* a fix round about this exact class of input handling:

- **PKCE stopped binding one string.** The shape check ran on the trimmed value,
  so for a challenge registered over some verifier `v`, every string that trimmed
  to `v` was accepted. A challenge bound over `"a" * 43` redeemed with
  `" " + "a" * 43 + "\n"` answered **200 with an `id_token`**. Keycloak, Okta and
  Auth0 all answer `invalid_grant`, and `base64.encodebytes()` appends exactly
  that newline — so a client minting a verifier that way passes every test here
  and fails at the first real provider, with an error naming the verifier rather
  than the encoder.
- **`state` came back trimmed**, where RFC 6749 §4.1.2 requires "the exact value
  received from the client".
- **`nonce` was issued trimmed**, so OIDC Core §3.1.3.7 step 11 fails in the
  client.

All three were found by an external reviewer, running a live instance.

**Root cause.** The normalisation sat between the wire and the guard, so the
guard was checking a value no client had sent. Two things make it hard to see.
First, `.strip()` reads as hygiene rather than as a decision — it looks
*defensive*, which is the opposite of what it was doing. Second, it is invisible
at the point that matters: `pkce_shape_problem(verifier)` at the call site looks
exactly right, and the argument had already been made well-formed one frame
earlier.

It is entry 23's family — a validation creating the appearance of a behaviour —
with the sharpest possible instance of it. The round *before* this one hardened
the same guard twice, adding an alphabet check and a length check to a parameter
that arrived pre-trimmed. Strengthening a check downstream of a repair produces a
guard that is more convincing and no more able to fire.

**Consequence.** A weakened PKCE binding in the service whose stated job is to
teach E1's client what a strict provider does, plus two echo semantics broken in
the direction a client reads as its own CSRF or replay check failing. Every one
of them was reachable by any client and none was reachable by any test.

**Rule.** **Validate what arrived, and only reject — never repair.** For every
check, ask what happened to the value between the socket and the check: a guard
whose input passed through `.strip()`, `.lower()`, `.replace()`, a
`urlsplit`-and-rebuild or a type coercion upstream is a guard checking a value
that never existed on the wire.

Where a presence test genuinely wants trimming — "three spaces is not a `state`"
— trim *for that test only* and hand the raw value onward. And treat any
parameter with **echo semantics** as untouchable: a value the protocol requires
back byte for byte, or that a signature or a digest is computed over, must reach
the comparison exactly as it arrived, because there the repair is not leniency —
it is a different value returned under the client's name.
