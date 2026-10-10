"""My Account / Preferences / My Downloads (helpers + screens). Handlers: plugins/account_flow.py"""
import datetime
import re

import pytz
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
import payments
from database.users_chats_db import db
from languages import LANG_NAMES, btn, get_lang, tr
from utils import temp

IST = pytz.timezone("Asia/Kolkata")
HTML = enums.ParseMode.HTML
QUALITIES = ["480p", "720p", "1080p", "4K"]
LANGS_PREF = ["Hindi", "English", "Tamil", "Telugu", "Kannada", "Malayalam"]
Q_RX = re.compile(r"\b(480p|576p|720p|1080p|1440p|2160p|4k|8k)\b", re.I)
L_RX = re.compile(r"\b(hindi|english|tamil|telugu|kannada|malayalam|bengali|punjabi|marathi|gujarati|dual|multi)\b", re.I)
hist = db.db["dl_history"]


# ---------------- preferences ----------------
async def get_prefs(uid):
    u = await db.col.find_one({"id": int(uid)}, {"pref_q": 1, "pref_l": 1}) or {}
    return u.get("pref_q"), u.get("pref_l")


async def set_pref(uid, field, value):
    await db.col.update_one({"id": int(uid)}, {"$set": {field: value}})


async def apply_pref(uid, search):
    """Search text + the user's preferred quality/language (only when he did not type his own)."""
    if not uid:
        return search
    q, l = await get_prefs(uid)
    out = search
    if q and not Q_RX.search(search):
        out += f" {q.lower()}"
    if l and not L_RX.search(search):
        out += f" {l.lower()}"
    return out


# ---------------- download history ----------------
async def record(uid, ref, name):
    if not ref:
        return
    await hist.delete_many({"uid": int(uid), "ref": ref})
    await hist.insert_one({"uid": int(uid), "ref": ref, "name": (name or "File")[:80],
                           "at": datetime.datetime.utcnow()})
    old = [d["_id"] async for d in hist.find({"uid": int(uid)}).sort("at", -1).skip(10)]
    if old:
        await hist.delete_many({"_id": {"$in": old}})


# ---------------- screens ----------------
def _fmt(dt):
    return pytz.utc.localize(dt).astimezone(IST).strftime("%d %b, %I:%M %p")


async def account_screen(uid, lang):
    st = await db.get_download_status(uid)
    u = await db.col.find_one({"id": int(uid)}, {"verified_until": 1}) or {}
    exp = await payments.get_expiry(uid)
    if exp:
        plan, left = tr("acc_premium", lang, until=_fmt(exp)), tr("acc_unlimited", lang)
    elif st.get("verified"):
        plan, left = tr("acc_verified", lang, until=_fmt(u["verified_until"])), tr("acc_unlimited", lang)
    else:
        plan, left = tr("acc_free", lang), f"{st['remaining']}/{st['daily_limit']}"
    rs = await payments.refer_stats(uid)
    q, l = await get_prefs(uid)
    anyl = tr("any_label", lang)
    text = tr("acc_text", lang, uid=uid, plan=plan, left=left, prog=rs["progress"], need=botcfg.get("refer_need"),
              lang_name=LANG_NAMES.get(lang, lang), pref=f"{q or anyl} • {l or anyl}")
    kb = M([[B(btn("btn_prefs", lang), callback_data="acc#pref"), B(btn("btn_downloads", lang), callback_data="acc#dl")],
            [B(btn("btn_premium", lang), callback_data="premium_info"), B(btn("btn_refer", lang), callback_data="pr#ref")],
            [B(btn("btn_language", lang), callback_data="lang_menu")],
            [B(btn("btn_back_home", lang), callback_data="start"), B(btn("btn_close", lang), callback_data="pr#close")]])
    return text, kb


async def pref_screen(uid, lang):
    q, l = await get_prefs(uid)
    anyl = tr("any_label", lang)
    text = tr("pref_text", lang, q=q or anyl, l=l or anyl)

    def b(label, field, cur):
        mark = "✅ " if cur == label else ""
        return B(f"{mark}{label}", callback_data=f"acc#set#{field}#{label}")

    rows = [[B(("✅ " if not q else "") + anyl, callback_data="acc#set#q#-")] + [b(x, "q", q) for x in QUALITIES[:2]],
            [b(x, "q", q) for x in QUALITIES[2:]],
            [B(("✅ " if not l else "") + anyl, callback_data="acc#set#l#-")] + [b(x, "l", l) for x in LANGS_PREF[:2]],
            [b(x, "l", l) for x in LANGS_PREF[2:5]],
            [b(x, "l", l) for x in LANGS_PREF[5:]],
            [B(btn("btn_back", lang), callback_data="acc#home"), B(btn("btn_close", lang), callback_data="pr#close")]]
    return text, M(rows)


async def downloads_screen(uid, lang):
    rows_db = [d async for d in hist.find({"uid": int(uid)}).sort("at", -1).limit(10)]
    back = [B(btn("btn_back", lang), callback_data="acc#home"), B(btn("btn_close", lang), callback_data="pr#close")]
    if not rows_db:
        return tr("dl_empty", lang), M([back])
    rows = [[B(f"🎬 {d['name']}"[:48], url=f"https://t.me/{temp.U_NAME}?start=file_0_{d['ref']}")] for d in rows_db]
    return tr("dl_text", lang), M(rows + [back])
