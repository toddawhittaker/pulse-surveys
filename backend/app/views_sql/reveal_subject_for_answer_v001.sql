-- The third function of the Care door: which student wrote this comment —
-- ticket E4-01, SPEC §4, SPEC §6.2, ADR 0043, ADR 0071, ADR 0094, ADR 0144.
--
-- **What it is for.** Until this ticket
-- `backend/app/services/safety.py::reveal_identity` took a `subject_user_id`
-- from whoever called it and checked only that the *actor* held a live CARE
-- assignment. `docs/tickets/e1/carried-from-e0.md` records what those two facts
-- compose into: `public.section_roster` hands instructor-scoped code the
-- `user_id` of every enrolled student, which is that view's whole point, and
-- §2.1 permits one person to hold a Care assignment and a teaching assignment at
-- once. So a Care officer who also teaches could take a key off her own roster,
-- reveal it, and leave an audit row indistinguishable from a legitimate access.
-- E4-01 deletes that parameter. The reveal now names the *record* Care is acting
-- on — one comment — and the subject is derived from it here:
-- `answer.response_id` to `response.user_id`.
--
-- **Why a function rather than a grant, which is the decision ADR 0144 exists
-- for.** The derivation runs on the `pulse_care` connection, and that connection
-- holds SELECT on exactly one base table, `public.role_assignment`, and on no
-- view at all. Granting it a read of `answer` and `response` — at either grain —
-- would hand the Care role a standing walk from any answer id to any user id
-- that works *outside* this door, with no record written and nothing in the
-- service in the way. Every refusal in `tests/integration/test_identity_grants.py`
-- is written against a Care connection whose own read surface is one table, and
-- a definer keeps it that way: the function answers, the caller reads nothing.
-- It is also ADR 0094's third mechanism used again, as E3-06's
-- `public.resolve_subject_for_user` used it, so the disclosure has a signature,
-- an owner, an inventory entry and a name a reviewer can grep for.
--
-- **It answers a key and never a name, which is what makes a third door not a
-- third way to obtain one.** `RETURNS uuid`, and the only column it selects is
-- `response.user_id` — a `public.user` row id. It reads no column of
-- `public.user_identity`, it reads no column of `public.person`, and there is no
-- path through it that returns a name or an address. That is the same argument
-- `public.record_identity_reveal` already carries, and it is the reason E0-10's
-- rule — "every additional door is a way to obtain a name without leaving a
-- record" — is not violated by a door that cannot obtain one. The record is
-- still written by `record_identity_reveal` and the name still comes only from
-- `reveal_student_identity`, against a record that has already committed.
--
-- **NULL is a defined answer rather than an error**, and the service is where it
-- becomes a refusal. An `answer_id` matching no row answers NULL here and
-- `app.services.safety` raises `UnknownRevealSubjectError` for it — a distinct
-- class from `NotCareStaffError`, so §6.2's queue can tell "you may not use this
-- door" from "that is not a record you can act on" without reading a message. A
-- database exception crossing that boundary would arrive as a `__cause__` that
-- quotes its parameters, which is what
-- `tests/integration/test_care_service_reveal.py::test_the_refusal_carries_no_part_of_the_students_identity`
-- exists to catch, so the refusal is deliberately in Python and the function
-- simply answers nothing.
--
-- The body matches on `answer.id`, which is the primary key, so it answers one
-- row or none — never somebody else's author.
--
-- **What this deliberately does not do: filter on a classification.** E4-01's
-- ticket recommends deriving the subject from a comment "whose latest
-- classification is in the threat or self-harm set". `public.classification`
-- exists, but `ClassificationTask` has exactly one member today —
-- `COMMENT_VALIDITY` — because the moderation task is E6's, and that enum's own
-- rule is that a member lands with the code that writes it. A predicate written
-- here against a verdict vocabulary nobody has produced yet would either refuse
-- every comment in the system or be a vocabulary this ticket invented for E6 to
-- inherit. ADR 0144 records the deferral, and it is a narrowing of this body when
-- E6 lands rather than a change to its signature.
--
-- **The controls, one per line of the body**, the same ones both halves of
-- `reveal_student_identity_v002.sql` carry and for the same reasons:
--
--   * SECURITY DEFINER, so the two reads are the owner's rather than the
--     caller's. The owner is `pulse_reveal_definer` — the role that already owns
--     the other two halves of this door. Not a new role: a `SECURITY DEFINER`
--     function spends its owner's privileges, so a second owner would be a second
--     privilege surface, and every rule in `test_identity_grants.py` about "what
--     the definer may reach" measures one set. ADR 0139 rejected a fifth NOLOGIN
--     role on the same ground — one holding a subset of an existing owner's
--     grants is a role to audit rather than a boundary.
--   * `SET search_path = pg_catalog, public, pg_temp`, with pg_temp named and
--     named **last**. ADR 0027 measured all four combinations: omitting pg_temp
--     is what puts it first, because Postgres searches the temporary schema for
--     relation names whether or not it appears in the path.
--   * Every relation schema-qualified, which is the half that survives somebody
--     later dropping the SET clause.
--   * `STABLE`, because it only reads. Not `IMMUTABLE`: the answer changes when
--     the rows do.
--   * No caller-supplied SQL: one typed parameter, no dynamic statement, no
--     `format()`, no `EXECUTE`.
--
-- **The owner's two new grants are column-scoped, and the grain is deliberate.**
-- `SELECT (id, response_id)` on `public.answer` and `SELECT (id, user_id)` on
-- `public.response` are exactly the four columns the body below reads. The
-- alternative — table-level SELECT on both — also works and is what
-- `has_table_privilege` can see, which is why
-- `test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs`
-- admits either. Column grain was chosen because it keeps `answer.comment_text`
-- out of the Care door's owner entirely: §6.2 gives Care the comment content
-- through the queue E10 builds, not through the function that turns a comment id
-- into a key, and the narrowest privilege that does the job is the answer to
-- question 3 of that test's own four-question test for a legitimate grant. The
-- cost is stated: a column-scoped grant lives in `pg_attribute.attacl`, where
-- `has_table_privilege` cannot see it, so the owner's equality cannot pin these
-- two the way it pins the other four — the behavioural tests in
-- `tests/integration/test_the_reveal_derives_its_subject.py` are what fail if
-- they are missing. ADR 0144 argues the trade.
--
-- **A function is the one kind of object that needs a REVOKE.** Postgres grants
-- EXECUTE on a new function to PUBLIC unless a migration says otherwise, and
-- every role in the cluster is a member of PUBLIC — `pulse_app` included, which
-- is the connection every instructor screen runs on. The REVOKE below is what
-- stops this being callable by the role this whole scheme exists to keep away
-- from a student's key.

CREATE FUNCTION public.reveal_subject_for_answer(in_answer_id uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT written.user_id
      FROM public.answer AS commented
      JOIN public.response AS written
        ON written.id = commented.response_id
     WHERE commented.id = in_answer_id;
$$;

GRANT SELECT (id, response_id) ON public.answer TO pulse_reveal_definer;
GRANT SELECT (id, user_id) ON public.response TO pulse_reveal_definer;

-- The owner change before the ACLs, so that no ACL entry ever names an owner the
-- function no longer has — the order `identity_grants_v002.sql` states and for
-- the same reason.
ALTER FUNCTION public.reveal_subject_for_answer(uuid) OWNER TO pulse_reveal_definer;

REVOKE ALL ON FUNCTION public.reveal_subject_for_answer(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.reveal_subject_for_answer(uuid) TO pulse_care;
