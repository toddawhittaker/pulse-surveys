# E5-09 — The named-set management UI

**ID:** E5-09
**Branch:** `e5/named-set-ui`
**Depends on:** E5-06 for merge order only — builds day one against fixture
responses shaped like E5-06's routes
**Lane:** light
**Security-relevant:** minimally; the route lives under
`frontend/src/routes/leadership/` and renders only what the API scoped.
The form's whole point is §5.1's "invalid combinations impossible".

## Context

The set-definition UI (§5.1): leadership lists, creates, edits and deletes
named sets. The spec's one hard sentence governs the form: invalid
length/level combinations are **impossible, not erroring** — the form
offers §2.2's lengths and §8's five levels as the only choices, and once
the level is chosen the course picker offers only courses of that level
(decision 3's shape rendered).

The preview (member count, resolved section count from E5-06) shows what a
set reaches, since no report renders one yet (decision 4 — say so in the
UI honestly, per the brief's plain-words register).

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6, §5.1,
§4.1 items 4 and 5; E5-06's route shapes; the existing leadership route
(`frontend/src/routes/leadership/index.tsx`) and the form conventions the
admin/instructor surfaces set.

## Scope

- The leadership route: set list with preview counts, create/edit form,
  delete with confirmation per the brief.
- The constrained form: length and level from the closed sets only; the
  course picker filtered by chosen level; changing the level re-filters
  and clears now-invalid members visibly, never silently submits them.
- Loading, empty ("no sets yet" in the brief's register), and error
  states; API refusals rendered in the API's vocabulary (E5-06 criterion
  3's messages), reachable only by races the form cannot prevent.

## Acceptance criteria

1. The form cannot express an invalid combination: no free-text length or
   level, and the course picker never offers a cross-level course —
   asserted by driving the form, not by reading the props.
2. Changing level with members selected surfaces the removal to the user
   (the visible-clearing rule above), asserted both ways: matching members
   survive, cross-level ones leave with a trace.
3. List, create, edit, delete each render against fixtures; the preview
   renders counts and renders honestly when the section count is absent
   (the E5-06 scope note's contingency).
4. Empty, loading and error states per the brief; no state renders a
   benchmark figure — this surface manages sets, it never shows
   comparison numbers (§4.1 item 7 has no chokepoint here, so nothing
   figure-shaped ships here at all).
5. Every string lives in the copy layout the inventory collects; §4.1
   item 4 self-check.
6. No raw hex; tokens only.

## Known traps

- **Client-side "validation" mistaken for the guarantee** — the form makes
  invalid input inexpressible for humans; the API and database still own
  refusal. Do not duplicate rule logic beyond what the closed choice lists
  already encode (MISTAKES entry 13's one-helper rule applies to the
  closed sets: they come from one shared module, not retyped here).
- **The closed sets retyped locally** — §2.2's lengths and §8's levels
  reach the form from one source the backend also serves or shares;
  a hand-typed list here is the two-currencies defect.

## Out of scope

- Attaching a set to any view — E9 (decision 4).
- The API's scoping — E5-06.
- Term-axis previews or any chart — E9 (decision 7).
