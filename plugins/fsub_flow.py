from pyrogram import Client, filters

import fsub_ui


@Client.on_callback_query(filters.regex(r"^fsx#"))
async def fsx_cb(client, query):
    if query.data == "fsx#ok":
        return await query.answer("✅")
    if query.data == "fsx#how":
        return await fsub_ui.how(query)
    await fsub_ui.manual_check(client, query)
