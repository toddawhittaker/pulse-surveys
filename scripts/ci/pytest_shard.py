"""A pytest plugin that runs one slice of the collection, for CI's sharded suite.

CI runs the unit and integration pass on several runners at once (docs/adr/0181).
Each runner loads this plugin with `-p pytest_shard` and names its slice in
`PULSE_TEST_SHARD` as `k/n`. The plugin keeps every n-th collected test, starting
at the k-th, and deselects the rest. Every runner collects the same tree in the
same order — xdist already refuses to run if two workers disagree about that — so
the n slices are disjoint and together hold the whole collection.

**That last sentence is checked, not trusted.** The plugin writes two lists into
`PULSE_TEST_SHARD_RECORD`: `collected.txt`, every test pytest collected before
the slice was taken, and `selected.txt`, the slice. `scripts/ci/check_test_shards.py`
reads every shard's lists and its JUnit XML after the shards finish, and fails
the pipeline unless the slices are disjoint, their union is the collection, and
each shard's JUnit report holds as many test cases as its slice. A slicing bug
therefore shows up as a red job rather than as tests that quietly stopped running.

With `PULSE_TEST_SHARD` unset the plugin does nothing, so loading it outside CI
runs the whole suite. A malformed value is a usage error, never a full run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

SHARD_VARIABLE = "PULSE_TEST_SHARD"
RECORD_VARIABLE = "PULSE_TEST_SHARD_RECORD"


def parse_shard(value: str) -> tuple[int, int]:
    """`"k/n"` as `(k, n)`, refusing anything that is not 1 <= k <= n."""
    try:
        index_text, count_text = value.split("/")
        index, count = int(index_text), int(count_text)
    except ValueError as error:
        raise pytest.UsageError(f"{SHARD_VARIABLE}={value!r} is not of the form k/n") from error
    if not 1 <= index <= count:
        raise pytest.UsageError(f"{SHARD_VARIABLE}={value!r} needs 1 <= k <= n")
    return index, count


# Last, so the slice is taken over what `-m`, `-k` and every other plugin left.
@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = os.environ.get(SHARD_VARIABLE, "")
    if not value:
        return
    index, count = parse_shard(value)

    kept = [item for position, item in enumerate(items) if position % count == index - 1]
    dropped = [item for position, item in enumerate(items) if position % count != index - 1]

    # Under xdist every worker collects and slices; one copy of the lists is
    # enough, and `gw0` always exists. Without xdist there is no worker id.
    worker = getattr(config, "workerinput", {}).get("workerid")
    record = os.environ.get(RECORD_VARIABLE, "")
    if record and worker in (None, "gw0"):
        directory = Path(record)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "collected.txt").write_text(
            "".join(f"{item.nodeid}\n" for item in items), encoding="utf-8"
        )
        (directory / "selected.txt").write_text(
            "".join(f"{item.nodeid}\n" for item in kept), encoding="utf-8"
        )

    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept
