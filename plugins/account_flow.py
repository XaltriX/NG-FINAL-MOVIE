"""My Account / Preferences / My Downloads handlers."""
from pyrogram import Client, filters

import account as acc
from languages import get_lang


async def _show(client, message, text, kb):
    import premium_ui as ui
    await ui.replace(client, message, text, kb)


@Client.on_callback_query(filters.regex(r"^acc#"))
async def acc_cb(client, query):
    uid = query.from_user.id
    lang = await get_lang(uid)
    p = query.data.split("#")
    act = p[1]
    if act == "home":
        screen = await acc.account_screen(uid, lang)
    elif act == "pref":
        screen = await acc.pref_screen(uid, lang)
    elif act == "dl":
        screen = await acc.downloads_screen(uid, lang)
    elif act == "set":
        field, val = p[2], p[3]
        await acc.set_pref(uid, "pref_q" if field == "q" else "pref_l", None if val == "-" else val)
        screen = await acc.pref_screen(uid, lang)
    else:
        return await query.answer()
    await query.answer()
    await _show(client, query.message, *screen)


@Client.on_message(filters.command(["account", "myaccount"]) & filters.private)
async def account_cmd(client, message):
    lang = await get_lang(message.from_user.id)
    text, kb = await acc.account_screen(message.from_user.id, lang)
    await message.reply_text(text, reply_markup=kb, parse_mode=acc.HTML)
