-- A `moderation_state` row with no decider is the router's alone — E6-03, ADR 0189.
--
-- Since E6-03 `pulse_app` may insert `answer_id` and `state` (among the six
-- columns a decision writes, `moderation_decision_grants_v001.sql`), and the
-- table's `CHECK`s accept a decider-less `FLAGGED_COLLAPSED` row, because that is
-- the routing definer's flag. Together those would let the application
-- connection write a flag no moderation verdict opened: a comment hidden from
-- students with no verdict behind it and nobody on record as deciding it.
--
-- So this trigger refuses a row whose `decided_by_person_id` is NULL unless
-- `current_user` is `pulse_moderation_definer`, the pattern E6-01's
-- `classification_moderation_row_only_through_its_door` holds on
-- `classification`. A trigger function runs as the role whose statement fired
-- it, so inside `public.route_moderation_verdict` (a `SECURITY DEFINER` owned by
-- that role) `current_user` is the definer and the router's own flag passes;
-- every other role, `pulse_app`, seeds, fixtures and the bootstrap superuser
-- included, has to name a decider. The check is on `current_user` and not on
-- `session_user`, which is still the caller inside the definer's body and would
-- refuse the router itself.
--
-- Insert only: nothing may update this table (no role but the owner holds
-- `UPDATE`), and the record is append-only.
--
-- SET search_path names pg_temp last (ADR 0027), and there is no dynamic SQL.

CREATE OR REPLACE FUNCTION public.moderation_state_router_rows_only_from_the_router()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NEW.decided_by_person_id IS NULL AND current_user <> 'pulse_moderation_definer' THEN
        RAISE EXCEPTION 'a moderation_state row with no decider is written only by public.route_moderation_verdict'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER moderation_state_router_rows_only_from_the_router
    BEFORE INSERT ON public.moderation_state
    FOR EACH ROW
    EXECUTE FUNCTION public.moderation_state_router_rows_only_from_the_router();
