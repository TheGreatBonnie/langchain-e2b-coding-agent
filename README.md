# Coding Agent

An autonomous AI software engineer that solves coding tasks inside an isolated **E2B sandbox**, powered by **LangChain Deep Agents** and **OpenRouter**. Configured entirely through files on disk — no hardcoded prompts, no monolithic configuration.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   User (CLI)                           │
│  uv run python coding_agent.py "Build a data pipeline" │
└──────────────────────┬─────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────┐
│               create_deep_agent()                       │
│  ┌──────────┐ ┌────────────────┐ ┌──────────────────┐ │
│  │  Memory   │ │    Skills      │ │    Subagents      │ │
│  │ AGENTS.md │ │  planning/     │ │  researcher       │ │
│  │           │ │  code-review/  │ │  (web_search)     │ │
│  └──────────┘ └────────────────┘ └──────────────────┘ │
│                       │                                │
│  ┌────────────────────▼─────────────────────────────┐ │
│  │              E2BSandbox Backend                   │ │
│  │  ┌─────────────────────────────────────────────┐ │ │
│  │  │   Isolated Cloud Sandbox (/home/user/)       │ │ │
│  │  │   execute │ read_file │ write_file │ edit    │ │ │
│  │  │   glob    │ grep      │ ls                   │ │ │
│  │  └─────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────┘ │
│                       │                                │
│  ┌────────────────────▼─────────────────────────────┐ │
│  │              ChatOpenRouter                       │ │
│  │  (openrouter/owl-alpha → any LLM)                 │ │
│  └─────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────┐
│               Rich Terminal Display                     │
│  AgentDisplay — streaming plans, commands, previews     │
└────────────────────────────────────────────────────────┘
```

### Components

| Layer               | Technology                                                                 | Role                                                                                                                |
| ------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Agent Framework** | [Deep Agents](https://github.com/langchain-ai/deepagents)                  | `create_deep_agent()` wires memory, skills, subagents, backend, and tooling into a stateful agent graph             |
| **Sandbox**         | [E2B](https://e2b.dev)                                                     | Isolated cloud sandbox where all code execution happens — fully destroyed after each session                        |
| **Sandbox Backend** | [LangChain E2B](https://python.langchain.com/docs/integrations/tools/e2b/) | Bridges E2B into Deep Agents, auto-provides `execute`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `ls` |
| **LLM**             | [OpenRouter](https://openrouter.ai)                                        | Unified API for 300+ models — swap `openrouter/owl-alpha` for `claude-3-opus`, `gpt-4o`, `gemini-2.0`, etc.         |
| **Display**         | [Rich](https://rich.readthedocs.io)                                        | Real-time streaming terminal UI with tool icons, plan rendering, command output, file previews                      |
| **Web Search**      | DuckDuckGo (via langchain-community)                                       | Built-in research capability, no API key needed                                                                     |

### Config-Driven Design

All agent behavior is configured through files on disk, completely separate from code:

```
AGENTS.md          → System prompt & workflow (4-phase: Plan, Implement, Review, Deliver)
skills/planning/   → Skill: structured implementation planning
skills/code-review/→ Skill: automated code review with lint checks
subagents.yaml     → Delegated subagents (researcher with web_search)
```

Deep Agents loads these at runtime through the E2B sandbox filesystem, making behavior changes a matter of editing markdown — no code changes needed.

## Why Sandboxes?

Sandboxes are used for security. They let agents execute arbitrary code, access files, and use the network without compromising your credentials, local files, or host system. This isolation is essential when agents run autonomously.

Every command the agent runs and every file it touches happens inside an **ephemeral E2B cloud sandbox** — not on your machine. This is the foundation of the project's security model.

The agent can freely run `git clone`, `pip install`,`pytest`, spin up servers, and execute build pipelines, all without risking your local development environment. The sandbox provides a full Linux environment that mirrors a real developer workstation, giving the agent the same capabilities a human engineer would have.

**What sandboxes protect against:**

- **Host compromise** — `rm -rf /`, malware installation, credential theft, or any other destructive action is contained. The sandbox has zero access to your local filesystem, SSH keys, or running processes.
- **Unintended side effects** — The agent can freely install packages, modify system configs, kill processes, or write files anywhere. None of it affects your development environment.
- **Context injection** — Even if an attacker manipulates the agent into running arbitrary commands, the blast radius is limited to the sandbox, which is destroyed immediately after the session.

### Sandbox as Tool

This project uses the **Sandbox as Tool** pattern (as defined in the [Deep Agents sandbox documentation](https://docs.langchain.com/oss/python/deepagents/sandboxes)): the agent runs on your machine, but all file and shell operations (`execute`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `ls`) are forwarded to a remote E2B sandbox via the Deep Agents backend protocol.

```
Your Machine                  E2B Cloud
┌──────────────┐     ┌─────────────────────┐
│ Agent Logic  │────>│  Ephemeral Sandbox  │
│ LLM (OpenRouter) │  │  /home/user/        │
│ web_search tool  │  │  /home/user/projects│
│ Display (Rich)   │  │  python, pip, git   │
└──────────────┘     └─────────────────────┘
     ↑ No secrets          ↑ Destroyed after
     │ in sandbox             session ends
     └─────────────────────────────────────────
```

**Security guarantees:**

- **Host isolation** — The sandbox has no access to your local files, `.env`, SSH keys, or any other machine-local resource. It runs in a cloud VM with its own filesystem and network stack.
- **Ephemeral by design** — Created per session, destroyed when the session ends. No state persists between runs.
- **Secrets stay outside** — API keys (`OPENROUTER_API_KEY`, `E2B_API_KEY`) are only used by the host process, never uploaded to the sandbox. Tools that need authentication (like `web_search`) run on the host, not inside the sandbox — following the [security best practice of keeping credentials out of sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes#handling-secrets-safely).
- **Two-plane file access** — The agent uses `read_file`/`write_file` (sandbox-internal tools mediated by `execute()`) to work on files, while the host uses `upload_files`/`download_files` (native provider APIs) to seed the sandbox and retrieve results.

### Sandbox Lifecycle

```
Create ──► Seed ──► Execute ──► Sync ──► Kill
E2B       AGENTS.md  agent works   download  terminate
Sandbox   + skills/  + commands    changed   VM
          + project                files
```

1. **Create** — `E2BSandbox.create(timeout=3600)` provisions a cloud VM with a 1-hour timeout
2. **Seed** — `_upload_config()` sends AGENTS.md and skills/ to `/home/user/`; `_upload_project()` sends the target codebase to `/home/user/projects/`
3. **Execute** — The agent works inside the sandbox: reads, writes, edits files, runs shell commands, installs dependencies, executes tests
4. **Sync** — `_download_project()` fetches all changed files back to `projects/` on the host
5. **Kill** — `sandbox.kill()` terminates the VM, removing all trace of the session

---

## How It Works

### 1. Start

The agent launches an E2B sandbox, uploads agent configuration (`AGENTS.md`, `skills/`) to `/home/user/` and the target project to `/home/user/projects/`, then builds the agent graph via `create_deep_agent()`.

### 2. Execute

Each user task triggers a streaming session. The agent follows a phased workflow:

- **Plan** — Explores the codebase, writes a structured todo list (`write_todos`)
- **Research** — Delegates to the `researcher` subagent for API/language research via web search
- **Implement** — Reads, writes, and edits files inside the sandbox; runs commands
- **Review** — Runs tests, linters, and code review checks
- **Deliver** — Commits changes

All file operations and command execution happen inside the E2B sandbox — the agent never touches the host filesystem directly.

### 3. Sync

When execution finishes (or errors), the agent downloads all changed files from the sandbox back to the local `projects/` directory, then terminates the sandbox.

### 4. Display

Every step streams to the terminal in real time via Rich:

```
📋 Plan
  ✓ Add endpoint to main.py
  ✓ Write unit tests
  ✓ Run test suite

💭 Let me first explore the current codebase...
🔍 Finding: **/*.py
📖 Reading: src/main.py
✏️ Editing: src/main.py
    ┌─ 24 lines ───────────────────────────┐
    │ @app.get("/api/status")               │
    │ async def get_status():               │
    │     return {"status": "ok"}           │
    └────────────────────────────────────────┘
⚙️ python -m pytest -v
  | collected 1 item
  | tests/test_main.py ✓
  ✓ Command finished (exit: 0)
```

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) or pip

### Installation

```bash
git clone <repo>
cd coding-agent

# Create environment and install dependencies
uv sync

# Configure API keys
cp .env.example .env
```

### Configuration

Edit `.env` with your API keys:

```
OPENROUTER_API_KEY="sk-or-v1-..."
E2B_API_KEY="e2b_..."
```

| Variable             | Required | Description                      |
| -------------------- | -------- | -------------------------------- |
| `OPENROUTER_API_KEY` | Yes      | LLM access via OpenRouter        |
| `E2B_API_KEY`        | Yes      | Cloud sandbox for code execution |

---

## Usage

### Basic

```bash
# Explore a codebase and suggest improvements
uv run python coding_agent.py

# Write tests for an existing module
uv run python coding_agent.py "Write tests for main.py"

# Refactor a specific component
uv run python coding_agent.py "Refactor the authentication module to use async/await"

# Fix a bug
uv run python coding_agent.py "Fix the off-by-one error in pagination logic"
```

### Intermediate

```bash
# Build a multi-file project from scratch
uv run python coding_agent.py "Create a CLI tool in projects/cli/ that reads a CSV, validates rows, and outputs JSON"

# Add a feature with tests
uv run python coding_agent.py "Add a /health endpoint to the FastAPI app in projects/api/, write tests, and verify they pass"

# Refactor + research
uv run python coding_agent.py "Use task(researcher) to research SQLAlchemy async patterns, then refactor the database layer in projects/app/"

# Code review pass
uv run python coding_agent.py "Run code review on all files in projects/lib/, fix any issues found, and confirm tests still pass"
```

### Advanced

```bash
# Full pipeline with research, implementation, and review
uv run python coding_agent.py "Build a data pipeline in projects/pipeline/ that: 1) scrapes Hacker News top stories, 2) summarizes them with a local LLM, 3) saves to SQLite, 4) serves via a FastAPI endpoint. Use task(researcher) for API research."

# Multi-step refactor with subagent delegation
uv run python coding_agent.py "Use task(researcher) to research modern Python packaging standards, then restructure projects/mypkg/ to use pyproject.toml, add a CLI entry point, and write integration tests."

# Add observability to an existing service
uv run python coding_agent.py "Add structured logging and metrics middleware to the FastAPI app in projects/api/. Use task(researcher) to find the best approach for OpenTelemetry integration."

# Scaffold, implement, and validate a full microservice
uv run python coding_agent.py "Create a FastAPI microservice in projects/analytics/ that accepts POST webhooks, validates them against a JSON Schema, enqueues them to an in-memory queue, and exposes a GET endpoint for processed results. Write tests for all endpoints."

# Polyglot project setup
uv run python coding_agent.py "Set up a project in projects/bench/ with a Python CLI (click) and a Rust extension (maturin + pyo3). The CLI should call the Rust function to compute SHA-256 hashes of files."
```

### Project Layout

```
projects/        ← Target codebase the agent works on
```

The agent reads from and writes to `projects/`. Any project you place there becomes the agent's workspace inside the sandbox at `/home/user/projects/`.

---

## Customization

### Change the LLM

Edit the model line in `coding_agent.py`:

```python
model = ChatOpenRouter(model="openrouter/owl-alpha")
```

Swap to any model OpenRouter supports: `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`, `google/gemini-2.0-flash`, `meta-llama/llama-3.3-70b`, etc.

### Modify Agent Behavior

Edit `AGENTS.md` to change the system prompt, workflow phases, coding standards, or subagent delegation patterns — no code changes required.

### Add Skills

Drop a `SKILL.md` into a new directory under `skills/`. Deep Agents loads all skills automatically at runtime. Skills are triggered by name in the agent's task description.

### Add Subagents

Edit `subagents.yaml`:

```yaml
linting-agent:
  description: "Runs linting and formatting checks on Python code"
  system_prompt: "You are a linting specialist..."
  tools:
    - web_search
```

The agent delegates to subagents via `task(subagent_type="linting-agent")`.

### Extend Tools

The agent auto-inherits `execute`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, and `ls` from the E2B sandbox backend. To add custom tools (e.g., a database query tool), define a `@tool` function in `coding_agent.py` and add it to the `tools` list in `create_coding_agent()`.

---

## Project Structure

```
.
├── coding_agent.py        # Entry point: sandbox setup, agent creation, streaming loop
├── agent_display.py       # Rich terminal UI for streaming agent progress
├── AGENTS.md              # Agent system prompt and workflow definition
├── subagents.yaml         # Subagent definitions (research, etc.)
├── skills/
│   ├── planning/          # Planning skill (SKILL.md)
│   └── code-review/       # Code review skill (SKILL.md + lint_check.py)
├── projects/              # Target codebase workspace
├── pyproject.toml         # Python dependencies
└── .env.example           # API key template
```

---

## Key Design Decisions

- **Isolation-first** — All code execution happens in ephemeral E2B sandboxes. The host filesystem is never exposed. Sandboxes are destroyed after each session.
- **Config over code** — Agent behavior comes from `AGENTS.md` and `skills/`, not from Python. Changing how the agent works means editing markdown.
- **Deep Agents as the backbone** — `create_deep_agent()` provides memory, skill loading, subagent delegation, streaming, and state management out of the box.
- **Sandbox-provisioned tools** — File operations and shell commands are not custom tools; they come automatically from the E2B backend. Only custom logic (web search) needs a dedicated tool.
- **Separation of concerns** — Agent config lives at `/home/user/`, target project at `/home/user/projects/`. This keeps the agent's own configuration separate from the codebase it's modifying.
- **One API key for all LLMs** — OpenRouter provides a single endpoint for 300+ models. No vendor lock-in.
- **Zero-cost web search** — DuckDuckGo requires no API key, making the researcher subagent work out of the box.
