"""Search result card: caption builder + button restyler (NeonGhost Network)."""
import re
import html
from pyrogram.types import InlineKeyboardButton
from languages import ubold

BRAND = "NeonGhost Network"
_SERIES_RE = re.compile(r"\bs\d{1,2}\b|\bs\d{1,2}\s?e\d{1,3}\b|\bseason\b|\bepisode\b|\be\d{2,3}\b", re.I)
_Q_RE = re.compile(r"\b(2160p|4k|1440p|1080p|720p|576p|480p|360p)\b", re.I)
_SE_RE = re.compile(r"\bS(\d{1,2})[\s._-]*E(\d{1,3})\b", re.I)
_LANGS = ["Hindi", "English", "Tamil", "Telugu", "Malayalam", "Kannada", "Bengali", "Punjabi", "Marathi",
          "Gujarati", "Urdu", "Korean", "Japanese", "Chinese", "Spanish", "French", "Dual", "Multi"]
_KEYCAP = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}

_last_series = [None]   # set by build_cap, consumed by restyle (same event-loop tick)
_last_sendall = [True]  # Send All only for premium/verified viewers


def is_series(search, names):
    if _SERIES_RE.search(search or ""):
        return True
    return any(_SERIES_RE.search(n or "") for n in names)


def _tags(name):
    parts = []
    m = _Q_RE.search(name)
    if m:
        parts.append("🎞 " + m.group(1).lower().replace("4k", "4K"))
    langs = [l for l in _LANGS if re.search(r"\b" + l, name, re.I)]
    if langs:
        parts.append("🌐 " + "+".join(langs[:3]))
    m = _SE_RE.search(name)
    if m:
        parts.append(f"📺 S{int(m.group(1)):02d}E{int(m.group(2)):02d}")
    return parts


def build_cap(search, files, total, secs, mention, chat_id, uname, start, size_fn, name_fn, footer="", send_all=True):
    title = str(search or "").strip().upper()
    if len(title) > 60:
        title = title[:59].rstrip() + "…"
    title = html.escape(title)
    _last_sendall[0] = bool(send_all)
    _last_series[0] = is_series(search, [f.file_name for f in files])
    try:
        secs_txt = f"{float(secs):.2f}"
        if not 0 <= float(secs) < 120:
            secs_txt = "0.50"
    except Exception:
        secs_txt = "0.50"
    cap = (
        f"<blockquote><b>🎬  {ubold(title)}</b></blockquote>\n"
        f"<b>📁 {ubold(str(total))} {ubold('Files')}   ⚡ {ubold(secs_txt)}{ubold('s')}   👤 {mention}</b>\n\n"
    )
    for i, f in enumerate(files, start=int(start)):
        num = _KEYCAP.get(i) or ubold(f"{i}.")
        link = f"https://telegram.me/{uname}?start=file_{chat_id}_{f.file_id}"
        tags = _tags(f.file_name)
        tags.append("💾 " + ubold(size_fn(f.file_size)))
        cap += (f"<blockquote><b>{num} <a href='{link}'>{html.escape(name_fn(f.file_name))}</a></b>\n"
                f"{' · '.join(tags)}</blockquote>\n")
    cap += f"\n⚜️ <b>{ubold('Powered By ' + BRAND)}</b>"
    if footer:
        cap += f"\n\n<b>{footer}</b>"
    return cap


def _header(key, series, send_all=True):
    rows = [[InlineKeyboardButton("🎞 " + ubold("Quality"), callback_data=f"qualities#{key}"),
             InlineKeyboardButton("🌐 " + ubold("Language"), callback_data=f"languages#{key}")]]
    if series:
        rows.append([InlineKeyboardButton("📺 " + ubold("Season"), callback_data=f"seasons#{key}"),
                     InlineKeyboardButton("🔢 " + ubold("Episode"), callback_data=f"episodes#{key}")])
    if send_all:
        rows.append([InlineKeyboardButton("📦 " + ubold("Send All"), callback_data=f"sendfiles#{key}")])
    return rows


def _pager(row):
    out, total_pages = [], None
    for b in row:
        t, cb = b.text or "", b.callback_data or ""
        m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", t)
        if m:
            total_pages = int(m.group(2))
            out.append(InlineKeyboardButton(ubold(f"{m.group(1)}/{m.group(2)}"), callback_data="pages"))
        elif "ɴᴇxᴛ" in t:
            out.append(InlineKeyboardButton(ubold("Next") + " ▶️", callback_data=cb))
        elif "ʙᴀᴄᴋ" in t:
            out.append(InlineKeyboardButton("◀️ " + ubold("Back"), callback_data=cb))
        elif t.strip() == "ᴘᴀɢᴇ":
            continue
        else:
            out.append(b)
    if total_pages == 1 or not out:
        return None
    return out


def restyle(rows):
    """Idempotent: only touches rows that look like a legacy result-card keyboard."""
    try:
        flat = [b for r in rows for b in r]
        cbs = [b.callback_data or "" for b in flat]
        qc = next((c for c in cbs if c.startswith("qualities#")), None)
        if not qc:
            return rows
        key = qc.split("#", 1)[1]
        series = _last_series[0]
        _last_series[0] = None
        send_all = _last_sendall[0]
        _last_sendall[0] = True
        if series is None:
            series = True
        out, done = [], False
        for r in rows:
            rc = [b.callback_data or "" for b in r]
            legacy = (any(c.startswith(("qualities#", "mtype#", "sendfiles#")) for c in rc)
                      or any((b.url or "").endswith("start=premium") for b in r))
            if legacy:
                if not done:
                    out += _header(key, series, send_all)
                    done = True
                continue
            if any(c.startswith("next_") or c == "pages" for c in rc):
                if any("ɴᴏ ᴍᴏʀᴇ" in (b.text or "") for b in r):
                    continue
                p = _pager(r)
                if p:
                    out.append(p)
                continue
            out.append(r)
        return out
    except Exception:
        return rows


_TITLE_CUT = re.compile(r"\b(2160p|1440p|1080p|720p|576p|480p|360p|4k|bluray|blu-ray|web-?dl|webrip|hdrip|hdtc|hdcam|dvdrip|x264|x265|hevc|s\d{1,2}e?\d{0,3})\b", re.I)


def file_caption(raw_name, size_text, brand_url):
    """Minimal file caption (design B): title • quality • language • size [• S01E03]."""
    name = (raw_name or "").strip()
    short = _TITLE_CUT.split(name, maxsplit=1)[0]
    short = re.sub(r"[._\-\[\]()]+", " ", short).strip() or re.sub(r"[._]+", " ", name)
    short = short[:60].rstrip().upper()
    tags = _tags(name)
    if size_text:
        tags.append("💾 " + ubold(size_text))
    return (f"<blockquote><b>🎬 {ubold(html.escape(short))}</b>\n{' · '.join(tags)}</blockquote>\n\n"
            f"⚜️ <b><a href=\"{brand_url}\">{ubold('Powered By ' + BRAND)}</a></b>")
