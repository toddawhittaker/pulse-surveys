# 0159 — The component and route trees are swept for strings no copy module governs

## Context

SPEC §4.1 items 4 and 5 are asserted over the copy inventory, and both stop at
its edge. A sentence written straight into a component renders identically to
one looked up by key and is in no inventory: item 4's vocabulary never reads it,
and item 5 cannot count a second confidentiality promise it never collected.

Every surface built since E2 has held to the convention that a component carries
no literal a person reads — and the convention was held by review alone. The E2
boundary recorded that as a gap rather than as a finding, because nothing was
violating it yet. Something was by E4: `UnknownAddress.tsx` rendered two
sentences as JSX text, and the four report copy modules sat outside the walked
copy directory, so every key their components looked up resolved to nothing the
inventory held.

The carried done-when governs the shape: a parse of the component and route
trees refusing a user-visible string literal outside the copy modules, reusing
the inventory's parser, with a planted offender and a near miss both proven.

## Decision

A scanner reads every `.ts`, `.tsx`, `.mts` and `.cts` file under
`frontend/src/components/` and `frontend/src/routes/`, at any depth, and hands
back every piece of text a reader could see — string literals with the position
they were written in, template-literal fragments, and JSX text runs. Each piece
is then classified, and anything that fits no rule is a finding.

**Refused:** JSX text carrying letters; a literal supplied to an attribute a
reader reads or hears (`aria-label`, `aria-roledescription`, `aria-valuetext`,
`alt`, `placeholder`, `title`); a sentence-shaped literal — whitespace plus
letters, trimmed — in any position no rule allows; and a dotted literal spelled
like a copy key that the collected inventory does not hold, because whatever it
looks up is not a governed string.

**Allowed:** module specifiers; values of named non-visible attributes
(`className`, `data-*`, `id`, `key`, `htmlFor`, `role`, `aria-labelledby` and
the SVG geometry attributes among them); a dotted key the inventory does hold;
and any single code token with no internal whitespace.

**The classifier fails closed.** A file the scanner cannot resolve — an
unterminated string, an unclosed block comment, JSX that never balances — is a
finding against that file, naming it, rather than an exception that ends the
sweep. Test modules are excluded because a test's strings do not ship, and three
named test-support modules inside the swept trees are excluded by path; the
sweep asserts each of them exists and is imported only from excluded files, so a
shipped import of one is itself a finding.

The escape and surrogate readers are the copy inventory's own, imported rather
than rewritten, so a padlock spelled as a surrogate pair decodes to the same
character in both.

## Alternatives rejected

**A regular expression over the sources.** The deciding case is
`WeekNav.tsx`'s `(week) => week < currentWeek`, which any search for text
between `>` and `<` reads as the JSX text ` week `. A rule that produces a false
finding on ordinary code is a rule somebody widens until it finds nothing.

**Reading `<` as JSX everywhere.** `Record<string, string>` and
`useState<Props>(null)` are not elements. `<` opens an element only in a `.tsx`
file and only where an expression may begin, which is what the scanner asks.

**Skipping what the scanner cannot classify.** That is the shape that reports a
clean tree over the strings it never understood, and it is `docs/MISTAKES.md`
entries 3 and 9 in one move.

**Excusing a whole statement by the word it starts with.** The first spelling of
the import rule read `^\s*(?:import|export)\s`, which lets
`export const EMPTY = 'Nothing is open this week.'` through — the same
prefix-matched allowance the copy parser had to remove for the same reason.

**A pattern excusing `*Fixtures.ts`.** It would excuse a component somebody
named that way. The three support modules are named one by one, and each name is
a claim the sweep checks.

**Sweeping `frontend/src` whole.** The copy directory is where strings are
supposed to live, and `lib/`, `main.tsx` and `router.tsx` are outside the
carried done-when's two trees.

## Consequences

The convention is a guarantee on those two trees now: a sentence written into a
component is a red, and so is a copy key that resolves to nothing. Both
directions are proven before the tree is read — nine planted offenders seen
refused, thirteen near misses seen allowed.

What it does not reach is disclosed in the sweep's own docstring rather than
discovered later. A string assembled at runtime, or reached through a variable,
is invisible: a sentence split across template fragments is three fragments none
of which is sentence-shaped, which is the same rule that lets a conditional class
list through. A single word in an expression position is allowed, because
widening to any letter-carrying literal would refuse every `'button'` and
`'polite'` in the tree. Files outside the two trees are not swept —
`frontend/src/lib/landings.ts` holds shipped sentences and is recorded as a
deferral. CSS `content:` properties put text on a screen from a stylesheet and
are outside this entirely. And a regular-expression literal is read as ordinary
code, which is harmless while its braces balance and refuses the file loudly
when they do not.

The cost of the key cross-check is that the sweep depends on the collected
inventory: a copy module that stops being collected turns every key that reads
it into a finding. That is the intended direction — a key nothing governs is the
defect — but it means the two rules fail together, and the inventory's own
canaries are what say which of them broke.
