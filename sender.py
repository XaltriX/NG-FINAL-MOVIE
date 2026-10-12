"""
ONE place that sends files to users (used by every /start deep-link path).

  gate()     -> daily-limit check; sends the "limit reached" screen (Verify / Premium) when blocked
  deliver()  -> sends the files, applies forward policy, schedules restart-proof auto-delete

Rules (all editable from /admin -> Settings):
  free user      : forward OFF, file deleted after  (movie length + delete_extra_min)
  verified user  : forward ON,  same delete time, unlimited files while verified
  premium user   : forward ON,  longer delete time, unlimited files
"""
import asyncio
import logging

from pyrogram import enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import access
import botcfg
import verifylib
from database.users_chats_db import db
from deleter import schedule_delete
from languages import tr, btn, ubold
import secrets
import urllib.parse
from info import UPDATE_CHNL_LNK

logger = logging.getLogger(__name__)


def fmt_duration(seconds, lang):
    seconds = max(int(seconds), 60)
    h, m = divmod(seconds // 60, 60)
    parts = []
    if h:
        parts.append(f"{h}{tr('unit_h', lang)}")
    if m or not h:
        parts.append(f"{m}{tr('unit_m', lang)}")
    return " ".join(parts)


def _upgrade_rows(lang):
    """[Verify] (only if usable) + [Premium] buttons."""
    rows = []
    if verifylib.available():
        rows.append([B(btn("btn_verify", lang, hours=botcfg.get("verify_hours")), callback_data="vf#go")])
    rows.append([B(btn("btn_premium", lang), callback_data="premium_info")])
    return rows


async def gate(client, user_id, lang, pending=None):
    """Returns (ok, policy, status). When not ok the user has already been told why."""
    st = await db.get_download_status(user_id)
    policy = access.policy_from_status(st)
    if st["is_premium"] or st["remaining"] > 0:      # is_premium is True for premium AND verified users
        return True, policy, st

    if pending:
        await db.set_pending_start(user_id, pending)  # so "Get my file" works after verification
    if verifylib.available():
        text = tr("limit_reached", lang, limit=st["daily_limit"], hours=botcfg.get("verify_hours"))
    else:
        text = tr("verify_unavailable", lang)
    for _ in range(2):
        try:
            await client.send_message(user_id, text, reply_markup=M(_upgrade_rows(lang)),
                                      parse_mode=enums.ParseMode.HTML)
            break
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.error(f"limit message failed: {e}")
            break
    return False, policy, st


_shares = db.db["shares"]


async def share_link(client, user_id, file_id):
    """Short code that remembers (file, referrer) -> https://t.me/<bot>?start=sh_<code>"""
    d = await _shares.find_one_and_update(
        {"ref": int(user_id), "file_id": file_id},
        {"$setOnInsert": {"code": secrets.token_urlsafe(6), "at": __import__("datetime").datetime.utcnow()}},
        upsert=True, return_document=True)
    return f"https://t.me/{client.me.username}?start=sh_{d['code']}"


async def file_markup(client, user_id, it, lang):
    rows = [[B(ubold(tr("btn_updates", lang).split(" ", 1)[1]).join(("📌 ", "")), url=UPDATE_CHNL_LNK)]]
    try:
        link = await share_link(client, user_id, it.get("ref") or it["file_id"])
        text = tr("share_text", lang, name=it.get("name") or "")
        rows.append([B(ubold(tr("btn_share_file", lang).split(" ", 1)[1]).join(("📤 ", "")),
                       url="https://t.me/share/url?url=" + urllib.parse.quote(link) + "&text=" + urllib.parse.quote(text))])
    except Exception as e:
        logger.debug(f"share link: {e}")
    return M(rows)


async def deliver(client, user_id, items, lang, policy):
    """
    items: [{"file_id", "caption", "cover"(optional), "legacy"(optional: caption is set after sending)}]
    Returns the list of sent messages.
    """
    from utils import build_file_caption  # local import: utils imports a lot

    sent, delays, done_items = [], [], []
    for it in items:
        msg = None
        markup = await file_markup(client, user_id, it, lang)
        for _ in range(3):
            try:
                msg = await client.send_cached_media(
                    chat_id=user_id,
                    file_id=it["file_id"],
                    caption=it.get("caption", ""),
                    protect_content=policy["protect"],
                    reply_markup=markup,
                    cover=it.get("cover"),
                )
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.exception(e)
                break
        if msg is None:
            continue

        if it.get("legacy"):   # file that is not in the DB: build the caption from the sent media
            try:
                media = getattr(msg, msg.media.value)
                await msg.edit_caption(
                    build_file_caption(media.file_name, media.file_size),
                    reply_markup=markup,
                )
            except Exception as e:
                logger.debug(f"legacy caption failed: {e}")

        sent.append(msg)
        done_items.append(it)
        delays.append(access.delete_seconds(policy, access.media_duration(msg)))
        await asyncio.sleep(0.3)

    if not sent:
        return sent

    if policy["free"]:
        await db.increase_download(user_id, len(sent))
    try:
        import account
        for _it in done_items:
            await account.record(user_id, _it.get('ref'), _it.get('name'))
    except Exception as e:
        logger.debug(f'history: {e}')
    try:
        import stats
        await stats.bump_downloads(len(sent))
    except Exception:
        pass
    try:   # refer & earn: the referred user's first received file counts for the referrer
        import payments
        await payments.refer_qualify(client, user_id)
    except Exception as e:
        logger.debug(f"refer qualify: {e}")

    # ONE short notice per delivery:  📦 1/3 • ⏳ 15 min • 🗑 Auto-delete   (free)  |  ⏳ 15 min • 🗑 Auto-delete (premium/verified)
    first = min(range(len(sent)), key=lambda i: delays[i])
    dur = fmt_duration(delays[first], lang)
    rows = []
    if policy["free"]:
        st2 = await db.get_download_status(user_id)
        total = int(st2["daily_limit"])
        used = min(total - int(st2["remaining"]), total)
        text = tr("after_free", lang, used=used, total=total, time=dur)
        if int(st2["remaining"]) <= 0:
            text += "\n\n" + tr("limit_last", lang)
            rows = _upgrade_rows(lang)
    else:
        text = tr("after_prem", lang, time=dur)
    notice = None
    try:
        notice = await client.send_message(user_id, text, reply_markup=M(rows) if rows else None,
                                           parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.debug(f"notice failed: {e}")

    for i, msg in enumerate(sent):
        await schedule_delete(user_id, [msg.id], delays[i],
                              notice_id=notice.id if (notice and i == first) else None, lang=lang)
    return sent


async def send_remaining(client, user_id, lang, st, sent_count):
    """Kept for compatibility: the 'x/y' counter is now part of the single notice sent by deliver()."""
    return
