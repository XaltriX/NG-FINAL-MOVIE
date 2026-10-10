"""Request button (user) + result buttons (admin) for requests_flow."""
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import requests_flow as rf
from info import ADMINS
from languages import btn, get_lang, tr

HTML = enums.ParseMode.HTML


def _plain(t):
    import re
    return re.sub(r"<[^>]+>", "", t)[:190]


@Client.on_callback_query(filters.regex(r"^rq#"))
async def rq_cb(client, query):
    p = query.data.split("#")
    act, arg = p[1], p[2]
    user = query.from_user

    if act == "r":                                   # user pressed "Request this movie"
        lang = await get_lang(user.id)
        title = rf.title_of(arg)
        if not title:
            return await query.answer(_plain(tr("req_expired", lang)), show_alert=True)
        src = "PM" if query.message.chat.type == enums.ChatType.PRIVATE else f"Group: {query.message.chat.title}"
        res = await rf.submit(client, user, title, src)
        if res == "already":
            return await query.answer(_plain(tr("req_already", lang)), show_alert=True)
        if res == "invalid":
            return await query.answer(_plain(tr("req_expired", lang)), show_alert=True)
        await query.answer()
        try:
            await query.message.edit_text(tr("req_sent", lang), parse_mode=HTML,
                                          reply_markup=M([[B(btn("btn_close", lang), callback_data="close_data")]]))
        except Exception:
            pass
        return

    if act in rf.STATUS:                             # admin result button
        if user.id not in ADMINS:
            return await query.answer("Only admins", show_alert=True)
        doc = await rf.close(client, arg, act, user.mention)
        if not doc:
            return await query.answer("Already handled ✔️", show_alert=True)
        await query.answer(f"Done • {len(doc['users'])} user(s) notified")
