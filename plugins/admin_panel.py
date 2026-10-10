"""
ADMIN PANEL  ->  /admin   (bot PM, ADMINS only)

Page 1 : global switches saved in the DB (survive restarts)
           - Forward      : users can forward / save files the bot sends (overrides every group's old setting)
           - PM Search    : search in bot PM on/off
           - Movie update : new-file posts in the update channel on/off
Page 2 : bulk group settings -> set one setting ON / OFF for ALL groups at once
Page 3 : fix old data
           - replace old channel names (AJK_BOY_OFFICAL, Tokyo_Updates ...) inside stored files
             (file_name / caption / title) -> dry-run first, then apply
           - clean old group settings (old caption / verification / shortener keys, old names in templates)
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pymongo import UpdateOne

from info import ADMINS, NEW_BRAND, OLD_BRAND_NAMES
from database.users_chats_db import db
from database.ia_filterdb import MEDIA_DBS
from utils import temp, brand_clean, OLD_BRAND_MONGO_REGEX
from languages import LANGS

logger = logging.getLogger(__name__)

GROUP_TOGGLES = [
    ("imdb", "IMDb poster"),
    ("spell_check", "Spell check"),
    ("auto_delete", "Auto delete"),
    ("welcome", "Welcome msg"),
    ("auto_ffilter", "Auto filter"),
    ("button", "Results as buttons"),
]

# keys that belonged to removed features (file_secure is replaced by the global Forward switch)
OBSOLETE_GROUP_KEYS = [
    "file_secure", "caption",
    "shortner", "api", "shortner_two", "api_two", "shortner_three", "api_three",
    "is_verify", "verify_time", "third_verify_time",
    "tutorial", "tutorial_2", "tutorial_3",
]

_cleanup_running = False


def _onoff(v):
    return "✅ ON" if v else "❌ OFF"


async def _main_page(client):
    bot_id = client.me.id
    pm = await db.pm_search_status(bot_id)
    mu = await db.movie_update_status(bot_id)
    text = (
        "<b>🛠 ADMIN PANEL</b>\n\n"
        "<b>🔁 Forwarding:</b> free users blocked, verified/premium allowed\n"
        "<b>   (change in ⚙️ Settings)</b>\n\n"
        f"🔎 <b>PM search</b> : {_onoff(pm)}\n"
        f"🎬 <b>Movie update posts</b> : {_onoff(mu)}\n\n"
        "<i>Tap a button to toggle. Saved in the database.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adx#stats"),
         InlineKeyboardButton("🔍 Top missing", callback_data="adx#missing")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="adc#home"),
         InlineKeyboardButton("💎 Premium", callback_data="adp#home")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adx#bcast"),
         InlineKeyboardButton("📡 Force-Sub", callback_data="adx#fsub")],
        [InlineKeyboardButton("🔤 Search aliases", callback_data="adx#alias")],
        [InlineKeyboardButton(f"🔎 PM Search: {_onoff(pm)}", callback_data="adm#t#pm")],
        [InlineKeyboardButton(f"🎬 Movie Update: {_onoff(mu)}", callback_data="adm#t#mu")],
        [InlineKeyboardButton("⚙️ Group settings (ALL groups)", callback_data="adm#g")],
        [InlineKeyboardButton("🌐 Languages (users)", callback_data="adm#lang")],
        [InlineKeyboardButton("🧹 Fix old data", callback_data="adm#fix")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="adm#home"),
         InlineKeyboardButton("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


async def _groups_page():
    lines = ["<b>⚙️ GROUP SETTINGS — ALL GROUPS</b>\n"]
    rows, total = [], 0
    for key, label in GROUP_TOGGLES:
        on, off, total = await db.count_group_setting(key)
        lines.append(f"• <b>{label}</b> : ✅ {on}  |  ❌ {off}")
        rows.append([
            InlineKeyboardButton(f"✅ {label} ON", callback_data=f"adm#gs#{key}#1"),
            InlineKeyboardButton("❌ OFF", callback_data=f"adm#gs#{key}#0"),
        ])
    lines.append(f"\n<i>Total groups: {total}. A button changes that setting in every group.</i>")
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="adm#home")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _lang_page():
    counts = await db.count_users_by_lang()
    total = sum(counts.values()) or 1
    lines = ["<b>🌐 USERS BY LANGUAGE</b>\n"]
    ranked = sorted(LANGS, key=lambda x: -counts.get(x[0], 0))
    for code, name, flag in ranked:
        n = counts.get(code, 0)
        lines.append(f"{flag} <b>{name}</b> : <code>{n}</code>  ({n * 100 // total}%)")
    none = counts.get(None, 0)
    lines.append(f"\n⏳ <b>Not chosen yet</b> : <code>{none}</code>")
    lines.append(f"👥 <b>Total users</b> : <code>{sum(counts.values())}</code>")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="adm#lang")],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm#home")],
    ])
    return "\n".join(lines), kb


def _fix_page():
    old = ", ".join(OLD_BRAND_NAMES) or "-"
    text = (
        "<b>🧹 FIX OLD DATA</b>\n\n"
        f"Old names : <code>{old}</code>\n"
        f"New name  : <code>{NEW_BRAND}</code>\n\n"
        "1️⃣ <b>Check</b> — counts stored files that still have an old name (changes nothing).\n"
        "2️⃣ <b>Replace</b> — rewrites file name / caption / title in the database.\n"
        "3️⃣ <b>Clean group data</b> — removes old caption / verification / shortener keys from every group "
        "and renames old names inside saved IMDb templates.\n\n"
        "<i>Files are always sent with the Script.py caption and the new name even without step 2.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Check old names in files (dry run)", callback_data="adm#nm#dry")],
        [InlineKeyboardButton("🧽 Replace old names in files", callback_data="adm#nm#ask")],
        [InlineKeyboardButton("🧹 Clean old group data", callback_data="adm#gd#go")],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm#home")],
    ])
    return text, kb


async def _safe_edit(message, text, kb=None):
    try:
        await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass


def _files_query():
    rx = {"$regex": OLD_BRAND_MONGO_REGEX, "$options": "i"}
    return {"$or": [{"file_name": rx}, {"caption": rx}, {"title": rx}]}


async def _count_old_names():
    out = []
    if not OLD_BRAND_MONGO_REGEX:
        return out
    q = _files_query()
    for i, media_cls in enumerate(MEDIA_DBS, 1):
        col = media_cls.collection
        out.append((f"DB {i}", await col.count_documents(q), await col.estimated_document_count()))
    return out


async def _replace_old_names(message):
    global _cleanup_running
    _cleanup_running = True
    fixed = 0
    try:
        q = _files_query()
        for i, media_cls in enumerate(MEDIA_DBS, 1):
            col = media_cls.collection
            ops, seen = [], 0
            async for doc in col.find(q, {"file_name": 1, "caption": 1, "title": 1}):
                seen += 1
                upd = {}
                for f in ("file_name", "caption", "title"):
                    old = doc.get(f)
                    if isinstance(old, str):
                        new = brand_clean(old)
                        if new != old:
                            upd[f] = new
                if upd:
                    ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": upd}))
                if len(ops) >= 500:
                    await col.bulk_write(ops, ordered=False)
                    fixed += len(ops)
                    ops = []
                    await _safe_edit(message, f"<b>🧽 Replacing old names…</b>\n\nDB {i}: checked {seen}\nFixed so far: <code>{fixed}</code>")
                    await asyncio.sleep(0.2)
            if ops:
                await col.bulk_write(ops, ordered=False)
                fixed += len(ops)
        text = f"<b>✅ Done.</b>\n\nFiles fixed: <code>{fixed}</code>\n\n<i>Old names → {NEW_BRAND}</i>"
    except Exception as e:
        logger.exception(e)
        text = f"<b>❌ Stopped with an error</b>\n\n<code>{e}</code>\n\nFixed before error: <code>{fixed}</code>"
    finally:
        _cleanup_running = False
    _, kb = _fix_page()
    await _safe_edit(message, text, kb)


async def _clean_group_data():
    unset = {f"settings.{k}": "" for k in OBSOLETE_GROUP_KEYS}
    r = await db.grp.update_many({"settings": {"$exists": True}}, {"$unset": unset})
    cleaned_tpl = 0
    if OLD_BRAND_MONGO_REGEX:
        rx = {"$regex": OLD_BRAND_MONGO_REGEX, "$options": "i"}
        async for g in db.grp.find({"settings.template": rx}, {"settings.template": 1}):
            old = g.get("settings", {}).get("template")
            new = brand_clean(old)
            if new != old:
                await db.grp.update_one({"_id": g["_id"]}, {"$set": {"settings.template": new}})
                cleaned_tpl += 1
    temp.SETTINGS.clear()  # every group reloads its settings from the DB
    return r.modified_count, cleaned_tpl


@Client.on_message(filters.command("admin") & filters.private & filters.user(ADMINS))
async def admin_panel_cmd(client, message):
    text, kb = await _main_page(client)
    await message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^adm#"))
async def admin_panel_cb(client, query):
    if not query.from_user or query.from_user.id not in ADMINS:
        return await query.answer("Only bot admins can use this panel.", show_alert=True)

    parts = query.data.split("#")
    action = parts[1] if len(parts) > 1 else "home"
    bot_id = client.me.id

    if action == "close":
        await query.answer()
        return await query.message.delete()

    if action == "open":   # from the /start menu (that message is a photo, so open the panel as a new message)
        await query.answer()
        text, kb = await _main_page(client)
        return await query.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)

    if action == "lang":
        await query.answer()
        text, kb = await _lang_page()
        return await _safe_edit(query.message, text, kb)

    if action == "home":
        await query.answer()
        text, kb = await _main_page(client)
        return await _safe_edit(query.message, text, kb)

    if action == "t":
        key = parts[2]
        if key == "pm":
            new = not await db.pm_search_status(bot_id)
            await db.update_pm_search_status(bot_id, new)
            toast = f"PM search {_onoff(new)}"
        elif key == "mu":
            new = not await db.movie_update_status(bot_id)
            await db.update_movie_update_status(bot_id, new)
            toast = f"Movie update {_onoff(new)}"
        else:
            return await query.answer("Unknown option", show_alert=True)
        await query.answer(toast)
        text, kb = await _main_page(client)
        return await _safe_edit(query.message, text, kb)

    if action == "g":
        await query.answer()
        text, kb = await _groups_page()
        return await _safe_edit(query.message, text, kb)

    if action == "gs":
        key, value = parts[2], parts[3] == "1"
        if key not in dict(GROUP_TOGGLES):
            return await query.answer("Unknown setting", show_alert=True)
        changed = await db.set_setting_all_groups(key, value)
        temp.SETTINGS.clear()
        await query.answer(f"{dict(GROUP_TOGGLES)[key]} {_onoff(value)} for {changed} groups", show_alert=True)
        text, kb = await _groups_page()
        return await _safe_edit(query.message, text, kb)

    if action == "fix":
        await query.answer()
        text, kb = _fix_page()
        return await _safe_edit(query.message, text, kb)

    if action == "nm":
        sub = parts[2]
        if sub in ("dry", "ask"):
            await query.answer("Checking…")
            rows = await _count_old_names()
            if not rows:
                return await query.answer("No old names configured (OLD_BRAND_NAMES is empty).", show_alert=True)
            body = "\n".join(f"• {label}: <code>{bad}</code> of {total} files" for label, bad, total in rows)
            total_bad = sum(b for _, b, _ in rows)
            if sub == "dry":
                text = f"<b>🔍 DRY RUN (nothing changed)</b>\n\n{body}\n\nTotal with old name: <code>{total_bad}</code>"
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧽 Replace now", callback_data="adm#nm#ask")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="adm#fix")],
                ])
            else:
                text = (f"<b>⚠️ Replace old names?</b>\n\n{body}\n\nTotal: <code>{total_bad}</code> files will be "
                        f"rewritten to <code>{NEW_BRAND}</code>.")
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, replace", callback_data="adm#nm#go")],
                    [InlineKeyboardButton("⬅️ Cancel", callback_data="adm#fix")],
                ])
            return await _safe_edit(query.message, text, kb)

        if sub == "go":
            if _cleanup_running:
                return await query.answer("A cleanup is already running.", show_alert=True)
            await query.answer("Started…")
            await _safe_edit(query.message, "<b>🧽 Replacing old names…</b>\n\nStarting…")
            asyncio.create_task(_replace_old_names(query.message))
            return

    if action == "gd":
        await query.answer("Cleaning…")
        n_groups, n_tpl = await _clean_group_data()
        text = (f"<b>✅ Group data cleaned</b>\n\nGroups updated: <code>{n_groups}</code>\n"
                f"Templates renamed: <code>{n_tpl}</code>\n\n<i>Settings cache cleared — no restart needed.</i>")
        _, kb = _fix_page()
        return await _safe_edit(query.message, text, kb)

    await query.answer()
