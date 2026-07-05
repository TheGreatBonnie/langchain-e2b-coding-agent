#!/usr/bin/env python3

# ── Suppress noisy Pydantic V1 deprecation warnings from dependencies ──
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

# ── Environment ─────────────────────────────────────────
# Load .env so that E2B_API_KEY and other secrets are available
from dotenv import load_dotenv

load_dotenv()

# ── Imports ─────────────────────────────────────────────
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
from os import getenv

import yaml
from e2b import Sandbox as E2BSandbox
from langchain_e2b import E2BSandbox as E2BBackend
from langchain_openrouter import ChatOpenRouter
from langchain_openai import ChatOpenAI

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.tools import tool
from rich.console import Console
from rich.live import Live

from agent_display import AgentDisplay

from deepagents import create_deep_agent

# ── Paths & Globals ─────────────────────────────────────

# The directory this script lives in; used to find AGENTS.md, skills/, projects/
EXAMPLE_DIR = Path(__file__).parent
console = Console()

# Shared sandbox and backend references, set once in main()
sandbox: Optional[E2BSandbox] = None
backend: Optional[E2BBackend] = None

# The LLM that drives the coding agent
model = ChatOpenRouter(model="nvidia/nemotron-3-ultra-550b-a55b:free")
# llm = ChatOpenAI(
#     openai_api_key=getenv("REQUESTY_API_KEY"),
#     openai_api_base=getenv("https://router.requesty.ai/v1"),
#     model_name="tensorx/deepseek-v4-flash",
# )

# ── Configuration Constants ─────────────────────────────

# Directories to skip when uploading/downloading project files
IGNORE_DIRS = {
    ".venv", ".git", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules",
}

# Remote sandbox paths
REMOTE_CONFIG = "/home/user"
REMOTE_HOME = f"{REMOTE_CONFIG}/projects"
PROJECTS_DIR = EXAMPLE_DIR / "projects"


# ══════════════════════════════════════════════════════════
#  HELPER: File-filter predicate
# ══════════════════════════════════════════════════════════

def _should_skip(rel_path: Path) -> bool:
    """Return True if a relative path should be excluded from upload/download."""
    parts = rel_path.parts
    for p in parts:
        # Skip directories that match IGNORE_DIRS or start with a dot
        if p in IGNORE_DIRS or p.startswith("."):
            return True
    return False


# ══════════════════════════════════════════════════════════
#  SANDBOX FILE OPERATIONS
# ══════════════════════════════════════════════════════════

def _upload_config():
    """Upload agent config files (AGENTS.md, skills/) to the sandbox root.

    These are loaded by deepagents middleware via the sandbox backend,
    so they must exist on the sandbox filesystem.
    """
    if backend is None or sandbox is None:
        return

    config_files = []

    # Collect AGENTS.md if present
    agents_md = EXAMPLE_DIR / "AGENTS.md"
    if agents_md.exists():
        config_files.append((f"{REMOTE_CONFIG}/AGENTS.md", agents_md.read_bytes()))

    # Collect every file under skills/ recursively
    skills_dir = EXAMPLE_DIR / "skills"
    if skills_dir.exists():
        for file_path in skills_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(EXAMPLE_DIR)
            config_files.append((f"{REMOTE_CONFIG}/{rel}", file_path.read_bytes()))

    # Upload collected files to the sandbox in a single batch
    if config_files:
        backend.upload_files(config_files)


def _upload_project():
    """Upload the local projects/ directory to the sandbox."""
    if backend is None or sandbox is None:
        return

    # Ensure remote project directory exists
    sandbox.commands.run(f"mkdir -p {REMOTE_HOME}")

    if not PROJECTS_DIR.exists():
        return

    files = []
    for file_path in PROJECTS_DIR.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(PROJECTS_DIR)
        # Skip files in ignored directories
        if _should_skip(rel):
            continue
        files.append((f"{REMOTE_HOME}/{rel}", file_path.read_bytes()))

    if files:
        backend.upload_files(files)


def _download_project():
    """Download changed files from the sandbox back to the local projects/ directory."""
    if backend is None or sandbox is None:
        return

    # List all remote files (excluding .pyc artifacts)
    result = sandbox.commands.run(
        f"find {REMOTE_HOME} -type f ! -name '*.pyc' 2>/dev/null || true"
    )
    remote_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    if not remote_files:
        return

    # Download all files and write them to the matching local path
    results = backend.download_files(remote_files)
    for r in results:
        if r.content is None:
            continue
        local_path = PROJECTS_DIR / Path(r.path).relative_to(REMOTE_HOME)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(r.content)


# ══════════════════════════════════════════════════════════
#  TOOLS
# ══════════════════════════════════════════════════════════

@tool
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for current information.

    Args:
        query: The search query (be specific and detailed)
        max_results: Number of results to return (default: 5)

    Returns:
        Search results with titles, URLs, and content excerpts.
    """
    if not query.strip():
        return {"error": "Empty query"}
    try:
        wrapper = DuckDuckGoSearchAPIWrapper(max_results=max_results)
        results = wrapper.results(query, max_results=max_results)
        return {
            "results": [
                {
                    "title": r["title"],
                    "url": r["link"],
                    "content": r["snippet"],
                }
                for r in results
            ]
        }
    except Exception as e:
        return {"error": f"Search failed: {e}"}


# ══════════════════════════════════════════════════════════
#  SUBAGENT LOADING
# ══════════════════════════════════════════════════════════

def load_subagents(config_path: Path) -> list:
    """Load subagent definitions from YAML and wire up tools."""
    # Tools available for subagents to use
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
        # Optionally override the default model for this subagent
        if "model" in spec:
            subagent["model"] = spec["model"]
        # Wire up tool references by name
        if "tools" in spec:
            subagent["tools"] = [
                available_tools[t] for t in spec["tools"] if t in available_tools
            ]
        subagents.append(subagent)

    return subagents


# ══════════════════════════════════════════════════════════
#  AGENT FACTORY
# ══════════════════════════════════════════════════════════

def create_coding_agent():
    """Create a coding agent configured by filesystem files.

    Uses E2B sandbox as the deepagents backend, which automatically
    provides execute, ls, read_file, write_file, edit_file, glob, and grep tools
    through the FilesystemMiddleware.
    """
    return create_deep_agent(
        model=model,
        # AGENTS.md is injected as a system-prompt memory
        memory=[f"{REMOTE_CONFIG}/AGENTS.md"],
        # Every .md file under skills/ is loaded as a skill
        skills=[f"{REMOTE_CONFIG}/skills/"],
        tools=[web_search],
        subagents=load_subagents(EXAMPLE_DIR / "subagents.yaml"),
        backend=backend,
    )


# ══════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════

async def main():
    """Run the coding agent with streaming output."""
    global sandbox, backend

    # ── Parse task from CLI args, fall back to a default ──
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Explore the current codebase and suggest improvements"

    # ── Print startup banner ──
    console.print()
    console.print("[bold blue]Coding Agent[/]")
    console.print(f"[dim]Task: {task}[/]")
    console.print()

    console.print("[dim]Starting E2B sandbox...[/]")

    # ── Create sandbox and upload files ──
    try:
        sandbox = E2BSandbox.create(timeout=3600)
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

    # ── Instantiate agent and display helper ──
    agent = create_coding_agent()
    display = AgentDisplay(console=console)

    # ── Stream agent responses with a live-updating spinner ──
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
                    live.stop()
                    for msg in chunk["messages"]:
                        display.print_message(msg)
                    live.start()
                    live.update(display.spinner)

    except Exception as e:
        console.print(f"[red]Error during agent execution: {e}[/]")

    finally:
        # ── Sync results back and clean up ──
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


# ══════════════════════════════════════════════════════════
#  SCRIPT ENTRY POINT
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/]")
