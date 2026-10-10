"""Callback for the [Verify] button (logic lives in verifylib.py)."""
from pyrogram import Client, filters

import verifylib


@Client.on_callback_query(filters.regex(r"^vf#go$"))
async def verify_go(client, query):
    await verifylib.start_verification(client, query)
