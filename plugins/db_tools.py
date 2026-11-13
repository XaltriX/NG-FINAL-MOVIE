from pyrogram import Client, filters

import migrate_db
from info import ADMINS


@Client.on_message(filters.command("cleanup_old_db") & filters.user(ADMINS))
async def cleanup_old_db(client, message):
    """After the data was copied to the dedicated DB: delete the OLD copies (shows the list first)."""
    if not migrate_db.needed() and BOT_DB_URI == DATABASE_URI:
        return await message.reply("ℹ️ No separate bot database is configured (set BOT_DB_URI).")
    confirm = len(message.command) > 1 and message.command[1] == "confirm"
    done = await migrate_db.cleanup_old(dry=not confirm)
    if done is None:
        return await message.reply("❌ Migration is not finished yet. Restart the bot once and try again.")
    names = "\n".join(f"• <code>{n}</code>" for n in done[:40]) or "<i>nothing to delete</i>"
    if not confirm:
        return await message.reply(f"⚠️ <b>These OLD copies will be deleted</b> (the bot already uses the new DB; "
                                   f"movie files are not touched):\n{names}\n\nSend <code>/cleanup_old_db confirm</code>")
    await message.reply(f"✅ Freed space: dropped {len(done)} old collections.\n{names}")


# ---------------- database size tools (admin) ----------------
import re

from motor.motor_asyncio import AsyncIOMotorClient

from info import BOT_DB_OLD_URI, BOT_DB_URI, DATABASE_NAME, DATABASE_URI, DATABASE_URI2, DATABASE_URIS

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


# ---------------- /dbs : every connected cluster, space used / free ----------------
import asyncio
import os

QUOTA = int(os.environ.get("DB_QUOTA_MB", 512))
_SYS = {"admin", "local", "config"}


def _host(uri):
    m = re.search(r"@([^/?]+)", uri or "")
    return (m.group(1).split(".")[0] + "…") if m else "?"


async def _cluster_all(uri):
    cl = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
    try:
        names = [n for n in await cl.list_database_names() if n not in _SYS]
    except Exception:
        names = list(dict.fromkeys(BOT_DBS))
    rows, total = [], 0
    for n in names:
        try:
            st = await cl[n].command("dbstats")
        except Exception:
            continue
        sz = st.get("storageSize", 0) + st.get("indexSize", 0)
        total += sz
        rows.append((n, sz))
    return total, sorted(rows, key=lambda r: -r[1])


@Client.on_message(filters.command("dbs") & filters.user(ADMINS))
async def dbs_cmd(client, message):
    """All connected databases at a glance: used / free MB and the biggest databases inside each."""
    m = await message.reply("⏳ Checking all databases...")
    labels = {}
    def add(uri, label):
        if uri:
            labels[uri] = f"{labels[uri]} + {label}" if uri in labels else label
    add(BOT_DB_URI, "🤖 Bot-data")
    for i, u in enumerate(DATABASE_URIS, 1):
        add(u, f"📁 Files {i}")
    if BOT_DB_OLD_URI not in labels:
        add(BOT_DB_OLD_URI, "🗃 Old / shared")
    items = list(labels.items())
    res = await asyncio.gather(*[_cluster_all(u) for u, _ in items], return_exceptions=True)
    out = f"<b>🗄 DATABASES</b>  ({len(items)} clusters, {QUOTA} MB each)\n"
    for (uri, label), r in zip(items, res):
        out += f"\n<b>{label}</b> · <code>{_host(uri)}</code>\n"
        if isinstance(r, Exception):
            out += "❌ not reachable\n"
            continue
        total, rows = r
        used = total / 1048576
        pct = min(used / QUOTA, 1)
        dot = "🔴" if pct > .85 else "🟡" if pct > .65 else "🟢"
        out += f"{dot} {'▰' * round(pct * 10)}{'▱' * (10 - round(pct * 10))} <b>{used:.0f}</b> / {QUOTA} MB ({pct * 100:.0f}%) · free <b>{max(QUOTA - used, 0):.0f} MB</b>\n"
        for j, (n, sz) in enumerate(rows[:5]):
            out += f"{'└' if j == min(len(rows), 5) - 1 else '├'} <code>{n}</code> {_mb(sz)}\n"
    await m.edit_text(out + "\n<i>Details: /dbstats  ·  free space: /dbclean</i>")
