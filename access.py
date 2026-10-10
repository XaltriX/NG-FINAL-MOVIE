"""Who may forward / how long files live. One place, used by every file-sending path."""
import botcfg
from database.users_chats_db import db


def policy_from_status(st):
    premium = bool(st.get("premium"))
    verified = bool(st.get("verified"))
    free = not (premium or verified)
    lock = bool(botcfg.get("lock_free_forward"))
    return {
        "premium": premium,
        "verified": verified,
        "free": free,
        "can_forward": (not free) or (not lock),
        "protect": free and lock,               # Telegram "noforwards"
    }


async def get_policy(user_id):
    return policy_from_status(await db.get_download_status(user_id))


def media_duration(msg):
    for attr in ("video", "audio", "animation", "video_note", "voice"):
        m = getattr(msg, attr, None)
        d = getattr(m, "duration", None) if m else None
        if d:
            return int(d)
    return 0


def delete_seconds(policy, duration):
    """movie length + extra minutes (premium gets more). Unknown length -> fallback."""
    if policy["premium"]:
        extra, fallback = botcfg.get("delete_extra_min_premium"), botcfg.get("delete_fallback_sec_premium")
    else:
        extra, fallback = botcfg.get("delete_extra_min"), botcfg.get("delete_fallback_sec")
    return int(duration) + int(extra) * 60 if duration else int(fallback)
