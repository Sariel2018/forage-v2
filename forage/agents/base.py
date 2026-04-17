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

    def __init__(
        self,
        workspace: str | None = None,           # DEPRECATED but still accepted
        knowledge_dir: str | None = None,
        private_ws: str | None = None,          # NEW: agent's private cwd
        shared_ws: str | None = None,           # NEW: shared dir path
    ):
        # Accept either old (workspace=) or new (private_ws + shared_ws) API
        if private_ws is not None:
            self.private_ws = Path(private_ws)
            self.shared_ws = Path(shared_ws) if shared_ws else self.private_ws
        elif workspace is not None:
            # Old API: private == shared (single workspace compat)
            self.private_ws = Path(workspace)
            self.shared_ws = Path(workspace)
        else:
            raise ValueError("Must pass either workspace= or private_ws=")

        # self.workspace stays as alias to private_ws for minimal churn
        self.workspace = self.private_ws
        self.private_ws.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir = knowledge_dir
        self.cost_usd = 0.0
        self.usage = {}  # full token usage from claude CLI
        self.session_id = str(uuid.uuid4())
        self.round_count = 0
        self.effort = "medium"  # default, overridden by spec
        self.model = "opus"  # default, overridden by spec

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
        Only salvages if files were modified AFTER the CLI call started
        (prevents returning stale data from previous rounds).

        Default implementation does nothing. Subclasses (EvaluatorAgent,
        PlannerAgent) override this with role-specific salvage logic that
        knows which files live in private_ws vs shared_ws.
        """
        return None

    def _save_cli_output(self, result) -> None:
        """Save raw claude CLI stdout/stderr to workspace for debugging."""
        agent_type = type(self).__name__.lower().replace("agent", "")
        log_dir = self.workspace / "cli_logs"
        log_dir.mkdir(exist_ok=True)
        # round_count has NOT been incremented yet (that happens in finally block)
        # so +1 to get the current round number
        round_num = self.round_count + 1
        prefix = f"r{round_num:02d}_{agent_type}"
        (log_dir / f"{prefix}_stdout.json").write_text(result.stdout if result.stdout else "")
        (log_dir / f"{prefix}_stderr.txt").write_text(result.stderr if result.stderr else "")
        # Save exit code
        (log_dir / f"{prefix}_exit.txt").write_text(str(result.returncode))

    def _save_cli_output_raw(self, stdout_bytes, reason: str = ""):
        """Save raw stdout on timeout/error (when subprocess.CompletedProcess isn't available)."""
        agent_type = type(self).__name__.lower().replace("agent", "")
        log_dir = self.workspace / "cli_logs"
        log_dir.mkdir(exist_ok=True)
        round_num = self.round_count + 1
        prefix = f"r{round_num:02d}_{agent_type}"
        stdout_str = stdout_bytes.decode("utf-8", errors="replace") if isinstance(stdout_bytes, bytes) else str(stdout_bytes)
        (log_dir / f"{prefix}_stdout.json").write_text(stdout_str)
        (log_dir / f"{prefix}_exit.txt").write_text(f"timeout ({reason})")

    def _build_command(self, user_message: str) -> list[str]:
        """Build the claude CLI command with session persistence flags.

        - First call (round_count == 0): --session-id UUID (creates session)
        - Subsequent calls (round_count > 0): --resume UUID (resumes session)
        """
        cmd = [
            "claude",
            "-p", user_message,
            "--output-format", "stream-json",
            "--verbose",
            "--max-turns", str(self.max_turns),
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--effort", self.effort,
            "--model", self.model,
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
                # Parse stdout even on error — stream-json has multiple lines
                cli_output = None
                if result.stdout and result.stdout.strip():
                    cli_output = self._parse_claude_output(result.stdout)
                    if isinstance(cli_output, dict):
                        self.cost_usd = cli_output.get("total_cost_usd", 0.0)
                        self.usage = cli_output.get("usage", {})

                # Check if this is max_turns exhaustion (not a real error)
                if cli_output and cli_output.get("subtype") == "error_max_turns":
                    # Agent ran out of turns but session is healthy — NEVER airdrop.
                    print(f"  (max_turns exhausted after {cli_output.get('num_turns', '?')} turns, salvaging from workspace)")
                    salvaged = self._salvage_from_workspace()
                    if salvaged:
                        salvaged["_max_turns_exhausted"] = True
                        return salvaged
                    # No work on disk, but session is still healthy — skip round, don't airdrop
                    return {"_max_turns_exhausted": True, "text": "Agent exhausted turns without producing output"}

                # Try to parse agent's response from stdout
                if cli_output:
                    parsed = self._parse_response(cli_output)
                    if parsed.get("text") != str(cli_output):
                        parsed["_cli_exit_code"] = result.returncode
                        return parsed

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

        except subprocess.TimeoutExpired as e:
            # stream-json: partial stdout may contain cost data + tool call history
            if e.stdout:
                self._save_cli_output_raw(e.stdout, "timeout")
                # Try to extract cost from partial stream output
                stdout_str = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else str(e.stdout)
                cli_output = self._parse_claude_output(stdout_str)
                if isinstance(cli_output, dict):
                    self.cost_usd = cli_output.get("total_cost_usd", 0.0)
                    self.usage = cli_output.get("usage", {})
            else:
                self._save_cli_output_raw(b"", "timeout_no_output")
                self.cost_usd = 0.0  # don't carry stale value
            # Timeout does NOT mean session is dead — NEVER airdrop.
            # Salvage work if available, otherwise skip round. Next round will --resume.
            salvaged = self._salvage_from_workspace()
            if salvaged:
                print(f"  (timeout after 1200s, but work found on disk — salvaging)")
                salvaged["_timeout"] = True
                return salvaged
            print(f"  (timeout after 1200s, no work on disk — skip round, resume next)")
            return {"_timeout": True, "text": "Agent timed out without producing output"}
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
        failed_cost = self.cost_usd  # save cost from first attempt

        # Check if the result indicates a failure
        if "error" not in result:
            return result

        # Before airdroping, check if agent already completed work on disk
        # (e.g., CLI crashed on output but eval.py/action.py were written)
        workspace_result = self._salvage_from_workspace()
        if workspace_result:
            print(f"  Warning: Agent CLI failed ({result['error']}) but work found on disk — salvaging")
            workspace_result["_cli_exit_code"] = result.get("error", "")
            return workspace_result

        print(f"  Warning: Agent session failed: {result['error']}")
        if result.get("stderr"):
            print(f"  STDERR: {result['stderr'][:500]}")
        print(f"  Airdropping replacement agent...")

        # Preserve failed agent's cli_logs before reset (avoid overwrite)
        log_dir = self.workspace / "cli_logs"
        if log_dir.is_dir():
            agent_type = type(self).__name__.lower().replace("agent", "")
            round_num = self.round_count  # already incremented by finally
            prefix = f"r{round_num:02d}_{agent_type}"
            for f in log_dir.glob(f"{prefix}_*"):
                f.rename(f.with_stem(f.stem + "_failed"))

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

        # round_count is 0, so run() will write CLAUDE.md automatically
        recovery_result = self.run(recovery_message)
        self.cost_usd += failed_cost  # add cost from failed first attempt
        recovery_result["_airdropped"] = True

        # If recovery also failed, reset for next round (fresh session)
        if "error" in recovery_result:
            print(f"  Warning: Recovery also failed. Resetting for next round.")
            self.session_id = str(uuid.uuid4())
            self.round_count = 0

        return recovery_result

    def _parse_claude_output(self, stdout: str) -> dict | str:
        """Parse the stream-json output from claude CLI.

        stream-json outputs one JSON object per line. The last line with
        type="result" contains the same data as json mode.
        """
        stdout = stdout.strip()
        if not stdout:
            return {"error": "empty output from claude CLI"}

        # Find the result line (last line with type=result)
        result_data = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict) and data.get("type") == "result":
                    result_data = data
            except json.JSONDecodeError:
                continue

        if result_data:
            return result_data

        # Fallback: try parsing as single JSON (backwards compat with json mode)
        try:
            data = json.loads(stdout)
            if isinstance(data, dict) and "result" in data:
                return data
            return data
        except json.JSONDecodeError:
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
