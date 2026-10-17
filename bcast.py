"""Restart-proof broadcast engine (users + groups).
 - progress (cursor + counters) is saved in MongoDB after every batch -> if Heroku restarts the dyno the job resumes by itself
 - nothing is kept in memory per user (no Message objects, no per-user tasks)  -> no memory growth / R14 restarts
 - FloodWait is waited out and retried, edit errors never stop the job
"""
import asyncio
import datetime
import logging
import time

import pymongo
from pyrogram.errors import (ChannelPrivate, ChatWriteForbidden, FloodWait, InputUserDeactivated, PeerIdInvalid,
                             UserDeactivated, UserDeactivatedBan, UserIsBlocked)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.users_chats_db import db
from info import BOT_DB_URI as DATABASE_URI
from utils import get_readable_time, temp

log = logging.getLogger(__name__)
jobs = db.db["broadcast_jobs"]
_sync = pymongo.MongoClient(DATABASE_URI)["broadcast_db"]
user_rec = _sync["user_broadcasts"]
group_rec = _sync["group_broadcasts"]
BATCH = 25
_running = set()
_last_edit = {}


async def send_message(bot, chat_id, msg, pin=False, _try=0):
    try:
        args = {"chat_id": chat_id, "reply_markup": msg.reply_markup}
        if msg.media and getattr(msg, "has_media_spoiler", False):
            args["has_spoiler"] = True
        sent = await msg.copy(**args)
        if pin:
            try:
                kw = {} if str(chat_id).startswith("-") else {"both_sides": True}
                await bot.pin_chat_message(chat_id, sent.id, disable_notification=True, **kw)
            except Exception:
                pass
        return sent, "Success"
    except FloodWait as e:
        if _try < 5:
            await asyncio.sleep(e.value + 1)
            return await send_message(bot, chat_id, msg, pin, _try + 1)
        return None, "Error"
    except UserIsBlocked:
        return None, "Blocked"
    except (InputUserDeactivated, UserDeactivated, UserDeactivatedBan, PeerIdInvalid, ChatWriteForbidden, ChannelPrivate):
        return None, "Deleted"
    except Exception as e:
        err = str(e).lower()
        if "blocked" in err:
            return None, "Blocked"
        if "not found" in err or "deactivated" in err or "deleted" in err:
            return None, "Deleted"
        return None, "Error"


async def safe_edit(bot, chat_id, msg_id, text, markup=None, force=False):
    now = time.time()
    if not force and now - _last_edit.get(msg_id, 0) < 4:
        return
    _last_edit[msg_id] = now
    try:
        await bot.edit_message_text(chat_id, msg_id, text, reply_markup=markup)
    except FloodWait:
        pass
    except Exception:
        pass


async def active_job():
    return await jobs.find_one({"status": "running"})


async def start_job(bot, kind, status_msg, src_msg, pin, auto_del):
    coll = db.col if kind == "users" else db.grp
    total = await coll.count_documents({})
    doc = {"kind": kind, "src_chat": src_msg.chat.id, "src_id": src_msg.id, "pin": pin, "auto_del": int(auto_del),
           "last": None, "total": total, "done": 0, "success": 0, "blocked": 0, "deleted": 0, "failed": 0,
           "status": "running", "status_chat": status_msg.chat.id, "status_id": status_msg.id,
           "elapsed": 0.0, "created": datetime.datetime.utcnow()}
    r = await jobs.insert_one(doc)
    asyncio.create_task(run_job(bot, r.inserted_id))


def _text(j, title):
    return (f"{title}\n\n👥 Total: <code>{j['total']}</code>\n✅ Done: <code>{j['done']}</code>\n"
            f"📬 Success: <code>{j['success']}</code>\n⛔ Blocked: <code>{j['blocked']}</code>\n"
            f"🗑️ Deleted: <code>{j['deleted']}</code>\n❌ Failed: <code>{j['failed']}</code>\n"
            f"⏱️ Time: {get_readable_time(int(j['elapsed']))}")


async def run_job(bot, job_id):
    if job_id in _running:
        return
    _running.add(job_id)
    try:
        j = await jobs.find_one({"_id": job_id})
        if not j or j["status"] != "running":
            return
        kind = j["kind"]
        coll = db.col if kind == "users" else db.grp
        rec = user_rec if kind == "users" else group_rec
        key = "user_id" if kind == "users" else "group_id"
        cancel_attr = "B_USERS_CANCEL" if kind == "users" else "B_GROUPS_CANCEL"
        try:
            b_msg = await bot.get_messages(j["src_chat"], j["src_id"])
        except Exception as e:
            await jobs.update_one({"_id": job_id}, {"$set": {"status": "failed"}})
            return await safe_edit(bot, j["status_chat"], j["status_id"], f"❌ Broadcast source message missing: {e}", force=True)
        title = "📣 <b>Broadcast Progress:</b>" if kind == "users" else "📣 <b>Group broadcast progress:</b>"
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ CANCEL", callback_data=f"broadcast_cancel#{kind}")]])
        t0 = time.time()
        base_elapsed = j.get("elapsed", 0.0)
        cancelled = False
        while True:
            if getattr(temp, cancel_attr, False):
                setattr(temp, cancel_attr, False)
                cancelled = True
                break
            q = {"_id": {"$gt": j["last"]}} if j.get("last") else {}
            batch = await coll.find(q, {"id": 1}).sort("_id", 1).limit(BATCH).to_list(BATCH)
            if not batch:
                break
            tb = time.time()
            res = await asyncio.gather(*[send_message(bot, int(u["id"]), b_msg, j["pin"]) for u in batch],
                                       return_exceptions=True)
            inc = {"done": len(batch), "success": 0, "blocked": 0, "deleted": 0, "failed": 0}
            recs, dels = [], []
            now = datetime.datetime.utcnow()
            for u, r in zip(batch, res):
                if isinstance(r, Exception):
                    inc["failed"] += 1
                    continue
                sent, status = r
                if status == "Success":
                    inc["success"] += 1
                    recs.append({key: int(u["id"]), "message_id": sent.id, "timestamp": datetime.datetime.now()})
                    if j["auto_del"] > 0:
                        dels.append({"chat_id": int(u["id"]), "ids": [sent.id], "notice_id": None, "lang": "en",
                                     "at": now + datetime.timedelta(seconds=j["auto_del"])})
                elif status == "Blocked":
                    inc["blocked"] += 1
                elif status == "Deleted":
                    inc["deleted"] += 1
                else:
                    inc["failed"] += 1
            if recs:
                await asyncio.to_thread(rec.insert_many, recs)
            if dels:
                await db.pdel.insert_many(dels)
            j["last"] = batch[-1]["_id"]
            el = base_elapsed + (time.time() - t0)
            await jobs.update_one({"_id": job_id}, {"$set": {"last": j["last"], "elapsed": el},
                                                    "$inc": inc})
            for k, v in inc.items():
                j[k] += v
            j["elapsed"] = el
            await safe_edit(bot, j["status_chat"], j["status_id"], _text(j, title), cancel_btn)
            await asyncio.sleep(max(0.05, 1.0 - (time.time() - tb)))
        await jobs.update_one({"_id": job_id}, {"$set": {"status": "cancelled" if cancelled else "done"}})
        title = "❌ <b>Broadcast Cancelled.</b>" if cancelled else "✅ <b>Broadcast Completed.</b>"
        j["elapsed"] = base_elapsed + (time.time() - t0)
        await safe_edit(bot, j["status_chat"], j["status_id"], _text(j, title), force=True)
    except Exception as e:
        log.exception(f"broadcast job crashed: {e}")      # status stays 'running' -> resumes on next start
    finally:
        _running.discard(job_id)


async def resume_broadcasts(bot):
    """Call once at startup: continue any broadcast that was interrupted by a restart."""
    try:
        async for j in jobs.find({"status": "running"}):
            await safe_edit(bot, j["status_chat"], j["status_id"], "♻️ <b>Bot restarted - resuming broadcast...</b>", force=True)
            asyncio.create_task(run_job(bot, j["_id"]))
    except Exception as e:
        log.warning(f"resume broadcasts: {e}")
