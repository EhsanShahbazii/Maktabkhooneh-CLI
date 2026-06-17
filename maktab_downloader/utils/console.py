from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta",
    "title": "bold cyan",
    "muted": "dim white",
})

console = Console(theme=custom_theme)


def print_banner():
    banner_text = (
        "[bold cyan]Maktabkhooneh Downloader & Metadata Scraper[/bold cyan]\n"
        "[dim]Created by Ehsan Shahbazi • High-performance Concurrent Crawler & Downloader[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def print_success(msg: str):
    console.print(f"[success]✓[/success] {msg}")


def print_info(msg: str):
    console.print(f"[info]ℹ[/info] {msg}")


def print_warning(msg: str):
    console.print(f"[warning]⚠[/warning] {msg}")


def print_error(msg: str):
    console.print(f"[error]✖[/error] {msg}")
