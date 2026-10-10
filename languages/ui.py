"""Start menu + language picker (shared by commands.py, pmfilter.py and plugins/language.py)."""
import random

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import ADMINS, PICS, UPDATE_CHNL_LNK, SUPPORT_CHAT, NEW_BRAND
from utils import temp
from languages import LANGS, btn, greeting, tr


def start_markup(lang, user_id):
    rows = [
        [InlineKeyboardButton(btn("btn_add_group", lang), url=f"https://t.me/{temp.U_NAME}?startgroup=true")],
        [InlineKeyboardButton(btn("btn_help", lang), callback_data="help"),
         InlineKeyboardButton(btn("btn_about", lang), callback_data="about")],
        [InlineKeyboardButton(btn("btn_top", lang), callback_data="topsearch"),
         InlineKeyboardButton(btn("btn_premium", lang), callback_data="premium_info")],
        [InlineKeyboardButton(btn("btn_language", lang), callback_data="lang_menu"),
         InlineKeyboardButton(btn("btn_account", lang), callback_data="acc#home")],
    ]
    if user_id in ADMINS:
        rows.append([InlineKeyboardButton(btn("btn_admin", lang), callback_data="adm#open")])
    return InlineKeyboardMarkup(rows)


def start_text(lang, user):
    return tr("start_txt", lang, name=user.mention, greet=greeting(lang), updates=UPDATE_CHNL_LNK,
              support=SUPPORT_CHAT, brand=f"https://t.me/{NEW_BRAND}")


def lang_picker_markup():
    rows, row = [], []
    for code, name, flag in LANGS:
        row.append(InlineKeyboardButton(f"{flag} {name}", callback_data=f"setlang#{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def send_start(client, user, chat_id, lang):
    await client.send_photo(
        chat_id=chat_id,
        photo=random.choice(PICS),
        caption=start_text(lang, user),
        reply_markup=start_markup(lang, user.id),
        parse_mode=enums.ParseMode.HTML,
    )
