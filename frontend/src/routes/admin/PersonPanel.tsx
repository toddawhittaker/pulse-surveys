import { useEffect, useId, useRef, useState, type FormEvent, type JSX } from 'react';

import {
  GRANTABLE_ROLES,
  editPerson,
  grantRole,
  linkWebLogin,
  readReportsToOptions,
  revokeRole,
  setReportsTo,
  unlinkWebLogin,
  type AssignmentLineView,
  type AssignmentRole,
  type PersonLineView,
  type ReportsToOptionView,
} from '../../api/admin';
import { copy, fillCopy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';
import { nodeText, type NodeLabels } from './nodeLabels';
import { settle } from './outcome';

/** Where a spec finds the panel. */
export const PERSON_PANEL_TESTID = 'pulse-admin-person-panel';

type Props = {
  readonly person: PersonLineView;
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onChanged: () => void;
  readonly onClose: () => void;
  readonly labels: NodeLabels;
};

export function roleLabel(role: AssignmentRole): string {
  return copy(`admin_people.page.role_${role}`);
}

/**
 * Everything the admin can change about one person: their name and category,
 * the roles they hold, whom each role reports to, and their web login.
 *
 * **Nothing here decides what is allowed.** The role control offers every role
 * the server will grant, the reports-to selector lists what the server offers
 * for that role, and each refusal (a revoke that leaves others reporting to the
 * role, a login linked to somebody else) is shown in the server's sentence with
 * nothing removed.
 */
/** The place an assignment is held at, if its node's name has arrived. */
function placeOf(labels: NodeLabels, assignment: AssignmentLineView): string | null {
  return labels.labelOf(assignment.scope_node_id);
}

/** An assignment as a person reads it: its role, and where it is held once that is known. */
function assignmentText(labels: NodeLabels, assignment: AssignmentLineView): string {
  const place = placeOf(labels, assignment);
  return place === null
    ? roleLabel(assignment.role)
    : fillCopy('admin_people.page.assignment_at', { role: roleLabel(assignment.role), place });
}

export function PersonPanel({
  person,
  announce,
  onGate,
  onChanged,
  onClose,
  labels,
}: Props): JSX.Element {
  const id = useId();
  const [name, setName] = useState(person.name);
  const [category, setCategory] = useState(person.category);
  const [role, setRole] = useState<AssignmentRole>(GRANTABLE_ROLES[0] ?? 'ADMIN');
  const [node, setNode] = useState('');
  const nodes = labels.nodesFor(role);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const rolesHeadingRef = useRef<HTMLHeadingElement>(null);
  const loginHeadingRef = useRef<HTMLHeadingElement>(null);
  const [issuer, setIssuer] = useState('');
  const [subject, setSubject] = useState('');

  // Opening the panel moves the reader into it: the control that opened it is
  // still where focus is, and a keyboard or screen-reader user would otherwise
  // have to find that something appeared.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // The places a role is granted at depend on the role, and the server says which.
  const { ensure } = labels;
  useEffect(() => {
    ensure(role);
  }, [ensure, role]);
  const heldRoles = [...new Set(person.assignments.map((assignment) => assignment.role))].join();
  useEffect(() => {
    for (const held of heldRoles === '' ? [] : (heldRoles.split(',') as AssignmentRole[])) {
      ensure(held);
    }
  }, [ensure, heldRoles]);

  async function submit(
    event: FormEvent,
    send: () => Promise<Parameters<typeof settle>[0]>,
    done: string,
  ): Promise<boolean> {
    event.preventDefault();
    const landed = settle(await send(), done, announce, onGate);
    if (landed) onChanged();
    return landed;
  }

  async function revoke(assignment: AssignmentLineView): Promise<void> {
    if (
      settle(
        await revokeRole(assignment.assignment_id),
        copy('admin_people.page.role_revoked'),
        announce,
        onGate,
      )
    ) {
      // The button pressed is about to leave; focus goes to the list's heading.
      rolesHeadingRef.current?.focus();
      onChanged();
    }
  }

  return (
    <section
      className="pulse-admin-section pulse-admin-panel"
      data-testid={PERSON_PANEL_TESTID}
      aria-labelledby={`${id}-heading`}
    >
      <h2 className="pulse-admin-subheading" id={`${id}-heading`} tabIndex={-1} ref={headingRef}>
        {fillCopy('admin_people.page.manage_heading', { name: person.name })}
      </h2>

      <form
        className="pulse-admin-form"
        onSubmit={(event) =>
          void submit(
            event,
            () => editPerson(person.person_id, name, category),
            copy('admin_people.page.person_saved'),
          )
        }
      >
        <Field id={`${id}-name`} label={copy('admin_people.page.field_name')}>
          <input
            id={`${id}-name`}
            className="pulse-admin-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id={`${id}-category`} label={copy('admin_people.page.field_category')}>
          <input
            id={`${id}-category`}
            className="pulse-admin-input"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          />
        </Field>
        <button type="submit" className="pulse-admin-button">
          {copy('admin_people.page.save_person')}
        </button>
      </form>

      <h3 className="pulse-admin-diff-heading" tabIndex={-1} ref={rolesHeadingRef}>
        {copy('admin_people.page.assignments_heading')}
      </h3>
      {person.assignments.length === 0 ? (
        <p className="pulse-admin-help">{copy('admin_people.page.no_roles')}</p>
      ) : (
        <ul className="pulse-admin-assignments">
          {person.assignments.map((assignment) => (
            <li key={assignment.assignment_id} className="pulse-admin-assignment">
              <span className="pulse-admin-role">{assignmentText(labels, assignment)}</span>
              <ReportsToSelect
                assignment={assignment}
                text={assignmentText(labels, assignment)}
                announce={announce}
                onGate={onGate}
                onChanged={onChanged}
              />
              <button
                type="button"
                className="pulse-admin-button-plain"
                onClick={() => void revoke(assignment)}
              >
                {placeOf(labels, assignment) === null
                  ? fillCopy('admin_people.page.revoke', { role: roleLabel(assignment.role) })
                  : fillCopy('admin_people.page.revoke_at', {
                      role: roleLabel(assignment.role),
                      place: placeOf(labels, assignment) ?? '',
                    })}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="pulse-admin-form"
        onSubmit={(event) =>
          void submit(
            event,
            () => grantRole(person.person_id, role, node),
            copy('admin_people.page.role_granted'),
          )
        }
      >
        <h3 className="pulse-admin-diff-heading">{copy('admin_people.page.grant_heading')}</h3>
        <Field id={`${id}-role`} label={copy('admin_people.page.field_role')}>
          <select
            id={`${id}-role`}
            className="pulse-admin-input"
            value={role}
            onChange={(event) => {
              setRole(event.target.value as AssignmentRole);
              setNode('');
            }}
          >
            {GRANTABLE_ROLES.map((offered) => (
              <option key={offered} value={offered}>
                {roleLabel(offered)}
              </option>
            ))}
          </select>
        </Field>
        <Field id={`${id}-node`} label={copy('admin_people.page.field_node')}>
          <select
            id={`${id}-node`}
            className="pulse-admin-input"
            value={node}
            required
            onChange={(event) => setNode(event.target.value)}
          >
            <option value="">{copy('admin_people.page.node_choose')}</option>
            {nodes.map((choice) => (
              <option key={choice.node_id} value={choice.node_id}>
                {nodeText(choice)}
              </option>
            ))}
          </select>
        </Field>
        <button type="submit" className="pulse-admin-button">
          {copy('admin_people.page.grant_submit')}
        </button>
      </form>

      <h3 className="pulse-admin-diff-heading" tabIndex={-1} ref={loginHeadingRef}>
        {copy('admin_people.page.login_heading')}
      </h3>
      {person.web_login_linked ? (
        <button
          type="button"
          className="pulse-admin-button-plain"
          onClick={() =>
            void unlinkWebLogin(person.person_id).then((answer) => {
              if (settle(answer, copy('admin_people.page.login_was_unlinked'), announce, onGate)) {
                loginHeadingRef.current?.focus();
                onChanged();
              }
            })
          }
        >
          {copy('admin_people.page.unlink_submit')}
        </button>
      ) : (
        <form
          className="pulse-admin-form"
          onSubmit={(event) =>
            void submit(
              event,
              () => linkWebLogin(person.person_id, issuer.trim(), subject.trim()),
              copy('admin_people.page.login_was_linked'),
            ).then((landed) => {
              // The form is about to be replaced by the unlink control.
              if (landed) loginHeadingRef.current?.focus();
            })
          }
        >
          <Field id={`${id}-issuer`} label={copy('admin_people.page.field_issuer')}>
            <input
              id={`${id}-issuer`}
              className="pulse-admin-input"
              value={issuer}
              onChange={(event) => setIssuer(event.target.value)}
            />
          </Field>
          <Field id={`${id}-subject`} label={copy('admin_people.page.field_subject')}>
            <input
              id={`${id}-subject`}
              className="pulse-admin-input"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
          </Field>
          <button type="submit" className="pulse-admin-button">
            {copy('admin_people.page.link_submit')}
          </button>
        </form>
      )}

      <div className="pulse-admin-row">
        <button type="button" className="pulse-admin-button-plain" onClick={onClose}>
          {copy('admin_people.page.close_panel')}
        </button>
      </div>
    </section>
  );
}

/** A labelled field. */
export function Field({
  id,
  label,
  children,
}: {
  readonly id: string;
  readonly label: string;
  readonly children: JSX.Element;
}): JSX.Element {
  return (
    <div className="pulse-admin-field">
      <label className="pulse-admin-label" htmlFor={id}>
        {label}
      </label>
      {children}
    </div>
  );
}

/**
 * Whom one assignment reports to, chosen from what the server offers for its
 * role and from nothing else. The current parent is kept as a choice even when
 * the offer no longer lists it, so the control never shows a parent it cannot name.
 */
function ReportsToSelect({
  assignment,
  text,
  announce,
  onGate,
  onChanged,
}: {
  readonly assignment: AssignmentLineView;
  readonly text: string;
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onChanged: () => void;
}): JSX.Element {
  const id = useId();
  const [options, setOptions] = useState<readonly ReportsToOptionView[] | null>(null);
  // The choice is held here and sent by its own button: a select fires `change`
  // on every arrow key, and a write per keystroke is a change of context
  // nobody asked for (WCAG 3.2.2).
  const [choice, setChoice] = useState(assignment.reports_to ?? '');

  useEffect(() => {
    let live = true;
    void readReportsToOptions(assignment.role).then((answer) => {
      if (!live) return;
      if (answer.kind === 'ok') setOptions(answer.value);
      else if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
        onGate(answer.kind);
      } else announce(copy('admin_people.page.options_unavailable'));
    });
    return () => {
      live = false;
    };
  }, [assignment.role, announce, onGate]);

  const parent = assignment.reports_to;
  const listed = (options ?? []).some((option) => option.assignment_id === parent);

  return (
    <span className="pulse-admin-field-inline">
      <label className="pulse-admin-label" htmlFor={id}>
        {fillCopy('admin_people.page.reports_to_label', { assignment: text })}
      </label>
      <select
        id={id}
        className="pulse-admin-input"
        value={choice}
        disabled={options === null}
        onChange={(event) => setChoice(event.target.value)}
      >
        <option value="">{copy('admin_people.page.reports_to_none')}</option>
        {parent !== null && !listed ? (
          <option value={parent}>
            {fillCopy('admin_people.page.reports_to_option', {
              name: assignment.reports_to_name ?? '',
              role: assignment.reports_to_role === null ? '' : roleLabel(assignment.reports_to_role),
            })}
          </option>
        ) : null}
        {(options ?? []).map((option) => (
          <option key={option.assignment_id} value={option.assignment_id}>
            {fillCopy('admin_people.page.reports_to_option', {
              name: option.name,
              role: roleLabel(option.role),
            })}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="pulse-admin-button-plain"
        onClick={() =>
          void setReportsTo(assignment.assignment_id, choice === '' ? null : choice).then(
            (answer) => {
              if (settle(answer, copy('admin_people.page.reports_to_saved'), announce, onGate)) {
                onChanged();
              }
            },
          )
        }
      >
        {fillCopy('admin_people.page.save_reports_to', { assignment: text })}
      </button>
    </span>
  );
}
