"""Scrpr Terminal UI — Claude Code inspired interface.

Run with: python -m app.tui
Requires backend running on localhost:8000.
"""
import asyncio
import httpx
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Header, Footer, Static, DataTable,
    RichLog, Button, Input, Label,
    TabbedContent, TabPane,
)
from textual.binding import Binding
from textual.screen import Screen

API_BASE = "http://localhost:8000/api"


async def api_get(path: str) -> dict | list:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{API_BASE}{path}")
        return resp.json()


async def api_post(path: str, data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}{path}", json=data or {})
        return resp.json()


class TableListView(Static):
    """Shows list of tables."""

    def compose(self) -> ComposeResult:
        yield Static("Loading tables...", id="table-list-content")

    async def on_mount(self) -> None:
        await self.refresh_tables()

    async def refresh_tables(self) -> None:
        try:
            data = await api_get("/tables")
            tables = data.get("items", data) if isinstance(data, dict) else data
            content = self.query_one("#table-list-content", Static)
            if not tables:
                content.update("[dim]No tables yet. Create one from the web UI.[/dim]")
                return
            lines = []
            for i, t in enumerate(tables):
                name = t.get("name", "?")
                tid = t.get("id", "")[:8]
                lines.append(f"  [{i+1}] [bold cyan]{name}[/] [dim]({tid})[/dim]")
            content.update("\n".join(lines))
        except Exception as e:
            content = self.query_one("#table-list-content", Static)
            content.update(f"[red]Error: {e}[/red]\n[dim]Is the backend running on :8000?[/dim]")


class TableView(Static):
    """Shows table data in a grid."""

    def __init__(self, table_id: str, table_name: str):
        super().__init__()
        self.table_id = table_id
        self.table_name = table_name

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.table_name}[/bold]", id="table-title")
        yield DataTable(id="data-grid")
        yield Static("", id="table-status")

    async def on_mount(self) -> None:
        await self.load_data()

    async def load_data(self) -> None:
        try:
            columns = await api_get(f"/tables/{self.table_id}/columns")
            rows = await api_get(f"/tables/{self.table_id}/rows")

            grid = self.query_one("#data-grid", DataTable)
            grid.clear(columns=True)

            # Add columns
            grid.add_column("#", key="row_num")
            col_map = {}
            for col in columns:
                col_type = col.get("type", "")
                label = col["name"]
                if col_type == "agent":
                    label = f"[cyan]{label}[/cyan] [dim](AI)[/dim]"
                elif col_type == "waterfall":
                    label = f"[cyan]{label}[/cyan] [dim](WF)[/dim]"
                key = col["id"]
                grid.add_column(label, key=key)
                col_map[col["id"]] = col["name"]

            # Add rows
            for i, row in enumerate(rows):
                cells = {c["column_id"]: c.get("value", "") or "" for c in row.get("cells", [])}
                values = [str(i + 1)]
                for col in columns:
                    val = cells.get(col["id"], "")
                    # Truncate long values
                    if len(val) > 40:
                        val = val[:37] + "..."
                    values.append(val)
                grid.add_row(*values, key=row["id"])

            status = self.query_one("#table-status", Static)
            status.update(f"[dim]{len(rows)} rows, {len(columns)} columns[/dim]")
        except Exception as e:
            status = self.query_one("#table-status", Static)
            status.update(f"[red]Error loading table: {e}[/red]")


class ScrprApp(App):
    """Scrpr Terminal UI."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
    }

    #sidebar {
        width: 30;
        border-right: solid $primary;
        padding: 1;
    }

    #content {
        width: 1fr;
        padding: 1;
    }

    #activity-log {
        height: 10;
        border-top: solid $primary;
        padding: 0 1;
    }

    DataTable {
        height: 1fr;
    }

    .action-bar {
        height: 3;
        padding: 0 1;
    }

    Button {
        margin: 0 1;
    }
    """

    TITLE = "Scrpr"
    SUB_TITLE = "Open-source Clay alternative"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "enrich", "Run Enrichment"),
        Binding("x", "export", "Export CSV"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.current_table_id = None
        self.current_table_name = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="sidebar"):
                yield Static("[bold cyan]Tables[/bold cyan]\n")
                yield TableListView(id="table-list")
                yield Static("\n[dim]Press number to select[/dim]")
            with Vertical(id="content"):
                yield Static("[dim]Select a table from the sidebar[/dim]", id="content-area")
        yield RichLog(id="activity-log", markup=True, highlight=True)
        yield Footer()

    async def on_mount(self) -> None:
        log = self.query_one("#activity-log", RichLog)
        log.write("[bold cyan]Scrpr[/bold cyan] Terminal UI started")
        log.write("[dim]Connecting to backend on localhost:8000...[/dim]")

        try:
            data = await api_get("/tables")
            tables = data.get("items", data) if isinstance(data, dict) else data
            log.write(f"[green]Connected![/green] {len(tables)} tables found")

            # Auto-select first table if any
            if tables:
                self.current_table_id = tables[0]["id"]
                self.current_table_name = tables[0]["name"]
                await self.load_table(self.current_table_id, self.current_table_name)
        except Exception as e:
            log.write(f"[red]Connection failed: {e}[/red]")
            log.write("[yellow]Make sure the backend is running: DATABASE_URL=... python -m uvicorn app.main:app --port 8000[/yellow]")

    async def load_table(self, table_id: str, table_name: str) -> None:
        self.current_table_id = table_id
        self.current_table_name = table_name

        content_container = self.query_one("#content")
        # Remove whatever is currently in the content area
        for child in list(content_container.children):
            if child.id != "activity-log":
                await child.remove()

        table_view = TableView(table_id, table_name)
        await content_container.mount(table_view)

        log = self.query_one("#activity-log", RichLog)
        log.write(f"Loaded table: [bold]{table_name}[/bold]")

    async def action_refresh(self) -> None:
        log = self.query_one("#activity-log", RichLog)
        log.write("[dim]Refreshing...[/dim]")
        table_list = self.query_one("#table-list", TableListView)
        await table_list.refresh_tables()
        if self.current_table_id:
            await self.load_table(self.current_table_id, self.current_table_name)

    async def action_enrich(self) -> None:
        log = self.query_one("#activity-log", RichLog)
        if not self.current_table_id:
            log.write("[yellow]No table selected[/yellow]")
            return
        log.write(f"[cyan]Triggering enrichment on {self.current_table_name}...[/cyan]")
        try:
            result = await api_post(f"/tables/{self.current_table_id}/enrich-all")
            log.write(f"[green]Triggered: {result.get('triggered', 0)} cells[/green]")
            log.write(f"  Agent: {result.get('agent_cells', 0)} | Waterfall: {result.get('waterfall_cells', 0)}")
        except Exception as e:
            log.write(f"[red]Enrichment failed: {e}[/red]")

    async def action_export(self) -> None:
        log = self.query_one("#activity-log", RichLog)
        if not self.current_table_id:
            log.write("[yellow]No table selected[/yellow]")
            return
        log.write(f"[dim]Export: open http://localhost:8000/api/tables/{self.current_table_id}/export-csv[/dim]")

    def action_help(self) -> None:
        log = self.query_one("#activity-log", RichLog)
        log.write("[bold]Keyboard shortcuts:[/bold]")
        log.write("  [cyan]r[/cyan] Refresh table data")
        log.write("  [cyan]e[/cyan] Run enrichment (all columns)")
        log.write("  [cyan]x[/cyan] Export to CSV")
        log.write("  [cyan]q[/cyan] Quit")
        log.write("  [cyan]?[/cyan] Show this help")


def main():
    app = ScrprApp()
    app.run()


if __name__ == "__main__":
    main()
