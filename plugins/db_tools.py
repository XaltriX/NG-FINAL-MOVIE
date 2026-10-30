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


# ---------------- database size tools (admin) ----------------
import re

from motor.motor_asyncio import AsyncIOMotorClient

from info import BOT_DB_URI, DATABASE_NAME, DATABASE_URI, DATABASE_URI2

PROTECTED = {"users", "uersz", "groups", "bot_settings", "premium", "referrals", "refers", "referusers", "requests"}
BOT_DBS = (DATABASE_NAME, "admin_database", "broadcast_db")


def _mb(n):
    return f"{n / 1048576:.1f} MB"


async def _cluster_report(uri, names, label):
    cl = AsyncIOMotorClient(uri)
    rows, total = [], 0
    for dbn in names:
        try:
            st = await cl[dbn].command("dbstats")
            total += st.get("storageSize", 0) + st.get("indexSize", 0)
            for cn in await cl[dbn].list_collection_names():
                try:
                    c = await cl[dbn].command("collStats", cn)
                    rows.append((c.get("storageSize", 0) + c.get("totalIndexSize", 0), f"{dbn}.{cn}", c.get("count", 0)))
                except Exception:
                    pass
        except Exception:
            pass
    rows.sort(reverse=True)
    out = f"<b>{label}</b>  (≈ {_mb(total)} of 512 MB)\n"
    for size, name, cnt in rows[:8]:
        out += f"• <code>{name}</code> — {_mb(size)} ({cnt} docs)\n"
    return out


@Client.on_message(filters.command("dbstats") & filters.user(ADMINS))
async def dbstats(client, message):
    """Which collections use the space (to decide what can be deleted)."""
    m = await message.reply("⏳ Checking database sizes...")
    text = await _cluster_report(BOT_DB_URI, BOT_DBS, "🗄 Bot-data cluster")
    if BOT_DB_URI != DATABASE_URI:
        text += "\n" + await _cluster_report(DATABASE_URI, (DATABASE_NAME,), "🗄 Files cluster 1")
    if DATABASE_URI2 not in (DATABASE_URI, BOT_DB_URI):
        text += "\n" + await _cluster_report(DATABASE_URI2, (DATABASE_NAME,), "🗄 Files cluster 2")
    text += "\n<i>Delete a big, unneeded collection with</i> <code>/dbdrop dbname.collection</code>"
    await m.edit_text(text)


@Client.on_message(filters.command("dbdrop") & filters.user(ADMINS))
async def dbdrop(client, message):
    """/dbdrop <db.collection> confirm   -> drops that collection on the bot-data cluster (frees space at once)."""
    if len(message.command) < 2 or "." not in message.command[1]:
        return await message.reply("Usage: <code>/dbdrop dbname.collection</code> (names from /dbstats)")
    dbn, cn = message.command[1].split(".", 1)
    if dbn not in BOT_DBS or cn in PROTECTED:
        return await message.reply("🚫 That collection is protected or not part of the bot data.")
    if len(message.command) < 3 or message.command[2] != "confirm":
        return await message.reply(f"⚠️ This deletes <code>{dbn}.{cn}</code> for good.\nSend <code>/dbdrop {dbn}.{cn} confirm</code> to continue.")
    await AsyncIOMotorClient(BOT_DB_URI)[dbn][cn].drop()
    await message.reply(f"✅ Dropped <code>{dbn}.{cn}</code>.")


@Client.on_message(filters.command("dbclean") & filters.user(ADMINS))
async def dbclean(client, message):
    """Safe automatic cleanup of data the bot can rebuild: old tokens, old delete jobs, old broadcast records, old search history."""
    import datetime
    cl = AsyncIOMotorClient(BOT_DB_URI)
    day_ago = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    done = []
    for dbn, cn in (("admin_database", "user"), ("broadcast_db", "user_broadcasts"), ("broadcast_db", "group_broadcasts")):
        try:
            await cl[dbn][cn].drop()
            done.append(f"{dbn}.{cn}")
        except Exception:
            pass
    try:
        r = await cl[DATABASE_NAME]["verify_tokens"].delete_many({"created": {"$lt": day_ago}})
        done.append(f"verify_tokens (old): {r.deleted_count}")
        r = await cl[DATABASE_NAME]["pending_deletes"].delete_many({"at": {"$lt": day_ago}})
        done.append(f"pending_deletes (old): {r.deleted_count}")
    except Exception:
        pass
    await message.reply("🧹 Cleaned:\n" + "\n".join(f"• {d}" for d in done) + "\n\nNow run /dbstats to see what is still big.")
