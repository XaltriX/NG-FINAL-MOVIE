"""Weekly trending list (Monday 12 AM IST -> next Monday), shared by /trendlist, /top_search and the Top searches button."""
import datetime
import html
import re

from languages import tr, ubold
from database.config_db import mdb

_OK = re.compile(r"^[a-zA-Z0-9 ]+$")


async def weekly_list(limit):
    seen, out = set(), []
    for q, n in await mdb.get_weekly(limit):
        if q in seen or not _OK.match(q):
            continue
        seen.add(q)
        out.append((q, n))
        if len(out) >= limit:
            break
    return out


def week_range():
    mon = datetime.datetime.strptime(mdb.week_start(), "%Y-%m-%d")
    sun = mon + datetime.timedelta(days=6)
    return mon.strftime("%d %b"), sun.strftime("%d %b")


async def weekly_text(limit, lang):
    rows = await weekly_list(limit)
    if not rows:
        return tr("tr_empty", lang), []
    a, b = week_range()
    lines = [f"<b>{tr('tr_title', lang)}</b>",
             f"<b>{tr('tr_sub', lang, a=a, b=b)}</b>", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, (q, n) in enumerate(rows, start=1):
        name = html.escape(q.title()[:32] + ("…" if len(q) > 32 else ""))
        lines.append(f"<b>{medals.get(i, str(i) + '.')} {name}</b>  •  🔍 {ubold(str(n))}")
    return "\n".join(lines), [q for q, _ in rows]
