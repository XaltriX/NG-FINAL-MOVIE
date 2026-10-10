"""
PREMIUM FLOW (user side + admin approval)
  Premium button -> plans -> pay (QR/UPI) -> "I have paid" -> screenshot -> admin Approve/Reject -> premium + notice
Callbacks: pr#...   (and the old premium_info / buy_info / reffff buttons)
"""
import logging

from pyrogram import Client, StopPropagation, enums, filters
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import payments
import premium_ui as ui
from info import ADMINS, OWNER_LNK
from languages import btn, get_lang, tr
from languages.ui import send_start
from utils import temp

logger = logging.getLogger(__name__)
HTML = enums.ParseMode.HTML

OLD_PREMIUM_CB = r"^(premium_info|buy_info|upi_info|star_info|give_trial|buy_\d+)$"


@Client.on_callback_query(filters.regex(OLD_PREMIUM_CB), group=-5)
async def old_buttons(client, query):
    await query.answer()
    lang = await get_lang(query.from_user.id)
    text, kb = await ui.premium_menu(query.from_user.id, lang)
    await ui.replace(client, query.message, text, kb)
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^(reffff|ref_point)$"), group=-5)
async def old_refer_buttons(client, query):
    await query.answer()
    lang = await get_lang(query.from_user.id)
    text, kb = await ui.refer_screen(query.from_user.id, lang)
    await ui.replace(client, query.message, text, kb)
    raise StopPropagation


def _admin_card(doc, user):
    name = user.mention if user else f"<code>{doc['user_id']}</code>"
    when = ui.fmt_dt(doc.get("submitted") or doc["created"])
    return (
        "<b>💳 NEW PAYMENT REQUEST</b>\n\n"
        f"<b>👤 User:</b> {name}\n"
        f"<b>🆔 ID:</b> <code>{doc['user_id']}</code>\n"
        f"<b>📦 Plan:</b> {ui.fmt_dur(doc['days'], 'en')}\n"
        f"<b>💰 Amount:</b> ₹{doc['price']}\n"
        f"<b>🕒 Time:</b> {when}\n"
        f"<b>🔖 Request:</b> <code>{doc['rid']}</code>"
    )


def _admin_kb(rid):
    return M([[B("✅ Approve", callback_data=f"pr#ok#{rid}"), B("❌ Reject", callback_data=f"pr#no#{rid}")]])


async def send_admin_card(client, admin_id, doc):
    try:
        user = await client.get_users(doc["user_id"])
    except Exception:
        user = None
    return await client.send_photo(admin_id, doc["shot_file"], caption=_admin_card(doc, user),
                                   reply_markup=_admin_kb(doc["rid"]), parse_mode=HTML)


@Client.on_callback_query(filters.regex(r"^pr#"))
async def pr_cb(client, query):
    uid = query.from_user.id
    p = query.data.split("#")
    act = p[1]
    arg = p[2] if len(p) > 2 else None
    lang = await get_lang(uid)
    msg = query.message

    if act == "close":
        await query.answer()
        try:
            return await msg.delete()
        except Exception:
            return

    if act == "menu":
        await query.answer()
        await payments.cancel_awaiting(uid)
        text, kb = await ui.premium_menu(uid, lang)
        return await ui.replace(client, msg, text, kb)

    if act == "ref":
        await query.answer()
        text, kb = await ui.refer_screen(uid, lang)
        return await ui.replace(client, msg, text, kb)

    if act == "p":                                  # plan chosen -> pay screen
        plan = ui.plan_by_id(arg)
        if not plan or not plan.get("on") or not ui.pay_methods():
            return await query.answer(ui_plain(tr("no_pay_method", lang)), show_alert=True)
        await query.answer()
        text, kb, photo = ui.pay_screen(plan, lang)
        return await ui.replace(client, msg, text, kb, photo=photo)

    if act == "paid":                               # "I have paid" -> ask for screenshot
        plan = ui.plan_by_id(arg)
        if not plan:
            return await query.answer("Plan not found", show_alert=True)
        if await payments.get_req(uid, "pending"):
            return await query.answer(ui_plain(tr("ss_pending_exists", lang)), show_alert=True)
        await query.answer()
        await payments.begin_payment(uid, plan)
        kb = M([[B(btn("btn_cancel", lang), callback_data="pr#menu")]])
        return await ui.replace(client, msg, tr("send_ss_prompt", lang), kb)

    if act in ("ok", "no"):                         # admin decision
        if uid not in ADMINS:
            return await query.answer("Only admins", show_alert=True)
        doc = await payments.decide(arg, act == "ok", uid)
        if not doc:
            return await query.answer("Already handled ✔️", show_alert=True)
        await query.answer("Approved ✅" if act == "ok" else "Rejected ❌")
        ulang = await get_lang(doc["user_id"])
        by = query.from_user.mention
        if act == "ok":
            until = await payments.grant_premium(doc["user_id"], doc["days"])
            note = tr("pay_approved", ulang, dur=ui.fmt_dur(doc["days"], ulang), until=ui.fmt_dt(until))
            result = f"\n\n<b>✅ APPROVED by {by}</b>\n<b>⏰ Till {ui.fmt_dt(until)}</b>"
            ukb = None
        else:
            note = tr("pay_rejected", ulang)
            result = f"\n\n<b>❌ REJECTED by {by}</b>"
            ukb = M([[B(btn("btn_try_again", ulang), callback_data="premium_info")],
                     [B(btn("btn_contact", ulang), url=OWNER_LNK)]])
        try:
            await client.send_message(doc["user_id"], note, reply_markup=ukb, parse_mode=HTML)
        except Exception as e:
            result += "\n<b>⚠️ Could not message the user (blocked bot?)</b>"
            logger.warning(f"notify user failed: {e}")
        # update every admin's copy so nobody taps it again
        base = msg.caption.html if msg.caption else ""
        for chat_id, mid in doc.get("admin_msgs", []):
            try:
                await client.edit_message_caption(chat_id, mid, (base or _admin_card(doc, None)) + result,
                                                  parse_mode=HTML, reply_markup=None)
            except Exception:
                pass
        try:
            from info import PREMIUM_LOGS
            await client.send_message(PREMIUM_LOGS,
                                      f"<b>#{'Premium_Approved' if act == 'ok' else 'Premium_Rejected'}</b>\n"
                                      f"<b>User:</b> <code>{doc['user_id']}</code> • ₹{doc['price']} • "
                                      f"{ui.fmt_dur(doc['days'], 'en')}\n<b>By:</b> {by}")
        except Exception:
            pass
        return


def ui_plain(html):
    import re
    return re.sub(r"<[^>]+>", "", html)[:190]


@Client.on_message(filters.private & (filters.photo | filters.document), group=-8)
async def screenshot(client, message):
    if not message.from_user:
        return
    uid = message.from_user.id
    awaiting = await payments.get_req(uid, "awaiting")
    pending = await payments.get_req(uid, "pending")
    if not awaiting and not pending:
        return                                       # normal file/photo -> other handlers
    lang = await get_lang(uid)
    if not awaiting:                                 # already has one under review
        await message.reply_text(tr("ss_pending_exists", lang), parse_mode=HTML,
                                 reply_markup=M([[B(btn("btn_contact_admin", lang), url=OWNER_LNK)]]))
        raise StopPropagation
    if message.photo:
        media = message.photo
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        media = message.document
    else:
        await message.reply_text(tr("ss_need_photo", lang), parse_mode=HTML)
        raise StopPropagation
    if await payments.shot_used(media.file_unique_id):
        await message.reply_text(tr("ss_duplicate", lang), parse_mode=HTML)
        raise StopPropagation
    # a document is sent as a document-photo? use file_id as is (send_photo accepts photo ids only) -> re-send as photo
    doc = await payments.submit_shot(awaiting["rid"], media.file_unique_id, media.file_id)
    if not doc:
        raise StopPropagation
    sent = []
    for admin in ADMINS:
        try:
            if message.photo:
                m = await send_admin_card(client, admin, doc)
            else:
                try:
                    user = await client.get_users(uid)
                except Exception:
                    user = None
                m = await client.send_document(admin, media.file_id, caption=_admin_card(doc, user),
                                               reply_markup=_admin_kb(doc["rid"]), parse_mode=HTML)
            sent.append([m.chat.id, m.id])
        except Exception as e:
            logger.warning(f"admin {admin} not reachable: {e}")
    if not sent:
        # nobody could be notified -> do not leave the user waiting forever
        await payments.req_col.update_one({"rid": doc["rid"]}, {"$set": {"status": "awaiting"}})
        await message.reply_text(tr("no_pay_method", lang), parse_mode=HTML)
        raise StopPropagation
    await payments.req_col.update_one({"rid": doc["rid"]}, {"$set": {"admin_msgs": sent}})
    await message.reply_text(tr("ss_received", lang) + "\n\n" + tr("ss_doubt", lang), parse_mode=HTML,
                             reply_markup=M([[B(btn("btn_contact_admin", lang), url=OWNER_LNK)]]))
    raise StopPropagation


@Client.on_message(filters.command(["plan", "premium"]) & filters.private)
async def plan_cmd(client, message):
    lang = await get_lang(message.from_user.id)
    await ui.send_premium_menu(client, message.chat.id, message.from_user.id, lang)


@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(client, message):
    uid = message.from_user.id
    lang = await get_lang(uid)
    exp = await payments.get_expiry(uid)
    if exp:
        text = tr("myplan_active", lang, until=ui.fmt_dt(exp))
        kb = M([[B(btn("btn_renew", lang), callback_data="premium_info")]])
    else:
        text = tr("myplan_none", lang)
        kb = M([[B(btn("btn_premium", lang), callback_data="premium_info")]])
    await message.reply_text(text, reply_markup=kb, parse_mode=HTML)


@Client.on_message(filters.command("pending") & filters.private & filters.user(ADMINS))
async def pending_cmd(client, message):
    rows = await payments.pending_list()
    if not rows:
        return await message.reply_text("<b>✅ No pending payments.</b>", parse_mode=HTML)
    for d in rows:
        try:
            m = await send_admin_card(client, message.chat.id, d)
            msgs = d.get("admin_msgs", []) + [[m.chat.id, m.id]]
            await payments.req_col.update_one({"rid": d["rid"]}, {"$set": {"admin_msgs": msgs}})
        except Exception as e:
            logger.warning(e)
