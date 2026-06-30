from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

TOOL_ICONS = {
    "execute": "⚙️",
    "read_file": "📖",
    "write_file": "📝",
    "edit_file": "✏️",
    "write_todos": "📋",
    "web_search": "🌐",
    "glob": "🔍",
    "grep": "🔍",
    "ls": "📂",
    "task": "🎯",
}

TODO_STATUS_ICONS = {"pending": "○", "in_progress": "◐", "completed": "✓"}
TODO_STATUS_COLORS = {"pending": "white", "in_progress": "yellow", "completed": "green"}


class AgentDisplay:
    """Manages the display of agent progress."""

    def __init__(self, console: Console):
        self.console = console
        self.seen_ids: set[str] = set()
        self.spinner = Spinner("dots", text="Thinking...")

    def update_spinner(self, text: str):
        self.spinner = Spinner("dots", text=text)

    def _render_content(self, content: str | list | object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return "\n".join(parts)
        return str(content) if content else ""

    def _render_toolbar(self, msg):
        content = self._render_content(msg.content)
        if content and content.strip() and msg.tool_calls:
            lines = [l for l in content.strip().split("\n") if l.strip()]
            preview = "\n".join(lines[:3])
            if len(lines) > 3:
                preview += "\n  [dim]...[/]"
            self.console.print(f"  [dim]💭 {preview}[/]")

    def _render_todos(self, todos: list[dict]) -> None:
        if not todos:
            return
        self.console.print("\n  [bold white]📋 Plan[/]")
        for todo in todos:
            if not isinstance(todo, dict):
                continue
            content = str(todo.get("content", "")).strip() or "Untitled step"
            status = str(todo.get("status", "pending")).strip()
            icon = TODO_STATUS_ICONS.get(status, "•")
            color = TODO_STATUS_COLORS.get(status, "white")
            self.console.print(f"  [{color}]{icon} {content}[/]")
        active = next(
            (t.get("content", "") for t in todos if isinstance(t, dict) and t.get("status") == "in_progress"),
            None,
        )
        if active:
            self.update_spinner(f"Planning: {active[:40]}...")

    def _render_file_preview(self, file_path: str, content: str):
        line_count = content.count("\n") + 1
        preview_lines = content.split("\n")[:5]
        self.console.print(
            f"  {TOOL_ICONS['write_file']} Writing: [yellow]{file_path}[/]"
        )
        self.console.print(
            f"    [dim]┌─ {line_count} lines ───────────────────────┐[/]"
        )
        for line in preview_lines:
            self.console.print(f"    [dim]│ {line[:80]}[/]")
        if line_count > 5:
            self.console.print(
                f"    [dim]│ ... ({line_count - 5} more lines)[/]"
            )
        self.console.print(f"    [dim]└────────────────────────────────────────┘[/]")

    def _render_tool_calls(self, tool_calls: list[dict]):
        for tc in tool_calls:
            name = tc.get("name", "unknown")
            args = tc.get("args", {})
            icon = TOOL_ICONS.get(name, "⚙️")

            if name == "task":
                desc = args.get("description", "delegating...")
                subagent_type = args.get("subagent_type", "")
                if subagent_type == "researcher":
                    self.console.print(f"\n  [bold magenta]🎯 Phase: Research[/]")
                else:
                    self.console.print(f"  {icon} [dim]{desc[:60]}...[/]")
                self.update_spinner(f"Working: {desc[:30]}...")
            elif name == "write_todos":
                todos = args.get("todos", [])
                if isinstance(todos, list):
                    self._render_todos(todos)
                else:
                    self.console.print(f"\n  [bold white]{icon} Planning[/]")
            elif name == "execute":
                cmd = args.get("command", "")
                self.console.print(f"  {icon} [dim]{cmd[:100]}[/]")
                self.update_spinner(f"Running: {cmd[:30]}...")
            elif name == "write_file":
                path = args.get("file_path", "")
                content = args.get("content", "")
                self._render_file_preview(path, content)
                self.update_spinner("Writing code...")
            elif name == "edit_file":
                path = args.get("file_path", "")
                self.console.print(f"  {icon} Editing: [yellow]{path}[/]")
            elif name == "read_file":
                path = args.get("file_path", "")
                self.console.print(f"  {icon} Reading: [dim]{path}[/]")
            elif name == "web_search":
                query = args.get("query", "")
                self.console.print(f"  {icon} Searching: [dim]{query[:50]}...[/]")
                self.update_spinner(f"Searching: {query[:30]}...")
            elif name == "glob":
                pat = args.get("pattern", "")
                self.console.print(f"  {icon} Finding: [dim]{pat}[/]")
            elif name == "grep":
                pat = args.get("pattern", "")
                self.console.print(f"  {icon} Grepping: [dim]{pat[:40]}...[/]")
            else:
                self.console.print(f"  {icon} [dim]{name}(...)[/]")

    def _render_execute_output(self, msg: ToolMessage):
        output = str(msg.content).strip() if msg.content else ""
        if not output:
            self.console.print(f"  [green]✓ Command executed[/]")
            return
        lines = output.split("\n")
        for line in lines[:20]:
            self.console.print(f"  [dim]| {line[:120]}[/]")
        if len(lines) > 20:
            self.console.print(
                f"  [dim]| ... ({len(lines) - 20} more lines)[/]"
            )
        code = 0
        if hasattr(msg, "additional_kwargs") and msg.additional_kwargs:
            code = msg.additional_kwargs.get("exit_code", 0)
        color = "green" if code == 0 else "red"
        self.console.print(f"  [{color}]✓ Command finished (exit: {code})[/]")

    def print_message(self, msg):
        if msg.id and msg.id in self.seen_ids:
            return
        if msg.id:
            self.seen_ids.add(msg.id)

        if isinstance(msg, HumanMessage):
            return

        if isinstance(msg, AIMessage):
            content = self._render_content(msg.content)
            if msg.tool_calls:
                self._render_toolbar(msg)

            if content and content.strip() and not msg.tool_calls:
                self.console.print(
                    Panel(Markdown(content), title="Agent", border_style="green")
                )

            if msg.tool_calls:
                self._render_tool_calls(msg.tool_calls)
            return

        if isinstance(msg, ToolMessage):
            name = getattr(msg, "name", "") or ""
            if name == "execute":
                self._render_execute_output(msg)
            elif name in ("write_file", "edit_file"):
                self.console.print(f"  [green]✓ File saved[/]")
            elif name == "write_todos":
                self.console.print(f"  [green]✓ Plan updated[/]")
            elif name == "web_search":
                if "error" not in str(msg.content).lower()[:100]:
                    self.console.print(f"  [green]✓ Search complete[/]")
            elif name == "task":
                self.console.print(f"  [green]✓ Phase complete[/]")
                self.update_spinner("Coordinating...")
