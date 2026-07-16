import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiofiles
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from maktab_downloader.config import settings
from maktab_downloader.db.database import db_instance
from maktab_downloader.db.repository import repo_instance
from maktab_downloader.network.client import MaktabClient
from maktab_downloader.utils.console import console, print_error, print_info, print_success, print_warning
from maktab_downloader.utils.helpers import ensure_dir, sanitize_filename


class ResourceDownloader:
    """High-performance concurrent file & video downloader with resume support, auto-refresh of expired tokens, and rich progress."""

    def __init__(
        self,
        client: Optional[MaktabClient] = None,
        download_dir: Optional[Path | str] = None,
        concurrency: Optional[int] = None,
    ):
        self.client = client or MaktabClient()
        self.download_dir = Path(download_dir or settings.DOWNLOAD_DIR)
        self.concurrency = concurrency or settings.MAX_CONCURRENT_DOWNLOADS
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def _build_target_path(self, item: Dict[str, Any], extension: str = "mp4") -> Path:
        """Construct a clean, Persian-safe directory structure for the resource."""
        course_name = sanitize_filename(item["course_title"])
        course_dir_name = f"{course_name} [mk{item['course_id']}]"

        ch_order = item.get("chapter_order", 1) or 1
        ch_name = sanitize_filename(item.get("chapter_title") or f"Chapter {ch_order}")
        chapter_dir_name = f"{ch_order:02d}. {ch_name}"

        u_order = item.get("unit_order", 1) or 1
        u_name = sanitize_filename(item.get("unit_title") or f"Unit {u_order}")
        quality_tag = f"[{item.get('quality', '1080p')}]"
        file_name = f"{u_order:02d}. {u_name} {quality_tag}.{extension}"

        target_dir = self.download_dir / course_dir_name / chapter_dir_name
        ensure_dir(target_dir)
        return target_dir / file_name

    async def _download_file(
        self,
        url: str,
        target_path: Path,
        progress: Progress,
        task_id: int,
        unit_id: Optional[int] = None,
    ) -> bool:
        """Download file with HTTP Range resume support and token refresh on 403."""
        part_path = target_path.with_suffix(target_path.suffix + ".part")

        # Check if already completed
        if target_path.exists() and target_path.stat().st_size > 0:
            progress.update(task_id, completed=100, visible=False)
            return True

        current_url = url
        resume_byte_pos = part_path.stat().st_size if part_path.exists() else 0

        async with self.semaphore:
            client = await self.client.get_client()

            for attempt in range(3):
                headers = {}
                if resume_byte_pos > 0:
                    headers["Range"] = f"bytes={resume_byte_pos}-"

                try:
                    async with client.stream("GET", current_url, headers=headers, timeout=settings.DOWNLOAD_TIMEOUT) as response:
                        # If expired URL (403/410) and unit_id is known, try refreshing unit details
                        if response.status_code in [401, 403, 410] and unit_id:
                            print_warning(f"URL expired for unit {unit_id}. Refreshing fresh download link...")
                            fresh_unit = await self.client.get_unit_detail(unit_id)
                            async with db_instance.connection() as conn:
                                await repo_instance.upsert_unit_detail(conn, fresh_unit)
                                await conn.commit()

                            # Find fresh url matching quality
                            for r in fresh_unit.get("resources", []):
                                if r.get("download_url"):
                                    current_url = r["download_url"]
                                    break
                            continue

                        response.raise_for_status()

                        is_range_response = response.status_code == 206
                        content_len_str = response.headers.get("content-length")
                        content_len = int(content_len_str) if content_len_str else 0

                        if is_range_response:
                            total_size = resume_byte_pos + content_len
                            file_mode = "ab"
                        else:
                            total_size = content_len
                            resume_byte_pos = 0
                            file_mode = "wb"

                        progress.update(task_id, total=total_size, completed=resume_byte_pos, visible=True)

                        async with aiofiles.open(part_path, file_mode) as f:
                            async for chunk in response.aiter_bytes(chunk_size=settings.CHUNK_SIZE):
                                await f.write(chunk)
                                progress.advance(task_id, len(chunk))

                        # Download completed successfully
                        if part_path.exists():
                            part_path.rename(target_path)
                        progress.update(task_id, visible=False)
                        return True

                except Exception as e:
                    if attempt == 2:
                        print_error(f"Download failed for {target_path.name}: {e}")
                        return False
                    await asyncio.sleep(2.0)

            return False

    async def _download_single_resource(
        self,
        item: Dict[str, Any],
        progress: Progress,
        overall_task: int,
    ) -> bool:
        """Download video resource and its accompanying caption / poster."""
        target_path = self._build_target_path(item)
        res_id = item["resource_id"]
        unit_id = item["unit_id"]

        # Add per-file task to progress
        file_task = progress.add_task(
            f"[cyan]{target_path.name[:35]}...",
            total=100,
            visible=True,
        )

        await repo_instance.update_resource_download_status(res_id, "downloading")

        success = await self._download_file(
            url=item["download_url"],
            target_path=target_path,
            progress=progress,
            task_id=file_task,
            unit_id=unit_id,
        )

        if success:
            file_size = target_path.stat().st_size if target_path.exists() else 0
            await repo_instance.update_resource_download_status(
                resource_id=res_id,
                status="completed",
                local_path=str(target_path),
                downloaded_bytes=file_size,
                total_bytes=file_size,
            )

            # Also download subtitle / caption if present
            if settings.DOWNLOAD_CAPTIONS and item.get("has_caption") and item.get("caption_file"):
                caption_url = item["caption_file"]
                if caption_url and not caption_url.endswith("file="):
                    caption_path = target_path.with_suffix(".vtt")
                    if not caption_path.exists():
                        sub_task = progress.add_task(f"[dim]Caption: {caption_path.name[:25]}", visible=False)
                        await self._download_file(caption_url, caption_path, progress, sub_task)

            progress.advance(overall_task, 1)
            progress.remove_task(file_task)
            return True
        else:
            await repo_instance.update_resource_download_status(
                resource_id=res_id,
                status="failed",
                error_msg="Network error or expired token",
            )
            progress.advance(overall_task, 1)
            progress.remove_task(file_task)
            return False

    async def download_course_resources(
        self,
        course_id: Optional[int] = None,
        preferred_quality: str = "1080p",
        include_completed: bool = False,
    ):
        """Download matching resources for courses."""
        await db_instance.init_db()

        resources = await repo_instance.get_downloadable_resources(
            course_id=course_id,
            preferred_quality=preferred_quality,
            include_completed=include_completed,
        )

        if not resources:
            print_info("No pending video resources found to download.")
            return

        print_info(
            f"Found {len(resources)} resources to download (Quality: {preferred_quality}, Concurrency: {self.concurrency})..."
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            overall_task = progress.add_task(
                f"[bold green]Overall Download Progress ({len(resources)} items)",
                total=len(resources),
            )

            tasks = [
                self._download_single_resource(dict(r), progress, overall_task)
                for r in resources
            ]
            results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r)
        print_success(f"Finished downloading! ({success_count}/{len(resources)} succeeded)")
