"""
Runtime settings editable from /admin (saved in MongoDB, cached in memory).
    botcfg.get("daily_limit")          -> value (default from DEFAULTS)
    await botcfg.set("daily_limit", 5) -> saved + cache updated
Plain module (not a plugin) so there is exactly ONE shared cache.
"""
import copy
from info import DELETE_TIME, OWNER_UPI_ID, QR_CODE

CFG_ID = -1   # document id in the bot_settings collection

DEFAULTS = {
    "daily_limit": 3,                 # free files per 24h
    "delete_extra_min": 15,           # free/verified: file length + this many minutes
    "delete_extra_min_premium": 45,   # premium: file length + this many minutes
    "delete_fallback_sec": DELETE_TIME,        # when file length is unknown (documents)
    "delete_fallback_sec_premium": 1800,
    "lock_free_forward": True,        # True = free (unverified) users cannot forward/save files
    "verify_on": True,
    "verify_hours": 3,                # access after one verification
    "verify_min_seconds": 20,         # faster than this = bypass attempt
    "shorteners": [],                 # [{id, site, api, tutorial, on}]
    "premium_on": True,               # False = Premium button shows "not available"
    "plans": [                        # days, price (INR), on, badge
        {"id": "p7",   "days": 7,   "price": 29,  "on": True, "badge": ""},
        {"id": "p15",  "days": 15,  "price": 45,  "on": True, "badge": ""},
        {"id": "p30",  "days": 30,  "price": 59,  "on": True, "badge": ""},
        {"id": "p90",  "days": 90,  "price": 149, "on": True, "badge": "🔥"},
        {"id": "p180", "days": 180, "price": 269, "on": True, "badge": ""},
        {"id": "p365", "days": 365, "price": 449, "on": True, "badge": "👑"},
    ],
    "pay_methods": [                  # type: upi (value = UPI id) | qr (value = photo file_id or image URL)
        {"id": "upi0", "type": "upi", "value": OWNER_UPI_ID, "on": True},
        {"id": "qr0",  "type": "qr",  "value": QR_CODE,       "on": True},
    ],
    "fsub_channels": [],              # extra force-sub channel ids (added from /admin)
    "refer_on": True,
    "refer_need": 2,                  # qualified friends needed for one reward
    "refer_days": 1,                  # premium days per reward
}

_cfg = {}


def get(key):
    return copy.deepcopy(_cfg[key] if key in _cfg else DEFAULTS[key])


async def set(key, value):
    from database.users_chats_db import db
    _cfg[key] = value
    await db.botcol.update_one({"id": CFG_ID}, {"$set": {f"cfg.{key}": value}}, upsert=True)


async def load():
    from database.users_chats_db import db
    doc = await db.botcol.find_one({"id": CFG_ID})
    _cfg.clear()
    _cfg.update((doc or {}).get("cfg", {}))
