"""Tool definitions and execution for Forage agents.

Each agent gets the same set of tools but different system prompts
and permission boundaries.
"""

import subprocess
import sys
from pathlib import Path

import httpx

# Tool schemas for Claude API tool_use
TOOL_SCHEMAS = [
    {
        "name": "run_python",
        "description": (
            "Execute a Python script. The code will be written to a temp file "
            "and run. Returns stdout, stderr, and exit code. Use this to run "
            "collection scripts, data processing, or any computation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to run (default 300)",
                    "default": 300,
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for information. Use this to discover data sources, "
            "find API documentation, understand site structure, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch the content of a URL. Returns the text content. "
            "Use this to inspect sitemaps, API responses, page structure, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Max characters to return (default 50000)",
                    "default": 50000,
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file in the workspace directory. "
            "Creates parent directories if needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to workspace (default: root)",
                    "default": ".",
                },
            },
        },
    },
]


class ToolExecutor:
    """Executes tool calls within a sandboxed workspace."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.request_count = 0

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result as a string."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"Error: unknown tool '{tool_name}'"
        try:
            return handler(tool_input)
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _tool_run_python(self, inp: dict) -> str:
        code = inp["code"]
        timeout = inp.get("timeout", 300)

        script_path = self.workspace / "_temp_script.py"
        script_path.write_text(code)

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.workspace),
            )
            output = ""
            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"
            output += f"EXIT CODE: {result.returncode}"
            return output or "Script completed with no output."
        except subprocess.TimeoutExpired:
            return f"Error: script timed out after {timeout}s"
        finally:
            script_path.unlink(missing_ok=True)

    def _tool_web_search(self, inp: dict) -> str:
        # Use a simple search via DuckDuckGo HTML (no API key needed)
        query = inp["query"]
        self.request_count += 1
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                # Extract result snippets (simple extraction)
                from html.parser import HTMLParser

                class ResultParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.results = []
                        self._in_result = False
                        self._current = ""

                    def handle_starttag(self, tag, attrs):
                        attrs_dict = dict(attrs)
                        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
                            self._in_result = True
                            self._current = attrs_dict.get("href", "")

                    def handle_data(self, data):
                        if self._in_result:
                            self._current += f" | {data.strip()}"

                    def handle_endtag(self, tag):
                        if tag == "a" and self._in_result:
                            self._in_result = False
                            if self._current:
                                self.results.append(self._current)

                parser = ResultParser()
                parser.feed(resp.text)
                if parser.results:
                    return "\n".join(parser.results[:10])
                return "No results found."
        except Exception as e:
            return f"Search error: {e}"

    def _tool_web_fetch(self, inp: dict) -> str:
        url = inp["url"]
        max_length = inp.get("max_length", 50000)
        self.request_count += 1
        try:
            with httpx.Client(timeout=45, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; ForageBot/0.1)"},
                )
                resp.raise_for_status()
                text = resp.text[:max_length]
                return text
        except Exception as e:
            return f"Fetch error: {e}"

    def _tool_read_file(self, inp: dict) -> str:
        path = self.workspace / inp["path"]
        if not path.is_file():
            return f"Error: file not found: {inp['path']}"
        try:
            content = path.read_text()
            if len(content) > 100000:
                return content[:100000] + f"\n... (truncated, total {len(content)} chars)"
            return content
        except Exception as e:
            return f"Error reading file: {e}"

    def _tool_write_file(self, inp: dict) -> str:
        path = self.workspace / inp["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(inp["content"])
        return f"Written {len(inp['content'])} chars to {inp['path']}"

    def _tool_list_files(self, inp: dict) -> str:
        path = self.workspace / inp.get("path", ".")
        if not path.is_dir():
            return f"Error: not a directory: {inp.get('path', '.')}"
        entries = sorted(path.iterdir())
        lines = []
        for e in entries[:200]:
            rel = e.relative_to(self.workspace)
            prefix = "d" if e.is_dir() else "f"
            size = e.stat().st_size if e.is_file() else ""
            lines.append(f"[{prefix}] {rel}  {size}")
        return "\n".join(lines) or "(empty directory)"
