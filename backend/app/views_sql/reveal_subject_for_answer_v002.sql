-- Which student wrote this comment, for a comment routed to Care only — v002,
-- ticket E6-01, SPEC §4, §6.2, ADR 0144, ADR 0187.
--
-- Supersedes reveal_subject_for_answer_v001.sql, whose header argues the door:
-- why it is a function, why it answers a key and never a name, why NULL is the
-- refusal, and the controls on every line. All of that still holds and is not
-- restated. The signature, the owner (`pulse_reveal_definer`) and the one
-- grantee (`pulse_care`) are v001's.
--
-- **What changed: the door answers only for a comment holding a threat or
-- self-harm moderation verdict.** E4-01 deferred this narrowing to E6 because no
-- moderation verdict existed to filter on (ADR 0144). E6-01 adds the task and its
-- writer, so the predicate is written here: the comment must hold a
-- `MODERATION` classification whose verdict is `threat` or `self_harm`. Any such
-- verdict, ever, and not the latest one, for the reason report_comment_v004.sql
-- gives: a comment once routed to Care stays Care's.
--
-- **For any other comment the body answers NULL**, exactly as for an id that
-- names no comment, and `app.services.safety.reveal_identity` turns that into
-- `UnknownRevealSubjectError` before any record is written. So a refusal leaves
-- no `audit_log` row, and the door gives no signal that tells "no such comment"
-- from "a comment Care has no case for".
--
-- **The owner's new read is column-grained**, as v001's two were: `answer_id`,
-- `task` and `verdict` on `classification`, the three columns the predicate
-- reads. A verdict names no person; the door still returns only a `user` row id.

CREATE OR REPLACE FUNCTION public.reveal_subject_for_answer(in_answer_id uuid)
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
     WHERE commented.id = in_answer_id
       AND EXISTS (
           SELECT 1
             FROM public.classification AS routed_to_care
            WHERE routed_to_care.answer_id = commented.id
              AND routed_to_care.task = 'MODERATION'
              AND routed_to_care.verdict IN ('threat', 'self_harm')
       );
$$;

GRANT SELECT (answer_id, task, verdict) ON public.classification TO pulse_reveal_definer;

-- v001's owner and ACL, restated so that this file does not depend on what the
-- replaced function happened to carry.
ALTER FUNCTION public.reveal_subject_for_answer(uuid) OWNER TO pulse_reveal_definer;

REVOKE ALL ON FUNCTION public.reveal_subject_for_answer(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.reveal_subject_for_answer(uuid) TO pulse_care;
