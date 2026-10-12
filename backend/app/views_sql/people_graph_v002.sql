-- The record of an applied CSV import — E9-06's fix round, ADR 0204.
--
-- SPEC §8: "`audit_log` is append-only and includes all re-identifications,
-- imports (with their dry-run diffs), and admin config edits." The per-record
-- definers in `people_graph_v001.sql` audit each mapping change, but creating
-- and editing a person is not audited (ADR 0200), and nothing tied a mapping
-- import's rows to one import or recorded what the admin was shown. So the apply
-- calls this function once, inside its own transaction, after its writes and
-- before its commit: a refused or failed apply leaves no row, and a failed
-- insert here fails the apply. A dry run never calls it.
--
-- **One `IMPORT_APPLIED` row** naming the acting admin, with `detail` holding
-- `{"kind": <kind>, "diff": <diff>}`: the kind is `people` or `lead_mappings`,
-- and the diff is the one the dry run answered, without its digest. It names no
-- subject person, because an import is about many; `audit_log`'s checks admit
-- exactly that shape for this action and no other.
--
-- **The admin check is v001's**, refusing with the same key, and is worth what
-- v001's header says it is worth: `pulse_app` supplies the key, so the route is
-- the real check. What this function adds over a table grant is that `pulse_app`
-- still holds no privilege on `audit_log`, so it cannot write an import row, or
-- any other row, except through a definer that checked the key. The insert sits
-- in no exception block.
--
-- Owned by `pulse_people_graph_definer`, the owner of v001's twelve, which gains
-- `INSERT` on the one column this fills that v001's rows do not. SET search_path
-- names pg_temp last (ADR 0027), every relation is schema-qualified, parameters
-- are typed, and there is no dynamic SQL.

GRANT INSERT (detail) ON public.audit_log TO pulse_people_graph_definer;


CREATE FUNCTION public.admin_record_import(
    in_actor_person_id uuid,
    in_kind text,
    in_diff jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    IF in_kind IS NULL OR in_kind NOT IN ('people', 'lead_mappings') THEN
        RAISE EXCEPTION 'admin_people.import_kind_unknown' USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO public.audit_log (action, actor_person_id, detail)
    VALUES ('IMPORT_APPLIED', in_actor_person_id,
            jsonb_build_object('kind', in_kind, 'diff', in_diff));
END;
$$;

ALTER FUNCTION public.admin_record_import(uuid, text, jsonb) OWNER TO pulse_people_graph_definer;
REVOKE ALL ON FUNCTION public.admin_record_import(uuid, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_record_import(uuid, text, jsonb) TO pulse_app;
