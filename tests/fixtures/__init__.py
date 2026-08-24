"""The suite's shared fixtures, one module per subject.

Loaded by `tests/conftest.py` through `pytest_plugins`, never imported by a test
module. A test asks for a fixture by name and pytest finds it; this package is a
package only so that one module can import another's plain helpers, constants and
classes, which fixture resolution does not reach.

There are deliberately no per-directory `conftest.py` files under `tests/`: these
fixtures cross the unit and integration boundary, and splitting them by directory
would put the same fixture in two places.
"""
