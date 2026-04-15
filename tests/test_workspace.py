"""Unit tests for forage.core.workspace."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forage.core.workspace import (
    RunWorkspaces,
    build_run_workspaces,
    cleanup_workspaces,
)


@pytest.fixture
def ws():
    """Create a fresh workspace and tear it down after the test."""
    w = build_run_workspaces(prefix="forage_test_")
    try:
        yield w
    finally:
        cleanup_workspaces(w.root)


def test_build_creates_three_dirs(ws: RunWorkspaces):
    """root contains eval_ws, plan_ws, shared; all are directories."""
    assert ws.root.is_dir()
    assert ws.eval_ws.is_dir()
    assert ws.plan_ws.is_dir()
    assert ws.shared.is_dir()

    # All three live under root
    assert ws.eval_ws.parent == ws.root
    assert ws.plan_ws.parent == ws.root
    assert ws.shared.parent == ws.root

    # Exactly these three entries (no stray files) at root
    names = {p.name for p in ws.root.iterdir()}
    assert names == {"eval_ws", "plan_ws", "shared"}


def test_build_creates_dataset(ws: RunWorkspaces):
    """shared/dataset/ exists and is a directory."""
    dataset = ws.shared / "dataset"
    assert dataset.is_dir()
    # Convenience accessor matches
    assert ws.dataset == dataset


def test_symlinks_resolve_to_shared(ws: RunWorkspaces):
    """eval_ws/shared/dataset and plan_ws/shared/dataset resolve to the
    same inode as shared/dataset."""
    real = (ws.shared / "dataset").resolve()
    via_eval = (ws.eval_ws / "shared" / "dataset").resolve()
    via_plan = (ws.plan_ws / "shared" / "dataset").resolve()

    assert via_eval == real
    assert via_plan == real

    # Stronger check: identical inode on the underlying filesystem
    real_stat = os.stat(real)
    eval_stat = os.stat(via_eval)
    plan_stat = os.stat(via_plan)
    assert (real_stat.st_dev, real_stat.st_ino) == (eval_stat.st_dev, eval_stat.st_ino)
    assert (real_stat.st_dev, real_stat.st_ino) == (plan_stat.st_dev, plan_stat.st_ino)

    # The symlink itself is a symlink
    assert (ws.eval_ws / "shared").is_symlink()
    assert (ws.plan_ws / "shared").is_symlink()


def test_write_through_symlink(ws: RunWorkspaces):
    """Writing via eval_ws's symlink is readable via plan_ws's symlink and
    at the real shared path."""
    payload = '{"coverage": 0.42}'
    (ws.eval_ws / "shared" / "metrics.json").write_text(payload)

    # Readable via plan_ws's symlink
    assert (ws.plan_ws / "shared" / "metrics.json").read_text() == payload
    # Readable at the real shared location
    assert (ws.shared / "metrics.json").read_text() == payload
    # And via the convenience accessor
    assert ws.metrics_json.read_text() == payload


def test_convenience_paths(ws: RunWorkspaces):
    """All convenience properties return the expected paths."""
    assert ws.dataset == ws.shared / "dataset"
    assert ws.metrics_json == ws.shared / "metrics.json"
    assert ws.eval_contract == ws.shared / "eval_contract.md"
    assert ws.knowledge == ws.shared / "knowledge"
    assert ws.eval_script == ws.eval_ws / "eval.py"
    assert ws.action_script == ws.plan_ws / "action.py"


def test_isolation_no_cross_visibility(ws: RunWorkspaces):
    """Scripts in one agent's workspace are not visible from the other
    without crossing the ``shared`` symlink.

    Notes on Python glob semantics:

    * ``Path.iterdir()`` does NOT follow symlinks; it returns the entries
      of the directory itself. So ``eval_ws/`` has exactly two entries:
      ``eval.py`` and the ``shared`` symlink.
    * ``Path.glob("**/*")`` does NOT follow symlinks to directories
      (consistent across Python 3.10+), so it will not descend into
      ``shared/`` via the symlink. This gives us a clean "private view"
      of the workspace.
    * ``Path.rglob(...)`` behaves similarly to ``glob("**/...")`` — it
      does not follow symlinks to directories on supported Python
      versions, so ``action.py`` is unreachable from ``eval_ws`` without
      explicitly traversing the ``shared`` symlink.
    """
    ws.eval_script.write_text("# eval.py\n")
    ws.action_script.write_text("# action.py\n")

    # Direct iterdir on each private workspace: must NOT see the other's script.
    eval_names = {p.name for p in ws.eval_ws.iterdir()}
    plan_names = {p.name for p in ws.plan_ws.iterdir()}
    assert "action.py" not in eval_names
    assert "eval.py" not in plan_names
    # Sanity: each sees its own script plus the shared symlink
    assert "eval.py" in eval_names
    assert "shared" in eval_names
    assert "action.py" in plan_names
    assert "shared" in plan_names

    # glob("**/*") does not cross symlinks: action.py is not findable from eval_ws
    eval_glob = list(ws.eval_ws.glob("**/*"))
    eval_glob_names = {p.name for p in eval_glob}
    assert "action.py" not in eval_glob_names
    # The symlink itself shows up, but not its contents.
    assert "shared" in eval_glob_names

    plan_glob = list(ws.plan_ws.glob("**/*"))
    plan_glob_names = {p.name for p in plan_glob}
    assert "eval.py" not in plan_glob_names
    assert "shared" in plan_glob_names

    # rglob consistency check — also must not reach into the other workspace.
    assert list(ws.eval_ws.rglob("action.py")) == []
    assert list(ws.plan_ws.rglob("eval.py")) == []

    # But the public `shared` dir IS reachable by explicitly going through
    # the symlink — that's the whole point of the contract surface.
    (ws.shared / "eval_contract.md").write_text("contract")
    assert (ws.eval_ws / "shared" / "eval_contract.md").read_text() == "contract"
    assert (ws.plan_ws / "shared" / "eval_contract.md").read_text() == "contract"


def test_build_non_isolated_mode():
    """build_run_workspaces(isolated=False) creates single-dir layout for M-no-iso."""
    ws = build_run_workspaces(prefix="noiso_test_", isolated=False)
    try:
        # eval_ws, plan_ws, and root are all the same
        assert ws.eval_ws == ws.root
        assert ws.plan_ws == ws.root
        # shared is a real subdir (not a symlink)
        assert ws.shared == ws.root / "shared"
        assert ws.shared.is_dir()
        assert not ws.shared.is_symlink()
        # dataset exists under shared (via property)
        assert ws.dataset.is_dir()
        # convenience properties resolve correctly
        assert ws.eval_script == ws.root / "eval.py"
        assert ws.action_script == ws.root / "action.py"
        assert ws.metrics_json == ws.root / "shared" / "metrics.json"
        assert ws.eval_contract == ws.root / "shared" / "eval_contract.md"
    finally:
        cleanup_workspaces(ws.root)


def test_non_isolated_no_cross_hiding():
    """In non-isolated mode, both scripts are in same dir and both visible."""
    ws = build_run_workspaces(prefix="noiso_test_", isolated=False)
    try:
        (ws.eval_ws / "eval.py").write_text("# eval")
        (ws.plan_ws / "action.py").write_text("# action")
        # Both scripts in same dir
        names = [p.name for p in ws.root.iterdir() if p.is_file()]
        assert "eval.py" in names
        assert "action.py" in names  # no isolation: both agents see both
        # ./shared/dataset/ still resolves the same way prompts expect
        assert (ws.root / "shared" / "dataset").is_dir()
    finally:
        cleanup_workspaces(ws.root)


def test_non_isolated_shared_roundtrip():
    """In non-isolated mode, writes to shared/ are visible from root-relative paths."""
    ws = build_run_workspaces(prefix="noiso_test_", isolated=False)
    try:
        payload = '{"coverage": 0.5}'
        ws.metrics_json.write_text(payload)
        # Accessible via ./shared/metrics.json from the single cwd (root)
        assert (ws.root / "shared" / "metrics.json").read_text() == payload
    finally:
        cleanup_workspaces(ws.root)


def test_cleanup():
    """cleanup_workspaces removes the root entirely."""
    w = build_run_workspaces(prefix="forage_cleanup_")
    # Populate some files to make sure rmtree handles non-empty trees.
    (w.eval_ws / "eval.py").write_text("x")
    (w.plan_ws / "action.py").write_text("y")
    (w.shared / "metrics.json").write_text("{}")

    root = w.root
    assert root.exists()
    cleanup_workspaces(root)
    assert not root.exists()

    # Idempotent: cleaning an already-gone root is a no-op.
    cleanup_workspaces(root)
    assert not root.exists()
