import asyncio
from pathlib import Path
from typing import Optional, Union
from telethon import TelegramClient
from telethon.sessions import StringSession

from maktab_downloader.config import settings
from maktab_downloader.utils.console import print_error, print_info, print_success, print_warning


class TelegramManager:
    """Manages Telethon Telegram client lifecycle, authentication, and session handling."""

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        bot_token: Optional[str] = None,
        session_string: Optional[str] = None,
        session_name: Optional[str] = None,
    ):
        self.api_id = api_id or settings.TELEGRAM_API_ID
        self.api_hash = api_hash or settings.TELEGRAM_API_HASH
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.session_string = session_string or settings.TELEGRAM_SESSION_STRING
        self.session_name = session_name or settings.TELEGRAM_SESSION_NAME
        self.client: Optional[TelegramClient] = None

    def _get_session(self) -> Union[StringSession, str]:
        """Return StringSession if provided, otherwise session name file."""
        if self.session_string:
            return StringSession(self.session_string)
        return self.session_name

    async def get_client(self) -> TelegramClient:
        """Create and start the Telethon TelegramClient session."""
        if self.client and self.client.is_connected():
            return self.client

        if not self.api_id or not self.api_hash:
            raise ValueError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are required. "
                "Please obtain them from https://my.telegram.org and set them in .env or via CLI."
            )

        session = self._get_session()
        self.client = TelegramClient(session, self.api_id, self.api_hash)

        if self.bot_token:
            print_info("Starting Telegram client in Bot mode...")
            await self.client.start(bot_token=self.bot_token)
        else:
            print_info("Starting Telegram client in User/Self-Bot mode...")
            await self.client.start()

        me = await self.client.get_me()
        user_or_bot = "Bot" if getattr(me, "bot", False) else "User"
        first_name = getattr(me, "first_name", "") or "Telegram Account"
        username = f"@{me.username}" if getattr(me, "username", None) else ""
        print_success(f"Telegram connected as {user_or_bot}: {first_name} {username} [ID: {me.id}]")

        return self.client

    async def close(self):
        """Disconnect Telegram client."""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            print_info("Telegram client disconnected.")
