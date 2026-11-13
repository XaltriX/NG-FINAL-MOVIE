"""Group link anti-spam.  Links / t.me / @channel-or-bot mentions from normal members are deleted.
Strike N (default 3, /admin config "spam_strikes") = mute for "spam_mute_min" (default 60) minutes; every action is logged
to LOG_CHANNEL. Group admins and bot ADMINS are exempt.
Commands:  /antispam on|off  (group admin)     /allowlink add|del <text> | /allowlink  (bot ADMINS)"""
import asyncio
import datetime
import html
import logging
import re
import time

from pyrogram import Client, enums, filters
from pyrogram.types import ChatPermissions

import botcfg
from database.users_chats_db import db
from info import ADMINS, LOG_CHANNEL
from plugins.group_clean import _can_manage
from utils import temp

log = logging.getLogger(__name__)
_col = db.db["antispam"]
_cfg = db.db["antispam_cfg"]
_on, _adm, _ment, _strikes, _noperm = {}, {}, {}, {}, {}
_allow = None                               # lower-case substrings that are always allowed

URL_RE = re.compile(
    r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/)\S+"
    r"|\b[a-z0-9][a-z0-9-]+\.(?:com|in|net|org|me|io|xyz|co|link|site|cc|app|info|top|club|online|live|tv|ly|gl|bio|fun|pw|shop|store|biz)\b(?:/\S*)?")
ET = enums.MessageEntityType


async def _allowed_list():
    global _allow
    if _allow is None:
        try:
            d = await _cfg.find_one({"_id": "allow"})
            _allow = {x.lower() for x in (d or {}).get("items", [])}
        except Exception:
            return set()
    return _allow


async def is_on(cid):
    if cid in _on:
        return _on[cid]
    try:
        d = await _col.find_one({"chat_id": cid})
        _on[cid] = not (d and d.get("on") is False)
    except Exception:
        return True
    return _on[cid]


async def _is_admin(client, cid, uid):
    if uid in ADMINS:
        return True
    v = _adm.get((cid, uid))
    if v and time.time() - v[1] < 300:
        return v[0]
    try:
        m = await client.get_chat_member(cid, uid)
        r = m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        r = False
    if len(_adm) > 5000:
        _adm.clear()
    _adm[(cid, uid)] = (r, time.time())
    return r


def _slice(text, e):
    b = text.encode("utf-16-le")
    return b[e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le", "ignore")


async def _mention_is_spam(client, name):
    v = _ment.get(name)
    if v and time.time() - v[1] < 3600:
        return v[0]
    try:
        c = await client.get_chat(name)
        r = c.type in (enums.ChatType.CHANNEL, enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.BOT)
    except Exception:
        r = False
    _ment[name] = (r, time.time())
    return r


async def _find_spam(client, message):
    """-> the offending link text, or None."""
    text = message.text or message.caption or ""
    if not text:
        return None
    ents = message.entities or message.caption_entities or []
    links = [m.group(0).lower() for m in URL_RE.finditer(text)]
    mentions = []
    for e in ents:
        if e.type == ET.TEXT_LINK and e.url:
            links.append(e.url.lower())
        elif e.type == ET.URL:
            links.append(_slice(text, e).lower())
        elif e.type == ET.MENTION:
            mentions.append(_slice(text, e).lstrip("@").lower())
    allow = set(await _allowed_list())
    me = (temp.U_NAME or client.me.username or "").lower()
    allow |= {f"t.me/{me}", f"@{me}"}
    for l in links:
        if not any(a in l for a in allow):
            return l
    for n in mentions:
        if n == me or f"@{n}" in allow or f"t.me/{n}" in allow:
            continue
        if await _mention_is_spam(client, n):
            return "@" + n
    return None


async def _later(m, sec):
    await asyncio.sleep(sec)
    try:
        await m.delete()
    except Exception:
        pass


async def _log(client, text):
    try:
        await client.send_message(LOG_CHANNEL, text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        pass


async def _act(client, message, link):
    cid, user = message.chat.id, message.from_user
    mention = f'<a href="tg://user?id={user.id}">{html.escape((user.first_name or "User")[:25])}</a>'
    try:
        await message.delete()
    except Exception:
        if time.time() - _noperm.get(cid, 0) > 3600:           # tell the owner once an hour
            _noperm[cid] = time.time()
            await _log(client, f"⚠️ <b>Anti-spam can't work in</b> {html.escape(message.chat.title or '')} "
                               f"(<code>{cid}</code>): give me admin with <b>Delete messages</b> + <b>Ban users</b>.")
        return
    mx, mins = int(botcfg.get("spam_strikes")), int(botcfg.get("spam_mute_min"))
    now, key = time.time(), (cid, user.id)
    hits = [t for t in _strikes.get(key, []) if now - t < 86400] + [now]
    muted = len(hits) >= mx
    if muted:
        _strikes.pop(key, None)
        try:
            await client.restrict_chat_member(cid, user.id, ChatPermissions(),
                                              until_date=datetime.datetime.utcnow() + datetime.timedelta(minutes=mins))
            note = f"🔇 {mention} is muted for <b>{mins} min</b> for sending links."
            action = f"Muted {mins} min"
        except Exception:
            note = f"🚫 {mention}, links are not allowed here."
            action = "Link deleted (mute failed: need Ban users right)"
    else:
        if len(_strikes) > 20000:
            _strikes.clear()
        _strikes[key] = hits
        note = f"⚠️ {mention}, links are not allowed here.\n<b>Warning {len(hits)}/{mx}</b> · the next one is a mute."
        action = f"Warning {len(hits)}/{mx}"
    try:
        n = await client.send_message(cid, note, parse_mode=enums.ParseMode.HTML)
        asyncio.create_task(_later(n, 20))
    except Exception:
        pass
    await _log(client, f"🛡 <b>ANTI-SPAM</b>\n👤 {mention} (<code>{user.id}</code>)\n"
                       f"💬 {html.escape(message.chat.title or '')} (<code>{cid}</code>)\n"
                       f"🔗 <code>{html.escape(link[:150])}</code>\n⚙️ <b>{action}</b>")


async def _check(client, message):
    try:
        u = message.from_user
        if not u or u.is_bot or u.id == 777000 or message.sender_chat or message.service:
            return False
        cid = message.chat.id
        if not botcfg.get("spam_on") or not (message.text or message.caption) or not await is_on(cid):
            return False
        link = await _find_spam(client, message)
        if not link or await _is_admin(client, cid, u.id):
            return False
        await _act(client, message, link)
        return True
    except Exception:
        log.exception("antispam")
        return False


@Client.on_message(filters.group & ~filters.service, group=-5)
async def spam_msg(client, message):
    if await _check(client, message):
        message.stop_propagation()


@Client.on_edited_message(filters.group & ~filters.service, group=-5)
async def spam_edit(client, message):
    if await _check(client, message):
        message.stop_propagation()


@Client.on_message(filters.group & filters.command("antispam"), group=-4)
async def antispam_cmd(client, message):
    if not message.from_user or not await _can_manage(client, message.chat.id, message.from_user.id):
        return
    cid = message.chat.id
    arg = message.command[1].lower() if len(message.command) > 1 else ""
    if arg in ("on", "off"):
        _on[cid] = arg == "on"
        try:
            await _col.update_one({"chat_id": cid}, {"$set": {"on": _on[cid]}}, upsert=True)
        except Exception:
            pass
    await message.reply_text(f"<b>🛡 Link anti-spam: {'🟢 ON' if await is_on(cid) else '🔴 OFF'}</b>\n"
                             f"Change: <code>/antispam on</code> or <code>/antispam off</code>",
                             parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()


@Client.on_message(filters.command("allowlink") & filters.user(ADMINS), group=-4)
async def allowlink_cmd(client, message):
    global _allow
    items = set(await _allowed_list())
    a = message.command
    if len(a) >= 3 and a[1].lower() in ("add", "del"):
        v = " ".join(a[2:]).strip().lower()
        items.add(v) if a[1].lower() == "add" else items.discard(v)
        _allow = items
        try:
            await _cfg.update_one({"_id": "allow"}, {"$set": {"items": sorted(items)}}, upsert=True)
        except Exception as e:
            return await message.reply_text(f"❌ Could not save: {e}")
    body = "\n".join(f"• <code>{html.escape(i)}</code>" for i in sorted(items)) or "<i>empty</i>"
    await message.reply_text(f"<b>✅ Allowed links</b>\n{body}\n\n<code>/allowlink add t.me/YourChannel</code>\n"
                             f"<code>/allowlink del t.me/YourChannel</code>", parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()
