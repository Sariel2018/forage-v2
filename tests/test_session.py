# tests/test_session.py
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
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
    assert "json" in cmd
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
