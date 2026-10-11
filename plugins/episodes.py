import re
import math
import time
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton
from languages import ubold
from info import MAX_B_TN
from utils import get_settings, get_cap, clean_search_text
from database.ia_filterdb import get_search_results
from plugins.pmfilter import BUTTONS, FRESH, MEDIA_TYPE, temp, InlineKeyboardMarkup

EP_COUNT = 24


def _owner_ok(query):
    try:
        return int(query.from_user.id) in [query.message.reply_to_message.from_user.id, 0]
    except Exception:
        return True


@Client.on_callback_query(filters.regex(r"^episodes#"))
async def episodes_menu(client, query):
    if not _owner_ok(query):
        return await query.answer("⚠️ Not your request", show_alert=True)
    key = query.data.split("#", 1)[1]
    if not (BUTTONS.get(key) or FRESH.get(key)):
        return await query.answer("⌛ Search expired, please search again.", show_alert=True)
    req = query.from_user.id
    rows = [[InlineKeyboardButton("⇊ " + ubold("Select Episode") + " ⇊", callback_data="ident")]]
    for i in range(1, EP_COUNT + 1, 4):
        rows.append([InlineKeyboardButton(ubold(f"E{n:02d}"), callback_data=f"fe#{n}#{key}")
                     for n in range(i, min(i + 4, EP_COUNT + 1))])
    rows.append([InlineKeyboardButton("↩️ " + ubold("Back to files"), callback_data=f"next_{req}_{key}_0")])
    await query.edit_message_reply_markup(InlineKeyboardMarkup(rows))
    await query.answer()


@Client.on_callback_query(filters.regex(r"^fe#"))
async def episode_pick(client, query):
    t0 = time.perf_counter()
    if not _owner_ok(query):
        return await query.answer("⚠️ Not your request", show_alert=True)
    _, num, key = query.data.split("#")
    base = BUTTONS.get(key) or FRESH.get(key)
    if not base:
        return await query.answer("⌛ Search expired, please search again.", show_alert=True)
    base = re.sub(r"\b(?:e|ep|episode)[\s-]*\d+\b", "", base.replace("_", " "), flags=re.I).strip()
    search = f"{base} e{int(num):02d}"
    chat_id = query.message.chat.id
    req = query.from_user.id
    files, n_offset, total = await get_search_results(chat_id, search, offset=0, filter=True,
                                                      media_type=MEDIA_TYPE.get(key))
    if not files:
        return await query.answer(f"🚫 E{int(num):02d} not found", show_alert=True)
    BUTTONS[key] = search
    temp.GETALL[key] = files
    settings = await get_settings(chat_id)
    per = 10 if settings.get("max_btn") else int(MAX_B_TN)
    btn = [[InlineKeyboardButton("q", callback_data=f"qualities#{key}")]]  # marker; restyle builds the header
    if n_offset != "":
        btn.append([InlineKeyboardButton(f"1/{math.ceil(int(total) / per)}", callback_data="pages"),
                    InlineKeyboardButton("ɴᴇxᴛ ⋟", callback_data=f"next_{req}_{key}_{n_offset}")])
    cap = await get_cap(settings, f"{time.perf_counter() - t0:.2f}", files, query, total,
                        clean_search_text(search), offset=1)
    try:
        await query.message.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn),
                                      disable_web_page_preview=True)
    except MessageNotModified:
        pass
    await query.answer()
