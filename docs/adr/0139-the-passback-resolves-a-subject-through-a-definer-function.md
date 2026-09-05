# 0139 — The passback resolves a subject through a definer function

## Context

SPEC §3.4 posts a participation score to a platform's gradebook, and AGS 2.0
names the student in a Score by the LTI `sub` and by nothing else. So E3-06's
weekly sweep, which holds a `user` row id for every student it is about to post
for, has to be able to reach that row's subject. It cannot post anything without
it.

This system holds a `sub` in exactly one column — `user.lms_user_id`, the claim
verbatim — and the application connection is deliberately refused it. E1-10's
round-3 security review revoked `SELECT (lms_user_id)` from `pulse_app` and gave
the reason in one sentence: a connection able to read it can enumerate every
subject that ever launched and join a response back to the person who gave it.
That connection is the one every screen in the product runs on, so the revocation
is not about the passback — it is about what a compromise or a careless query
anywhere in the product can reach. `tests/integration/test_identity_grants.py`
holds the remaining column set as an equality, and
`tests/unit/test_no_service_reads_an_identity_table_directly.py`, which is
`invariant`-marked, refuses the read from the application side as well.

ADR 0094 already answered the mirror-image question. E1-12's launch door and
E1-11's roster sync both hold a subject and need the row, and both go through a
`SECURITY DEFINER` function owned by `pulse_resolve_definer` — a NOLOGIN role
that exists for nothing else — which answers one point question while the caller
holds no read on the column. What is new here is the direction: the passback holds
the row and needs the subject.

## Decision

**A sixth sanctioned definer function, `public.resolve_subject_for_user(user_id
uuid) RETURNS text`**, shipped in `views_sql/identity_resolution_v002.sql` and
applied by revision `f3b7d05c9e42`. It is `SECURITY DEFINER`, `STABLE`, sets
`search_path = pg_catalog, public, pg_temp` with `pg_temp` named last, matches on
the primary key, and answers the row's `lms_user_id` or NULL for an id that names
no row. `EXECUTE` is revoked from `PUBLIC` and granted to `pulse_app`.

**The owner gains nothing, and that is the pin this record rests on.**
`pulse_resolve_definer` already holds `SELECT (id, lti_platform_id, lms_user_id)`
on `user`, because `resolve_platform_user` matches on exactly those columns. So
this file issues no `GRANT` on any table and creates no role: it opens a new
*direction* through an unchanged blast radius. An entry appearing in
`RESOLVE_DEFINER_COLUMN_PRIVILEGES` in this ticket's name would mean the opposite
— that the door reaches something the five columns did not — and that inventory is
expected to stay green across E3-06, before the migration and after it.

**NULL is a defined answer rather than an error.** The sweep walks enrollments and
a row can go missing between the walk and the read, so the caller branches on it
and steps over that student instead of failing the section it is in the middle of.
Matching on the primary key is what makes NULL honest: a body written as a join
with a `LIMIT 1` would answer *some* row's subject for an id matching none, which
is right against a demo database with one user and posts one student's score under
another student's identifier against a term's worth of data.

**The Python caller is `app.services.identity.subject_for_user`**, beside the three
that were already there, and `app/services/grading.py` reads no column of `user` by
any route.

## Alternatives rejected

**Re-granting `SELECT (lms_user_id)` on `user` to `pulse_app`.** Two lines, no
migration ceremony, and it is the change somebody reaches for the moment the sweep
cannot resolve a subject. It undoes E1-10's round-3 fix wholesale: the join goes
back inside reach of every query the product runs, on the connection every screen
uses, for the sake of one background job. The narrowness of what is actually needed
— one row's value, from a caller that already holds the row's id — is exactly what
a column grant cannot express.

**A worker-only database role.** A second login role for the Celery worker,
holding the column read that `pulse_app` does not, would keep the revoked property
intact for the API process — a compromise of a request path would still be unable
to enumerate subjects, which is the half of the threat model that matters most and
is a real thing to buy. It is not taken here because of what it costs for one
function's need: a second role to create, grant and keep in step, a second database
URL in the configuration surface and in every deployment, a second connection pool,
and a privilege inventory that has to be asserted twice for every table in the
schema rather than once. It also moves rather than removes the enumeration — the
worker would hold it — and the worker runs the same `app/services/` modules the
API does, so the application-side sweep would have to grow a per-process rule to
stay meaningful. If a later epic gives the worker its own role for reasons of its
own, this function is the right size to move behind it.

**Copying the subject onto a table `pulse_app` may read** — a column on
`enrollment`, or a passback-owned projection. It reads as the smallest change and
it is a second copy of identity data: two places a `sub` can be, which drift, and a
new table for §4's retention and §8's grants to reason about. ADR 0001's split
exists so there is one place, and the answer to "which copy is right" should never
be a question anyone has to ask.

**Leaving the sweep unable to post, and rendering scores some other way.** SPEC
§3.4 posts to the platform's gradebook; there is no other way for a score to reach
a student in v1, and E3 renders none itself.

## Consequences

- **A caller able to enumerate `user.id` can now map ids to subjects, one call at
  a time, through one auditable function.** `pulse_app` holds `SELECT (id)` on
  `user`, so that describes it. This is part of what E1-10's revocation bought,
  given back deliberately for exactly this need — stated plainly here rather than
  left to be discovered, because the honest reading of this decision is that the
  property is narrowed rather than preserved. What is bought back for it is that
  the disclosure has a name, a signature, an owner and an inventory entry, instead
  of being a column any query can join to.
- **Names remain unreachable.** A subject is pseudonymous: it identifies a person
  only to the platform that issued it. `user_identity` is refused to `pulse_app` by
  every mechanism this scheme has, `person.identity_name` is not among the five
  columns this function's owner holds, and the Care door stays the only route to a
  name.
- **The inventory's warning now aims at a seventh entry.**
  `SANCTIONED_APPLICATION_EXECUTE` said that a sixth entry appearing in it would be
  "a new door into identity that some later ticket opened without arguing for it".
  This is the sixth, argued for here; the sentence is unchanged and points one
  further along.
- The sweep costs one statement per student it is about to post for, which is a
  point lookup beside an HTTP call. A batch resolver would be cheaper and would be
  a function that returns a set, which is the shape this mechanism exists not to
  have.
- A downgrade of `f3b7d05c9e42` drops the function and leaves the role, its column
  grants and the four other resolvers untouched, so a database walked back to
  `e5b83c60f7a1` keeps every forward door and loses only the passback's.
