"""
ADMIN SETTINGS  (/admin -> ⚙️ Settings)   callback prefix: adc#
  Limits       : daily limit, auto-delete extra minutes (free / premium), fallback time, forward lock
  Verification : on/off, access hours, min seconds, shorteners (add / on-off / tutorial / delete)
Values are saved in MongoDB through botcfg and apply immediately (no restart).
"""
import re
import uuid

from pyrogram import Client, filters, StopPropagation
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
from info import ADMINS

PENDING = {}   # admin_id -> {"kind": ..., ...}

# key -> (label, unit, min, max)
NUM = {
    "daily_limit": ("Daily free files", "files", 1, 1000),
    "delete_extra_min": ("Extra delete time (free/verified)", "min", 0, 1440),
    "delete_extra_min_premium": ("Extra delete time (premium)", "min", 0, 10080),
    "delete_fallback_sec": ("Delete time if length unknown (free)", "sec", 30, 86400),
    "delete_fallback_sec_premium": ("Delete time if length unknown (premium)", "sec", 30, 604800),
    "group_cmd_delete_sec": ("Group: delete /command after", "sec", 5, 3600),
    "verify_hours": ("Access after verification", "hours", 1, 720),
    "verify_min_seconds": ("Minimum verify time (anti-bypass)", "sec", 0, 600),
}


def _onoff(v):
    return "✅ ON" if v else "❌ OFF"


async def _edit(msg, text, kb):
    try:
        await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass


def _home():
    text = ("<b>⚙️ BOT SETTINGS</b>\n\n"
            "<b>📦 Limits</b> — daily files, auto-delete, forward lock\n"
            "<b>🔓 Verification</b> — shorteners, access hours\n"
            "<b>💎 Premium</b> — plans, payment, pending\n"
            "<b>🫂 Refer</b> — refer & earn rules\n\n"
            "<b>Choose a section 👇</b>")
    kb = M([[B("📦 Limits", callback_data="adc#lim"), B("🔓 Verification", callback_data="adc#ver")],
            [B("💎 Premium", callback_data="adp#home"), B("🫂 Refer", callback_data="adp#ref")],
            [B("⬅️ Back", callback_data="adm#home"), B("❌ Close", callback_data="adm#close")]])
    return text, kb


def _lim():
    g = botcfg.get
    text = (
        "<b>📦 LIMITS & AUTO-DELETE</b>\n\n"
        f"<b>📥 Daily free files:</b> {g('daily_limit')}\n"
        f"<b>⏳ Free/verified delete:</b> movie length + {g('delete_extra_min')} min\n"
        f"<b>💎 Premium delete:</b> movie length + {g('delete_extra_min_premium')} min\n"
        f"<b>❓ Length unknown:</b> free {g('delete_fallback_sec')}s • premium {g('delete_fallback_sec_premium')}s\n"
        f"<b>🔒 Forward lock for free users:</b> {_onoff(g('lock_free_forward'))}\n"
        f"<b>🧹 Group /command@bot delete:</b> {_onoff(g('group_cmd_delete'))} after {g('group_cmd_delete_sec')}s\n\n"
        "<b>Tap to edit 👇</b>"
    )
    kb = M([
        [B("📥 Daily limit", callback_data="adc#set#daily_limit"),
         B("⏳ Free delete", callback_data="adc#set#delete_extra_min")],
        [B("💎 Premium delete", callback_data="adc#set#delete_extra_min_premium")],
        [B("❓ Unknown (free)", callback_data="adc#set#delete_fallback_sec"),
         B("❓ Unknown (prem)", callback_data="adc#set#delete_fallback_sec_premium")],
        [B(f"🔒 Forward lock: {_onoff(g('lock_free_forward'))}", callback_data="adc#t#lock_free_forward")],
        [B(f"🧹 Group cmd delete: {_onoff(g('group_cmd_delete'))}", callback_data="adc#t#group_cmd_delete"),
         B("⏱ Delay", callback_data="adc#set#group_cmd_delete_sec")],
        [B("⬅️ Back", callback_data="adc#home"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _ver():
    g = botcfg.get
    shs = g("shorteners")
    lines = "\n".join(f"{i}. {'✅' if s.get('on') else '❌'} {s['site']}" for i, s in enumerate(shs, 1)) or "—"
    text = (
        "<b>🔓 VERIFICATION</b>\n\n"
        f"<b>Status:</b> {_onoff(g('verify_on'))}\n"
        f"<b>⏰ Access after verify:</b> {g('verify_hours')} hours\n"
        f"<b>🛡 Min verify time:</b> {g('verify_min_seconds')} sec\n\n"
        f"<b>🔗 Shorteners ({len(shs)}):</b>\n{lines}\n\n"
        "<b>ℹ️ Same-day 2nd verification uses the next shortener.</b>"
    )
    rows = [[B(f"Verification: {_onoff(g('verify_on'))}", callback_data="adc#t#verify_on")],
            [B("⏰ Hours", callback_data="adc#set#verify_hours"),
             B("🛡 Min time", callback_data="adc#set#verify_min_seconds")]]
    for i, s in enumerate(shs, 1):
        rows.append([B(f"{'✅' if s.get('on') else '❌'} {i}. {s['site']}"[:60], callback_data=f"adc#sh#{s['id']}")])
    rows.append([B("➕ Add shortener", callback_data="adc#shadd")])
    rows.append([B("⬅️ Back", callback_data="adc#home"), B("❌ Close", callback_data="adm#close")])
    return text, M(rows)


def _sh(sid):
    s = next((x for x in botcfg.get("shorteners") if x["id"] == sid), None)
    if not s:
        return None, None
    key = s["api"]
    masked = (key[:4] + "••••" + key[-3:]) if len(key) > 8 else "••••"
    text = (
        "<b>🔗 SHORTENER</b>\n\n"
        f"<b>🌐 Site:</b> {s['site']}\n"
        f"<b>🔑 API:</b> <code>{masked}</code>\n"
        f"<b>🎬 Tutorial:</b> {s.get('tutorial') or '—'}\n"
        f"<b>Status:</b> {_onoff(s.get('on'))}"
    )
    kb = M([
        [B(f"{'❌ Turn OFF' if s.get('on') else '✅ Turn ON'}", callback_data=f"adc#sht#{sid}")],
        [B("🎬 Edit tutorial", callback_data=f"adc#sht_ed#{sid}"),
         B("🗑 Delete", callback_data=f"adc#shdel#{sid}")],
        [B("⬅️ Back", callback_data="adc#ver"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _cancel_kb(back):
    return M([[B("🚫 Cancel", callback_data=f"adc#cancel#{back}")]])


@Client.on_callback_query(filters.regex(r"^adc#"))
async def adc_cb(client, query):
    if not query.from_user or query.from_user.id not in ADMINS:
        return await query.answer("Only bot admins can use this.", show_alert=True)
    uid = query.from_user.id
    p = query.data.split("#")
    act = p[1]
    arg = p[2] if len(p) > 2 else None
    msg = query.message
    import sys
    _ap = sys.modules.get('plugins.admin_premium')
    if _ap:
        _ap.PENDING.pop(uid, None)

    if act in ("home", "lim", "ver"):
        PENDING.pop(uid, None)
        await query.answer()
        text, kb = {"home": _home, "lim": _lim, "ver": _ver}[act]()
        return await _edit(msg, text, kb)

    if act == "cancel":
        PENDING.pop(uid, None)
        await query.answer("Cancelled")
        text, kb = {"lim": _lim, "ver": _ver}.get(arg, _home)()
        return await _edit(msg, text, kb)

    if act == "t":
        if arg not in ("lock_free_forward", "verify_on", "group_cmd_delete"):
            return await query.answer("Unknown", show_alert=True)
        new = not botcfg.get(arg)
        await botcfg.set(arg, new)
        await query.answer(_onoff(new))
        text, kb = _ver() if arg == "verify_on" else _lim()
        return await _edit(msg, text, kb)

    if act == "set":
        if arg not in NUM:
            return await query.answer("Unknown", show_alert=True)
        label, unit, lo, hi = NUM[arg]
        back = "ver" if arg.startswith("verify") else "lim"
        PENDING[uid] = {"kind": "num", "key": arg, "back": back, "msg": msg}
        await query.answer()
        return await _edit(msg, f"<b>✏️ {label}</b>\n\n<b>Current:</b> {botcfg.get(arg)} {unit}\n"
                                f"<b>Send a new number ({lo}-{hi}) 👇</b>", _cancel_kb(back))

    if act == "shadd":
        PENDING[uid] = {"kind": "sh_site", "msg": msg}
        await query.answer()
        return await _edit(msg, "<b>➕ ADD SHORTENER</b>\n\n<b>Step 1/3 — send the site</b>\n"
                                "<b>Example:</b> <code>gplinks.com</code>", _cancel_kb("ver"))

    if act == "sh":
        text, kb = _sh(arg)
        await query.answer()
        if not text:
            text, kb = _ver()
        return await _edit(msg, text, kb)

    if act in ("sht", "shdel", "sht_ed"):
        lst = botcfg.get("shorteners")
        s = next((x for x in lst if x["id"] == arg), None)
        if not s:
            await query.answer("Not found", show_alert=True)
            text, kb = _ver()
            return await _edit(msg, text, kb)
        if act == "sht":
            s["on"] = not s.get("on")
            await botcfg.set("shorteners", lst)
            await query.answer(_onoff(s["on"]))
            text, kb = _sh(arg)
            return await _edit(msg, text, kb)
        if act == "shdel":
            await botcfg.set("shorteners", [x for x in lst if x["id"] != arg])
            await query.answer("Deleted 🗑")
            text, kb = _ver()
            return await _edit(msg, text, kb)
        PENDING[uid] = {"kind": "sh_tut_edit", "id": arg, "msg": msg}
        await query.answer()
        return await _edit(msg, "<b>🎬 Send the tutorial link</b>\n<b>Send</b> <code>-</code> <b>to remove it.</b>",
                           _cancel_kb("ver"))


@Client.on_message(filters.private & filters.user(ADMINS) & filters.text & ~filters.regex(r"^/"), group=-5)
async def adc_input(client, message):
    uid = message.from_user.id
    st = PENDING.get(uid)
    if not st:
        return   # not for us -> normal handlers continue
    txt = message.text.strip()
    kind = st["kind"]
    msg = st["msg"]

    async def show(text, kb):
        await message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)

    if kind == "num":
        label, unit, lo, hi = NUM[st["key"]]
        if not txt.isdigit() or not (lo <= int(txt) <= hi):
            await message.reply_text(f"<b>❌ Send a number between {lo} and {hi}.</b>")
            raise StopPropagation
        await botcfg.set(st["key"], int(txt))
        PENDING.pop(uid, None)
        text, kb = _ver() if st["back"] == "ver" else _lim()
        await show(f"<b>✅ {label} = {txt} {unit}</b>\n\n" + text, kb)

    elif kind == "sh_site":
        site = re.sub(r"^https?://", "", txt).strip("/ ").lower()
        if "." not in site or " " in site:
            await message.reply_text("<b>❌ Send a valid site like</b> <code>gplinks.com</code>")
            raise StopPropagation
        st.update(kind="sh_api", site=site)
        await show("<b>Step 2/3 — send the API key</b>", _cancel_kb("ver"))

    elif kind == "sh_api":
        st.update(kind="sh_tut", api=txt)
        try:
            await message.delete()   # do not leave the API key in the chat
        except Exception:
            pass
        await show("<b>Step 3/3 — send the tutorial link</b>\n<b>Send</b> <code>-</code> <b>to skip.</b>",
                   _cancel_kb("ver"))

    elif kind in ("sh_tut", "sh_tut_edit"):
        tut = "" if txt == "-" else txt
        if tut and not tut.startswith("http"):
            await message.reply_text("<b>❌ Send a link starting with http, or</b> <code>-</code>")
            raise StopPropagation
        lst = botcfg.get("shorteners")
        if kind == "sh_tut":
            lst.append({"id": uuid.uuid4().hex[:8], "site": st["site"], "api": st["api"],
                        "tutorial": tut, "on": True})
            done = "<b>✅ Shortener added & ON</b>"
        else:
            for x in lst:
                if x["id"] == st["id"]:
                    x["tutorial"] = tut
            done = "<b>✅ Tutorial updated</b>"
        await botcfg.set("shorteners", lst)
        PENDING.pop(uid, None)
        text, kb = _ver()
        await show(done + "\n\n" + text, kb)
    raise StopPropagation
