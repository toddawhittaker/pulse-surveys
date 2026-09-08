/**
 * The two sentences the fallback screen writes — ticket E4-12.
 *
 * `UnknownAddress` is what `/app` itself, and any address under it that names
 * no view, renders. It shipped with both sentences written straight into its
 * JSX, which is the shape E4-12's component-and-route sweep exists to refuse:
 * a string in a component is a string SPEC §4.1 items 4 and 5 are asserted over
 * nothing at all. So they live here, in the shape
 * `frontend/src/copy/studentSurvey.ts` settles for a surface's strings —
 * **stable dotted keys, one entry per string, one mapping** — and the component
 * looks them up.
 *
 * The words are unchanged. This ticket ships governance, not a rewording.
 *
 * **This surface owes item 5 no confidentiality line**, and that is recorded
 * rather than assumed: it shows nobody's data, so there is nothing about
 * anybody's identity for a sentence to promise.
 * `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
 * holds the surface in its no-line map with that reason written out, and ADR
 * 0158 records the split.
 */

export const UNKNOWN_ADDRESS_COPY = {
  // The product's name, which is all a page that resolves to nothing can
  // honestly put at the top of itself.
  'unknown_address.heading': 'Pulse Surveys',
  // The whole of what this page knows. It names no view, suggests no address
  // and blames nobody: the doors send everyone to a role route, so a reader
  // here followed a link that has stopped meaning anything.
  'unknown_address.body': 'There is nothing at this address.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type UnknownAddressCopyKey = keyof typeof UNKNOWN_ADDRESS_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: UnknownAddressCopyKey): string {
  return UNKNOWN_ADDRESS_COPY[key];
}
