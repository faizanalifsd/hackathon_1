"""
db.py — Neon Serverless Postgres connection for chat history.
"""
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("NEON_DATABASE_URL")

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


async def init_db():
    """Create tables if they don't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    print("Database initialized.")


async def save_chat(session_id: str, question: str, answer: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_history (session_id, question, answer) VALUES ($1, $2, $3)",
            session_id, question, answer,
        )


async def get_history(session_id: str, limit: int = 10) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT question, answer, created_at FROM chat_history "
            "WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
            session_id, limit,
        )
    return [dict(r) for r in rows]
