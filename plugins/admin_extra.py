"""ADMIN: Stats / Top missing requests / Force-Sub channels / Search aliases / Broadcast help   prefix: adx#"""
import sys
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
import payments
import stats
from database.ia_filterdb import MEDIA_DBS
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNELS
from languages import LANGS

PENDING = {}   # admin_id -> {"kind", "t", "msg", ...}
BACK = [B("⬅️ Back", callback_data="adm#home"), B("❌ Close", callback_data="adm#close")]


async def _edit(msg, text, kb):
    try:
        await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass


async def _stats():
    users = await db.total_users_count()
    groups = await db.total_chat_count()
    files = 0
    for m in MEDIA_DBS:
        try:
            files += await m.collection.estimated_document_count()
        except Exception:
            pass
    prem = await db.all_premium_users()
    total_dl, today_dl = await stats.downloads()
    pend = await payments.pending_count()
    counts = await db.count_users_by_lang()
    langs = " • ".join(f"{f} {counts.get(c, 0)}" for c, _, f in LANGS if counts.get(c, 0))
    text = (
        "<b>📊 BOT STATS</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>👥 Users:</b> {users}\n<b>👨‍👩‍👧 Groups:</b> {groups}\n<b>🎬 Files:</b> {files}\n"
        f"<b>💎 Premium now:</b> {prem}\n<b>⏳ Pending payments:</b> {pend}\n\n"
        f"<b>📥 Downloads:</b> {total_dl}\n<b>📅 Today:</b> {today_dl}\n\n"
        f"<b>🌐 Languages:</b> {langs or '—'}"
    )
    return text, M([[B("🔄 Refresh", callback_data="adx#stats"), B("🌐 Languages", callback_data="adm#lang")], BACK])


async def _missing():
    rows = await stats.top_missing()
    lines = "\n".join(f"{i}. <code>{d['q']}</code> — <b>{d['count']}</b>" for i, d in enumerate(rows, 1)) or "Nothing missing 🎉"
    text = f"<b>🔍 TOP MISSING REQUESTS</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n{lines}\n\n<b>Add these movies to get more users 👆</b>"
    return text, M([[B("🗑 Clear list", callback_data="adx#mclear"), B("🔄 Refresh", callback_data="adx#missing")], BACK])


def _fsub():
    ch = botcfg.get("fsub_channels")
    env = ", ".join(f"<code>{c}</code>" for c in AUTH_CHANNELS) or "—"
    lines = "\n".join(f"{i}. <code>{c}</code>" for i, c in enumerate(ch, 1)) or "—"
    text = (f"<b>📡 FORCE-SUB CHANNELS</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>Added here:</b>\n{lines}\n\n"
            f"<b>From settings (fixed):</b> {env}\n\n<b>⚠️ Bot must be admin in the channel.</b>")
    rows = [[B(f"🗑 {c}", callback_data=f"adx#fdel#{c}")] for c in ch]
    rows += [[B("➕ Add channel", callback_data="adx#fadd")], BACK]
    return text, M(rows)


async def _aliases():
    rows = await stats.list_aliases()
    lines = "\n".join(f"• <code>{d['a']}</code> ➜ {d['real']}" for d in rows) or "—"
    text = (f"<b>🔤 SEARCH ALIASES</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n{lines}\n\n"
            "<b>User types the left name, bot searches the right name.</b>\n<b>Example:</b> <code>kgf 2 ➜ KGF Chapter 2</code>")
    kb = [[B(f"🗑 {d['a']}"[:40], callback_data=f"adx#adel#{i}")] for i, d in enumerate(rows)]
    kb += [[B("➕ Add alias", callback_data="adx#aadd")], BACK]
    return text, M(kb), rows


BCAST = ("<b>📢 BROADCAST</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n"
         "<b>1️⃣ Send or forward the message to this chat</b>\n"
         "<b>2️⃣ Reply to it with:</b>\n"
         "<code>/broadcast</code> — all users\n<code>/grp_broadcast</code> — all groups\n"
         "<code>/del_broadcast</code> — delete the last broadcast")


@Client.on_callback_query(filters.regex(r"^adx#"))
async def adx_cb(client, query):
    if not query.from_user or query.from_user.id not in ADMINS:
        return await query.answer("Only bot admins can use this.", show_alert=True)
    uid, msg = query.from_user.id, query.message
    p = query.data.split("#")
    act, a = p[1], (p[2] if len(p) > 2 else None)
    PENDING.pop(uid, None)
    for mod in ("plugins.admin_config", "plugins.admin_premium"):
        if mod in sys.modules:
            sys.modules[mod].PENDING.pop(uid, None)

    if act == "stats":
        await query.answer()
        return await _edit(msg, *await _stats())
    if act == "missing":
        await query.answer()
        return await _edit(msg, *await _missing())
    if act == "mclear":
        await stats.missing_col.delete_many({})
        await query.answer("Cleared 🗑")
        return await _edit(msg, *await _missing())
    if act == "bcast":
        await query.answer()
        return await _edit(msg, BCAST, M([BACK]))
    if act == "fsub":
        await query.answer()
        return await _edit(msg, *_fsub())
    if act == "fdel":
        await botcfg.set("fsub_channels", [c for c in botcfg.get("fsub_channels") if str(c) != a])
        await query.answer("Removed")
        return await _edit(msg, *_fsub())
    if act == "fadd":
        PENDING[uid] = {"kind": "fadd", "t": time.time(), "msg": msg}
        await query.answer()
        return await _edit(msg, "<b>➕ Send the channel ID</b>\n<b>Example:</b> <code>-1001234567890</code>",
                           M([[B("🚫 Cancel", callback_data="adx#fsub")]]))
    if act == "alias":
        await query.answer()
        t, kb, _ = await _aliases()
        return await _edit(msg, t, kb)
    if act == "adel":
        rows = await stats.list_aliases()
        if a.isdigit() and int(a) < len(rows):
            await stats.del_alias(rows[int(a)]["a"])
        await query.answer("Deleted 🗑")
        t, kb, _ = await _aliases()
        return await _edit(msg, t, kb)
    if act == "aadd":
        PENDING[uid] = {"kind": "aadd", "t": time.time(), "msg": msg}
        await query.answer()
        return await _edit(msg, "<b>➕ Send like this:</b>\n<code>kgf 2 = KGF Chapter 2</code>",
                           M([[B("🚫 Cancel", callback_data="adx#alias")]]))


@Client.on_message(filters.private & filters.user(ADMINS) & filters.text & ~filters.regex(r"^/"), group=-4)
async def adx_text(client, message):
    st = PENDING.get(message.from_user.id)
    if not st:
        return
    if time.time() - st["t"] > 300:        # stale -> let the text go to normal search
        PENDING.pop(message.from_user.id, None)
        return
    txt = message.text.strip()
    if st["kind"] == "fadd":
        try:
            cid = int(txt)
            chat = await client.get_chat(cid)
        except Exception:
            await message.reply_text("<b>❌ Invalid ID, or bot is not in that channel.</b>")
            raise StopPropagation
        ch = botcfg.get("fsub_channels")
        if cid not in ch:
            ch.append(cid)
            await botcfg.set("fsub_channels", ch)
        PENDING.pop(message.from_user.id, None)
        t, kb = _fsub()
        await message.reply_text(f"<b>✅ Added: {chat.title}</b>\n\n{t}", reply_markup=kb)
    elif st["kind"] == "aadd":
        if "=" not in txt or not txt.split("=", 1)[0].strip() or not txt.split("=", 1)[1].strip():
            await message.reply_text("<b>❌ Use:</b> <code>short name = Real Name</code>")
            raise StopPropagation
        a_, r_ = txt.split("=", 1)
        await stats.add_alias(a_, r_)
        PENDING.pop(message.from_user.id, None)
        t, kb, _ = await _aliases()
        await message.reply_text("<b>✅ Saved</b>\n\n" + t, reply_markup=kb)
    raise StopPropagation
