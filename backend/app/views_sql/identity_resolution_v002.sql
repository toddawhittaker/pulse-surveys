-- The reverse point lookup: a `user` row id to the platform's own subject —
-- ticket E3-06, SPEC §3.4, SPEC §4, ADR 0094, ADR 0139.
--
-- `identity_resolution_v001.sql` answers the forward question — this subject, at
-- this registration, is which stored row — and it is the shape every door has
-- needed until now: a caller holds a subject from a token it verified or a roster
-- document it fetched, and wants the row. E3-06's grade passback is the first
-- caller that holds the row and wants the subject. SPEC §3.4 posts a
-- participation score to a platform's gradebook, and AGS 2.0 names the student
-- in that score by the LTI `sub` and by nothing else, so the sweep cannot post
-- anything without it.
--
-- The column that answers it, `user.lms_user_id`, is exactly the one E1-10's
-- round-3 review revoked from `pulse_app`: "a connection able to read it can
-- enumerate every subject that ever launched and join a response back to the
-- person who gave it". That revocation stands. So this is ADR 0094's third
-- mechanism used once more, in the other direction — a SECURITY DEFINER function
-- answers one point question, this row's subject, while the connection holds no
-- read on the column at all.
--
-- **The owner does not change and gains nothing.** `pulse_resolve_definer` is
-- created and granted by `identity_resolution_v001.sql`, and the two columns this
-- body reads — `user.id` and `user.lms_user_id` — are already among the five it
-- holds, because `resolve_platform_user` matches on exactly those. So this file
-- creates no role and issues no `GRANT` on any table: it opens a new *direction*
-- through an unchanged blast radius, which is the pin ADR 0139 rests on and which
-- `test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers`
-- keeps green across this ticket. A new column grant appearing there would mean
-- the door reaches something the five columns did not.
--
-- **What is given back, said plainly, and it is more than a point lookup.** A
-- scalar function is callable per row inside a `SELECT`, so a caller composing its
-- own queries can join this against `user` and read a whole table's worth of
-- subjects — and `pulse_app` holds `SELECT (id)` on `user`, so it has the ids to
-- do it with. **This door is therefore not enumeration resistance**, and calling
-- it one would be containment theater: for a caller that writes SQL it is as wide
-- as the column was. E3-06's security round found the earlier wording here
-- claiming otherwise, and the honest claim is narrower.
--
-- Two things are bought, and they are the reason this shape was chosen over
-- re-granting the column. **Auditability**: the disclosure has a signature, an
-- owner, an inventory entry, an ADR and a name a reviewer can grep for, instead of
-- being a column any join can pick up unremarked in a module nobody is reviewing
-- for it. And **the line at a name**: what comes back is a pseudonymous identifier
-- the issuing platform assigned, while `user_identity` and `person.identity_name`
-- stay refused to `pulse_app` by every mechanism this scheme has.
--
-- **The body is deliberately not narrowed** — no `EXISTS` against a live
-- enrollment, no section argument. ADR 0139 records why: a guard like that still
-- resolves nearly every student the data holds, while widening this owner's own
-- read surface to `enrollment` and breaking the pinned privilege equality that is
-- the one thing here anybody can check.
--
-- **NULL is a defined answer, not an error.** The sweep walks enrollments and a
-- `user` row can go missing between the walk and the read, so "no such row" has
-- to be a value the caller branches on. The body matches on the primary key, so
-- it answers one row or none — never somebody else's subject.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, the parameter is typed, and there
-- is no dynamic SQL.

CREATE OR REPLACE FUNCTION public.resolve_subject_for_user(
    in_user_id uuid
)
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT known.lms_user_id
      FROM public."user" AS known
     WHERE known.id = in_user_id;
$$;

ALTER FUNCTION public.resolve_subject_for_user(uuid)
    OWNER TO pulse_resolve_definer;

REVOKE ALL ON FUNCTION public.resolve_subject_for_user(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.resolve_subject_for_user(uuid) TO pulse_app;
