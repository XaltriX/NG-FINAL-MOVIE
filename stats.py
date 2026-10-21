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


# ---- verification counters (day = 12 AM -> 12 AM IST) ----
vlog_col = db.db["verified_log"]


async def bump_verified(user_id, sid=None):
    day = _today()
    try:
        await stat_col.update_one({"id": "global"}, {"$inc": {
            "verified": 1, f"vday.{day}": 1, f"vs.{sid}.total": 1, f"vs.{sid}.{day}": 1}}, upsert=True)
        await vlog_col.update_one({"day": day, "uid": int(user_id)}, {"$inc": {"n": 1}}, upsert=True)
    except Exception:
        pass


async def verified_stats():
    d = await stat_col.find_one({"id": "global"}) or {}
    day = _today()
    uniq = await vlog_col.count_documents({"day": day})
    per = {k: (v.get("total", 0), v.get(day, 0)) for k, v in (d.get("vs") or {}).items()}
    return d.get("verified", 0), (d.get("vday") or {}).get(day, 0), uniq, per


# ---- force-sub funnel: how many users saw the card for a channel and how many joined ----
async def bump_fsub(ch, kind):
    """kind: 'shown' | 'joined'"""
    day = _today()
    try:
        await stat_col.update_one({"id": "global"}, {"$inc": {f"fs.{ch}.{kind}": 1, f"fs.{ch}.{kind}_{day}": 1}}, upsert=True)
    except Exception:
        pass


async def fsub_stats():
    d = await stat_col.find_one({"id": "global"}) or {}
    day = _today()
    out = {}
    for ch, v in (d.get("fs") or {}).items():
        out[ch] = (v.get("shown", 0), v.get("joined", 0), v.get(f"shown_{day}", 0), v.get(f"joined_{day}", 0))
    return out
