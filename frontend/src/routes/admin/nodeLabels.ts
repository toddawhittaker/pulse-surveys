import { useCallback, useRef, useState } from 'react';

import { readOrgNodes, type AssignmentRole, type OrgNodeView } from '../../api/admin';
import { copy, fillCopy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';

/** A node as people read it: its name, and its parent's when it has one. */
export function nodeText(node: OrgNodeView): string {
  return node.parent_label === null
    ? node.label
    : fillCopy('admin_people.page.node_option', { name: node.label, parent: node.parent_label });
}

export interface NodeLabels {
  /** The nodes the server grants `role` at, once they have arrived; none before. */
  readonly nodesFor: (role: AssignmentRole) => readonly OrgNodeView[];
  /** The text of the node with this id, if any role's answer so far held it. */
  readonly labelOf: (nodeId: string) => string | null;
  /** Ask for a role's nodes unless they were already asked for. */
  readonly ensure: (role: AssignmentRole) => void;
}

/**
 * The organization nodes by role, read once per role for the page's life.
 *
 * `GET /admin/org-nodes?role=` is the only place the screen learns a node's
 * name, and the role decides the level, so a scope id shown beside a role is
 * resolved through that role's answer. The grant picker reads the same cache.
 */
export function useNodeLabels(
  announce: (message: string) => void,
  onGate: (gate: Exclude<Gate, null>) => void,
): NodeLabels {
  const [byRole, setByRole] = useState<Readonly<Partial<Record<AssignmentRole, readonly OrgNodeView[]>>>>({});
  const asked = useRef(new Set<AssignmentRole>());

  const ensure = useCallback(
    (role: AssignmentRole): void => {
      if (asked.current.has(role)) return;
      asked.current.add(role);
      void readOrgNodes(role).then((answer) => {
        if (answer.kind === 'ok') {
          setByRole((previous) => ({ ...previous, [role]: answer.value }));
        } else if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
          onGate(answer.kind);
        } else {
          asked.current.delete(role);
          announce(copy('admin_people.page.nodes_unavailable'));
        }
      });
    },
    [announce, onGate],
  );

  const nodesFor = (role: AssignmentRole): readonly OrgNodeView[] => byRole[role] ?? [];
  const labelOf = (nodeId: string): string | null => {
    for (const nodes of Object.values(byRole)) {
      const found = nodes.find((node) => node.node_id === nodeId);
      if (found !== undefined) return nodeText(found);
    }
    return null;
  };

  return { nodesFor, labelOf, ensure };
}
