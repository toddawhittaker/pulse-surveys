# Scratch probe for E0-38

This file exists to give the E0-38 path filter a diff that touches nothing but
inert documentation. It is not part of the project and its branch is deleted
once the run has been read.

The question it asks: does a pull request whose only changed path sits inside
the inert set finish without running pytest, the image builds, Playwright, the
evals or the supply-chain audit, while the required `CI` check still reports
success rather than pending?

Reading the workflow cannot answer that. The wiring test reads the guard
conditions without evaluating them, so a guard with its sense reversed passes
every assertion in the suite.
