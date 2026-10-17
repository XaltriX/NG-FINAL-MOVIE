from pyrogram import Client, filters

import migrate_db
from info import ADMINS


@Client.on_message(filters.command("cleanup_old_db") & filters.user(ADMINS))
async def cleanup_old_db(client, message):
    """After the data was copied to the dedicated DB: delete the old copies from the full cluster."""
    if not migrate_db.needed():
        return await message.reply("ℹ️ No dedicated bot database is configured (set DATABASE_URI3).")
    if len(message.command) < 2 or message.command[1] != "confirm":
        return await message.reply("⚠️ This deletes the OLD copy of users/settings/etc from the first database "
                                   "(the bot already uses the new one). Movie files are not touched.\n\n"
                                   "Send <code>/cleanup_old_db confirm</code> to continue.")
    done = await migrate_db.cleanup_old()
    if done is None:
        return await message.reply("❌ Migration is not finished yet. Restart the bot once and try again.")
    await message.reply(f"✅ Freed space: dropped {len(done)} old collections.")
