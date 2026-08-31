# Entry 31. "Running it twice is safe" was tested only against a database the loader itself had filled

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** `scripts/seed.py` is idempotent by matching each row on a
natural key and re-using what it finds. Two tests asserted it: seed, seed again,
compare every row. Both passed, every time, and neither could ever have failed —
the database they ran against was created for the module and written to by
nothing but the seed, so "the rows I find" and "the rows I wrote" were the same
set by construction.

The key for `prefix` was `code`, which is `UNIQUE` across the whole table rather
than per institution (ADR 0017). Against a database that already held a real
institution — which is what E1's roster sync will produce — the seed did not
create a prefix, it **adopted** one: `MATH` was re-pointed at the demo's
Mathematics department, the real `MATH 210` underneath it was then reached by
`(prefix_id, lms_number)` and its title overwritten, and its lead-faculty mapping
was replaced by a demo person. The run exited 0 and printed its success line.

**Root cause.** Idempotency is a claim about a *second* run's interaction with
whatever is already in the database. A fixture that starts empty tests only the
loader's interaction with itself, which is the easy half and the half that
cannot fail. Nothing in the suite ever put a row the loader did not write in
front of it.

**Consequence.** Purview is computed from the containment tree and from
`lead_faculty_mapping`, so demo leadership gained purview over real courses and
the real lead lost the mapping that granted theirs — silently, and surfacing much
later as a scoping bug hunted in `authz.py`. The records made it worse rather than
better: `README.md` promised "a second run writes nothing", and ADR 0064 listed
the natural keys without noting that this one, alone, was scoped to nothing.

**Rule.** **Test an idempotent loader against rows it did not write.** Before a
second-run test means anything, put a foreign row in its way — one that shares
the natural key the loader matches on — and assert what the loader does with it.
The interesting answer is usually "refuse", and a loader that has never been
shown a foreign row has not been asked the question.

The design half, which is cheaper than the test half and catches it earlier:
**every natural key must be scoped to a row the loader created, or be a value the
loader invented.** Walk the list and classify each one. A key that is neither —
a globally unique column holding a name the outside world also uses — is an
adoption waiting to happen, and it does not look like one in a table of keys.

---

**2026-08-25, E1-05 (`e1/registration-columns`).** The ticket adds
`authorization_endpoint` to `lti_platform` and the seed's upsert has to write it
on a **matched** row, not only on an insert — every development database already
holds the mock's registration from before the column existed, and a launch from
the mock is refused until it is filled. My own verification was going to be:
run the seed, read the column back. That proves nothing, for this entry's exact
reason — the row I would have found is the row I had just written, and an upsert
that never touches a matched row passes it.

What I did instead: planted an old-shape row as the superuser, with
`authorization_endpoint` NULL and `lti_platform` otherwise empty, and only then
ran `python scripts/seed.py`. The column came back filled **and the row kept its
id**, which is the second half — `user` and `lti_deployment` both key to that
row, so a seed that completed the registration by replacing it would have taken
a development database's launches with it.

Without this entry I would have reported the matched-row path verified having
never exercised it, in a ticket whose whole upgrade story is that path.
