"""Base agent class: uses Claude Code CLI (OAuth) as the LLM runtime.

Instead of calling the Anthropic API directly, we invoke `claude -p "prompt"`
as a subprocess. This uses the user's existing OAuth login — no API key needed.

Claude Code natively provides: Bash, Read, Write, WebSearch, WebFetch, Glob, Grep.
We don't need to define custom tools.
"""

import json
import subprocess
from pathlib import Path


class BaseAgent:
    """Base class for Forage agents.

    Each agent invocation is a separate `claude` CLI call with:
    - A system prompt (via CLAUDE.md in the workspace)
    - A user prompt describing the task
    - Working directory set to the isolated workspace
    """

    max_turns = 30

    def __init__(self, workspace: str, knowledge_dir: str | None = None):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir = knowledge_dir
        self.cost_usd = 0.0
        self.usage = {}  # full token usage from claude CLI

    @property
    def system_prompt(self) -> str:
        raise NotImplementedError

    def _load_knowledge(self) -> str:
        """Load knowledge files if available."""
        if not self.knowledge_dir:
            return ""
        knowledge_path = Path(self.knowledge_dir)
        if not knowledge_path.is_dir():
            return ""
        texts = []
        for f in sorted(knowledge_path.glob("*.md")):
            texts.append(f"## {f.stem}\n\n{f.read_text()}")
        return "\n\n---\n\n".join(texts) if texts else ""

    def run(self, user_message: str) -> dict:
        """Run the agent via Claude Code CLI.

        1. Write a CLAUDE.md with the system prompt to the workspace
        2. Call `claude -p "user_message"` with cwd=workspace
        3. Parse the output
        """
        # Write system prompt as CLAUDE.md in workspace
        system = self.system_prompt
        knowledge = self._load_knowledge()
        if knowledge:
            system += f"\n\n# Experience Knowledge Base\n\n{knowledge}"

        claude_md = self.workspace / "CLAUDE.md"
        claude_md.write_text(system)

        # Build the claude command
        cmd = [
            "claude",
            "-p", user_message,
            "--output-format", "json",
            "--max-turns", str(self.max_turns),
            "--dangerously-skip-permissions",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200,  # 20 min max per agent call
                cwd=str(self.workspace),
            )

            if result.returncode != 0:
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
            return {"error": "claude CLI timed out after 600s"}
        except Exception as e:
            return {"error": f"claude CLI error: {e}"}
        finally:
            # Clean up CLAUDE.md to avoid leaking system prompt
            claude_md.unlink(missing_ok=True)

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
