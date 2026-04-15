"""Physical workspace isolation for Forage v2 runs.

Forage v2 replaces the "hidden dotfile" convention for method isolation
between Evaluator and Planner with a three-directory layout:

    root/
    ├── eval_ws/       # Evaluator's private cwd
    │   └── shared -> ../shared   (symlink)
    ├── plan_ws/       # Planner's private cwd
    │   └── shared -> ../shared   (symlink)
    └── shared/        # public, both agents see this
        └── dataset/

Each agent runs with its own ``cwd`` and cannot see the other's scripts
(``eval.py`` / ``action.py``) without crossing the ``shared`` symlink,
which only exposes the public contract surface.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunWorkspaces:
    """Container for the three-directory layout of an isolated run."""

    root: Path          # parent dir containing all three
    eval_ws: Path       # Evaluator's private cwd
    plan_ws: Path       # Planner's private cwd
    shared: Path        # shared public dir

    # Convenience accessors for common paths
    @property
    def dataset(self) -> Path:
        return self.shared / "dataset"

    @property
    def metrics_json(self) -> Path:
        return self.shared / "metrics.json"

    @property
    def eval_contract(self) -> Path:
        return self.shared / "eval_contract.md"

    @property
    def knowledge(self) -> Path:
        return self.shared / "knowledge"

    @property
    def eval_script(self) -> Path:
        return self.eval_ws / "eval.py"

    @property
    def action_script(self) -> Path:
        return self.plan_ws / "action.py"


def build_run_workspaces(prefix: str = "forage_", isolated: bool = True) -> RunWorkspaces:
    """Create a new run workspace.

    Two layouts depending on ``isolated``:

    Isolated (default, used by full/freeze_eval/no_eval modes):
        root/
        ├── eval_ws/
        │   └── shared -> ../shared (symlink)
        ├── plan_ws/
        │   └── shared -> ../shared (symlink)
        └── shared/
            └── dataset/

    Non-isolated (used by M-no-iso ablation only):
        root/
        ├── eval.py         (lives here; both agents can see it)
        ├── action.py       (lives here; both agents can see it)
        └── shared/
            └── dataset/

    In non-isolated mode, both agents use ``root`` as their cwd, so neither
    is physically hidden from the other's scripts. ``shared/`` remains a
    real subdirectory so all ``./shared/...`` path references used by the
    system prompts continue to resolve identically in both modes.

    Args:
        prefix: tempdir prefix.
        isolated: if True, dual-workspace layout with symlinks (enforces
            method isolation). If False, single workspace with a real
            ``shared/`` subdir (M-no-iso ablation).

    Returns:
        RunWorkspaces dataclass with all paths.

    Raises:
        OSError: in isolated mode, if symlink creation fails on the host
            filesystem.
    """
    root = Path(tempfile.mkdtemp(prefix=prefix))

    if not isolated:
        # Single shared workspace — eval_ws == plan_ws == root; shared is a
        # real subdir so ./shared/... paths still resolve.
        shared = root / "shared"
        shared.mkdir()
        (shared / "dataset").mkdir()
        return RunWorkspaces(
            root=root,
            eval_ws=root,
            plan_ws=root,
            shared=shared,
        )

    eval_ws = root / "eval_ws"
    plan_ws = root / "plan_ws"
    shared = root / "shared"

    eval_ws.mkdir()
    plan_ws.mkdir()
    shared.mkdir()
    (shared / "dataset").mkdir()

    # Symlinks use relative target so they remain valid after move/rename
    (eval_ws / "shared").symlink_to("../shared", target_is_directory=True)
    (plan_ws / "shared").symlink_to("../shared", target_is_directory=True)

    # Sanity check — if symlinks don't work on this filesystem, fail loudly
    if not (eval_ws / "shared" / "dataset").is_dir():
        raise OSError(f"Symlink verification failed at {root}")
    if not (plan_ws / "shared" / "dataset").is_dir():
        raise OSError(f"Symlink verification failed at {root}")

    return RunWorkspaces(
        root=root,
        eval_ws=eval_ws,
        plan_ws=plan_ws,
        shared=shared,
    )


def cleanup_workspaces(root: Path) -> None:
    """Remove the entire workspace tree."""
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
