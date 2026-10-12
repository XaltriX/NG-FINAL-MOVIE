"""Force-subscribe card: one card in the user's language, live-updated as channels get joined,
file is sent automatically when everything is joined."""
import asyncio
import logging

from pyrogram import enums
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import botcfg
from database.users_chats_db import db
from info import AUTH_CHANNELS, AUTH_REQ_CHANNELS
from languages import tr, btn as lbtn, get_lang
from utils import get_settings

log = logging.getLogger(__name__)
_LINKS = {}          # (channel, is_req) -> invite link
_TITLES = {}
_CTX = {}            # user_id -> (token, group_id, on_done, card)
_WATCH = {}          # user_id -> running poll task
POLL_SEC, POLL_MAX = 3, 100   # ~5 minutes of live updates


async def channels_for(group_id):
    try:
        s = await get_settings(group_id) if group_id else None
    except Exception:
        s = None
    normal = list(dict.fromkeys((s.get("fsub", []) if s else []) + AUTH_CHANNELS + botcfg.get("fsub_channels")))
    normal = [int(c) for c in normal]
    return [(c, False) for c in normal] + [(int(c), True) for c in AUTH_REQ_CHANNELS if int(c) not in normal]


async def _joined(bot, uid, ch, is_req):
    if is_req and await db.has_joined_channel(uid, ch):
        return True
    try:
        m = await bot.get_chat_member(ch, uid)
        if m.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
            return False
        if is_req:
            await db.add_join_req(uid, ch)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:           # bot not admin / channel gone -> don't block the user
        log.warning("fsub check %s: %s", ch, e)
        return True


async def _meta(bot, ch, is_req):
    key = (ch, is_req)
    if key not in _LINKS:
        try:
            chat = await bot.get_chat(ch)
            _TITLES[ch] = chat.title
            _LINKS[key] = (await bot.create_chat_invite_link(ch, creates_join_request=is_req)).invite_link
        except Exception as e:
            log.warning("fsub invite %s: %s", ch, e)
            return _TITLES.get(ch, str(ch)), None
    return _TITLES.get(ch, str(ch)), _LINKS[key]


async def states(bot, uid, chans):
    res = await asyncio.gather(*[_joined(bot, uid, c, r) for c, r in chans])
    return list(res)


async def render(bot, uid, name, lang, chans, st, token):
    rows, kb = [], []
    for (ch, is_req), ok in zip(chans, st):
        title, link = await _meta(bot, ch, is_req)
        if ok:
            rows.append(f"<b>✅ {title}</b>")
            kb.append([InlineKeyboardButton("✅ " + title[:28], callback_data="fsx#ok")])
        else:
            rows.append(f"<b>⬜ {title}</b>" + (f" <i>({tr('fs_req', lang)})</i>" if is_req else ""))
            if link:
                kb.append([InlineKeyboardButton("📢 " + title[:28], url=link)])
    if not all(st):
        kb.append([InlineKeyboardButton(lbtn("fs_btn_check", lang), callback_data=f"fsx#chk#{token}")])
    text = tr("fs_card", lang, name=name, rows="\n".join(rows), n=sum(st), total=len(st))
    return text, InlineKeyboardMarkup(kb)


async def prompt(bot, message, token, group_id, on_done):
    """Returns True if user is blocked (card shown). on_done() is awaited when all channels are joined."""
    uid = message.from_user.id
    chans = await channels_for(group_id)
    if not chans:
        return False
    st = await states(bot, uid, chans)
    if all(st):
        return False
    lang = await get_lang(uid)
    text, kb = await render(bot, uid, message.from_user.first_name, lang, chans, st, token)
    card = await message.reply_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    _CTX[uid] = (token, group_id, on_done, card)
    old = _WATCH.pop(uid, None)
    if old:
        old.cancel()
    _WATCH[uid] = asyncio.create_task(_watch(bot, card, message.from_user, lang, chans, st, token, on_done))
    return True


async def _watch(bot, card, user, lang, chans, st, token, on_done):
    try:
        last = sum(st)
        for _ in range(POLL_MAX):
            await asyncio.sleep(POLL_SEC)
            st = await states(bot, user.id, chans)
            if all(st):
                try:
                    await card.edit_text(tr("fs_done", lang), parse_mode=enums.ParseMode.HTML)
                except Exception:
                    pass
                await on_done()
                try:
                    await card.delete()
                except Exception:
                    pass
                return
            if sum(st) != last:
                last = sum(st)
                text, kb = await render(bot, user.id, user.first_name, lang, chans, st, token)
                try:
                    await card.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
        try:
            await card.edit_reply_markup(card.reply_markup)
        except Exception:
            pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.warning("fsub watch: %s", e)
    finally:
        if _WATCH.get(user.id) is asyncio.current_task():
            _WATCH.pop(user.id, None)


async def manual_check(bot, query):
    """Callback fsx#chk -> 'I have joined' button."""
    uid = query.from_user.id
    ctx = _CTX.get(uid)
    lang = await get_lang(uid)
    if not ctx:
        return await query.answer(tr("fs_notyet", lang).replace("⚠️ ", ""), show_alert=True)
    token, group_id, on_done, card = ctx
    chans = await channels_for(group_id)
    st = await states(bot, uid, chans)
    if not all(st):
        text, kb = await render(bot, uid, query.from_user.first_name, lang, chans, st, token)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass
        return await query.answer(tr("fs_notyet", lang), show_alert=True)
    _CTX.pop(uid, None)
    w = _WATCH.pop(uid, None)
    if w:
        w.cancel()
    await query.answer()
    try:
        await query.message.edit_text(tr("fs_done", lang), parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
    await on_done()
    try:
        await query.message.delete()
    except Exception:
        pass
