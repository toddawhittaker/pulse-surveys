import { useEffect, useId, useState, type FormEvent, type JSX } from 'react';

import {
  GRANTABLE_ROLES,
  editPerson,
  grantRole,
  linkWebLogin,
  readOrgNodes,
  readReportsToOptions,
  revokeRole,
  setReportsTo,
  unlinkWebLogin,
  type AssignmentLineView,
  type AssignmentRole,
  type OrgNodeView,
  type PersonLineView,
  type ReportsToOptionView,
} from '../../api/admin';
import { copy, fillCopy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';
import { settle } from './outcome';

/** Where a spec finds the panel. */
export const PERSON_PANEL_TESTID = 'pulse-admin-person-panel';

type Props = {
  readonly person: PersonLineView;
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onChanged: () => void;
  readonly onClose: () => void;
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
export function PersonPanel({ person, announce, onGate, onChanged, onClose }: Props): JSX.Element {
  const id = useId();
  const [name, setName] = useState(person.name);
  const [category, setCategory] = useState(person.category);
  const [role, setRole] = useState<AssignmentRole>(GRANTABLE_ROLES[0] ?? 'ADMIN');
  const [node, setNode] = useState('');
  const [loaded, setLoaded] = useState<{
    readonly role: AssignmentRole;
    readonly nodes: readonly OrgNodeView[];
  } | null>(null);
  // Nodes read for another role are not this role's, so none show until its own arrive.
  const nodes = loaded !== null && loaded.role === role ? loaded.nodes : [];
  const [issuer, setIssuer] = useState('');
  const [subject, setSubject] = useState('');

  // The places a role is granted at depend on the role, and the server says which.
  useEffect(() => {
    let live = true;
    void readOrgNodes(role).then((answer) => {
      if (!live) return;
      if (answer.kind === 'ok') setLoaded({ role, nodes: answer.value });
      else if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
        onGate(answer.kind);
      } else announce(copy('admin_people.page.nodes_unavailable'));
    });
    return () => {
      live = false;
    };
  }, [role, announce, onGate]);

  async function submit(
    event: FormEvent,
    send: () => Promise<Parameters<typeof settle>[0]>,
    done: string,
  ): Promise<void> {
    event.preventDefault();
    if (settle(await send(), done, announce, onGate)) onChanged();
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
      onChanged();
    }
  }

  return (
    <section
      className="pulse-admin-section pulse-admin-panel"
      data-testid={PERSON_PANEL_TESTID}
      aria-labelledby={`${id}-heading`}
    >
      <h2 className="pulse-admin-subheading" id={`${id}-heading`}>
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

      <h3 className="pulse-admin-diff-heading">{copy('admin_people.page.assignments_heading')}</h3>
      {person.assignments.length === 0 ? (
        <p className="pulse-admin-help">{copy('admin_people.page.no_roles')}</p>
      ) : (
        <ul className="pulse-admin-assignments">
          {person.assignments.map((assignment) => (
            <li key={assignment.assignment_id} className="pulse-admin-assignment">
              <span className="pulse-admin-role">{roleLabel(assignment.role)}</span>
              <ReportsToSelect
                assignment={assignment}
                announce={announce}
                onGate={onGate}
                onChanged={onChanged}
              />
              <button
                type="button"
                className="pulse-admin-button-plain"
                onClick={() => void revoke(assignment)}
              >
                {fillCopy('admin_people.page.revoke', { role: roleLabel(assignment.role) })}
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
            onChange={(event) => setNode(event.target.value)}
          >
            <option value="">{copy('admin_people.page.node_choose')}</option>
            {nodes.map((choice) => (
              <option key={choice.node_id} value={choice.node_id}>
                {choice.parent_label === null
                  ? choice.label
                  : fillCopy('admin_people.page.node_option', {
                      name: choice.label,
                      parent: choice.parent_label,
                    })}
              </option>
            ))}
          </select>
        </Field>
        <button type="submit" className="pulse-admin-button">
          {copy('admin_people.page.grant_submit')}
        </button>
      </form>

      <h3 className="pulse-admin-diff-heading">{copy('admin_people.page.login_heading')}</h3>
      {person.web_login_linked ? (
        <button
          type="button"
          className="pulse-admin-button-plain"
          onClick={() =>
            void unlinkWebLogin(person.person_id).then((answer) => {
              if (settle(answer, copy('admin_people.page.login_was_unlinked'), announce, onGate)) {
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
            )
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
  announce,
  onGate,
  onChanged,
}: {
  readonly assignment: AssignmentLineView;
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onChanged: () => void;
}): JSX.Element {
  const id = useId();
  const [options, setOptions] = useState<readonly ReportsToOptionView[] | null>(null);

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
        {fillCopy('admin_people.page.reports_to_label', { role: roleLabel(assignment.role) })}
      </label>
      <select
        id={id}
        className="pulse-admin-input"
        value={parent ?? ''}
        disabled={options === null}
        onChange={(event) => {
          const chosen = event.target.value;
          void setReportsTo(assignment.assignment_id, chosen === '' ? null : chosen).then(
            (answer) => {
              if (settle(answer, copy('admin_people.page.reports_to_saved'), announce, onGate)) {
                onChanged();
              }
            },
          );
        }}
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
    </span>
  );
}
