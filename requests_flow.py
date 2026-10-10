"""
Movie requests: ONE card per movie in the request channel; every extra user is added to the same card.
Admin taps a result button -> the card is closed and EVERY requester gets a message (in his language).
"""
import asyncio
import datetime
import hashlib
import logging
import re

import pytz
from pymongo.errors import DuplicateKeyError
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import stats
from database.users_chats_db import db
from info import ADMINS, REQST_CHANNEL
from languages import tr, btn, get_lang
from utils import temp

logger = logging.getLogger(__name__)
col = db.db["movie_requests"]
IST = pytz.timezone("Asia/Kolkata")
HTML = enums.ParseMode.HTML
NOISE = {"movie", "movies", "full", "hd", "download", "please", "plz", "pls", "send", "new", "480p", "720p", "1080p", "free"}
STATUS = {  # code -> (db status, header on the card, message key)
    "up": ("uploaded", "✅ UPLOADED", "req_up"),
    "al": ("available", "♻️ ALREADY AVAILABLE", "req_al"),
    "un": ("unavailable", "⚠️ UNAVAILABLE", "req_un"),
    "nr": ("not_released", "📌 NOT RELEASED", "req_nr"),
    "ws": ("wrong_spelling", "♨️ WRONG SPELLING", "req_ws"),
}
_titles = {}   # token -> title (for the "Request" button on the not-found message)
_indexed = False


def make_token(title):
    tok = hashlib.md5(title.lower().encode()).hexdigest()[:10]
    if len(_titles) > 5000:
        _titles.clear()
    _titles[tok] = title.strip()[:100]
    return tok


def title_of(tok):
    return _titles.get(tok)


def key_of(title):
    words = [w for w in stats.clean_query(title).split() if w not in NOISE]
    return " ".join(sorted(words))


async def _ensure_index():
    global _indexed
    if not _indexed:
        try:
            await col.create_index("key", unique=True, partialFilterExpression={"status": "open"})
            _indexed = True
        except Exception as e:
            logger.warning(f"request index: {e}")


def card_text(doc, header=None):
    users = doc["users"]
    shown = "\n".join(f"{i}. {u['name']} <code>{u['id']}</code>" for i, u in enumerate(users[:15], 1))
    more = f"\n… +{len(users) - 15} more" if len(users) > 15 else ""
    when = pytz.utc.localize(doc["created"]).astimezone(IST).strftime("%d %b, %I:%M %p")
    head = f"<b>{header}</b>\n" if header else ""
    return (f"{head}<b>🎬 REQUEST:</b> <code>{doc['title']}</code>\n<b>━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>👥 Requested by ({len(users)}):</b>\n{shown}{more}\n\n"
            f"<b>🕒 First request:</b> {when}\n<b>📍 From:</b> {doc.get('source', '—')}\n\n<b>#request</b>")


def card_kb(doc):
    r = doc["rid"]
    return M([[B("✅ Uploaded", callback_data=f"rq#up#{r}"), B("⚠️ Unavailable", callback_data=f"rq#un#{r}")],
              [B("📌 Not released", callback_data=f"rq#nr#{r}"), B("♨️ Wrong spelling", callback_data=f"rq#ws#{r}")],
              [B("♻️ Already available", callback_data=f"rq#al#{r}")]])


async def submit(client, user, title, source="PM"):
    """-> 'new' | 'joined' | 'already' | 'invalid'"""
    key = key_of(title)
    if len(key) < 2:
        return "invalid"
    await _ensure_index()
    entry = {"id": user.id, "name": (user.first_name or "User")[:25]}
    for _ in range(2):
        doc = await col.find_one({"key": key, "status": "open"})
        if doc:
            if any(u["id"] == user.id for u in doc["users"]):
                return "already"
            await col.update_one({"_id": doc["_id"]}, {"$push": {"users": entry}})
            doc["users"].append(entry)
            await _refresh(client, doc)
            return "joined"
        doc = {"rid": hashlib.md5(f"{key}{datetime.datetime.utcnow()}".encode()).hexdigest()[:10], "key": key,
               "title": title.strip()[:100], "users": [entry], "status": "open",
               "created": datetime.datetime.utcnow(), "source": source}
        try:
            await col.insert_one(doc)
        except DuplicateKeyError:
            continue                      # somebody created it a moment ago -> join that card
        await _post_card(client, doc)
        return "new"
    return "already"


async def _post_card(client, doc):
    targets = [REQST_CHANNEL] if REQST_CHANNEL else list(ADMINS)
    for chat in targets:
        try:
            m = await client.send_message(chat, card_text(doc), reply_markup=card_kb(doc), parse_mode=HTML)
            await col.update_one({"rid": doc["rid"]}, {"$push": {"cards": [m.chat.id, m.id]}})
        except Exception as e:
            logger.warning(f"request card to {chat}: {e}")


async def _refresh(client, doc, header=None, kb=True):
    for chat, mid in doc.get("cards", []):
        try:
            await client.edit_message_text(chat, mid, card_text(doc, header), parse_mode=HTML,
                                           reply_markup=card_kb(doc) if kb else None)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" not in str(e).upper():
                logger.debug(f"card edit: {e}")


async def close(client, rid, code, admin_mention):
    """Admin decision. Returns the doc or None (already handled)."""
    status, header, key = STATUS[code]
    doc = await col.find_one_and_update({"rid": rid, "status": "open"},
                                        {"$set": {"status": status, "closed": datetime.datetime.utcnow()}},
                                        return_document=True)
    if not doc:
        return None
    await _refresh(client, doc, header=f"{header} • by {admin_mention}", kb=False)
    asyncio.create_task(_notify(client, doc, code))
    return doc


async def _notify(client, doc, code):
    _, _, key = STATUS[code]
    slug = re.sub(r"[^\w]+", "-", doc["title"]).strip("-")
    for u in doc["users"]:
        lang = await get_lang(u["id"])
        kb = None
        if code in ("up", "al"):
            kb = M([[B(btn("btn_search_now", lang), url=f"https://t.me/{temp.U_NAME}?start=getfile-{slug}")]])
        try:
            await client.send_message(u["id"], tr(key, lang, title=doc["title"]), reply_markup=kb, parse_mode=HTML)
        except Exception:
            pass
        await asyncio.sleep(0.1)
