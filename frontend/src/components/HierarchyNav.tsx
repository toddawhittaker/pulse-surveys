import { useState, type JSX, type ReactNode } from 'react';

import type { RollupNodeView } from '../api/leadership';
import { copy, fillCopy } from '../copy/leadershipRollupCopy';
import './leadershipRollup.css';

/**
 * SPEC §7.6's `HierarchyNav`: the roll-up's tree (SPEC §2.1, §5.5).
 *
 * `design/HierarchyNav.dc.html` is the contract: a card holding "Expand all"
 * and "Collapse all", then one row per node with a disclosure triangle, the
 * node's name and its mono count line beneath. **The tree starts fully
 * collapsed** (§5.5's "Trees default fully collapsed"), so a reader with
 * several roots sees every root before any of them opens.
 *
 * **The rows are in the server's order, and nothing here sorts them.** The
 * payload orders siblings by name (§4.1 item 4: no score-sorting anywhere), and
 * a client sort would be a second opinion that could put a figure into it.
 *
 * **Each row's words are the server's.** The name and the count line (SPEC
 * §2.1's "N departments · N sections · Dean: {name}" and its kin) arrive in the
 * payload; a section row's line is its code and its teaching instructor.
 *
 * **Keyboard and screen reader.** The tree is nested lists inside a labelled
 * `nav`. Each row is two native buttons: the disclosure, which names its node
 * once and says whether it is open through `aria-expanded`, and the row itself, which
 * selects the node and carries `aria-current` when it is the one shown. A
 * section row is a link instead, because selecting a section opens its report
 * at an address of its own (`sectionLink`).
 */
export function HierarchyNav({
  roots,
  selectedId,
  onSelect,
  sectionLink,
}: {
  /** The tree's roots, in the payload's order. */
  readonly roots: readonly RollupNodeView[];
  /** The node whose figures the page is showing, if any. */
  readonly selectedId: string | null;
  /** Show a node's figures. Never called for a section. */
  readonly onSelect: (node: RollupNodeView) => void;
  /** The link a section row is: its drill-down, at its own address. */
  readonly sectionLink: (node: RollupNodeView, children: ReactNode) => JSX.Element;
}): JSX.Element {
  // Collapsed, except the way down to the node shown, so its row (and its
  // `aria-current`) is in the document from the start.
  const [open, setOpen] = useState<ReadonlySet<string>>(
    () => new Set(selectedId === null ? [] : ancestorsOf(roots, selectedId)),
  );

  function toggle(id: string): void {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  }

  return (
    <nav className="pulse-hierarchy" aria-label={copy('leadership_rollup.nav.label')}>
      <div className="pulse-hierarchy-all">
        <button
          type="button"
          className="pulse-hierarchy-all-button"
          onClick={() => {
            setOpen(new Set(openable(roots)));
          }}
        >
          {copy('leadership_rollup.nav.expand_all')}
        </button>
        <button
          type="button"
          className="pulse-hierarchy-all-button"
          onClick={() => {
            setOpen(new Set());
          }}
        >
          {copy('leadership_rollup.nav.collapse_all')}
        </button>
      </div>
      <Rows
        nodes={roots}
        depth={0}
        open={open}
        toggle={toggle}
        selectedId={selectedId}
        onSelect={onSelect}
        sectionLink={sectionLink}
      />
    </nav>
  );
}

/** The ids of the nodes above the one with `id`, root first, or none. */
function ancestorsOf(nodes: readonly RollupNodeView[], id: string): string[] {
  for (const node of nodes) {
    if (node.id === id) return [];
    const below = ancestorsOf(node.children, id);
    if (below.length > 0 || node.children.some((child) => child.id === id)) {
      return [node.id, ...below];
    }
  }
  return [];
}

/** Every node with children, at any depth: what "Expand all" opens. */
function openable(nodes: readonly RollupNodeView[]): string[] {
  return nodes.flatMap((node) =>
    node.children.length > 0 ? [node.id, ...openable(node.children)] : [],
  );
}

function Rows({
  nodes,
  depth,
  open,
  toggle,
  selectedId,
  onSelect,
  sectionLink,
}: {
  readonly nodes: readonly RollupNodeView[];
  readonly depth: number;
  readonly open: ReadonlySet<string>;
  readonly toggle: (id: string) => void;
  readonly selectedId: string | null;
  readonly onSelect: (node: RollupNodeView) => void;
  readonly sectionLink: (node: RollupNodeView, children: ReactNode) => JSX.Element;
}): JSX.Element {
  return (
    <ul className="pulse-hierarchy-list">
      {nodes.map((node) => {
        const hasChildren = node.children.length > 0;
        const isOpen = open.has(node.id);
        const selected = node.id === selectedId;
        return (
          <li key={`${node.kind}:${node.id}`} className="pulse-hierarchy-item">
            <div
              className={`pulse-hierarchy-row${selected ? ' pulse-hierarchy-row-selected' : ''}`}
              // The 4px ramp's 8 and 16: the indent is the only per-row geometry.
              style={{ paddingLeft: 8 + depth * 16 }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className="pulse-hierarchy-toggle"
                  aria-expanded={isOpen}
                  aria-label={fillCopy('leadership_rollup.nav.toggle', { name: node.name })}
                  onClick={() => {
                    toggle(node.id);
                  }}
                >
                  <svg
                    width="8"
                    height="10"
                    aria-hidden="true"
                    focusable="false"
                    className={isOpen ? 'pulse-hierarchy-caret-open' : 'pulse-hierarchy-caret'}
                  >
                    <path d="M1 1 L7 5 L1 9 Z" />
                  </svg>
                </button>
              ) : (
                <span className="pulse-hierarchy-toggle-space" aria-hidden="true" />
              )}
              {node.kind === 'section' ? (
                sectionLink(node, <span className="pulse-hierarchy-name">{node.label}</span>)
              ) : (
                <button
                  type="button"
                  className="pulse-hierarchy-select"
                  aria-current={selected ? 'true' : undefined}
                  onClick={() => {
                    onSelect(node);
                  }}
                >
                  <span className="pulse-hierarchy-name">{node.name}</span>
                  <span className="pulse-hierarchy-count">{node.label}</span>
                </button>
              )}
            </div>
            {hasChildren && isOpen ? (
              <Rows
                nodes={node.children}
                depth={depth + 1}
                open={open}
                toggle={toggle}
                selectedId={selectedId}
                onSelect={onSelect}
                sectionLink={sectionLink}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
