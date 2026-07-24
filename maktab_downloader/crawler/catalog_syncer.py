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


class CatalogSyncer:
    """Handles searching public courses, syncing rich landing page metadata, and course registration/enrollment."""

    def __init__(
        self,
        client: Optional[MaktabClient] = None,
        concurrency: int = 5,
    ):
        self.client = client or MaktabClient()
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def search_and_sync_catalog(
        self,
        query: str = "-",
        types: Optional[List[str]] = None,
        sorting: str = "new",
        max_pages: Optional[int] = None,
        limit_per_page: int = 12,
    ) -> int:
        """Search and crawl public catalog courses into SQLite database."""
        await db_instance.init_db()
        print_info(f"Searching public catalog courses (query='{query}', types={types or ['MAKTAB', 'PLUS', 'HAMAYESH']})...")

        page = 1
        offset = 0
        total_courses_count = None
        courses_synced = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Crawling catalog...", total=None)

            while True:
                try:
                    data = await self.client.search_catalog(
                        page=page,
                        offset=offset,
                        limit=limit_per_page,
                        types=types,
                        sorting=sorting,
                        q=query,
                    )
                except Exception as e:
                    print_error(f"Failed to fetch catalog search (page {page}): {e}")
                    break

                courses_data = data.get("courses") or {}
                if total_courses_count is None:
                    total_courses_count = courses_data.get("count", 0)
                    progress.update(task, total=total_courses_count)

                results = courses_data.get("results", [])
                if not results:
                    break

                async with db_instance.connection() as conn:
                    for item in results:
                        await repo_instance.upsert_course(conn, item, is_enrolled=False)
                    await conn.commit()

                courses_synced += len(results)
                progress.update(task, completed=courses_synced)

                if max_pages and page >= max_pages:
                    break

                if not courses_data.get("next") or courses_synced >= (total_courses_count or 0):
                    break

                page += 1
                offset += limit_per_page

        print_success(f"Catalog sync finished! Discovered and stored {courses_synced} courses.")
        return courses_synced

    async def _sync_single_landing(self, course: Dict[str, Any], progress: Progress, task_id: int) -> bool:
        """Sync landing page details for one course."""
        async with self.semaphore:
            c_id = course["id"]
            slug = course["slug"] or f"course-{c_id}"
            try:
                data = await self.client.get_course_landing_detail(slug, c_id)
                async with db_instance.connection() as conn:
                    await repo_instance.upsert_course_landing(conn, c_id, data)
                    await conn.commit()
                progress.advance(task_id, 1)
                return True
            except Exception as e:
                progress.advance(task_id, 1)
                return False

    async def sync_landing_details(self, course_id: Optional[int] = None, force_refresh: bool = False):
        """Fetch rich public landing page metadata for courses."""
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses()
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        if not force_refresh:
            courses_to_sync = [c for c in courses if not c["landing_synced"]]
        else:
            courses_to_sync = courses

        if not courses_to_sync:
            print_info("All course landing pages are already synced.")
            return

        print_info(f"Syncing landing details for {len(courses_to_sync)} courses (concurrency={self.concurrency})...")

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
            task = progress.add_task("[magenta]Fetching landing details...", total=len(courses_to_sync))
            tasks = [
                self._sync_single_landing(dict(c), progress, task)
                for c in courses_to_sync
            ]
            await asyncio.gather(*tasks)

        print_success("Completed course landing details sync.")

    async def check_actions_and_enroll(self, course_id: int) -> Dict[str, Any]:
        """Check course eligibility and enroll into the course."""
        await db_instance.init_db()
        course = await repo_instance.get_course_by_id(course_id)
        if not course:
            return {"success": False, "error": f"Course ID {course_id} not found in database."}

        slug = course["slug"] or f"course-{course_id}"

        # 1. Check actions
        try:
            actions_data = await self.client.get_course_actions(slug, course_id)
            async with db_instance.connection() as conn:
                await repo_instance.update_course_actions(conn, course_id, actions_data)
                await conn.commit()
        except Exception as e:
            return {"success": False, "error": f"Failed to check course actions: {e}"}

        cta = actions_data.get("actions", {}).get("call_to_action")
        cta_text = actions_data.get("actions", {}).get("call_to_action_text", "")
        enrollment = actions_data.get("enrollment") or {}

        if enrollment.get("access_level") and enrollment["access_level"] > 0:
            await repo_instance.mark_course_enrolled(course_id, True)
            return {"success": True, "status": "already_enrolled", "message": f"Already enrolled in '{course['title']}'!"}

        # 2. Perform enrollment
        try:
            enroll_res = await self.client.enroll_course(slug, course_id)
            if enroll_res.get("success"):
                await repo_instance.mark_course_enrolled(course_id, True)
                return {"success": True, "status": "enrolled", "message": f"Successfully enrolled in '{course['title']}' ({cta_text})!"}
            else:
                return {"success": False, "error": f"Enrollment returned status {enroll_res.get('status_code')}: {enroll_res.get('text')}"}
        except Exception as e:
            return {"success": False, "error": f"Enrollment request failed: {e}"}

    async def bulk_enroll(self, max_courses: int = 50) -> Dict[str, int]:
        """Bulk enroll in available Plus / Free courses from catalog."""
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses()
        unenrolled = [c for c in courses if not c["is_enrolled"]][:max_courses]

        if not unenrolled:
            print_info("No unenrolled courses found in catalog.")
            return {"enrolled": 0, "failed": 0, "skipped": 0}

        print_info(f"Attempting registration for {len(unenrolled)} courses...")
        enrolled_count = 0
        failed_count = 0

        for c in unenrolled:
            res = await self.check_actions_and_enroll(c["id"])
            if res.get("success"):
                enrolled_count += 1
                print_success(res.get("message", f"Enrolled: {c['title']}"))
            else:
                failed_count += 1
                print_warning(f"Skipped {c['title']}: {res.get('error')}")

        return {"enrolled": enrolled_count, "failed": failed_count}
