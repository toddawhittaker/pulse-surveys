-- The one door into identity, in two calls, and the record is not the caller's
-- to discard — tickets E0-10 and E0-26 item 1.
--
-- SPEC §4: "Traceability exists for safety, not oversight. Re-identification is
-- possible only through the Care queue (§6.2), only by the Care role, and every
-- identity access is automatically audit-logged with actor, timestamp, and
-- case."
--
-- **What replaced what, and why.** E0-10 shipped one function that returned
-- identity and wrote the audit row in the caller's transaction. Postgres has
-- already streamed the result rows to the client by the time the caller decides
-- what to do with that transaction, so
--
--     BEGIN;
--     SELECT * FROM public.reveal_student_identity(<a real CARE person id>,
--                                                  <any user id>, NULL);
--     ROLLBACK;
--
-- returned the real name and email address and left audit_log at zero rows.
-- Reproduced twice on the pinned image during E0-10's review, with the controls
-- that make it a finding rather than a coincidence: a non-CARE actor was still
-- refused, and the identical call without the ROLLBACK did write the row. That is
-- a live gap in the guarantee §4 states, and E0-26 item 1 closes it.
--
-- plpgsql has no autonomous transaction, so the fix is structural rather than
-- plumbing. `dblink` and a loopback `postgres_fdw` would each write the record
-- over a second connection that commits independently, and both were rejected on
-- 2026-08-18: each puts a database credential *inside* a SECURITY DEFINER
-- function, which is a new privilege surface of exactly the kind ADR 0043 exists
-- to keep small. **The door becomes two calls instead** (ADR 0071):
--
--   * public.record_identity_reveal records that a reveal is about to happen and
--     returns the audit_log row's id. The caller must COMMIT it.
--   * public.reveal_student_identity takes that id and nothing else, and returns
--     identity only against a record that is already committed.
--
-- A caller that rolls back therefore keeps no name: the rollback destroys the
-- record, and without a committed record the second call raises rather than
-- answering. The three-argument reveal is **dropped** by the revision that
-- executes this file rather than kept beside the new one — a door that still
-- opens the old way is not closed.
--
-- **What it costs, stated because a control whose price is unstated gets read as
-- free**: the log now over-records rather than under-records. A caller that
-- commits a record and then never spends it leaves a row saying an access was
-- authorised, and §6.2's periodic review reads that as an access. That is the
-- safe direction for a safety log and it is a real change in what a row means.
-- ADR 0071 argues it.
--
-- **This is deliberately the one hole in the wall**, so every line of both
-- functions is a control:
--
--   * SECURITY DEFINER, so identity is read and the record is written with the
--     owner's privileges — pulse_care itself holds no grant on
--     public.user_identity or public.audit_log, which is what makes this the only
--     route rather than the convenient one. **The owner is
--     pulse_reveal_definer**, a NOLOGIN role that holds four grants and exists
--     for nothing else, so "the definer's privileges" is a list you can read in
--     `identity_grants_v002.sql` against these two bodies. ADR 0043 records why,
--     and ADR 0071 records the fourth grant — SELECT on public.audit_log, which
--     the reveal needs because it now reads its subject and its actor out of the
--     committed record instead of taking them from its caller.
--   * `SET search_path = pg_catalog, public, pg_temp`, with pg_temp named and
--     named last. A plpgsql body is parsed on every call, and Postgres searches
--     the temporary schema first for relation names whether or not it appears in
--     the path — omitting it is what puts it first. ADR 0027 measured all four
--     combinations against E0-09's trigger; the two that omit pg_temp store the
--     write the guard exists to refuse.
--   * Every relation and every function schema-qualified, which is the half that
--     survives somebody later dropping the SET clause. A caller who can redirect
--     a name inside a SECURITY DEFINER function spends the definer's privileges
--     on a table of their own choosing — or, cheaper, empties an assignment
--     check.
--   * No caller-supplied SQL anywhere: typed parameters, no dynamic statement,
--     no format(), no EXECUTE.
--
-- **The CARE check is in the service and in both halves of the door, and that is
-- the design.** backend/app/services/safety.py verifies the actor independently
-- before it calls anything, record_identity_reveal verifies the actor it is
-- handed, and reveal_student_identity verifies the actor named by the record it
-- is spending. Neither alone: a caller reaching these functions by any other
-- route still gets nothing, and a routing mistake inside the service still gets
-- nothing. E0-10 says so in as many words, and E0-26 keeps it true across the
-- split — without the re-check, a committed record would be a bearer token,
-- recorded while its actor held CARE and spendable after the assignment was
-- revoked.
--
-- "Live" reads as "exists" today, because E0-09's role_assignment has no
-- end-dating — a revoked assignment is a deleted row. When E9 or E10 adds
-- validity dates both predicates gain them, and the sentence above stays true.
--
-- **What this still does not give**, unchanged by E0-26 and each carried to E10
-- with a ticket: the acting person is a parameter rather than a property of the
-- connection, so a holder of the pulse_care credential can record a reveal in
-- somebody else's name (E0-26 item 3); the record carries no conflict-of-interest
-- marking (item 2); and nothing here limits a record to being spent once.
--
-- E10 replaces this with the real audited reveal — the case model, the two-action
-- queue, the disposition note and §6.2's conflict-of-interest flag. What it
-- inherits is a door rather than a wall, which is the whole reason this ships
-- before there is a queue to open it from.


-- Half one. Records that a reveal is about to happen, and hands back the record's
-- id and nothing else — no identity, on any path. It is declared RETURNS uuid for
-- that reason: a caller that could obtain a name here would have no reason to
-- make the second call, and the whole exchange would be back inside one
-- transaction it can roll back.
CREATE FUNCTION public.record_identity_reveal(
    in_actor_person_id uuid,
    in_subject_user_id uuid,
    in_case_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_reveal_id uuid;
BEGIN
    -- Before the INSERT, so an actor who is refused writes nothing. The ordering
    -- is not observable from a caller — a RAISE aborts the transaction, so a row
    -- written first would be discarded anyway — and it is written this way
    -- because "check, then act" is the order somebody reading this has to be able
    -- to see.
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'CARE'
    ) THEN
        RAISE EXCEPTION
            'no reveal was recorded: the acting party % holds no live CARE assignment, '
            'and only the Care role may re-identify a student (SPEC 6.2)',
            in_actor_person_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- The foreign keys on audit_log do real work here: an actor who is not in the
    -- people graph, or a subject who is not a known LMS user, is refused by the
    -- record rather than revealed without one. Nothing checks that the subject
    -- has a user_identity row — they legitimately may not, the reveal answers
    -- zero rows for that student, and a check here would be a second read of
    -- identity outside the audited call.
    INSERT INTO public.audit_log (action, actor_person_id, subject_user_id, case_id)
    VALUES ('IDENTITY_REVEAL', in_actor_person_id, in_subject_user_id, in_case_id)
    RETURNING id INTO v_reveal_id;

    RETURN v_reveal_id;
END;
$$;


-- Half two. Returns identity, and only against a record that is already
-- committed. It takes the record's id and nothing else, so the subject is read
-- from the record and cannot be substituted by the caller.
--
-- **Every refusal here raises rather than returning zero rows**, and that is a
-- criterion rather than a preference. Zero rows already means "this student has
-- no user_identity row", which is a legitimate answer that
-- backend/app/services/safety.py hands back as None — so a refusal that returned
-- nothing would reach §6.2's queue as "no identity on file" about a student the
-- queue is open on. A refusal that is indistinguishable from an absence is a
-- wrong answer wearing the right one's clothes, and each refusal below carries
-- its own SQLSTATE so a caller can tell them apart.
CREATE FUNCTION public.reveal_student_identity(in_reveal_id uuid)
RETURNS TABLE (identity_name text, identity_email text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_actor_person_id uuid;
    v_subject_user_id uuid;
    v_action public.audit_action;
    -- The 32-bit id of the transaction that wrote the record, and the same id
    -- with its epoch, which is what pg_xact_status takes.
    v_writer xid;
    v_writer_full xid8;
BEGIN
    SELECT recorded.actor_person_id,
           recorded.subject_user_id,
           recorded.action,
           recorded.xmin
      INTO v_actor_person_id, v_subject_user_id, v_action, v_writer
      FROM public.audit_log AS recorded
     WHERE recorded.id = in_reveal_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'identity was not revealed: there is no reveal record %', in_reveal_id
            USING ERRCODE = 'no_data_found';
    END IF;

    IF v_action <> 'IDENTITY_REVEAL' THEN
        RAISE EXCEPTION
            'identity was not revealed: record % is a % and not an IDENTITY_REVEAL',
            in_reveal_id, v_action
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- **The guard this ticket exists for.** A record the calling transaction has
    -- not committed is visible to that transaction and to nobody else, so
    -- answering against one would hand over a name whose record the caller can
    -- still discard with a ROLLBACK — which is precisely the finding E0-26 item 1
    -- closes.
    --
    -- Comparing recorded.xmin against pg_current_xact_id() is the obvious way to
    -- write this and it is wrong: a caller that wraps the recording call in a
    -- SAVEPOINT gives the row a *sub*transaction id, which differs from the
    -- top-level one, so the comparison decides the row belongs to somebody else
    -- and opens the door on a record that still vanishes on ROLLBACK. A savepoint
    -- is not exotic — SQLAlchemy's begin_nested, plpgsql's own
    -- BEGIN … EXCEPTION block and psql's \set ON_ERROR_ROLLBACK each open one.
    --
    -- pg_xact_status answers the question directly and is not defeated by that:
    -- it reports "in progress" for the calling transaction *and every
    -- subtransaction of it*, and "committed" only once the top-level transaction
    -- has committed. Measured on the pinned image, plain and inside a released
    -- savepoint. It is a pg_catalog function executable by PUBLIC, so it needs no
    -- grant of its own.
    --
    -- It takes a 64-bit id and recorded.xmin is the 32-bit one, which carries no
    -- epoch. The epoch is taken from the current snapshot's xmax: every
    -- transaction whose row is visible here completed before that snapshot, so it
    -- belongs to the same epoch. A record from an earlier epoch is one written
    -- more than 2^32 transactions ago — it is committed, and reading it as a
    -- transaction of this epoch says so or raises, both of which are answers this
    -- function is allowed to give. Nothing here can read an uncommitted record as
    -- committed, which is the direction that matters.
    v_writer_full := (
        pg_catalog.div(
            pg_catalog.pg_snapshot_xmax(pg_catalog.pg_current_snapshot())::text::numeric,
            4294967296
        ) * 4294967296 + v_writer::text::numeric
    )::text::xid8;

    IF pg_catalog.pg_xact_status(v_writer_full) IS DISTINCT FROM 'committed' THEN
        RAISE EXCEPTION
            'identity was not revealed: reveal record % is not committed, so the caller '
            'could still discard the record of this access (SPEC 4)', in_reveal_id
            USING ERRCODE = 'object_not_in_prerequisite_state';
    END IF;

    -- The actor is re-checked against the record rather than trusted because the
    -- record exists. Without this a committed record is a bearer token: written
    -- while its actor held CARE, spent afterwards by whoever holds the pulse_care
    -- credential. §2.1 has no end-dating, so deleting the assignment row is what
    -- revoking it means today.
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = v_actor_person_id
           AND acting.role = 'CARE'
    ) THEN
        RAISE EXCEPTION
            'identity was not revealed: the acting party % named by reveal record % holds '
            'no live CARE assignment, and only the Care role may re-identify a student '
            '(SPEC 6.2)', v_actor_person_id, in_reveal_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Zero rows where the student has no identity on file, which is an ordinary
    -- state and not a refusal: an LMS user Pulse has seen but whose name never
    -- arrived over NRPS. One row with a null identity_email where the platform
    -- released no address. Neither is read with INTO STRICT, and neither raises.
    RETURN QUERY
    SELECT revealed.identity_name, revealed.identity_email
      FROM public.user_identity AS revealed
     WHERE revealed.user_id = v_subject_user_id;
END;
$$;
