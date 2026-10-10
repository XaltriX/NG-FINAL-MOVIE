"""
ADMIN: Premium + Refer settings   (/admin -> ⚙️ Settings -> 💎 Premium / 🫂 Refer)   callback prefix: adp#
  plans (price / days / badge / on-off / add / delete), payment methods (UPI id, QR photo: add / on-off / delete),
  pending payments, premium on/off, refer on/off + numbers.
"""
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
import payments
from database.users_chats_db import db
from info import ADMINS

PENDING = {}   # admin_id -> state


def _onoff(v):
    return "✅ ON" if v else "❌ OFF"


async def _edit(msg, text, kb):
    try:
        await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception:
        await msg.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


def _dur(d):
    from premium_ui import fmt_dur
    return fmt_dur(d, "en")


async def _home():
    pend = await payments.pending_count()
    active = await db.all_premium_users()
    text = (
        "<b>💎 PREMIUM SETTINGS</b>\n\n"
        f"<b>Status:</b> {_onoff(botcfg.get('premium_on'))}\n"
        f"<b>👑 Active premium users:</b> {active}\n"
        f"<b>⏳ Pending payments:</b> {pend}\n\n"
        "<b>Choose 👇</b>"
    )
    kb = M([
        [B(f"Premium: {_onoff(botcfg.get('premium_on'))}", callback_data="adp#t#premium_on")],
        [B("📦 Plans & prices", callback_data="adp#plans"), B("💳 Payment methods", callback_data="adp#pm")],
        [B(f"⏳ Pending ({pend})", callback_data="adp#pend"), B("🫂 Refer", callback_data="adp#ref")],
        [B("⬅️ Back", callback_data="adc#home"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _plans():
    ps = botcfg.get("plans")
    lines = "\n".join(
        f"{'✅' if p.get('on') else '❌'} {p.get('badge') or ''} <b>{_dur(p['days'])}</b> — ₹{p['price']}" for p in ps) or "—"
    text = f"<b>📦 PLANS</b>\n\n{lines}\n\n<b>Tap a plan to edit 👇</b>"
    rows, row = [], []
    for p in ps:
        row.append(B(f"{'✅' if p.get('on') else '❌'} {_dur(p['days'])} • ₹{p['price']}", callback_data=f"adp#pl#{p['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([B("➕ Add plan", callback_data="adp#pladd")])
    rows.append([B("⬅️ Back", callback_data="adp#home"), B("❌ Close", callback_data="adm#close")])
    return text, M(rows)


def _plan(pid):
    p = next((x for x in botcfg.get("plans") if x["id"] == pid), None)
    if not p:
        return None, None
    text = (f"<b>📦 {_dur(p['days'])}</b>\n\n<b>💰 Price:</b> ₹{p['price']}\n<b>📅 Days:</b> {p['days']}\n"
            f"<b>🏷 Badge:</b> {p.get('badge') or '—'}\n<b>Status:</b> {_onoff(p.get('on'))}")
    kb = M([
        [B("❌ Turn OFF" if p.get("on") else "✅ Turn ON", callback_data=f"adp#plt#{pid}")],
        [B("💰 Price", callback_data=f"adp#ple#price#{pid}"), B("📅 Days", callback_data=f"adp#ple#days#{pid}")],
        [B("🏷 Badge", callback_data=f"adp#ple#badge#{pid}"), B("🗑 Delete", callback_data=f"adp#pld#{pid}")],
        [B("⬅️ Back", callback_data="adp#plans"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _methods():
    ms = botcfg.get("pay_methods")
    lines = "\n".join(
        f"{'✅' if m.get('on') else '❌'} {'📲 UPI' if m['type'] == 'upi' else '🖼 QR'} — "
        f"{m['value'] if m['type'] == 'upi' else '(image)'}" for m in ms) or "—"
    text = ("<b>💳 PAYMENT METHODS</b>\n\n" + lines +
            "\n\n<b>Users see every method that is ON on the pay screen (first QR + all UPI ids).</b>")
    rows = [[B(f"{'✅' if m.get('on') else '❌'} {'UPI ' + m['value'] if m['type'] == 'upi' else 'QR ' + m['id']}"[:60],
               callback_data=f"adp#m#{m['id']}")] for m in ms]
    rows.append([B("➕ UPI ID", callback_data="adp#madd#upi"), B("➕ QR code", callback_data="adp#madd#qr")])
    rows.append([B("⬅️ Back", callback_data="adp#home"), B("❌ Close", callback_data="adm#close")])
    return text, M(rows)


def _method(mid):
    m = next((x for x in botcfg.get("pay_methods") if x["id"] == mid), None)
    if not m:
        return None, None
    text = (f"<b>{'📲 UPI ID' if m['type'] == 'upi' else '🖼 QR CODE'}</b>\n\n"
            f"{('<code>' + m['value'] + '</code>') if m['type'] == 'upi' else '(image)'}\n"
            f"<b>Status:</b> {_onoff(m.get('on'))}")
    kb = M([
        [B("❌ Turn OFF" if m.get("on") else "✅ Turn ON", callback_data=f"adp#mt#{mid}")],
        [B("🗑 Delete", callback_data=f"adp#md#{mid}")],
        [B("⬅️ Back", callback_data="adp#pm"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _refer():
    g = botcfg.get
    text = (
        "<b>🫂 REFER & EARN</b>\n\n"
        f"<b>Status:</b> {_onoff(g('refer_on'))}\n"
        f"<b>👥 Friends needed:</b> {g('refer_need')}\n"
        f"<b>🎁 Reward:</b> {_dur(g('refer_days'))} premium\n\n"
        "<b>ℹ️ A friend counts only if he is a NEW user and gets at least one file.</b>"
    )
    kb = M([
        [B(f"Refer: {_onoff(g('refer_on'))}", callback_data="adp#t#refer_on")],
        [B("👥 Friends needed", callback_data="adp#rn#refer_need"), B("🎁 Reward days", callback_data="adp#rn#refer_days")],
        [B("⬅️ Back", callback_data="adp#home"), B("❌ Close", callback_data="adm#close")],
    ])
    return text, kb


def _cancel(back):
    return M([[B("🚫 Cancel", callback_data=f"adp#{back}")]])


@Client.on_callback_query(filters.regex(r"^adp#"))
async def adp_cb(client, query):
    if not query.from_user or query.from_user.id not in ADMINS:
        return await query.answer("Only bot admins can use this.", show_alert=True)
    uid = query.from_user.id
    p = query.data.split("#")
    act = p[1]
    a = p[2] if len(p) > 2 else None
    b = p[3] if len(p) > 3 else None
    msg = query.message
    PENDING.pop(uid, None)
    import sys
    _ac = sys.modules.get('plugins.admin_config')
    if _ac:
        _ac.PENDING.pop(uid, None)

    if act == "home":
        await query.answer()
        text, kb = await _home()
        return await _edit(msg, text, kb)
    if act == "plans":
        await query.answer()
        text, kb = _plans()
        return await _edit(msg, text, kb)
    if act == "pm":
        await query.answer()
        text, kb = _methods()
        return await _edit(msg, text, kb)
    if act == "ref":
        await query.answer()
        text, kb = _refer()
        return await _edit(msg, text, kb)

    if act == "t":
        if a not in ("premium_on", "refer_on"):
            return await query.answer("Unknown", show_alert=True)
        new = not botcfg.get(a)
        await botcfg.set(a, new)
        await query.answer(_onoff(new))
        text, kb = await _home() if a == "premium_on" else _refer()
        return await _edit(msg, text, kb)

    if act == "pend":
        rows = await payments.pending_list()
        if not rows:
            return await query.answer("No pending payments ✅", show_alert=True)
        await query.answer(f"Sending {len(rows)} request(s)…")
        from plugins.premium_flow import send_admin_card
        for d in rows:
            try:
                m = await send_admin_card(client, uid, d)
                await payments.req_col.update_one({"rid": d["rid"]},
                                                  {"$set": {"admin_msgs": d.get("admin_msgs", []) + [[m.chat.id, m.id]]}})
            except Exception:
                pass
        return

    # ---- plans ----
    if act in ("pl", "plt", "pld"):
        plans = botcfg.get("plans")
        pl = next((x for x in plans if x["id"] == a), None)
        if not pl:
            await query.answer("Not found", show_alert=True)
            text, kb = _plans()
            return await _edit(msg, text, kb)
        if act == "plt":
            pl["on"] = not pl.get("on")
            await botcfg.set("plans", plans)
            await query.answer(_onoff(pl["on"]))
        elif act == "pld":
            await botcfg.set("plans", [x for x in plans if x["id"] != a])
            await query.answer("Deleted 🗑")
            text, kb = _plans()
            return await _edit(msg, text, kb)
        else:
            await query.answer()
        text, kb = _plan(a)
        return await _edit(msg, text, kb)

    if act == "ple":    # edit price/days/badge: adp#ple#<field>#<id>
        field, pid = a, b
        PENDING[uid] = {"kind": "plan_edit", "field": field, "id": pid, "msg": msg}
        hint = {"price": "a new price in ₹ (number)", "days": "number of days (number)",
                "badge": "an emoji badge like 🔥 (or - for none)"}[field]
        await query.answer()
        return await _edit(msg, f"<b>✏️ Send {hint} 👇</b>", _cancel(f"pl#{pid}"))

    if act == "pladd":
        PENDING[uid] = {"kind": "plan_add_days", "msg": msg}
        await query.answer()
        return await _edit(msg, "<b>➕ NEW PLAN</b>\n\n<b>Step 1/2 — how many days?</b> (number)", _cancel("plans"))

    # ---- payment methods ----
    if act in ("m", "mt", "md"):
        ms = botcfg.get("pay_methods")
        m = next((x for x in ms if x["id"] == a), None)
        if not m:
            await query.answer("Not found", show_alert=True)
            text, kb = _methods()
            return await _edit(msg, text, kb)
        if act == "mt":
            m["on"] = not m.get("on")
            await botcfg.set("pay_methods", ms)
            await query.answer(_onoff(m["on"]))
        elif act == "md":
            await botcfg.set("pay_methods", [x for x in ms if x["id"] != a])
            await query.answer("Deleted 🗑")
            text, kb = _methods()
            return await _edit(msg, text, kb)
        else:
            await query.answer()
        text, kb = _method(a)
        return await _edit(msg, text, kb)

    if act == "madd":
        PENDING[uid] = {"kind": "m_" + a, "msg": msg}
        await query.answer()
        ask = ("<b>➕ UPI ID</b>\n\n<b>Send the UPI id</b>\n<b>Example:</b> <code>name@bank</code>" if a == "upi"
               else "<b>➕ QR CODE</b>\n\n<b>Send the QR as a photo</b> (or an image link).")
        return await _edit(msg, ask, _cancel("pm"))

    if act == "rn":
        PENDING[uid] = {"kind": "refer_num", "key": a, "msg": msg}
        await query.answer()
        return await _edit(msg, f"<b>✏️ Send a new number for {'friends needed' if a == 'refer_need' else 'reward days'} 👇</b>",
                           _cancel("ref"))


async def _done(message, prefix, text, kb):
    await message.reply_text(prefix + "\n\n" + text, reply_markup=kb, disable_web_page_preview=True)


@Client.on_message(filters.private & filters.user(ADMINS) & filters.text & ~filters.regex(r"^/"), group=-6)
async def adp_text(client, message):
    uid = message.from_user.id
    st = PENDING.get(uid)
    if not st:
        return
    txt = message.text.strip()
    kind = st["kind"]

    if kind == "plan_edit":
        plans = botcfg.get("plans")
        pl = next((x for x in plans if x["id"] == st["id"]), None)
        f = st["field"]
        if not pl:
            PENDING.pop(uid, None)
            raise StopPropagation
        if f == "badge":
            pl["badge"] = "" if txt == "-" else txt[:4]
        else:
            if not txt.isdigit() or int(txt) < 1 or int(txt) > (100000 if f == "price" else 3650):
                await message.reply_text("<b>❌ Send a valid number.</b>")
                raise StopPropagation
            pl[f] = int(txt)
        await botcfg.set("plans", plans)
        PENDING.pop(uid, None)
        text, kb = _plan(st["id"])
        await _done(message, "<b>✅ Saved</b>", text, kb)

    elif kind == "plan_add_days":
        if not txt.isdigit() or not (1 <= int(txt) <= 3650):
            await message.reply_text("<b>❌ Send days as a number.</b>")
            raise StopPropagation
        st.update(kind="plan_add_price", days=int(txt))
        await message.reply_text("<b>Step 2/2 — price in ₹?</b> (number)", reply_markup=_cancel("plans"))

    elif kind == "plan_add_price":
        if not txt.isdigit() or not (1 <= int(txt) <= 100000):
            await message.reply_text("<b>❌ Send price as a number.</b>")
            raise StopPropagation
        plans = botcfg.get("plans")
        plans.append({"id": "p" + uuid.uuid4().hex[:6], "days": st["days"], "price": int(txt), "on": True, "badge": ""})
        plans.sort(key=lambda x: x["days"])
        await botcfg.set("plans", plans)
        PENDING.pop(uid, None)
        text, kb = _plans()
        await _done(message, "<b>✅ Plan added</b>", text, kb)

    elif kind == "m_upi":
        if " " in txt or len(txt) < 3:
            await message.reply_text("<b>❌ Send a valid UPI id.</b>")
            raise StopPropagation
        ms = botcfg.get("pay_methods")
        ms.append({"id": "upi" + uuid.uuid4().hex[:5], "type": "upi", "value": txt, "on": True})
        await botcfg.set("pay_methods", ms)
        PENDING.pop(uid, None)
        text, kb = _methods()
        await _done(message, "<b>✅ UPI added</b>", text, kb)

    elif kind == "m_qr":
        if not txt.startswith("http"):
            await message.reply_text("<b>❌ Send the QR as a photo, or an image link starting with http.</b>")
            raise StopPropagation
        ms = botcfg.get("pay_methods")
        ms.append({"id": "qr" + uuid.uuid4().hex[:5], "type": "qr", "value": txt, "on": True})
        await botcfg.set("pay_methods", ms)
        PENDING.pop(uid, None)
        text, kb = _methods()
        await _done(message, "<b>✅ QR added</b>", text, kb)

    elif kind == "refer_num":
        if not txt.isdigit() or not (1 <= int(txt) <= 1000):
            await message.reply_text("<b>❌ Send a number (1-1000).</b>")
            raise StopPropagation
        await botcfg.set(st["key"], int(txt))
        PENDING.pop(uid, None)
        text, kb = _refer()
        await _done(message, "<b>✅ Saved</b>", text, kb)
    else:
        return
    raise StopPropagation


@Client.on_message(filters.private & filters.user(ADMINS) & filters.photo, group=-9)
async def adp_photo(client, message):
    uid = message.from_user.id
    st = PENDING.get(uid)
    if not st or st["kind"] != "m_qr":
        return
    ms = botcfg.get("pay_methods")
    ms.append({"id": "qr" + uuid.uuid4().hex[:5], "type": "qr", "value": message.photo.file_id, "on": True})
    await botcfg.set("pay_methods", ms)
    PENDING.pop(uid, None)
    text, kb = _methods()
    await _done(message, "<b>✅ QR added</b>", text, kb)
    raise StopPropagation
