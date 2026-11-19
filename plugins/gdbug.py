"""/gdebug  (group admins / bot ADMINS) - one card that shows why the bot may be silent in a group:
privacy mode, admin rights, how many group messages it really received, group settings, gclean/antispam/welcome state."""
import logging
import time

from pyrogram import Client, enums, filters, raw

import botcfg
from info import ADMINS
from plugins.group_clean import _can_manage, is_on as gclean_on
from utils import get_settings

log = logging.getLogger(__name__)
_seen = {}                                   # chat_id -> [count, last_time, last_text]
_total = [0]


@Client.on_message(filters.group & ~filters.service, group=-20)
async def _count(client, message):
    _total[0] += 1
    s = _seen.setdefault(message.chat.id, [0, 0, ""])
    s[0] += 1
    s[1] = time.time()
    s[2] = (message.text or message.caption or "<media>")[:25]
    if _total[0] <= 15:
        log.warning(f"[GDBG] group msg #{_total[0]} chat={message.chat.id} user={getattr(message.from_user, 'id', None)} "
                    f"text={s[2]!r}")


@Client.on_message(filters.group & filters.command("gdebug"), group=-19)
async def gdebug(client, message):
    if not message.from_user or not await _can_manage(client, message.chat.id, message.from_user.id):
        return
    cid = message.chat.id
    try:
        me = (await client.invoke(raw.functions.users.GetUsers(id=[raw.types.InputUserSelf()])))[0]
        privacy = "🟢 OFF (bot reads every message)" if getattr(me, "bot_chat_history", False) else "🔴 ON (bot only gets commands/replies unless it is admin)"
    except Exception as e:
        privacy = f"? ({e})"
    try:
        m = await client.get_chat_member(cid, client.me.id)
        adm = f"{m.status.name}" + (f" · delete={m.privileges.can_delete_messages} · ban={m.privileges.can_restrict_members}"
                                    if m.privileges else "")
    except Exception as e:
        adm = f"? ({e})"
    try:
        st = await get_settings(cid)
        sett = f"auto_ffilter={st.get('auto_ffilter')} · auto_delete={st.get('auto_delete')}"
    except Exception as e:
        sett = f"? ({e})"
    s = _seen.get(cid)
    got = f"{s[0]} (last {int(time.time() - s[1])}s ago: {s[2]!r})" if s else "0  ← nothing received yet"
    await message.reply_text(
        "<b>🔧 GROUP DEBUG</b>\n"
        f"<b>Privacy mode:</b> {privacy}\n"
        f"<b>Bot in this group:</b> {adm}\n"
        f"<b>Group messages received here:</b> {got}\n"
        f"<b>All groups since start:</b> {_total[0]}\n"
        f"<b>Settings:</b> {sett}\n"
        f"<b>/gclean:</b> {'ON' if await gclean_on(cid) else 'OFF'} · <b>Welcome:</b> {botcfg.get('welcome_on')} · "
        f"<b>Anti-spam:</b> {botcfg.get('spam_on')}\n\n"
        "<i>Now send any normal text here and run /gdebug again.</i>",
        parse_mode=enums.ParseMode.HTML)
    message.stop_propagation()
