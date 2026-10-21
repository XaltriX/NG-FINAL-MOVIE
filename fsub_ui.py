"""Force-subscribe, one channel per file.
  free + verified users: file #1 -> channel 1, file #2 -> channel 2, ... (already joined channels are never asked again)
  premium users: never asked.
One simple card in the user's language: one button, 3 tiny steps, live progress, file arrives automatically."""
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
_LINKS, _TITLES = {}, {}
_CTX = {}      # user_id -> dict(token, chans, total, step_no, file, on_done)
_WATCH = {}
POLL_SEC, POLL_MAX, HINT_AT = 3, 100, 20      # ~5 min of live updates, hint after ~1 min


async def all_channels(group_id):
    try:
        s = await get_settings(group_id) if group_id else None
    except Exception:
        s = None
    normal = [int(c) for c in dict.fromkeys((s.get("fsub", []) if s else []) + AUTH_CHANNELS + botcfg.get("fsub_channels"))]
    return [(c, False) for c in normal] + [(int(c), True) for c in AUTH_REQ_CHANNELS if int(c) not in normal]


async def _step(uid):
    d = await db.users.find_one({"id": int(uid)}, {"fsub_step": 1})
    return int((d or {}).get("fsub_step", 0))


async def bump(uid):
    """Call after a file was delivered to a non-premium user: next file needs one more channel."""
    try:
        await db.users.update_one({"id": int(uid)}, {"$inc": {"fsub_step": 1}}, upsert=True)
    except Exception as e:
        log.warning("fsub bump: %s", e)


async def required(uid, group_id):
    chans = await all_channels(group_id)
    k = min((await _step(uid)) + 1, len(chans))
    return chans[:k], len(chans)


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
    except Exception as e:           # bot not admin / channel gone -> never block the user because of our problem
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
    return list(await asyncio.gather(*[_joined(bot, uid, c, r) for c, r in chans]))


async def render(bot, ctx, st, lang, hint=False):
    chans, total = ctx["chans"], ctx["total"]
    idx = next((i for i, ok in enumerate(st) if not ok), 0)       # first channel still missing
    ch, is_req = chans[idx]
    title, link = await _meta(bot, ch, is_req)
    n = ctx["step_no"]
    dots = " ".join("●" if i < n - 1 or (i == n - 1 and all(st)) else "○" for i in range(total))
    text = (f"<b>{tr('fs_head', lang)}</b>\n\n"
            f"{tr('fs_intro', lang, file=ctx['file'] or tr('fs_files', lang))}\n\n"
            f"<b>📢 {title}</b>\n"
            f"<b>{dots}     {tr('fs_step_label', lang, n=n, total=total)}</b>\n\n"
            f"{tr('fs_steps_req' if is_req else 'fs_steps_pub', lang)}")
    if hint:
        text += f"\n\n<b>{tr('fs_hint', lang)}</b>"
    kb = []
    if link:
        kb.append([InlineKeyboardButton(lbtn("fs_btn_request" if is_req else "fs_btn_join", lang), url=link)])
    kb.append([InlineKeyboardButton(lbtn("fs_btn_how", lang), callback_data="fsx#how")])
    kb.append([InlineKeyboardButton(lbtn("fs_btn_check", lang), callback_data="fsx#chk")])
    return text, InlineKeyboardMarkup(kb)


async def prompt(bot, message, token, group_id, on_done, file_name=None):
    """True = user is blocked (card shown). on_done() runs when the required channel(s) are joined."""
    uid = message.from_user.id
    chans, total = await required(uid, group_id)
    if not chans:
        return False
    st = await states(bot, uid, chans)
    if all(st):
        return False
    lang = await get_lang(uid)
    ctx = {"token": token, "chans": chans, "total": total, "step_no": len(chans), "file": file_name, "on_done": on_done,
           "missing": [c for (c, _), ok in zip(chans, st) if not ok]}
    try:
        import stats
        for _c in ctx["missing"]:
            await stats.bump_fsub(_c, "shown")
    except Exception:
        pass
    text, kb = await render(bot, ctx, st, lang)
    card = await message.reply_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    ctx["card"] = card
    _CTX[uid] = ctx
    old = _WATCH.pop(uid, None)
    if old:
        old.cancel()
    _WATCH[uid] = asyncio.create_task(_watch(bot, message.from_user, lang, ctx))
    return True


async def _finish(bot, uid, lang, ctx, card):
    if _CTX.pop(uid, None) is None:
        return                                   # already finished (watcher and button raced)
    try:
        import stats
        for _c in ctx.get("missing", []):
            await stats.bump_fsub(_c, "joined")
    except Exception:
        pass
    try:
        await card.edit_text(f"<b>{tr('fs_done', lang)}</b>", parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass
    await ctx["on_done"]()
    try:
        await card.delete()
    except Exception:
        pass


async def _watch(bot, user, lang, ctx):
    card, hinted = ctx["card"], False
    try:
        for i in range(POLL_MAX):
            await asyncio.sleep(POLL_SEC)
            st = await states(bot, user.id, ctx["chans"])
            if all(st):
                return await _finish(bot, user.id, lang, ctx, card)
            if i >= HINT_AT and not hinted:
                hinted = True
                text, kb = await render(bot, ctx, st, lang, hint=True)
                try:
                    await card.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.warning("fsub watch: %s", e)
    finally:
        if _WATCH.get(user.id) is asyncio.current_task():
            _WATCH.pop(user.id, None)


async def how(query):
    lang = await get_lang(query.from_user.id)
    await query.answer(tr("fs_how", lang)[:195], show_alert=True)


async def manual_check(bot, query):
    """'I have joined' button."""
    uid = query.from_user.id
    lang = await get_lang(uid)
    ctx = _CTX.get(uid)
    if not ctx:
        return await query.answer(tr("fs_notyet", lang), show_alert=True)
    st = await states(bot, uid, ctx["chans"])
    if not all(st):
        text, kb = await render(bot, ctx, st, lang, hint=True)
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass
        return await query.answer(tr("fs_notyet", lang), show_alert=True)
    w = _WATCH.pop(uid, None)
    if w:
        w.cancel()
    await query.answer()
    await _finish(bot, uid, lang, ctx, query.message)
