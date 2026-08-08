import asyncio
import re
from typing import Optional
from telethon import events, TelegramClient

from maktab_downloader.config import settings
from maktab_downloader.telegram.client import TelegramManager
from maktab_downloader.telegram.uploader import CourseTelegramUploader
from maktab_downloader.utils.console import print_info, print_success, print_warning


class TelegramBotService:
    """Listens for Telegram commands (/maktab <start> <end>, /upload <id>) and runs uploads."""

    def __init__(
        self,
        telegram_manager: Optional[TelegramManager] = None,
        target_chat: Optional[str] = None,
        max_storage_mb: float = 2048.0,
    ):
        self.tg_manager = telegram_manager or TelegramManager()
        self.target_chat = target_chat or settings.TELEGRAM_TARGET_CHAT or "me"
        self.max_storage_mb = max_storage_mb or settings.STORAGE_LIMIT_MB
        self.uploader = CourseTelegramUploader(
            telegram_manager=self.tg_manager,
            target_chat=self.target_chat,
            max_storage_mb=self.max_storage_mb,
        )

    async def start(self):
        """Start listening for commands on Telegram."""
        client: TelegramClient = await self.tg_manager.get_client()

        print_success("Telegram Bot / Userbot is active and listening for commands!")
        print_info("Available commands on Telegram:")
        print_info("  • /maktab <start_index_or_id> <end_index_or_id>  (Upload range of courses)")
        print_info("  • /upload <course_id>                          (Upload specific course)")
        print_info("  • /help                                         (Show command guide)")

        @client.on(events.NewMessage(pattern=r"(?i)^/maktab\s+(\d+)\s+(\d+)"))
        async def handle_range_upload(event):
            match = re.match(r"(?i)^/maktab\s+(\d+)\s+(\d+)", event.raw_text.strip())
            if not match:
                return
            start_val = int(match.group(1))
            end_val = int(match.group(2))

            reply_msg = await event.reply(
                f"⏳ دریافت دستور آپلود دوره‌ها از `{start_val}` تا `{end_val}`...\n"
                f"فضای ذخیره‌سازی موقت: `{self.max_storage_mb} MB`\n"
                f"مقصد: `{self.target_chat}`"
            )

            async def status_callback(text: str):
                try:
                    await client.send_message(event.chat_id, text, parse_mode="md")
                except Exception:
                    pass

            # Run in background task so Telegram remains responsive
            asyncio.create_task(
                self.uploader.upload_course_range(
                    start_index=start_val,
                    end_index=end_val,
                    status_callback=status_callback,
                )
            )

        @client.on(events.NewMessage(pattern=r"(?i)^/upload\s+(\d+)"))
        async def handle_single_upload(event):
            match = re.match(r"(?i)^/upload\s+(\d+)", event.raw_text.strip())
            if not match:
                return
            course_id = int(match.group(1))

            await event.reply(f"⏳ شروع دانلود و آپلود دوره `{course_id}` به `{self.target_chat}`...")

            async def status_callback(text: str):
                try:
                    await client.send_message(event.chat_id, text, parse_mode="md")
                except Exception:
                    pass

            asyncio.create_task(
                self.uploader.upload_course(
                    course_id=course_id,
                    status_callback=status_callback,
                )
            )

        @client.on(events.NewMessage(pattern=r"(?i)^/(start|help)"))
        async def handle_help(event):
            help_text = (
                "🎓 **ربات آپلود خودکار مکتب‌خونه**\n\n"
                "📌 **دستورات قابل استفاده:**\n"
                "🔹 `/maktab <start> <end>` : آپلود ترتیبی دوره‌ها از شماره/آیدی ابتدا تا انتها\n"
                "🔹 `/upload <course_id>` : آپلود یک دوره مشخص با آیدی\n\n"
                f"📁 کانال / مقصد فعلی: `{self.target_chat}`\n"
                f"💾 سقف حافظه هاست: `{self.max_storage_mb} MB`"
            )
            await event.reply(help_text, parse_mode="md")

        await client.run_until_disconnected()
