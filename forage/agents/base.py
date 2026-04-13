"""Base agent class: uses Claude Code CLI (OAuth) as the LLM runtime.

Instead of calling the Anthropic API directly, we invoke `claude -p "prompt"`
as a subprocess. This uses the user's existing OAuth login — no API key needed.

Claude Code natively provides: Bash, Read, Write, WebSearch, WebFetch, Glob, Grep.
We don't need to define custom tools.
"""

import json
import subprocess
import uuid
from pathlib import Path


class BaseAgent:
    """Base class for Forage agents.

    Uses persistent sessions (explorer team mode): the agent remembers
    everything within a run. First call creates a named session via
    --session-id; subsequent calls resume it via --resume.

    Each agent invocation is a `claude` CLI call with:
    - A system prompt (via CLAUDE.md in the workspace, written on first call)
    - A user prompt describing the task
    - Working directory set to the isolated workspace
    """

    max_turns = 15

    def __init__(self, workspace: str, knowledge_dir: str | None = None):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir = knowledge_dir
        self.cost_usd = 0.0
        self.usage = {}  # full token usage from claude CLI
        self.session_id = str(uuid.uuid4())
        self.round_count = 0

    @property
    def system_prompt(self) -> str:
        raise NotImplementedError

    def _load_knowledge(self) -> str:
        """Load all knowledge files (fallback for recovery mode)."""
        if not self.knowledge_dir:
            return ""
        knowledge_path = Path(self.knowledge_dir)
        if not knowledge_path.is_dir():
            return ""
        texts = []
        for f in sorted(knowledge_path.glob("*.md")):
            texts.append(f"## {f.stem}\n\n{f.read_text()}")
        return "\n\n---\n\n".join(texts) if texts else ""

    def _load_index(self) -> str:
        """Load INDEX.md from knowledge_dir (v2: agents read details on demand)."""
        if not self.knowledge_dir:
            return ""
        index_path = Path(self.knowledge_dir) / "INDEX.md"
        if not index_path.is_file():
            return ""
        return index_path.read_text()

    def _salvage_from_workspace(self) -> dict | None:
        """Check if agent completed work on disk despite CLI failure.

        Returns a fallback result dict if work is found, None otherwise.
        Subclasses can override to check for their specific output files.
        """
        import json as _json
        # Evaluator: eval.py + metrics.json
        eval_py = self.workspace / "eval.py"
        metrics_json = self.workspace / "metrics.json"
        if eval_py.is_file() and metrics_json.is_file():
            try:
                metrics = _json.loads(metrics_json.read_text())
                return {
                    "eval_script_path": "eval.py",
                    "denominator": metrics.get("denominator", "unknown"),
                    "denominator_source": metrics.get("denominator_source", "salvaged from metrics.json"),
                    "denominator_confidence": "medium",
                    "decision": "continue",
                    "decision_reason": "Salvaged from workspace (CLI failed but work completed)",
                    "_salvaged": True,
                }
            except (ValueError, KeyError):
                pass
        # Planner: collect.py
        collect_py = self.workspace / "collect.py"
        if collect_py.is_file():
            return {
                "strategy_name": "salvaged_strategy",
                "strategy_description": "Salvaged from workspace (CLI failed but collect.py written)",
                "collect_script_path": "collect.py",
                "_salvaged": True,
            }
        return None

    def _save_cli_output(self, result) -> None:
        """Save raw claude CLI stdout/stderr to workspace for debugging."""
        agent_type = type(self).__name__.lower().replace("agent", "")
        log_dir = self.workspace / "cli_logs"
        log_dir.mkdir(exist_ok=True)
        # round_count already reflects current round (incremented in finally after this)
        round_num = self.round_count + 1
        prefix = f"r{round_num:02d}_{agent_type}"
        if result.stdout:
            (log_dir / f"{prefix}_stdout.json").write_text(result.stdout[-50000:])
        if result.stderr:
            (log_dir / f"{prefix}_stderr.txt").write_text(result.stderr[-5000:])
        # Save exit code
        (log_dir / f"{prefix}_exit.txt").write_text(str(result.returncode))

    def _build_command(self, user_message: str) -> list[str]:
        """Build the claude CLI command with session persistence flags.

        - First call (round_count == 0): --session-id UUID (creates session)
        - Subsequent calls (round_count > 0): --resume UUID (resumes session)
        """
        cmd = [
            "claude",
            "-p", user_message,
            "--output-format", "json",
            "--max-turns", str(self.max_turns),
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
        ]

        if self.round_count == 0:
            cmd.extend(["--session-id", self.session_id])
        else:
            cmd.extend(["--resume", self.session_id])

        return cmd

    def run(self, user_message: str) -> dict:
        """Run the agent via Claude Code CLI.

        Uses persistent sessions (explorer team mode):
        - First call: writes CLAUDE.md + uses --session-id
        - Subsequent calls: reuses session via --resume (CLAUDE.md already there)
        """
        # Only write CLAUDE.md on first call — session persists it
        if self.round_count == 0:
            system = self.system_prompt
            index = self._load_index()
            if index:
                system += f"\n\n# Experience Knowledge Base\n\n{index}"
            claude_md = self.workspace / "CLAUDE.md"
            claude_md.write_text(system)

        cmd = self._build_command(user_message)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200,  # 20 min max per agent call
                cwd=str(self.workspace),
            )

            # Save raw CLI output for debugging (always, regardless of exit code)
            self._save_cli_output(result)

            if result.returncode != 0:
                # Still try to parse stdout — agent may have completed work
                # before CLI errored (e.g., output too large)
                if result.stdout and result.stdout.strip():
                    try:
                        output = self._parse_claude_output(result.stdout)
                        if isinstance(output, dict):
                            self.cost_usd = output.get("total_cost_usd", 0.0)
                            self.usage = output.get("usage", {})
                        parsed = self._parse_response(output)
                        if parsed.get("text") != str(output):
                            # Got a valid structured response despite exit code
                            parsed["_cli_exit_code"] = result.returncode
                            return parsed
                    except Exception:
                        pass
                return {
                    "error": f"claude CLI failed (exit {result.returncode})",
                    "stderr": result.stderr[-1000:] if result.stderr else "",
                }

            # Parse JSON output from claude CLI
            output = self._parse_claude_output(result.stdout)

            # Extract cost and token usage
            if isinstance(output, dict):
                self.cost_usd = output.get("total_cost_usd", 0.0)
                self.usage = output.get("usage", {})

            return self._parse_response(output)

        except subprocess.TimeoutExpired:
            return {"error": "claude CLI timed out after 1200s"}
        except Exception as e:
            return {"error": f"claude CLI error: {e}"}
        finally:
            self.round_count += 1

    def run_with_recovery(self, user_message: str, trajectory=None) -> dict:
        """Run with fault tolerance — airdrop replacement if agent fails.

        If the persistent session crashes or times out, creates a new session
        with a recovery summary from the trajectory. Maintains method isolation
        in the summary (only includes role-appropriate data).

        Returns dict with optional "_airdropped": True if recovery was used.
        """
        result = self.run(user_message)

        # Check if the result indicates a failure
        if "error" not in result:
            return result

        # Before airdroping, check if agent already completed work on disk
        # (e.g., CLI crashed on output but eval.py/collect.py were written)
        workspace_result = self._salvage_from_workspace()
        if workspace_result:
            print(f"  Warning: Agent CLI failed ({result['error']}) but work found on disk — salvaging")
            workspace_result["_cli_exit_code"] = result.get("error", "")
            return workspace_result

        print(f"  Warning: Agent session failed: {result['error']}")
        if result.get("stderr"):
            print(f"  STDERR: {result['stderr'][:500]}")
        print(f"  Airdropping replacement agent...")

        # New session (replacement agent)
        self.session_id = str(uuid.uuid4())
        old_round_count = self.round_count
        self.round_count = 0

        # Build recovery summary from trajectory
        recovery_summary = ""
        if trajectory:
            view = "evaluator" if "Evaluator" in type(self).__name__ else "planner"
            recovery_summary = trajectory.render_narrative(view=view)

        recovery_message = (
            f"[RECOVERY] You are replacing the previous agent who became "
            f"unavailable at round {old_round_count}.\n"
            f"Here is a summary of progress so far:\n\n"
            f"{recovery_summary}\n\n"
            f"Continue the task:\n{user_message}"
        )

        # Re-write CLAUDE.md for new session
        system = self.system_prompt
        index = self._load_index()
        if index:
            system += f"\n\n# Experience Knowledge Base\n\n{index}"
        claude_md = self.workspace / "CLAUDE.md"
        claude_md.write_text(system)

        recovery_result = self.run(recovery_message)
        recovery_result["_airdropped"] = True

        # If recovery also failed, reset for next round (fresh session)
        if "error" in recovery_result:
            print(f"  Warning: Recovery also failed. Resetting for next round.")
            self.session_id = str(uuid.uuid4())
            self.round_count = 0

        return recovery_result

    def _parse_claude_output(self, stdout: str) -> dict | str:
        """Parse the JSON output from claude CLI."""
        stdout = stdout.strip()
        if not stdout:
            return {"error": "empty output from claude CLI"}

        try:
            data = json.loads(stdout)
            # claude --output-format json returns {"result": "...", "cost_usd": ..., ...}
            if isinstance(data, dict) and "result" in data:
                return data
            return data
        except json.JSONDecodeError:
            # If not valid JSON, return as text
            return {"result": stdout}

    def _parse_response(self, output: dict | str) -> dict:
        """Extract the agent's structured response from claude output."""
        if isinstance(output, str):
            text = output
        elif isinstance(output, dict):
            text = output.get("result", str(output))
        else:
            text = str(output)

        if isinstance(text, str):
            text = text.strip()
            # Try to find a JSON object in the response (prefer {} over [])
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start = text.find(start_char)
                end = text.rfind(end_char)
                if start != -1 and end > start:
                    try:
                        parsed = json.loads(text[start : end + 1])
                        # Always return a dict — wrap lists
                        if isinstance(parsed, dict):
                            return parsed
                        elif isinstance(parsed, list):
                            return {"items": parsed}
                    except json.JSONDecodeError:
                        continue
            return {"text": text}

        return output if isinstance(output, dict) else {"text": str(output)}
