"""Group cleanup: commands sent to this bot in a group (e.g. /trendlist@MyBot) are deleted after a few seconds.
Needs the bot to be admin with 'Delete messages' in that group. Settings: /admin -> Settings -> Limits."""
import asyncio
import time

from pyrogram import Client, enums, filters
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

from database.users_chats_db import db
from info import ADMINS

import botcfg
from deleter import schedule_delete
from utils import temp


@Client.on_message(filters.group & filters.text & filters.regex(r"^/\w+@\w+"), group=-3)
async def clean_commands(client, message):
    if not botcfg.get("group_cmd_delete"):
        return
    text = message.text.split(None, 1)[0].lower()
    if not text.endswith("@" + (temp.U_NAME or client.me.username).lower()):
        return                                          # command for another bot -> leave it
    try:
        me = await client.get_chat_member(message.chat.id, client.me.id)
        if me.status != enums.ChatMemberStatus.ADMINISTRATOR or not (me.privileges and me.privileges.can_delete_messages):
            return
    except Exception:
        return
    await schedule_delete(message.chat.id, [message.id], int(botcfg.get("group_cmd_delete_sec")))


# ---------------- Group clean: delete EVERY message older than N seconds (default 2 min) ----------------
# Per-group on/off:  /gclean  (group admin).  Bot must be admin with "Delete messages".
_col = db.db["gclean"]
_cache = {}                       # chat_id -> (on, fetched_at)
GROUPS = (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP)


async def is_on(chat_id):
    v = _cache.get(chat_id)
    if v and time.time() - v[1] < 60:
        return v[0]
    d = await _col.find_one({"chat_id": int(chat_id)})
    on = bool(d and d.get("on"))
    _cache[chat_id] = (on, time.time())
    return on


async def _set(chat_id, on):
    await _col.update_one({"chat_id": int(chat_id)}, {"$set": {"on": on}}, upsert=True)
    _cache[chat_id] = (on, time.time())


async def track(chat_id, msg_id):
    try:
        if await is_on(chat_id):
            await schedule_delete(chat_id, [msg_id], int(botcfg.get("gclean_sec")))
    except Exception:
        pass


@Client.on_message(filters.group, group=-10)
async def gclean_incoming(client, message):
    if message.command and message.command[0].lower().split("@")[0] == "gclean":
        return                                   # keep the settings card usable
    await track(message.chat.id, message.id)


def _wrap(name):
    orig = getattr(Client, name, None)
    if orig is None:
        return

    async def wrapper(self, *a, **k):
        r = await orig(self, *a, **k)
        try:
            for m in (r if isinstance(r, list) else [r]):
                if getattr(m, "chat", None) and m.chat.type in GROUPS:
                    asyncio.create_task(track(m.chat.id, m.id))
        except Exception:
            pass
        return r
    setattr(Client, name, wrapper)


for _n in ("send_message", "send_photo", "send_document", "send_video", "send_animation", "send_sticker",
           "send_audio", "send_voice", "copy_message", "send_cached_media", "send_media_group"):
    _wrap(_n)


async def _can_manage(client, chat_id, user_id):
    if user_id in ADMINS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        return False


async def _bot_can_delete(client, chat_id):
    try:
        me = await client.get_chat_member(chat_id, client.me.id)
        return me.status == enums.ChatMemberStatus.ADMINISTRATOR and bool(me.privileges and me.privileges.can_delete_messages)
    except Exception:
        return False


async def _card(client, chat_id):
    on = await is_on(chat_id)
    sec = int(botcfg.get("gclean_sec"))
    warn = "" if await _bot_can_delete(client, chat_id) else "\n\n<b>⚠️ Make me admin with “Delete messages” permission.</b>"
    text = (f"<b>🧹 GROUP CLEAN</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>Every message in this group is deleted after {sec // 60 if sec >= 60 else sec}"
            f"{' min' if sec >= 60 else ' sec'}.</b>\n<b>Status: {'🟢 ON' if on else '🔴 OFF'}</b>{warn}")
    kb = M([[B("🔴 Turn OFF" if on else "🟢 Turn ON", callback_data="gcl#toggle")]])
    return text, kb


@Client.on_message(filters.group & filters.command("gclean"), group=-11)
async def gclean_cmd(client, message):
    if not message.from_user or not await _can_manage(client, message.chat.id, message.from_user.id):
        return
    text, kb = await _card(client, message.chat.id)
    await message.reply_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()


@Client.on_callback_query(filters.regex(r"^gcl#"))
async def gclean_cb(client, query):
    chat_id = query.message.chat.id
    if not await _can_manage(client, chat_id, query.from_user.id):
        return await query.answer("Only group admins can change this.", show_alert=True)
    await _set(chat_id, not await is_on(chat_id))
    text, kb = await _card(client, chat_id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
    await query.answer("✅")
