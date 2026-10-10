"""
Shortener verification (all settings come from /admin -> Settings -> Verification).

Flow:  limit reached -> [Verify] -> link made with shortener #N -> user opens it, finishes the page,
       comes back with  /start vf_<token>  -> unlimited files + forwarding for `verify_hours`.

Rotation: the Nth verification of the SAME DAY uses the Nth shortener (wraps around), so a user who
verifies twice in one day is sent to a different shortener.
Anti-bypass: coming back faster than `verify_min_seconds` fails; tokens are one-time and user-bound.
"""
import asyncio
import datetime
import logging
import secrets

import pytz
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
from database.users_chats_db import db
from languages import tr, btn, get_lang

logger = logging.getLogger(__name__)

TOKEN_TTL_MIN = 30
IST = pytz.timezone("Asia/Kolkata")


def enabled_shorteners():
    return [s for s in botcfg.get("shorteners") if s.get("on") and s.get("site") and s.get("api")]


def available():
    return bool(botcfg.get("verify_on")) and bool(enabled_shorteners())


async def pick_shortener(user_id):
    lst = enabled_shorteners()
    if not lst:
        return None
    return lst[(await db.verify_count_today(user_id)) % len(lst)]


async def _shorten(site, api, url):
    from shortzy import Shortzy   # imported lazily so the bot still starts if the package is missing
    sz = Shortzy(api, site)
    try:
        return await asyncio.wait_for(sz.convert(url), 20)
    except Exception:
        try:
            return await asyncio.wait_for(sz.get_quick_link(url), 20)
        except Exception as e:
            logger.error(f"shortener {site} failed: {e}")
            return None


async def start_verification(client, query):
    """Callback 'vf#go' -> shows the 'Verify now' screen."""
    user_id = query.from_user.id
    lang = await get_lang(user_id)

    st = await db.get_download_status(user_id)
    if st.get("verified"):
        u = await db.users.find_one({"id": user_id}, {"verified_until": 1})
        return await query.answer(
            _plain(tr("verify_active", lang, until=_fmt(u["verified_until"]))), show_alert=True)

    s = await pick_shortener(user_id) if botcfg.get("verify_on") else None
    if not s:
        return await query.answer(_plain(tr("verify_unavailable", lang)), show_alert=True)

    await query.answer()
    token = secrets.token_urlsafe(8)
    pending = await db.pop_pending_start(user_id)
    await db.create_verify_token(user_id, token, s["id"], pending)
    short = await _shorten(s["site"], s["api"], f"https://t.me/{client.me.username}?start=vf_{token}")
    if not short:
        return await query.message.reply_text(tr("verify_unavailable", lang), parse_mode=enums.ParseMode.HTML)

    rows = [[B(btn("btn_verify_now", lang), url=short)]]
    if s.get("tutorial"):
        rows.append([B(btn("btn_how_to", lang), url=s["tutorial"])])
    await query.message.reply_text(tr("verify_intro", lang, hours=botcfg.get("verify_hours")),
                                   reply_markup=M(rows), parse_mode=enums.ParseMode.HTML,
                                   disable_web_page_preview=True)


async def finish_verification(client, message, token):
    """/start vf_<token>"""
    user_id = message.from_user.id
    lang = await get_lang(user_id)
    doc = await db.pop_verify_token(token, user_id)
    now = datetime.datetime.utcnow()
    if not doc or (now - doc["created"]) > datetime.timedelta(minutes=TOKEN_TTL_MIN):
        return await message.reply_text(tr("verify_expired", lang), parse_mode=enums.ParseMode.HTML)
    if (now - doc["created"]).total_seconds() < int(botcfg.get("verify_min_seconds")):
        return await message.reply_text(tr("verify_fast", lang), parse_mode=enums.ParseMode.HTML)

    until = await db.complete_verification(user_id, botcfg.get("verify_hours"))
    rows = []
    if doc.get("pending"):
        rows.append([B(btn("btn_get_file", lang), url=f"https://t.me/{client.me.username}?start={doc['pending']}")])
    await message.reply_text(tr("verify_success", lang, until=_fmt(until)),
                             reply_markup=M(rows) if rows else None, parse_mode=enums.ParseMode.HTML)


def _fmt(utc_dt):
    return pytz.utc.localize(utc_dt).astimezone(IST).strftime("%d %b, %I:%M %p")


def _plain(html):
    import re
    return re.sub(r"<[^>]+>", "", html)[:190]   # alerts are plain text, max 200 chars
