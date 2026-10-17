from motor.motor_asyncio import AsyncIOMotorClient
from info import BOT_DB_URI
from datetime import datetime, timedelta
import re
import pytz

class Database:
    def __init__(self, uri, db_name):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.col = self.db.user
        self.config_col = self.db.configuration
        self.weekly = self.db.weekly_searches

    @staticmethod
    def week_start():
        """Monday 12:00 AM IST of the current week, as 'YYYY-MM-DD'."""
        now = datetime.now(pytz.timezone("Asia/Kolkata"))
        return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

    async def _bump_weekly(self, message_text):
        q = re.sub(r"\s+", " ", (message_text or "").lower()).strip()
        if len(q) < 2 or len(q) > 60 or q.startswith("/"):
            return
        wk = self.week_start()
        await self.weekly.update_one({"week": wk, "q": q}, {"$inc": {"count": 1}}, upsert=True)

    async def get_weekly(self, limit=20):
        """[(text, count)] for the current Monday->Sunday week; older weeks are cleared automatically."""
        wk = self.week_start()
        old = (datetime.strptime(wk, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y-%m-%d")
        try:
            await self.weekly.delete_many({"week": {"$lt": old}})
        except Exception:
            pass
        rows = await self.weekly.find({"week": wk}).sort("count", -1).limit(max(limit * 3, 60)).to_list(None)
        return [(r["q"], r["count"]) for r in rows]

    async def update_top_messages(self, user_id, message_text):
        """Statistics only: must NEVER stop a search (e.g. when the Atlas cluster is full and writes are blocked)."""
        try:
            await self._bump_weekly(message_text)
            user = await self.col.find_one({"user_id": user_id, "messages.text": message_text})
            if not user:
                await self.col.update_one({"user_id": user_id}, {"$push": {"messages": {"text": message_text, "count": 1}}}, upsert=True)
            else:
                await self.col.update_one({"user_id": user_id, "messages.text": message_text}, {"$inc": {"messages.$.count": 1}})
        except Exception:
            pass

    async def get_top_messages(self, limit=30):
        pipeline = [
            {"$unwind": "$messages"},
            {"$group": {"_id": "$messages.text", "count": {"$sum": "$messages.count"}}},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        results = await self.col.aggregate(pipeline).to_list(limit)
        return [result['_id'] for result in results]
    
    async def delete_all_messages(self):
        await self.col.delete_many({})

mdb = Database(BOT_DB_URI, "admin_database")