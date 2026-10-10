"""
Multi-language support.
  tr(key, lang, **fmt)      -> translated text (falls back to English, never raises)
  btn(key, lang, **fmt)     -> same, but Latin letters/digits become bold unicode (inline buttons can't use <b>)
  get_lang / set_lang       -> per-user language, cached, stored in users collection field `lang`
New texts: add the key to languages/en.py and to every other file (missing ones fall back to English).
"""
import datetime
from importlib import import_module

import pytz

# code, name (in its own script), flag/icon
LANGS = [
    ("en", "English", "🇬🇧"),
    ("hi", "हिन्दी", "🇮🇳"),
    ("ta", "தமிழ்", "🇮🇳"),
    ("kn", "ಕನ್ನಡ", "🇮🇳"),
    ("ml", "മലയാളം", "🇮🇳"),
    ("te", "తెలుగు", "🇮🇳"),
]
CODES = [c for c, _, _ in LANGS]
DEFAULT = "en"
LANG_NAMES = {c: n for c, n, _ in LANGS}

LANG_PICK_TEXT = (
    "<b>🌐 Choose your language</b>\n"
    "<b>अपनी भाषा चुनें</b>\n"
    "<b>உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்</b>\n"
    "<b>ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆರಿಸಿ</b>\n"
    "<b>നിങ്ങളുടെ ഭാഷ തിരഞ്ഞെടുക്കുക</b>\n"
    "<b>మీ భాషను ఎంచుకోండి</b>"
)

_S = {c: import_module(f"languages.{c}").S for c in CODES}


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def tr(key, lang=None, **fmt):
    text = _S.get(lang or DEFAULT, {}).get(key)
    if text is None:
        text = _S[DEFAULT].get(key, key)
    if fmt:
        try:
            return text.format_map(_Safe(fmt))
        except Exception:
            return text
    return text


def _bold_char(c):
    o = ord(c)
    if 65 <= o <= 90:
        return chr(0x1D5D4 + o - 65)
    if 97 <= o <= 122:
        return chr(0x1D5EE + o - 97)
    if 48 <= o <= 57:
        return chr(0x1D7EC + o - 48)
    return c


def ubold(text):
    return "".join(_bold_char(c) for c in text)


def btn(key, lang=None, **fmt):
    return ubold(tr(key, lang, **fmt))


def greeting(lang):
    h = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).hour
    k = "greet_morning" if h < 12 else "greet_afternoon" if h < 17 else "greet_evening" if h < 21 else "greet_night"
    return tr(k, lang)


# ---------------- per-user language (cache + DB) ----------------
from database.users_chats_db import db  # noqa: E402

_cache = {}


async def get_lang_raw(user_id):
    """None = user never chose a language."""
    uid = int(user_id)
    if uid in _cache:
        return _cache[uid]
    try:
        code = await db.get_user_lang(uid)
    except Exception:
        code = None
    if code not in CODES:
        code = None
    _cache[uid] = code
    return code


async def get_lang(user_id):
    return (await get_lang_raw(user_id)) or DEFAULT


async def set_lang(user_id, code):
    if code not in CODES:
        return False
    uid = int(user_id)
    await db.set_user_lang(uid, code)
    _cache[uid] = code
    return True
