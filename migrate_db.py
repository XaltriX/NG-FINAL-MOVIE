"""One-time, restart-safe copy of the bot's own data (NOT movie files) from DATABASE_URI -> BOT_DB_URI.
Runs automatically at startup when BOT_DB_URI differs from DATABASE_URI. Safe to run again: it skips documents that
already exist and only marks itself done when everything was copied."""
import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import BulkWriteError

from info import BOT_DB_OLD_URI, BOT_DB_URI, COLLECTION_NAME, DATABASE_NAME, DATABASE_URI

log = logging.getLogger(__name__)
DBS = (DATABASE_NAME, "admin_database", "broadcast_db")
SKIP = {COLLECTION_NAME, "_migration"}
CHUNK = 1000


def needed():
    return BOT_DB_URI != BOT_DB_OLD_URI


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
    src = AsyncIOMotorClient(BOT_DB_OLD_URI)
    dst = AsyncIOMotorClient(BOT_DB_URI)
    flag = dst[DATABASE_NAME]["_migration"]
    if await flag.find_one({"_id": "v1"}):
        return
    log.warning("[MIGRATE] copying bot data to the dedicated database ...")
    jobs = []
    for dbname in DBS:
        for cn in await src[dbname].list_collection_names():
            if cn in SKIP or cn.startswith("system."):
                continue
            jobs.append((dbname, cn))
    sem = asyncio.Semaphore(4)

    async def one(dbname, cn):
        async with sem:
            n = await _copy_collection(src[dbname][cn], dst[dbname][cn])
            log.warning(f"[MIGRATE] {dbname}.{cn}: {n} docs")
            return n

    total = sum(await asyncio.gather(*[one(d, c) for d, c in jobs]))
    await flag.insert_one({"_id": "v1", "docs": total})
    log.warning(f"[MIGRATE] done, {total} documents copied.")


# collections this bot uses: only these are ever dropped from a cluster that may be SHARED with another bot
KNOWN = {"users", "uersz", "groups", "requests", "bot_settings", "misc", "filename", "movie_updates", "connections",
         "verify_tokens", "pending_deletes", "weekly_searches", "configuration", "bot_stats", "broadcast_jobs",
         "dl_history", "gclean", "missing_requests", "movie_requests", "pay_requests", "refer_stats", "referrals",
         "search_aliases", "shares", "verified_log", "premium", "refers", "referusers", "user", "user_broadcasts",
         "group_broadcasts", "welcome", "antispam", "antispam_cfg"}


async def cleanup_old(dry=False):
    """Drop the OLD copies of the bot data (frees space). Only after a finished migration; dry=True only lists them.
    Files cluster: every bot-data collection. A cluster shared with another bot (BOT_DB_OLD_URI): only KNOWN names that
    are fully present in the new DB."""
    dst = AsyncIOMotorClient(BOT_DB_URI)
    if not await dst[DATABASE_NAME]["_migration"].find_one({"_id": "v1"}):
        return None
    jobs = []
    if BOT_DB_URI != DATABASE_URI:
        jobs.append((DATABASE_URI, False))
    if BOT_DB_OLD_URI not in (DATABASE_URI, BOT_DB_URI):
        jobs.append((BOT_DB_OLD_URI, True))
    dropped = []
    for uri, shared in jobs:
        src = AsyncIOMotorClient(uri)
        for dbname in DBS:
            for cn in await src[dbname].list_collection_names():
                if cn in SKIP or cn.startswith("system.") or (shared and cn not in KNOWN):
                    continue
                if shared and await dst[dbname][cn].count_documents({}) < await src[dbname][cn].count_documents({}):
                    continue
                if not dry:
                    await src[dbname][cn].drop()
                dropped.append(f"{dbname}.{cn}" + (" (old shared DB)" if shared else ""))
    return dropped
