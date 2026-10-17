"""One-time, restart-safe copy of the bot's own data (NOT movie files) from DATABASE_URI -> BOT_DB_URI.
Runs automatically at startup when BOT_DB_URI differs from DATABASE_URI. Safe to run again: it skips documents that
already exist and only marks itself done when everything was copied."""
import logging

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import BulkWriteError

from info import BOT_DB_URI, COLLECTION_NAME, DATABASE_NAME, DATABASE_URI

log = logging.getLogger(__name__)
DBS = (DATABASE_NAME, "admin_database", "broadcast_db")
SKIP = {COLLECTION_NAME, "_migration"}
CHUNK = 500


def needed():
    return BOT_DB_URI != DATABASE_URI


async def _copy_collection(src, dst):
    n = 0
    batch = []
    async for d in src.find({}):
        batch.append(d)
        if len(batch) >= CHUNK:
            n += await _flush(dst, batch)
            batch = []
    if batch:
        n += await _flush(dst, batch)
    return n


async def _flush(dst, batch):
    try:
        r = await dst.insert_many(batch, ordered=False)
        return len(r.inserted_ids)
    except BulkWriteError as e:                     # duplicates from an earlier partial run are fine
        return e.details.get("nInserted", 0)


async def run():
    if not needed():
        return
    src = AsyncIOMotorClient(DATABASE_URI)
    dst = AsyncIOMotorClient(BOT_DB_URI)
    flag = dst[DATABASE_NAME]["_migration"]
    if await flag.find_one({"_id": "v1"}):
        return
    log.warning("[MIGRATE] copying bot data to the dedicated database ...")
    total = 0
    for dbname in DBS:
        for cn in await src[dbname].list_collection_names():
            if cn in SKIP or cn.startswith("system."):
                continue
            n = await _copy_collection(src[dbname][cn], dst[dbname][cn])
            total += n
            log.warning(f"[MIGRATE] {dbname}.{cn}: {n} docs")
    await flag.insert_one({"_id": "v1", "docs": total})
    log.warning(f"[MIGRATE] done, {total} documents copied.")


async def cleanup_old():
    """Drop the OLD copies of the bot data on DATABASE_URI (frees space). Only after a finished migration."""
    dst = AsyncIOMotorClient(BOT_DB_URI)
    if not await dst[DATABASE_NAME]["_migration"].find_one({"_id": "v1"}):
        return None
    src = AsyncIOMotorClient(DATABASE_URI)
    dropped = []
    for dbname in DBS:
        for cn in await src[dbname].list_collection_names():
            if cn in SKIP or cn.startswith("system."):
                continue
            await src[dbname][cn].drop()
            dropped.append(f"{dbname}.{cn}")
    return dropped
