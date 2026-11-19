"""Group anti-spam: links, @channel mentions, forwards from channels/bots, inline-button links, via-bot messages.
Ladder: warning 1..(N-1), strike N = mute "spam_mute_min" min, any spam after that = PERMANENT BAN (N = "spam_strikes", default 3).
Strikes are stored in the DB and forgotten after 30 days. Every action goes to LOG_CHANNEL with an Unban button.
Commands:  /antispam on|off  (group admin)     /allowlink add|del <text> | /allowlink  (bot ADMINS)"""
import asyncio
import datetime
import html
import logging
import re
import time

from pyrogram import Client, enums, filters
from pyrogram.types import ChatPermissions, InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
from database.users_chats_db import db
from info import ADMINS, LOG_CHANNEL
from plugins.group_clean import _can_manage
from utils import temp

log = logging.getLogger(__name__)
_col = db.db["antispam"]
_cfg = db.db["antispam_cfg"]
_str = db.db["spam_strikes"]
_on, _adm, _ment, _mem, _noperm = {}, {}, {}, {}, {}
_trust = None                                # user ids that are never checked
EXPIRE = 30 * 86400                          # strikes are forgotten after 30 days
SAFE_VIA = {"gif", "vid", "pic", "bing", "wiki", "youtube", "yt", "imdb", "music", "like", "sticker", "vote"}
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


async def _trusted():
    global _trust
    if _trust is None:
        try:
            d = await _cfg.find_one({"_id": "trust"})
            _trust = set((d or {}).get("ids", []))
        except Exception:
            return set()
    return _trust


def _fwd_chat(message):
    """channel / group a message was forwarded from (or None)."""
    o = getattr(message, "forward_origin", None)
    return getattr(o, "chat", None) or getattr(o, "sender_chat", None) if o else None


async def _find_spam(client, message):
    """-> (kind, detail) of the first violation, or None.  kinds: link, mention, forward, button, via"""
    allow = set(await _allowed_list())
    me = (temp.U_NAME or client.me.username or "").lower()
    allow |= {f"t.me/{me}", f"@{me}"}
    ok = lambda x: any(a in x for a in allow)
    # 1) forwarded from a channel / group / bot
    fc = _fwd_chat(message)
    o = getattr(message, "forward_origin", None)
    fu = getattr(o, "sender_user", None) if o else None
    if fc is not None or (fu is not None and fu.is_bot):
        un = (getattr(fc, "username", None) or getattr(fu, "username", None) or "").lower()
        ident = [f"t.me/{un}", f"@{un}", str(getattr(fc, "id", ""))] if un or fc else [f"@{un}"]
        if not any(i and i in allow for i in ident):
            return "forward", (getattr(fc, "title", None) or getattr(fu, "first_name", None) or "channel") + (f" (@{un})" if un else "")
    # 2) sent through an inline bot
    vb = getattr(message, "via_bot", None)
    if vb and (vb.username or "").lower() not in SAFE_VIA and (vb.username or "").lower() != me and not ok(f"@{(vb.username or '').lower()}"):
        return "via", f"@{vb.username}"
    # 3) inline buttons with links
    rm = getattr(message, "reply_markup", None)
    for row in (getattr(rm, "inline_keyboard", None) or []):
        for b in row:
            u = (getattr(b, "url", None) or getattr(b, "login_url", None) and b.login_url.url or "").lower()
            if u and not ok(u):
                return "button", u
    # 4) links / @channel mentions in text or caption
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
    for l in links:
        if not ok(l):
            return "link", l
    for n in mentions:
        if n == me or ok(f"@{n}") or ok(f"t.me/{n}"):
            continue
        if await _mention_is_spam(client, n):
            return "mention", "@" + n
    return None


async def _later(m, sec):
    await asyncio.sleep(sec)
    try:
        await m.delete()
    except Exception:
        pass


async def _log(client, text, markup=None):
    try:
        await client.send_message(LOG_CHANNEL, text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True,
                                  reply_markup=markup)
    except Exception:
        pass


async def _bump(cid, uid):
    """persistent strike counter (30 days); memory fallback when the DB refuses writes."""
    now, key = time.time(), f"{cid}:{uid}"
    try:
        d = await _str.find_one({"_id": key})
        n = (d["n"] if d and now - d["ts"] < EXPIRE else 0) + 1
        await _str.update_one({"_id": key}, {"$set": {"n": n, "ts": now}}, upsert=True)
        return n
    except Exception:
        m = _mem.get(key)
        n = (m[0] if m and now - m[1] < EXPIRE else 0) + 1
        _mem[key] = (n, now)
        return n


async def _reset(cid, uid):
    _mem.pop(f"{cid}:{uid}", None)
    try:
        await _str.delete_one({"_id": f"{cid}:{uid}"})
    except Exception:
        pass


KIND = {"link": "🔗 link", "mention": "📣 @channel/bot", "forward": "↪️ forward from", "button": "🔘 button link", "via": "🤖 via bot"}


async def _act(client, message, hit):
    kind, detail = hit
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
    n = await _bump(cid, user.id)
    what = "links, forwards and buttons"
    unban = M([[B("♻️ Unban / Unmute", callback_data=f"sp#ub#{cid}#{user.id}")]])
    markup = None
    if n > mx:                                                  # warnings + mute were ignored -> permanent ban
        try:
            await client.ban_chat_member(cid, user.id)
            await _reset(cid, user.id)
            note, action, markup = f"🚫 {mention} is <b>banned</b> for repeated spam.", "BANNED (permanent)", unban
        except Exception:
            note, action = f"🚫 {mention}, {what} are not allowed here.", "Deleted (ban failed: need Ban users right)"
    elif n == mx:
        try:
            await client.restrict_chat_member(cid, user.id, ChatPermissions(),
                                              until_date=datetime.datetime.utcnow() + datetime.timedelta(minutes=mins))
            note, action, markup = (f"🔇 {mention} is muted for <b>{mins} min</b>. <b>Next spam = permanent ban.</b>",
                                    f"Muted {mins} min (strike {n}/{mx})", unban)
        except Exception:
            note, action = f"🚫 {mention}, {what} are not allowed here.", "Deleted (mute failed: need Ban users right)"
    else:
        note = f"⚠️ {mention}, {what} are not allowed here.\n<b>Warning {n}/{mx - 1}</b> · next ones: mute, then ban."
        action = f"Warning {n}/{mx - 1}"
    try:
        m = await client.send_message(cid, note, parse_mode=enums.ParseMode.HTML)
        asyncio.create_task(_later(m, 25))
    except Exception:
        pass
    await _log(client, f"🛡 <b>ANTI-SPAM</b>\n👤 {mention} (<code>{user.id}</code>)\n"
                       f"💬 {html.escape(message.chat.title or '')} (<code>{cid}</code>)\n"
                       f"{KIND.get(kind, kind)}: <code>{html.escape(detail[:150])}</code>\n⚙️ <b>{action}</b>", markup)


async def _check(client, message):
    try:
        u = message.from_user
        if not u or u.is_bot or u.id == 777000 or message.sender_chat or message.service:
            return False
        cid = message.chat.id
        if not botcfg.get("spam_on") or not await is_on(cid):
            return False
        if u.id in await _trusted():
            return False
        hit = await _find_spam(client, message)
        if not hit or await _is_admin(client, cid, u.id):
            return False
        await _act(client, message, hit)
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


@Client.on_callback_query(filters.regex(r"^sp#ub#") & filters.user(ADMINS))
async def unban_cb(client, q):
    _, _, cid, uid = q.data.split("#")
    try:
        await client.unban_chat_member(int(cid), int(uid))
        await _reset(int(cid), int(uid))
        await q.answer("✅ Unbanned, strikes cleared", show_alert=True)
        await q.message.edit_reply_markup(None)
    except Exception as e:
        await q.answer(f"❌ {str(e)[:150]}", show_alert=True)


@Client.on_message(filters.command("trust") & filters.user(ADMINS), group=-4)
async def trust_cmd(client, message):
    global _trust
    ids = set(await _trusted())
    a = message.command
    if len(a) >= 3 and a[1].lower() in ("add", "del") and a[2].lstrip("-").isdigit():
        ids.add(int(a[2])) if a[1].lower() == "add" else ids.discard(int(a[2]))
        _trust = ids
        try:
            await _cfg.update_one({"_id": "trust"}, {"$set": {"ids": sorted(ids)}}, upsert=True)
        except Exception as e:
            return await message.reply_text(f"❌ Could not save: {e}")
    body = "\n".join(f"• <code>{i}</code>" for i in sorted(ids)) or "<i>empty</i>"
    await message.reply_text(f"<b>🤝 Trusted users (never checked)</b>\n{body}\n\n<code>/trust add 123456</code> · <code>/trust del 123456</code>",
                             parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()
