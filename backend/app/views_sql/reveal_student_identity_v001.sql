-- The one door into identity, and it writes its own record — ticket E0-10.
--
-- SPEC §4: "Traceability exists for safety, not oversight. Re-identification is
-- possible only through the Care queue (§6.2), only by the Care role, and every
-- identity access is automatically audit-logged with actor, timestamp, and
-- case." ADR 0001 settles the mechanism: one SECURITY DEFINER function that
-- returns identity and writes the audit row in the same transaction, so the two
-- cannot come apart. Logging as a separate step afterwards was rejected there,
-- because it makes the audit trail a convention a future code path can skip.
--
-- **This is deliberately the one hole in the wall**, so every line of it is a
-- control:
--
--   * SECURITY DEFINER, so it reads public.user_identity with its owner's
--     privileges — pulse_care itself holds no grant on that table, which is what
--     makes this the only route rather than the convenient one. **Its owner is
--     pulse_reveal_definer**, a NOLOGIN role that holds three grants and exists
--     for nothing else, so "the definer's privileges" is a list you can read in
--     `identity_grants_v001.sql` rather than whatever the migration ran as. ADR
--     0043 records why, and the difference is not academic: applied as written
--     but owned by the migration identity, a caller of this function is running
--     as a superuser, and a probe function built that way read every row of
--     pg_authid for a pulse_care caller that is refused that table directly.
--   * `SET search_path = pg_catalog, public, pg_temp`, with pg_temp named and
--     named last. A plpgsql body is parsed on every call, and Postgres searches
--     the temporary schema first for relation names whether or not it appears in
--     the path — omitting it is what puts it first. ADR 0027 measured all four
--     combinations against E0-09's trigger; the two that omit pg_temp store the
--     write the guard exists to refuse.
--   * Every relation schema-qualified, which is the half that survives somebody
--     later dropping the SET clause. A caller who can redirect a name inside a
--     SECURITY DEFINER function spends the definer's privileges on a table of
--     their own choosing — or, cheaper, empties the assignment check below.
--   * No caller-supplied SQL anywhere: three typed parameters, no dynamic
--     statement, no format(), no EXECUTE.
--
-- **The CARE check is here as well as in the service, and that is the design.**
-- backend/app/services/safety.py verifies the actor independently before it
-- calls this, and this verifies for itself. Neither alone: a caller reaching this
-- function by any other route still gets nothing, and a routing mistake inside
-- the service still gets nothing. E0-10 says so in as many words.
--
-- "Live" reads as "exists" today, because E0-09's role_assignment has no
-- end-dating — a revoked assignment is a deleted row. When E9 or E10 adds
-- validity dates this predicate gains them, and the sentence above stays true.
--
-- **The audit row is written before the identity is read**, so an actor whose
-- INSERT is refused never reaches the SELECT. The foreign keys on audit_log do
-- real work here: an actor who is not in the people graph, or a subject who is
-- not a known LMS user, is refused by the record rather than revealed without
-- one.
--
-- E10 replaces this with the real audited reveal — the case model, the two-action
-- queue, the disposition note and §6.2's conflict-of-interest flag. What it
-- inherits is a door rather than a wall, which is the whole reason this ships
-- before there is a queue to open it from.

CREATE FUNCTION public.reveal_student_identity(
    in_actor_person_id uuid,
    in_subject_user_id uuid,
    in_case_id uuid
)
RETURNS TABLE (identity_name text, identity_email text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'CARE'
    ) THEN
        RAISE EXCEPTION
            'identity was not revealed: the acting party % holds no live CARE assignment, '
            'and only the Care role may re-identify a student (SPEC 6.2)',
            in_actor_person_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.audit_log (action, actor_person_id, subject_user_id, case_id)
    VALUES ('IDENTITY_REVEAL', in_actor_person_id, in_subject_user_id, in_case_id);

    RETURN QUERY
    SELECT revealed.identity_name, revealed.identity_email
      FROM public.user_identity AS revealed
     WHERE revealed.user_id = in_subject_user_id;
END;
$$;
