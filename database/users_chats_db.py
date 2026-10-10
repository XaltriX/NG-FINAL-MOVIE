import motor.motor_asyncio
from info import *
import datetime
import pytz  
from pymongo.errors import DuplicateKeyError

class Database:    
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        # Collections
        self.col = self.db.users
        self.grp = self.db.groups
        self.users = self.db.uersz
        self.req = self.db.requests
        self.botcol = self.db.bot_settings
        self.misc = self.db.misc
        self.filename_col = self.db.filename
        self.movie_updates = self.db.movie_updates
        self.connection = self.db.connections
        self.tokens = self.db.verify_tokens
        self.pdel = self.db.pending_deletes

    async def add_name(self, filename):
        if await self.movie_updates.find_one({'_id': filename}):
            return False
        await self.movie_updates.insert_one({'_id': filename})
        return True

    async def delete_all_msg(self):
        await self.movie_updates.delete_many({})
        print("All filenames notification have been deleted.")
        return True


    async def add_join_req(self, user_id: int, channel_id: int): #update
        await self.req.update_one(
            {'user_id': user_id},
            {
                '$addToSet': {'channels': channel_id},
                '$setOnInsert': {'created_at': datetime.datetime.utcnow()}
            },
            upsert=True
        )

    async def has_joined_channel(self, user_id: int, channel_id: int):
        doc = await self.req.find_one({'user_id': user_id})
        return doc and 'channels' in doc and channel_id in doc['channels']

    async def del_join_req(self):
        await self.req.drop()

    def new_user(self, id, name):
        return dict(
            id = id,
            name = name,
            ban_status=dict(
                is_banned=False,
                ban_reason="",
            ),
        )

    def new_group(self, id, title):
        return dict(
            id = id,
            title = title,
            chat_status=dict(
                is_disabled=False,
                reason="",
            ),
        )

    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def remove_ban(self, id):
        ban_status = dict(
            is_banned=False,
            ban_reason=''
        )
        await self.col.update_one({'id': id}, {'$set': {'ban_status': ban_status}})

    async def ban_user(self, user_id, ban_reason="No Reason"):
        ban_status = dict(
            is_banned=True,
            ban_reason=ban_reason
        )
        await self.col.update_one({'id': user_id}, {'$set': {'ban_status': ban_status}})

    async def get_ban_status(self, id):
        default = dict(
            is_banned=False,
            ban_reason=''
        )
        user = await self.col.find_one({'id':int(id)})
        if not user:
            return default
        return user.get('ban_status', default)

    async def get_all_users(self):
        return self.col.find({})

    async def get_premium_users(self):
        """
        Bug fix: /premium_users used to loop through EVERY user who ever
        started the bot (self.col, could be lakhs) and run a SEPARATE
        MongoDB query per user just to check for premium — making the
        command take forever ("Fetching..." never finishes) on any bot
        with a decent-sized user base.

        This queries the premium collection (self.users) directly for
        only the users who actually have an expiry_time set — a single
        efficient filtered query instead of thousands of round trips.
        """
        return self.users.find({"expiry_time": {"$ne": None}})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def delete_chat(self, id):
        await self.grp.delete_many({'id': int(id)})    

    async def get_banned(self):
        users = self.col.find({'ban_status.is_banned': True})
        chats = self.grp.find({'chat_status.is_disabled': True})
        b_chats = [chat['id'] async for chat in chats]
        b_users = [user['id'] async for user in users]
        return b_users, b_chats

    async def add_chat(self, chat, title):
        chat = self.new_group(chat, title)
        await self.grp.insert_one(chat)

    async def get_chat(self, chat):
        chat = await self.grp.find_one({'id':int(chat)})
        return False if not chat else chat.get('chat_status')

    async def re_enable_chat(self, id):
        chat_status=dict(
            is_disabled=False,
            reason="",
            )
        await self.grp.update_one({'id': int(id)}, {'$set': {'chat_status': chat_status}})

    async def update_settings(self, id, settings):
        await self.grp.update_one({'id': int(id)}, {'$set': {'settings': settings}})

    async def get_settings(self, id):
        default = {
            'button': BUTTON_MODE,
            'botpm': P_TTI_SHOW_OFF,
            'imdb': IMDB,
            'spell_check': SPELL_CHECK_REPLY,
            'welcome': MELCOW_NEW_USERS,
            'auto_delete': AUTO_DELETE,
            'auto_ffilter': AUTO_FFILTER,
            'max_btn': MAX_BTN,
            'template': IMDB_TEMPLATE,
            'log': LOG_CHANNEL,
            'fsub': AUTH_CHANNELS,
        }
        chat = await self.grp.find_one({'id':int(id)})
        if chat and 'settings' in chat:
            return chat['settings']
        else:
            return default.copy()

    async def dreamx_reset_settings(self):
        try:
            result = await self.grp.update_many(
                {'settings': {'$exists': True}}, 
                {'$unset': {'settings': ""}}    
            )
            return result.modified_count
        except Exception as e:
            print(f"[ERROR] Failed to reset group settings: {e}")
            raise  

    async def disable_chat(self, chat, reason="No Reason"):
        chat_status=dict(
            is_disabled=True,
            reason=reason,
            )
        await self.grp.update_one({'id': int(chat)}, {'$set': {'chat_status': chat_status}})

    async def total_chat_count(self):
        count = await self.grp.count_documents({})
        return count

    async def get_all_chats(self):
        return self.grp.find({})

    async def get_db_size(self):
        return (await self.db.command("dbstats"))['dataSize']

    async def get_user(self, user_id):
        user_data = await self.users.find_one({"id": user_id})
        return user_data
    async def update_user(self, user_data):
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def has_premium_access(self, user_id):
        user_data = await self.get_user(user_id)
        if user_data:
            expiry_time = user_data.get("expiry_time")
            if expiry_time is None:
                return False
            elif isinstance(expiry_time, datetime.datetime):
                # Bug fix: normalize naive (legacy) datetimes to UTC-aware
                # before comparing, so naive and UTC-aware expiry values are both compared correctly.
                if expiry_time.tzinfo is None:
                    expiry_time = expiry_time.replace(tzinfo=pytz.utc)
                if datetime.datetime.now(pytz.utc) <= expiry_time:
                    return True
                else:
                    await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
            else:
                await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
        return False

    # ==========================================================
    # Daily Download Limit System function start
    # Free users are allowed DAILY_DOWNLOAD_LIMIT file downloads
    # every rolling 24 hours. Premium users are always unlimited.
    # ==========================================================
    async def get_download_status(self, user_id):
        """
        Single-query helper that returns the user's current premium +
        download status, auto-resetting the daily counter if 24 hours
        have passed since the last reset. Used internally by
        can_download / increase_download / remaining_downloads /
        reset_download_if_needed so we never hit MongoDB twice for the
        same check.
        Returns: {"is_premium": bool, "count": int, "remaining": int}
        """
        user_id = int(user_id)
        now = datetime.datetime.now()
        user_data = await self.users.find_one({"id": user_id})

        # ---- Premium check (mirrors has_premium_access logic) ----
        is_premium = False
        if user_data:
            expiry_time = user_data.get("expiry_time")
            if isinstance(expiry_time, datetime.datetime) and datetime.datetime.utcnow() <= (expiry_time.replace(tzinfo=None) if expiry_time.tzinfo is None else expiry_time.astimezone(pytz.utc).replace(tzinfo=None)):
                is_premium = True
            elif expiry_time is not None:
                await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})

        import botcfg
        limit = int(botcfg.get("daily_limit"))

        if is_premium:
            # Unlimited downloads, no need to touch the counters
            return {"is_premium": True, "premium": True, "verified": False, "count": 0, "remaining": limit, "daily_limit": limit}

        # ---- Verified (free access for a few hours after a shortener verification) ----
        vu = user_data.get("verified_until") if user_data else None
        if isinstance(vu, datetime.datetime) and vu > datetime.datetime.utcnow():
            return {"is_premium": True, "premium": False, "verified": True, "count": 0, "remaining": limit, "daily_limit": limit}

        # ---- Free user: resolve / reset the daily counter ----
        count = user_data.get("daily_download_count", 0) if user_data else 0
        last_reset = user_data.get("last_download_reset") if user_data else None

        if not last_reset or (now - last_reset) >= datetime.timedelta(hours=24):
            count = 0
            await self.users.update_one(
                {"id": user_id},
                {"$set": {"daily_download_count": 0, "last_download_reset": now}},
                upsert=True
            )

        remaining = limit - count
        remaining = remaining if remaining > 0 else 0
        return {"is_premium": False, "premium": False, "verified": False, "count": count, "remaining": remaining, "daily_limit": limit}

    async def reset_download_if_needed(self, user_id):
        """Resets the user's daily_download_count to 0 if last_download_reset was >= 24 hours ago."""
        return await self.get_download_status(user_id)

    async def can_download(self, user_id):
        """Returns True if the user (premium or free within limit) is allowed to download a file right now."""
        status = await self.get_download_status(user_id)
        return status["is_premium"] or status["remaining"] > 0

    async def increase_download(self, user_id, count: int = 1):
        """Increments the free user's daily_download_count by `count` (default 1). Call this only AFTER file(s) have been sent. Pass a higher count for bulk/batch downloads to avoid multiple DB round trips."""
        user_id = int(user_id)
        if count <= 0:
            return

        await self.users.update_one(
            {"id": user_id},
            {
                "$inc": {"daily_download_count": count},
                "$setOnInsert": {"last_download_reset": datetime.datetime.now()}
            },
            upsert=True
        )

    async def remaining_downloads(self, user_id):
        """Returns remaining downloads left today for the user. Premium users get DAILY_DOWNLOAD_LIMIT (unlimited)."""
        status = await self.get_download_status(user_id)
        return status["daily_limit"] if status["is_premium"] else status["remaining"]
    
    # Daily Download Limit System function End👆👆
    # =========================================================

    
    async def update_one(self, filter_query, update_data):
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception as e:
            print(f"Error updating document: {e}")
            return False

    async def get_expired(self, current_time):
        expired_users = []
        if data := self.users.find({"expiry_time": {"$lt": current_time}}):
            async for user in data:
                expired_users.append(user)
        return expired_users

    async def remove_premium_access(self, user_id):
        return await self.update_one(
            {"id": user_id}, {"$set": {"expiry_time": None}}
        )

    async def check_trial_status(self, user_id):
        user_data = await self.get_user(user_id)

        if not user_data:
            return False

        trial_claimed_at = user_data.get("trial_claimed_at")

        if not trial_claimed_at:
            return False

        if isinstance(trial_claimed_at, datetime.datetime):
            next_trial_time = trial_claimed_at + datetime.timedelta(days=30)

            if datetime.datetime.now() >= next_trial_time:
                return False

        return True

    async def give_free_trial(self, user_id):
        now = datetime.datetime.now()
        seconds = 5 * 60

        user_data = await self.get_user(user_id)

        if user_data:
            current_expiry = user_data.get("expiry_time")

            if (
                isinstance(current_expiry, datetime.datetime)
                and current_expiry > now
            ):
                return False

        expiry_time = now + datetime.timedelta(seconds=seconds)

        await self.users.update_one(
            {"id": user_id},
            {
                "$set": {
                    "expiry_time": expiry_time,
                    "has_free_trial": True,
                    "trial_claimed_at": now
                }
            },
            upsert=True
        )

        return True

    async def reset_free_trial(self, user_id=None):
        if user_id is None:
            update_data = {
                "$set": {
                    "has_free_trial": False
                },
                "$unset": {
                    "trial_claimed_at": ""
                }
            }
            result = await self.users.update_many({}, update_data)
            return result.modified_count

        else:
            update_data = {
                "$set": {
                    "has_free_trial": False
                },
                "$unset": {
                    "trial_claimed_at": ""
                }
            }
            result = await self.users.update_one(
                {"id": user_id},
                update_data
            )
            return 1 if result.modified_count > 0 else 0

    async def all_premium_users(self):
        count = await self.users.count_documents({
        "expiry_time": {"$gt": datetime.datetime.now()}
        })
        return count

    # ---------- verification (shortener) ----------
    @staticmethod
    def _today_ist():
        return datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')

    async def verify_count_today(self, user_id):
        u = await self.users.find_one({"id": int(user_id)}, {"verify_day": 1, "verify_count": 1})
        if u and u.get("verify_day") == self._today_ist():
            return int(u.get("verify_count", 0))
        return 0

    async def set_pending_start(self, user_id, data):
        await self.users.update_one({"id": int(user_id)}, {"$set": {"pending_start": data}}, upsert=True)

    async def pop_pending_start(self, user_id):
        u = await self.users.find_one_and_update({"id": int(user_id)}, {"$unset": {"pending_start": ""}})
        return u.get("pending_start") if u else None

    async def create_verify_token(self, user_id, token, shortener_id, pending):
        await self.tokens.delete_many({"user_id": int(user_id)})   # one open token per user
        await self.tokens.insert_one({"token": token, "user_id": int(user_id), "sid": shortener_id,
                                      "pending": pending, "created": datetime.datetime.utcnow()})

    async def pop_verify_token(self, token, user_id=None):
        q = {"token": token}
        if user_id is not None:
            q["user_id"] = int(user_id)
        return await self.tokens.find_one_and_delete(q)

    async def complete_verification(self, user_id, hours):
        until = datetime.datetime.utcnow() + datetime.timedelta(hours=float(hours))
        count = await self.verify_count_today(user_id) + 1
        await self.users.update_one(
            {"id": int(user_id)},
            {"$set": {"verified_until": until, "verify_day": self._today_ist(), "verify_count": count}},
            upsert=True)
        return until

    # ---------- user language ----------
    async def set_user_lang(self, user_id, lang):
        await self.col.update_one({'id': int(user_id)}, {'$set': {'lang': lang}})

    async def get_user_lang(self, user_id):
        u = await self.col.find_one({'id': int(user_id)}, {'lang': 1})
        return u.get('lang') if u else None

    async def count_users_by_lang(self):
        """{lang_code or None: users}"""
        out = {}
        async for r in self.col.aggregate([{'$group': {'_id': '$lang', 'n': {'$sum': 1}}}]):
            out[r['_id']] = r['n']
        return out

    async def get_bot_setting(self, bot_id, setting_key, default_value):
        bot = await self.botcol.find_one({'id': int(bot_id)}, {setting_key: 1, '_id': 0})
        return bot[setting_key] if bot and setting_key in bot else default_value

    async def update_bot_setting(self, bot_id, setting_key, value):
        await self.botcol.update_one(
            {'id': int(bot_id)}, 
            {'$set': {setting_key: value}}, 
            upsert=True
        )

    async def connect_group(self, group_id, user_id):
        user= await self.connection.find_one({'_id': user_id})
        if user:
            if group_id not in user["group_ids"]:
                await self.connection.update_one({'_id': user_id}, {"$push": {"group_ids": group_id}})
        else:
            await self.connection.insert_one({'_id': user_id, 'group_ids': [group_id]})

    async def get_connected_grps(self, user_id):
        user = await self.connection.find_one({'_id': user_id})
        if user:
            return user["group_ids"]
        else:
            return []

    async def remove_group_connection(self, group_id, user_id):
        await self.connection.update_one(
            {'_id': user_id},
            {'$pull': {'group_ids': group_id}}
        )

    async def pm_search_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'PM_SEARCH', PM_SEARCH)

    async def update_pm_search_status(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'PM_SEARCH', enable)

    async def movie_update_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'MOVIE_UPDATE_NOTIFICATION', MOVIE_UPDATE_NOTIFICATION)

    async def update_movie_update_status(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'MOVIE_UPDATE_NOTIFICATION', enable)

    # ---------- global FORWARD switch (admin panel) ----------
    async def forward_allowed_status(self, bot_id):
        return await self.get_bot_setting(bot_id, 'FORWARD_ALLOWED', FORWARD_ALLOWED)

    async def update_forward_allowed(self, bot_id, enable):
        await self.update_bot_setting(bot_id, 'FORWARD_ALLOWED', bool(enable))

    # ---------- bulk helpers for group settings (admin panel) ----------
    async def count_group_setting(self, key):
        """(on, off, total). Groups without saved settings count by the default value."""
        default = (await self.get_settings(0)).get(key)
        total = await self.grp.count_documents({})
        with_settings = await self.grp.count_documents({'settings': {'$exists': True}})
        on = await self.grp.count_documents({f'settings.{key}': True})
        off = await self.grp.count_documents({f'settings.{key}': False})
        no_settings = total - with_settings
        if default:
            on += no_settings
        else:
            off += no_settings
        return on, off, total

    async def set_setting_all_groups(self, key, value):
        """Set one setting for EVERY group (groups without saved settings get defaults + this key)."""
        r1 = await self.grp.update_many({'settings': {'$exists': True}}, {'$set': {f'settings.{key}': value}})
        default = await self.get_settings(0)
        default[key] = value
        r2 = await self.grp.update_many({'settings': {'$exists': False}}, {'$set': {'settings': default}})
        return r1.modified_count + r2.modified_count

db = Database(DATABASE_URI, DATABASE_NAME)    
db2 = Database(DATABASE_URI2, DATABASE_NAME)
