import asyncio
from typing import Any, Dict, List, Optional
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from maktab_downloader.config import settings
from maktab_downloader.db.database import db_instance
from maktab_downloader.db.repository import repo_instance
from maktab_downloader.network.client import MaktabClient
from maktab_downloader.utils.console import console, print_error, print_info, print_success, print_warning
from maktab_downloader.utils.helpers import format_bytes


class SizeInspector:
    """Inspects and caches resource sizes without downloading full video payloads (0 or 1 byte inspection)."""

    def __init__(
        self,
        client: Optional[MaktabClient] = None,
        concurrency: int = 10,
    ):
        self.client = client or MaktabClient()
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def _inspect_single_resource(
        self,
        item: Dict[str, Any],
        progress: Progress,
        task_id: int,
    ) -> Optional[int]:
        """Check size for a single resource and update database."""
        async with self.semaphore:
            # If size is already known and > 0, we can use it
            if item.get("total_bytes") and item["total_bytes"] > 0:
                progress.advance(task_id, 1)
                return item["total_bytes"]

            if item.get("size_mb") and item["size_mb"] > 0:
                bytes_val = int(item["size_mb"] * 1024 * 1024)
                await repo_instance.update_resource_size(item["resource_id"], bytes_val)
                progress.advance(task_id, 1)
                return bytes_val

            url = item["download_url"]
            unit_id = item["unit_id"]

            size_bytes = await self.client.get_resource_size(url=url, unit_id=unit_id)
            if size_bytes:
                await repo_instance.update_resource_size(item["resource_id"], size_bytes)

            progress.advance(task_id, 1)
            return size_bytes

    async def inspect_course_sizes(
        self,
        course_id: Optional[int] = None,
        preferred_quality: str = "1080p",
    ) -> Dict[str, Any]:
        """Inspect all selected quality resources for a course or all courses."""
        await db_instance.init_db()

        resources = await repo_instance.get_downloadable_resources(
            course_id=course_id,
            preferred_quality=preferred_quality,
            include_completed=True,
        )

        if not resources:
            return {"total_items": 0, "total_bytes": 0, "formatted_size": "0 B"}

        print_info(f"Inspecting sizes for {len(resources)} resources ({preferred_quality}) via HTTP HEAD/Range...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Calculating sizes...", total=len(resources))
            tasks = [
                self._inspect_single_resource(dict(r), progress, task)
                for r in resources
            ]
            sizes = await asyncio.gather(*tasks)

        total_bytes = sum(s for s in sizes if s)
        success_count = sum(1 for s in sizes if s)

        return {
            "total_items": len(resources),
            "inspected_items": success_count,
            "total_bytes": total_bytes,
            "formatted_size": format_bytes(total_bytes),
        }
