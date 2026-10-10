-- The one door a moderation verdict is written through — E6-01, SPEC §5.2,
-- §6.2, §7.4, §8, ADR 0043, ADR 0187.
--
-- **What one call does.** It writes one `MODERATION` row to
-- `public.classification` and, in the same call, that verdict's route:
--
--   * `harmful` or `privacy`: a `FLAGGED_COLLAPSED` row in
--     `public.moderation_state`, which puts the comment in front of a reviewer
--     (SPEC §5.2);
--   * `threat` or `self_harm`: a `public.threat_case` row naming the new
--     classification, which routes the comment to Care (SPEC §6.2). The table is
--     unique per comment, and a second Care-class verdict on a comment that
--     already has a case leaves that case alone, with no error, so a re-run of
--     moderation neither fails nor opens a second case;
--   * `clear` or `nonsense`: nothing more.
--
-- It answers the new classification's id.
--
-- **Why a function and not grants.** A grant cannot make two writes one.
-- `pulse_app` already inserts into `classification` (validity verdicts, E0-13),
-- so with `INSERT` on the two route tables beside it the application could store
-- a threat verdict with no case: a student at risk recorded and routed to nobody.
-- So `pulse_app` holds `EXECUTE` here, only `SELECT` on `moderation_state`, and
-- no privilege on `threat_case` at all.
--
-- **The verdict and its route land together or not at all.** There is no
-- exception handler: if the route's insert fails, the whole call fails and the
-- verdict's insert is rolled back with it. `ON CONFLICT (answer_id) DO NOTHING`
-- answers exactly one conflict, a second case for the same comment; any other
-- failure still raises.
--
-- **A `MODERATION` row cannot be written around this door.** The trigger below
-- refuses an insert or an update that leaves a row with `task = 'MODERATION'`
-- unless `current_user` is `pulse_moderation_definer`. Inside this function
-- `current_user` is the owner, so the door's own insert passes; every other role,
-- `pulse_app`, seeds, fixtures and the bootstrap superuser included, is refused.
-- The check is on `current_user` and not on `session_user`, which is still the
-- caller inside a `SECURITY DEFINER` body and would refuse the door itself.
--
-- **A NULL answer is refused.** `classification.answer_id` is nullable for rows
-- written before E2-08, and a moderation verdict about no comment would route
-- nothing anybody can read.
--
-- The owner is `pulse_moderation_definer`, a NOLOGIN role that exists for nothing
-- else (ADR 0043: one role per door). It holds `INSERT` on the three tables one
-- call writes, `SELECT (id)` on `classification` because `RETURNING id` reads
-- that column, and `SELECT (answer_id)` on `threat_case` because
-- `ON CONFLICT (answer_id)` reads the conflict column. Nothing on any person table. No other door's owner writes
-- any of these three tables, so reusing one would join two blast radii.
--
-- SET search_path names pg_temp last (ADR 0027), every relation is
-- schema-qualified, parameters are typed, and there is no dynamic SQL.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_moderation_definer'
    ) THEN
        CREATE ROLE pulse_moderation_definer NOLOGIN;
    END IF;
END
$do$;

GRANT INSERT ON public.classification TO pulse_moderation_definer;
GRANT SELECT (id) ON public.classification TO pulse_moderation_definer;
GRANT INSERT ON public.moderation_state TO pulse_moderation_definer;
GRANT INSERT ON public.threat_case TO pulse_moderation_definer;
GRANT SELECT (answer_id) ON public.threat_case TO pulse_moderation_definer;

CREATE OR REPLACE FUNCTION public.route_moderation_verdict(
    in_answer_id uuid,
    in_verdict text,
    in_prompt_version text,
    in_model_id text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    verdict_id uuid;
BEGIN
    IF in_answer_id IS NULL THEN
        RAISE EXCEPTION 'route_moderation_verdict needs the comment the verdict is about'
            USING ERRCODE = 'null_value_not_allowed';
    END IF;

    -- The task's vocabulary is the table's per-task CHECK; an unknown verdict is
    -- refused there, before any route is written.
    INSERT INTO public.classification (answer_id, task, verdict, prompt_version, model_id)
    VALUES (in_answer_id, 'MODERATION', in_verdict, in_prompt_version, in_model_id)
    RETURNING id INTO verdict_id;

    IF in_verdict IN ('harmful', 'privacy') THEN
        INSERT INTO public.moderation_state (answer_id, state)
        VALUES (in_answer_id, 'FLAGGED_COLLAPSED');
    ELSIF in_verdict IN ('threat', 'self_harm') THEN
        INSERT INTO public.threat_case (answer_id, classification_id)
        VALUES (in_answer_id, verdict_id)
        ON CONFLICT (answer_id) DO NOTHING;
    END IF;

    RETURN verdict_id;
END;
$$;

ALTER FUNCTION public.route_moderation_verdict(uuid, text, text, text)
    OWNER TO pulse_moderation_definer;

REVOKE ALL ON FUNCTION public.route_moderation_verdict(uuid, text, text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.route_moderation_verdict(uuid, text, text, text) TO pulse_app;

-- The wall beside the door. A trigger function runs as the role whose statement
-- fired it, so `current_user` here is whoever is inserting: the door's owner
-- when the insert comes from the function above, and the caller otherwise.
CREATE OR REPLACE FUNCTION public.classification_moderation_row_only_through_its_door()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NEW.task = 'MODERATION' AND current_user <> 'pulse_moderation_definer' THEN
        RAISE EXCEPTION 'a moderation verdict is written only through public.route_moderation_verdict'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER classification_moderation_row_only_through_its_door
    BEFORE INSERT OR UPDATE ON public.classification
    FOR EACH ROW
    EXECUTE FUNCTION public.classification_moderation_row_only_through_its_door();
