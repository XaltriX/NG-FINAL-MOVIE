"""/language command + language picker callbacks."""
from pyrogram import Client, filters, enums

from database.users_chats_db import db
from languages import LANG_PICK_TEXT, get_lang, set_lang, tr, btn
from languages.ui import lang_picker_markup, send_start


@Client.on_message(filters.command("language") & filters.private)
async def language_cmd(client, message):
    if not message.from_user:
        return
    await message.reply_text(LANG_PICK_TEXT, reply_markup=lang_picker_markup(), parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^lang_menu$"))
async def lang_menu_cb(client, query):
    await query.answer()
    await query.message.reply_text(LANG_PICK_TEXT, reply_markup=lang_picker_markup(), parse_mode=enums.ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^setlang#"))
async def set_lang_cb(client, query):
    code = query.data.split("#", 1)[1]
    user = query.from_user
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
    if not await set_lang(user.id, code):
        return await query.answer("Unknown language", show_alert=True)
    await query.answer(tr("lang_saved", code), show_alert=False)
    try:
        await query.message.delete()
    except Exception:
        pass
    await send_start(client, user, query.message.chat.id, code)
