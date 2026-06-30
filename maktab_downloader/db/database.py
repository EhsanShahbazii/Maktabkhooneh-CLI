import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from maktab_downloader.config import settings
from maktab_downloader.db.schema import SCHEMA_SQL
from maktab_downloader.utils.helpers import ensure_dir


class Database:
    """Manages SQLite database connection lifecycle with WAL mode and 60-second busy timeout."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or settings.DB_PATH)
        ensure_dir(self.db_path.parent)

    async def init_db(self):
        """Initialize database schema, tables, pragmas and indexes."""
        async with aiosqlite.connect(self.db_path, timeout=60.0) as db:
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA busy_timeout = 60000;")
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provide a managed connection context with WAL mode and generous busy timeout."""
        async with aiosqlite.connect(self.db_path, timeout=60.0) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode = WAL;")
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute("PRAGMA busy_timeout = 60000;")
            yield conn


db_instance = Database()
