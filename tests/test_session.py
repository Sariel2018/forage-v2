# tests/test_session.py
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from forage.agents.base import BaseAgent


def test_agent_has_session_id():
    """Each agent instance gets a unique session ID."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    assert hasattr(agent, "session_id")
    assert len(agent.session_id) == 36  # UUID format


def test_first_call_uses_session_id():
    """First call uses --session-id flag."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    cmd = agent._build_command("test message")
    assert "--session-id" in cmd
    assert agent.session_id in cmd
    assert "--resume" not in cmd


def test_subsequent_call_uses_resume():
    """After first call, uses --resume flag."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    agent.round_count = 1  # simulate first call done
    cmd = agent._build_command("test message")
    assert "--resume" in cmd
    assert agent.session_id in cmd
    assert "--session-id" not in cmd


def test_session_id_is_valid_uuid():
    """session_id is a valid UUID4."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    parsed = uuid.UUID(agent.session_id)
    assert parsed.version == 4


def test_round_count_starts_at_zero():
    """round_count initializes to 0."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    assert agent.round_count == 0


def test_build_command_includes_base_flags():
    """_build_command always includes output-format, max-turns, skip-permissions."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    cmd = agent._build_command("hello")
    assert "claude" in cmd
    assert "-p" in cmd
    assert "hello" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--max-turns" in cmd
    assert "--dangerously-skip-permissions" in cmd


def test_load_index_returns_index_content():
    """_load_index reads INDEX.md from knowledge_dir."""
    with tempfile.TemporaryDirectory() as d:
        index_path = Path(d) / "INDEX.md"
        index_path.write_text("# Knowledge Base Index\n\n- [proxy_check](universal/proxy_check.md)")
        agent = BaseAgent.__new__(BaseAgent)
        agent.__init__(workspace="/tmp/test_workspace_session", knowledge_dir=d)
        result = agent._load_index()
        assert "proxy_check" in result


def test_load_index_returns_empty_when_no_dir():
    """_load_index returns empty string when no knowledge_dir."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    result = agent._load_index()
    assert result == ""


def test_load_index_returns_empty_when_no_index_file():
    """_load_index returns empty string when INDEX.md doesn't exist."""
    with tempfile.TemporaryDirectory() as d:
        agent = BaseAgent.__new__(BaseAgent)
        agent.__init__(workspace="/tmp/test_workspace_session", knowledge_dir=d)
        result = agent._load_index()
        assert result == ""


def test_two_agents_have_different_sessions():
    """Two agent instances get different session IDs."""
    agent1 = BaseAgent.__new__(BaseAgent)
    agent1.__init__(workspace="/tmp/test_workspace_session_1")
    agent2 = BaseAgent.__new__(BaseAgent)
    agent2.__init__(workspace="/tmp/test_workspace_session_2")
    assert agent1.session_id != agent2.session_id


def test_model_defaults_to_opus():
    """model attribute defaults to 'opus'."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    assert agent.model == "opus"


def test_build_command_includes_model():
    """_build_command includes --model flag."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    cmd = agent._build_command("hello")
    idx = cmd.index("--model")
    assert cmd[idx + 1] == "opus"


def test_build_command_includes_custom_model():
    """_build_command passes through custom model."""
    agent = BaseAgent.__new__(BaseAgent)
    agent.__init__(workspace="/tmp/test_workspace_session")
    agent.model = "sonnet"
    cmd = agent._build_command("hello")
    idx = cmd.index("--model")
    assert cmd[idx + 1] == "sonnet"


# --- New API: per-role workspace isolation -------------------------------


def test_new_api_private_and_shared_ws():
    """BaseAgent(private_ws=..., shared_ws=...) sets both attributes correctly."""
    with tempfile.TemporaryDirectory() as d:
        priv = Path(d) / "private"
        shared = Path(d) / "shared"
        priv.mkdir()
        shared.mkdir()
        agent = BaseAgent.__new__(BaseAgent)
        agent.__init__(private_ws=str(priv), shared_ws=str(shared))
        assert agent.private_ws == priv
        assert agent.shared_ws == shared
        assert agent.private_ws != agent.shared_ws
        # workspace alias points to private_ws
        assert agent.workspace == priv


def test_old_api_sets_both_to_same():
    """BaseAgent(workspace=...) sets private_ws == shared_ws == workspace."""
    with tempfile.TemporaryDirectory() as d:
        agent = BaseAgent.__new__(BaseAgent)
        agent.__init__(workspace=d)
        assert agent.private_ws == Path(d)
        assert agent.shared_ws == Path(d)
        assert agent.private_ws == agent.shared_ws
        assert agent.workspace == Path(d)


def test_missing_both_raises():
    """BaseAgent() with no workspace/private_ws raises ValueError."""
    agent = BaseAgent.__new__(BaseAgent)
    with pytest.raises(ValueError):
        agent.__init__()


def test_new_api_shared_defaults_to_private():
    """If only private_ws is passed, shared_ws defaults to private_ws."""
    with tempfile.TemporaryDirectory() as d:
        priv = Path(d) / "private"
        priv.mkdir()
        agent = BaseAgent.__new__(BaseAgent)
        agent.__init__(private_ws=str(priv))
        assert agent.private_ws == priv
        assert agent.shared_ws == priv


def test_build_command_uses_private_ws_as_cwd():
    """run() uses private_ws as the subprocess cwd."""
    with tempfile.TemporaryDirectory() as d:
        priv = Path(d) / "private"
        shared = Path(d) / "shared"
        priv.mkdir()
        shared.mkdir()

        # Give the agent a concrete system_prompt so run() doesn't raise.
        class _FakeAgent(BaseAgent):
            @property
            def system_prompt(self) -> str:
                return "fake system prompt"

        agent = _FakeAgent(private_ws=str(priv), shared_ws=str(shared))

        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = '{"type":"result","result":"{}","total_cost_usd":0.0,"usage":{}}'
        fake_result.stderr = ""

        with patch("forage.agents.base.subprocess.run", return_value=fake_result) as mock_run:
            agent.run("hello")
            # cwd kwarg should be private_ws string, not shared_ws
            _, kwargs = mock_run.call_args
            assert kwargs["cwd"] == str(priv)
            assert kwargs["cwd"] != str(shared)


def test_evaluator_prompt_uses_shared_paths():
    """Evaluator system_prompt references shared/ not raw paths."""
    from forage.agents.evaluator import EvaluatorAgent
    agent = EvaluatorAgent.__new__(EvaluatorAgent)
    agent.__init__(workspace="/tmp/test_eval_prompt")
    prompt = agent.system_prompt
    # New paths must be present
    assert "shared/dataset" in prompt
    assert "shared/metrics.json" in prompt
    assert "shared/eval_contract.md" in prompt
    # Workspace layout section
    assert "Your workspace layout" in prompt


def test_planner_prompt_uses_shared_paths():
    """Planner system_prompt references shared/ not raw paths."""
    from forage.agents.planner import PlannerAgent
    agent = PlannerAgent.__new__(PlannerAgent)
    agent.__init__(workspace="/tmp/test_plan_prompt")
    prompt = agent.system_prompt
    assert "shared/dataset" in prompt
    assert "shared/metrics.json" in prompt
    assert "shared/eval_contract.md" in prompt
    assert "Your workspace layout" in prompt
