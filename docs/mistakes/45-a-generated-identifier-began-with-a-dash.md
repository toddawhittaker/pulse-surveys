# 45. A generated base64url identifier began with a dash and argparse read it as an option

## Instance: a signing key whose kid begins with `-` could not be retired (2026-09-04)

`scripts/signing_key.py retire <kid>` takes an RFC 7638 thumbprint — base64url,
which draws from an alphabet containing `-`. About one thumbprint in
sixty-four begins with it, and argparse read such a kid as an option flag:
`error: the following arguments are required: kid`, about an argument that was
on the command line. Every scoped run of the retire tests passed, because the
fixtures' generated keys happened to produce kids starting with other
characters; the full-suite pass across many generated keys is what surfaced
it, and on any smaller battery the failure would have read as a flake and been
re-run into silence.

The repair inserts `--` into the argv ahead of the positional value
(`argv_with_the_kid_protected`), and the proof generated keys until one came
out dash-first and retired it. The rule's stronger form is to plant the
dash-first identifier deliberately in the test, so the case runs every time
instead of one time in sixty-four.
