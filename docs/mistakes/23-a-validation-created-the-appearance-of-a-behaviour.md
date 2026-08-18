# Entry 23. A validation created the appearance of a behaviour

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(Writing E0-13's tests, and it is this entry's rule applied to a
credential before the credential existed. The ticket asks for "a masked key", and
a key can be masked by deleting the field: `Settings` would then hold nothing, no
serialisation would leak anything, every masking assertion would pass, and every
hosted endpoint would be unreachable. So the suite asserts both halves —
`test_the_provider_key_is_still_readable_by_the_application` for the value the
application can read, and, in the integration module, that the stub actually
**received** the key in a header before anything is asserted about the error not
carrying it. That is this entry's question asked of a configuration field: name
the code that reads it, and if the answer is "nothing", it is decorative. The
answer here is `app/ai/gateway.py`, and the test that names it is the one that
fails if a later refactor stops sending it.)*

**What happened.** In E0-15's mock platform, the AGS Result fold ignored
`gradingProgress` entirely. A score posted `NotReady` — the value that says the
grading process has not started — read back as a finished grade, and so did
`Failed` and `Pending`; measured across all five values by a reviewer.

That is an ordinary omission. What makes it worth an entry is the round in
between. The previous review pass found the field checked only for presence, and
the fix added a vocabulary check: `gradingProgress` had to be one of AGS 2.0's
five exact strings, refused loudly otherwise, with a control asserting all five
were accepted. Every one of those things is correct and none of them made the
grade right. After that fix the field was **validated on the way in, recorded
verbatim in the log, echoed in the readback, and consulted by nothing** — and it
now looked handled from every angle a reader has. The code had a named constant
for its vocabulary. The suite had a case per value. Anyone scanning either would
conclude the field was understood.

**Root cause.** Checking that a value is *well-formed* and never asking what it
is *for*. A vocabulary check is an assertion about the shape of an input; it says
nothing about whether anything downstream reads it. The two are easy to confuse
because a validated field looks like a used field: it appears in a constant, in
an error message, and in the name of something green.

It is entry 2's family — behaviour with nothing asserting it — and it is the
inverse of it, which is why it needs its own heading. There, a guard exists and
nothing covers it. Here, the coverage exists, it passes, and the field it
describes was never wired to anything. Entry 2's rule — try to reintroduce the
defect, and a green suite means you wrote a convention — cannot find this,
because there is nothing to reintroduce: removing the fold's use of the field is
a no-op, since it had none.

**Consequence.** Two rounds, and the second made the defect harder to see than
the first. Had it shipped, E3 would post a score at submit time — before SPEC
§3.3's classification has decided whether the response counts — and the gradebook
would show a participation grade computed from a week that has not been graded.
The student sees a number that will change, and nothing on the tool's side could
find it, because the tool is built against this mock.

**Rule.** **For every field a service validates, name the code that reads it.**
If the answer is "nothing", the field is decorative, and one of two things has to
happen: it gets acted on, or the validation says in writing that it is a shape
check and nothing more. The question to ask of an input is not only "is this
checked?" but "what changes when it changes?".

The cheap version is a search: grep the field name and count the sites that are
not the validator. One hit means the value goes in and stops there. And **a round
that adds validation to a field is the round to ask this**, because adding a
check to a field nothing consumes makes the gap less visible rather than more —
the next reader inherits a field that looks settled.

---
