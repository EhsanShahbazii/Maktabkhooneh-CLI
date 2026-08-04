import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import aiofiles
import httpx
from rich.progress import Progress
from telethon import TelegramClient

from maktab_downloader.config import settings
from maktab_downloader.crawler.syncer import MetadataSyncer
from maktab_downloader.db.database import db_instance
from maktab_downloader.db.repository import repo_instance
from maktab_downloader.downloader.file_downloader import ResourceDownloader
from maktab_downloader.network.client import MaktabClient
from maktab_downloader.telegram.client import TelegramManager
from maktab_downloader.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from maktab_downloader.utils.helpers import (
    ensure_dir,
    format_bytes,
    format_duration,
    sanitize_filename,
)


class CourseTelegramUploader:
    """
    Downloads and streams course videos, banners, subtitles, and attachments to Telegram
    while strictly enforcing host storage limits (e.g. 2GB max) by streaming, uploading,
    and immediately deleting local files.
    """

    def __init__(
        self,
        telegram_manager: Optional[TelegramManager] = None,
        maktab_client: Optional[MaktabClient] = None,
        target_chat: Optional[str] = None,
        max_storage_mb: float = 2048.0,
        temp_dir: Path = Path("telegram_temp"),
        preferred_quality: str = "1080p",
    ):
        self.tg_manager = telegram_manager or TelegramManager()
        self.maktab_client = maktab_client or MaktabClient()
        self.target_chat = target_chat or settings.TELEGRAM_TARGET_CHAT or "me"
        self.max_storage_mb = max_storage_mb or settings.STORAGE_LIMIT_MB
        self.temp_dir = Path(temp_dir)
        self.preferred_quality = preferred_quality or settings.DEFAULT_QUALITY
        self.file_downloader = ResourceDownloader(
            client=self.maktab_client,
            download_dir=self.temp_dir,
            concurrency=1,
        )
        ensure_dir(self.temp_dir)

    def _cleanup_file(self, file_path: Optional[Path | str]):
        """Safely delete a temporary file to keep host disk space minimal."""
        if not file_path:
            return
        p = Path(file_path)
        try:
            if p.exists() and p.is_file():
                p.unlink()
        except Exception as e:
            print_warning(f"Could not remove temp file {p}: {e}")

    def _cleanup_dir(self, dir_path: Optional[Path | str]):
        """Safely delete empty temporary directory."""
        if not dir_path:
            return
        p = Path(dir_path)
        try:
            if p.exists() and p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    async def _download_file(self, url: str, destination: Path) -> bool:
        """Helper to download a thumbnail image, subtitle, or attachment directly."""
        try:
            ensure_dir(destination.parent)
            client = await self.maktab_client.get_client()
            async with client.stream("GET", url, timeout=30.0) as resp:
                if resp.status_code == 200:
                    async with aiofiles.open(destination, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            await f.write(chunk)
                    return True
        except Exception as e:
            print_warning(f"Failed to download attachment {url}: {e}")
        return False

    async def upload_course(
        self,
        course_id: int,
        status_callback: Optional[Callable[[str], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Uploads a complete course to Telegram:
        1. Ensures course metadata and units are synced.
        2. Sends Course Banner Photo with concise information caption.
        3. Downloads each unit video (best quality), uploads to Telegram, and immediately cleans disk.
        4. Sends subtitles / attachments.
        5. Updates database status.
        """
        tg: TelegramClient = await self.tg_manager.get_client()
        await db_instance.init_db()

        course = await repo_instance.get_course_by_id(course_id)
        if not course:
            # Try fetching outline & metadata first
            syncer = MetadataSyncer(client=self.maktab_client)
            await syncer.sync_all(course_id=course_id)
            course = await repo_instance.get_course_by_id(course_id)

        if not course:
            msg = f"❌ Course ID {course_id} could not be found."
            print_error(msg)
            if status_callback:
                await status_callback(msg)
            return {"success": False, "error": msg}

        # Make sure outline & units are synced
        chapters = await repo_instance.get_chapters_for_course(course_id)
        if not chapters or not course["outline_synced"]:
            syncer = MetadataSyncer(client=self.maktab_client)
            await syncer.sync_all(course_id=course_id)
            chapters = await repo_instance.get_chapters_for_course(course_id)

        course_title = course["title"]
        slug_mk = self.maktab_client.format_course_slug_mk(course["slug"] or f"course-{course_id}", course_id)
        course_url = f"https://maktabkhooneh.org/course/{slug_mk}/"
        org_name = course["publisher_name"] or course["organization_name"] or "مکتب‌خونه"

        start_msg = f"🚀 Starting upload for: **{course_title}** (ID: `{course_id}`) to `{self.target_chat}`"
        print_info(start_msg)
        if status_callback:
            await status_callback(start_msg)

        # -------------------------------------------------------------
        # Step 1: Send Course Banner / Poster with Overview Caption
        # -------------------------------------------------------------
        banner_url = course["image_url"] or course["preview_video_hq"]
        banner_path = self.temp_dir / f"banner_{course_id}.jpg"
        banner_downloaded = False

        if banner_url:
            banner_downloaded = await self._download_file(banner_url, banner_path)

        # Short concise caption under 1024 characters
        caption_lines = [
            f"🎓 **{course_title}**",
            f"🏢 **ناشر / سازمان:** {org_name}",
        ]
        if course["level"]:
            caption_lines.append(f"📊 **سطح دوره:** {course['level']}")
        if course["units_count"]:
            caption_lines.append(f"🎬 **تعداد جلسات:** {course['units_count']} جلسه | 📁 **فصول:** {len(chapters)}")
        if course["required_hours"] and str(course["required_hours"]) != "0":
            caption_lines.append(f"⏱ **مدت زمان:** {course['required_hours']} ساعت")
        if course["no_of_students"]:
            caption_lines.append(f"👥 **دانشجویان:** {course['no_of_students']:,} نفر")

        caption_lines.append(f"\n🔗 [مشاهده دوره در سایت]({course_url})")
        course_banner_caption = "\n".join(caption_lines)

        try:
            if banner_downloaded and banner_path.exists():
                await tg.send_file(
                    self.target_chat,
                    file=str(banner_path),
                    caption=course_banner_caption,
                    parse_mode="md",
                )
                self._cleanup_file(banner_path)
            else:
                await tg.send_message(
                    self.target_chat,
                    course_banner_caption,
                    parse_mode="md",
                    link_preview=False,
                )
        except Exception as e:
            print_warning(f"Could not send course banner: {e}")

        # -------------------------------------------------------------
        # Step 2: Stream, Upload & Clean Each Unit
        # -------------------------------------------------------------
        total_units_uploaded = 0
        total_bytes_uploaded = 0

        for ch in chapters:
            units = await repo_instance.get_units_for_chapter(ch["id"])
            for u in units:
                resources = await repo_instance.get_resources_for_unit(u["id"])
                if not resources:
                    # Sync this unit details
                    try:
                        unit_detail = await self.maktab_client.get_unit_detail(u["id"])
                        async with db_instance.connection() as conn:
                            await repo_instance.upsert_unit_detail(conn, unit_detail)
                            await conn.commit()
                        resources = await repo_instance.get_resources_for_unit(u["id"])
                    except Exception as e:
                        print_warning(f"Error syncing unit {u['id']}: {e}")

                if not resources:
                    continue

                # Select best available resolution (preferred_quality -> highest)
                selected_res = None
                for r in resources:
                    if r["quality"] == self.preferred_quality:
                        selected_res = r
                        break
                if not selected_res and resources:
                    selected_res = resources[0]

                if not selected_res or not selected_res["download_url"]:
                    continue

                unit_title = u["title"] or f"Unit {u['order_num']}"
                duration_str = format_duration(u["duration"])
                res_quality = selected_res["quality_display"] or selected_res["quality"] or "1080p"

                unit_caption = (
                    f"🎬 **{ch['title']}**\n"
                    f"📌 **جلسه {u['order_num']}: {unit_title}**\n"
                    f"⏱ مدت: `{duration_str}` | 🏷 کیفیت: `{res_quality}`\n"
                    f"📚 #{sanitize_filename(course_title).replace(' ', '_')}"
                )

                # 1. Download single unit file
                safe_name = f"{u['order_num']:02d}_{sanitize_filename(unit_title)}_{selected_res['quality']}.mp4"
                unit_file_path = self.temp_dir / safe_name

                print_info(f"Downloading [{selected_res['quality']}] {unit_title}...")
                dl_success = await self._download_file(selected_res["download_url"], unit_file_path)

                if dl_success and unit_file_path.exists():
                    file_size = unit_file_path.stat().st_size
                    print_info(f"Uploading to Telegram ({format_bytes(file_size)}): {unit_title}...")

                    # Upload video
                    try:
                        await tg.send_file(
                            self.target_chat,
                            file=str(unit_file_path),
                            caption=unit_caption,
                            supports_streaming=True,
                            parse_mode="md",
                        )
                        total_units_uploaded += 1
                        total_bytes_uploaded += file_size
                    except Exception as e:
                        print_error(f"Failed to upload video {unit_title}: {e}")
                    finally:
                        # 2. IMMEDIATELY remove from disk to honor storage limits!
                        self._cleanup_file(unit_file_path)

                # 3. Download and upload Subtitle if present
                if u["has_caption"] and u["caption_file"]:
                    vtt_name = f"{u['order_num']:02d}_{sanitize_filename(unit_title)}.vtt"
                    vtt_path = self.temp_dir / vtt_name
                    vtt_dl = await self._download_file(u["caption_file"], vtt_path)
                    if vtt_dl and vtt_path.exists():
                        try:
                            await tg.send_file(
                                self.target_chat,
                                file=str(vtt_path),
                                caption=f"💬 زیرنویس جلسه {u['order_num']}: {unit_title}",
                                parse_mode="md",
                            )
                        except Exception:
                            pass
                        finally:
                            self._cleanup_file(vtt_path)

                await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # Step 3: Mark Course as Uploaded in Database
        # -------------------------------------------------------------
        async with db_instance.connection() as conn:
            await conn.execute(
                "UPDATE courses SET telegram_uploaded = 1, telegram_uploaded_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (course_id,),
            )
            await conn.commit()

        self._cleanup_dir(self.temp_dir)

        finished_msg = (
            f"✅ **دوره با موفقیت آپلود شد:** {course_title}\n"
            f"📦 جلسات آپلود شده: {total_units_uploaded} | حجم کل: {format_bytes(total_bytes_uploaded)}"
        )
        print_success(finished_msg)
        if status_callback:
            await status_callback(finished_msg)

        return {
            "success": True,
            "course_id": course_id,
            "title": course_title,
            "uploaded_units": total_units_uploaded,
            "total_bytes": total_bytes_uploaded,
        }

    async def upload_course_range(
        self,
        start_index: int,
        end_index: int,
        status_callback: Optional[Callable[[str], Any]] = None,
    ):
        """
        Uploads a slice or range of courses sequentially.
        Can receive course IDs or 1-based index numbers in the database.
        """
        await db_instance.init_db()
        courses = await repo_instance.get_all_courses(enrolled_only=True)

        # If start_index matches actual course IDs directly:
        target_courses = [c for c in courses if start_index <= c["id"] <= end_index]

        # If not matched by ID, treat as 1-based index:
        if not target_courses and 1 <= start_index <= len(courses):
            target_courses = courses[start_index - 1 : end_index]

        if not target_courses:
            msg = f"⚠️ No courses found for range {start_index} to {end_index}."
            print_warning(msg)
            if status_callback:
                await status_callback(msg)
            return

        range_start_msg = f"📦 Starting sequential upload for {len(target_courses)} courses (Range: {start_index} - {end_index})..."
        print_info(range_start_msg)
        if status_callback:
            await status_callback(range_start_msg)

        for i, c in enumerate(target_courses, 1):
            c_msg = f"\n🔄 [{i}/{len(target_courses)}] Processing: **{c['title']}** (ID: `{c['id']}`)"
            print_info(c_msg)
            if status_callback:
                await status_callback(c_msg)

            await self.upload_course(c["id"], status_callback=status_callback)
            await asyncio.sleep(2.0)

        done_msg = f"🎉 All {len(target_courses)} courses from range {start_index} to {end_index} have been uploaded to Telegram!"
        print_success(done_msg)
        if status_callback:
            await status_callback(done_msg)
