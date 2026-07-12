import asyncio
from typing import Any, Dict, List, Optional
import httpx
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


class MetadataSyncer:
    """Orchestrates high-performance concurrent crawling and syncing of Maktabkhooneh course metadata."""

    def __init__(
        self,
        client: Optional[MaktabClient] = None,
        concurrency: Optional[int] = None,
    ):
        self.client = client or MaktabClient()
        self.concurrency = concurrency or settings.MAX_CONCURRENT_REQUESTS
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def sync_my_courses(self, limit: int = 24) -> int:
        """Fetch all enrolled courses and upsert into SQLite."""
        await db_instance.init_db()
        print_info("Starting sync of enrolled courses (My Courses)...")

        offset = 0
        total_count = None
        courses_fetched = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching course list...", total=None)

            while True:
                try:
                    data = await self.client.get_my_courses_page(limit=limit, offset=offset)
                except Exception as e:
                    print_error(f"Error fetching courses page (offset={offset}): {e}")
                    break

                if total_count is None:
                    total_count = data.get("count", 0)
                    progress.update(task, total=total_count)

                results = data.get("results", [])
                if not results:
                    break

                async with db_instance.connection() as conn:
                    for item in results:
                        await repo_instance.upsert_course(conn, item, is_enrolled=True)
                    await conn.commit()

                courses_fetched += len(results)
                progress.update(task, completed=courses_fetched)

                if not data.get("next") or courses_fetched >= total_count:
                    break

                offset += limit

        print_success(f"Synced {courses_fetched} enrolled courses into database.")
        return courses_fetched

    async def _sync_single_outline(self, course: Dict[str, Any], progress: Progress, task_id: int) -> bool:
        """Fetch outline for a single course with 403 auto-enrollment fallback."""
        async with self.semaphore:
            course_id = course["id"]
            slug = course.get("slug") or f"course-{course_id}"

            try:
                outline_data = await self.client.get_course_outline(course_id, slug=slug)
                async with db_instance.connection() as conn:
                    await repo_instance.upsert_outline(conn, course_id, outline_data)
                    await conn.commit()
                progress.advance(task_id, 1)
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    # Attempt auto-enrollment if access is forbidden
                    try:
                        enroll_res = await self.client.enroll_course(slug, course_id)
                        if enroll_res.get("success"):
                            # Retry outline
                            outline_data = await self.client.get_course_outline(course_id, slug=slug)
                            async with db_instance.connection() as conn:
                                await repo_instance.upsert_outline(conn, course_id, outline_data)
                                await repo_instance.mark_course_enrolled(course_id, True, conn=conn)
                                await conn.commit()
                            progress.advance(task_id, 1)
                            return True
                    except Exception:
                        pass

                    # Mark outline as restricted/locked so future syncs don't hang on it
                    async with db_instance.connection() as conn:
                        await conn.execute(
                            "UPDATE courses SET outline_synced = 2, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                            (course_id,),
                        )
                        await conn.commit()
                    progress.advance(task_id, 1)
                    return False
                else:
                    async with db_instance.connection() as conn:
                        await conn.execute(
                            "UPDATE courses SET outline_synced = -1, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                            (course_id,),
                        )
                        await conn.commit()
                    progress.advance(task_id, 1)
                    return False
            except Exception as e:
                try:
                    async with db_instance.connection() as conn:
                        await conn.execute(
                            "UPDATE courses SET outline_synced = -1, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                            (course_id,),
                        )
                        await conn.commit()
                except Exception:
                    pass
                progress.advance(task_id, 1)
                return False

    async def sync_outlines(
        self,
        course_id: Optional[int] = None,
        force_refresh: bool = False,
        enrolled_only: bool = True,
    ):
        """Fetch outlines (chapters and unit lists) for courses."""
        courses = await repo_instance.get_all_courses(enrolled_only=enrolled_only)
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        if not force_refresh:
            courses_to_sync = [c for c in courses if not c["outline_synced"]]
        else:
            courses_to_sync = courses

        if not courses_to_sync:
            print_info("All course outlines are already up to date.")
            return

        print_info(f"Syncing outlines for {len(courses_to_sync)} courses (concurrency={self.concurrency})...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[magenta]Syncing outlines...", total=len(courses_to_sync))
            tasks = [
                self._sync_single_outline(dict(c), progress, task)
                for c in courses_to_sync
            ]
            await asyncio.gather(*tasks)

        print_success("Completed course outlines sync.")

    async def _sync_single_unit(self, unit_id: int, progress: Progress, task_id: int) -> bool:
        """Fetch detailed metadata for a single unit and save resources to database."""
        async with self.semaphore:
            try:
                unit_data = await self.client.get_unit_detail(unit_id)
                async with db_instance.connection() as conn:
                    await repo_instance.upsert_unit_detail(conn, unit_data)
                    await conn.commit()
                progress.advance(task_id, 1)
                return True
            except httpx.HTTPStatusError as e:
                async with db_instance.connection() as conn:
                    await repo_instance.mark_unit_error(conn, unit_id, f"HTTP {e.response.status_code}")
                    await conn.commit()
                progress.advance(task_id, 1)
                return False
            except Exception as e:
                async with db_instance.connection() as conn:
                    await repo_instance.mark_unit_error(conn, unit_id, str(e))
                    await conn.commit()
                progress.advance(task_id, 1)
                return False

    async def sync_units(self, course_id: Optional[int] = None, force_refresh: bool = False):
        """Fetch unit details and video download resources."""
        if force_refresh:
            units = await repo_instance.get_all_units(course_id)
        else:
            units = await repo_instance.get_pending_units(course_id)

        if not units:
            print_info("All unit details and video links are already up to date.")
            return

        print_info(f"Syncing {len(units)} unit details & video links (concurrency={self.concurrency})...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[yellow]Fetching unit details...", total=len(units))
            tasks = [
                self._sync_single_unit(u["id"], progress, task)
                for u in units
            ]
            await asyncio.gather(*tasks)

        print_success("Completed unit details & video resources sync.")

    async def sync_all(
        self,
        course_id: Optional[int] = None,
        force_refresh: bool = False,
        enrolled_only: bool = True,
    ):
        """Execute end-to-end full synchronization."""
        await db_instance.init_db()
        await self.sync_my_courses()
        await self.sync_outlines(course_id=course_id, force_refresh=force_refresh, enrolled_only=enrolled_only)
        await self.sync_units(course_id=course_id, force_refresh=force_refresh)
        print_success("🎉 Full sync finished successfully! Database is completely up to date.")
