"""Welcome card for new group members + owner panel for its buttons.
Group admins: /welcome on|off          Owner (bot ADMINS, in PM): /welcomebtn   (callbacks: wl#)
One card per group: when new members join, the previous card is deleted and a new one is sent (joins within a few
seconds are merged into ONE card). The card is never auto-deleted by /gclean."""
import asyncio
import html
import logging
import time

from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
from database.users_chats_db import db
from info import ADMINS
from plugins.group_clean import NOCLEAN, _can_manage
from utils import temp

log = logging.getLogger(__name__)
_col = db.db["welcome"]
_on, _last, _q = {}, {}, {}
WINDOW = 4                         # seconds: joins inside this window are merged into one card
DOTS = {"blue": "🔵", "green": "🟢", "red": "🔴", "none": ""}
MAX_BTNS = 6

_BOLD = {**{chr(65 + i): chr(0x1D5D4 + i) for i in range(26)}, **{chr(97 + i): chr(0x1D5EE + i) for i in range(26)}}


def bold(s):
    return "".join(_BOLD.get(c, c) for c in s)


def esc(s, n=25):
    return html.escape((s or "User").strip()[:n])


def _uname(client):
    return temp.U_NAME or client.me.username


def names_text(users):
    ms = [f'<a href="tg://user?id={i}">{esc(n)}</a>' for i, n in list(users.items())[:3]]
    extra = len(users) - len(ms)
    if extra > 0:
        return ", ".join(ms) + f" &amp; {extra} others"
    return ms[0] if len(ms) == 1 else ", ".join(ms[:-1]) + " &amp; " + ms[-1]


def card_text(client, users, title):
    return (f"👋 <b>{bold('Welcome')}, {names_text(users)}!</b>\n"
            f"📍 <b>{esc(title, 60)}</b>\n\n"
            f"🎬 <b>{bold(client.me.first_name or 'Movie Bot')}</b>\n"
            f"Get any movie or series in seconds.\n\n"
            f"🔍 <b>{bold('How to search')}</b>\n"
            f"Just type the name in this chat 👇\n\n"
            f"   ➤ <code>Jailer 2 2026</code>\n"
            f"   ➤ <code>Loki S01 E01</code>\n"
            f"   ➤ <code>Pushpa 2 Hindi</code>\n\n"
            f"<blockquote>✨ <b>{bold('Why us?')}</b>\n"
            f"⚡ Fast speed\n🆓 Free to use\n🚫 No ads\n🎞 HD quality</blockquote>")


def card_kb(client):
    row = [B("▶️ Start Bot", url=f"https://t.me/{_uname(client)}?start=start")]
    for b in botcfg.get("welcome_btns")[:MAX_BTNS]:
        row.append(B(f"{DOTS.get(b.get('c'), '')} {b['t']}".strip(), url=b["u"]))
    return M([row[i:i + 2] for i in range(0, len(row), 2)])


# ---------------------------------------------------------------- per-group switch
async def is_on(cid):
    if cid in _on:
        return _on[cid]
    try:
        d = await _col.find_one({"chat_id": cid})
        _on[cid] = not (d and d.get("on") is False)
    except Exception:
        return True
    return _on[cid]


@Client.on_message(filters.group & filters.command("welcome"), group=-4)
async def welcome_cmd(client, message):
    if not message.from_user or not await _can_manage(client, message.chat.id, message.from_user.id):
        return
    cid = message.chat.id
    arg = message.command[1].lower() if len(message.command) > 1 else ""
    if arg == "test":                                   # shows the card now, for the admin who asked
        tok = NOCLEAN.set(True)
        try:
            await client.send_message(cid, card_text(client, {message.from_user.id: message.from_user.first_name},
                                                     message.chat.title or ""), reply_markup=card_kb(client),
                                      parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            await message.reply_text(f"❌ Could not send the card: <code>{html.escape(str(e))[:200]}</code>",
                                     parse_mode=enums.ParseMode.HTML)
        finally:
            NOCLEAN.reset(tok)
        return message.stop_propagation()
    if arg in ("on", "off"):
        _on[cid] = arg == "on"
        try:
            await _col.update_one({"chat_id": cid}, {"$set": {"on": _on[cid]}}, upsert=True)
        except Exception:
            pass
    st = "🟢 ON" if await is_on(cid) else "🔴 OFF"
    await message.reply_text(f"<b>👋 Welcome card: {st}</b>\nChange: <code>/welcome on</code> / <code>/welcome off</code> · try: <code>/welcome test</code>",
                             parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()


# ---------------------------------------------------------------- sending
_seen = {}                          # (chat, user) -> time: the same join can arrive as service message AND member update


async def _enqueue(client, chat, members):
    cid = chat.id
    now = time.time()
    if len(_seen) > 5000:
        _seen.clear()
    users = []
    for u in members:
        if u.is_bot or u.id == client.me.id or now - _seen.get((cid, u.id), 0) < 120:
            continue
        _seen[(cid, u.id)] = now
        users.append(u)
    if not users or not botcfg.get("welcome_on") or not await is_on(cid):
        return
    q = _q.setdefault(cid, {"users": {}, "task": None})
    for u in users:
        q["users"][u.id] = u.first_name or "User"
    if not q["task"] or q["task"].done():
        q["task"] = asyncio.create_task(_flush(client, cid, chat.title or ""))


@Client.on_message(filters.group & filters.new_chat_members, group=-4)
async def on_join(client, message):
    try:
        await _enqueue(client, message.chat, message.new_chat_members)
    except Exception:
        log.exception("welcome join")


@Client.on_chat_member_updated(filters.group, group=-4)
async def on_member_update(client, upd):
    """Big groups send no 'X joined' service message; admin bots get this update instead."""
    try:
        new, old = upd.new_chat_member, upd.old_chat_member
        if not new or new.status != enums.ChatMemberStatus.MEMBER:
            return
        if old and old.status in (enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR,
                                  enums.ChatMemberStatus.OWNER):
            return
        await _enqueue(client, upd.chat, [new.user])
    except Exception:
        log.exception("welcome member update")


async def _flush(client, cid, title):
    q = _q[cid]
    while q["users"]:
        await asyncio.sleep(WINDOW)
        users, q["users"] = q["users"], {}
        if not users:
            break
        tok = NOCLEAN.set(True)
        try:
            for _ in range(2):
                try:
                    m = await client.send_message(cid, card_text(client, users, title), reply_markup=card_kb(client),
                                                  parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
                    break
                except FloodWait as e:
                    await asyncio.sleep(min(e.value, 30))
            else:
                continue
        except Exception as e:
            log.warning(f"welcome send failed in {cid}: {e}")
            continue
        finally:
            NOCLEAN.reset(tok)
        old = _last.get(cid)
        if old is None:
            try:
                d = await _col.find_one({"chat_id": cid})
                old = d.get("last_id") if d else None
            except Exception:
                old = None
        if old:
            try:
                await client.delete_messages(cid, old)
            except Exception:
                pass
        _last[cid] = m.id
        try:
            await _col.update_one({"chat_id": cid}, {"$set": {"last_id": m.id}}, upsert=True)
        except Exception:
            pass


# ---------------------------------------------------------------- owner panel for buttons (PM)
_wait = {}                          # admin_id -> ("add"|"ed", index)


def _panel():
    bs = botcfg.get("welcome_btns")
    t = "<b>🎛 WELCOME BUTTONS</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>1.</b> ▶️ Start Bot <i>(fixed)</i>\n"
    for i, b in enumerate(bs, 2):
        t += f"<b>{i}.</b> {DOTS.get(b.get('c'), '')} {html.escape(b['t'])}\n<code>{html.escape(b['u'])}</code>\n"
    t += "\n<i>🎨 colour  ✏️ edit  ⬆️ up  🗑 delete</i>"
    t += f"\n\n👋 <b>Welcome card:</b> {'🟢 ON' if botcfg.get('welcome_on') else '🔴 OFF'}   🛡 <b>Link anti-spam:</b> {'🟢 ON' if botcfg.get('spam_on') else '🔴 OFF'}"
    rows = [[B(f"🎨 {i}", callback_data=f"wl#col#{i - 2}"), B(f"✏️ {i}", callback_data=f"wl#ed#{i - 2}"),
             B(f"⬆️ {i}", callback_data=f"wl#up#{i - 2}"), B(f"🗑 {i}", callback_data=f"wl#del#{i - 2}")]
            for i in range(2, len(bs) + 2)]
    rows.append(([B("➕ Add button", callback_data="wl#add")] if len(bs) < MAX_BTNS else [])
                + [B("👁 Preview", callback_data="wl#prev")])
    rows.append([B("👋 Welcome ON/OFF", callback_data="wl#tw"), B("🛡 Anti-spam ON/OFF", callback_data="wl#ts")])
    rows.append([B("♻️ Reset", callback_data="wl#reset"), B("⬅️ Back", callback_data="adm#home")])
    return t, M(rows)


async def _show(msg):
    t, kb = _panel()
    try:
        await msg.edit_text(t, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    except MessageNotModified:
        pass


@Client.on_message(filters.private & filters.command("welcomebtn") & filters.user(ADMINS), group=-4)
async def welcomebtn_cmd(client, message):
    _wait.pop(message.from_user.id, None)
    t, kb = _panel()
    await message.reply_text(t, reply_markup=kb, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    message.stop_propagation()


@Client.on_callback_query(filters.regex(r"^wl#") & filters.user(ADMINS))
async def wl_cb(client, q):
    p = q.data.split("#")
    act, uid = p[1], q.from_user.id
    bs = botcfg.get("welcome_btns")
    i = int(p[2]) if len(p) > 2 and p[2].lstrip("-").isdigit() else -1
    if act == "close":
        _wait.pop(uid, None)
        return await q.message.delete()
    if act == "add":
        _wait[uid] = ("add", -1, q.message)
        return await q.message.edit_text("<b>➕ Send the button as:</b>\n<code>Button text | https://link</code>\n\n"
                                         "Example: <code>Join Channel | https://t.me/NeonGhost_Network</code>",
                                         reply_markup=M([[B("⬅️ Cancel", callback_data="wl#home")]]),
                                         parse_mode=enums.ParseMode.HTML)
    if act == "ed" and 0 <= i < len(bs):
        _wait[uid] = ("ed", i, q.message)
        return await q.message.edit_text(f"<b>✏️ Send the new text and link for button {i + 2}:</b>\n"
                                         f"<code>Button text | https://link</code>",
                                         reply_markup=M([[B("⬅️ Cancel", callback_data="wl#home")]]),
                                         parse_mode=enums.ParseMode.HTML)
    _wait.pop(uid, None)
    if act == "col" and 0 <= i < len(bs):
        row = [B(f"{DOTS[c] or '⚪'} {c.title()}", callback_data=f"wl#cl#{i}#{c}") for c in DOTS]
        return await q.message.edit_text(f"<b>🎨 Colour for button {i + 2}</b>\n<i>(shown as a coloured dot before the text)</i>",
                                         reply_markup=M([row[:2], row[2:], [B("⬅️ Back", callback_data="wl#home")]]),
                                         parse_mode=enums.ParseMode.HTML)
    if act == "cl" and 0 <= i < len(bs) and len(p) > 3 and p[3] in DOTS:
        bs[i]["c"] = p[3]
        await botcfg.set("welcome_btns", bs)
    elif act == "up" and 0 < i < len(bs):
        bs[i - 1], bs[i] = bs[i], bs[i - 1]
        await botcfg.set("welcome_btns", bs)
    elif act == "del" and 0 <= i < len(bs):
        bs.pop(i)
        await botcfg.set("welcome_btns", bs)
    elif act == "tw":
        await botcfg.set("welcome_on", not botcfg.get("welcome_on"))
    elif act == "ts":
        await botcfg.set("spam_on", not botcfg.get("spam_on"))
    elif act == "reset":
        await botcfg.set("welcome_btns", botcfg.DEFAULTS["welcome_btns"])
    elif act == "prev":
        await client.send_message(q.message.chat.id, card_text(client, {uid: q.from_user.first_name}, "Your Group"),
                                  reply_markup=card_kb(client), parse_mode=enums.ParseMode.HTML)
        return await q.answer("👁 Preview sent")
    await _show(q.message)
    await q.answer()


@Client.on_message(filters.private & filters.user(ADMINS) & filters.text & ~filters.command(["welcomebtn"]), group=-3)
async def wl_input(client, message):
    st = _wait.get(message.from_user.id)
    if not st or message.text.startswith("/"):
        return
    kind, i, panel = st
    t, _, u = message.text.partition("|")
    t, u = t.strip(), u.strip()
    if not t or not u.lower().startswith(("http://", "https://", "tg://")):
        return await message.reply_text("❌ Use this format:\n<code>Button text | https://link</code>", parse_mode=enums.ParseMode.HTML)
    bs = botcfg.get("welcome_btns")
    if kind == "add":
        bs.append({"t": t[:30], "u": u, "c": "blue"})
    elif 0 <= i < len(bs):
        bs[i].update({"t": t[:30], "u": u})
    await botcfg.set("welcome_btns", bs)
    _wait.pop(message.from_user.id, None)
    await message.delete()
    await _show(panel)
    message.stop_propagation()
