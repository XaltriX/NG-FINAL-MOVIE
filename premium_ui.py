"""Premium + refer screens (used by plugins/premium_flow.py, commands.py, Premium.py)."""
import urllib.parse

import pytz
from pyrogram import enums
from pyrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import botcfg
import payments
from info import OWNER_LNK
from languages import tr, btn
from utils import temp

IST = pytz.timezone("Asia/Kolkata")
HTML = enums.ParseMode.HTML


def fmt_dt(naive_utc):
    return pytz.utc.localize(naive_utc).astimezone(IST).strftime("%d %b %Y, %I:%M %p")


def fmt_dur(days, lang):
    days = int(days)
    if days % 365 == 0:
        n, k = days // 365, "pl_year"
    elif days % 30 == 0:
        n, k = days // 30, "pl_month"
    else:
        n, k = days, "pl_day"
    return f"{n} {tr(k if n == 1 else k + 's', lang)}"


def active_plans():
    return [p for p in botcfg.get("plans") if p.get("on")]


def plan_by_id(pid):
    return next((p for p in botcfg.get("plans") if p["id"] == pid), None)


def plan_label(p, lang):
    badge = f"{p['badge']} " if p.get("badge") else ""
    return f"{badge}{fmt_dur(p['days'], lang)} ₹{p['price']}"


def pay_methods():
    return [m for m in botcfg.get("pay_methods") if m.get("on") and m.get("value")]


async def replace(client, message, text, kb, photo=None):
    """Show a screen in place of `message`. Text->text is edited, anything involving a photo is re-sent."""
    chat_id = message.chat.id
    if not photo and not message.media:
        try:
            return await message.edit_text(text, reply_markup=kb, parse_mode=HTML, disable_web_page_preview=True)
        except Exception as e:
            if "MESSAGE_NOT_MODIFIED" in str(e).upper():
                return message
    try:
        await message.delete()
    except Exception:
        pass
    if photo:
        try:
            return await client.send_photo(chat_id, photo, caption=text, reply_markup=kb, parse_mode=HTML)
        except Exception:
            pass   # bad photo (broken URL / file id) -> fall back to text only
    return await client.send_message(chat_id, text, reply_markup=kb, parse_mode=HTML, disable_web_page_preview=True)


# ---------------- premium menu ----------------
async def premium_menu(user_id, lang):
    if not botcfg.get("premium_on") or not active_plans() or not pay_methods():
        kb = M([[B(btn("btn_contact", lang), url=OWNER_LNK)],
                [B(btn("btn_back", lang), callback_data="start"), B(btn("btn_close", lang), callback_data="pr#close")]])
        return tr("no_pay_method", lang), kb
    exp = await payments.get_expiry(user_id)
    status = tr("premium_active_line", lang, until=fmt_dt(exp)) if exp else ""
    text = tr("premium_menu", lang, status=status)
    rows, row = [], []
    for p in active_plans():
        row.append(B(plan_label(p, lang), callback_data=f"pr#p#{p['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if botcfg.get("refer_on"):
        rows.append([B(btn("btn_refer", lang), callback_data="pr#ref")])
    rows.append([B(btn("btn_back", lang), callback_data="start"), B(btn("btn_close", lang), callback_data="pr#close")])
    return text, M(rows)


async def send_premium_menu(client, chat_id, user_id, lang):
    text, kb = await premium_menu(user_id, lang)
    await client.send_message(chat_id, text, reply_markup=kb, parse_mode=HTML)


# ---------------- payment screen ----------------
def pay_screen(plan, lang):
    """-> (text, kb, qr_photo_or_None)"""
    ms = pay_methods()
    lines, photo = [], None
    for m in ms:
        if m["type"] == "upi":
            lines.append(tr("pay_upi_line", lang, upi=m["value"]))
        elif m["type"] == "qr" and not photo:
            photo = m["value"]
            lines.append(tr("pay_qr_line", lang))
    text = tr("pay_screen", lang, price=plan["price"], dur=fmt_dur(plan["days"], lang), methods="\n".join(lines))
    kb = M([[B(btn("btn_paid", lang), callback_data=f"pr#paid#{plan['id']}")],
            [B(btn("btn_back", lang), callback_data="pr#menu"), B(btn("btn_close", lang), callback_data="pr#close")]])
    return text, kb, photo


# ---------------- refer ----------------
async def refer_screen(user_id, lang):
    if not botcfg.get("refer_on"):
        kb = M([[B(btn("btn_back", lang), callback_data="pr#menu")]])
        return tr("refer_off", lang), kb
    st = await payments.refer_stats(user_id)
    need, days = int(botcfg.get("refer_need")), int(botcfg.get("refer_days"))
    link = f"https://t.me/{temp.U_NAME}?start=reff_{user_id}"
    text = tr("refer_menu", lang, need=need, days=fmt_dur(days, lang), link=link,
              joined=st["joined"], qualified=st["qualified"], progress=st["progress"], rewards=st["rewards"])
    share = f"https://t.me/share/url?url={urllib.parse.quote(link)}&text={urllib.parse.quote(tr('refer_share_text', lang))}"
    kb = M([[B(btn("btn_share", lang), url=share)],
            [B(btn("btn_back", lang), callback_data="pr#menu"), B(btn("btn_close", lang), callback_data="pr#close")]])
    return text, kb
