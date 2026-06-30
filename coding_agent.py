#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")

"""
Coding Agent

An autonomous coding agent configured entirely through files on disk:
- AGENTS.md defines the agent's behavior and workflow
- skills/ provides specialized workflows (planning, code review)
- subagents handle research and other delegated tasks
- Tools execute inside an E2B sandbox for safety

Usage:
    uv run python coding_agent.py "Refactor the authentication module"
    uv run python coding_agent.py "Write tests for main.py"
"""

from dotenv import load_dotenv

load_dotenv()

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import yaml
from e2b import Sandbox as E2BSandbox
from langchain_e2b import E2BSandbox as E2BBackend
from langchain_openrouter import ChatOpenRouter

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from deepagents import create_deep_agent

EXAMPLE_DIR = Path(__file__).parent
console = Console()

sandbox: Optional[E2BSandbox] = None
backend: Optional[E2BBackend] = None

model = ChatOpenRouter(model="openrouter/owl-alpha")

IGNORE_DIRS = {
    ".venv", ".git", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules",
}
REMOTE_CONFIG = "/home/user"
REMOTE_HOME = f"{REMOTE_CONFIG}/projects"
PROJECTS_DIR = EXAMPLE_DIR / "projects"


def _should_skip(rel_path: Path) -> bool:
    parts = rel_path.parts
    for p in parts:
        if p in IGNORE_DIRS or p.startswith("."):
            return True
    return False


def _upload_config():
    """Upload agent config files (AGENTS.md, skills/) to the sandbox root.

    These are loaded by deepagents middleware via the sandbox backend,
    so they must exist on the sandbox filesystem.
    """
    if backend is None or sandbox is None:
        return

    config_files = []

    agents_md = EXAMPLE_DIR / "AGENTS.md"
    if agents_md.exists():
        config_files.append((f"{REMOTE_CONFIG}/AGENTS.md", agents_md.read_bytes()))

    skills_dir = EXAMPLE_DIR / "skills"
    if skills_dir.exists():
        for file_path in skills_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(EXAMPLE_DIR)
            config_files.append((f"{REMOTE_CONFIG}/{rel}", file_path.read_bytes()))

    if config_files:
        backend.upload_files(config_files)


def _upload_project():
    if backend is None or sandbox is None:
        return
    sandbox.commands.run(f"mkdir -p {REMOTE_HOME}")

    if not PROJECTS_DIR.exists():
        return

    files = []
    for file_path in PROJECTS_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(PROJECTS_DIR)
        if _should_skip(rel):
            continue
        files.append((f"{REMOTE_HOME}/{rel}", file_path.read_bytes()))
    if files:
        backend.upload_files(files)


def _download_project():
    if backend is None or sandbox is None:
        return
    result = sandbox.commands.run(
        f"find {REMOTE_HOME} -type f ! -name '*.pyc' 2>/dev/null || true"
    )
    remote_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    if not remote_files:
        return
    results = backend.download_files(remote_files)
    for r in results:
        if r.content is None:
            continue
        local_path = PROJECTS_DIR / Path(r.path).relative_to(REMOTE_HOME)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(r.content)


@tool
def web_search(query: str, max_results: int = 5, topic: str = "general") -> dict:
    """Search the web for current information.

    Args:
        query: The search query (be specific and detailed)
        max_results: Number of results to return (default: 5)
        topic: 'general' for most queries, 'news' for current events

    Returns:
        Search results with titles, URLs, and content excerpts.
    """
    if not query.strip():
        return {"error": "Empty query"}
    try:
        from tavily import TavilyClient
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return {"error": "TAVILY_API_KEY not set"}
        client = TavilyClient(api_key=api_key)
        return client.search(query, max_results=max_results, topic=topic)
    except ImportError:
        return {"error": "tavily package not installed"}
    except Exception as e:
        return {"error": f"Search failed: {e}"}


def load_subagents(config_path: Path) -> list:
    """Load subagent definitions from YAML and wire up tools."""
    available_tools = {
        "web_search": web_search,
    }
    if not config_path.exists():
        return []
    with open(config_path) as f:
        config = yaml.safe_load(f)
        if config is None:
            return []
    subagents = []
    for name, spec in config.items():
        subagent = {
            "name": name,
            "description": spec["description"],
            "system_prompt": spec["system_prompt"],
        }
        if "model" in spec:
            subagent["model"] = spec["model"]
        if "tools" in spec:
            subagent["tools"] = [
                available_tools[t] for t in spec["tools"] if t in available_tools
            ]
        subagents.append(subagent)
    return subagents


def create_coding_agent():
    """Create a coding agent configured by filesystem files.

    Uses E2B sandbox as the deepagents backend, which automatically
    provides execute, ls, read_file, write_file, edit_file, glob, and grep tools
    through the FilesystemMiddleware.
    """
    return create_deep_agent(
        model=model,
        memory=[f"{REMOTE_CONFIG}/AGENTS.md"],
        skills=[f"{REMOTE_CONFIG}/skills/"],
        tools=[web_search],
        subagents=load_subagents(EXAMPLE_DIR / "subagents.yaml"),
        backend=backend,
    )


class AgentDisplay:
    """Manages the display of agent progress."""

    def __init__(self):
        self.printed_count = 0
        self.spinner = Spinner("dots", text="Thinking...")

    def update_spinner(self, text: str):
        self.spinner = Spinner("dots", text=text)

    def print_message(self, msg):
        if isinstance(msg, HumanMessage):
            console.print(Panel(str(msg.content), title="You", border_style="blue"))

        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if content and content.strip():
                console.print(
                    Panel(Markdown(content), title="Agent", border_style="green")
                )

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name", "unknown")
                    args = tc.get("args", {})
                    if name == "execute":
                        cmd = args.get("command", "")
                        console.print(f"  [bold yellow]>> Running:[/] {cmd[:80]}...")
                        self.update_spinner(f"Running: {cmd[:30]}...")
                    elif name == "read_file":
                        path = args.get("file_path", "")
                        console.print(f"  [bold cyan]>> Reading:[/] {path}")
                    elif name == "write_file":
                        path = args.get("file_path", "")
                        console.print(f"  [bold yellow]>> Writing:[/] {path}")
                        self.update_spinner(f"Writing: {path}")
                    elif name == "edit_file":
                        path = args.get("file_path", "")
                        console.print(f"  [bold yellow]>> Editing:[/] {path}")
                    elif name == "web_search":
                        query = args.get("query", "")
                        console.print(f"  [bold blue]>> Searching:[/] {query[:50]}...")
                        self.update_spinner(f"Searching: {query[:30]}...")
                    elif name == "glob":
                        pat = args.get("pattern", "")
                        console.print(f"  [bold magenta]>> Finding:[/] {pat}")
                    elif name == "grep":
                        pat = args.get("pattern", "")
                        console.print(f"  [bold magenta]>> Searching code:[/] {pat[:40]}...")
                    elif name == "task":
                        desc = args.get("description", "delegating...")
                        console.print(f"  [bold magenta]>> Delegating:[/] {desc[:60]}...")
                        self.update_spinner(f"Delegating: {desc[:30]}...")

        elif isinstance(msg, ToolMessage):
            name = getattr(msg, "name", "")
            if name == "execute":
                console.print(f"  [green]✓ Command executed[/]")
            elif name in ("write_file", "edit_file"):
                console.print(f"  [green]✓ File written[/]")
            elif name == "web_search":
                if "error" not in msg.content.lower()[:100]:
                    console.print(f"  [green]✓ Search complete[/]")
            elif name == "task":
                console.print(f"  [green]✓ Subagent complete[/]")


async def main():
    """Run the coding agent with streaming output."""
    global sandbox, backend

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Explore the current codebase and suggest improvements"

    console.print()
    console.print("[bold blue]Coding Agent[/]")
    console.print(f"[dim]Task: {task}[/]")
    console.print()

    console.print("[dim]Starting E2B sandbox...[/]")
    try:
        sandbox = E2BSandbox.create()
        backend = E2BBackend(sandbox=sandbox, workdir=REMOTE_HOME)
        console.print("[green]✓ Sandbox ready[/]")
        console.print("[dim]Uploading agent config to sandbox...[/]")
        _upload_config()
        console.print("[dim]Uploading projects/ to sandbox...[/]")
        _upload_project()
        console.print("[green]✓ Project files uploaded[/]")
    except Exception as e:
        console.print(f"[red]✗ Failed to start sandbox: {e}[/]")
        console.print("[yellow]Make sure E2B_API_KEY is set in your environment[/]")
        return

    console.print()

    agent = create_coding_agent()
    display = AgentDisplay()

    try:
        with Live(
            display.spinner, console=console, refresh_per_second=10, transient=True
        ) as live:
            async for chunk in agent.astream(
                {"messages": [("user", task)]},
                config={"configurable": {"thread_id": "coding-agent-session"}},
                stream_mode="values",
            ):
                if "messages" in chunk:
                    messages = chunk["messages"]
                    if len(messages) > display.printed_count:
                        live.stop()
                        for msg in messages[display.printed_count:]:
                            display.print_message(msg)
                        display.printed_count = len(messages)
                        live.start()
                        live.update(display.spinner)
    except Exception as e:
        console.print(f"[red]Error during agent execution: {e}[/]")
    finally:
        console.print()
        console.print("[dim]Syncing changes back to local project...[/]")
        _download_project()
        console.print("[green]✓ Changes synced[/]")
        console.print("[dim]Closing sandbox...[/]")
        if sandbox is not None:
            sandbox.kill()
        console.print("[dim]Sandbox closed[/]")

    console.print()
    console.print("[bold green]✓ Done![/]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/]")
