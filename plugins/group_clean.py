"""Group cleanup: commands sent to this bot in a group (e.g. /trendlist@MyBot) are deleted after a few seconds.
Needs the bot to be admin with 'Delete messages' in that group. Settings: /admin -> Settings -> Limits."""
from pyrogram import Client, enums, filters

import botcfg
from deleter import schedule_delete
from utils import temp


@Client.on_message(filters.group & filters.text & filters.regex(r"^/\w+@\w+"), group=-3)
async def clean_commands(client, message):
    if not botcfg.get("group_cmd_delete"):
        return
    text = message.text.split(None, 1)[0].lower()
    if not text.endswith("@" + (temp.U_NAME or client.me.username).lower()):
        return                                          # command for another bot -> leave it
    try:
        me = await client.get_chat_member(message.chat.id, client.me.id)
        if me.status != enums.ChatMemberStatus.ADMINISTRATOR or not (me.privileges and me.privileges.can_delete_messages):
            return
    except Exception:
        return
    await schedule_delete(message.chat.id, [message.id], int(botcfg.get("group_cmd_delete_sec")))
