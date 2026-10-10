"""
Premium core: granting (stacking), payment requests, referral rewards, expiry reminders.
Plain module (not a plugin). Texts live in languages/*, screens in premium_ui.py.
"""
import asyncio
import datetime
import logging
import uuid

import botcfg
from database.users_chats_db import db
from languages import tr, btn, get_lang

logger = logging.getLogger(__name__)

req_col = db.db["pay_requests"]     # payment requests
ref_col = db.db["referrals"]        # one doc per referred user
refstat_col = db.db["refer_stats"]  # one doc per referrer: progress / rewards

_indexed = False


async def ensure_indexes():
    global _indexed
    if _indexed:
        return
    try:
        await req_col.create_index("rid", unique=True)
        await req_col.create_index([("user_id", 1), ("status", 1)])
        await req_col.create_index("shot_uid")
        await ref_col.create_index("referred_id", unique=True)
        await ref_col.create_index("referrer_id")
        await refstat_col.create_index("id", unique=True)
        _indexed = True
    except Exception as e:
        logger.warning(f"index: {e}")


def _naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


async def get_expiry(user_id):
    """Active premium expiry (naive UTC) or None."""
    doc = await db.get_user(int(user_id))
    exp = _naive_utc(doc.get("expiry_time")) if doc else None
    if exp and exp > datetime.datetime.utcnow():
        return exp
    return None


async def grant_premium(user_id, days):
    """Adds `days` on top of any running premium (plans stack). Returns the new expiry (naive UTC)."""
    now = datetime.datetime.utcnow()
    cur = await get_expiry(user_id)
    base = cur if cur and cur > now else now
    new = base + datetime.timedelta(days=int(days))
    await db.update_user({"id": int(user_id), "expiry_time": new, "exp_reminded": None})
    return new


# ---------------- payment requests ----------------
async def get_req(user_id, status):
    return await req_col.find_one({"user_id": int(user_id), "status": status}, sort=[("created", -1)])


async def begin_payment(user_id, plan):
    """User tapped 'I have paid' -> waiting for the screenshot (replaces an older 'awaiting' one)."""
    await ensure_indexes()
    await req_col.delete_many({"user_id": int(user_id), "status": "awaiting"})
    doc = {"rid": uuid.uuid4().hex[:10], "user_id": int(user_id), "plan_id": plan["id"], "days": int(plan["days"]),
           "price": plan["price"], "status": "awaiting", "created": datetime.datetime.utcnow(), "admin_msgs": []}
    await req_col.insert_one(doc)
    return doc


async def cancel_awaiting(user_id):
    await req_col.delete_many({"user_id": int(user_id), "status": "awaiting"})


async def shot_used(uid_unique):
    return bool(await req_col.find_one({"shot_uid": uid_unique, "status": {"$in": ["pending", "approved"]}}))


async def submit_shot(rid, uid_unique, file_id):
    return await req_col.find_one_and_update(
        {"rid": rid, "status": "awaiting"},
        {"$set": {"status": "pending", "shot_uid": uid_unique, "shot_file": file_id,
                  "submitted": datetime.datetime.utcnow()}},
        return_document=True)


async def decide(rid, ok, admin_id):
    """Atomically moves pending -> approved/rejected (so two admins cannot both act). Returns the doc or None."""
    return await req_col.find_one_and_update(
        {"rid": rid, "status": "pending"},
        {"$set": {"status": "approved" if ok else "rejected", "by": int(admin_id),
                  "decided": datetime.datetime.utcnow()}},
        return_document=True)


async def pending_list(limit=20):
    return [d async for d in req_col.find({"status": "pending"}).sort("created", 1).limit(limit)]


async def pending_count():
    return await req_col.count_documents({"status": "pending"})


# ---------------- referral ----------------
async def refer_register(referrer_id, referred_id):
    """Call ONLY for a brand-new user who opened the bot with a refer link."""
    if not botcfg.get("refer_on") or int(referrer_id) == int(referred_id):
        return False
    if not await db.is_user_exist(int(referrer_id)):
        return False
    await ensure_indexes()
    try:
        r = await ref_col.update_one(
            {"referred_id": int(referred_id)},
            {"$setOnInsert": {"referrer_id": int(referrer_id), "created": datetime.datetime.utcnow(),
                              "qualified": False}},
            upsert=True)
        return r.upserted_id is not None
    except Exception as e:
        logger.debug(f"refer register: {e}")
        return False


async def refer_stats(user_id):
    joined = await ref_col.count_documents({"referrer_id": int(user_id)})
    st = await refstat_col.find_one({"id": int(user_id)}) or {}
    return {"joined": joined, "qualified": st.get("qualified", 0), "progress": st.get("progress", 0),
            "rewards": st.get("rewards", 0)}


async def refer_qualify(client, user_id):
    """Called when a user receives a file. First time only -> counts for the referrer; may grant the reward."""
    if not botcfg.get("refer_on"):
        return
    doc = await ref_col.find_one_and_update(
        {"referred_id": int(user_id), "qualified": False},
        {"$set": {"qualified": True, "qualified_at": datetime.datetime.utcnow()}})
    if not doc:
        return
    rid = doc["referrer_id"]
    need = max(int(botcfg.get("refer_need")), 1)
    days = int(botcfg.get("refer_days"))
    st = await refstat_col.find_one_and_update(
        {"id": rid}, {"$inc": {"qualified": 1, "progress": 1}}, upsert=True, return_document=True)
    lang = await get_lang(rid)
    rewarded = 0
    while True:
        r = await refstat_col.find_one_and_update(
            {"id": rid, "progress": {"$gte": need}}, {"$inc": {"progress": -need, "rewards": 1}},
            return_document=True)
        if not r:
            break
        rewarded += 1
        st = r
    try:
        if rewarded:
            until = await grant_premium(rid, days * rewarded)
            from premium_ui import fmt_dt, fmt_dur
            await client.send_message(rid, tr("refer_reward", lang, days=fmt_dur(days * rewarded, lang), until=fmt_dt(until)),
                                      parse_mode=_html())
        else:
            await client.send_message(rid, tr("refer_qualified", lang, progress=st.get("progress", 0), need=need),
                                      parse_mode=_html())
    except Exception as e:
        logger.debug(f"refer notify: {e}")


def _html():
    from pyrogram import enums
    return enums.ParseMode.HTML


# ---------------- reminders / expiry ----------------
async def premium_loop(client):
    """Every 10 min: 'ends in <24h' reminder (once per expiry) and 'ended' notice."""
    from pyrogram import enums
    from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    from sender import fmt_duration
    while True:
        try:
            now = datetime.datetime.utcnow()
            soon = now + datetime.timedelta(hours=24)
            async for u in db.users.find({"expiry_time": {"$gt": now, "$lt": soon}}).limit(200):
                exp = _naive_utc(u["expiry_time"])
                if _naive_utc(u.get("exp_reminded")) == exp:
                    continue
                lang = await get_lang(u["id"])
                try:
                    await client.send_message(
                        u["id"], tr("remind_exp", lang, left=fmt_duration((exp - now).total_seconds(), lang)),
                        reply_markup=M([[B(btn("btn_renew", lang), callback_data="premium_info")]]),
                        parse_mode=enums.ParseMode.HTML)
                except Exception as e:
                    logger.debug(f"remind: {e}")
                await db.users.update_one({"id": u["id"]}, {"$set": {"exp_reminded": exp}})
                await asyncio.sleep(0.5)
            async for u in db.users.find({"expiry_time": {"$ne": None, "$lte": now}}).limit(200):
                await db.users.update_one({"id": u["id"]}, {"$set": {"expiry_time": None, "exp_reminded": None}})
                lang = await get_lang(u["id"])
                try:
                    await client.send_message(
                        u["id"], tr("expired_msg", lang),
                        reply_markup=M([[B(btn("btn_renew", lang), callback_data="premium_info")]]),
                        parse_mode=enums.ParseMode.HTML)
                except Exception as e:
                    logger.debug(f"expired notice: {e}")
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"premium loop: {e}")
        await asyncio.sleep(600)
