"""
Auto-delete that SURVIVES restarts (Heroku restarts dynos every day):
pending deletions are stored in MongoDB and a background loop removes the due ones.
"""
import asyncio
import datetime
import logging

from database.users_chats_db import db
from languages import tr

logger = logging.getLogger(__name__)


async def schedule_delete(chat_id, msg_ids, delay, notice_id=None, lang="en"):
    await db.pdel.insert_one({
        "chat_id": int(chat_id),
        "ids": [int(i) for i in msg_ids],
        "at": datetime.datetime.utcnow() + datetime.timedelta(seconds=int(delay)),
        "notice_id": int(notice_id) if notice_id else None,
        "lang": lang,
    })


async def _run_due(client):
    now = datetime.datetime.utcnow()
    async for d in db.pdel.find({"at": {"$lte": now}}).limit(100):
        try:
            await client.delete_messages(d["chat_id"], d["ids"])
        except Exception as e:
            logger.debug(f"delete failed: {e}")
        if d.get("notice_id"):
            try:
                await client.edit_message_text(d["chat_id"], d["notice_id"], tr("deleted_notice", d.get("lang", "en")))
            except Exception:
                pass
        await db.pdel.delete_one({"_id": d["_id"]})


async def delete_loop(client):
    while True:
        try:
            await _run_due(client)
        except Exception as e:
            logger.error(f"delete loop error: {e}")
        await asyncio.sleep(30)
