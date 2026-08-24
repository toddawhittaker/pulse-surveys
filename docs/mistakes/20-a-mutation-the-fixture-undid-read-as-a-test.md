# Entry 20. A mutation the fixture undid, read as a test that could not fail

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** In E0-14, checking by mutation that "issuer keys are generated
per run" is really asserted. The obvious mutation is to make the key survive a
restart, so it was moved to a module-level constant: `_CACHED_KEY =
IssuerKey.generate()` at import, with `create_app()` handing it out. All 27 tests
stayed green, which reads as the criterion being asserted by nothing.

It is not. `import_mock_lms_application` in `tests/fixtures/app_imports.py` drops every
`app.*` module from `sys.modules` and re-imports before each platform starts —
deliberately, and its docstring says why. So a module-level constant is
*regenerated per platform*, and the mutation had not made the key survive
anything. A second mutation that actually did — drawing the primes from a
module-level seeded PRNG, which restarts identically on every re-import — turned
two tests red immediately, and they were the right two.

**Root cause.** Mutating at the wrong layer. The property under test is "two
platform starts produce two keys", and the fixture's definition of a platform
start is a fresh import — so any mutation *above* the import boundary is undone
by the harness before the assertion runs. The mutation looked like it changed the
lifetime of the key and changed nothing at all.

**Consequence.** None this time, because the first result was disbelieved and a
second mutation was tried. Had it been believed, the conclusion available was
"this criterion is asserted by nothing" — followed by either a dispute against a
test that is in fact correct and sharp, or a quiet decision that the key lifetime
does not matter. It is a bad failure mode precisely because the evidence looks
clean: a green suite after a deliberate break is the strongest signal there is,
which is why a false one is expensive.

**Rule.** Before believing a mutation that did not fail, say which mechanism was
supposed to carry it to the assertion, and check the harness does not neutralise
it. `tests/fixtures/app_imports.py` has two fixtures that drop and restore `sys.modules` —
`import_app_module` and `import_mock_lms_application` — so **anything at module
scope is per-test state, not process state**, and a mutation that relies on
process lifetime has to go below the import: into a file, into the environment, or
into a deterministic source of randomness. A mutation that fails to fail is a
result about the mutation until you have shown otherwise.

---
