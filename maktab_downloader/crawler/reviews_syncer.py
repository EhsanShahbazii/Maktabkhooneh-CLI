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


class ReviewsSyncer:
    """Collects and stores student reviews, user ratings, and instructor replies for courses."""

    def __init__(
        self,
        client: Optional[MaktabClient] = None,
        concurrency: int = 5,
    ):
        self.client = client or MaktabClient()
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def sync_reviews_for_course(
        self,
        course_id: int,
        limit_per_page: int = 12,
        max_pages: Optional[int] = None,
    ) -> int:
        """Fetch and store all reviews for a single course with pagination."""
        await db_instance.init_db()
        course = await repo_instance.get_course_by_id(course_id)
        if not course:
            print_error(f"Course ID {course_id} not found in database.")
            return 0

        slug = course["slug"] or f"course-{course_id}"
        page = 1
        offset = 0
        total_reviews = None
        reviews_synced = 0

        while True:
            try:
                data = await self.client.get_course_reviews(
                    slug_or_id=slug,
                    course_id=course_id,
                    page=page,
                    limit=limit_per_page,
                    offset=offset,
                )
            except Exception as e:
                print_warning(f"Error fetching reviews for course {course_id} (page {page}): {e}")
                break

            if total_reviews is None:
                total_reviews = data.get("count", 0)
                if total_reviews == 0:
                    break

            results = data.get("results", [])
            if not results:
                break

            async with db_instance.connection() as conn:
                for rev in results:
                    await repo_instance.upsert_review(conn, course_id, rev)
                await conn.commit()

            reviews_synced += len(results)

            if max_pages and page >= max_pages:
                break

            if not data.get("next") or reviews_synced >= (total_reviews or 0):
                break

            page += 1
            offset += limit_per_page

        return reviews_synced

    async def _sync_reviews_worker(self, course: Dict[str, Any], progress: Progress, task_id: int) -> int:
        """Worker for concurrent course review syncing."""
        async with self.semaphore:
            c_id = course["id"]
            count = await self.sync_reviews_for_course(c_id)
            progress.advance(task_id, 1)
            return count

    async def sync_all_reviews(
        self,
        course_id: Optional[int] = None,
        enrolled_only: bool = False,
    ):
        """Sync reviews for multiple courses concurrently."""
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses(enrolled_only=enrolled_only)
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        if not courses:
            print_info("No courses available to sync reviews.")
            return

        print_info(f"Syncing student reviews for {len(courses)} course(s) (concurrency={self.concurrency})...")

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
            task = progress.add_task("[yellow]Collecting reviews...", total=len(courses))
            tasks = [
                self._sync_reviews_worker(dict(c), progress, task)
                for c in courses
            ]
            results = await asyncio.gather(*tasks)

        total_synced = sum(results)
        print_success(f"Finished collecting reviews! Stored {total_synced} student reviews across {len(courses)} course(s).")
