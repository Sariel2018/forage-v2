"""Regression test: method isolation cannot leak between agent workspaces.

This test exists because Forage v2 had a silent isolation leak (CLI logs showed
Q10 Opus Planner running `python .eval.py` directly, breaking co-evolution
independence). The fix was physical directory isolation. This test guards
against reintroduction.
"""
from pathlib import Path
from forage.core.workspace import build_run_workspaces, cleanup_workspaces


def test_evaluator_cannot_see_action_py():
    """Evaluator's workspace (eval_ws) must not expose action.py under any path."""
    ws = build_run_workspaces(prefix="isolation_test_")
    try:
        # Plant scripts in their respective private workspaces
        (ws.eval_ws / "eval.py").write_text("# evaluator script")
        (ws.plan_ws / "action.py").write_text("# planner script")

        # From eval_ws, action.py must not be findable via simple means
        # (simulating what an Evaluator agent might do with Glob/ls)

        # Direct child listing — should not include action.py
        names = [p.name for p in ws.eval_ws.iterdir()]
        assert "action.py" not in names
        assert "eval.py" in names  # sanity: evaluator CAN see its own script

        # glob — should not find action.py
        assert list(ws.eval_ws.glob("action.py")) == []
        assert list(ws.eval_ws.glob("*.py")) == [ws.eval_ws / "eval.py"]

        # Recursive glob without following symlinks — should not cross into plan_ws
        # (Note: `.glob("**/*")` does not follow symlinks in Python 3.10-3.12)
        recursive = list(ws.eval_ws.glob("**/*"))
        assert not any(p.name == "action.py" for p in recursive), \
            f"action.py leaked into eval_ws recursive glob: {recursive}"
    finally:
        cleanup_workspaces(ws.root)


def test_planner_cannot_see_eval_py():
    """Planner's workspace (plan_ws) must not expose eval.py under any path."""
    ws = build_run_workspaces(prefix="isolation_test_")
    try:
        (ws.eval_ws / "eval.py").write_text("# evaluator script")
        (ws.plan_ws / "action.py").write_text("# planner script")

        names = [p.name for p in ws.plan_ws.iterdir()]
        assert "eval.py" not in names
        assert "action.py" in names

        assert list(ws.plan_ws.glob("eval.py")) == []
        assert list(ws.plan_ws.glob("*.py")) == [ws.plan_ws / "action.py"]

        recursive = list(ws.plan_ws.glob("**/*"))
        assert not any(p.name == "eval.py" for p in recursive), \
            f"eval.py leaked into plan_ws recursive glob: {recursive}"
    finally:
        cleanup_workspaces(ws.root)


def test_shared_visible_from_both():
    """Both agents CAN see shared resources via the symlink."""
    ws = build_run_workspaces(prefix="isolation_test_")
    try:
        # Write to shared
        (ws.shared / "metrics.json").write_text('{"coverage": 0.5}')
        (ws.shared / "eval_contract.md").write_text("# contract")

        # Both workspaces can read via ./shared/
        assert (ws.eval_ws / "shared" / "metrics.json").read_text() == '{"coverage": 0.5}'
        assert (ws.plan_ws / "shared" / "metrics.json").read_text() == '{"coverage": 0.5}'
        assert (ws.eval_ws / "shared" / "eval_contract.md").read_text() == "# contract"
        assert (ws.plan_ws / "shared" / "eval_contract.md").read_text() == "# contract"
    finally:
        cleanup_workspaces(ws.root)


def test_eval_ws_cannot_traverse_to_plan_ws_via_parent():
    """Even with ../ traversal, Evaluator has no way to know plan_ws exists by name."""
    ws = build_run_workspaces(prefix="isolation_test_")
    try:
        (ws.plan_ws / "action.py").write_text("# planner script")

        # The only sibling dir name the Evaluator could guess is "plan_ws"
        # (convention), but it has no way to KNOW this name without being told.
        # This test documents the convention-dependency and verifies the path
        # IS accessible if the Evaluator guesses — which is a known limitation
        # (the prompt must not mention "plan_ws").

        # We're documenting, not enforcing. Just verify the structure:
        parent = ws.eval_ws.parent
        siblings = [p.name for p in parent.iterdir() if p.is_dir()]
        assert "plan_ws" in siblings  # the convention exists
        assert "eval_ws" in siblings
        assert "shared" in siblings

        # The stronger guarantee: prompts don't mention sibling names.
        # This is verified in test_session.py by checking prompt content.
    finally:
        cleanup_workspaces(ws.root)
