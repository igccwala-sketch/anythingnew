import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import aiosqlite

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS access_keys (
                    key TEXT PRIMARY KEY,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    max_uses INTEGER DEFAULT 100,
                    current_uses INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS created_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT,
                    password TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by_key TEXT,
                    proxy_used TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_string TEXT UNIQUE,
                    type TEXT,
                    status TEXT DEFAULT 'unchecked',
                    last_checked TIMESTAMP,
                    response_time FLOAT,
                    fail_count INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    async def create_key(self, key: str, owner_id: int, hours: int, max_uses: int) -> bool:
        expires = datetime.now() + timedelta(hours=hours)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO access_keys (key, created_by, expires_at, max_uses) VALUES (?, ?, ?, ?)",
                (key, owner_id, expires, max_uses)
            )
            await db.commit()
        return True

    async def validate_key(self, key: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM access_keys WHERE key = ? AND is_active = 1",
                (key,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            key_data = dict(row)

            if datetime.now() > datetime.fromisoformat(key_data['expires_at']):
                return {"valid": False, "reason": "expired"}

            if key_data['current_uses'] >= key_data['max_uses']:
                return {"valid": False, "reason": "usage_limit"}

            return {"valid": True, "data": key_data}

    async def increment_key_usage(self, key: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE access_keys SET current_uses = current_uses + 1 WHERE key = ?",
                (key,)
            )
            await db.commit()

    async def add_proxy(self, proxy: str, proxy_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO proxies (proxy_string, type) VALUES (?, ?)",
                (proxy, proxy_type)
            )
            await db.commit()

    async def get_live_proxies(self, limit: int = 10) -> List[str]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT proxy_string FROM proxies WHERE status = 'live' AND fail_count < 3 ORDER BY response_time ASC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def mark_proxy_failed(self, proxy: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE proxies SET fail_count = fail_count + 1 WHERE proxy_string = ?",
                (proxy,)
            )
            await db.commit()

    async def update_proxy_status(self, proxy: str, status: str, response_time: float = None):
        async with aiosqlite.connect(self.db_path) as db:
            if status == 'live':
                await db.execute(
                    "UPDATE proxies SET status = ?, last_checked = ?, response_time = ?, fail_count = 0 WHERE proxy_string = ?",
                    (status, datetime.now(), response_time, proxy)
                )
            else:
                await db.execute(
                    "UPDATE proxies SET status = ?, last_checked = ? WHERE proxy_string = ?",
                    (status, datetime.now(), proxy)
                )
            await db.commit()

    async def log_account(self, email: str, password: str, fname: str, lname: str, key: str, proxy: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO created_accounts 
                   (email, password, first_name, last_name, created_by_key, proxy_used) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (email, password, fname, lname, key, proxy)
            )
            await db.commit()
