"""Counters used by the admin panel: downloads, missing (not found) requests, search aliases."""
import datetime
import re
import time

import pytz

from database.users_chats_db import db

stat_col = db.db["bot_stats"]
missing_col = db.db["missing_requests"]
alias_col = db.db["search_aliases"]
IST = pytz.timezone("Asia/Kolkata")


def _today():
    return datetime.datetime.now(IST).strftime("%Y-%m-%d")


async def bump_downloads(n=1):
    try:
        await stat_col.update_one({"id": "global"}, {"$inc": {"downloads": n, f"day.{_today()}": n}}, upsert=True)
    except Exception:
        pass


async def downloads():
    d = await stat_col.find_one({"id": "global"}) or {}
    return d.get("downloads", 0), (d.get("day") or {}).get(_today(), 0)


def clean_query(q):
    q = re.sub(r"[^\w\s]", " ", (q or "").lower())
    return re.sub(r"\s+", " ", q).strip()[:80]


async def record_missing(query, user_id=None):
    q = clean_query(query)
    if len(q) < 2:
        return
    try:
        await missing_col.update_one(
            {"q": q},
            {"$inc": {"count": 1}, "$set": {"last": datetime.datetime.utcnow(), "user": user_id}}, upsert=True)
    except Exception:
        pass


async def top_missing(limit=15):
    return [d async for d in missing_col.find({}).sort("count", -1).limit(limit)]


# ---- aliases (Hinglish / short names) : cached in memory, edited from admin panel ----
_aliases = {}
_loaded_at = 0


async def _load():
    global _aliases, _loaded_at
    _aliases = {d["a"]: d["real"] async for d in alias_col.find({})}
    _loaded_at = time.time()


async def apply_alias(search):
    """'kgf 2' -> real stored title, if the admin added an alias for it."""
    if time.time() - _loaded_at > 120:
        try:
            await _load()
        except Exception:
            return search
    return _aliases.get(clean_query(search), search)


async def list_aliases():
    return [d async for d in alias_col.find({}).sort("a", 1).limit(40)]


async def add_alias(alias, real):
    await alias_col.update_one({"a": clean_query(alias)}, {"$set": {"real": real.strip()}}, upsert=True)
    await _load()


async def del_alias(alias):
    await alias_col.delete_one({"a": alias})
    await _load()
