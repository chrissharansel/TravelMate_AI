"""MongoDB (PyMongo native async client) + index creation."""
from pymongo import AsyncMongoClient, ASCENDING, DESCENDING
from .config import get_settings

_client: AsyncMongoClient | None = None
COLLECTIONS = ["users", "user_preferences", "conversations", "trips", "itineraries", "agent_execution_logs", "memory"]


def get_client() -> AsyncMongoClient:
    global _client
    s = get_settings()
    if not s.mongodb_uri:
        raise RuntimeError("MONGODB_URI is empty. Set it in backend/.env")
    if _client is None:
        _client = AsyncMongoClient(s.mongodb_uri, serverSelectionTimeoutMS=4000)
    return _client


def get_db():
    return get_client()[get_settings().mongodb_database]


async def ping_db() -> dict:
    await get_client().admin.command("ping")
    return {"ok": True, "database": get_settings().mongodb_database}


async def ensure_indexes(db=None):
    db = db if db is not None else get_db()
    await db.users.create_index("user_id", unique=True)
    await db.user_preferences.create_index("user_id", unique=True)
    await db.conversations.create_index("conversation_id", unique=True)
    await db.conversations.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
    await db.trips.create_index("trip_id", unique=True)
    await db.trips.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await db.itineraries.create_index([("trip_id", ASCENDING), ("version", DESCENDING)], unique=True)
    await db.agent_execution_logs.create_index([("execution_id", ASCENDING), ("seq", ASCENDING)])
    await db.agent_execution_logs.create_index([("trip_id", ASCENDING), ("timestamp", ASCENDING)])
    await db.memory.create_index([("user_id", ASCENDING), ("key", ASCENDING)], unique=True)


async def close_db():
    global _client
    if _client is not None:
        await _client.close()
        _client = None
