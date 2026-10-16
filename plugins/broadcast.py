# ---------------- Optimized Persistent Broadcast Bot ----------------
# Developed by 【𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫_𝐁𝐨𝐲™(𝓐𝓷𝓴𝓲𝓽_𝓜𝐞𝐞𝐧𝐚😝)】
# Don't remove credit

import time
import asyncio
import bcast
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserDeactivated, UserDeactivatedBan, PeerIdInvalid, ChatWriteForbidden, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from database.users_chats_db import db
from info import ADMINS
from utils import temp, get_readable_time
import pymongo
from datetime import datetime
from info import DATABASE_URI

lock = asyncio.Lock()

# ---------------- MongoDB setup for persistent broadcast ----------------
_mongo_client = pymongo.MongoClient(DATABASE_URI)
broadcast_db = _mongo_client["broadcast_db"]
user_broadcast_collection = broadcast_db["user_broadcasts"]
group_broadcast_collection = broadcast_db["group_broadcasts"]

# ----------------- Runtime temp lists -----------------
temp.LAST_USER_BROADCAST = []
temp.LAST_GROUP_BROADCAST = []

# ----------------- Auto-delete -----------------
async def auto_delete(msg, delay, chat_id=None, message_id=None):
    """
    Broadcast message auto-delete.
    msg object ke alawa chat_id + message_id bhi pass karo —
    agar msg object stale ho jaye tab bhi delete kaam kare.
    """
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        if chat_id and message_id:
            try:
                await msg._client.delete_messages(chat_id, message_id)
            except Exception:
                pass
    for lst in (temp.LAST_USER_BROADCAST, temp.LAST_GROUP_BROADCAST):
        try:
            lst.remove(msg)
        except ValueError:
            pass

# ----------------- Track messages in runtime -----------------
async def track_message(sent_msg, target="user"):
    return   # no longer kept in memory (was a leak); ids are stored in MongoDB by bcast.py
    if sent_msg:
        if target == "user":
            temp.LAST_USER_BROADCAST.append(sent_msg)
        elif target == "group":
            temp.LAST_GROUP_BROADCAST.append(sent_msg)

# ----------------- Cancel Callback -----------------
@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, target = query.data.split("#", 1)
    if target == 'users':
        temp.B_USERS_CANCEL = True
        await query.message.edit("🛑 Trying to cancel users broadcasting...")
    elif target == 'groups':
        temp.B_GROUPS_CANCEL = True
        await query.message.edit("🛑 Trying to cancel groups broadcasting...")

# ----------------- Send message helper (Optimized for Formatting, Pin & Spoiler) -----------------
async def send_message(bot, chat_id, reply_msg, pin=False, _try=0):
    try:
        # Basic copy arguments
        copy_args = {
            "chat_id": chat_id,
            "reply_markup": reply_msg.reply_markup
        }
        
        # Check agar message me media hai aur uspar spoiler laga hai
        if reply_msg.media and getattr(reply_msg, "has_media_spoiler", False):
            copy_args["has_spoiler"] = True

        # Copy command with dynamic arguments
        sent = await reply_msg.copy(**copy_args)

        if pin:
            try:
                # Group aur User PM ke liye alag pin logic
                if str(chat_id).startswith("-"):
                    await bot.pin_chat_message(
                        chat_id=chat_id,
                        message_id=sent.id,
                        disable_notification=True
                    )
                else:
                    # User PM me both_sides=True required hota hai
                    await bot.pin_chat_message(
                        chat_id=chat_id,
                        message_id=sent.id,
                        disable_notification=True,
                        both_sides=True
                    )
            except Exception:
                pass
        return sent, "Success"

    except FloodWait as e:
        if _try < 5:
            await asyncio.sleep(e.value + 1)
            return await send_message(bot, chat_id, reply_msg, pin, _try + 1)
        return None, "Error"
    except (UserIsBlocked,):
        return None, "Blocked"
    except (InputUserDeactivated, UserDeactivated, UserDeactivatedBan, PeerIdInvalid, ChatWriteForbidden, ChannelPrivate):
        return None, "Deleted"
    except Exception as e:
        err = str(e).lower()
        if "blocked" in err:
            return None, "Blocked"
        if "chat not found" in err or "deactivated" in err or "deleted" in err:
            return None, "Deleted"
        return None, "Error"


_last_edit = {}


async def safe_edit(msg, text, markup=None, force=False):
    """Progress edits: at most one per 4 s, and never let an edit error stop the broadcast."""
    now = time.time()
    if not force and now - _last_edit.get(msg.id, 0) < 4:
        return
    _last_edit[msg.id] = now
    try:
        await msg.edit(text, reply_markup=markup)
    except FloodWait:
        pass
    except Exception:
        pass


# ----------------- User Broadcast -----------------
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_users(bot, message):
    if await bcast.active_job():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")

    ask = await message.reply(
        "<b>Do you want to pin this message in users?</b>",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    try:
        user_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
    except asyncio.TimeoutError:
        await ask.delete()
        return await message.reply("❌ Timed out. Broadcast cancelled.")
    await ask.delete()
    if user_response.text not in ("Yes", "No"):
        return await message.reply("❌ Invalid input. Broadcast cancelled.")
    is_pin = user_response.text == "Yes"

    ask_time = await message.reply("<b>Enter auto-delete time in seconds (0 to disable auto-delete):</b>")
    try:
        time_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
        auto_delete_time = int(time_response.text)
    except:
        await ask_time.delete()
        return await message.reply("❌ Invalid or no response. Broadcast cancelled.")
    await ask_time.delete()

    status_msg = await message.reply_text("📤 <b>Broadcasting your message...</b>")
    await bcast.start_job(bot, "users", status_msg, message.reply_to_message, is_pin, auto_delete_time)


# ----------------- Delete all user broadcasts (Optimized & Non-Freezing) -----------------
@Client.on_message(filters.command("del_broadcast") & filters.user(ADMINS))
async def del_all_user_broadcast(bot, message):
    records = list(user_broadcast_collection.find({}))
    total_records = len(records)
    
    if not records:
        return await message.reply("⚠️ No user broadcast messages to delete.")

    status_msg = await message.reply(f"🗑️ <b>Starting deletion of {total_records} messages...</b>")
    
    deleted_count = 0
    failed_count = 0
    batch_size = 50

    for i in range(0, total_records, batch_size):
        batch = records[i:i + batch_size]
        for record in batch:
            try:
                await bot.delete_messages(record["user_id"], record["message_id"])
                deleted_count += 1
            except Exception:
                failed_count += 1
        
        # Prevent Bot Freeze
        await asyncio.sleep(0.1)
        
        # Update progress UI
        done = i + len(batch)
        if done % 100 == 0 or done == total_records:
            await status_msg.edit(
                f"🗑️ <b>User Deletion Progress:</b>\n\n"
                f"🔢 Total: <code>{total_records}</code>\n"
                f"✅ Deleted: <code>{deleted_count}</code>\n"
                f"⛔ Failed/Blocked: <code>{failed_count}</code>"
            )

    # Free up DB storage
    user_broadcast_collection.delete_many({})
    temp.LAST_USER_BROADCAST.clear()
    
    await status_msg.edit(
        f"✅ <b>All user broadcasts deleted successfully!</b>\n\n"
        f"🗑️ Deleted from Chat: <code>{deleted_count}</code>\n"
        f"⛔ Blocked/Failed (Skipped): <code>{failed_count}</code>\n"
        f"💾 DB Storage: <b>Cleared 100%</b>"
    )

# ----------------- Group Broadcast -----------------
@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_group(bot, message):
    if await bcast.active_job():
        return await message.reply("⚠️ Another broadcast is in progress. Please wait...")
    ask = await message.reply(
        "<b>Do you want to pin this message in groups?</b>",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    try:
        user_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
    except asyncio.TimeoutError:
        await ask.delete()
        return await message.reply("❌ Timed out. Broadcast cancelled.")
    await ask.delete()
    is_pin = user_response.text == "Yes"

    ask_time = await message.reply("<b>Enter auto-delete time in seconds (0 to disable auto-delete):</b>")
    try:
        time_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
        auto_delete_time = int(time_response.text)
    except:
        await ask_time.delete()
        return await message.reply("❌ Invalid or no response. Broadcast cancelled.")
    await ask_time.delete()

    status_msg = await message.reply_text("📤 <b>Broadcasting your message to groups...</b>")
    await bcast.start_job(bot, "groups", status_msg, message.reply_to_message, is_pin, auto_delete_time)


# ----------------- Delete all group broadcasts (Optimized & Non-Freezing) -----------------
@Client.on_message(filters.command("del_grp_broadcast") & filters.user(ADMINS))
async def del_all_group_broadcast(bot, message):
    records = list(group_broadcast_collection.find({}))
    total_records = len(records)
    
    if not records:
        return await message.reply("⚠️ No group broadcast messages to delete.")

    status_msg = await message.reply(f"🗑️ <b>Starting deletion of {total_records} group messages...</b>")
    
    deleted_count = 0
    failed_count = 0
    batch_size = 50

    for i in range(0, total_records, batch_size):
        batch = records[i:i + batch_size]
        for record in batch:
            try:
                await bot.delete_messages(record["group_id"], record["message_id"])
                deleted_count += 1
            except Exception:
                failed_count += 1
        
        # Prevent Bot Freeze
        await asyncio.sleep(0.1)
        
        # Update progress UI
        done = i + len(batch)
        if done % 100 == 0 or done == total_records:
            await status_msg.edit(
                f"🗑️ <b>Group Deletion Progress:</b>\n\n"
                f"🔢 Total: <code>{total_records}</code>\n"
                f"✅ Deleted: <code>{deleted_count}</code>\n"
                f"⛔ Failed: <code>{failed_count}</code>"
            )

    # Free up DB storage
    group_broadcast_collection.delete_many({})
    temp.LAST_GROUP_BROADCAST.clear()
    
    await status_msg.edit(
        f"✅ <b>All group broadcasts deleted successfully!</b>\n\n"
        f"🗑️ Deleted from Groups: <code>{deleted_count}</code>\n"
        f"⛔ Failed/Missing (Skipped): <code>{failed_count}</code>\n"
        f"💾 DB Storage: <b>Cleared 100%</b>"
    )


@Client.on_message(filters.command("bcancel") & filters.user(ADMINS))
async def broadcast_force_cancel(bot, message):
    """Emergency: mark any stuck broadcast as cancelled so a new one can be started."""
    r = await bcast.jobs.update_many({"status": "running"}, {"$set": {"status": "cancelled"}})
    temp.B_USERS_CANCEL = temp.B_GROUPS_CANCEL = True
    await message.reply(f"🛑 Cancelled {r.modified_count} running broadcast(s).")
